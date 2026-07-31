"""해결 시뮬레이션 — "하나만 풀면 어떻게 되나".

★ 이 파일에도 LLM 은 없다. 판정 결과(C3)만 가지고 계산한다.

왜 필요한가
  이 프로젝트는 한 사람의 실제 경험에서 시작했다.
    "해외결제를 풀려고 카드 설정에 들어갔다. 하나 풀어서 되나 했는데 안 되고,
     하나 더 풀 게 있더라. 어디 있는지 몰라서 검색했다."
  조건을 나열해 주는 것만으로는 이 경험이 해결되지 않는다.
  **하나를 풀어도 여전히 막힌다는 사실**을 미리 말해줘야 한다.

무엇을 계산하나
  1. 반드시 해결해야 하는 것 / 해도 되고 안 해도 되는 것 (severity 기준)
  2. 앱에서 되는 것 / 창구에 가야 하는 것
  3. "이것만 해결하면?" 각각의 결과
  4. 전부 해결해도 도달할 수 있는 최선 — 모르는 값이 남으면 여전히 "된다"고 말할 수 없다

어떻게 계산하나 (중요)
  가상의 프로필을 만들어 값을 지어내지 않는다. **"이 조건이 충족됐다고 치면"** 이라는
  집합 연산만 한다. 값을 지어내면 그 값이 맞는지 아무도 보증할 수 없고,
  "모르는 건 모른다"는 원칙과도 어긋난다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.judge.schema import ConditionResult, Verdict

Outcome = Literal["ok", "blocked", "indeterminate"]


# ── C4 계약 (judge/ 가 생산 → api/ → web/ 이 소비) ────────────────

class WhatIf(BaseModel):
    """'이것들을 해결하면 어떻게 되나' 한 줄.

    scope 와 result 를 나눠 담는다. 조건 label 이 "~해야 합니다"로 끝나기 때문에
    한 문장으로 이으면 어법이 깨진다. 화면에서 `scope → result` 로 붙여 보여준다.
    """
    fixed_ids: list[str]
    scope: str = Field(description="무엇을 해결했다고 가정했는가")
    result: str = Field(description="그러면 어떻게 되는가")
    outcome: Outcome
    remaining_blocking: int = 0
    remaining_unknown: int = 0


class Plan(BaseModel):
    """해결 계획 + 시뮬레이션 결과."""
    goal_id: str
    must_fix: list[ConditionResult] = Field(default_factory=list)
    optional_fix: list[ConditionResult] = Field(default_factory=list)
    in_app_ids: list[str] = Field(default_factory=list)
    needs_visit_ids: list[str] = Field(default_factory=list)
    unsure_path_ids: list[str] = Field(
        default_factory=list,
        description="해결 채널이 수집한 문서에서 확인되지 않은 조건. '영업점에 가라'고 말하지 않는다",
    )
    what_ifs: list[WhatIf] = Field(default_factory=list)
    final_outcome: Outcome = "ok"
    final_note: str | None = None
    summary: str = ""


# ── 계산 ──────────────────────────────────────────────────────────

def _outcome(verdict: Verdict, fixed: set[str]) -> tuple[Outcome, int, int]:
    """fixed 에 든 조건이 충족됐다고 가정했을 때의 판정. engine._decide 와 같은 규칙."""
    blocking = [r for r in verdict.unmet if r.severity == "blocking" and r.id not in fixed]
    unknown = [r for r in verdict.unknown if r.severity == "blocking" and r.id not in fixed]
    if blocking:
        return "blocked", len(blocking), len(unknown)
    if unknown:
        return "indeterminate", 0, len(unknown)
    return "ok", 0, 0


def _result_text(outcome: Outcome, blocking: int, unknown: int) -> str:
    if outcome == "blocked":
        return f"여전히 안 됩니다 · 필수 조건 {blocking}개 남음"
    if outcome == "indeterminate":
        return f"막는 조건은 없음 · 판정에 필요한 값 {unknown}개 미확인"
    return "됩니다"


def _step(verdict: Verdict, targets: list[ConditionResult], scope: str | None = None) -> WhatIf:
    fixed = {r.id for r in targets}
    outcome, blocking, unknown = _outcome(verdict, fixed)
    return WhatIf(
        fixed_ids=sorted(fixed),
        scope=scope or (targets[0].label if len(targets) == 1 else f"{len(targets)}개 모두"),
        result=_result_text(outcome, blocking, unknown),
        outcome=outcome,
        remaining_blocking=blocking,
        remaining_unknown=unknown,
    )


# actionable_in_app 은 세 값이다. is True / is False 로 명시해서 읽는다 —
# None(모름)을 falsy 로 흘리면 "앱에서 안 된다"고 주장하게 된다.
def _is(results: list[ConditionResult], value: bool | None) -> list[ConditionResult]:
    return [r for r in results
            if (r.remedy.actionable_in_app if r.remedy else None) is value]


def _grouped_steps(verdict: Verdict, must: list[ConditionResult]) -> list[WhatIf]:
    """채널별 묶음 — '앱에서 할 수 있는 것만 다 하면?' 이 가장 중요한 질문이다."""
    in_app = _is(must, True)
    if 1 < len(in_app) < len(must):
        return [_step(verdict, in_app, scope="앱에서 할 수 있는 것 모두")]
    return []


def _summary(must: list[ConditionResult], visit: list[str], unsure: list[str],
             final: Outcome, unknown: int) -> str:
    if not must:
        if final == "indeterminate":
            return (f"막고 있는 조건은 찾지 못했습니다. 다만 판정에 필요한 값 {unknown}개를 "
                    f"알 수 없어 된다고 답하지는 않습니다.")
        return "지금 막고 있는 조건은 없습니다."

    if len(must) == 1:
        head = "아래 1개만 해결하면 됩니다."
        if visit:
            head += " 다만 이것은 앱에서 해결할 수 없습니다."
    else:
        head = f"{len(must)}개를 모두 해결해야 합니다. 하나만 해결하면 여전히 막힙니다."
        if visit:
            head += f" 그중 {len(visit)}개는 앱 밖에서 해결해야 합니다."
    # 해결 채널을 모르는 조건은 "영업점에 가라"고 말하지 않는다. 모른다고 말한다.
    if unsure:
        head += (f" {len(unsure)}개는 어디서 해결하는지 수집한 문서에서 찾지 못해 "
                 f"안내드리지 못합니다.")
    if final == "indeterminate":
        head += " 전부 해결해도 판정에 필요한 값이 남아 '됩니다'라고 단정하지는 않습니다."
    return head


def simulate(verdict: Verdict) -> Plan:
    """판정 결과 → 해결 계획. 같은 판정이면 언제나 같은 계획이 나온다."""
    must = [r for r in verdict.unmet if r.severity == "blocking"]
    optional = [r for r in verdict.unmet if r.severity != "blocking"]

    in_app = [r.id for r in _is(must, True)]
    needs_visit = [r.id for r in _is(must, False)]
    unsure = [r.id for r in _is(must, None)]      # 해결 채널이 확인되지 않은 것

    what_ifs: list[WhatIf] = []
    if len(must) > 1:
        what_ifs += [_step(verdict, [r]) for r in must]        # 하나씩 풀어보기
        what_ifs += _grouped_steps(verdict, must)
    if must:
        what_ifs.append(_step(verdict, must))                  # 전부 풀어보기

    final, _, unknown = _outcome(verdict, {r.id for r in must})

    return Plan(
        goal_id=verdict.goal_id,
        must_fix=must,
        optional_fix=optional,
        in_app_ids=in_app,
        needs_visit_ids=needs_visit,
        what_ifs=what_ifs,
        final_outcome=final,
        final_note=(f"판정에 필요한 값 {unknown}개가 확인되지 않았습니다. 그 값을 알기 전에는 "
                    f"된다고 답하지 않습니다." if final == "indeterminate" else None),
        unsure_path_ids=unsure,
        summary=_summary(must, needs_visit, unsure, final, unknown),
    )
