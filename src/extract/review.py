"""검수 관문 — 자동 추출한 조건을 트리에 넣을지 사람이 승인한다.

왜 필요한가
  1차 추출(252청크)에서 병합 15개 중 8개가 틀렸다. 방향이 뒤집히거나(안심차단이
  '켜져 있어야 한다'), subject 가 label 과 다른 것을 가리켰다.
  프롬프트를 고쳐 오류를 줄일 수는 있어도 0으로 만들 수는 없다.
  틀린 조건이 트리에 들어가면 판정은 **자신 있게 틀린 답**을 낸다. 그게 가장 나쁘다.

무엇을 사람이 하는가 — 여기서 경계가 중요하다
  ○ 승인 / 반려 판단
  ○ severity 교정 **하나만** 허용 (blocking ↔ warning). 사유를 반드시 적는다.
     원문이 "제한이 있을 수 있습니다" 처럼 흐릿할 때 LLM 이 blocking 으로 올리는 일이 잦고,
     그대로 두면 판정이 "차단됨"으로 확정돼 사용자에게 없는 벽을 만든다.
  ✕ label·predicate·evidence·remedy 는 **고칠 수 없다.** 전부 LLM 출력 그대로다.
  즉 사람은 게이트지 저자가 아니다. 그래서 "문서 → 조건 자동 변환"이라는 주장이 유지된다.
  교정한 조건은 트리에 `review_override` 로 표시돼, 무엇을 사람이 손댔는지 감춰지지 않는다.

기록
  `data/review/decisions.yaml` 에 결정과 사유를 남긴다. 이 파일이 곧 감사 기록이다.
  결정이 없는 조건은 pending 이며 **트리에 들어가지 않는다** (모르면 넣지 않는다).
"""
from __future__ import annotations

import json

import yaml

from src.config import DATA_DIR
from src.judge.schema import Condition

REVIEW_FILE = DATA_DIR / "review" / "decisions.yaml"


def review_key(goal_id: str, cond: Condition) -> str:
    """검수 키 = 목표 + 판정 엔진이 실제로 쓰는 값. 문구가 바뀌어도 키는 그대로다.

    목표를 넣는 이유: 같은 predicate 라도 목표가 다르면 판단이 달라진다.
    실제로 `account.nonface_open_block eq false` 가 해외결제 목표에서도 나왔는데,
    그쪽은 '해외안심결제'를 잘못 매핑한 것이라 반려해야 한다. 목표가 없으면 둘을 구분할 수 없다.
    """
    value = json.dumps(cond.predicate.value, sort_keys=True, ensure_ascii=False)
    return f"{goal_id}|{cond.predicate.subject}|{cond.predicate.op}|{value}"


def load_decisions() -> dict[str, dict]:
    if not REVIEW_FILE.exists():
        return {}
    cfg = yaml.safe_load(REVIEW_FILE.read_text(encoding="utf-8")) or {}
    return {d["key"]: d for d in (cfg.get("decisions") or [])}


ALLOWED_OVERRIDES = {"severity"}


def _apply_override(cond: Condition, d: dict) -> Condition:
    """허용된 필드만 교정한다. 그 외 키는 조용히 무시하지 않고 오류로 세운다."""
    override = d.get("override") or {}
    bad = set(override) - ALLOWED_OVERRIDES
    if bad:
        raise SystemExit(f"검수 교정 불가 필드: {sorted(bad)} (허용: {sorted(ALLOWED_OVERRIDES)}) "
                         f"— key={d['key']}")
    if not override:
        return cond

    return cond.model_copy(update={
        **override,
        "review_override": f"{'/'.join(f'{k}: {getattr(cond, k)} → {v}' for k, v in override.items())}"
                           f" · {d.get('reason', '')}",
    })


def split(goal_id: str, conditions: list[Condition]) -> tuple[list[Condition], list[tuple[Condition, str]], list[Condition]]:
    """반환: (승인, [(반려 조건, 사유)], 미검수)"""
    decisions = load_decisions()
    approved: list[Condition] = []
    rejected: list[tuple[Condition, str]] = []
    pending: list[Condition] = []

    for c in conditions:
        d = decisions.get(review_key(goal_id, c))
        if d is None:
            pending.append(c)
        elif d.get("decision") == "approve":
            approved.append(_apply_override(c, d))
        else:
            rejected.append((c, d.get("reason", "")))

    return approved, rejected, pending


def format_pending(goal_id: str, conds: list[Condition]) -> str:
    """미검수 조건을 decisions.yaml 에 그대로 붙여넣을 수 있는 형태로 만든다."""
    if not conds:
        return ""
    lines = ["  # ── 아래는 아직 검수되지 않은 조건이다. decision 을 approve/reject 로 바꾼다 ──"]
    for c in conds:
        sup = c.provenance.support_count if c.provenance else 1
        lines += [
            f"  # {c.label}",
            f"  #   근거({sup}곳) \"{c.evidence.quote[:60]}\"",
            f"  - key: \"{review_key(goal_id, c)}\"",
            f"    decision: pending",
            f"    reason: \"\"",
        ]
    return "\n".join(lines)
