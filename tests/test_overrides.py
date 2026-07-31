"""화면에서 직접 바꾼 상태값(overrides)이 안전하게 처리되는지 검증한다.

이 기능은 "프로필마다 답을 박아둔 것 아니냐"는 의심에 답하려고 만들었다.
그러려면 두 가지가 동시에 참이어야 한다.

  1. 값을 바꾸면 판정이 **실제로** 바뀐다      — 아니면 증명이 안 된다
  2. 바꿔도 원본 프로필은 **그대로**다          — 아니면 다음 사람이 보는 화면이 오염된다
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app

CLIENT = TestClient(app)
BASE = {"goal_id": "overseas_payment_online", "profile_id": "overseas_blocked"}


def _judge(**extra) -> dict:
    res = CLIENT.post("/api/judge", json={**BASE, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def test_override_changes_verdict() -> None:
    """차단을 해제하면 미충족이 줄어야 한다. 줄지 않으면 값에 반응하지 않는 것이다."""
    before = _judge()
    after = _judge(overrides={"card.dcc_block": False})

    assert len(before["unmet"]) == 3
    assert len(after["unmet"]) == 2
    assert "c_dcc_block" not in {r["id"] for r in after["unmet"]}


def test_all_blocks_cleared_flips_to_ok() -> None:
    """막힌 것을 전부 풀면 판정이 뒤집혀야 한다."""
    verdict = _judge(overrides={
        "card.dcc_block": False,
        "card.overseas_block_online": False,
        "card.ic_pin_registered": True,
    })

    assert verdict["verdict"] == "ok"
    assert not verdict["unmet"]


def test_override_to_null_becomes_unknown() -> None:
    """'모름'으로 바꾸면 충족·미충족으로 추측하지 않고 unknown 으로 가야 한다."""
    verdict = _judge(overrides={"card.dcc_block": None})

    assert "c_dcc_block" in {r["id"] for r in verdict["unknown"]}
    assert "c_dcc_block" not in {r["id"] for r in verdict["unmet"]}


def test_override_does_not_mutate_stored_profile() -> None:
    """바꾼 값은 그 요청에만 산다. 다음 요청은 원래 프로필로 판정해야 한다."""
    _judge(overrides={"card.dcc_block": False, "card.overseas_block_online": False})

    assert len(_judge()["unmet"]) == 3

    stored = CLIENT.get("/api/profile/overseas_blocked").json()
    assert stored["card"]["dcc_block"] is True
    assert stored["card"]["overseas_block_online"] is True


def test_unknown_key_is_rejected() -> None:
    """프로필에 없는 키는 만들 수 없다. 만들 수 있으면 없는 상태를 지어내는 셈이다."""
    res = CLIENT.post("/api/judge", json={**BASE, "overrides": {"card.does_not_exist": True}})
    assert res.status_code == 400


def test_paths_outside_state_groups_are_rejected() -> None:
    """card·account·context 밖은 건드릴 수 없다 (profile_id 덮어쓰기 등)."""
    for bad in ("profile_id", "description", "secret.key", "card", "card.dcc_block.deep"):
        res = CLIENT.post("/api/judge", json={**BASE, "overrides": {bad: "x"}})
        assert res.status_code == 400, f"막지 못한 경로: {bad}"


def test_boolean_on_numeric_condition_stays_unknown() -> None:
    """금액 조건에 참/거짓이 들어와도 추측하지 않고 unknown 으로 둔다.

    화면은 이런 조건에 참/거짓 버튼을 붙이지 않지만, 엔진은 화면을 믿지 않는다.
    """
    verdict = _judge(overrides={"context.daily_used_krw": True})

    assert "c_limit_daily" in {r["id"] for r in verdict["unknown"]}
    assert "c_limit_daily" not in {r["id"] for r in verdict["met"]}


def test_simulate_uses_the_same_overrides() -> None:
    """판정과 해결 계획이 다른 상태를 보면 화면이 앞뒤가 안 맞는 말을 하게 된다."""
    plan = CLIENT.post("/api/simulate", json={
        **BASE, "overrides": {"card.dcc_block": False},
    })
    assert plan.status_code == 200
    assert len(plan.json()["must_fix"]) == 2
