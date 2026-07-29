"""HTTP 계층. 판정 엔진과 데모 화면을 잇는다.

★ 여기에도 LLM 호출은 없다. 목표 식별(resolve/)이 붙기 전까지는
  goal_id 를 직접 받거나 aliases 로 단순 매칭한다.

실행:  uvicorn src.api.main:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import PROFILES_DIR, ROOT, TREES_DIR
from src.judge.engine import judge, load_profile, load_tree
from src.judge.schema import ConditionTree, Verdict

app = FastAPI(title="다 됐나요? — 실행 실패 원인 판정 엔진", version="0.1.0")

WEB_DIR = ROOT / "web"


# ── 로딩 ───────────────────────────────────────────────────────────
# 요청 시점에 읽는다. 기동 시 캐시하면 추출 파이프라인이 트리를 새로 만들어도
# 서버를 재시작하기 전까지 반영되지 않아, "파일이 곧 진실"이라는 전제가 깨진다.
# 트리는 수 KB·수 개 수준이라 매 요청 로드가 비용이 되지 않는다.

def load_all_trees() -> dict[str, ConditionTree]:
    trees: dict[str, ConditionTree] = {}
    for p in sorted(TREES_DIR.glob("*.json")):
        t = load_tree(p)
        trees[t.goal_id] = t
    return trees


# ── 요청 모델 ─────────────────────────────────────────────────────

class JudgeRequest(BaseModel):
    goal_id: str | None = None
    query: str | None = None          # 자연어. resolve/ 붙기 전엔 alias 단순 매칭
    profile_id: str
    context: dict | None = None


# ── 엔드포인트 ────────────────────────────────────────────────────

@app.get("/api/goals")
def list_goals() -> list[dict]:
    trees = load_all_trees()
    return [
        {
            "goal_id": t.goal_id,
            "goal_label": t.goal_label,
            "aliases": t.aliases,
            "condition_count": len(t.conditions),
            "collected_at": t.source_meta.collected_at,
        }
        for t in trees.values()
    ]


@app.get("/api/profiles")
def list_profiles() -> list[dict]:
    out = []
    for p in sorted(PROFILES_DIR.glob("*.json")):
        prof = load_profile(p)
        out.append({"profile_id": prof.profile_id, "description": prof.description})
    return out


def _resolve_goal(req: JudgeRequest) -> ConditionTree:
    trees = load_all_trees()
    if req.goal_id:
        if req.goal_id not in trees:
            raise HTTPException(404, f"알 수 없는 goal_id: {req.goal_id}")
        return trees[req.goal_id]

    if req.query:
        q = req.query.replace(" ", "")
        for t in trees.values():
            if any(a.replace(" ", "") in q or q in a.replace(" ", "") for a in t.aliases):
                return t
        raise HTTPException(404, f"질의에 해당하는 목표를 찾지 못함: {req.query}")

    raise HTTPException(400, "goal_id 또는 query 중 하나가 필요합니다")


@app.post("/api/judge", response_model=Verdict)
def judge_endpoint(req: JudgeRequest) -> Verdict:
    tree = _resolve_goal(req)

    profile_path = PROFILES_DIR / f"{req.profile_id}.json"
    if not profile_path.exists():
        raise HTTPException(404, f"알 수 없는 profile_id: {req.profile_id}")

    return judge(tree, load_profile(profile_path), req.context)


# ── 데모 화면 ─────────────────────────────────────────────────────

@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """브라우저 기본 요청. 파비콘이 없어 404 가 콘솔에 남는 것을 막는다."""
    return Response(status_code=204)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
