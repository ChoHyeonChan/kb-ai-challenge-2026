# 팀원 구현 스펙 — 무엇을 어떻게 만드나

> 제8회 KB AI Challenge · 마감 8/3 16:00 (**8/2 제출**)
> 이 문서는 **구현 지시서**다. 처음이라면 `팀원_시작하기.md` 부터 보고 여기로 오면 된다.
> 협업 방식은 `TEAM_GUIDE.md`, AI 규약은 루트의 `AGENTS.md`.
> Codex에 그대로 넣어도 되게 썼다. 다만 **결과는 반드시 직접 실행해서 확인할 것.**
>
> **진행 상황 (2026-07-29 기준)**
> M1 실측 완료(326초) · B4 프로필 5종 완료 · 조건트리 12개 확정 → **남은 것은 B6·B7·B8**

---

## 0. 당신이 만드는 것 — 전체 그림

```
M1  수동 확인 시간 실측        ← ✅ 완료 (326초)
B4  가상 사용자 프로필 3~5종    ← ✅ 완료 (data/profiles/ 5종)
B6  결정론성 테스트            ← tests/test_determinism.py   ★ 배점 직결 · 지금 할 것
B7  엣지 입력 테스트           ← tests/test_edge.py
B8  클린설치 재현 기록          ← docs/REPRODUCE.md
D2' 기술설명서 완성            ← Claude 초안 위에
```

**담당 폴더**: `tests/` · `data/profiles/` · `docs/`
**남의 폴더**(`src/extract/`, `src/judge/` 등)를 고쳐야 하면 **먼저 알린다.**

---

## 1. 공통 — 이것부터 알고 시작

### 1.1 판정 함수 시그니처 (계약 · 변경 불가)

```python
# src/judge/engine.py 에 구현될 함수. 당신은 이걸 호출만 한다.
def judge(
    tree: ConditionTree,        # data/trees/*.json 을 로드한 것
    profile: UserProfile,       # data/profiles/*.json 을 로드한 것
    context: dict | None = None # 결제금액 등 상황값. 없으면 None
) -> Verdict:
    ...
```

### 1.2 Verdict(판정 결과) 구조 — C3

```json
{
  "goal_id": "overseas_payment_online",
  "verdict": "blocked",
  "unmet":   [ { "id": "...", "label": "...", "severity": "blocking",
                 "remedy": {...}, "evidence": {...} } ],
  "met":     [ { "id": "...", "label": "..." } ],
  "unknown": [ { "id": "...", "label": "...", "reason": "여권 정보 미보유" } ],
  "low_confidence": [ { "id": "...", "label": "...", "reason": "해석 개입" } ],
  "engine_version": "1.0.0",
  "tree_collected_at": "2026-07-28",
  "evaluated_at": "2026-07-29T10:00:00"     ← ★ 매 실행마다 달라짐. 비교에서 제외
}
```

- `verdict`: `"ok"` | `"blocked"` | `"indeterminate"`  ← **3값이다** (문서 초판의 2값에서 바뀜)
  - `blocked` : blocking 조건이 미충족 → 지금은 안 된다
  - `indeterminate` : 미충족은 없지만 **판정에 필요한 값을 몰라** 된다고 말할 수 없다
  - `ok` : blocking 조건을 전부 확인했고 모두 충족
  > `indeterminate` 가 있는 이유: 모르는 상태에서 "됩니다"라고 답하지 않기 위해서다.
  > **B7 엣지 테스트의 핵심이 이것**이다 — 빈 프로필에 `ok` 가 나오면 버그다.
- **네 분류를 반드시 구분**: 충족 / 미충족 / **모름** / **신뢰도 낮음**
- `evaluated_at`은 **실행 시각**이라 매번 다르다. **결정론성 비교 시 제외해야 한다** (1.3 참조)

### 1.3 ★ 결정론성 비교 규칙 (B6에서 쓸 것)

같은 입력에 같은 결과여야 하지만, **아래는 예외**로 처리한다.

| 필드 | 처리 |
|---|---|
| `evaluated_at` | **비교 제외** (실행 시각) |
| `unmet` / `met` / `unknown` 배열 | **`id` 기준 정렬 후 비교** (순서가 달라도 같은 결과로 본다) |
| dict 키 순서 | 무시 (`json.dumps(..., sort_keys=True)`) |

