@echo off
REM 데모 실행. 처음부터 돌리려면:
REM   python -m src.collect.fetch  ^&^&  python -m src.collect.chunk
python -m uvicorn src.api.main:app --port 8000 --reload
