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

// `support_count` 는 **문장(청크) 수**다. 문서 수가 아니다.
// (merge.py 가 같은 뜻으로 읽힌 청크 묶음의 크기를 넣는다)
// 이걸 "문서 N곳"이라고 표시하고 있었다 — 12개 조건 중 5개가 부풀려졌고,
// 심사자가 트리의 source_ids 만 세어도 걸리는 자리였다.
// 문서 수와 문장 수를 나눠서, 각각 정확히 말한다.
function support(prov){
  const docs = prov && prov.source_ids ? new Set(prov.source_ids).size : 0;
  const spans = (prov && prov.support_count) || 0;
  return {docs, spans};
}

function supportText(prov){
  const {docs, spans} = support(prov);
  if(docs > 1) return `<b>문서 ${docs}곳</b>에서 같은 조건이 추출됨` + (spans > docs ? ` · 문장 ${spans}개` : "");
  if(spans > 1) return `한 문서의 <b>문장 ${spans}개</b>에서 같은 조건이 추출됨`;
  return "";
}

// 링크로 그릴 수 있는 주소인가. 조건 트리는 LLM 이 만든 데이터이므로
// `javascript:` 같은 스킴이 섞여 들어올 여지를 남기지 않는다.
const safeUrl = u => /^https?:\/\//i.test(String(u || "")) ? String(u) : "";

function evidence(ev, prov, open, key){
  if(!ev) return "";
  const conf = ev.confidence !== "high" ? ` · 신뢰도 ${esc(ev.confidence)}` : "";
  // 같은 조건이 여러 곳에서 확인됐다는 사실 자체가 신뢰의 근거다. 요약줄에 드러낸다.
  const n = supportText(prov);
  const href = safeUrl(ev.url);
  const link = href
    ? `<a class="src" href="${esc(href)}" target="_blank" rel="noopener">원문 열기 ↗<span class="sr-only">(새 창)</span></a>` : "";
  return `<details${open ? " open" : ""} data-key="ev-${esc(key || "")}"><summary>근거 원문 ${n}</summary>
    <blockquote>${esc(ev.quote)}
      <cite>${esc(ev.source_title)} · ${esc(ev.collected_at)} 수집${conf} ${link}</cite>
    </blockquote></details>`;
}

// showSev: 이 절에 필수와 참고가 **섞여 있을 때만** 칩을 단다.
// 전부 필수인 화면에 「필수」를 다는 것은 정보가 아니라 잡음이다.
function node(r, kind, open, hideReason, showSev){
  const rem = r.remedy || {};
  const sev = showSev
    ? (r.severity === "blocking"
        ? `<span class="sev must">필수</span>` : `<span class="sev note">참고</span>`)
    : "";
  let body = "";
  if(kind === "stop"){
    if(rem.primary_path) body += `<div class="meta">해결 <b>${esc(rem.primary_path)}</b></div>`;
    // 세 값이다. null(모름)을 "앱에서 불가"로 뭉치면 근거 없는 주장이 된다.
    if(rem.actionable_in_app === false){
      body += `<div><span class="offapp">앱 밖에서만</span></div>`;
    }else if(rem.actionable_in_app === null || rem.actionable_in_app === undefined){
      body += rem.primary_path
        ? `<div><span class="nopath">어디서 하는지는 수집한 문서에 없음</span></div>`
        : `<div><span class="nopath">해결 방법이 수집한 문서에 없음</span></div>`;
      if(rem.note) body += `<div class="t-note">${esc(rem.note)}</div>`;
    }
    // 검수에서 사람이 쓴 문장이라 **강조**가 섞인다. escEm 은 이스케이프한 뒤
    // 별표만 되살리므로 태그가 새어 들어갈 수 없다 (review_override 와 같은 처리).
    if(r.scope_note) body += `<div class="scope">${escEm(r.scope_note)}</div>`;
    body += evidence(r.evidence, r.provenance, open, r.id);
  }else if(kind === "hold" && r.reason && !hideReason){
    body += `<div class="meta">${esc(r.reason)}</div>`;
  }
  // 레일 마커는 색과 테두리 모양으로만 상태를 말한다. 보조기술에는 안 들린다.
  return `<div class="node ${kind}">
    <div class="label"><span class="sr-only">${NODE_STATE[kind] || ""}. </span>${esc(r.label)}${sev}</div>
    ${body}</div>`;
}

