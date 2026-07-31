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
from src.judge.schema import ConditionTree, UserProfile, Verdict
from src.judge.simulate import Plan, simulate

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
    # 화면에서 사람이 직접 바꾼 상태값. {"card.dcc_block": false} 형태.
    # 규칙 엔진이 정말 값에 반응하는지 그 자리에서 확인시키기 위한 것이다.
    overrides: dict | None = None


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
        out.append({
            "profile_id": prof.profile_id,
            # 드롭다운은 폭이 좁다. 설명문을 넣으면 잘리므로 짧은 이름을 따로 둔다.
            "short": getattr(prof, "short", prof.profile_id),
            "description": prof.description,
            # 이 상태로 판정하는 것이 의미 있는 목표. 화면이 목록을 걸러내는 데 쓴다.
            # (엔진은 어떤 조합이든 받는다 — 걸러내는 것은 화면의 일이다)
            "goals": getattr(prof, "goals", []),
            "demo_default": bool(getattr(prof, "demo_default", False)),
        })
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


@app.get("/api/tree/{goal_id}", response_model=ConditionTree)
def get_tree(goal_id: str) -> ConditionTree:
    """조건 트리 원본 — 이 프로젝트의 핵심 산출물을 화면이 그대로 보여주기 위한 것.

    판정 결과만 보여주면 '조건 트리가 재사용 가능한 자산'이라는 주장을 확인할 방법이 없다.
    """
    trees = load_all_trees()
    if goal_id not in trees:
        raise HTTPException(404, f"알 수 없는 goal_id: {goal_id}")
    return trees[goal_id]


@app.get("/api/profile/{profile_id}", response_model=UserProfile)
def get_profile(profile_id: str) -> UserProfile:
    """사용자 상태 원본.

    이 시스템에서 **가짜는 사용자 상태 하나뿐**이라고 말해왔다.
    그렇다면 그 하나를 감추지 말고 화면에 펼쳐야 한다.
    조건(트리) · 상태(프로필) · 판정(결과)이 모두 보여야 손으로 검증할 수 있다.
    """
    return _resolve_profile(profile_id)


def _resolve_profile(profile_id: str) -> UserProfile:
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists():
        raise HTTPException(404, f"알 수 없는 profile_id: {profile_id}")
    return load_profile(path)


# 상태를 바꿀 수 있는 묶음. 프로필 스키마가 정한 세 곳뿐이다.
OVERRIDABLE_GROUPS = ("card", "account", "context")


def _apply_overrides(prof: UserProfile, overrides: dict | None) -> UserProfile:
    """화면에서 바꾼 상태값을 이 요청에만 덮어쓴다.

    파일은 건드리지 않는다. 요청이 끝나면 원래 프로필 그대로다.

    **이미 있는 키만** 바꿀 수 있다. 없는 키를 만들 수 있게 하면 조건 트리에
    없는 상태를 지어내는 셈이고, 그 값이 맞는지 아무도 보증할 수 없다.
    """
    if not overrides:
        return prof

    data = prof.model_dump()
    for path, value in overrides.items():
        group, _, key = str(path).partition(".")
        if group not in OVERRIDABLE_GROUPS or not key or "." in key:
            raise HTTPException(400, f"바꿀 수 없는 경로입니다: {path}")
        if key not in data.get(group, {}):
            raise HTTPException(400, f"이 프로필에 없는 상태값입니다: {path}")
        if value is not None and not isinstance(value, (bool, int, float, str)):
            raise HTTPException(400, f"상태값으로 쓸 수 없는 형태입니다: {path}")
        data[group][key] = value
    return UserProfile.model_validate(data)


def _profile_for(req: JudgeRequest) -> UserProfile:
    return _apply_overrides(_resolve_profile(req.profile_id), req.overrides)


@app.post("/api/judge", response_model=Verdict)
def judge_endpoint(req: JudgeRequest) -> Verdict:
    return judge(_resolve_goal(req), _profile_for(req), req.context)


@app.post("/api/simulate", response_model=Plan)
def simulate_endpoint(req: JudgeRequest) -> Plan:
    """'하나만 풀면 어떻게 되나' — 판정과 같은 입력으로 해결 계획을 계산한다.

    판정(C3)과 계약을 분리해 둔다. 화면이 계획을 안 쓰더라도 판정은 그대로 동작해야 하고,
    팀원이 작성하는 /api/judge 테스트도 영향을 받지 않아야 한다.
    """
    return simulate(judge(_resolve_goal(req), _profile_for(req), req.context))


# ── 진단 ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    """이 함수가 무엇을 볼 수 있는지 그대로 보고한다.

    배포 환경(서버리스)에서는 데이터 파일이 번들에 실리지 않아 조용히 빈 결과가
    나오는 일이 흔하다. 그때 '왜 안 되는지'를 추측하지 않고 바로 확인하기 위한 창구다.
    비밀값은 담지 않는다 — 경로와 개수만 본다.
    """
    return {
        "ok": TREES_DIR.exists() and PROFILES_DIR.exists() and (WEB_DIR / "index.html").exists(),
        "root": str(ROOT),
        "trees_dir": {"path": str(TREES_DIR), "exists": TREES_DIR.exists(),
                      "files": sorted(p.name for p in TREES_DIR.glob("*.json"))},
        "profiles_dir": {"path": str(PROFILES_DIR), "exists": PROFILES_DIR.exists(),
                         "count": len(list(PROFILES_DIR.glob("*.json")))},
        "web": {"path": str(WEB_DIR), "exists": WEB_DIR.exists(),
                "files": sorted(p.name for p in WEB_DIR.glob("*")) if WEB_DIR.exists() else []},
        "conditions": sum(len(t.conditions) for t in load_all_trees().values()),
    }


# ── 데모 화면 ─────────────────────────────────────────────────────

@app.get("/")
def index():
    """데모 화면. 파일이 없으면 크래시 대신 무엇이 없는지 알린다."""
    page = WEB_DIR / "index.html"
    if not page.exists():
        raise HTTPException(
            503,
            f"데모 화면 파일을 찾지 못했습니다: {page}. /api/health 로 배포 상태를 확인하세요.",
        )
    return FileResponse(page)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """브라우저 기본 요청. 파비콘이 없어 404 가 콘솔에 남는 것을 막는다."""
    return Response(status_code=204)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
