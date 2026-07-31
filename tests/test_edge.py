"""B7 엣지 입력에서 판정 엔진과 API가 안전하게 실패하는지 검증한다."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app
from src.judge.engine import judge, load_profile, load_tree
from src.judge.schema import UserProfile


TREES_DIR = PROJECT_ROOT / "data" / "trees"
PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"
CLIENT = TestClient(app)


def _tree(name: str):
    return load_tree(TREES_DIR / name)


def _profile(name: str) -> UserProfile:
    return load_profile(PROFILES_DIR / name)


def test_empty_profile_is_indeterminate() -> None:
    """필수 상태가 없으면 ok가 아니라 indeterminate여야 한다."""
    tree = _tree("overseas_payment_online.json")
    verdict = judge(tree, UserProfile(profile_id="empty"))

    assert verdict.verdict == "indeterminate"
    assert not verdict.met
    assert not verdict.unmet
    assert {result.id for result in verdict.unknown} == {
        condition.id for condition in tree.conditions
    }


def test_null_value_is_classified_as_unknown() -> None:
    """null은 충족·미충족으로 추측하지 않고 unknown으로 분류한다."""
    verdict = judge(
        _tree("overseas_payment_online.json"),
        UserProfile(profile_id="null_value", card={"dcc_block": None}),
    )

    assert verdict.verdict == "indeterminate"
    assert "c_dcc_block" in {result.id for result in verdict.unknown}


def test_unknown_goal_returns_404() -> None:
    """없는 goal_id 요청은 서버 오류가 아닌 404로 응답해야 한다."""
    response = CLIENT.post(
        "/api/judge",
        json={"goal_id": "does_not_exist", "profile_id": "overseas_ok"},
    )

    assert response.status_code == 404


def test_unknown_profile_returns_404() -> None:
    """없는 profile_id 요청은 서버 오류가 아닌 404로 응답해야 한다."""
    response = CLIENT.post(
        "/api/judge",
        json={"goal_id": "overseas_payment_online", "profile_id": "does_not_exist"},
    )

    assert response.status_code == 404


def test_numeric_string_is_classified_as_unknown() -> None:
    """숫자 조건에 문자열이 오면 크래시 대신 해당 조건을 unknown으로 분류한다."""
    data = _profile("overseas_ok.json").model_dump()
    data["context"]["amount_krw"] = "삼만원"

    verdict = judge(_tree("overseas_payment_online.json"), UserProfile.model_validate(data))

    assert "c_limit_single" in {result.id for result in verdict.unknown}


def test_empty_condition_tree_returns_ok() -> None:
    """조건이 없는 트리도 예외 없이 ok 판정을 반환해야 한다."""
    tree = _tree("account_open_nonface.json").model_copy(update={"conditions": []})

    verdict = judge(tree, UserProfile(profile_id="empty_tree"))

    assert verdict.verdict == "ok"
    assert not verdict.unmet
    assert not verdict.unknown
