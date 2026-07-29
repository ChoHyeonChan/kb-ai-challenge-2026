"""조건 추출 프롬프트.

★ 이 파일이 A4의 핵심이다. 로직 파일에 프롬프트 문자열을 박지 않고 여기만 고친다.

설계 근거 — directed symbolic prompting
  통제된 어휘(허용 subject·op 목록)를 명시적으로 주면 형식화 성공률이 크게 오른다.
  (Neuro-Symbolic Framework for Public-Sector AI, arXiv:2512.12109 / FAccT 2026)
  자유롭게 두면 LLM 이 존재하지 않는 경로를 지어내고, 그 조건은 프로필과 매칭되지 않아 전부 unknown 이 된다.

구성 (파일이 길어지지 않도록 셋으로 나눠 둔다)
  vocabulary.py  허용 subject·op·category   ← 검증(validate)도 같은 목록을 본다
  examples.py    few-shot 예시
  prompt.py      규칙 + 조립 (이 파일)

[현찬 판단 자리]  이 파일에서 판단이 필요한 곳
  1. CONDITION_CRITERIA — 무엇을 '조건'으로 볼 것인가
  2. PITFALLS           — 관측된 실패를 막는 규칙 (지울 때는 재현되는지 먼저 확인)
  3. CONFIDENCE_RULE    — 언제 신뢰도를 낮출 것인가
  4. REMEDY_RULE        — 앱에서 해결 가능하다는 것의 정의
"""
from __future__ import annotations

from src.extract.examples import FEW_SHOTS
from src.extract.rules import (
    CONDITION_CRITERIA,
    CONFIDENCE_RULE,
    PITFALLS,
    REMEDY_RULE,
)
from src.extract.vocabulary import (
    ALLOWED_OPS,
    ALLOWED_SUBJECTS,
    CATEGORY_MEANING,
)


SYSTEM_PROMPT = f"""당신은 금융 약관·안내문에서 **기계가 판정할 수 있는 조건**을 추출한다.

{CONDITION_CRITERIA}

{PITFALLS}

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