> 이 규칙을 안 지키면 **실제로는 결정론적인데 테스트가 실패**한다. 반대로 너무 느슨하게 잡으면 진짜 문제를 놓친다.

---

## 2. M1 — 수동 확인 시간 실측  ✅ 완료 (기록만 참고)

> **가장 먼저 할 일.** 판정 엔진이 나오기 전에만 순수하게 측정할 수 있다.
> 이미 답을 알고 재면 시간이 왜곡된다.

### 측정 방법
KB Pay / KB스타뱅킹을 켜고, **해외결제가 되는지 확인하기 위해** 아래 7개를 하나씩 직접 찾아본다. 스톱워치로 잰다.

| # | 확인할 조건 | 어디서 |
|---|---|---|
| 1 | 해외거래정지(온라인) 해제 여부 | KB Pay 설정 |
| 2 | 해외원화결제(DCC) 차단 여부 | 별도 메뉴 |
| 3 | 카드 뒷면 서명 | 실물 카드 |
| 4 | 카드–여권 영문명 일치 | 카드 + 여권 |
| 5 | 카드 유효기한 | 실물 카드 |
| 6 | 1회/1일 이용한도 | FAQ 또는 안내 페이지 |
| 7 | T&E 업종 누적 한도 | FAQ |

### 기록 양식 → `eval/results/manual_lookup_time.md`

```markdown
# 수동 확인 시간 실측

- 측정자:
- 측정일: 2026-07-27
- 환경: KB Pay 앱 / KB스타뱅킹 (기기: ___)

| # | 조건 | 소요(초) | 어디서 찾았나 | 메모 |
|---|---|---|---|---|
| 1 | 해외거래정지 | | | |
| 2 | DCC 차단 | | | |
| 3 | 뒷면 서명 | | | |
| 4 | 영문명 일치 | | | |
| 5 | 유효기한 | | | |
| 6 | 1회/1일 한도 | | | |
| 7 | T&E 한도 | | | |
| | **합계** | | | |

## 관찰 기록
- 메뉴로 바로 찾은 것 / 검색을 쓴 것:
- 앱을 벗어나 검색한 것(포털·블로그):
- 끝내 못 찾은 것:
- 중간에 포기하고 싶었던 지점:
```

### 완료 기준
- [ ] 7개 항목 각각의 소요 시간이 기록됨
- [ ] 합계 시간 (초 단위)
- [ ] **못 찾은 항목이 있으면 "못 찾음"으로 기록** ← 이것도 데이터다. 억지로 채우지 말 것

> **주의: 정확할 필요는 없지만 정직해야 한다.** 짧게 보이려고 서두르거나 길게 보이려고 늘리지 않는다. 평소처럼 찾는다.

---

## 3. B4 — 가상 사용자 프로필

### 만들 파일
```
data/profiles/
├─ overseas_blocked.json       ① 해외결제 막힌 사람
├─ overseas_ok.json            ② 해외결제 되는 사람
├─ account_safeblock.json      ③ 안심차단 걸린 사람
├─ account_ok.json             ④ 계좌개설 가능한 사람
└─ partial_unknown.json        ⑤ 값을 일부 모르는 사람  ★ 중요
```

### 형식 (C2)

```json
{
  "profile_id": "overseas_blocked",
  "description": "해외거래정지·DCC 차단이 둘 다 켜져 있는 사용자",
  "card": {
    "overseas_block_online": true,
    "dcc_block": true,
    "signature": true,
    "name_matches_passport": null,
    "expiry_date": "2029-05-31",
    "type": "debit"
  },
  "account": {
    "nonface_open_block": null,
    "id_scan_quality": null,
    "phone_auth": null
  },
  "context": {
    "amount_krw": 32000,
    "travel_end_date": null
  }
}
```

### 규칙
- **모르는 값은 `null`.** 추측해서 채우지 않는다 → 판정에서 `unknown`으로 분류된다
- `description`에 **이 프로필이 어떤 상황인지** 한 줄로 쓴다 (문서에 그대로 쓰인다)
- ⑤ `partial_unknown`은 **일부러 `null`을 많이 넣는다.** *"모르는 건 모른다고 한다"* 를 보여주는 데모용

