"""판정 엔진.

★ 이 파일에는 LLM 호출이 없다. 있어서도 안 된다.
  judge(tree, profile) 는 동일 입력에 동일 출력을 보장한다.
  그 일치율을 tests/test_determinism.py 가 측정하고, 결과를 제출물에 포함한다.
"""
from __future__ import annotations

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


# ── 분류 결과 컨테이너 ────────────────────────────────────────────

class _Buckets:
    """조건을 네 갈래로 나눠 담는다: 미충족 / 충족 / 불명 / 해석개입."""

    def __init__(self) -> None:
        self.unmet: list[ConditionResult] = []
        self.met: list[ConditionResult] = []
        self.unknown: list[ConditionResult] = []
        self.not_applicable: list[ConditionResult] = []
        self.low_confidence: list[ConditionResult] = []


def _to_result(c: Condition, *, reason: str | None = None, full: bool = True) -> ConditionResult:
    return ConditionResult(
        id=c.id,
        label=c.label,
        severity=c.severity if full else None,
        remedy=c.remedy if full else None,
        evidence=c.evidence if full else None,
        reason=reason,
        # 적용 범위는 요약(full=False)에서도 내린다 — 조건을 좁히는 말이라,
        # 빠지면 화면이 조건을 실제보다 넓게 말하게 된다.
        scope_note=c.scope_note,
        provenance=c.provenance if full else None,
    )


# ── 단계별 함수 ───────────────────────────────────────────────────

def _with_context(profile: UserProfile, context: dict | None) -> UserProfile:
    """context 를 프로필에 병합한다. 원본은 건드리지 않는다."""
    if not context:
        return profile
    merged = profile.model_dump()
    merged["context"] = {**merged.get("context", {}), **context}
    return UserProfile.model_validate(merged)


def _classify(tree: ConditionTree, profile: UserProfile, today: date | None) -> _Buckets:
    """각 조건을 평가해 네 갈래로 분류한다."""
    b = _Buckets()
    for c in tree.conditions:
        # ① 이 조건이 이 사용자에게 걸리기는 하는가.
        #    인용이 "체크카드의 경우"라고 대상을 한정했는데 조건을 모두에게 걸면,
        #    조건이 인용보다 넓어진다. 실제로 신용카드 사용자에게 체크카드 전용
        #    한도 2개가 '충족'으로 집계되고 있었다 — 통과시켜도 틀린 말이다.
        if c.applies_when is not None:
            try:
                if not evaluate(c.applies_when, profile, today=today):
                    b.not_applicable.append(_to_result(c, full=False))
                    continue
            except Unknown as e:
                # 걸리는지조차 모르면 조건도 모르는 것이다. 추측하지 않는다.
                r = _to_result(c, reason=f"적용 대상인지 확인하지 못했습니다 — {e.reason}", full=False)
                r.severity = c.severity
                b.unknown.append(r)
                continue

        try:
            ok = evaluate(c.predicate, profile, today=today)
        except Unknown as e:
            r = _to_result(c, reason=e.reason, full=False)
            r.severity = c.severity          # 판정 불가여도 중요도는 유지한다
            b.unknown.append(r)
            continue

        (b.met if ok else b.unmet).append(_to_result(c, full=not ok))

        # high 가 아닌 근거는 별도 표시한다.
        # 원문을 그대로 옮기지 못하고 해석이 개입했다면 사용자가 알아야 한다.
        if c.evidence.confidence != "high":
            b.low_confidence.append(
                _to_result(c, reason=c.evidence.note or "근거 추출에 해석이 개입함", full=False)
            )
    return b


def _decide(b: _Buckets) -> str:
    """logic == "ALL" 기준 최종 판정.

    blocking 미충족이 있으면              → blocked
    미충족은 없지만 blocking 조건을 모르면 → indeterminate (추측해서 ok 를 주지 않는다)
    전부 확인했고 모두 충족               → ok
    """
    if any(r.severity == "blocking" for r in b.unmet):
        return "blocked"
    if any(r.severity == "blocking" for r in b.unknown):
        return "indeterminate"
    return "ok"


# ── 공개 API ──────────────────────────────────────────────────────

def judge(
    tree: ConditionTree,
    profile: UserProfile,
    context: dict | None = None,
    *,
    today: date | None = None,
) -> Verdict:
    """조건 트리와 사용자 상태를 대조해 판정한다."""
    b = _classify(tree, _with_context(profile, context), today)
    return Verdict(
        goal_id=tree.goal_id,
        goal_label=tree.goal_label,
        verdict=_decide(b),
        unmet=b.unmet,
        met=b.met,
        unknown=b.unknown,
        not_applicable=b.not_applicable,
        low_confidence=b.low_confidence,
        engine_version=ENGINE_VERSION,
        tree_collected_at=tree.source_meta.collected_at,
    )


# ── 로더 (테스트·API 공용) ─────────────────────────────────────────

def load_tree(path: str | Path) -> ConditionTree:
    return ConditionTree.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | Path) -> UserProfile:
    return UserProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))
