"""수집한 HTML을 조건 추출용 atomic snippet 으로 분할한다.

설계 근거
  - 조건 추출 정확도는 청크 단위에 크게 좌우된다 (Gao et al. 2024, RAG Survey)
  - 규범 텍스트는 atomic snippet 으로 쪼개는 편이 규칙 추출에 유리하다 (Horner et al. 2506.08899)
  - KB 안내 페이지는 **한도·조건이 표에 들어있다** → 표를 행 단위로 살려야 한다

외부 의존 없음 (bs4 미사용, 표준 html.parser).

실행:  python -m src.collect.chunk
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

from src.config import (
    CHUNKS_DIR,
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    CHUNK_MIN_CHARS_MANUAL,
    RAW_DIR,
)

SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "iframe", "select", "option"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "dd", "dt",
    "figcaption", "caption", "blockquote", "label", "strong",
} | HEADING_TAGS

# 메뉴·푸터 등 조건이 들어있지 않은 상투구 (수집 페이지 공통)
NOISE_PATTERNS = [
    r"^KB국민카드$", r"^로그인$", r"^전체메뉴$", r"^닫기$", r"^열기$", r"^이전$", r"^다음$",
    r"^TOP$", r"^more$", r"^더보기$", r"^바로가기$", r"^메뉴$", r"^검색$",
    r"개인정보처리방침", r"이메일무단수집거부", r"고객센터\s*\d", r"^Copyright", r"^ⓒ",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    goal: str | None
    url: str
    fetched_at: str
    kind: str          # heading | paragraph | list_item | table_row
    section: str       # 직전 heading (문맥 보존용)
    text: str


class _Extractor(HTMLParser):
    """블록 단위 텍스트 + 표를 행 단위로 뽑는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []   # (kind, text)
        self._skip_depth = 0
        self._buf: list[str] = []
        self._cur_kind = "paragraph"
        # 표 상태
        self._in_table = 0
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_cell = False

    # ── 내부 헬퍼 ──
    def _flush_block(self) -> None:
        text = _clean(" ".join(self._buf))
        if text:
            self.blocks.append((self._cur_kind, text))
        self._buf = []
        self._cur_kind = "paragraph"

    def _flush_row(self) -> None:
        cells = [_clean(c) for c in self._row]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            # "항목 | 값 | 값" 형태로 직렬화 — 조건이 표에 있는 경우가 많다
            #
            # ★ 이 `|` 는 우리가 넣은 기호다. 원문 HTML 에는 없다.
            #   표에서 뽑힌 조건은 근거 인용에도 이 형태로 남으므로,
            #   HTML 을 그대로 검색하면 그 인용 문자열은 나오지 않는다 (각 셀은 실재한다).
            #   README '데이터 출처와 한계' 에 이 사실을 명시해 두었다.
            self.blocks.append(("table_row", " | ".join(cells)))
        elif len(cells) == 1:
            self.blocks.append(("paragraph", cells[0]))
        self._row = []

    # ── HTMLParser 훅 ──
    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "table":
            self._flush_block()
            self._in_table += 1
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag in ("td", "th") and self._in_table:
            self._in_cell = True
            self._cell = []
        elif tag == "br":
            self._buf.append(" ")
        elif tag in BLOCK_TAGS:
            self._flush_block()
            if tag in HEADING_TAGS:
                self._cur_kind = "heading"
            elif tag == "li":
                self._cur_kind = "list_item"

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag == "table":
            self._in_table = max(0, self._in_table - 1)
        elif tag == "tr" and self._in_table:
            self._flush_row()
        elif tag in ("td", "th") and self._in_table:
            self._row.append(" ".join(self._cell))
            self._cell = []
            self._in_cell = False
        elif tag in BLOCK_TAGS:
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            return
        if self._in_cell:
            self._cell.append(data)
        else:
            self._buf.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush_block()


