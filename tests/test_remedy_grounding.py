"""해결 방법(remedy)이 근거에 묶여 있는지 검증한다.

이 테스트가 없던 동안 사고가 났다. 한도 조건의 근거 원문에는 한도 **수치**만
있는데 "앱에서 한도 조정 (KB Pay)"이 붙었다. 프롬프트 예시가 그대로 새어나온
것이고, 검수자는 조건과 인용만 봤지 remedy 는 보지 않았다.

지키는 명제는 하나다.
    **주장에는 근거가 있어야 한다. `false` 도 주장이다.**
"앱에서 안 된다"는 말도 근거 없이 하면 "앱에서 된다"만큼 틀렸다.
"""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.judge.engine import load_tree

TREES = sorted((PROJECT_ROOT / "data/trees").glob("*.json"))
# 앱/영업점 등 채널을 가리키는 말. 근거 원문에 이 중 하나는 있어야 한다.
CHANNEL_WORDS = (
    "앱", "KB Pay", "KB페이", "스타뱅킹", "인터넷뱅킹", "모바일", "홈페이지",
    "영업점", "지점", "창구", "방문", "ATM", "고객센터", "전화",
)


def _conditions():
    for path in TREES:
        for c in load_tree(path).conditions:
            yield path.name, c


def test_trees_exist() -> None:
    assert TREES, "조건 트리가 없습니다"


def test_no_claim_without_basis() -> None:
    """actionable_in_app 을 말했다면 무엇이 그것을 뒷받침하는지 적혀 있어야 한다."""
    bad = [
        f"{f}:{c.id} — in_app={c.remedy.actionable_in_app} 인데 basis 가 없음"
        for f, c in _conditions()
        if c.remedy.actionable_in_app is not None and c.remedy.basis is None
    ]
    assert not bad, "근거 없는 주장:\n" + "\n".join(bad)


def test_no_channels_without_basis() -> None:
    """채널·경로도 마찬가지다. 근거 없이 '어디서 하세요'라고 말하지 않는다."""
    bad = [
        f"{f}:{c.id} — channels={c.remedy.channels} path={c.remedy.primary_path}"
        for f, c in _conditions()
        if c.remedy.basis is None and (c.remedy.channels or c.remedy.primary_path)
    ]
    assert not bad, "근거 없는 해결 경로:\n" + "\n".join(bad)


def test_app_claim_needs_a_channel_in_the_quote() -> None:
    """앱에서 되는지/안 되는지를 말했다면 인용에 **채널**이 있어야 한다.

    채널은 '어디서'(앱·영업점·고객센터)다. '무엇을'(재발급·해제)은 채널이 아니다.
    라벨만 바꿔 놓고 근거는 그대로인 상태를 막는다.
    """
    bad = [
        f"{f}:{c.id} — in_app={c.remedy.actionable_in_app} 인데 인용에 채널이 없음: {c.evidence.quote[:45]}…"
        for f, c in _conditions()
        if c.remedy.basis == "evidence" and c.remedy.actionable_in_app is not None
        and not any(w in c.evidence.quote for w in CHANNEL_WORDS)
    ]
    assert not bad, "evidence 라고 했지만 인용에 채널이 없음:\n" + "\n".join(bad)


def test_action_only_evidence_still_quotes_the_action() -> None:
    """채널은 몰라도 '무엇을 해야 하는지'를 적었다면 그 말이 인용에 있어야 한다.

    카드 유효기한이 이 경우다 — 원문이 "사용 전 갱신 재발급이 필요합니다"라고
    말하므로 할 일은 알지만, 어디서 하는지는 원문에 없다.
    """
    action_words = ("재발급", "해제", "등록", "신청", "변경", "갱신", "서명", "확인")
    bad = [
        f"{f}:{c.id} — path='{c.remedy.primary_path}' 인데 인용에 근거가 없음"
        for f, c in _conditions()
        if c.remedy.basis == "evidence" and c.remedy.actionable_in_app is None
        and c.remedy.primary_path
        and not any(w in c.evidence.quote for w in action_words)
    ]
    assert not bad, "할 일을 적었지만 인용에 없음:\n" + "\n".join(bad)


