"""predicate 평가기.

★ 이 파일에는 LLM 호출이 없다. 있어서도 안 된다.
   같은 (predicate, profile) 이면 언제나 같은 결과가 나와야 한다.
   현재 시각에 의존하는 op 는 `today` 를 인자로 받는다 — 테스트 가능하게.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src.judge.schema import Predicate, UserProfile


class Unknown(Exception):
    """판정에 필요한 값을 알 수 없음. 추측하지 않고 unknown 으로 분류한다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _parse_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        # "2029-05-31" | "2029-05" | "2029/05/31"
        s = s.replace("/", "-")
        parts = s.split("-")
        try:
            if len(parts) == 2:
                y, m = int(parts[0]), int(parts[1])
                # 월만 주어지면 말일로 본다 (카드 유효기한 관례)
                nxt = date(y + (m // 12), (m % 12) + 1, 1)
                return nxt - timedelta(days=1)
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError as e:
            raise Unknown(f"날짜 형식을 해석할 수 없음: {v!r}") from e
    raise Unknown(f"날짜 형식을 해석할 수 없음: {v!r}")


def _resolve_value(value: Any, profile: UserProfile, today: date) -> Any:
    """리터럴 | {"ref": path} | {"now_plus_days": N} 을 실제 값으로."""
    if isinstance(value, dict):
        if "ref" in value:
            ref_val, known = profile.lookup(value["ref"])
            if not known:
                raise Unknown(f"참조값을 알 수 없음: {value['ref']}")
            return ref_val
        if "now_plus_days" in value:
            return today + timedelta(days=int(value["now_plus_days"]))
    return value


def _as_number(v: Any, what: str) -> float:
    if isinstance(v, bool):
        raise Unknown(f"{what}: 불리언을 수치로 비교할 수 없음")
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = v.replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError as e:
            raise Unknown(f"{what}: 수치로 해석할 수 없음 ({v!r})") from e
    raise Unknown(f"{what}: 수치로 해석할 수 없음 ({v!r})")


def evaluate(pred: Predicate, profile: UserProfile, *, today: date | None = None) -> bool:
    """조건 충족 여부. 값을 모르면 Unknown 을 던진다 (추측 금지)."""
    today = today or date.today()
    op = pred.op

    subject_val, known = profile.lookup(pred.subject)

    # 존재 여부만 묻는 op 는 known 판정 전에 처리
    if op == "exists":
        return known
    if op == "not_exists":
        return not known

    if not known:
        raise Unknown(f"값을 알 수 없음: {pred.subject}")

    value = _resolve_value(pred.value, profile, today)

    # ── 동등·포함 ──
    if op == "eq":
        return subject_val == value
    if op == "neq":
        return subject_val != value
    if op == "in":
        if not isinstance(value, (list, tuple, set)):
            raise Unknown(f"in 비교 대상이 목록이 아님: {value!r}")
        return subject_val in value
    if op == "not_in":
        if not isinstance(value, (list, tuple, set)):
            raise Unknown(f"not_in 비교 대상이 목록이 아님: {value!r}")
        return subject_val not in value

    # ── 수치 ──
    if op in ("gte", "lte", "gt", "lt"):
        a = _as_number(subject_val, pred.subject)
        b = _as_number(value, "비교값")
        return {"gte": a >= b, "lte": a <= b, "gt": a > b, "lt": a < b}[op]

    # ── 시간 ──
    if op in ("date_after", "date_before"):
        a = _parse_date(subject_val)
        b = _parse_date(value)
        return a > b if op == "date_after" else a < b

    if op in ("within_days", "not_within_days"):
        days = int(value["days"]) if isinstance(value, dict) else int(value)
        a = _parse_date(subject_val)
        inside = (today - a).days <= days
        return inside if op == "within_days" else not inside

    # ── 횟수 ── subject 는 날짜 목록. {"days": N, "n": M}
    if op in ("count_lte", "count_gte"):
        if not isinstance(value, dict) or "days" not in value or "n" not in value:
            raise Unknown('count 연산은 {"days": N, "n": M} 형식이 필요함')
        if not isinstance(subject_val, list):
            raise Unknown(f"{pred.subject}: 목록이어야 함")
        window = int(value["days"])
        cnt = sum(1 for d in subject_val if (today - _parse_date(d)).days <= window)
        return cnt <= int(value["n"]) if op == "count_lte" else cnt >= int(value["n"])

    raise Unknown(f"지원하지 않는 연산자: {op}")
