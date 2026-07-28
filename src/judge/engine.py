"""판정 엔진.

★ 이 파일에는 LLM 호출이 없다. 있어서도 안 된다.
   judge(tree, profile) 는 동일 입력에 동일 출력을 보장한다.
   그 일치율을 tests/test_determinism.py 가 측정하고, 결과를 제출물에 포함한다.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.judge.predicate import Unknown, evaluate
from src.judge.schema import (
    Condition,
    ConditionResult,
    ConditionTree,
    UserProfile,
    Verdict,
)

ENGINE_VERSION = "1.0.0"


def _to_result(c: Condition, *, reason: str | None = None, full: bool = True) -> ConditionResult:
    return ConditionResult(
        id=c.id,
        label=c.label,
        severity=c.severity if full else None,
        remedy=c.remedy if full else None,
        evidence=c.evidence if full else None,
        reason=reason,
    )


def judge(
    tree: ConditionTree,
    profile: UserProfile,
    context: dict | None = None,
    *,
    today: date | None = None,
) -> Verdict:
    """조건 트리와 사용자 상태를 대조해 판정한다.

    분류
      unmet          미충족 (조건이 거짓)
      met            충족
      unknown        값을 알 수 없어 판정 불가 — 추측하지 않는다
      low_confidence 판정은 했으나 근거 추출에 해석이 개입함 (evidence.confidence == "low")
    """
    if context:
        # context 는 프로필을 덮어쓰지 않고 병합한다 (원본 불변)
        merged = profile.model_dump()
        merged["context"] = {**merged.get("context", {}), **context}
        profile = UserProfile.model_validate(merged)

    unmet: list[ConditionResult] = []
    met: list[ConditionResult] = []
    unknown: list[ConditionResult] = []
    low_conf: list[ConditionResult] = []

    for c in tree.conditions:
        try:
            ok = evaluate(c.predicate, profile, today=today)
        except Unknown as e:
            r = _to_result(c, reason=e.reason, full=False)
            r.severity = c.severity          # 판정 불가여도 중요도는 유지한다
            unknown.append(r)
            continue

        if ok:
            met.append(_to_result(c, full=False))
        else:
            unmet.append(_to_result(c))

        # high 가 아닌 근거는 별도로 표시한다.
        # 원문을 그대로 옮기지 못하고 해석이 개입했다면 사용자가 알아야 한다.
        if c.evidence.confidence != "high":
            low_conf.append(
                _to_result(c, reason=c.evidence.note or "근거 추출에 해석이 개입함", full=False)
            )

    # logic == "ALL"
    #   blocking 미충족이 하나라도 있으면        → blocked
    #   미충족은 없지만 blocking 조건을 모르면    → indeterminate  (추측해서 ok 를 주지 않는다)
    #   전부 확인했고 모두 충족                  → ok
    if any(r.severity == "blocking" for r in unmet):
        verdict = "blocked"
    elif any(r.severity == "blocking" for r in unknown):
        verdict = "indeterminate"
    else:
        verdict = "ok"

    return Verdict(
        goal_id=tree.goal_id,
        goal_label=tree.goal_label,
        verdict=verdict,
        unmet=unmet,
        met=met,
        unknown=unknown,
        low_confidence=low_conf,
        engine_version=ENGINE_VERSION,
        tree_collected_at=tree.source_meta.collected_at,
    )


# ── 로더 (테스트·API 공용) ─────────────────────────────────────────

def load_tree(path: str | Path) -> ConditionTree:
    return ConditionTree.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | Path) -> UserProfile:
    return UserProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))
