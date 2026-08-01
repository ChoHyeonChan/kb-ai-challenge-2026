# 재현 절차

> 담당: 팀원 (B8) · 2차 실행 Claude
> 기준일: 2026-07-31
> 상태: **완주 성공.** 단, 1차 시도는 환경 문제로 중단됐고 그 기록도 그대로 남긴다.
>
> **이 재현 시험이 실제 결함 하나를 잡았다** (3-B절). 형식적인 절차가 아니었다.

## 1. 목표와 기준

README와 `docs/팀원_시작하기.md`의 절차만 사용해, 기존 가상환경·캐시를 쓰지 않는 새 폴더에서 데모와 테스트가 실행되는지 확인한다.

## 2. 재현 절차

Windows PowerShell에서 다음 순서로 실행한다.

```powershell
git clone https://github.com/ChoHyeonChan/kb-ai-challenge-2026.git
cd kb-ai-challenge-2026
git config core.hooksPath .githooks

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m src.extract.assemble --dry-run
python -m pytest tests\test_determinism.py tests\test_edge.py -v
python -m uvicorn src.api.main:app --port 8000 --reload
```

`.env`가 필요한 LLM 기능을 시험할 때만 `.env.example`을 복사해 각자 발급한 키를 입력한다. `.env`는 커밋하거나 로그에 출력하지 않는다. 판정 엔진·테스트·`assemble --dry-run`은 API 키 없이 실행한다.

## 3. 2026-07-31 클린 설치 시도 로그

### 환경

- OS: Windows (PowerShell)
- 복제 위치: 새 임시 폴더 `C:\Users\User\AppData\Local\Temp\kb-ai-challenge-2026-b8-20260731`
- 기존 프로젝트의 `.venv`·캐시는 사용하지 않음

### 성공한 단계

```text
> git clone --no-local C:\Users\User\Documents\kb-ai-challenge-2026 C:\Users\User\AppData\Local\Temp\kb-ai-challenge-2026-b8-20260731
Cloning into 'C:\Users\User\AppData\Local\Temp\kb-ai-challenge-2026-b8-20260731'...

> git -C C:\Users\User\AppData\Local\Temp\kb-ai-challenge-2026-b8-20260731 config core.hooksPath .githooks
```

### 중단 지점

```text
> python --version
PowerShell에서 python 실행기를 찾지 못함

> python -m venv .venv
실행 불가: Python 실행기가 없음

확인 결과
- .venv\pyvenv.cfg 없음
- .venv\Scripts\python.exe 없음
```

따라서 의존성 설치, `assemble --dry-run`, pytest, uvicorn 실행은 수행하지 못했다. 성공으로 기록하지 않는다.

## 3-B. 2026-07-31 클린 설치 완주 (Claude, 다른 폴더·다른 venv)

1차 시도가 Python 미설치로 멈춘 지점부터, Python 이 있는 환경에서 처음부터 다시 수행했다.

### ★ 이 과정에서 발견한 결함 — `pip install` 이 실패했다

```text
> python -m pip install -r requirements.txt
  File ".../pip/_internal/utils/encoding.py", line 34, in auto_decode
    return data.decode(locale.getpreferredencoding(False) or ...)
UnicodeDecodeError: 'cp949' codec can't decode byte 0xec in position 2
```

**원인**: pip 은 `requirements.txt` 를 UTF-8 이 아니라 **시스템 로케일 인코딩**으로 읽는다.
한국어 Windows 는 cp949 이므로, 파일에 있던 **UTF-8 한글 주석**에서 죽는다.

**영향**: 한국어 Windows 를 쓰는 사람은 **의존성 설치조차 못 한다.** 가장 흔한 심사 환경이다.

**조치**: `requirements.txt` 의 주석을 전부 ASCII 로 바꾸고, 재발 방지를 위해
그 이유를 파일 첫 줄에 남겼다 (커밋 `b5f53b3`).

> 이 결함은 코드를 읽어서는 보이지 않는다. **실제로 새 환경에서 돌려봐야 나온다.**
> "돌아갈 것이다"와 "돌려봤다"의 차이가 이것이다.

### 수정 후 전 단계 실행 로그

```text
[1] git clone + git config core.hooksPath .githooks
    b5f53b3 fix: requirements.txt 를 ASCII 로

[2] python --version
    Python 3.13.2
    python -m venv .venv                        OK

[3] .venv/Scripts/python -m pip install -r requirements.txt
    OK  (오류 없음)

[4] python -m pytest tests/ -q
    7 passed, 1 warning in 0.77s

[5] python -m src.extract.assemble --dry-run     <- API 키 없이 실행됨
    account_open_nonface     : 추출 7건  -> 병합 2개  -> 승인 1  / 반려 1 / 미검수 0
    overseas_payment_online  : 추출 37건 -> 병합 14개 -> 승인 11 / 반려 3 / 미검수 0

[6] python -m uvicorn src.api.main:app --port 8020
    GET  /                                    200
    GET  /api/goals                           200
    GET  /api/tree/overseas_payment_online    200
    GET  /static/style.css                    200
    POST /api/judge                           200
         -> verdict=blocked, 미충족 3 / 충족 7 / 모름 1
```

### 확인된 것

- **API 키 없이 데모와 테스트가 전부 동작한다.** 판정 경로에 LLM 호출이 없기 때문이다.
  `.env` 는 조건 추출을 처음부터 다시 돌릴 때만 필요하다.
- 새 venv·새 폴더에서 기존 캐시를 전혀 쓰지 않았다.

## 4. 다음 재현 전 준비

1. Python 3.12 이상을 설치하고 새 PowerShell에서 `python --version`이 출력되는지 확인한다.
2. 위의 **2. 재현 절차**를 새 폴더에서 처음부터 다시 실행한다.
3. pytest와 uvicorn의 실제 전체 출력을 이 문서의 3절에 추가하고, 아래 체크 항목을 완료 처리한다.

## 5. 확인된 산출물

| 단계 | 1차 (팀원) | 2차 (Claude) |
|---|---|---|
| 새 폴더에 저장소 복제 | 완료 | 완료 |
| Git 보안 훅 경로 설정 | 완료 | 완료 |
| Python 가상환경 생성 | 중단 (Python 미설치) | 완료 |
| 의존성 설치 | — | 완료 (**결함 1건 발견·수정 후**) |
| 결정론성·엣지 테스트 | — | 완료 (7 passed) |
| 조건 트리 조립 dry-run | — | 완료 |
| 판정 API 응답 확인 | — | 완료 (200 / blocked) |
| 데모 화면 렌더 | — | 완료 (200) |

> 1차 기록을 지우지 않는다. **중단된 시도도 재현 가능성에 대한 정보**이고,
> 그 기록이 없었으면 2차를 다른 환경에서 돌려볼 이유도 없었다.
