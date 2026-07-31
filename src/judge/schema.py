"""C1/C2/C3 계약의 단일 출처.

이 파일이 세 사람의 접점이다. 필드를 바꾸면 남의 코드가 깨진다 — 합의 후 변경할 것.

설계 의도
  - evidence 필수        → 근거 없는 조건은 존재할 수 없다 (근거 표시율 100% 구조적 보장)
  - confidence           → 해석이 개입한 조건은 신뢰도를 낮춰 표시한다
  - actionable_in_app    → 앱에서 못 고치는 조건을 데이터로 구분한다 (안심차단이 false).
                           **근거로 확인되지 않으면 None** — 아래 remedy.basis 참조
  - unknown / low_confidence → 모르는 건 모른다고 한다
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ─────────────────────────────── 공통 ───────────────────────────────

Severity = Literal["blocking", "warning"]
Confidence = Literal["high", "medium", "low"]
Category = Literal["setting", "document", "limit", "temporal", "eligibility"]

Op = Literal[
    # 동등·포함
    "eq", "neq", "in", "not_in",
    # 수치
    "gte", "lte", "gt", "lt",
    # 존재
    "exists", "not_exists",
    # 시간
    "date_after", "date_before",
    "within_days", "not_within_days",
    # 횟수
    "count_lte", "count_gte",
]


class Evidence(BaseModel):
    """근거. 모든 조건에 필수."""
    source_title: str
    url: str
    quote: str = Field(description="원문 문장 그대로. 요약하지 않는다")
    collected_at: str = Field(description="YYYY-MM-DD. 약관은 개정된다")
    confidence: Confidence = "high"
    note: str | None = Field(default=None, description="해석이 개입했다면 무엇을 어떻게 옮겼는지")


# 이 remedy 를 무엇이 뒷받침하는가. 근거가 없으면 아예 비운다.
#
# 이 필드가 없던 동안 LLM 이 해결 방법을 지어냈다. 근거 원문에는 한도 '수치'만
# 있는데 "앱에서 한도 조정"이 붙는 식이었다(프롬프트 예시가 그대로 새어나왔다).
# 조건·상태·판정에서는 "모르면 모른다"를 지켰으면서 remedy 에서만 빠져 있었다.
RemedyBasis = Literal["evidence", "measured", "self_evident"]


class Remedy(BaseModel):
    """미충족일 때 무엇을 해야 하는가.

    **모르면 비운다.** actionable_in_app 이 None 이면 "앱에서 되는지 확인되지 않음"이며,
    되지 않는다는 뜻이 아니다. 둘을 섞으면 근거 없는 주장을 하게 된다.
    """
    actionable_in_app: bool | None = Field(
        default=None,
        description="앱에서 해결 가능한가. 근거로 확인되지 않으면 None(모름). 추측하지 않는다",
    )
    channels: list[str] = Field(default_factory=list, description='예: ["app:KB Pay", "branch:영업점"]')
    primary_path: str | None = None
    note: str | None = None
    basis: RemedyBasis | None = Field(
        default=None,
        description=(
            "evidence=근거 원문에 채널이 명시됨 / "
            "measured=앱에서 직접 확인(eval/results/kbpay_hands_on.md) / "
            "self_evident=조건 자체로 자명(실물 카드 등). "
            "None 이면 actionable_in_app 도 None 이어야 한다"
        ),
    )


class Predicate(BaseModel):
    """LLM이 만들고, 규칙 엔진이 평가한다. LLM은 평가에 관여하지 않는다."""
    subject: str = Field(description='프로필 경로. 예: "card.overseas_block_online"')
    op: Op
    value: Any = Field(default=None, description='리터럴 | {"ref": "..."} | {"now_plus_days": N} | {"days": N, "n": M}')


class Provenance(BaseModel):
    """이 조건이 어느 청크에서 몇 번 확인됐는가. 병합 단계(extract/assemble)가 채운다.

    판정에는 쓰이지 않는다. 같은 조건이 여러 문서에서 반복 확인됐다는 사실 자체가
    추출 신뢰도의 근거이므로, 트리 파일만 열어도 보이도록 남긴다.
    """
    support_count: int = 1
    chunk_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Condition(BaseModel):
    id: str
    label: str = Field(description="사용자에게 그대로 보여줄 문장")
    category: Category
    predicate: Predicate
    severity: Severity = "blocking"
    remedy: Remedy
    evidence: Evidence
    scope_note: str | None = None
    provenance: Provenance | None = None   # 수기 시드 트리에는 없다 → 선택 필드
    review_override: str | None = Field(
        default=None,
        description="검수에서 사람이 교정한 내용과 사유. 손댄 곳을 감추지 않기 위해 트리에 남긴다",
    )


class SourceMeta(BaseModel):
    collected_at: str
    extractor_version: str = "0.1.0"
    source_count: int = 0


class ConditionTree(BaseModel):
    """C1 — extract/ 가 생산하고 judge/ 가 소비한다."""
    schema_version: str = "1.0"
    goal_id: str
    goal_label: str
    aliases: list[str] = Field(default_factory=list, description="RAG 목표 식별용 자연어 표현")
    domain: str = ""
    logic: Literal["ALL"] = "ALL"
    conditions: list[Condition]
    source_meta: SourceMeta


# ─────────────────────────────── C2 ───────────────────────────────

class UserProfile(BaseModel):
    """C2 — 데모용 가상 사용자 상태.

    알 수 없는 값은 None 으로 둔다. 추측해서 채우지 않는다.
    None 인 조건은 판정에서 unknown 으로 분류된다.
    """
    model_config = {"extra": "allow"}   # 도메인별 필드 추가를 허용

    profile_id: str
    description: str = ""
    card: dict[str, Any] = Field(default_factory=dict)
    account: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    def lookup(self, path: str) -> tuple[Any, bool]:
        """subject 경로로 값을 찾는다. 반환: (값, 알고있음 여부)"""
        cur: Any = self.model_dump()
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None, False        # 경로 자체가 없음 → 모름
            cur = cur[part]
        return cur, cur is not None       # None 이면 모름


# ─────────────────────────────── C3 ───────────────────────────────

class ConditionResult(BaseModel):
    id: str
    label: str
    severity: Severity | None = None
    remedy: Remedy | None = None
    evidence: Evidence | None = None
    reason: str | None = Field(default=None, description="unknown/low_confidence 사유")
    provenance: Provenance | None = Field(
        default=None,
        description="근거가 몇 개 문서에서 확인됐는가. 화면이 '문서 N곳에서 확인'을 표시하는 데 쓴다",
    )


class Verdict(BaseModel):
    """C3 — judge/ 가 생산하고 api/ → web/ 이 소비한다.

    verdict 3값
      blocked        blocking 조건이 미충족 → 지금은 안 된다
      indeterminate  미충족은 없지만 **판정에 필요한 값을 몰라** 된다고 말할 수 없다
      ok             blocking 조건을 전부 확인했고 모두 충족

    ★ indeterminate 가 있는 이유: 모르는 상태에서 "됩니다"라고 답하지 않기 위해서다.
      값을 모르는데 ok 를 주면 그건 추측이고, 이 시스템의 설계 원칙 위반이다.
    """
    goal_id: str
    goal_label: str = ""
    verdict: Literal["ok", "blocked", "indeterminate"]
    unmet: list[ConditionResult] = Field(default_factory=list)
    met: list[ConditionResult] = Field(default_factory=list)
    unknown: list[ConditionResult] = Field(default_factory=list)
    low_confidence: list[ConditionResult] = Field(default_factory=list)
    engine_version: str = "1.0.0"
    tree_collected_at: str = ""
    evaluated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


__all__ = [
    "Condition", "ConditionResult", "ConditionTree", "Evidence",
    "Predicate", "Provenance", "Remedy", "SourceMeta", "UserProfile", "Verdict",
]
