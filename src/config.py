"""경로·상수 단일 출처. 하드코딩 금지."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows 기본 콘솔(cp949)에서 한글·기호 출력이 깨지지 않도록.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent

# .env 를 환경변수로 로드한다. 없으면 조용히 넘어간다(수집·판정은 키 없이도 동작).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

DATA_DIR = ROOT / "data"
SOURCES_DIR = DATA_DIR / "sources"
RAW_DIR = DATA_DIR / "raw"
CHUNKS_DIR = DATA_DIR / "chunks"
TREES_DIR = DATA_DIR / "trees"
PROFILES_DIR = DATA_DIR / "profiles"

EVAL_DIR = ROOT / "eval" / "results"

SOURCES_FILE = SOURCES_DIR / "sources.yaml"

# LLM 캐시 — 같은 문서 재호출 방지 (비용 + 재현성)
LLM_CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", DATA_DIR / ".llm_cache"))

# 청킹 파라미터
CHUNK_MIN_CHARS = 40      # 이보다 짧은 조각은 버린다 (HTML: 메뉴·버튼 라벨 걸러내기용)

# 수동 확보한 평문(manual/*.txt)은 사람이 본문만 골라 저장한 것이라 버릴 잡음이 없다.
# 같은 40자 기준을 쓰면 "서비스 해제는 영업점에서만 가능합니다."(22자) 같은
# **핵심 문장이 통째로 사라진다.** 실제로 그 사고가 있었다.
CHUNK_MIN_CHARS_MANUAL = 12
CHUNK_MAX_CHARS = 1200    # 이보다 길면 문장 경계로 다시 자른다