def test_measured_remedy_has_a_record() -> None:
    """basis=measured 는 실측 기록 문서가 저장소에 있어야 한다."""
    measured = [c.id for _, c in _conditions() if c.remedy.basis == "measured"]
    if not measured:
        return
    record = PROJECT_ROOT / "eval/results/kbpay_hands_on.md"
    assert record.exists(), f"실측 근거 문서가 없습니다: {record} (해당 조건 {measured})"

    text = record.read_text(encoding="utf-8")
    missing = [cid for cid in measured if cid not in text]
    assert not missing, f"실측 문서에 언급되지 않은 조건: {missing}"


def test_remedy_without_basis_is_fully_empty() -> None:
    """근거가 없다면 채널·경로도 비어 있어야 한다. 절반만 비우면 더 헷갈린다.

    `actionable_in_app` 이 None 이어도 해결 **방법**은 알 수 있다.
    카드 유효기한이 그렇다 — 원문이 "사용 전 갱신 재발급이 필요합니다"라고 말하므로
    무엇을 해야 하는지는 안다(basis=evidence). 다만 어디서 하는지는 원문에 없어
    `actionable_in_app` 은 None 이다. 이 둘은 다른 층위다.
    """
    bad = [
        f"{f}:{c.id} — basis 없음인데 channels={c.remedy.channels} path={c.remedy.primary_path}"
        for f, c in _conditions()
        if c.remedy.basis is None and (c.remedy.channels or c.remedy.primary_path)
    ]
    assert not bad, "근거 없이 경로를 말함:\n" + "\n".join(bad)


def test_unknown_remedy_says_why() -> None:
    """모른다고 했으면 **무엇을 못 찾았는지** 적혀 있어야 한다.

    빈칸은 "해당 없음"으로도 읽힌다. 찾아봤지만 없었다는 사실 자체가 정보다.
    """
    bad = [
        f"{f}:{c.id} — actionable_in_app=None 인데 note 가 없음"
        for f, c in _conditions()
        if c.remedy.actionable_in_app is None and not (c.remedy.note or "").strip()
    ]
    assert not bad, "모른다면서 이유를 안 적음:\n" + "\n".join(bad)


def test_prompt_example_does_not_teach_ungrounded_remedy() -> None:
    """프롬프트 예시가 근거 없는 해결 방법을 가르치지 않는지 확인한다.

    사고의 원인이 예시였다. 예시를 되돌리면 같은 일이 반복된다.
    """
    from src.extract.examples import FEW_SHOTS

    head = FEW_SHOTS.split("[예시 2", 1)[0]          # 한도 조건 예시
    assert '"한도 조정"' not in head, "한도 예시가 다시 해결 경로를 지어내고 있습니다"
    assert '"actionable_in_app": null' in head, "한도 예시가 null 을 가르치지 않습니다"


def test_validator_strips_remedy_when_source_has_no_channel() -> None:
    """검증 게이트가 근거 없는 remedy 를 실제로 비우는지 확인한다."""
    from src.extract.validate import strip_unfounded_remedy

    class _R:
        actionable_in_app = True
        channels = ["app:KB Pay"]
        primary_path = "한도 조정"
        note = None

        def model_copy(self, update):
            r = _R()
            for k, v in update.items():
                setattr(r, k, v)
            return r

    class _C:
        id = "c_limit_daily"
        remedy = _R()

        def model_copy(self, update):
            c = _C()
            c.remedy = update["remedy"]
            return c

    quote = "1일 한도 | 현금인출/가맹점이용 | 600만원 상당의 달러(USD) 환산액"
    cleaned, note = strip_unfounded_remedy(_C(), quote)

    assert note is not None, "근거 없는 remedy 를 그냥 통과시켰습니다"
    assert cleaned.remedy.actionable_in_app is None
    assert cleaned.remedy.channels == []
    assert cleaned.remedy.primary_path is None
