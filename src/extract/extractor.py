"""청크 → 조건 추출 (LLM).

★ 여기가 이 프로젝트에서 LLM 을 쓰는 두 곳 중 하나다 (다른 하나는 resolve/).
  판정(judge/)에는 절대 LLM 이 들어가지 않는다.

핵심 안전장치
  1. 스키마 강제  — pydantic 모델로 구조를 고정한다 (지어낸 필드가 들어올 수 없다)
  2. 검증 게이트  — `validate.py` 에서 인용·경로·값·신뢰도를 확인한다
  3. 캐싱        — 같은 (목표, 청크, 프롬프트) 재호출 금지. 비용 + 재현성

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
from src.extract.validate import validate
from src.goals import label_of

MODEL = os.getenv("EXTRACT_MODEL", "")


# ── LLM 출력 스키마 (C1 의 Condition 과 1:1은 아니다. 평탄화해서 받는다) ──

class RemedyOut(BaseModel):
    # 세 값이다. 스키마가 bool 만 받으면 모델은 모를 때도 반드시 하나를 고르게 되고,
    # 그 결과 프롬프트 예시를 베낀 해결 방법이 들어왔다.
    actionable_in_app: bool | None = None
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


# ── 추출 ──────────────────────────────────────────────────────────

def extract_one(chunk: dict, *, model: str, client) -> ExtractionOut:
    # 목표가 다르면 같은 문장에서 뽑아야 할 조건도 달라진다 → 캐시 키에 목표를 포함한다
    key = _cache_key(f"{chunk.get('goal', '')}\n{chunk['text']}", model)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    completion = client.chat.completions.parse(
        model=model,
        temperature=0,                      # 재현성
        messages=[
            {"role": "system", "content": P.SYSTEM_PROMPT},
            {"role": "user", "content": P.build_user_prompt(
                chunk["text"], chunk.get("section", ""), label_of(chunk.get("goal", "")))},
        ],
        response_format=ExtractionOut,
    )
    msg = completion.choices[0].message
    if msg.parsed is None:
        raise RuntimeError(f"파싱 실패 (refusal: {msg.refusal})")

    _cache_put(key, msg.parsed)
    return msg.parsed


def _pick_chunks(goal: str | None, limit: int | None, grep: str | None) -> list[dict]:
    chunks = select(goal)
    if grep:
        # 프롬프트 튜닝용: 특정 키워드가 든 청크만 골라 소량으로 시험한다
        pat = re.compile(grep)
        chunks = [c for c in chunks if pat.search(c["text"])]
    return chunks[:limit] if limit else chunks


def _extract_all(chunks: list[dict], client) -> tuple[list[dict], list[str], int]:
    kept_all: list[dict] = []
    rejected_all: list[str] = []
    fitted = 0

    for i, c in enumerate(chunks, 1):
        try:
            out = extract_one(c, model=MODEL, client=client)
        except Exception as e:                      # noqa: BLE001 — 한 건 실패가 전체를 막지 않게
            rejected_all.append(f"{c['chunk_id']}: 호출 실패 {e}")
            continue

        if not out.is_condition:
            continue

        kept, rejected = validate(out, c["text"])
        fitted += sum(1 for k in kept if "인용 자동 보정" in (k.note or ""))

        rejected_all.extend(f"{c['chunk_id']} / {r}" for r in rejected)
        kept_all.extend({"chunk": c, "condition": k.model_dump()} for k in kept)

        print(f"  [{i}/{len(chunks)}] {c['chunk_id']}  조건 {len(kept)}개"
              + (f" (폐기 {len(rejected)})" if rejected else ""))

    return kept_all, rejected_all, fitted


def _report(kept: list[dict], rejected: list[str], fitted: int) -> None:
    print(f"\n추출 {len(kept)}건 / 폐기 {len(rejected)}건 / 인용 자동 보정 {fitted}건")
    if rejected:
        print("\n── 폐기 사유 (프롬프트 개선 힌트) ──")
        for r in rejected[:20]:
            print(f"  {r}")

    out_path = LLM_CACHE_DIR.parent / "extracted_conditions.json"
    out_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path}")


def run(goal: str | None, limit: int | None, dry_run: bool, grep: str | None = None) -> None:
    chunks = _pick_chunks(goal, limit, grep)
    print(f"대상 청크 {len(chunks)}개" + (f" (goal={goal})" if goal else ""))

    if dry_run:
        for c in chunks[:20]:
            print(f"  [{c['kind']:10s}] {c['text'][:100]}")
        print("\n--dry-run: LLM 호출 없음")
        return

    if not MODEL:
        raise SystemExit("EXTRACT_MODEL 환경변수를 설정하세요 (.env 참고)")

    from openai import OpenAI          # 여기서만 import — judge/ 는 openai 를 모른다

    _report(*_extract_all(chunks, OpenAI()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--grep", default=None, help="이 정규식이 든 청크만 (프롬프트 튜닝용)")
    a = ap.parse_args()
    run(a.goal, a.limit, a.dry_run, a.grep)