### 완료 기준
- [ ] 5개 파일 존재
- [ ] 각 파일이 스키마 검증 통과 (`src/judge/schema.py`의 `UserProfile`)
- [ ] 막힘/통과/불명 케이스가 모두 있음
- [ ] `description` 작성됨

---

## 4. B6 — 결정론성 테스트 ★ 배점 직결

> 우리 제안의 핵심 주장이 **"판정은 LLM이 하지 않으므로 같은 입력엔 같은 출력"** 이다.
> 이걸 증명하는 게 이 테스트고, 결과가 그대로 제출물이 된다.

### 만들 파일
```
tests/test_determinism.py
eval/results/determinism.md     ← 실행 결과 기록
```

### 구현 스펙

```python
# tests/test_determinism.py
import json
from pathlib import Path
from src.judge.engine import judge
from src.judge.schema import ConditionTree, UserProfile

REPEAT = 10          # 반복 횟수
IGNORE_FIELDS = {"evaluated_at"}   # 실행 시각은 제외


def canonical(verdict: dict) -> str:
    """비교용 정규화: 제외 필드 제거 → 배열 id 정렬 → 키 정렬 직렬화"""
    v = {k: val for k, val in verdict.items() if k not in IGNORE_FIELDS}
    for key in ("unmet", "met", "unknown", "low_confidence"):
        if key in v and isinstance(v[key], list):
            v[key] = sorted(v[key], key=lambda x: x["id"])
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def run_case(tree_path: Path, profile_path: Path) -> tuple[int, int]:
    """(일치 횟수, 전체 횟수) 반환"""
    tree = ConditionTree.model_validate_json(tree_path.read_text(encoding="utf-8"))
    profile = UserProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))

    results = [canonical(judge(tree, profile).model_dump()) for _ in range(REPEAT)]
    first = results[0]
    matches = sum(1 for r in results if r == first)
    return matches, REPEAT


def test_all_combinations():
    trees = sorted(Path("data/trees").glob("*.json"))
    profiles = sorted(Path("data/profiles").glob("*.json"))
    assert trees and profiles, "조건트리 또는 프로필이 없습니다"

    failures = []
    for t in trees:
        for p in profiles:
            matches, total = run_case(t, p)
            if matches != total:
                failures.append(f"{t.name} x {p.name}: {matches}/{total}")

    assert not failures, "결정론성 위반:\n" + "\n".join(failures)
```

### 결과 기록 → `eval/results/determinism.md`

```markdown
# 결정론성 측정 결과

- 실행일:
- 반복 횟수: 10
- 조건트리 수: __ / 프로필 수: __ → 조합 __건
- 제외 필드: evaluated_at (실행 시각)
- 배열 비교: id 기준 정렬 후 비교

| 조건트리 | 프로필 | 일치 | 결과 |
|---|---|---|---|
| overseas_payment_online | overseas_blocked | 10/10 | ✅ |
| ... | | | |

**전체 일치율: __%**

## 실행 로그
```
(pytest 출력 그대로 붙여넣기)
```
```

### 완료 기준
- [ ] 모든 (조건트리 × 프로필) 조합에서 **10/10 일치**
- [ ] 실행 로그가 `eval/results/determinism.md`에 있음
- [ ] **일치율이 100%가 아니면 즉시 공유** — 어딘가에 LLM 호출이나 랜덤이 끼어든 것이다

> ⚠️ 만약 실패하면 그건 당신 테스트의 문제가 아니라 **엔진의 설계 위반**일 가능성이 높다. 고치려 하지 말고 알려달라.

---

## 5. B7 — 엣지 입력 테스트

### 만들 파일
```
tests/test_edge.py
tests/cases/edge_cases.json     (선택)
```

### 반드시 포함할 케이스

| # | 입력 | 기대 동작 |
|---|---|---|
| 1 | 프로필의 모든 값이 `null` | 크래시 없이 전부 `unknown`으로 분류 |
| 2 | 존재하지 않는 `goal_id` | 명확한 예외 또는 빈 결과. **조용히 성공하면 안 됨** |
| 3 | 조건이 0개인 트리 | `verdict: "ok"` 또는 명시적 처리 |
| 4 | `context` 없이 호출 (`None`) | context 필요한 조건은 `unknown` |
| 5 | 프로필에 스키마에 없는 필드가 추가됨 | 무시하거나 검증 에러. 크래시 X |
| 6 | 날짜 형식이 잘못됨 (`"2029-13-45"`) | 검증 에러로 잡힘 |
| 7 | 숫자 자리에 문자열 (`amount_krw: "삼만원"`) | 검증 에러로 잡힘 |

