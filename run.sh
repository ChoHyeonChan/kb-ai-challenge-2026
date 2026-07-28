#!/usr/bin/env bash
# 데모 실행. 수집·청킹은 이미 되어 있다고 가정한다 (data/raw, data/chunks).
# 처음부터 돌리려면:  python -m src.collect.fetch && python -m src.collect.chunk
set -e
python -m uvicorn src.api.main:app --port 8000 --reload
