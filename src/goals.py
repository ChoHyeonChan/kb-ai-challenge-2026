"""목표 정의 로더 — `data/sources/goals.yaml` 의 단일 출입구.

조건은 문서에서 자동 추출되지만, "이 조건들이 어떤 목표에 속하는가"와
"사용자가 그 목표를 어떤 말로 부르는가"는 문서에 없다. 그것만 여기서 읽는다.

세 곳이 같은 정의를 쓴다 — 그래서 각자 파싱하지 않고 이 모듈을 거친다.
  extract/extractor  : 목표 이름을 프롬프트에 넣어 '목표와 무관한 조건'을 걸러내게 한다
  extract/assemble   : 트리의 goal_label·aliases·domain 을 채운다
  resolve/retriever  : aliases 로 자연어 질의를 goal_id 로 바꾼다
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from src.config import SOURCES_DIR

GOALS_FILE = SOURCES_DIR / "goals.yaml"


@lru_cache(maxsize=1)
def load_goals() -> dict[str, dict]:
    cfg = yaml.safe_load(GOALS_FILE.read_text(encoding="utf-8"))
    return {g["id"]: g for g in cfg["goals"]}


def label_of(goal_id: str) -> str:
    """goal_id → 사람이 읽는 이름. 정의가 없으면 id 를 그대로 돌려준다."""
    return load_goals().get(goal_id, {}).get("label", goal_id)