### 완료 기준
- [ ] 7개 케이스 전부 테스트 존재
- [ ] **크래시(예상치 못한 예외) 0건**
- [ ] 각 케이스의 실제 동작이 문서에 기록됨

> 핵심은 "에러가 안 나는 것"이 아니라 **"예상 가능한 방식으로 실패하는 것"** 이다.
> 잘못된 입력에 조용히 `ok`를 뱉는 게 제일 나쁘다.

---

## 6. B8 — 클린설치 재현 기록

> 심사에서 실현가능성 15점의 핵심. *"제3자가 재현할 수 있는가"*
> **"될 것이다"가 아니라 "실제로 했다"의 기록**이어야 한다.

### 절차
1. **완전히 새 폴더**를 만든다 (기존 작업 폴더 X)
2. 리포를 새로 clone 또는 zip 압축 해제
3. README에 적힌 절차를 **그대로** 따라 한다
4. 막히는 지점이 있으면 **그것도 기록**한다 (그리고 README를 고친다)
5. 전체 터미널 출력을 복사해 붙인다

### 기록 → `docs/REPRODUCE.md`
양식은 파일에 이미 있다. 채우면 된다.

### 완료 기준
- [ ] 새 폴더에서 처음부터 실행 성공
- [ ] 터미널 로그 전문 첨부
- [ ] **README와 실제 절차가 일치** (다르면 README를 고침)
- [ ] Python 버전·OS 기재

> ⚠️ *"내 환경에선 되는데"* 가 제일 흔한 실패다. **캐시·기존 가상환경·이미 받아둔 데이터가 없는 상태**에서 해야 의미가 있다.

---

## 7. 기술설명서 완성

Claude가 초안을 만들면(7/30~31) 그 위에 완성한다.

### 반드시 들어갈 것
- [ ] 배점 6항목 대응 (문제정의15 / 활용가능성15 / 창의성20 / 기술적정성20 / 개발계획15 / 실현가능성15)
- [ ] **당신이 측정한 숫자** — M1 시간 실측, 결정론성 일치율
- [ ] 한계 장 (정직하게)
- [ ] 데이터 수집 범위·방법 명시

### 금지
- ❌ 측정하지 않은 수치 ("민원 20% 감소" 같은 것)
- ❌ 외부 이미지 (저작권 실격 조항) — 시각요소는 CSS/도형 자작
- ❌ 문서에 적었는데 실제로 없는 기능

---

## 8. 전체 완료 체크리스트

```
[ ] M1  시간 실측 → eval/results/manual_lookup_time.md
[ ] B4  프로필 5종 → data/profiles/
[ ] B6  결정론성 테스트 → 일치율 100% + eval/results/determinism.md
[ ] B7  엣지 테스트 7케이스 → 크래시 0
[ ] B8  클린설치 재현 → docs/REPRODUCE.md 로그 첨부
[ ] 서약서 · 개인정보동의서 개별 서명 (본인 몫)
[ ] AI 사용 기록 (docs/AI_USAGE.md에 본인 사용분 추가)
[ ] 기술설명서 완성
```

---

## 9. 막히면

| 상황 | 대응 |
|---|---|
| 스키마가 이해 안 됨 | `src/judge/schema.py`가 단일 출처. 그래도 모르면 물어본다 |
| 결정론성 테스트가 실패 | **고치려 하지 말고 즉시 공유.** 엔진 설계 문제일 가능성 |
| 계약(C1/C2/C3)을 바꿔야 할 것 같음 | **혼자 바꾸지 않는다.** 먼저 합의 |
| Codex가 같은 실패 반복 | 3번 시도 후 멈추고 상황 정리해서 공유 |

> 7일짜리 프로젝트에서 **잘못된 가정 위에 이틀 쌓는 것보다 10분 물어보는 게 낫다.**
