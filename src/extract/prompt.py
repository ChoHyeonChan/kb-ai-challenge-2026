"""조건 추출 프롬프트.

★ 이 파일이 A4의 핵심이다. 로직 파일에 프롬프트 문자열을 박지 않고 여기만 고친다.

설계 근거 — directed symbolic prompting
  통제된 어휘(허용 subject·op 목록)를 명시적으로 주면 형식화 성공률이 크게 오른다.
  (Neuro-Symbolic Framework for Public-Sector AI, arXiv:2512.12109 / FAccT 2026)
  자유롭게 두면 LLM 이 존재하지 않는 경로를 지어내고, 그 조건은 프로필과 매칭되지 않아 전부 unknown 이 된다.

[현찬 판단 자리]  아래 4곳에 판단이 필요하다. 주석 참고.
  1. ALLOWED_SUBJECTS   — 어떤 상태값을 조건이 참조할 수 있는가
  2. CONDITION_CRITERIA — 무엇을 '조건'으로 볼 것인가
  3. CONFIDENCE_RULE    — 언제 신뢰도를 낮출 것인가
  4. FEW_SHOTS          — 예시로 무엇을 보여줄 것인가
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# 1. 허용 subject 경로  [현찬 판단]
#    프로필(C2)에 실제로 존재하는 경로만 넣는다.
#    여기 없는 경로를 LLM 이 만들면 그 조건은 영원히 unknown 이 된다.
#    새 경로가 필요하면 data/profiles/*.json 에도 함께 추가할 것.
# ─────────────────────────────────────────────────────────────
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
    # 계좌 상태
    "account.nonface_open_block": "비대면 계좌개설 안심차단 설정 여부 (bool)",
    "account.id_scan_quality": "신분증 촬영 품질 (pass | fail)",
    "account.phone_auth": "본인명의 휴대폰 인증 (pass | fail)",
    "account.recent_open_dates": "최근 계좌개설 이력 날짜 목록 (list[YYYY-MM-DD])",
    # 상황값 (거래 시점 정보)
    "context.amount_krw": "이번 결제 금액 (원)",
    "context.tne_accumulated_krw": "T&E 업종 누적 이용액 (원)",
    "context.daily_used_krw": "당일 누적 이용액 (원)",
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


# remedy.actionable_in_app 은 우리 서비스의 핵심 인사이트를 담는 필드다.
# 정의가 흔들리면 "앱에서 해결 불가" 배지가 엉뚱하게 붙는다.
REMEDY_RULE = """
remedy 는 '미충족일 때 무엇을 해야 하는가'다.

**actionable_in_app** — 앱·인터넷뱅킹·홈페이지에서 **직접 처리**할 수 있는가
  true  : 원문에 앱/홈페이지/인터넷뱅킹 채널이 **하나라도** 언급되면 true.
          다른 채널(영업점·고객센터)이 함께 적혀 있어도 **true 다.**
  false : 앱으로는 불가능한 경우에만 false.
          예) 영업점 방문만 가능 / 카드 재발급 필요 / 실물 카드에 직접 조치

**channels** — 가능한 모든 경로를 접두어와 함께 나열한다
  "app:KB Pay"  "web:홈페이지"  "callcenter:1588-1688"  "branch:영업점"  "self:본인 조치"
  원문에 적힌 채널만 넣는다. 없는 채널을 추측해 넣지 않는다.

**primary_path** — 가장 빠른 경로 하나를 문장으로. 원문에 근거가 있을 때만 구체적으로 적는다.
"""


# ─────────────────────────────────────────────────────────────
# 2. 무엇을 '조건'으로 볼 것인가  [현찬 판단]
#    이 기준이 느슨하면 안내문·홍보문구까지 조건으로 뽑힌다.
#    너무 빡빡하면 실제 조건을 놓친다. 문서 2~3개로 돌려보며 조정할 것.
# ─────────────────────────────────────────────────────────────
CONDITION_CRITERIA = """
조건이란: 사용자가 목표를 달성하기 위해 **충족해야 하는 상태**를 말한다.
충족 여부를 참/거짓으로 판정할 수 있어야 한다.

