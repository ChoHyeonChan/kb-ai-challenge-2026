"""조건이 인용보다 넓게 적용되지 않는가.

수집 원문은 카드 종류를 명시적으로 가른다.

    card_overseas_faq#0003     "신용카드의 경우, 해외 한도는 국내와 통합으로 운영…
                                체크카드의 경우, 해외 이용 한도는 다음과 같습니다"
    card_overseas_general#0056 "신용카드 승인은 1회 또는 1일 제한 기준이 없으며…"

그런데 조건은 모두에게 걸리고 있었다. 신용카드 사용자에게 체크카드 전용 한도가
'충족'으로 집계됐다 — 통과시켜도 틀린 말이고, 금액이 한도를 넘으면 **틀린 판정**이 나온다.

`applies_when` 이 그것을 막는다. 이 파일은 그 방어선이 살아 있는지 지킨다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.judge.engine import judge, load_profile, load_tree
from src.judge.schema import ConditionTree

ROOT = Path(__file__).resolve().parent.parent
TREE = ROOT / "data" / "trees" / "overseas_payment_online.json"

# 원문이 체크카드로 범위를 건 조건들
DEBIT_ONLY = {"c_limit_daily", "c_limit_single", "c_limit_accumulated"}


@pytest.fixture(scope="module")
def tree() -> ConditionTree:
    return load_tree(TREE)


def test_체크카드_전용_조건에는_적용범위가_붙어_있다(tree: ConditionTree) -> None:
    """근거가 '체크카드의 경우'라고 말하면 조건도 그렇게 말해야 한다."""
    guarded = {c.id for c in tree.conditions if c.applies_when is not None}
    assert DEBIT_ONLY <= guarded, f"적용 범위가 빠진 조건: {DEBIT_ONLY - guarded}"

    for c in tree.conditions:
        if c.id in DEBIT_ONLY:
            assert c.applies_when.subject == "card.type"
            assert c.applies_when.op == "eq"
            assert c.applies_when.value == "debit"
            # 화면이 사람에게도 설명할 수 있어야 한다
            assert c.scope_note, f"{c.id}: applies_when 만 있고 사람이 읽을 설명이 없다"


def test_신용카드에는_체크카드_한도가_걸리지_않는다(tree: ConditionTree) -> None:
    prof = load_profile(ROOT / "data" / "profiles" / "overseas_ok.json")
    assert prof.card.get("type") == "credit"

    v = judge(tree, prof)
    na = {r.id for r in v.not_applicable}
    assert na == DEBIT_ONLY, f"해당 없음이어야 할 조건: {DEBIT_ONLY}, 실제: {na}"

    # 해당 없는 조건이 충족·미충족·불명 어디에도 섞이면 안 된다
    graded = {r.id for r in v.met} | {r.id for r in v.unmet} | {r.id for r in v.unknown}
    assert not (DEBIT_ONLY & graded), "적용되지 않는 조건이 채점됐다"


def test_체크카드에는_그대로_걸린다(tree: ConditionTree) -> None:
    prof = load_profile(ROOT / "data" / "profiles" / "overseas_blocked.json")
    assert prof.card.get("type") == "debit"

    v = judge(tree, prof)
    assert not v.not_applicable, "체크카드인데 제외된 조건이 있다"
    graded = {r.id for r in v.met} | {r.id for r in v.unmet} | {r.id for r in v.unknown}
    assert DEBIT_ONLY <= graded


def test_한도초과_신용카드는_막히지_않는다(tree: ConditionTree) -> None:
    """이것이 이 기능을 만든 이유다.

    600만원을 넘겨도 신용카드에는 1회·1일 한도가 없다고 원문이 말한다.
    범위 검사가 없으면 여기서 잘못된 `blocked` 가 나온다.
    """
    prof = load_profile(ROOT / "data" / "profiles" / "overseas_ok.json")

    v = judge(tree, prof, context={"amount_krw": 9_000_000})
    assert v.verdict == "ok", f"신용카드 900만원인데 {v.verdict} 가 나왔다"
    assert not [r for r in v.unmet if r.id in DEBIT_ONLY]

    # 대조 — 같은 금액을 체크카드로 쓰면 실제로 막혀야 한다
    debit = load_profile(ROOT / "data" / "profiles" / "overseas_ok.json").model_copy(deep=True)
    debit.card["type"] = "debit"
    v2 = judge(tree, debit, context={"amount_krw": 9_000_000})
    assert v2.verdict == "blocked"
    assert {r.id for r in v2.unmet} & DEBIT_ONLY, "체크카드 900만원인데 한도 조건이 안 걸렸다"


def test_카드종류를_모르면_충족이라고_말하지_않는다(tree: ConditionTree) -> None:
    """적용 대상인지조차 모르면 추측하지 않는다 — 이 시스템의 기본 원칙."""
    prof = load_profile(ROOT / "data" / "profiles" / "overseas_ok.json").model_copy(deep=True)
    prof.card["type"] = None

    v = judge(tree, prof)
    unknown_ids = {r.id for r in v.unknown}
    assert DEBIT_ONLY <= unknown_ids, "카드 종류를 모르는데 한도 조건을 단정했다"
    assert not v.not_applicable, "모르는 것을 '해당 없음'으로 처리했다"
    for r in v.unknown:
        if r.id in DEBIT_ONLY:
            assert "적용 대상" in (r.reason or ""), r.reason


def test_분류가_전부를_덮는다(tree: ConditionTree) -> None:
    """어떤 조건도 조용히 사라지지 않는다."""
    for path in sorted((ROOT / "data" / "profiles").glob("*.json")):
        prof = load_profile(path)
        v = judge(tree, prof)
        total = len(v.met) + len(v.unmet) + len(v.unknown) + len(v.not_applicable)
        assert total == len(tree.conditions), f"{path.name}: {total} != {len(tree.conditions)}"


def test_적용범위도_결정론이다(tree: ConditionTree) -> None:
    prof = load_profile(ROOT / "data" / "profiles" / "overseas_ok.json")
    first = json.dumps(
        [r.id for r in judge(tree, prof).not_applicable], ensure_ascii=False
    )
    for _ in range(50):
        assert json.dumps(
            [r.id for r in judge(tree, prof).not_applicable], ensure_ascii=False
        ) == first
