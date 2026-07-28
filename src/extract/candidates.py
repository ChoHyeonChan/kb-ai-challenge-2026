"""조건 후보 선별.

256개 청크를 전부 LLM 에 넣으면 비용도 들고 노이즈도 늘어난다.
조건이 들어있을 법한 청크만 1차로 거른다.

[현찬 판단 자리]
  SIGNAL / NEGATIVE 패턴을 조정한다. 놓치는 조건이 있으면 SIGNAL 을 넓히고,
  쓰레기가 많이 들어오면 NEGATIVE 를 넓힌다.
  `python -m src.extract.candidates` 로 무엇이 걸러지는지 눈으로 확인할 수 있다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.config import CHUNKS_DIR

# 조건일 가능성을 높이는 신호  [현찬 판단]
SIGNAL = re.compile(
    r"("
    r"해야|하셔야|필요|필수|가능|불가|제한|초과|이내|이상|이하|미만"
    r"|한도|등록|해제|차단|정지|승인|거절|확인|일치|만료|유효"
    r"|되지\s*않|안\s*됩니다|불가능|없습니다|아닙니다"
    r"|해당|대상|조건|기준|경우에\s*한|단,|다만"
    r")"
)

# 조건이 아닐 가능성이 높은 신호  [현찬 판단]
NEGATIVE = re.compile(
    r"("
    r"알려드릴게요|알아봤어요|소개합니다|안내해\s*드립니다"
    r"|이벤트|혜택을\s*누리|추천\s*드립니다|지금\s*신청하세요"
    r"|^#|해시태그|콘텐츠는.*기준으로\s*작성"
    r"|고객센터\s*\d|전화\s*\d{2,}|©|Copyright"
    r")"
)


def load_chunks() -> list[dict]:
    path = CHUNKS_DIR / "chunks.jsonl"
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def is_candidate(chunk: dict) -> bool:
    """조건 후보인지 1차 판별.

    SIGNAL 검사는 쓰지 않는다.
    실측에서 "카드 뒷면 본인 서명을 기재해주세요" 같은 **실제 조건**이
    지시형이라는 이유로 걸러졌다. 놓치는 비용이 잘못 넣는 비용보다 크므로,
    명백한 노이즈(NEGATIVE)와 너무 짧은 조각만 제외하고 판단은 LLM 에 맡긴다.
    LLM 은 is_condition=false 로 2차 필터 역할을 한다.
    """
    text = chunk["text"]
    if len(text) < 15:
        return False
    if NEGATIVE.search(text):
        return False
    return True


def select(goal: str | None = None) -> list[dict]:
    chunks = load_chunks()
    if goal:
        chunks = [c for c in chunks if c.get("goal") == goal]
    return [c for c in chunks if is_candidate(c)]


if __name__ == "__main__":
    all_chunks = load_chunks()
    picked = [c for c in all_chunks if is_candidate(c)]
    dropped = [c for c in all_chunks if not is_candidate(c)]

    print(f"전체 {len(all_chunks)}개 → 후보 {len(picked)}개 (제외 {len(dropped)}개)\n")

    by_goal: dict[str, int] = {}
    for c in picked:
        by_goal[c.get("goal") or "?"] = by_goal.get(c.get("goal") or "?", 0) + 1
    for g, n in by_goal.items():
        print(f"  {g}: {n}개")

    print("\n── 후보 샘플 8개 ──")
    for c in picked[:8]:
        print(f"  [{c['kind']:10s}] {c['text'][:110]}")

    print("\n── 제외된 것 샘플 8개 (놓친 조건이 없는지 확인) ──")
    for c in dropped[:8]:
        print(f"  [{c['kind']:10s}] {c['text'][:110]}")