// 해결 계획 — "하나만 풀면 어떻게 되나".
// 서버(judge/simulate.py)가 계산한 문장을 그대로 쓴다. 화면에서 다시 판단하지 않는다.
function planSection(plan){
  // 막는 조건이 없어도 서버는 상황을 설명하는 문장을 만든다.
  //   "막고 있는 조건은 찾지 못했습니다. 다만 확인되지 않은 값이 N개 있어
  //    된다고 답하지는 않습니다."
  // 이 문장이 「모르면 모른다」는 우리 원칙을 담은 유일한 자리인데,
  // must_fix 가 비었다는 이유로 화면이 통째로 버리고 있었다.
  if(!plan) return "";
  if(!plan.must_fix.length){
    // ok 는 판정 블록이 이미 다 말했다. 같은 말을 절 하나 더 써서 반복하지 않는다.
    if(plan.final_outcome !== "indeterminate" || !plan.summary) return "";
    return `<section class="plan">
      <h3><span class="eyebrow">계획</span>무엇을 더 알아야 하나</h3>
      <p class="lede">${esc(plan.summary)}</p>
    </section>`;
  }

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

  // 소요 시간은 잰 적이 없다. 그리고 '앱에서 불가'가 곧 '창구'도 아니다 —
  // 영업점·ATM·고객센터가 섞여 있다. 데이터가 보증하는 데까지만 말한다.
  const visit = plan.needs_visit_ids.length
    ? `<p class="order">앱 밖에서 해결해야 하는 조건은 <b>어디서 하는지가
       각 조건의 근거 원문에 적혀 있습니다.</b></p>` : "";

  // 풀 것이 하나뿐이면 "하나만 풀면 되나요?"는 답이 정해진 질문이다.
  return `<section class="plan">
    <h3><span class="eyebrow">계획</span>${plan.must_fix.length === 1
      ? "무엇을 해야 하나" : "하나만 풀면 되나요?"}</h3>
    <p class="lede">${esc(plan.summary)}</p>
    ${rows ? `<ul class="ladder">${rows}</ul>` : ""}
    ${visit}
    ${plan.final_note ? `<p class="order">${esc(plan.final_note)}</p>` : ""}
  </section>`;
}

// ── 대조한 사용자 상태 ─────────────────────────────────────────
// 이 시스템에서 가짜는 사용자 상태 하나뿐이다. 그렇다면 감추지 말고 펼친다.
// 조건 · 상태 · 판정이 모두 보여야 심사자가 손으로 검증할 수 있다.

// 이 절은 "이 상태로 판정했습니다"라고 말한다. 그러므로 **판정에 실제로 쓰인 값**을
// 보여야 한다. 직접 바꾼 값을 빼고 원본만 그리면 화면이 거짓말을 하게 된다.
function effectiveState(prof){
  const out = [];
  ["card", "account", "context"].forEach(group => {
    Object.entries(prof[group] || {}).forEach(([k, v]) => {
      const path = `${group}.${k}`;
      const changed = path in overrides;
      out.push({path, value: changed ? overrides[path] : v, changed});
    });
  });
  return out;
}

function stateRows(prof){
  return effectiveState(prof).map(({path, value, changed}) => {
    const unknown = value === null || value === undefined;
    const val = unknown ? "모름"
      : typeof value === "boolean" ? (value ? "예" : "아니오")
      : typeof value === "number" ? value.toLocaleString("ko-KR") : String(value);
    return `<tr class="${[unknown ? "u" : "", changed ? "c" : ""].filter(Boolean).join(" ")}">
      <th scope="row"><code>${esc(path)}</code></th><td>${esc(val)}</td></tr>`;
  }).join("");
}

