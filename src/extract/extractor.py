"""청크 → 조건 추출 (LLM).

★ 여기가 이 프로젝트에서 LLM 을 쓰는 두 곳 중 하나다 (다른 하나는 resolve/).
  판정(judge/)에는 절대 LLM 이 들어가지 않는다.

핵심 안전장치
  1. 스키마 강제  — pydantic 모델로 구조를 고정한다 (지어낸 필드가 들어올 수 없다)
  2. 인용 검증    — evidence_quote 가 원문 청크에 실제로 있는지 확인한다
                    없으면 폐기한다. 이것이 "근거 100%" 주장의 실질적 보증이다
  3. 경로 검증    — subject 가 허용 목록에 있는지 확인한다
  4. 캐싱        — 같은 (청크, 프롬프트) 재호출 금지. 비용 + 재현성

실행:
  python -m src.extract.extractor --dry-run          # 호출 없이 대상만 확인
  python -m src.extract.extractor --limit 3          # 3건만 실제 호출 (프롬프트 튜닝용)
  python -m src.extract.extractor --goal overseas_payment_online
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

from src.config import LLM_CACHE_DIR
from src.extract import prompt as P
from src.extract.candidates import select

MODEL = os.getenv("EXTRACT_MODEL", "")


# ── LLM 출력 스키마 (C1 의 Condition 과 1:1은 아니다. 평탄화해서 받는다) ──

class RemedyOut(BaseModel):
    actionable_in_app: bool
    channels: list[str] = Field(default_factory=list)
    primary_path: str | None = None
    note: str | None = None


class PredicateOut(BaseModel):
    subject: str
    op: str
    # OpenAI structured output 은 strict JSON Schema 를 요구한다.
    # `any` 타입(object)을 쓰면 400 (schema must have a 'type' key) 이 난다.
    # 그래서 값을 **JSON 리터럴 문자열**로 받고 우리가 파싱한다.
    #   예: "false" / "6000000" / "\"2029-05\"" / "{\"now_plus_days\": 0}"
    value_json: str


class ConditionOut(BaseModel):
    id: str
    label: str
    category: str
    predicate: PredicateOut
    severity: Literal["blocking", "warning"]
    remedy: RemedyOut
    evidence_quote: str
    confidence: Literal["high", "medium", "low"]
    note: str | None = None


class ExtractionOut(BaseModel):
    is_condition: bool
    conditions: list[ConditionOut] = Field(default_factory=list)


# ── 캐시 ──────────────────────────────────────────────────────────

def _cache_key(chunk_text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(P.SYSTEM_PROMPT.encode("utf-8"))   # 프롬프트가 바뀌면 캐시도 무효
    h.update(model.encode("utf-8"))
    h.update(chunk_text.encode("utf-8"))
    return h.hexdigest()[:24]


def _cache_get(key: str) -> ExtractionOut | None:
    path = LLM_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    return ExtractionOut.model_validate_json(path.read_text(encoding="utf-8"))


def _cache_put(key: str, value: ExtractionOut) -> None:
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (LLM_CACHE_DIR / f"{key}.json").write_text(
        value.model_dump_json(indent=2), encoding="utf-8"
    )


# ── 검증 ──────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s)


def validate(out: ExtractionOut, chunk_text: str) -> tuple[list[ConditionOut], list[str]]:
    """지어낸 인용·경로를 걸러낸다. 반환: (통과 조건, 폐기 사유 목록)"""
    kept: list[ConditionOut] = []
    rejected: list[str] = []
    src = _normalize(chunk_text)

    for c in out.conditions:
        # 1. 인용이 원문에 실제로 있는가  ★ 근거 100% 의 실질적 보증
        if _normalize(c.evidence_quote) not in src:
            rejected.append(f"{c.id}: 인용이 원문에 없음 — {c.evidence_quote[:40]}…")
            continue
        # 2. subject 가 허용 경로인가
        if c.predicate.subject not in P.ALLOWED_SUBJECTS:
            rejected.append(f"{c.id}: 허용되지 않은 subject — {c.predicate.subject}")
            continue
        # 3. op 가 허용 연산자인가
        if c.predicate.op not in P.ALLOWED_OPS:
            rejected.append(f"{c.id}: 허용되지 않은 op — {c.predicate.op}")
            continue
        # 4. value_json 이 유효한 JSON 인가
        try:
            json.loads(c.predicate.value_json)
        except (json.JSONDecodeError, TypeError):
            rejected.append(f"{c.id}: value_json 파싱 실패 — {c.predicate.value_json!r}")
            continue
        # 5. medium/low 인데 note 가 없으면 규칙 위반
        if c.confidence in ("medium", "low") and not (c.note or "").strip():
            rejected.append(f"{c.id}: confidence={c.confidence} 인데 note 없음")
            continue
        kept.append(c)

    return kept, rejected


# ── 추출 ──────────────────────────────────────────────────────────

def extract_one(chunk: dict, *, model: str, client) -> ExtractionOut:
    key = _cache_key(chunk["text"], model)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    completion = client.chat.completions.parse(
        model=model,
        temperature=0,                      # 재현성
        messages=[
            {"role": "system", "content": P.SYSTEM_PROMPT},
            {"role": "user", "content": P.build_user_prompt(
                chunk["text"], chunk.get("section", ""), chunk.get("goal", ""))},
        ],
        response_format=ExtractionOut,
    )
    msg = completion.choices[0].message
    if msg.parsed is None:
        raise RuntimeError(f"파싱 실패 (refusal: {msg.refusal})")

    _cache_put(key, msg.parsed)
    return msg.parsed


def run(goal: str | None, limit: int | None, dry_run: bool, grep: str | None = None) -> None:
    chunks = select(goal)
    if grep:
        # 프롬프트 튜닝용: 특정 키워드가 든 청크만 골라 소량으로 시험한다
        pat = re.compile(grep)
        chunks = [c for c in chunks if pat.search(c["text"])]
    if limit:
        chunks = chunks[:limit]

    print(f"대상 청크 {len(chunks)}개" + (f" (goal={goal})" if goal else ""))
    if dry_run:
        for c in chunks[:20]:
            print(f"  [{c['kind']:10s}] {c['text'][:100]}")
        print("\n--dry-run: LLM 호출 없음")
        return

    if not MODEL:
        raise SystemExit("EXTRACT_MODEL 환경변수를 설정하세요 (.env 참고)")

    from openai import OpenAI          # 여기서만 import — judge/ 는 openai 를 모른다
    client = OpenAI()

    kept_all: list[dict] = []
    rejected_all: list[str] = []

    for i, c in enumerate(chunks, 1):
        try:
            out = extract_one(c, model=MODEL, client=client)
        except Exception as e:                      # noqa: BLE001 — 한 건 실패가 전체를 막지 않게
            rejected_all.append(f"{c['chunk_id']}: 호출 실패 {e}")
            continue

        if not out.is_condition:
            continue

        kept, rejected = validate(out, c["text"])
        rejected_all.extend(f"{c['chunk_id']} / {r}" for r in rejected)
        for k in kept:
            kept_all.append({"chunk": c, "condition": k.model_dump()})

        print(f"  [{i}/{len(chunks)}] {c['chunk_id']}  조건 {len(kept)}개"
              + (f" (폐기 {len(rejected)})" if rejected else ""))

    print(f"\n추출 {len(kept_all)}건 / 폐기 {len(rejected_all)}건")
    if rejected_all:
        print("\n── 폐기 사유 (프롬프트 개선 힌트) ──")
        for r in rejected_all[:20]:
            print(f"  {r}")

    out_path = LLM_CACHE_DIR.parent / "extracted_conditions.json"
    out_path.write_text(json.dumps(kept_all, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--grep", default=None, help="이 정규식이 든 청크만 (프롬프트 튜닝용)")
    a = ap.parse_args()
    run(a.goal, a.limit, a.dry_run, a.grep)
