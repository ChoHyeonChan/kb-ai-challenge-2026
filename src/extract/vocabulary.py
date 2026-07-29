"""통제 어휘 — 조건이 참조할 수 있는 상태·연산자·분류.

★ 이 파일이 directed symbolic prompting 의 '사전'이다.
  자유롭게 두면 모델이 존재하지 않는 경로를 지어내고, 그 조건은 프로필과 매칭되지 않아
  영원히 unknown 이 된다. (Neuro-Symbolic Framework for Public-Sector AI, arXiv:2512.12109)

추출(prompt)과 검증(validate)이 **같은 목록**을 봐야 하므로 프롬프트에서 떼어 여기 둔다.

[현찬 판단 자리]
  새 경로를 넣으려면 `data/profiles/*.json` 에도 같은 경로를 만들어야 한다.
  프로필에 없는 경로는 판정에서 늘 unknown 이 된다.
"""
from __future__ import annotations

ALLOWED_SUBJECTS: dict[str, str] = {
    # 카드 상태
    "card.overseas_block_online": "해외거래정지(온라인) 설정 여부 (bool)",
    "card.overseas_block_offline": "해외거래정지(오프라인) 설정 여부 (bool)",
    "card.overseas_block_cash": "해외거래정지(현금서비스) 설정 여부 (bool)",
    "card.dcc_block": "해외원화결제(DCC) 차단 설정 여부 (bool)",
    "card.signature": "카드 뒷면 서명 여부 (bool)",
    "card.name_matches_passport": "카드 영문명과 여권 영문명 일치 여부 (bool)",
    "card.expiry_date": "카드 유효기한 (YYYY-MM 또는 YYYY-MM-DD)",
    "card.type": "카드 종류 (credit | debit)",
    "card.locked": "비밀번호 누적 오류로 카드가 잠겨 사용할 수 없는 상태인지 (bool). 해외거래정지·명의도용차단과는 다른 것이다",
    "card.ic_pin_registered": "IC칩 비밀번호가 등록·재기록되어 있는지 (bool)",
    "card.identity_theft_block": "명의도용 차단서비스 이용 여부 (bool). 켜져 있으면 인증 문자메시지를 받지 못한다",
    # 계좌 상태
    "account.nonface_open_block": "비대면 계좌개설 안심차단 설정 여부 (bool)",
    "account.id_scan_quality": "신분증 촬영 품질 (pass | fail)",
    "account.phone_auth": "본인명의 휴대폰 인증 (pass | fail)",
    "account.recent_open_dates": "최근 계좌개설 이력 날짜 목록 (list[YYYY-MM-DD])",
    # 상황값 (거래 시점 정보)
    "context.amount_krw": "이번 결제 금액 (원)",
    "context.tne_accumulated_krw": "T&E 업종 누적 이용액 (원)",
    "context.daily_used_krw": "당일 누적 이용액 (원)",
    "context.monthly_used_krw": "당월 누적 이용액 (원)",
    "context.account_type": "개설하려는 계좌 종류 (문자열)",
    "context.travel_end_date": "해외 체류 종료 예정일 (YYYY-MM-DD)",
}

ALLOWED_OPS: dict[str, str] = {
    "eq": "같다", "neq": "다르다", "in": "목록에 포함", "not_in": "목록에 미포함",
    "gte": "이상", "lte": "이하", "gt": "초과", "lt": "미만",
    "exists": "값이 존재", "not_exists": "값이 없음",
    "date_after": "기준일 이후", "date_before": "기준일 이전",
    "within_days": "N일 이내", "not_within_days": "N일 이내가 아님",
    "count_lte": "기간 내 횟수 이하", "count_gte": "기간 내 횟수 이상",
}

CATEGORIES = ["setting", "document", "limit", "temporal", "eligibility"]

# category 는 이름만 주면 LLM 이 흔들린다. 뜻을 함께 준다.
CATEGORY_MEANING = """
  setting     : 앱·시스템에서 켜고 끄는 **설정 상태** (해외거래정지, 안심차단, DCC 차단)
  document    : **실물 카드·서류**에 관한 것 (뒷면 서명, 여권 영문명 일치, 신분증)
  limit       : **금액·횟수 한도** (1회/1일 한도, 누적 한도)
  temporal    : **날짜·기간** 조건 (유효기한, N일 이내, 신청 후 경과일)
  eligibility : **자격 요건** (연령, 적용 대상 여부, 계좌·카드 종류)
"""
