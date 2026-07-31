# 재현 절차

> 담당: 팀원 (B8)
> 기준일: 2026-07-31
> 상태: **설치 환경 문제로 중단됨. 아래 로그는 실제 클린 복제·실행 시도의 기록이다.**

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

## 4. 다음 재현 전 준비

1. Python 3.11 이상을 설치하고 새 PowerShell에서 `python --version`이 출력되는지 확인한다.
2. 위의 **2. 재현 절차**를 새 폴더에서 처음부터 다시 실행한다.
3. pytest와 uvicorn의 실제 전체 출력을 이 문서의 3절에 추가하고, 아래 체크 항목을 완료 처리한다.

## 5. 확인된 산출물

- [x] 새 폴더에 저장소 복제
- [x] Git 보안 훅 경로 설정
- [ ] Python 가상환경 생성
- [ ] 의존성 설치
- [ ] 조건 트리 조립 dry-run
- [ ] 판정 API 응답 확인
- [ ] 데모 화면 렌더
- [ ] 결정론성·엣지 테스트 통과
