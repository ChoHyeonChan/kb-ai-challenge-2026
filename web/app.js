// 「다 됐나요?」 데모 화면 동작.
// 서버가 준 값만 그린다 — 화면에서 판정을 다시 계산하지 않는다.

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// 검수 기록(decisions.yaml)은 사람이 읽으라고 쓴 문장이라 **강조**가 섞여 있다.
// 이스케이프한 **뒤에** 강조만 되살린다 — 태그가 아니라 별표만 해석하므로 안전하다.
const escEm = s => esc(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");

const VERDICT = {
  blocked:       {cls:"v-blocked",       kicker:"판정",      title:"지금은 되지 않습니다",   desc:"아래 조건이 충족되지 않았습니다."},
  ok:            {cls:"v-ok",            kicker:"판정",      title:"가능합니다",             desc:"확인한 조건을 모두 충족합니다."},
  indeterminate: {cls:"v-indeterminate", kicker:"판정 보류", title:"확인할 수 없습니다",     desc:"판정에 필요한 정보를 알 수 없어 된다고 말씀드릴 수 없습니다."},
};

function evidence(ev, prov){
  if(!ev) return "";
  const conf = ev.confidence !== "high" ? ` · 신뢰도 ${esc(ev.confidence)}` : "";
  // 같은 조건이 여러 문서에서 확인됐다는 사실 자체가 신뢰의 근거다. 요약줄에 드러낸다.
  const n = prov && prov.support_count > 1 ? `<b>문서 ${prov.support_count}곳</b>에서 확인` : "";
  const link = ev.url
    ? `<a class="src" href="${esc(ev.url)}" target="_blank" rel="noopener">원문 열기 ↗</a>` : "";
  return `<details><summary>근거 원문 ${n}</summary>
    <blockquote>${esc(ev.quote)}
      <cite>${esc(ev.source_title)} · ${esc(ev.collected_at)} 수집${conf} ${link}</cite>
    </blockquote></details>`;
}

function node(r, kind){
  const rem = r.remedy || {};
  let body = "";
  if(kind === "stop"){
    if(rem.primary_path) body += `<div class="meta">해결 <b>${esc(rem.primary_path)}</b></div>`;
    if(rem.actionable_in_app === false) body += `<div><span class="offapp">앱에서 해결 불가</span></div>`;
    body += evidence(r.evidence, r.provenance);
  }else if(kind === "hold" && r.reason){
    body += `<div class="meta">${esc(r.reason)}</div>`;
  }
  return `<div class="node ${kind}"><div class="label">${esc(r.label)}</div>${body}</div>`;
}

// 해결 계획 — "하나만 풀면 어떻게 되나".
// 서버(judge/simulate.py)가 계산한 문장을 그대로 쓴다. 화면에서 다시 판단하지 않는다.
function planSection(plan){
  if(!plan || !plan.must_fix.length) return "";

  // 필수 조건이 하나뿐이면 사다리가 요약문과 같은 말을 반복한다. 요약만 보여준다.
  const rows = plan.what_ifs.length < 2 ? "" : plan.what_ifs.map(w => {
    const last = w.outcome === "ok";
    return `<li class="${last ? "reach" : "short"}">
      <span class="scope">${esc(w.scope)}</span>
      <span class="result">${esc(w.result)}</span>
    </li>`;
  }).join("");

  const visit = plan.needs_visit_ids.length
    ? `<p class="order"><b>${plan.needs_visit_ids.length}개는 앱에서 할 수 없습니다.</b>
       창구 방문이 전체 소요를 결정하므로 먼저 시작하는 편이 빠릅니다.</p>` : "";

  return `<section class="plan">
    <h3><span class="eyebrow">계획</span>하나만 풀면 되나요?</h3>
    <p class="lede">${esc(plan.summary)}</p>
    ${rows ? `<ul class="ladder">${rows}</ul>` : ""}
    ${visit}
    ${plan.final_note ? `<p class="order">${esc(plan.final_note)}</p>` : ""}
  </section>`;
}

// ── 대조한 사용자 상태 ─────────────────────────────────────────
// 이 시스템에서 가짜는 사용자 상태 하나뿐이다. 그렇다면 감추지 말고 펼친다.
// 조건 · 상태 · 판정이 모두 보여야 심사자가 손으로 검증할 수 있다.

function stateRows(prof){
  const rows = [];
  ["card", "account", "context"].forEach(group => {
    Object.entries(prof[group] || {}).forEach(([k, v]) => {
      const unknown = v === null || v === undefined;
      const val = unknown ? "모름"
        : typeof v === "boolean" ? (v ? "예" : "아니오")
        : typeof v === "number" ? v.toLocaleString("ko-KR") : String(v);
      rows.push(`<tr class="${unknown ? "u" : ""}">
        <td><code>${esc(group)}.${esc(k)}</code></td><td>${esc(val)}</td></tr>`);
    });
  });
  return rows.join("");
}

function stateSection(prof){
  if(!prof) return "";
  const all = ["card", "account", "context"]
    .flatMap(g => Object.values(prof[g] || {}));
  const unknown = all.filter(v => v === null || v === undefined).length;
  return `<section class="state">
    <h3><span class="eyebrow">입력</span>대조한 사용자 상태</h3>
    <p class="lede">${esc(prof.description)}</p>
    <details><summary>상태값 ${all.length}개 보기${unknown ? ` · 모름 ${unknown}개` : ""}</summary>
      <table class="st"><tbody>${stateRows(prof)}</tbody></table>
      <p class="foot">이 시스템에서 <b>가짜는 이 상태 하나뿐</b>입니다.
        조건과 근거는 전부 KB 공개문서에서 나옵니다.
        실제 서비스에서는 이 값을 은행 내부 API로 조회합니다.</p>
    </details>
  </section>`;
}

// ── 조건 트리 원본 보기 ────────────────────────────────────────
// 우리는 "핵심 산출물은 서비스가 아니라 조건 트리"라고 말한다.
// 판정 결과만 보여주면 그 말을 확인할 방법이 없다. 트리를 그대로 펼쳐 둔다.

const CAT = {
  setting: "설정 상태", document: "실물·서류", limit: "금액·횟수 한도",
  temporal: "날짜·기간", eligibility: "자격 요건",
};
const OPTEXT = {
  eq: "=", neq: "≠", gte: "≥", lte: "≤", gt: ">", lt: "<",
  in: "∈", not_in: "∉", exists: "존재", not_exists: "없음",
  // 연산자는 기호로 — "card.expiry_date 이후 오늘" 처럼 어순이 깨지지 않게 한다
  date_after: ">", date_before: "<",
  within_days: "≤", not_within_days: ">",
  count_lte: "횟수 ≤", count_gte: "횟수 ≥",
};

function predText(p){
  const op = OPTEXT[p.op] || p.op;
  let v = p.value;
  if(v && typeof v === "object"){
    if("now_plus_days" in v) v = v.now_plus_days === 0 ? "오늘" : `오늘+${v.now_plus_days}일`;
    else if("days" in v) v = `${v.days}일`;
    else v = JSON.stringify(v);
  }else if(Array.isArray(v)) v = v.join(", ");
  else if(typeof v === "number") v = v.toLocaleString("ko-KR");
  else v = String(v);
  return `${p.subject} ${op} ${v}`;
}

function treeItem(c){
  const app = c.remedy.actionable_in_app
    ? `<span class="chip">앱에서 가능</span>`
    : `<span class="chip off">앱에서 불가</span>`;
  const sev = c.severity === "blocking"
    ? `<span class="chip stop">차단</span>` : `<span class="chip warn">주의</span>`;
  const sup = (c.provenance && c.provenance.support_count) || 1;
  return `<li>
    <div class="t-label">${esc(c.label)}</div>
    <div class="t-pred"><code>${esc(predText(c.predicate))}</code></div>
    <div class="t-meta">${sev}${app}<span class="chip q">근거 ${sup}곳</span></div>
    <details><summary>근거 원문</summary>
      <blockquote>${esc(c.evidence.quote)}
        <cite>${esc(c.evidence.source_title)} · ${esc(c.evidence.collected_at)} 수집
          <a class="src" href="${esc(c.evidence.url)}" target="_blank" rel="noopener">원문 열기 ↗</a>
        </cite></blockquote>
      ${c.review_override ? `<p class="ovr">검수 기록 — ${escEm(c.review_override)}</p>` : ""}
    </details>
  </li>`;
}

function treeSection(tree){
  if(!tree) return "";
  const byCat = {};
  tree.conditions.forEach(c => (byCat[c.category] = byCat[c.category] || []).push(c));
  const groups = Object.keys(CAT).filter(k => byCat[k]).map(k =>
    `<h4>${CAT[k]} <em>${byCat[k].length}</em></h4>
     <ul class="tree">${byCat[k].map(treeItem).join("")}</ul>`).join("");

  const appOff = tree.conditions.filter(c => !c.remedy.actionable_in_app).length;
  return `<section class="asset">
    <h3><span class="eyebrow">근거 자료</span>이 목표의 조건 전체</h3>
    <p class="lede">판정에 쓰인 조건을 그대로 펼칩니다.
      <b>사람이 쓴 문장이 아니라 KB 공개문서에서 자동 추출한 것</b>이며,
      각 조건은 기계가 평가하는 형태(<code>subject op value</code>)를 함께 가집니다.</p>
    <div class="t-stat">
      <div><b>${tree.conditions.length}</b>조건</div>
      <div><b>${appOff}</b>앱에서 불가</div>
      <div><b>${tree.source_meta.source_count}</b>근거 문서</div>
      <div><b>${esc(tree.source_meta.collected_at)}</b>수집</div>
    </div>
    <details class="t-open"><summary>조건 ${tree.conditions.length}개 펼쳐 보기</summary>
      ${groups}
      <p class="foot">추출기 <code>${esc(tree.source_meta.extractor_version)}</code> ·
        원본 <code>data/trees/${esc(tree.goal_id)}.json</code></p>
    </details>
  </section>`;
}

function render(v, plan, tree, prof){
  const t = VERDICT[v.verdict] || VERDICT.indeterminate;
  const total = v.unmet.length + v.met.length + v.unknown.length;
  const lowById = new Map(v.low_confidence.map(r => [r.id, r]));

  // 판정은 이 서비스의 결론이다. 문서 위에 찍힌 도장처럼 한 덩어리로 세운다.
  let h = `<section class="verdict ${t.cls}">
      <div class="v-head">
        <span class="v-kicker">${t.kicker}</span>
        <span class="v-goal">${esc(v.goal_label)}</span>
      </div>
      <h2>${t.title}</h2>
      <p>${t.desc}</p>
      <div class="tally">
        <div class="n-stop"><b>${v.unmet.length}</b><span>미충족</span></div>
        <div><b>${v.met.length}</b><span>충족</span></div>
        ${v.unknown.length ? `<div class="n-hold"><b>${v.unknown.length}</b><span>확인 불가</span></div>` : ""}
        <div class="n-all"><b>${total}</b><span>전체 조건</span></div>
      </div>
    </section>`;

  if(v.unmet.length || v.unknown.length){
    h += `<section class="rail"><h3><span class="eyebrow">원인</span>어디서 막혔나</h3>
      ${v.unmet.map(r => node(r, "stop")).join("")}
      ${v.unknown.map(r => node(r, "hold")).join("")}</section>`;
  }

  h += planSection(plan);

  if(v.met.length){
    // 해석이 개입한 조건은 별도 섹션으로 빼지 않고 충족 목록 안에서 `~` 로 표시한다.
    const rows = v.met.map(r => {
      const low = lowById.get(r.id);
      return low
        ? `<li class="interp">${esc(r.label)}<em>${esc(low.reason || "근거 해석이 개입함")}</em></li>`
        : `<li>${esc(r.label)}</li>`;
    }).join("");
    h += `<section class="met"><h3><span class="eyebrow">확인됨</span>충족한 조건</h3><ul>${rows}</ul></section>`;
  }

  h += stateSection(prof);
  h += treeSection(tree);

  h += `<p class="foot">판정 엔진 v${esc(v.engine_version)} · 조건 수집일 ${esc(v.tree_collected_at)}</p>`;
  $("#out").innerHTML = h;
}

async function judge(){
  const btn = $("#run");
  btn.disabled = true; btn.textContent = "판정 중…";
  try{
    const body = JSON.stringify({goal_id:$("#goal").value, profile_id:$("#profile").value});
    const opt = {method:"POST", headers:{"Content-Type":"application/json"}, body};
    const [res, planRes, treeRes, profRes] = await Promise.all([
      fetch("/api/judge", opt),
      fetch("/api/simulate", opt),
      fetch(`/api/tree/${encodeURIComponent($("#goal").value)}`),
      fetch(`/api/profile/${encodeURIComponent($("#profile").value)}`),
    ]);
    if(!res.ok) throw new Error((await res.json()).detail || "판정에 실패했습니다");
    // 계획·트리는 부가 정보다. 실패해도 판정은 보여준다.
    render(await res.json(),
           planRes.ok ? await planRes.json() : null,
           treeRes.ok ? await treeRes.json() : null,
           profRes.ok ? await profRes.json() : null);
  }catch(e){
    $("#out").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }finally{
    btn.disabled = false; btn.textContent = "판정하기";
  }
}

(async function init(){
  try{
    const [goals, profiles] = await Promise.all([
      fetch("/api/goals").then(r => r.json()),
      fetch("/api/profiles").then(r => r.json()),
    ]);
    $("#goal").innerHTML = goals.map(g =>
      `<option value="${esc(g.goal_id)}">${esc(g.goal_label)} — 조건 ${g.condition_count}개</option>`).join("");

    // 목표에 맞는 상태만 보여준다. 계좌개설 목표에 해외결제용 상태를 고르면
    // 관련 정보가 없어 indeterminate 가 나오는데, 데모에서는 혼란만 준다.
    // (엔진은 어떤 조합이든 받는다 — 걸러내는 것은 화면의 일이다)
    function fillProfiles(goalId, keep){
      const list = profiles.filter(p => !p.goals.length || p.goals.includes(goalId));
      $("#profile").innerHTML = list.map(p =>
        `<option value="${esc(p.profile_id)}">${esc(p.short || p.profile_id)}</option>`).join("");
      if(keep && list.some(p => p.profile_id === keep)) $("#profile").value = keep;
    }

    // 데모는 빈 화면으로 두지 않는다. 첫 화면에 판정 결과가 이미 보이게 한다.
    // 어느 조합을 보여줄지는 프로필 데이터가 정한다.
    const featured = profiles.find(p => p.demo_default) || profiles[0];
    $("#goal").value = featured.goals[0] || goals[0].goal_id;
    fillProfiles($("#goal").value, featured.profile_id);

    // 목표를 바꾸면 상태 목록도 함께 바뀐다
    $("#goal").addEventListener("change", () => {
      fillProfiles($("#goal").value);
      judge();
    });
    $("#profile").addEventListener("change", judge);

    await judge();
  }catch{
    $("#out").innerHTML = `<div class="err">서버에 연결하지 못했습니다. <code>uvicorn src.api.main:app</code> 가 실행 중인지 확인해 주세요.</div>`;
  }
})();

$("#run").addEventListener("click", judge);
