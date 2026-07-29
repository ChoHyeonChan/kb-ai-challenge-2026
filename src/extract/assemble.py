"""추출 결과 → 조건 트리 파일 (C1).

파이프라인의 마지막 칸이다.

  수집 → 청킹 → 추출(LLM) → 병합(규칙) → **검수(사람)** → 조립(이 파일) → data/trees/*.json
                                              ↑
                          승인된 조건만 트리에 들어간다. 미검수는 들어가지 않는다.

목표 이름·별칭은 문서에 적혀 있지 않으므로 `data/sources/goals.yaml` 에서 읽는다.

실행:
  python -m src.extract.assemble --dry-run     # 파일 쓰지 않고 결과만 확인
  python -m src.extract.assemble               # 트리 기록 + 미검수 목록 출력
"""
from __future__ import annotations

import argparse
import json
import os

import yaml

from src.config import DATA_DIR, SOURCES_FILE, TREES_DIR
from src.extract import review
from src.extract.merge import merge
from src.goals import load_goals
from src.judge.schema import Condition, ConditionTree, SourceMeta

EXTRACTED_FILE = DATA_DIR / "extracted_conditions.json"
PENDING_FILE = DATA_DIR / "review" / "pending.suggested.yaml"


# ── 입력 ──────────────────────────────────────────────────────────

def load_source_titles() -> dict[str, str]:
    """source_id → 문서 제목. 자동 수집분과 수동 확보분을 모두 포함한다."""
    cfg = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))
    entries = (cfg.get("targets") or []) + (cfg.get("manual") or [])
    return {e["id"]: e["title"] for e in entries}


def load_extracted() -> list[dict]:
    if not EXTRACTED_FILE.exists():
        raise SystemExit(f"{EXTRACTED_FILE} 이 없습니다. 먼저 `python -m src.extract.extractor` 실행")
    return json.loads(EXTRACTED_FILE.read_text(encoding="utf-8"))


# ── 조립 ──────────────────────────────────────────────────────────

def build_tree(goal_id: str, conditions: list[Condition], goals: dict[str, dict]) -> ConditionTree:
    meta = goals.get(goal_id)
    if meta is None:
        raise SystemExit(f"goals.yaml 에 '{goal_id}' 정의가 없습니다")

    # 수집 일자는 근거로 쓰는 문서 중 **가장 오래된** 것을 적는다.
    # 약관은 개정되므로, 트리의 유효성은 가장 낡은 근거에 좌우된다.
    collected = min((c.evidence.collected_at for c in conditions), default="")
    sources = {sid for c in conditions for sid in (c.provenance.source_ids if c.provenance else [])}

    return ConditionTree(
        goal_id=goal_id,
        goal_label=meta["label"],
        aliases=meta.get("aliases", []),
        domain=meta.get("domain", ""),
        conditions=conditions,
        source_meta=SourceMeta(
            collected_at=collected,
            extractor_version=f"llm:{os.getenv('EXTRACT_MODEL', '?')}+merge-1.0+review",
            source_count=len(sources),
        ),
    )


# ── 출력 ──────────────────────────────────────────────────────────

def _line(c: Condition) -> str:
    app = "앱O" if c.remedy.actionable_in_app else "앱X"
    sup = c.provenance.support_count if c.provenance else 1
    return (f"   [{c.severity:8s}] [{c.category:11s}] [{app}] x{sup:<2d} {c.label}\n"
            f"        {c.predicate.subject} {c.predicate.op} "
            f"{json.dumps(c.predicate.value, ensure_ascii=False)}  · {c.evidence.confidence}")


def _print_goal(goal_id: str, raw: int, approved, rejected, pending, notes: list[str]) -> None:
    print(f"\n■ {goal_id} — 추출 {raw}건 → 병합 {len(approved)+len(rejected)+len(pending)}개 "
          f"→ 승인 {len(approved)} / 반려 {len(rejected)} / 미검수 {len(pending)}")
    for c in approved:
        print(_line(c))
    for c, why in rejected:
        print(f"   [반려] {c.label}  ← {why}")
    for c in pending:
        print(f"   [미검수] {c.label}")
    for n in notes:
        print(f"   ⚠ {n}")


def run(dry_run: bool) -> None:
    goals = load_goals()
    titles = load_source_titles()

    by_goal: dict[str, list[dict]] = {}
    for it in load_extracted():
        by_goal.setdefault(it["chunk"]["goal"], []).append(it)

    pending_blocks: list[str] = []

    for goal_id in sorted(by_goal):
        conditions, notes = merge(by_goal[goal_id], titles, review.evidence_picks(goal_id))
        approved, rejected, pending = review.split(goal_id, conditions)
        _print_goal(goal_id, len(by_goal[goal_id]), approved, rejected, pending, notes)

        if pending:
            pending_blocks.append(f"  # ===== {goal_id} =====\n{review.format_pending(goal_id, pending)}")

        if dry_run:
            continue
        tree = build_tree(goal_id, approved, goals)
        path = TREES_DIR / f"{goal_id}.json"
        path.write_text(
            json.dumps(tree.model_dump(exclude_none=True), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"   → {path}")

    for goal_id in sorted(set(goals) - set(by_goal)):
        print(f"\n⚠ {goal_id}: 추출된 조건이 0건입니다. 원문 수집 상태를 확인하세요")

    _write_pending(pending_blocks, dry_run)


def _write_pending(blocks: list[str], dry_run: bool) -> None:
    if not blocks:
        print("\n미검수 조건 없음")
        return
    if dry_run:
        print("\n--dry-run: 파일을 쓰지 않았습니다")
        return

    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(
        "# 자동 생성 — 검수 대기 조건. 판단한 항목을 decisions.yaml 로 옮긴다.\n"
        "# 이 파일을 직접 고치지 말 것 (assemble 실행 때마다 덮어쓴다).\n"
        "decisions:\n" + "\n".join(blocks) + "\n",
        encoding="utf-8",
    )
    print(f"\n검수 대기 → {PENDING_FILE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(ap.parse_args().dry_run)
