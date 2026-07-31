"""추출 예시 (few-shot).

[현찬 판단 자리] 무엇을 예시로 보여줄 것인가.
  ★ 예시 인용문은 **실제 수집 문서의 문장을 그대로 쓰지 않는다.**
    모델이 그 문장을 그대로 베껴 다른 청크의 근거로 내놓아 검증에서 폐기되는 사고가 있었다.
    형식을 보여야 할 때는 가상 문장임을 명시한다.
"""
from __future__ import annotations

FEW_SHOTS = """
[예시 1 — 표 행에서 한도 조건. ★ 해결 채널이 원문에 없으면 **비운다**]
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
    "remedy": {"actionable_in_app": null, "channels": [], "primary_path": null, "note": null},
    "evidence_quote": "1일 한도 | 현금인출/가맹점이용 | 600만원 상당의 달러(USD) 환산액",
    "confidence": "high",
    "note": null
  }]
}
→ 이 청크는 한도 **수치**만 말한다. 어디서 조정하는지는 한 글자도 없다.
  그런데 "앱에서 한도 조정"이라고 쓰면 그것은 **지어낸 것**이다.
  `false` 도 주장이다 — "앱에서 안 된다"고 말하는 것이므로 근거가 있어야 한다.
  모르면 **null**. 이것이 유일하게 정직한 답이다.

[예시 2 — 방향 뒤집힘 방지 + 앱에서 해결 불가]
※ 아래 청크는 형식을 보이기 위한 **가상 문장**이다. 실제 KB 문서 인용이 아니다.
   실제 인용은 언제나 입력 청크에서만 가져온다.
목표: 비대면 계좌개설
입력 청크: "안심차단이 등록된 상태에서는 비대면 채널로 계좌를 개설할 수 없으며, 해제는 영업점 방문으로만 가능합니다."
출력:
{
  "is_condition": true,
  "conditions": [{
    "id": "c_nonface_open_block",
    "label": "비대면 계좌개설 안심차단이 해제되어 있어야 합니다",
    "category": "setting",
    "predicate": {"subject": "account.nonface_open_block", "op": "eq", "value_json": "false"},
    "severity": "blocking",
    "remedy": {"actionable_in_app": false, "channels": ["branch:영업점"],
               "primary_path": "영업점 방문 (신분증 지참)", "note": null},
    "evidence_quote": "안심차단이 등록된 상태에서는 비대면 채널로 계좌를 개설할 수 없으며, 해제는 영업점 방문으로만 가능합니다.",
    "confidence": "high",
    "note": null
  }]
}
→ 원문은 "등록되면 안 된다"고 말한다. 조건은 그 반대인 **eq false** 다 (오류 ①).

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

[예시 5 — 조건이 아님: 안내문]
입력 청크: "비대면 계좌개설 안심차단 서비스 특징과 이용방법을 알려드릴게요."
출력: {"is_condition": false, "conditions": []}

[예시 6 — 조건이 아님: 목표와 무관 (오류 ③)]
목표: 해외 온라인 결제
입력 청크: "해외이용 이의신청은 매출표 접수일로부터 45일 이내에 신청하셔야 하며, 기일 초과 시 접수가 거절될 수 있습니다."
출력: {"is_condition": false, "conditions": []}
→ 이의신청 기한은 **결제가 되게 하는 조건**이 아니라 결제 후 분쟁 절차다.

[예시 7 — 조건이 아님: 달러로만 적힌 한도 (오류 ④)]
목표: 해외 온라인 결제
입력 청크: "해외 T&E업종 이용한도는 5,500달러입니다."
출력: {"is_condition": false, "conditions": []}
→ 원화 기준이 없으면 환산이 필요하고, 환율은 매일 달라져 판정이 흔들린다. 추출하지 않는다.
"""