function stateSection(prof){
  if(!prof) return "";
  const rows = effectiveState(prof);
  const unknown = rows.filter(r => r.value === null || r.value === undefined).length;
  const changed = rows.filter(r => r.changed).length;

  // 값을 바꿨다면 프로필 설명은 더 이상 이 상태를 정확히 말하지 않는다. 그렇게 적는다.
  const lede = changed
    ? `${esc(prof.description)}<span class="edited">여기에 직접 바꾼 값 ${changed}개가 얹혀 있습니다.
       아래 표는 <b>판정에 실제로 쓰인 값</b>입니다.</span>`
    : esc(prof.description);

  return `<section class="state">
    <h3><span class="eyebrow">입력</span>대조한 사용자 상태</h3>
    <p class="lede">${lede}</p>
    <details${changed ? " open" : ""} data-key="state"><summary>상태값 ${rows.length}개 보기${unknown ? ` · 모름 ${unknown}개` : ""}${changed ? ` · 바꿈 ${changed}개` : ""}</summary>
      <table class="st"><caption class="sr-only">판정에 실제로 쓰인 사용자 상태값</caption>
        <tbody>${stateRows(prof)}</tbody></table>
      <p class="foot">이 시스템에서 <b>가짜는 이 상태 하나뿐</b>입니다.
        조건과 인용은 KB 공개문서에서 나옵니다. 문서에 없어 저희가 앱에서
        직접 확인한 것은 <b>「앱에서 직접 확인」</b>으로 표시했습니다.
        실제 서비스라면 이 값은 은행 내부 조회로 채워지게 됩니다.</p>
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

// 값이 필요 없는 연산자. "card.pin 존재 null" 같은 문장이 나오지 않게 한다.
const OP_NO_VALUE = new Set(["exists", "not_exists"]);

function predText(p){
  const op = OPTEXT[p.op] || p.op;
  if(OP_NO_VALUE.has(p.op)) return `${p.subject} ${op}`;

  let v = p.value;
  // 배열을 먼저 본다. object 분기가 앞에 있으면 배열이 거기로 삼켜져
  // join 이 영원히 실행되지 않고 원시 JSON 이 그대로 노출된다.
  if(Array.isArray(v)) v = v.join(", ");
  else if(v && typeof v === "object"){
    if("now_plus_days" in v) v = v.now_plus_days === 0 ? "오늘" : `오늘+${v.now_plus_days}일`;
    else if("days" in v && "n" in v) v = `${v.days}일 내 ${v.n}회`;   // n 을 빠뜨리면 뜻이 바뀐다
    else if("days" in v) v = `${v.days}일`;
    else v = JSON.stringify(v);
  }
  else if(typeof v === "number") v = v.toLocaleString("ko-KR");
  else v = String(v);
  return `${p.subject} ${op} ${v}`;
}

// 무엇이 이 해결 방법을 뒷받침하는가. 근거가 없으면 아무 말도 하지 않는다.
//
// evidence 는 두 경우가 있다. 원문이 **어디서** 하라고 말한 경우와,
// **무엇을** 하라고만 말한 경우다. 카드 유효기한이 후자다 —
// "갱신 재발급이 필요합니다"는 있지만 어디서 하는지는 없다. 라벨을 구분한다.
function basisLabel(r){
  if(!r.basis) return "";
  if(r.basis === "measured") return "앱에서 직접 확인";
  if(r.basis === "self_evident") return "조건 자체로 자명";
  return r.actionable_in_app === null || r.actionable_in_app === undefined
    ? "근거 원문에 할 일 명시" : "근거 원문에 채널 명시";
}

function treeItem(c){
  const a = c.remedy.actionable_in_app;
  const app = a === true ? `<span class="chip">앱에서 가능</span>`
            : a === false ? `<span class="chip off">앱 밖에서만</span>`
            : c.remedy.primary_path
              ? `<span class="chip none">해결 장소 미확인</span>`
              : `<span class="chip none">해결 방법 미확인</span>`;
  // 심각도지 현재 상태가 아니다. 조건 이름에 이미 '차단'이 들어가 있어
  // 「차단」이라고 쓰면 "지금 차단됐다"로 읽힌다. 계획 절의 "필수 조건"과 말을 맞춘다.
  const sev = c.severity === "blocking"
    ? `<span class="chip stop">필수</span>` : `<span class="chip warn">참고</span>`;
  // 근거의 두께는 **문서 수**로 센다. 문장 수는 부가 정보다.
  // provenance 가 없으면 "1곳"이라고 지어내지 않고 칩 자체를 뺀다.
  const {docs, spans} = support(c.provenance);
  const supChip = docs
    ? `<span class="chip q">문서 ${docs}곳${spans > docs ? ` · 문장 ${spans}` : ""}</span>` : "";
  return `<li>
    <div class="t-label">${esc(c.label)}</div>
    <div class="t-pred"><code>${esc(predText(c.predicate))}</code></div>
    <div class="t-meta">${sev}${app}${supChip}
      ${c.remedy.basis ? `<span class="chip b">${esc(basisLabel(c.remedy))}</span>` : ""}</div>
    ${c.remedy.primary_path ? `<div class="t-path">해결 <b>${esc(c.remedy.primary_path)}</b></div>` : ""}
    ${c.remedy.note ? `<div class="t-note">${esc(c.remedy.note)}</div>` : ""}
    ${c.scope_note ? `<div class="scope">${escEm(c.scope_note)}</div>` : ""}
    <details data-key="tree-${esc(c.id)}"><summary>근거 원문</summary>
      <blockquote>${esc(c.evidence.quote)}
        <cite>${esc(c.evidence.source_title)} · ${esc(c.evidence.collected_at)} 수집
          ${safeUrl(c.evidence.url) ? `<a class="src" href="${esc(safeUrl(c.evidence.url))}" target="_blank" rel="noopener">원문 열기 ↗<span class="sr-only">(새 창)</span></a>` : ""}
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

  const appYes = tree.conditions.filter(c => c.remedy.actionable_in_app === true).length;
  const appNo = tree.conditions.filter(c => c.remedy.actionable_in_app === false).length;
  const noPath = tree.conditions.length - appYes - appNo;
  // 화면이 여기서 범위를 바꾼다. 위는 '고른 상태 한 사람', 아래는 '사람과 무관한 원본'.
  // 이 경계를 말하지 않으면 판정이 「가능」인데 조건 목록이 또 뜨는 것으로 읽힌다.
  // 「근거 자료」라는 이름도 같은 오해를 키웠다 — 이 판정의 근거로 읽혔다.
  return `<section class="asset">
    <p class="scope-break"><b>여기부터는 판정과 별개입니다.</b>
      아래 목록은 <b>지금 고른 상태와 무관하게 언제나 같습니다.</b>
      위에서 충족·미충족으로 나뉘었던 조건이 여기서는 원본 그대로 다시 나옵니다.</p>
    <h3><span class="eyebrow">조건 원본</span>이 목표에 걸린 조건 전체</h3>
    <p class="lede">조건과 인용은 <b>KB 공개문서에서 자동 추출</b>했고, 각 조건은 기계가 평가하는
      형태(<code>subject op value</code>)를 함께 가집니다.
      사람이 검수 단계에서 더한 메모는 <b>그 자리에 함께 표시</b>합니다.
      「문서 N곳」은 <b>같은 조건이 몇 개 문서에서 추출됐는지</b>이지, 그만큼 독립적으로
      입증됐다는 뜻이 아닙니다. 인용이 적용 범위를 걸어둔 조건은 <b>그 범위를 함께</b> 적습니다.
      <b>이 트리가 저희가 만든 자산입니다.</b></p>
    <div class="t-stat">
      <div><b>${tree.conditions.length}</b>조건</div>
      <div><b>${appYes}</b>앱에서 가능</div>
      <div><b>${appNo}</b>앱 밖에서만</div>
      <div><b>${noPath}</b>경로 미확인</div>
      <div><b>${tree.source_meta.source_count}</b>근거 문서</div>
      <div><b>${esc(tree.source_meta.collected_at)}</b>수집</div>
    </div>
    <details class="t-open" data-key="tree-all"><summary>조건 ${tree.conditions.length}개를 근거 원문과 함께 펼쳐 보기</summary>
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
    <span>규칙 엔진 <b>v${esc(v.engine_version)}</b></span><i aria-hidden="true">·</i>
    <span>실행 시점 LLM <b>0회</b></span><i aria-hidden="true">·</i>
    <span>같은 입력 <b>10가지</b>를 각 200회, <b>${DETERMINISM_RUNS.toLocaleString("ko-KR")}회</b> 돌려 <b>매번 같은 판정</b></span>
  </div>
  <p class="trust-note">정답률이 아니라 <b>흔들림이 없다</b>는 뜻입니다. 목표 2종 × 상태 5종 = 10가지 조합.</p>`;
}