조건이다:
  - "해외거래정지를 등록했는지 확인"        → 해외거래정지가 해제되어 있어야 함
  - "1일 한도 600만원 상당 USD"             → 이용액이 한도 이내여야 함
  - "카드 뒷면 본인 서명 필수 기재"          → 서명이 되어 있어야 함
  - "해제는 반드시 지점을 방문해 신청"       → 해제 상태여야 함 (해결 경로는 지점)

조건이 아니다:
  - "해외 여행 시 유용한 팁을 알려드립니다"   → 안내문
  - "DCC는 약 3~8% 수수료가 부과됩니다"      → 설명. 단 '차단 해제 여부'는 조건
  - "고객센터 1588-1688"                     → 연락처
  - "이 콘텐츠는 2025년 3월 기준입니다"       → 메타정보
"""


# ─────────────────────────────────────────────────────────────
# 3. 신뢰도 규칙  [현찬 판단]
#    "근거 100%"를 주장하려면 해석이 개입한 지점을 스스로 드러내야 한다.
# ─────────────────────────────────────────────────────────────
CONFIDENCE_RULE = """
confidence 는 '원문이 조건을 얼마나 직접적으로 말하는가'다.

  high   : 원문이 조건을 그대로 서술한다. 옮기면서 의미를 바꾸지 않았다.
  medium : 원문을 해석해 조건으로 바꿨다. 반드시 note 에 무엇을 어떻게 옮겼는지 적는다.
  low    : 원문만으로는 조건을 확정하기 어렵다. note 에 무엇이 불확실한지 적는다.

medium/low 인데 note 가 비어 있으면 잘못된 출력이다.
"""


# ─────────────────────────────────────────────────────────────
# 4. 예시  [현찬 판단] — 표 행 / 문장 / 해석개입 세 유형을 보여준다
# ─────────────────────────────────────────────────────────────
FEW_SHOTS = """
[예시 1 — 표 행에서 한도 조건]
입력 청크: "1일 한도 | 현금인출/가맹점이용 | 600만원 상당의 달러(USD) 환산액"
출력:
{
  "is_condition": true,
  "conditions": [{
    "id": "c_limit_daily",
    "label": "1일 이용한도 이내여야 합니다 (600만원 상당 USD)",
    "category": "limit",
    "predicate": {"subject": "context.daily_used_krw", "op": "lte", "value_json": "6000000"},
    "severity": "blocking",
    "remedy": {"actionable_in_app": true, "channels": ["app:KB Pay"], "primary_path": "한도 조정"},
    "evidence_quote": "1일 한도 | 현금인출/가맹점이용 | 600만원 상당의 달러(USD) 환산액",
    "confidence": "high",
    "note": null
  }]
}

[예시 2 — 앱에서 해결 불가한 조건]
입력 청크: "서비스 해제는 반드시 지점을 방문해 직접 신청해야 합니다. 다만, 신청할 때와 달리, 내가 거래하지 않는 금융회사에서도 해제할 수 있어요."
출력:
{
  "is_condition": true,
  "conditions": [{
    "id": "c_nonface_open_block",
    "label": "비대면 계좌개설 안심차단이 해제되어 있어야 합니다",
    "category": "setting",
    "predicate": {"subject": "account.nonface_open_block", "op": "eq", "value_json": "false"},
    "severity": "blocking",
    "remedy": {"actionable_in_app": false, "channels": ["branch:금융회사 지점"],
               "primary_path": "금융회사 지점 방문 (신분증 지참)",
               "note": "거래하지 않는 금융회사 지점에서도 해제 가능"},
    "evidence_quote": "서비스 해제는 반드시 지점을 방문해 직접 신청해야 합니다. 다만, 신청할 때와 달리, 내가 거래하지 않는 금융회사에서도 해제할 수 있어요.",
    "confidence": "high",
    "note": null
  }]
}

