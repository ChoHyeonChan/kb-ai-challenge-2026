// 「다 됐나요?」 데모 화면 동작.
// 서버가 준 값만 그린다 — 화면에서 판정을 다시 계산하지 않는다.

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// 검수 기록(decisions.yaml)은 사람이 읽으라고 쓴 문장이라 **강조**가 섞여 있다.
// 이스케이프한 **뒤에** 강조만 되살린다 — 태그가 아니라 별표만 해석하므로 안전하다.
const escEm = s => esc(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");

// 조건 트리 11개를 처음부터 펼치면 페이지가 4.1화면이 된다(실측).
// 대신 접힘 밖에서 규모(조건 수·근거 문서 수·수집일)를 보이고,
// 근거 원문은 '어디서 막혔나'의 첫 건을 펼쳐 둔다 — 클릭하지 않아도 증거는 보인다.

const VERDICT = {
  blocked:       {cls:"v-blocked",       kicker:"판정",      title:"지금은 되지 않습니다",   desc:"아래 조건이 충족되지 않았습니다."},
  ok:            {cls:"v-ok",            kicker:"판정",      title:"가능합니다",             desc:"확인한 조건을 모두 충족합니다."},
  indeterminate: {cls:"v-indeterminate", kicker:"판정 보류", title:"확인할 수 없습니다",     desc:"판정에 필요한 정보를 알 수 없어 된다고 말씀드릴 수 없습니다."},
};

function evidence(ev, prov, open){
  if(!ev) return "";
  const conf = ev.confidence !== "high" ? ` · 신뢰도 ${esc(ev.confidence)}` : "";
  // 같은 조건이 여러 문서에서 확인됐다는 사실 자체가 신뢰의 근거다. 요약줄에 드러낸다.
  const n = prov && prov.support_count > 1 ? `<b>문서 ${prov.support_count}곳</b>에서 확인` : "";
  const link = ev.url
    ? `<a class="src" href="${esc(ev.url)}" target="_blank" rel="noopener">원문 열기 ↗</a>` : "";
  return `<details${open ? " open" : ""}><summary>근거 원문 ${n}</summary>
    <blockquote>${esc(ev.quote)}
      <cite>${esc(ev.source_title)} · ${esc(ev.collected_at)} 수집${conf} ${link}</cite>
    </blockquote></details>`;
}

function node(r, kind, open){
  const rem = r.remedy || {};
  let body = "";
  if(kind === "stop"){
    if(rem.primary_path) body += `<div class="meta">해결 <b>${esc(rem.primary_path)}</b></div>`;
    if(rem.actionable_in_app === false) body += `<div><span class="offapp">앱에서 해결 불가</span></div>`;
    body += evidence(r.evidence, r.provenance, open);
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
  //
  // 조건이 전부 AND 로 묶이면 "어느 하나만 풀어도 안 된다"가 전부 같은 문장이 된다.
  // 실제로 5줄 중 3줄이 글자까지 같았다 — 정보는 늘지 않고 높이만 먹는다.
  // 서버 출력은 그대로 두고(검증 가능해야 하므로), 화면에서 같은 결과끼리 묶어 보여준다.
  const groups = [];
  plan.what_ifs.forEach(w => {
    const prev = groups[groups.length - 1];
    if(prev && prev.result === w.result && prev.outcome === w.outcome) prev.scopes.push(w.scope);
    else groups.push({result: w.result, outcome: w.outcome, scopes: [w.scope]});
  });

  const rows = plan.what_ifs.length < 2 ? "" : groups.map(g => {
    const scope = g.scopes.length === 1
      ? g.scopes[0]
      : `${g.scopes.length}개 중 어느 하나만 해결`;
    return `<li class="${g.outcome === "ok" ? "reach" : "short"}">
      <span class="scope">${esc(scope)}</span>
      <span class="result">${esc(g.result)}</span>
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
    <details class="t-open"><summary>조건 ${tree.conditions.length}개를 근거 원문과 함께 펼쳐 보기</summary>
      ${groups}
      <p class="foot">추출기 <code>${esc(tree.source_meta.extractor_version)}</code> ·
        원본 <code>data/trees/${esc(tree.goal_id)}.json</code></p>
    </details>
  </section>`;
}

// ── 판정 — 왼쪽에 붙박이는 결론 ────────────────────────────────
// 이 수치의 출처는 eval/results/determinism_interim.md (10조합 × 200회).
// 화면에서 다시 재지 않는다. 잰 값을 인용할 뿐이다.
const DETERMINISM_RUNS = 2000;

function trustStrip(v){
  // 무엇이 이 판정을 만들었는가. 결론과 같은 덩어리 안에 둔다.
  // 페이지 맨 밑 12px 각주로 보내면 아무도 읽지 않는다 — 실제로 그랬다.
  return `<div class="trust">
    <span>규칙 엔진 <b>v${esc(v.engine_version)}</b></span><i>·</i>
    <span>실행 시점 LLM <b>0회</b></span><i>·</i>
    <span>동일 입력 <b>${DETERMINISM_RUNS.toLocaleString("ko-KR")}회</b> 반복 <b>100%</b> 일치</span>
  </div>`;
}

function verdictSection(v){
  const t = VERDICT[v.verdict] || VERDICT.indeterminate;
  const total = v.unmet.length + v.met.length + v.unknown.length;
  return `<section class="verdict ${t.cls}">
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
    ${trustStrip(v)}
  </section>`;
}

function railSection(v, tree){
  if(!v.unmet.length && !v.unknown.length) return "";

  // 문제 정의를 끝내는 한 줄. "조건이 많다"가 아니라 "앱 안에서 끝낼 수 없다"가
  // 우리가 문서에서 찾아낸 것이고, 이 서비스가 필요한 이유다.
  let impact = "";
  if(tree){
    const all = tree.conditions.length;
    const off = tree.conditions.filter(c => !c.remedy.actionable_in_app).length;
    // "1개 중 1개" 같은 말이 되지 않게, 조건 수에 따라 문장을 고른다.
    const text =
      off === 0 ? "" :
      off < all ? `이 목표의 조건 <b>${all}개</b> 중 <b>${off}개</b>는 앱 안에서 고칠 수 없습니다.` :
      all === 1 ? `이 조건은 <b>앱 안에서 고칠 수 없습니다.</b>` :
                  `이 목표의 조건 <b>${all}개 전부</b> 앱 안에서 고칠 수 없습니다.`;
    if(text) impact = `<p class="impact">${text}</p>`;
  }

  // 근거는 접어두면 없는 것과 같다. 첫 건은 펼쳐 둔다 —
  // 클릭하지 않는 사람에게도 "출처 있는 판정"이 즉시 보여야 한다.
  const stops = v.unmet.map((r, i) => node(r, "stop", i === 0)).join("");
  return `<section class="rail"><h3><span class="eyebrow">원인</span>어디서 막혔나</h3>
    ${impact}${stops}${v.unknown.map(r => node(r, "hold")).join("")}</section>`;
}

// ── 직접 바꿔 보기 ─────────────────────────────────────────────
// "프로필마다 답을 박아둔 것 아니냐"는 의심에 대한 답은 말이 아니라 조작이다.
// 값을 바꾸면 판정이 그 자리에서 다시 계산된다. 규칙 엔진이라 그럴 수 있다.
//
// overrides 는 이 브라우저 세션에만 있다. 서버는 요청 한 건에만 적용하고
// 프로필 파일은 건드리지 않는다.
let overrides = {};

function currentValue(subject, prof){
  if(subject in overrides) return overrides[subject];
  const [g, k] = subject.split(".");
  return (prof && prof[g]) ? prof[g][k] : undefined;
}

function tweakSection(tree, prof, v){
  if(!tree || !prof) return "";

  // 참/거짓 조건만 다룬다. 금액·날짜는 세 버튼으로 표현할 수 없다.
  const rows = tree.conditions.filter(c => {
    const [g, k] = c.predicate.subject.split(".");
    if(!prof[g] || !(k in prof[g])) return false;      // 이 프로필에 없는 값은 못 바꾼다
    const cur = currentValue(c.predicate.subject, prof);
    return typeof cur === "boolean" || cur === null;
  });
  if(!rows.length) return "";

  // 막힌 것부터 올린다. 지금 문제가 되는 조건이 맨 위에 있어야 바로 눌러본다.
  const rank = new Map();
  v.unmet.forEach(r => rank.set(r.id, 0));
  v.unknown.forEach(r => rank.set(r.id, 1));
  rows.sort((a, b) => (rank.has(a.id) ? rank.get(a.id) : 2) - (rank.has(b.id) ? rank.get(b.id) : 2));

  const seg = (subject, cur) => [[true,"예"],[false,"아니오"],[null,"모름"]]
    .map(([val, text]) =>
      `<button class="seg${cur === val ? " on" : ""}" type="button"
        data-subject="${esc(subject)}" data-value="${val === null ? "null" : val}">${text}</button>`)
    .join("");

  const list = rows.map(c => {
    const s = c.predicate.subject;
    const changed = s in overrides ? " changed" : "";
    return `<li class="${changed.trim()}">
      <span class="tw-label">${esc(c.label)}</span>
      <span class="tw-seg">${seg(s, currentValue(s, prof))}</span>
    </li>`;
  }).join("");

  const n = Object.keys(overrides).length;
  const reset = n
    ? `<button class="reset" type="button" id="reset">직접 바꾼 값 ${n}개 되돌리기</button>` : "";

  return `<section class="tweak">
    <h3><span class="eyebrow">실험</span>값을 바꾸면 판정이 바뀝니다</h3>
    <p class="lede">아래 상태를 바꾸면 판정을 <b>즉시 다시 계산</b>합니다.
      규칙 엔진이라 같은 값이면 항상 같은 답이 나옵니다.
      바꾼 값은 이 화면에만 적용되고 <b>저장되지 않습니다</b>.</p>
    <ul class="tw">${list}</ul>
    ${reset}
  </section>`;
}

function metSection(v, lowById){
  if(!v.met.length) return "";
  // 해석이 개입한 조건은 별도 섹션으로 빼지 않고 충족 목록 안에서 `~` 로 표시한다.
  const rows = v.met.map(r => {
    const low = lowById.get(r.id);
    return low
      ? `<li class="interp">${esc(r.label)}<em>${esc(low.reason || "근거 해석이 개입함")}</em></li>`
      : `<li>${esc(r.label)}</li>`;
  }).join("");
  return `<section class="met"><h3><span class="eyebrow">확인됨</span>충족한 조건</h3><ul>${rows}</ul></section>`;
}

function render(v, plan, tree, prof){
  const lowById = new Map(v.low_confidence.map(r => [r.id, r]));

  $("#verdict").innerHTML = verdictSection(v);

  // 오른쪽은 근거의 흐름이다. 진짜(조건 트리)를 가짜(가상 상태)보다 앞에 둔다.
  $("#out").innerHTML =
      railSection(v, tree)
    + tweakSection(tree, prof, v)
    + planSection(plan)
    + metSection(v, lowById)
    + treeSection(tree)
    + stateSection(prof)
    + `<p class="foot">판정 엔진 v${esc(v.engine_version)} · 조건 수집일 ${esc(v.tree_collected_at)}<br>
        조건은 KB 공개 안내·약관·FAQ에서 추출했으며 항목마다 <b>출처와 수집일</b>이 있습니다.</p>`;
}

async function judge(){
  const btn = $("#run");
  btn.disabled = true; btn.textContent = "판정 중…";
  try{
    const body = JSON.stringify({
      goal_id: $("#goal").value, profile_id: $("#profile").value, overrides,
    });
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
    // 마운트가 둘이므로 둘 다 비운다. 판정이 실패했는데 왼쪽에 이전 결론이
    // 남아 있으면 화면이 거짓말을 하게 된다.
    $("#verdict").innerHTML = "";
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
    // 조건 수는 드롭다운에 쓰지 않는다. 목표마다 조건 수가 달라
    // "조건 1개"가 나란히 보이면 자산의 규모를 스스로 깎는다.
    // 규모는 판정 뒤 조건 트리 섹션에서 근거와 함께 보여준다.
    $("#goal").innerHTML = goals.map(g =>
      `<option value="${esc(g.goal_id)}">${esc(g.goal_label)}</option>`).join("");

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

    // 목표나 상태를 다시 고르면 직접 바꾼 값은 버린다.
    // 다른 사람의 상태에 내가 바꾼 값을 얹으면 그건 아무의 상태도 아니다.
    $("#goal").addEventListener("change", () => {
      overrides = {};
      fillProfiles($("#goal").value);
      judge();
    });
    $("#profile").addEventListener("change", () => { overrides = {}; judge(); });

    // 값 바꾸기 — 다시 그려지는 영역이라 위임으로 받는다
    $("#out").addEventListener("click", e => {
      const seg = e.target.closest("button.seg");
      if(seg){
        const raw = seg.dataset.value;
        overrides[seg.dataset.subject] = raw === "null" ? null : raw === "true";
        judge();
        return;
      }
      if(e.target.closest("#reset")){ overrides = {}; judge(); }
    });

    await judge();
  }catch{
    $("#out").innerHTML = `<div class="err">서버에 연결하지 못했습니다. <code>uvicorn src.api.main:app</code> 가 실행 중인지 확인해 주세요.</div>`;
  }
})();

$("#run").addEventListener("click", judge);