// 판정은 **차단(blocking) 조건**만 보고 정해진다. 주의(warning) 조건이 미충족이거나
// 값을 몰라도 `ok` 가 나온다. 그런데 화면이 "확인한 조건을 모두 충족합니다"라고 하면
// 바로 옆 집계의 "확인 불가 1"과 정면으로 부딪힌다.
// 남은 것이 있으면 남았다고 말한다.
function verdictDesc(v){
  const t = VERDICT[v.verdict] || VERDICT.indeterminate;
  if(v.verdict !== "ok") return t.desc;

  const left = [];
  if(v.unknown.length) left.push(`확인하지 못한 값 <b>${v.unknown.length}개</b>`);
  if(v.unmet.length) left.push(`주의 조건 <b>${v.unmet.length}개</b>`);
  if(!left.length) return t.desc;
  return `막는 조건은 없습니다. 다만 ${left.join(" · ")}가 남아 있습니다.`;
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
    <p>${verdictDesc(v)}</p>
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
  // 이 자리는 화면에서 가장 먼저 읽히는 문장이다. **지금 이 사람의 사실**을 쓴다.
  // 트리 전체 통계(11개 중 2/3/6)는 '이 목표의 조건 전체' 절에 같은 숫자로 이미 있다.
  let impact = "";
  const blocking = v.unmet.filter(r => r.severity === "blocking");
  const offApp = blocking.filter(r => r.remedy && r.remedy.actionable_in_app === false).length;
  if(blocking.length && offApp){
    impact = blocking.length === 1
      ? `<p class="impact">막고 있는 이 조건은 <b>앱에서 해결할 수 없습니다.</b>
         앱만 만져서는 끝나지 않습니다.</p>`
      : `<p class="impact">지금 막고 있는 조건 <b>${blocking.length}개</b> 중
         <b>${offApp}개는 앱에서 해결할 수 없습니다.</b> 앱만 만져서는 끝나지 않습니다.</p>`;
  }

  // 우리 최고의 증거(직접 바꿔 보기)가 스크롤 아래에 있다. 여기서 존재를 알린다.
  const one = v.unmet.length + v.unknown.length === 1;
  const jump = `<p class="to-tweak-wrap"><a class="to-tweak" href="#tweak">${one
    ? "이 조건의 값을 직접 바꿔 판정이 어떻게 달라지는지 보실 수 있습니다"
    : "이 조건들의 값을 직접 바꿔 판정이 어떻게 달라지는지 보실 수 있습니다"}</a></p>`;

  // 근거는 접어두면 없는 것과 같다. 첫 건은 펼쳐 둔다 —
  // 클릭하지 않는 사람에게도 "출처 있는 판정"이 즉시 보여야 한다.
  // 미충족 안에 필수와 참고가 섞이면, 집계의 「미충족 N」과 아래 문장의 「막고 있는 M개」가
  // 다른 수가 된다. 실제로 4 vs 3 이 나왔다. 무엇을 세는 수인지 화면이 말해야 한다.
  const warnUnmet = v.unmet.filter(r => r.severity !== "blocking");
  const mixedStop = warnUnmet.length > 0 && blocking.length > 0;
  const stopLead = mixedStop
    ? `<p class="hold-lead">아래 <b>${v.unmet.length}개</b> 가운데
       <b>${blocking.length}개</b>가 판정을 막습니다.
       「참고」 ${warnUnmet.length}개는 충족되지 않았지만 판정을 막지는 않습니다.</p>`
    : "";
  const stops = stopLead
    + v.unmet.map((r, i) => node(r, "stop", i === 0, false, mixedStop)).join("");

  // 사유가 같은 노드가 여러 개면 같은 문장이 세로로 쌓인다(실측 10줄 중 8줄이 글자까지 동일).
  // 사람이 쓴 화면은 그러지 않는다. 사유를 절 위로 한 번씩만 올리고 목록에서는 뺀다.
  const byReason = new Map();
  v.unknown.forEach(r => {
    const k = r.reason || "";
    byReason.set(k, (byReason.get(k) || 0) + 1);
  });
  const grouped = v.unknown.length > 2;
  // 이 중 몇 개가 판정을 막는지 밝힌다 — 집계의 '확인 불가'와 계획의 숫자가
  // 다른 이유가 여기 있다. 나머지는 몰라도 판정이 바뀌지 않는다.
  const holdBlocking = v.unknown.filter(r => r.severity === "blocking").length;
  const holdLead = grouped
    ? `<p class="hold-lead">` + [...byReason]
        .map(([reason, cnt]) => `<b>${cnt}개</b>는 ${esc(reason.replace(/^이 (사용자 상태에는 )?/, ""))}`)
        .join(" · ")
      + (holdBlocking && holdBlocking < v.unknown.length
          ? `<br>이 가운데 <b>${holdBlocking}개</b>가 판정을 막습니다.
             나머지 ${v.unknown.length - holdBlocking}개는 몰라도 판정이 달라지지 않습니다.`
          : "")
      + `</p>`
    : "";
  const mixedHold = holdBlocking > 0 && holdBlocking < v.unknown.length;
  const holds = holdLead
    + v.unknown.map(r => node(r, "hold", false, grouped, mixedHold)).join("");

  // 제목이 판정과 어긋나면 안 된다. `ok` 인데 "어디서 막혔나"가 뜨면
  // 바로 위 판정과 정면으로 부딪힌다. 무엇이 남았는지에 따라 이름을 고른다.
  const head =
    v.verdict === "blocked" ? {tag: "원인", title: "어디서 막혔나"} :
    v.verdict === "indeterminate" ? {tag: "확인 필요", title: "무엇을 알아야 하나"} :
    {tag: "남은 것", title: "막지는 않지만 확인이 필요합니다"};

  // 문제 정의 문장은 '막혔을 때'의 말이다. 통과한 화면에 붙이면 맥락이 없다.
  const lead = v.verdict === "blocked" ? impact : "";

  return `<section class="rail"><h3><span class="eyebrow">${head.tag}</span>${head.title}</h3>
    ${lead}${stops}${holds}${jump}</section>`;
}

