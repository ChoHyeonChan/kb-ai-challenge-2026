"""추출 결과 검증 게이트 — 지어낸 근거·경로를 막는다.

★ "근거 표시율 100%"를 말이 아니라 **구조로** 보증하는 자리다.
  스키마가 evidence 를 필수로 만들고, 여기서 그 evidence 가 원문에 실제로 있는지 확인한다.

인용 보정 (fit_quote)
  모델은 원문 문장 앞뒤에 없는 말을 덧붙이는 실수를 반복한다.
    원문   "… 권유 드립니다. 원화 결제 시 추가로 부과되는 …"
    모델   "해외 가맹점에서 원화 결제 시 추가로 부과되는 …"   ← 앞에 없는 구절을 붙임
  그대로 폐기하면 **실제로 존재하는 조건이 사라진다.** 실측에서 DCC 차단 조건이 그렇게 빠졌다.

  LLM 에게 사유를 알려주고 다시 묻는 방법을 먼저 시도했다 — 3건 중 0건 복구. 같은 실수를 반복했다.
  그래서 규칙으로 바꿨다. 모델 인용에서 **원문에 실제로 있는 최장 연속 구간**을 찾아 그것만 남긴다.
  결과는 언제나 원문의 부분 문자열이므로, 보정을 거쳐도 근거는 여전히 원문이다.
  잘라낸 사실은 note 에 남겨 감추지 않는다.
"""
from __future__ import annotations

import json

from src.extract.vocabulary import ALLOWED_OPS, ALLOWED_SUBJECTS

# 보정 후 남은 인용이 이보다 짧거나, 원래 인용의 이 비율보다 작으면 폐기한다.
# 너무 많이 잘라내면 문장의 뜻이 바뀔 수 있다 (부정어가 잘려나가는 경우 등).
MIN_FITTED_CHARS = 25
MIN_FITTED_RATIO = 0.6


