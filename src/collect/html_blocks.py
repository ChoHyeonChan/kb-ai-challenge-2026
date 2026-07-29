"""HTML → 블록(kind, text) 추출기.

표준 `html.parser` 만 쓴다 (bs4 미사용 — 외부 의존 최소화).

★ 표를 행 단위로 살리는 것이 핵심이다.
  KB 안내 페이지는 한도·조건이 표에 들어 있어, 표를 뭉개면 조건 자체가 사라진다.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "iframe", "select", "option"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "dd", "dt",
    "figcaption", "caption", "blockquote", "label", "strong",
} | HEADING_TAGS


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

