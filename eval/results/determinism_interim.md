# 결정론성 중간 측정

> 정식 테스트 스위트는 `tests/test_determinism.py` (팀원 담당). 이 문서는 **중간 측정**이다.
> 비교 시 `evaluated_at`(실행 시각)을 제외하고, 조건 목록은 `id` 기준 정렬 후 비교했다.

| 항목 | 값 |
|---|---|
| 조합 (트리 × 프로필) | 10 |
| 조합당 반복 | 200회 |
| 총 판정 횟수 | 2000 |
| **결과가 하나뿐인 조합** | **10 / 10** |
| **일치율** | **100.0%** |
| 판정 1회 소요 (중앙값) | 0.0556 ms |

판정과 해결 계획을 **함께** 직렬화해 비교했다. 둘 중 하나라도 흔들리면 불일치로 잡힌다.

## 조합별

| 목표 | 프로필 | 판정 | 서로 다른 결과 수 |
|---|---|---|---|
| account_open_nonface | account_ok | ok | 1 ✓ |
| account_open_nonface | account_safeblock | blocked | 1 ✓ |
| account_open_nonface | overseas_blocked | indeterminate | 1 ✓ |
| account_open_nonface | overseas_ok | indeterminate | 1 ✓ |
| account_open_nonface | partial_unknown | indeterminate | 1 ✓ |
| overseas_payment_online | account_ok | indeterminate | 1 ✓ |
| overseas_payment_online | account_safeblock | indeterminate | 1 ✓ |
| overseas_payment_online | overseas_blocked | blocked | 1 ✓ |
| overseas_payment_online | overseas_ok | ok | 1 ✓ |
| overseas_payment_online | partial_unknown | indeterminate | 1 ✓ |

## 이 수치가 의미하는 것

판정 경로에 LLM 호출이 없다는 설계가 **말이 아니라 측정으로** 확인된다.
LLM 은 조건을 문서에서 뽑을 때만 쓰이고, 그 결과는 파일(조건 트리)로 고정된다.
같은 트리와 같은 사용자 상태라면 언제 실행해도 같은 답이 나온다.
