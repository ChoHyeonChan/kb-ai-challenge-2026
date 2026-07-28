"""공개 안내 문서 수집.

원칙 (AGENTS.md 절대규칙 4)
  - robots.txt 에서 자동 수집이 금지된 도메인은 받지 않는다 (sources.yaml 의 allowed=false)
  - 요청 간격을 둔다
  - 수집 일자를 함께 기록한다 (약관은 개정된다)

실행:  python -m src.collect.fetch
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

from src.config import RAW_DIR, SOURCES_FILE


@dataclass(frozen=True)
class FetchResult:
    target_id: str
    url: str
    status: int
    bytes_len: int
    saved_to: Path


def _load_sources() -> dict:
    with SOURCES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _allowed_hosts(sources: dict) -> set[str]:
    return {d["host"] for d in sources.get("domains", []) if d.get("allowed")}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fetch_one(target: dict, *, user_agent: str, timeout: int) -> FetchResult:
    """대상 1건을 받아 원문과 메타를 저장한다."""
    url = target["url"]
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()

    # 서버가 인코딩을 잘못 알려주는 경우가 있어 apparent_encoding 을 우선 신뢰
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding

    text = resp.text
    html_path = RAW_DIR / f"{target['id']}.html"
    html_path.write_text(text, encoding="utf-8")

    meta = {
        "id": target["id"],
        "goal": target.get("goal"),
        "title": target.get("title"),
        "url": url,
        "host": urlparse(url).netloc,
        "fetched_at": _now_iso(),
        "http_status": resp.status_code,
        "content_type": resp.headers.get("Content-Type", ""),
        "bytes": len(text.encode("utf-8")),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "collection_method": "auto",
    }
    (RAW_DIR / f"{target['id']}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return FetchResult(target["id"], url, resp.status_code, meta["bytes"], html_path)


def run() -> list[FetchResult]:
    sources = _load_sources()
    meta = sources.get("meta", {})
    user_agent = meta.get("user_agent", "KB-AI-Challenge-Research/0.1")
    delay = float(meta.get("crawl_delay_sec", 1.5))
    timeout = int(meta.get("timeout_sec", 20))

    allowed = _allowed_hosts(sources)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    results: list[FetchResult] = []
    for i, target in enumerate(sources.get("targets", [])):
        host = urlparse(target["url"]).netloc
        if host not in allowed:
            # robots.txt 판정이 allowed=false 인 호스트는 건너뛴다.
            print(f"[SKIP] {target['id']}  ({host} — robots.txt 자동수집 불가)")
            continue

        if i:
            time.sleep(delay)
        try:
            r = fetch_one(target, user_agent=user_agent, timeout=timeout)
            print(f"[OK]   {r.target_id}  {r.status}  {r.bytes_len:,}B")
            results.append(r)
        except requests.RequestException as e:
            print(f"[FAIL] {target['id']}  {e}")

    _write_manual_placeholders(sources)
    return results


def _write_manual_placeholders(sources: dict) -> None:
    """수동 확보 대상은 자리와 메타만 만들어 둔다. 본문은 사람이 채운다."""
    manual_dir = RAW_DIR / "manual"
    manual_dir.mkdir(parents=True, exist_ok=True)

    for item in sources.get("manual", []):
        meta_path = manual_dir / f"{item['id']}.meta.json"
        if meta_path.exists():
            continue
        meta = {**item, "collection_method": "manual", "recorded_at": _now_iso()}
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        txt_path = manual_dir / f"{item['id']}.txt"
        if not txt_path.exists():
            txt_path.write_text(
                f"# {item['title']}\n"
                f"# 출처: {item['url']}\n"
                f"# 확보 방법: {item['method']} ({item['captured_at']}, {item['captured_by']})\n"
                f"# 사유: {item['reason']}\n\n"
                f"(브라우저로 열람한 본문을 여기에 붙여넣는다)\n",
                encoding="utf-8",
            )
        print(f"[MANUAL] {item['id']}  자리 생성 — 본문은 사람이 채운다")


if __name__ == "__main__":
    ok = run()
    print(f"\n수집 완료: {len(ok)}건 → {RAW_DIR}")
