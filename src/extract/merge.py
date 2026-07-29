"""추출된 조건들을 하나로 합친다 — 중복 제거·대표 선정.

★ 여기에 LLM 은 없다. 순수 함수만 있다.
  같은 조건이 여러 문서에서 반복 등장하므로(해외거래정지는 6개 문서에 나온다)
  같은 조건인지 판단하고 하나로 합치는 규칙이 필요하다.
  그 규칙이 LLM 이면 실행할 때마다 트리가 달라진다. 그래서 규칙으로 고정한다.

같은 조건인가?  →  (subject, op, value) 가 같으면 같은 조건이다.
  값이 다르면(600만원 vs 2000만원) 다른 조건이다. 합치지 않는다.
"""
from __future__ import annotations

import json

from src.extract.agreement import (
    CONF_RANK,
    _norm_label,
    _rep_sorter,
    cluster_by_label,
)
from src.judge.schema import Condition, Evidence, Predicate, Provenance, Remedy

# 트리 안에서 조건을 보여줄 순서 — 사용자가 먼저 확인해야 할 것부터
CATEGORY_ORDER = {"setting": 0, "eligibility": 1, "document": 2, "limit": 3, "temporal": 4}

# ★ 병합의 원칙 — 화면에 보이는 모든 정보는 **하나의 인용**에서 나온다
#
#   처음에는 채널·해결경로를 문서들의 합집합으로 모았다. 그러다 실제 사고가 났다.
#   안심차단 해제 조건에, "앱에서 안심차단을 **신청**할 수 있어요" 청크의
#   `app:KB스타뱅킹` 이 섞여 들어가 "앱에서 해제 가능"으로 뒤집혔다.
#   신청과 해제는 채널이 다르다. 합치는 순간 그 구분이 사라진다.
#
#   그래서 label·predicate·severity·remedy·evidence 는 **전부 대표 하나에서** 가져온다.
#   다른 문서의 값이 다르면 합치지 않고 `검수 메모`로 남겨 사람에게 넘긴다.
#   합집합으로 얻는 정보량보다, 근거와 화면이 어긋나지 않는 것이 중요하다.


def dedup_key(cond: dict) -> tuple[str, str, str]:
    """같은 조건인지 판단하는 열쇠. value 는 JSON 정규화해 표기 차이를 흡수한다."""
    p = cond["predicate"]
    value = json.dumps(json.loads(p["value_json"]), sort_keys=True, ensure_ascii=False)
    return (p["subject"], p["op"], value)


def _remedy_of(cond: dict) -> Remedy:
    r = cond["remedy"]
    return Remedy(
        actionable_in_app=r["actionable_in_app"],
        channels=list(r.get("channels") or []),
        primary_path=r.get("primary_path"),
        note=r.get("note"),
    )


def _conflicts(group: list[dict], strays: list[dict], cid: str) -> list[str]:
    """대표와 다른 값을 말하는 문서를 검수 메모로 남긴다. 조용히 덮지 않는다."""
    rep = group[0]["condition"]
    notes: list[str] = []

    if strays:
        labels = sorted({i["condition"]["label"] for i in strays})
        notes.append(f"{cid}: 같은 predicate 인데 뜻이 다른 조건 {len(strays)}건이 함께 묶였다 "
                     f"→ 근거 수에서 제외했다. subject 추가가 필요한지 확인: {labels[:3]}")

    severities = {i["condition"]["severity"] for i in group}
    if len(severities) > 1:
        notes.append(f"{cid}: severity 가 문서마다 다름 {sorted(severities)} "
                     f"→ 대표값 '{rep['severity']}' 사용. 확인 필요")

    apps = {i["condition"]["remedy"]["actionable_in_app"] for i in group}
    if len(apps) > 1:
        others = [i["chunk"]["chunk_id"] for i in group[1:]
                  if i["condition"]["remedy"]["actionable_in_app"]
                  != rep["remedy"]["actionable_in_app"]]
        notes.append(f"{cid}: 앱 해결 가능 여부가 문서마다 다름 "
                     f"→ 대표값 {rep['remedy']['actionable_in_app']} 사용. 다른 문서: {others}")

    return notes


def _evidence(rep: dict, titles: dict[str, str]) -> Evidence:
    c, ch = rep["condition"], rep["chunk"]
    return Evidence(
        source_title=titles.get(ch["source_id"], ch["source_id"]),
        url=ch["url"],
        quote=c["evidence_quote"],
        collected_at=ch["fetched_at"][:10],
        confidence=c["confidence"],
        note=c.get("note"),
    )


def _provenance(group: list[dict]) -> Provenance:
    source_ids: list[str] = []
    for i in group:
        if i["chunk"]["source_id"] not in source_ids:
            source_ids.append(i["chunk"]["source_id"])
    return Provenance(
        support_count=len(group),
        chunk_ids=[i["chunk"]["chunk_id"] for i in group],
        source_ids=source_ids,
    )


def _to_condition(group: list[dict], titles: dict[str, str], cid: str) -> Condition:
    rep = group[0]["condition"]
    return Condition(
        id=cid,
        label=rep["label"],
        category=rep["category"],
        predicate=Predicate(
            subject=rep["predicate"]["subject"],
            op=rep["predicate"]["op"],
            value=json.loads(rep["predicate"]["value_json"]),
        ),
        severity=rep["severity"],
        remedy=_remedy_of(rep),
        evidence=_evidence(group[0], titles),
        provenance=_provenance(group),
    )


def _unique_id(base: str, used: set[str]) -> str:
    """LLM 이 서로 다른 조건에 같은 id 를 붙이는 경우가 있다. 뒤에 번호를 붙인다."""
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def merge(items: list[dict], titles: dict[str, str]) -> tuple[list[Condition], list[str]]:
    """추출 결과(청크별) → 조건 목록. 반환: (조건, 검토 필요 메모)"""
    groups: dict[tuple, list[dict]] = {}
    for item in items:
        groups.setdefault(dedup_key(item["condition"]), []).append(item)

    conditions: list[Condition] = []
    notes: list[str] = []
    used: set[str] = set()

    for key in sorted(groups):
        main, strays = cluster_by_label(groups[key])       # 문서 합의가 가장 큰 무리
        main = sorted(main, key=_rep_sorter(main))          # 그 안에서 보여줄 근거 선택
        cid = _unique_id(main[0]["condition"]["id"], used)
        used.add(cid)
        conditions.append(_to_condition(main, titles, cid))
        notes.extend(_conflicts(main, strays, cid))

    conditions.sort(key=lambda c: (CATEGORY_ORDER.get(c.category, 9), c.id))
    return conditions, notes