def _norm_map(text: str) -> tuple[str, list[int]]:
    """공백을 뺀 문자열과, 각 글자가 원문에서 몇 번째인지의 대응표."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if not ch.isspace():
            chars.append(ch)
            index.append(i)
    return "".join(chars), index


def _longest_common_span(needle: str, haystack: str) -> str:
    """needle 안에서 haystack 에 통째로 들어 있는 가장 긴 연속 구간."""
    best = ""
    for i in range(len(needle)):
        if len(needle) - i <= len(best):
            break
        for j in range(len(needle), i + len(best), -1):
            if needle[i:j] in haystack:
                best = needle[i:j]
                break
    return best


def fit_quote(quote: str, chunk_text: str) -> str | None:
    """모델 인용 → 원문의 연속 구간. 찾지 못하면 None.

    반환값은 **반드시 chunk_text 의 부분 문자열**이다 (공백 표기까지 원문 그대로).
    """
    nq, _ = _norm_map(quote)
    ns, src_index = _norm_map(chunk_text)
    if not nq or not ns:
        return None

    span = nq if nq in ns else _longest_common_span(nq, ns)

    # 최소 길이는 **청크 길이를 넘을 수 없다.**
    # 그러지 않으면 짧은 청크는 통째로 인용해도 영원히 통과하지 못한다 —
    # 실제로 "서비스 해제는 영업점에서만 가능합니다."(18자) 라는 핵심 문장 하나짜리 청크가
    # 25자 문턱에 걸려 폐기됐다. 문턱은 '잘라낸 조각이 너무 짧은가'를 보려는 것이지
    # '원문이 짧은가'를 벌하려는 것이 아니다.
    floor = min(MIN_FITTED_CHARS, len(ns))
    if len(span) < floor or len(span) < len(nq) * MIN_FITTED_RATIO:
        return None

    start = ns.find(span)
    return chunk_text[src_index[start]: src_index[start + len(span) - 1] + 1]


def _note_with(note: str | None, added: str) -> str:
    return f"{note} / {added}" if (note or "").strip() else added


# 해결 경로가 원문에 있는지 판단할 때 찾는 말. 이 중 하나도 없으면
# 그 청크는 "무엇을 해야 하는지"를 말하지 않은 것이다.
CHANNEL_WORDS = (
    "앱", "어플", "KB Pay", "KB페이", "스타뱅킹", "인터넷뱅킹", "모바일",
    "홈페이지", "웹", "영업점", "지점", "창구", "방문", "ATM",
    "고객센터", "콜센터", "전화", "상담", "재발급", "신청", "해제", "등록",
)


def strip_unfounded_remedy(c, chunk_text: str):
    """원문이 해결 경로를 말하지 않으면 remedy 를 비운다.

    이 관문이 없던 동안 실제로 사고가 났다. 한도 조건의 근거 원문에는
    한도 **수치**만 있는데 "앱에서 한도 조정"이 붙었다 — 프롬프트 예시가
    그대로 새어나온 것이다. 그리고 검수자는 remedy 를 보지 않았다.

    **`false` 도 비운다.** "앱에서 안 된다"도 주장이고, 주장에는 근거가 필요하다.
    모르는 것은 `None` 으로 둔다.
    """
    r = c.remedy
    if r.actionable_in_app is None and not r.channels and not r.primary_path:
        return c, None                                   # 이미 비어 있다

    if any(w in chunk_text for w in CHANNEL_WORDS):
        return c, None                                   # 원문이 경로를 말한다

    dropped = f"in_app={r.actionable_in_app} channels={r.channels} path={r.primary_path}"
    cleaned = c.model_copy(update={
        "remedy": r.model_copy(update={
            "actionable_in_app": None, "channels": [], "primary_path": None,
            "note": "KB 공개문서에서 이 조건의 해결 채널을 찾지 못했습니다",
        }),
    })
    return cleaned, f"{c.id}: 근거 없는 remedy 를 비움 — {dropped}"


def validate(out, chunk_text: str) -> tuple[list, list[str]]:
    """지어낸 인용·경로를 걸러낸다. 반환: (통과 조건, 폐기 사유 목록)

    통과 조건의 evidence_quote 는 원문 부분 문자열로 보정돼 있다.
    """
    kept: list = []
    rejected: list[str] = []

    for c in out.conditions:
        # 1. 인용이 원문에 실제로 있는가  ★ 근거 100% 의 실질적 보증
        fitted = fit_quote(c.evidence_quote, chunk_text)
        if fitted is None:
            rejected.append(f"{c.id}: 인용이 원문에 없음 — {c.evidence_quote[:40]}…")
            continue
        # 2. subject 가 허용 경로인가
        if c.predicate.subject not in ALLOWED_SUBJECTS:
            rejected.append(f"{c.id}: 허용되지 않은 subject — {c.predicate.subject}")
            continue
        # 3. op 가 허용 연산자인가
        if c.predicate.op not in ALLOWED_OPS:
            rejected.append(f"{c.id}: 허용되지 않은 op — {c.predicate.op}")
            continue
        # 4. value_json 이 유효한 JSON 인가
        try:
            json.loads(c.predicate.value_json)
        except (json.JSONDecodeError, TypeError):
            rejected.append(f"{c.id}: value_json 파싱 실패 — {c.predicate.value_json!r}")
            continue
        # 5. medium/low 인데 note 가 없으면 규칙 위반
        if c.confidence in ("medium", "low") and not (c.note or "").strip():
            rejected.append(f"{c.id}: confidence={c.confidence} 인데 note 없음")
            continue

        if _norm_map(fitted)[0] != _norm_map(c.evidence_quote)[0]:
            c = c.model_copy(update={
                "evidence_quote": fitted,
                "note": _note_with(c.note, "인용 자동 보정: 모델 출력에서 원문에 없는 부분을 잘라냈다"),
            })

        # 6. 해결 경로가 원문에 근거하는가.
        #    조건 자체는 유효하므로 폐기하지 않고 remedy 만 비운다.
        c, note = strip_unfounded_remedy(c, chunk_text)
        if note:
            rejected.append(note)
        kept.append(c)

    return kept, rejected