// ── 직접 바꿔 보기 ─────────────────────────────────────────────
// "프로필마다 답을 박아둔 것 아니냐"는 의심에 대한 답은 말이 아니라 조작이다.
// 값을 바꾸면 판정이 그 자리에서 다시 계산된다. 규칙 엔진이라 그럴 수 있다.
//
// overrides 는 이 브라우저 세션에만 있다. 서버는 요청 한 건에만 적용하고
// 프로필 파일은 건드리지 않는다.
let overrides = {};
// 실험 목록의 표시 순서. 목표·상태를 다시 고를 때만 새로 정한다.
let tweakOrder = null;
// 서버가 준 **원본** 프로필. 덮어쓴 값이 원래 값으로 돌아왔는지 판단하는 데 쓴다.
let lastProfile = null;

// 이 조건을 충족시키는 답이 '예'인가 '아니오'인가.
// 참/거짓으로 말할 수 없는 조건(금액·날짜)에는 붙이지 않는다 — 없는 답을 지어내지 않는다.
function wantedAnswer(p){
  if(typeof p.value !== "boolean") return null;
  if(p.op === "eq") return p.value ? "예" : "아니오";
  if(p.op === "neq") return p.value ? "아니오" : "예";
  return null;
}

function currentValue(subject, prof){
  if(subject in overrides) return overrides[subject];
  const [g, k] = subject.split(".");
  return (prof && prof[g]) ? prof[g][k] : undefined;
}