[예시 3 — 채널이 여러 개인 경우: 앱이 하나라도 있으면 actionable_in_app=true]
입력 청크: "해외에서 카드 사용이 필요한 경우 홈페이지/KB Pay, KB국민카드 고객센터(1588-1688), 영업점 방문을 통해 해외거래정지 해제가 필요합니다."
출력:
{
  "is_condition": true,
  "conditions": [{
    "id": "c_overseas_block",
    "label": "해외거래정지가 해제되어 있어야 합니다",
    "category": "setting",
    "predicate": {"subject": "card.overseas_block_online", "op": "eq", "value_json": "false"},
    "severity": "blocking",
    "remedy": {"actionable_in_app": true,
               "channels": ["app:KB Pay", "web:홈페이지", "callcenter:1588-1688", "branch:영업점"],
               "primary_path": "KB Pay 에서 해외거래정지 해제",
               "note": null},
    "evidence_quote": "해외에서 카드 사용이 필요한 경우 홈페이지/KB Pay, KB국민카드 고객센터(1588-1688), 영업점 방문을 통해 해외거래정지 해제가 필요합니다.",
    "confidence": "high",
    "note": null
  }]
}
→ '영업점 방문'이라는 표현이 있어도 KB Pay 가 함께 있으므로 actionable_in_app 은 true 다.

[예시 4 — 실물 조치: 앱과 무관하므로 false, 단 영업점도 아님]
입력 청크: "카드 뒷면 본인 서명을 기재해주세요. 서명이 없는 카드에 노출·복제 사고가 발생하는 경우 보상이 어려울 수 있습니다."
출력:
{
  "is_condition": true,
  "conditions": [{
    "id": "c_card_signature",
    "label": "카드 뒷면에 본인 서명이 되어 있어야 합니다",
    "category": "document",
    "predicate": {"subject": "card.signature", "op": "eq", "value_json": "true"},
    "severity": "warning",
    "remedy": {"actionable_in_app": false, "channels": ["self:실물 카드"],
               "primary_path": "카드 뒷면에 직접 서명", "note": null},
    "evidence_quote": "카드 뒷면 본인 서명을 기재해주세요. 서명이 없는 카드에 노출·복제 사고가 발생하는 경우 보상이 어려울 수 있습니다.",
    "confidence": "high",
    "note": null
  }]
}
→ 실물 카드에 하는 조치이므로 category 는 document, channels 는 self 다.

[예시 5 — 조건이 아님]
입력 청크: "비대면 계좌개설 안심차단 서비스 특징과 이용방법을 알려드릴게요."
출력: {"is_condition": false, "conditions": []}
"""


SYSTEM_PROMPT = f"""당신은 금융 약관·안내문에서 **기계가 판정할 수 있는 조건**을 추출한다.

{CONDITION_CRITERIA}

## 반드시 지킬 것

1. **evidence_quote 는 입력 청크의 문장을 그대로 복사한다.** 요약·윤문·재작성 금지.
   원문에 없는 문자열을 넣으면 검증 단계에서 폐기된다.

2. **predicate.subject 는 아래 목록에서만 고른다.** 목록에 없는 경로를 지어내지 않는다.
   해당하는 경로가 없으면 그 조건은 추출하지 않는다 (is_condition=false 또는 해당 조건 제외).

{chr(10).join(f"   - {k}: {v}" for k, v in ALLOWED_SUBJECTS.items())}

3. **op 는 아래에서만 고른다.**
{chr(10).join(f"   - {k}: {v}" for k, v in ALLOWED_OPS.items())}

4. **category 는 다음 중 하나다.** 뜻을 보고 고른다.
{CATEGORY_MEANING}

4-1. **predicate.value_json 은 JSON 리터럴을 문자열로 적는다.**
   - 불리언:   "false"  /  "true"
   - 숫자:     "6000000"
   - 문자열:   "\"2029-05\""   (따옴표를 포함한 JSON 문자열)
   - 목록:     "[\"수시입출금\", \"외화계좌\"]"
   - 현재기준: "{{\"now_plus_days\": 0}}"        (date_after/date_before 에 사용)
   - 기간:     "{{\"days\": 20}}"                 (within_days 에 사용)
   - 기간+횟수: "{{\"days\": 20, \"n\": 0}}"      (count_lte/count_gte 에 사용)
   - 다른 값 참조: "{{\"ref\": \"context.travel_end_date\"}}"

5. {REMEDY_RULE}

6. {CONFIDENCE_RULE}

7. 하나의 청크에서 조건이 여러 개 나올 수 있다. 무리해서 쪼개지는 말 것.

{FEW_SHOTS}
"""


def build_user_prompt(chunk_text: str, section: str, goal_label: str) -> str:
    return f"""목표: {goal_label}
문서 섹션: {section or "(없음)"}

입력 청크:
\"\"\"{chunk_text}\"\"\"

위 청크에서 조건을 추출하라."""
