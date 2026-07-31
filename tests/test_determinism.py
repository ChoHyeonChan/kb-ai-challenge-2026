"""동일 입력에 대한 규칙 엔진의 결정론성을 검증한다."""

import json
from pathlib import Path

from src.judge.engine import judge
from src.judge.schema import ConditionTree, UserProfile


REPEAT = 10
IGNORE_FIELDS = {"evaluated_at"}
RESULT_LIST_FIELDS = ("unmet", "met", "unknown", "low_confidence")


def canonical(verdict: dict) -> str:
    """실행 시각·배열 순서처럼 판정 의미와 무관한 차이를 제거한다."""
    normalized = {
        key: value for key, value in verdict.items() if key not in IGNORE_FIELDS
    }
    for key in RESULT_LIST_FIELDS:
        if key in normalized and isinstance(normalized[key], list):
            normalized[key] = sorted(normalized[key], key=lambda item: item["id"])
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def run_case(tree_path: Path, profile_path: Path) -> tuple[int, int]:
    """하나의 트리·프로필 조합을 반복 실행해 일치 횟수를 반환한다."""
    tree = ConditionTree.model_validate_json(tree_path.read_text(encoding="utf-8"))
    profile = UserProfile.model_validate_json(
        profile_path.read_text(encoding="utf-8")
    )

    results = [canonical(judge(tree, profile).model_dump()) for _ in range(REPEAT)]
    first = results[0]
    matches = sum(result == first for result in results)
    return matches, REPEAT


def test_all_combinations() -> None:
    """모든 조건 트리·프로필 조합은 10회 모두 같은 판정을 반환해야 한다."""
    trees = sorted(Path("data/trees").glob("*.json"))
    profiles = sorted(Path("data/profiles").glob("*.json"))
    assert trees and profiles, "조건트리 또는 프로필이 없습니다"

    failures: list[str] = []
    for tree_path in trees:
        for profile_path in profiles:
            matches, total = run_case(tree_path, profile_path)
            if matches != total:
                failures.append(f"{tree_path.name} x {profile_path.name}: {matches}/{total}")

    assert not failures, "결정론성 위반:\n" + "\n".join(failures)
