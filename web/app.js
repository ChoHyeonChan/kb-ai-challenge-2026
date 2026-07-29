// 「다 됐나요?」 데모 화면 동작.
// 서버가 준 값만 그린다 — 화면에서 판정을 다시 계산하지 않는다.

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const VERDICT = {
  blocked:       {cls:"v-blocked",       kicker:"판정",      title:"지금은 되지 않습니다",   desc:"아래 조건이 충족되지 않았습니다."},
  ok:            {cls:"v-ok",            kicker:"판정",      title:"가능합니다",             desc:"확인한 조건을 모두 충족합니다."},
  indeterminate: {cls:"v-indeterminate", kicker:"판정 보류", title:"확인할 수 없습니다",     desc:"판정에 필요한 정보를 알 수 없어 된다고 말씀드릴 수 없습니다."},
};

function evidence(ev){
  if(!ev) return "";
  const conf = ev.confidence !== "high" ? ` · 신뢰도 ${esc(ev.confidence)}` : "";
  return `<details><summary>근거 원문</summary>
    <blockquote>${esc(ev.quote)}
      <cite>${esc(ev.source_title)} · ${esc(ev.collected_at)} 수집${conf}</cite>
    </blockquote></details>`;
}

function node(r, kind){
  const rem = r.remedy || {};
  let body = "";
  if(kind === "stop"){
    if(rem.primary_path) body += `<div class="meta">해결 <b>${esc(rem.primary_path)}</b></div>`;
    if(rem.actionable_in_app === false) body += `<div><span class="offapp">앱에서 해결 불가</span></div>`;
    body += evidence(r.evidence);
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
    <h3>하나만 풀면 되나요?</h3>
    <p class="lede">${esc(plan.summary)}</p>
    ${rows ? `<ul class="ladder">${rows}</ul>` : ""}
    ${visit}
    ${plan.final_note ? `<p class="order">${esc(plan.final_note)}</p>` : ""}
  </section>`;
}

function render(v, plan){
  const t = VERDICT[v.verdict] || VERDICT.indeterminate;
  const total = v.unmet.length + v.met.length + v.unknown.length;
  const lowById = new Map(v.low_confidence.map(r => [r.id, r]));

  let h = `<section class="verdict ${t.cls}">
      <div class="line">${t.kicker}</div>
      <h2>${t.title}</h2><p>${t.desc}</p>
      <div class="tally">
        <div class="n-stop"><b>${v.unmet.length}</b>미충족</div>
        <div><b>${v.met.length}</b>충족</div>
        ${v.unknown.length ? `<div><b>${v.unknown.length}</b>확인 불가</div>` : ""}
        <div><b>${total}</b>전체 조건</div>
      </div>
    </section>`;

  if(v.unmet.length || v.unknown.length){
    h += `<section class="rail"><h3>어디서 막혔나</h3>
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
    h += `<section class="met"><h3 class="eyebrow">충족한 조건</h3><ul>${rows}</ul></section>`;
  }

  h += `<p class="foot">판정 엔진 v${esc(v.engine_version)} · 조건 수집일 ${esc(v.tree_collected_at)}</p>`;
  $("#out").innerHTML = h;
}

async function judge(){
  const btn = $("#run");
  btn.disabled = true; btn.textContent = "판정 중…";
  try{
    const body = JSON.stringify({goal_id:$("#goal").value, profile_id:$("#profile").value});
    const opt = {method:"POST", headers:{"Content-Type":"application/json"}, body};
    const [res, planRes] = await Promise.all([
      fetch("/api/judge", opt),
      fetch("/api/simulate", opt),
    ]);
    if(!res.ok) throw new Error((await res.json()).detail || "판정에 실패했습니다");
    // 계획은 부가 정보다. 실패해도 판정은 보여준다.
    render(await res.json(), planRes.ok ? await planRes.json() : null);
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
    $("#profile").innerHTML = profiles.map(p =>
      `<option value="${esc(p.profile_id)}">${esc(p.description || p.profile_id)}</option>`).join("");
    // 데모는 빈 화면으로 두지 않는다. 첫 화면에 판정 결과가 이미 보이게 한다.
    // 어느 조합을 보여줄지는 프로필 데이터(demo_goal)가 정한다.
    const featured = profiles.find(p => p.demo_goal);
    if(featured){
      $("#goal").value = featured.demo_goal;
      $("#profile").value = featured.profile_id;
    }
    await judge();
  }catch{
    $("#out").innerHTML = `<div class="err">서버에 연결하지 못했습니다. <code>uvicorn src.api.main:app</code> 가 실행 중인지 확인해 주세요.</div>`;
  }
})();

$("#run").addEventListener("click", judge);