def _clean(s: str) -> str:
    s = s.replace("\xa0", " ").replace("​", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ·-|")


def _is_noise(text: str, min_chars: int = CHUNK_MIN_CHARS) -> bool:
    if len(text) < min_chars:
        return True
    if NOISE_RE.search(text):
        return True
    # 한글이 거의 없는 조각(스크립트 잔재·영문 메뉴)은 버린다
    hangul = len(re.findall(r"[가-힣]", text))
    return hangul < len(text) * 0.15


def _split_long(text: str) -> list[str]:
    """긴 조각은 문장 경계로 자른다."""
    if len(text) <= CHUNK_MAX_CHARS:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?。])\s+|(?<=니다)\s+|(?<=됩니다)\s+", text):
        if len(cur) + len(sent) + 1 > CHUNK_MAX_CHARS and cur:
            parts.append(cur.strip())
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _blocks_from_text(path: Path) -> list[tuple[str, str]]:
    """수동 확보한 평문(.txt) → 블록.

    robots.txt 가 자동 수집을 금지한 페이지는 사람이 브라우저로 열어 본문만 저장한다.
    HTML 태그가 없어 표·목록 구조를 알 수 없으므로 **줄 단위로만** 나눈다.
    문장부호나 종결어미로 끝나지 않는 짧은 줄은 소제목으로 본다 (원문 소제목의 형태).
    `#` 로 시작하는 줄은 우리가 붙인 확보 메타이므로 버린다.
    """
    blocks: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 글머리표로 시작하는 줄은 내용이다 — 소제목이 아니다.
        # (제거를 먼저 하면 이 신호가 사라져 "- 영업일/토요일 07:00~22:00" 이 소제목이 됐다)
        bullet = line.startswith(("-", "·", "*", "※"))
        line = line.lstrip("-·*").strip()

        if not bullet and len(line) <= 40 and not line.endswith((".", "다", "요")):
            # ★ 소제목으로 보이더라도 **버리지 않는다.**
            #   HTML 과 달리 평문에는 소제목을 구별할 표시가 없어 판정이 자주 틀린다.
            #   실제로 "영업점, KB스타뱅킹/인터넷뱅킹, KB스타기업뱅킹"(해제·신청 채널)이
            #   소제목으로 오인돼 통째로 사라졌다.
            #   그래서 문맥용 section 으로 쓰면서 **내용으로도 함께 남긴다.** 손실이 0이 된다.
            blocks.append(("heading", line))
        blocks.append(("paragraph", line))
    return blocks


def chunk_file(path: Path) -> list[Chunk]:
    meta_path = path.parent / f"{path.stem}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    if path.suffix == ".txt":
        blocks = _blocks_from_text(path)
    else:
        parser = _Extractor()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        blocks = parser.blocks

    chunks: list[Chunk] = []
    section = ""
    seen: set[str] = set()
    min_chars = CHUNK_MIN_CHARS_MANUAL if path.suffix == ".txt" else CHUNK_MIN_CHARS

    for kind, text in blocks:
        if kind == "heading":
            if not _is_noise(text, min_chars) or len(text) >= 4:
                section = text
            continue
        if _is_noise(text, min_chars):
            continue
        for piece in _split_long(text):
            if piece in seen:      # 페이지 내 반복 문구 제거
                continue
            seen.add(piece)
            chunks.append(
                Chunk(
                    chunk_id=f"{meta['id']}#{len(chunks):04d}",
                    source_id=meta["id"],
                    goal=meta.get("goal"),
                    url=meta["url"],
                    fetched_at=meta["fetched_at"],
                    kind=kind,
                    section=section,
                    text=piece,
                )
            )
    return chunks


def run() -> int:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CHUNKS_DIR / "chunks.jsonl"

    total = 0
    with out_path.open("w", encoding="utf-8") as f:
        # 자동 수집분(*.html) + 수동 확보분(manual/*.txt)
        sources = sorted(RAW_DIR.glob("*.html")) + sorted((RAW_DIR / "manual").glob("*.txt"))
        for path in sources:
            chunks = chunk_file(path)
            for c in chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
            print(f"[CHUNK] {path.stem:26s} {len(chunks):4d}개"
                  + (" (수동 확보)" if path.suffix == ".txt" else ""))
            total += len(chunks)

    print(f"\n총 {total}개 → {out_path}")
    return total


if __name__ == "__main__":
    run()