function tweakSection(tree, prof, v){
  if(!tree || !prof) return "";

  // 참/거짓 조건만 다룬다. 금액·날짜는 세 버튼으로 표현할 수 없다.
  //
  // 판단 기준은 **조건 쪽**이다. 현재 값이 null 이라는 이유로 토글을 붙이면
  // 금액 조건(≤ 6,000,000)에 '예'를 넣게 되고, 엔진은 그것을 비교하지 못해
  // 무조건 unknown 을 낸다 — 누를 수는 있는데 아무 일도 일어나지 않는 버튼이 된다.
  const rows = tree.conditions.filter(c => {
    if(typeof c.predicate.value !== "boolean") return false;   // 참/거짓 조건만
    const [g, k] = c.predicate.subject.split(".");
    if(!prof[g] || !(k in prof[g])) return false;      // 이 프로필에 없는 값은 못 바꾼다
    const cur = currentValue(c.predicate.subject, prof);
    return typeof cur === "boolean" || cur === null;
  });
  if(!rows.length) return "";

  const state = new Map();
  v.unmet.forEach(r => state.set(r.id, "stop"));
  v.unknown.forEach(r => state.set(r.id, "hold"));
  v.met.forEach(r => state.set(r.id, "ok"));

  // 막힌 것부터 올린다 — 지금 문제가 되는 조건이 맨 위에 있어야 바로 눌러본다.
  //
  // 다만 순서를 **매번** 다시 매기면 안 된다. 조건을 풀 때마다 그 행이 아래로
  // 내려가고, 방금 누른 버튼이 손가락 밑에서 사라진다(실측 225~316px 이동).
  // 순서는 목표·상태를 고른 시점에 한 번 정하고 그대로 유지한다.
  if(!tweakOrder){
    const rank = new Map();
    v.unmet.forEach(r => rank.set(r.id, 0));
    v.unknown.forEach(r => rank.set(r.id, 1));
    tweakOrder = rows.slice()
      .sort((a, b) => (rank.has(a.id) ? rank.get(a.id) : 2) - (rank.has(b.id) ? rank.get(b.id) : 2))
      .map(c => c.id);
  }
  rows.sort((a, b) => tweakOrder.indexOf(a.id) - tweakOrder.indexOf(b.id));

  // 선택 상태를 배경색으로만 표현하면 보조기술은 알 수 없다 (WCAG 1.4.1 · 4.1.2).
  const seg = (subject, cur) => [[true,"예"],[false,"아니오"],[null,"모름"]]
    .map(([val, text]) =>
      `<button class="seg${cur === val ? " on" : ""}" type="button"
        aria-pressed="${cur === val}"
        data-subject="${esc(subject)}" data-value="${val === null ? "null" : val}">${text}</button>`)
    .join("");

  const list = rows.map((c, i) => {
    const s = c.predicate.subject;
    const st = state.get(c.id);
    const cls = [st, s in overrides ? "changed" : ""].filter(Boolean).join(" ");
    // 버튼 이름이 "예/아니오/모름" 뿐이라 어느 조건인지 알 수 없었다. 라벨과 묶는다.
    const labelId = `tw-l${i}`;
    // 어느 쪽을 눌러야 충족인지 조건마다 다르다.
    //   card.locked 는 '아니오'여야 충족(잠기지 않아야 하므로)
    //   card.ic_pin_registered 는 '예'여야 충족(등록되어 있어야 하므로)
    // 조건 문장은 당위("~해야 합니다")고 버튼은 사실(현재 값)이라, 방향을 적어주지 않으면
    // 버튼이 조건에 대한 예/아니오처럼 읽혀 정반대로 이해된다.
    const want = wantedAnswer(c.predicate);
    // ✓/✕/? 는 CSS ::before 로 그린 기호다. 읽히지 않거나 뜻이 모호하므로 말로도 준다.
    const stateText = st === "ok" ? "현재 충족" : st === "stop" ? "현재 미충족" : "현재 확인 불가";
    return `<li class="${cls}">
      <span class="sr-only">${stateText}. </span>
      <span class="tw-label" id="${labelId}">${esc(c.label)}
        ${want ? `<span class="want">충족하려면 <b>${want}</b></span>` : ""}</span>
      <span class="tw-seg" role="group" aria-labelledby="${labelId}">${seg(s, currentValue(s, prof))}</span>
    </li>`;
  }).join("");

  const n = Object.keys(overrides).length;
  const reset = n
    ? `<button class="reset" type="button" id="reset">직접 바꾼 값 ${n}개 되돌리기</button>` : "";

  const skipped = tree.conditions.length - rows.length;
  return `<section class="tweak" id="tweak">
    <h3><span class="eyebrow">실험</span>값을 바꾸면 판정이 바뀝니다</h3>
    <p class="lede">아래 상태를 바꾸면 판정을 <b>즉시 다시 계산</b>합니다.
      규칙 엔진이라 같은 값이면 항상 같은 답이 나옵니다.
      바꾼 값은 이 화면에만 적용되고 <b>저장되지 않습니다</b>.
      ${rows.length === 1
        ? `이 목표의 조건은 1개입니다. <b>세 버튼을 차례로 눌러보시면
           가능 · 불가 · 확인 불가 세 판정이 모두 나옵니다.</b>`
        : skipped
          ? `여기 있는 것은 <b>예·아니오로 답할 수 있는 ${rows.length}개</b>입니다.
             금액·날짜 조건 ${skipped}개는 세 버튼으로 표현할 수 없어 빠져 있습니다.`
          : ""}</p>
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

// 화면을 통째로 다시 그리면 세 가지가 사라진다.
//   ① 방금 누른 버튼의 포커스 → 키보드로는 다음 조건을 만질 수 없다 (버튼이 21개다)
//   ② 펼쳐 둔 근거 원문 → 우리가 자산이라 부르는 것이 값을 바꿀 때마다 접힌다 (6개 → 2개 실측)
//   ③ 스크롤 위치 → 조건이 풀려 위가 줄면 아래가 당겨진다 (89px 튐 실측)
// 다시 그리기 전에 기억하고, 그린 뒤에 되돌린다.
const NODE_STATE = {stop: "미충족", pass: "충족", hold: "확인 불가"};

function announce(v){
  const t = VERDICT[v.verdict] || VERDICT.indeterminate;
  const parts = [t.title, `미충족 ${v.unmet.length}`, `충족 ${v.met.length}`];
  if(v.unknown.length) parts.push(`확인 불가 ${v.unknown.length}`);
  $("#announce").textContent = parts.join(", ") + ".";
}

function summaryKey(d){
  return d.dataset.key || "";
}

function renderKeeping(v, plan, tree, prof){
  const active = document.activeElement;
  const focusKey = active && active.classList && active.classList.contains("seg")
    ? [active.dataset.subject, active.dataset.value] : null;
  const openState = new Map(
    [...document.querySelectorAll("#out details")]
      .map(d => [summaryKey(d), d.open]).filter(([k]) => k));
  const anchorTop = (() => {
    const el = focusKey ? active : document.querySelector("#tweak");
    return el ? el.getBoundingClientRect().top : null;
  })();

  render(v, plan, tree, prof);

  // 펼침을 먼저 되돌린다 — 높이가 달라지므로 스크롤 보정보다 앞서야 한다
  document.querySelectorAll("#out details").forEach(d => {
    const was = openState.get(summaryKey(d));
    if(was !== undefined) d.open = was;      // 접어둔 것은 접힌 채로 둔다
  });
  const back = focusKey
    ? document.querySelector(
        `button.seg[data-subject="${CSS.escape(focusKey[0])}"][data-value="${focusKey[1]}"]`)
    : document.querySelector("#tweak");
  if(anchorTop !== null && back) window.scrollBy(0, back.getBoundingClientRect().top - anchorTop);
  if(focusKey && back) back.focus({preventScroll: true});
  announce(v);
}

function render(v, plan, tree, prof){
  lastProfile = prof;
  const lowById = new Map(v.low_confidence.map(r => [r.id, r]));

  $("#verdict").innerHTML = verdictSection(v);

  // 오른쪽은 범위 순이다. **고른 상태 한 사람** 이야기를 먼저 다 끝내고(원인·실험·계획·
  // 충족·그 판정에 쓴 입력), 그 다음에 사람과 무관한 조건 원본으로 넘어간다.
  // 트리를 가운데 끼우면 경계가 두 번 생겨 "여기부터 판정과 별개"라고 말할 수 없다.
  $("#out").innerHTML =
      railSection(v, tree)
    + tweakSection(tree, prof, v)
    + planSection(plan)
    + metSection(v, lowById)
    + stateSection(prof)
    + treeSection(tree)
    + `<p class="foot">판정 엔진 v${esc(v.engine_version)} · 조건 수집일 ${esc(v.tree_collected_at)}<br>
        조건은 KB <b>공개 안내 페이지·FAQ·카드뉴스</b>에서 추출했으며 항목마다 출처와 수집일이 있습니다.
        <br>이 목록은 저희가 수집한 문서에서 찾아낸 조건이며, <b>KB 조건의 전부라고 보증하지 않습니다.</b>
        <br>제8회 KB Future Finance A.I. Challenge 출품작입니다.
        <b>KB국민카드·KB국민은행의 공식 서비스가 아닙니다.</b></p>`;
}

// 값을 빠르게 여러 번 바꾸면 요청이 겹친다. 응답은 보낸 순서대로 오지 않는다.
// 늦게 도착한 옛 응답이 최신 판정을 덮어쓰면, 버튼·상태표는 새 값인데 판정만
// 과거가 되어 화면이 앞뒤가 안 맞는 말을 하게 된다.
// (느린 응답 1.8초를 주입해 실제로 재현했다 — 판정만 이전 값으로 남았다)
let requestSeq = 0;

// FastAPI 의 422 는 `detail` 이 **배열**이다. 그대로 Error 에 넣으면 화면에
// `[object Object]` 가 뜬다. 서버가 HTML 오류 페이지를 내면 json() 자체가 던진다.
async function errorText(res){
  try{
    const body = await res.json();
    if(typeof body.detail === "string") return body.detail;
  }catch{ /* JSON 이 아니면 아래 기본 문구로 */ }
  return `요청이 처리되지 않았습니다 (HTTP ${res.status})`;
}

async function judge(){
  const mine = ++requestSeq;
  const stale = () => mine !== requestSeq;
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
    if(stale()) return;                 // 더 최신 요청이 있다. 이 결과는 버린다
    // 목표를 바꾸는 사이 옛 화면의 버튼을 누르면 새 프로필에 없는 키가 실려 400 이 온다.
    // 그 값은 지금 화면에서 의미가 없으므로 버리고 한 번만 다시 판정한다.
    if(res.status === 400 && Object.keys(overrides).length){
      overrides = {}; tweakOrder = null;
      return judge();
    }
    if(!res.ok) throw new Error(await errorText(res));
    // 계획·트리는 부가 정보다. 실패해도 판정은 보여준다.
    const [verdict, plan, tree, prof] = [
      await res.json(),
      planRes.ok ? await planRes.json() : null,
      treeRes.ok ? await treeRes.json() : null,
      profRes.ok ? await profRes.json() : null,
    ];
    if(stale()) return;                 // 본문을 읽는 동안에도 새 요청이 올 수 있다
    $("#err").innerHTML = "";           // 지난 오류를 남겨두지 않는다
    renderKeeping(verdict, plan, tree, prof);
  }catch(e){
    if(stale()) return;                 // 옛 요청의 실패로 최신 화면을 지우지 않는다
    // 판정이 실패했는데 이전 결론이 남아 있으면 화면이 거짓말을 하게 된다.
    // 다만 오른쪽(#out)은 지우지 않는다 — 되돌리기 버튼이 거기 있어서,
    // 덮어버리면 사용자가 직접 바꾼 값을 되돌릴 방법이 사라진다.
    $("#verdict").innerHTML = "";
    $("#err").innerHTML = `<div class="err">${esc(e.message)}
      <button type="button" id="retry">다시 시도</button></div>`;
  }finally{
    if(!stale()){ btn.disabled = false; btn.textContent = "판정하기"; }
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
      overrides = {}; tweakOrder = null;
      fillProfiles($("#goal").value);
      judge();
    });
    $("#profile").addEventListener("change", () => { overrides = {}; tweakOrder = null; judge(); });

    // 값 바꾸기 — 다시 그려지는 영역이라 위임으로 받는다
    $("#out").addEventListener("click", e => {
      // 안내를 눌렀을 때. 주소를 바꾸지 않고(뒤로가기를 만들지 않고) 데려간다
      const jump = e.target.closest(".to-tweak");
      if(jump){
        e.preventDefault();
        const el = $(".tweak");
        if(!el) return;
        const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        el.scrollIntoView({behavior: smooth ? "smooth" : "auto", block: "center"});
        el.classList.add("flash");
        setTimeout(() => el.classList.remove("flash"), 1400);
        return;
      }

      const seg = e.target.closest("button.seg");
      if(seg){
        const raw = seg.dataset.value;
        const next = raw === "null" ? null : raw === "true";
        const subject = seg.dataset.subject;
        // 원래 값으로 돌아왔으면 '바꿈'이 아니다. 덮어쓰기를 지운다 —
        // 이미 선택된 버튼을 다시 눌러도 "직접 바꾼 값 1개"가 뜨던 문제.
        const [g, k] = subject.split(".");
        const base = lastProfile && lastProfile[g] ? lastProfile[g][k] : undefined;
        if(next === base) delete overrides[subject];
        else overrides[subject] = next;
        judge();
        return;
      }
      if(e.target.closest("#reset")){
        overrides = {}; tweakOrder = null;
        judge().then(() => {
          // 되돌리기 버튼은 사라진다. 포커스를 실험 절 첫 버튼으로 옮겨
          // 키보드 사용자가 페이지 맨 앞으로 튕기지 않게 한다.
          const first = document.querySelector("ul.tw .seg");
          if(first) first.focus({preventScroll: true});
        });
      }
    });
    $("#err").addEventListener("click", e => {
      if(e.target.closest("#retry")) judge();
    });

    await judge();
  }catch(e){
    console.error("초기 로딩 실패 — 로컬이라면 `uvicorn src.api.main:app` 실행 여부를 확인하세요.", e);
    $("#err").innerHTML = `<div class="err">화면을 불러오지 못했습니다.
      잠시 뒤 새로고침해 주세요. 계속 같으면 서버가 내려간 상태입니다.</div>`;
  }
})();

$("#run").addEventListener("click", judge);
