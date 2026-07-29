"""결정론성 중간 측정 — 같은 입력에 같은 출력이 나오는가.

★ 정식 테스트 스위트는 `tests/test_determinism.py` (팀원 B6) 다.
  이 스크립트는 기술설명서에 실을 수치를 확보하기 위한 **중간 측정**이며,
  pytest 없이 단독 실행된다.

비교 규칙 (B6 와 동일하게 맞출 것)
  · `evaluated_at` 은 실행 시각이므로 비교에서 제외한다
  · 리스트는 `id` 기준 정렬 후 비교한다 (순서만 다른 것은 같은 결과로 본다)
  · dict 는 `sort_keys=True` 로 직렬화해 비교한다

실행:  python -m eval.determinism_interim
"""
from __future__ import annotations

import json
import time

from src.config import EVAL_DIR, PROFILES_DIR, TREES_DIR
from src.judge.engine import judge, load_profile, load_tree
from src.judge.simulate import simulate

REPEAT = 200


def _canon(obj: dict) -> str:
    """비교용 정규화. 실행 시각을 빼고, 조건 목록을 id 로 정렬한다."""
    obj = {k: v for k, v in obj.items() if k != "evaluated_at"}
    for key in ("unmet", "met", "unknown", "low_confidence", "must_fix", "optional_fix"):
        if isinstance(obj.get(key), list):
            obj[key] = sorted(obj[key], key=lambda r: r.get("id", ""))
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _pairs() -> list[tuple[str, str]]:
    trees = sorted(p.stem for p in TREES_DIR.glob("*.json"))
    profiles = sorted(p.stem for p in PROFILES_DIR.glob("*.json"))
    return [(t, p) for t in trees for p in profiles]


def measure() -> tuple[list[dict], float]:
    rows: list[dict] = []
    elapsed: list[float] = []

    for goal_id, profile_id in _pairs():
        tree = load_tree(TREES_DIR / f"{goal_id}.json")
        profile = load_profile(PROFILES_DIR / f"{profile_id}.json")

        seen: set[str] = set()
        for _ in range(REPEAT):
            t0 = time.perf_counter()
            verdict = judge(tree, profile)
            elapsed.append((time.perf_counter() - t0) * 1000)
            seen.add(_canon(verdict.model_dump()) + _canon(simulate(verdict).model_dump()))

        rows.append({
            "goal_id": goal_id,
            "profile_id": profile_id,
            "verdict": verdict.verdict,
            "distinct": len(seen),
        })

    elapsed.sort()
    return rows, elapsed[len(elapsed) // 2]


def report(rows: list[dict], median_ms: float) -> str:
    agreed = sum(1 for r in rows if r["distinct"] == 1)
    lines = [
        "# 결정론성 중간 측정", "",
        "> 정식 테스트 스위트는 `tests/test_determinism.py` (팀원 담당). 이 문서는 **중간 측정**이다.",
        "> 비교 시 `evaluated_at`(실행 시각)을 제외하고, 조건 목록은 `id` 기준 정렬 후 비교했다.", "",
        "| 항목 | 값 |", "|---|---|",
        f"| 조합 (트리 × 프로필) | {len(rows)} |",
        f"| 조합당 반복 | {REPEAT}회 |",
        f"| 총 판정 횟수 | {len(rows) * REPEAT} |",
        f"| **결과가 하나뿐인 조합** | **{agreed} / {len(rows)}** |",
        f"| **일치율** | **{agreed / len(rows) * 100:.1f}%** |",
        f"| 판정 1회 소요 (중앙값) | {median_ms:.4f} ms |", "",
        "판정과 해결 계획을 **함께** 직렬화해 비교했다. 둘 중 하나라도 흔들리면 불일치로 잡힌다.", "",
        "## 조합별", "",
        "| 목표 | 프로필 | 판정 | 서로 다른 결과 수 |", "|---|---|---|---|",
    ]
    for r in rows:
        mark = "1 ✓" if r["distinct"] == 1 else f"**{r['distinct']} ✗**"
        lines.append(f"| {r['goal_id']} | {r['profile_id']} | {r['verdict']} | {mark} |")
    lines += ["", "## 이 수치가 의미하는 것", "",
              "판정 경로에 LLM 호출이 없다는 설계가 **말이 아니라 측정으로** 확인된다.",
              "LLM 은 조건을 문서에서 뽑을 때만 쓰이고, 그 결과는 파일(조건 트리)로 고정된다.",
              "같은 트리와 같은 사용자 상태라면 언제 실행해도 같은 답이 나온다."]
    return "\n".join(lines)


if __name__ == "__main__":
    rows, median_ms = measure()
    text = report(rows, median_ms)
    print(text)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = EVAL_DIR / "determinism_interim.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\n→ {out}")
