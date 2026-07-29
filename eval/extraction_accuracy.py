"""조건 추출 정확도 — 수동 라벨 대비 정밀도·재현율.

측정 대상: **자동 추출한 트리**(`data/trees/`) vs **사람이 문서를 읽고 만든 라벨**(`eval/labels/`).

라벨의 정직한 성격
  라벨은 자동 추출을 돌리기 **전에** 같은 원문을 사람이 읽고 손으로 만든 조건 목록이다
  (커밋 `0a5beec`, extractor_version="seed-manual-0.1"). 자동 결과를 보고 만든 것이 아니다.
  즉 이 수치는 "사람이 손으로 뽑은 것을 기계가 얼마나 재현했는가"다.

일치 판정 기준
  (subject, op, value) 가 같으면 같은 조건으로 본다 — 판정 엔진이 실제로 쓰는 값 그대로다.
  label 문구가 달라도 기계가 같은 판정을 하면 같은 조건이다.

주의
  라벨에 없는데 자동이 찾아낸 조건이 곧 오답인 것은 아니다. 사람이 놓친 것일 수 있다.
  그래서 이 스크립트는 점수만 내고, **자동에만 있는 조건을 전부 나열한다.**
  유효/무효 판단은 사람이 하고 `eval/results/extraction_accuracy.md` 에 기록한다.

실행:  python -m eval.extraction_accuracy
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.config import EVAL_DIR, TREES_DIR
from src.extract.review import load_decisions

LABELS_DIR = Path(__file__).resolve().parent / "labels"
ERRATA_FILE = LABELS_DIR / "errata.yaml"


def _key(cond: dict) -> tuple[str, str, str]:
    p = cond["predicate"]
    return (p["subject"], p["op"], json.dumps(p.get("value"), sort_keys=True, ensure_ascii=False))


def _load(path: Path) -> dict[tuple, dict]:
    tree = json.loads(path.read_text(encoding="utf-8"))
    return {_key(c): c for c in tree["conditions"]}


def compare(goal_id: str) -> dict:
    auto = _load(TREES_DIR / f"{goal_id}.json")
    gold = _load(LABELS_DIR / f"{goal_id}.manual.json")

    hit = sorted(set(auto) & set(gold))
    only_auto = sorted(set(auto) - set(gold))
    only_gold = sorted(set(gold) - set(auto))

    return {
        "goal_id": goal_id,
        "auto_count": len(auto),
        "gold_count": len(gold),
        "hit": [auto[k] for k in hit],
        "only_auto": [auto[k] for k in only_auto],
        "only_gold": [gold[k] for k in only_gold],
        "precision": len(hit) / len(auto) if auto else 0.0,
        "recall": len(hit) / len(gold) if gold else 0.0,
    }


def _fmt(cond: dict) -> str:
    p = cond["predicate"]
    sup = (cond.get("provenance") or {}).get("support_count", "-")
    return (f"  · {cond['label']}\n"
            f"      {p['subject']} {p['op']} {json.dumps(p.get('value'), ensure_ascii=False)}"
            f"  | {cond['evidence']['confidence']} | 근거 {sup}곳\n"
            f"      \"{cond['evidence']['quote'][:70]}\"")


def _block(conds: list[dict]) -> list[str]:
    return [_fmt(c) for c in conds] or ["  (없음)"]


def load_errata() -> dict[str, dict]:
    """수동 라벨의 알려진 결함. 라벨 파일은 고치지 않고 여기에만 기록한다."""
    if not ERRATA_FILE.exists():
        return {}
    cfg = yaml.safe_load(ERRATA_FILE.read_text(encoding="utf-8")) or {}
    return {f"{e['goal_id']}|{e['key']}": e for e in (cfg.get("errata") or [])}


def _errata_block(goal_id: str, only_gold: list[dict], errata: dict) -> list[str]:
    """자동이 놓친 것 중 '사실은 라벨이 틀린 것'을 구분해 보여준다."""
    lines: list[str] = []
    for c in only_gold:
        e = errata.get(f"{goal_id}|{_key_str(c)}")
        if not e:
            continue
        lines += [f"- **{c['label']}** → 판정: **{e['verdict']}**",
                  f"  - {' '.join(e['finding'].split())}",
                  f"  - 교훈: {' '.join(e['lesson'].split())}"]
    return ["### ⚠ 위 '자동이 놓친 것' 중 라벨 자체가 틀린 항목", "", *lines, ""] if lines else []


def _key_str(cond: dict) -> str:
    return "|".join(_key(cond))


def _review_summary() -> list[str]:
    """검수 결과 요약. 라벨 대비 정밀도만으로는 성능을 오해하기 쉬워 함께 싣는다."""
    decisions = load_decisions().values()
    approved = [d for d in decisions if d.get("decision") == "approve"]
    rejected = [d for d in decisions if d.get("decision") != "approve"]
    sev = [d for d in approved if "severity" in (d.get("override") or {})]
    ev = [d for d in approved if "evidence_from" in (d.get("override") or {})]

    lines = ["## 검수 결과 (data/review/decisions.yaml)", "",
             "| 항목 | 수 |", "|---|---|",
             f"| 병합된 조건 | {len(decisions)} |",
             f"| **승인** (트리에 들어감) | **{len(approved)}** |",
             f"| 반려 | {len(rejected)} |",
             f"| severity 교정 후 승인 | {len(sev)} |",
             f"| 대표 인용을 사람이 지정 | {len(ev)} |",
             f"| **검수 통과율** | **{len(approved) / len(decisions):.2f}** |", "",
             "### 반려 사유", ""]
    for d in rejected:
        lines.append(f"- `{d['key']}`  \n  {' '.join(d.get('reason', '').split())[:180]}")
    return lines + [""]


def report(goal_ids: list[str]) -> str:
    lines = ["# 조건 추출 정확도", "",
             "자동 추출 트리 vs 수동 라벨. 일치 기준 = (subject, op, value).", "",
             "> **정밀도를 읽는 법.** 라벨은 사람이 같은 문서를 읽고 손으로 만든 것이라 **완전하지 않다.**",
             "> 자동 추출이 라벨에 없는 조건을 찾아내면 여기서는 오답으로 계산되지만,",
             "> 실제로는 사람이 놓친 것일 수 있다. 그래서 아래 '자동에만 있는 조건'을 반드시 함께 읽는다.",
             "> 트리에 실제로 들어간 것은 **검수를 통과한 조건뿐이다.**", "",
             *_review_summary()]

    errata = load_errata()
    for gid in goal_ids:
        r = compare(gid)
        lines += [
            f"## {gid}", "",
            f"| 지표 | 값 |", "|---|---|",
            f"| 수동 라벨 조건 수 | {r['gold_count']} |",
            f"| 자동 추출 조건 수 | {r['auto_count']} |",
            f"| 일치 | {len(r['hit'])} |",
            f"| **정밀도** (일치/자동) | **{r['precision']:.2f}** |",
            f"| **재현율** (일치/수동) | **{r['recall']:.2f}** |", "",
            f"### 일치한 조건 {len(r['hit'])}개", "```",
            *_block(r["hit"]), "```", "",
            f"### 자동에만 있는 조건 {len(r['only_auto'])}개 — 검수를 통과한 것들이다 (수동 라벨이 놓친 조건)", "```",
            *_block(r["only_auto"]), "```", "",
            f"### 수동 라벨에만 있는 조건 {len(r['only_gold'])}개 — 자동이 놓친 것", "```",
            *_block(r["only_gold"]), "```", "",
            *_errata_block(gid, r["only_gold"], errata),
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    goals = sorted(p.stem.replace(".manual", "") for p in LABELS_DIR.glob("*.manual.json"))
    text = report(goals)
    print(text)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = EVAL_DIR / "extraction_accuracy.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\n→ {out}")
