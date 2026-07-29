"""같은 조건인지, 어느 근거를 보여줄지 — 문서 간 합의를 재는 규칙.

★ 여기에 LLM 은 없다. 같은 입력이면 같은 결과가 나온다.

왜 합의를 재는가
  같은 규칙이 문서 여러 곳에 조금씩 다른 문장으로 실린다. 그중 무엇을 대표로 삼을지
  길이나 순서로 정하면 엉뚱한 것이 뽑힌다 — 실제로 '해외거래정지가 해제되어 있어야 합니다'(문서 5곳)가
  '해외사이트에서 해제신청이 되어 있어야 합니다'(문서 1곳)에 밀려난 적이 있다.
  길이는 신뢰의 근거가 아니다. **여러 문서가 같은 뜻으로 읽었다는 사실**이 근거다.
"""
from __future__ import annotations

import re
from collections import Counter

CONF_RANK = {"high": 0, "medium": 1, "low": 2}

# label 이 같은 뜻인지 판정하는 문턱  [현찬 판단]
# 낮추면 뜻이 다른 조건이 뭉치고, 높이면 같은 조건이 갈라진다.
LABEL_SIMILARITY = 0.55


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _jaccard(a: str, b: str) -> float:
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y)


def _similar(a: str, b: str) -> bool:
    """두 label 이 같은 뜻인가. 글자 2-gram 자카드 유사도로 본다.

    같은 조건을 문서마다 조금씩 다르게 쓴다 —
      "카드와 여권 영문명이 일치해야 합니다" / "카드 영문명과 여권 영문명이 일치해야 합니다"
    글자 그대로 비교하면 남남이 되고, 아예 안 보면 뜻이 다른 것까지 뭉친다.
    """
    return _jaccard(a, b) >= LABEL_SIMILARITY


def _norm_quote(item: dict) -> str:
    return re.sub(r"\s", "", item["condition"]["evidence_quote"])


def _supports(item: dict) -> float:
    """이 항목의 인용이 자기 label 을 얼마나 뒷받침하는가 — label 이 인용에 담긴 비율.

    자카드(대칭)를 쓰면 **긴 인용이 손해를 본다.** label 을 온전히 담고 있어도
    나머지 문장이 길다는 이유로 점수가 낮아진다. 실제로 그것 때문에
    '해제해야 한다'고 말하는 긴 문장이, 해제를 언급조차 않는 짧은 문장에 밀렸다.
    근거는 짧아서 좋은 게 아니라 **주장을 담고 있어서** 좋은 것이므로 포함률로 본다.
    """
    c = item["condition"]
    label = _bigrams(_norm_label(c))
    quote = _bigrams(_norm_quote(item))
    return len(label & quote) / len(label)


def cluster_by_label(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """뜻이 같은 것끼리 묶고, **가장 큰 무리**를 대표 무리로 삼는다.

    ★ 이것이 대표 선정의 핵심이다.
      처음에는 인용 길이로 대표를 골랐다. 짧은 것을 고르니 규칙을 스치듯 언급한 문장이,
      긴 것을 고르니 다른 얘기를 하는 긴 문단이 대표가 됐다 —
      실제로 '해외거래정지가 해제되어 있어야 합니다'(문서 5곳)가
      '해외사이트에서 해제신청이 되어 있어야 합니다'(문서 1곳)에 밀려나는 사고가 났다.

      길이는 신뢰의 근거가 아니다. **여러 문서가 같은 뜻으로 읽었다는 사실**이 근거다.
      그래서 문서 간 합의가 가장 큰 무리를 대표로 삼는다.
      나머지는 버리지 않고 검수 메모로 넘겨 사람이 본다.
    """
    clusters: list[list[dict]] = []
    for item in sorted(items, key=lambda i: i["chunk"]["chunk_id"]):
        label = _norm_label(item["condition"])
        for c in clusters:
            if _similar(label, _norm_label(c[0]["condition"])):
                c.append(item)
                break
        else:
            clusters.append([item])

    clusters.sort(key=lambda c: (-len(c), c[0]["chunk"]["chunk_id"]))
    return clusters[0], [i for c in clusters[1:] for i in c]


def _rep_sorter(cluster: list[dict]):
    """대표 무리 안에서 **어느 인용을 화면에 보여줄지**  [현찬 판단]

    1) confidence 가 높은 것 — 해석이 덜 개입한 서술
    2) **여러 문서에 똑같이 실린 문장** — KB 문서는 같은 규칙을 여러 페이지에 같은 문장으로 싣는다.
       그 문장이 그 규칙의 정본이다. 한 페이지에만 있는 서술보다 믿을 만하다.
    3) label 을 잘 뒷받침하는 것 — 근거는 길이가 아니라 주장을 담고 있어서 좋은 것이다
    4) 같은 정도로 뒷받침한다면 **짧은 것** — 조건과 무관한 문장이 덜 섞인다
       (길이를 먼저 보던 시절의 사고는 3)에서 막는다. 여기서는 이미 뒷받침 정도가 같은 것들끼리다)
    5) chunk_id 사전순 — 동률이어도 결과가 흔들리지 않게 (결정론성)
    """
    counts = Counter(_norm_quote(i) for i in cluster)

    def key(item: dict) -> tuple:
        c = item["condition"]
        q = _norm_quote(item)
        return (CONF_RANK[c["confidence"]], -counts[q], -_supports(item),
                len(q), item["chunk"]["chunk_id"])

    return key


def _norm_label(cond: dict) -> str:
    return re.sub(r"[\s()·,.\-]", "", cond["label"])

