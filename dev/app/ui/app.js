/* Crusader Wars 2 launcher UI. Python side: bridge.py via pywebview js_api.
   Flow: CK3 save -> pick battle -> roll armies -> battle pack -> fight in 3K -> result. */
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = n => Number(n||0).toLocaleString("en-CA");

/* ---- event bus the Python side pushes into via evaluate_js ---- */
window.cw2 = { handlers:{}, on(t,f){(this.handlers[t]=this.handlers[t]||[]).push(f)},
  emit(t,p){(this.handlers[t]||[]).forEach(f=>f(p)); log(`${t} ${JSON.stringify(p)}`)} };

/* ---- bridge call: {'ok':...} or {'error': msg} -> JS exception ---- */
async function call(method, ...args){
  const r = await window.pywebview.api[method](...args);
  if (r && r.error !== undefined) throw new Error(r.error);
  return r || {};
}
const err = e => (e && (e.message || e)) ? (e.message || String(e)) : String(e);

/* ---- state ---- */
const STEPS=[
  {id:"setup",   title:"Start in CK3"},
  {id:"enc",     title:"Pick the CK3 battle"},
  {id:"roster",  title:"Roll armies"},
  {id:"battle",  title:"Fight in 3K"},
  {id:"return",  title:"Write back"}
];
const S={view:0, reached:0, sealed:false, busy:false, mode:"records",
  health:null, enc:null, roster:null, install:[], installed:false,
  launched:false, removed:false, result:null, diff:null, error:null};

function log(msg){const el=document.getElementById("log");
  el.textContent+=`[${new Date().toLocaleTimeString("en-CA",{hour12:false})}] ${msg}\n`;el.scrollTop=el.scrollHeight;}

/* tally gap: 5 finished steps closes it; seal after write-back */
function setTally(){
  const done=S.sealed?5:S.reached; const g=(5-done)*7;
  document.getElementById("halfL").style.transform=`translateX(${-g}px)`;
  document.getElementById("halfR").style.transform=`translateX(${g}px)`;
  document.getElementById("seal").classList.toggle("on",S.sealed);
  document.getElementById("stepline").innerHTML=S.sealed
    ? "<b>Sealed.</b> Result is in the save."
    : `Step <b>${S.view+1}</b> of 5: ${STEPS[S.view].title}`;
}

function renderRail(){
  document.getElementById("rail").innerHTML=STEPS.map((s,i)=>{
    const state=i===S.view?"current":i>S.reached?"locked":"done";
    return `<li><button data-go="${i}" data-state="${state}" ${i>S.reached?"disabled":""}
      aria-current="${i===S.view?"step":"false"}"><span class="n">${i+1}</span>${s.title}</button></li>`;
  }).join("");
}

function render(){
  renderRail(); setTally();
  document.getElementById("main").innerHTML=V[STEPS[S.view].id]();
}
function go(i){S.view=i; S.reached=Math.max(S.reached,i); S.error=null; render(); document.getElementById("main").focus();}

/* ---- screens ---- */
const V={
  setup(){
    const h=S.health;
    if(!h) return `<h2>Start in Crusader Kings III</h2><p class="lede">Checking game paths and tools...</p>`;
    const ck3Ok=h.gates && h.gates.ck3;
    return `<h2>Start in Crusader Kings III</h2>
    <p class="lede">Every battle starts in CK3. Open your campaign, pause while your armies are fighting, and save. The launcher reads that save, rolls both armies from Three Kingdoms units, and stages the fight.</p>
    <div class="panel paths">${h.paths.map(p=>`
      <div class="pathrow"><span class="dot ${p.ok?"":"bad"}" aria-label="${p.ok?"Found":"Missing"}"></span>
        <span>${esc(p.label)}</span><code title="${esc(p.value)}">${esc(p.value)}</code></div>`).join("")}
    </div>
    <div class="stack" style="margin-top:16px">
      ${h.tk_running
        ? `<p class="notice">Three Kingdoms is running. Close it before installing or removing the battle pack.</p>`
        : `<p class="notice ok">Three Kingdoms is closed. Pack operations are available.</p>`}
      ${h.ck3_running
        ? `<p class="notice ok">Crusader Kings III is running. Save while a battle is on, then load it here.</p>`
        : ``}
    </div>
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}
    <div class="actions">
      <button class="btn-primary" data-action="toEncounter" ${ck3Ok?"":"disabled"}>Load my latest CK3 save</button>
      ${h.ck3_running?"":`<button class="btn-quiet" data-action="launchCk3">Open Crusader Kings III</button>`}
      <button class="btn-quiet" data-action="recheck">Check again</button>
    </div>`;
  },
  enc(){
    const e=S.enc;
    if(!e) return `<h2>Pick the CK3 battle</h2>${S.error?`<p class="notice">${esc(S.error)}</p>
      <div class="actions"><button class="btn-quiet" data-action="toEncounter">Try again</button></div>`
      :`<p class="lede">Reading your latest save...</p>`}`;
    const side=s=>`<section class="panel side" aria-label="${s.role}">
      <p class="role">${s.role}${s.yours?" · your army":""}</p><h3>${fmt(Math.round(s.fighting))} fighting men</h3>
      <dl class="kv" style="margin-top:12px">
        <dt>At the start</dt><dd>${fmt(Math.round(s.initial))} men</dd>
        <dt>CK3 armies</dt><dd><code style="font-size:.75rem">${esc(s.army_ids.join(", "))}</code></dd>
      </dl></section>`;
    const list=e.battles.map(b=>`<li><button class="${b.combat_id===e.combat_id?"btn-primary":"btn-quiet"}" data-action="pickBattle" data-id="${esc(b.combat_id)}"
      aria-pressed="${b.combat_id===e.combat_id}">${fmt(b.men[0])} v ${fmt(b.men[1])}${b.yours?" · yours":""}</button></li>`).join("");
    return `<h2>Pick the CK3 battle</h2>
    <p class="lede"><code>${esc(e.save_name)}</code>, ${esc(e.date||"undated")}: ${e.battles.length} battle${e.battles.length===1?"":"s"} in progress. Battles with one of your own armies are marked; a vassal's or ally's army is not detected, so pick yours.</p>
    <ul class="picks" style="list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:6px">${list}</ul>
    <div class="faceoff">${side(e.sides[0])}<div class="vs" aria-hidden="true">vs</div>${side(e.sides[1])}</div>
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}
    <div class="actions">
      <button class="btn-primary" data-action="toRoster">Roll armies</button>
      <button class="btn-quiet" data-action="toEncounter">Reload latest save</button>
    </div>`;
  },
  roster(){
    const r=S.roster;
    if(!r) return `<h2>Roll armies</h2>${S.error?`<p class="notice">${esc(S.error)}</p>`:`<p class="lede">Rolling...</p>`}`;
    const col=side=>`<section class="panel"><h3 style="font-family:var(--display);font-weight:400;margin:0">${esc(side.role)}</h3>
      <p style="color:var(--bone-dim);margin:2px 0 8px">${side.generals.length} general${side.generals.length>1?"s":""} + ${side.retinue} units = ${side.cards} cards · ${fmt(side.men)} men${side.trim?` (${side.trim} trimmed)`:""}</p>
      ${side.generals.map(g=>`<div class="general">
        <p class="gname"><b>${g.role==="Commander"?"Commander":"Knight"}</b> <span>${g.kind==="hero"?"hero":"general with bodyguard"}, ${g.men} ${g.men===1?"man":"men"}, leads ${g.units.length}</span></p>
        <table><tbody>${g.units.map(u=>`<tr><td>${esc(u.name)}${u.proven?"":` <span title="Not yet fought in a CW2 battle" style="color:var(--bone-dim)">*</span>`}</td>
          <td>${esc(u.tier)}</td><td class="num">${u.men}</td></tr>`).join("")}</tbody></table>
      </div>`).join("")}</section>`;
    const prog=S.install.length?`<ul class="progress">${S.install.map(x=>x?`<li data-s="${x.status}"><span class="dot"></span>${esc(x.label)}</li>`:"").join("")}</ul>`:"";
    const probeOk=S.health && S.health.gates && S.health.gates.probe;
    const scale=r.scale>=1?"1 : 1":`1 : ${(1/r.scale).toFixed(1)}`;
    return `<h2>Roll armies</h2>
    <p class="lede">Scale ${scale}, seed <code>${r.seed}</code>. Units are drawn from vanilla Three Kingdoms units; * marks units not yet fought in a CW2 battle.</p>
    <div class="actions" role="group" aria-label="Game mode" style="margin-top:0">
      ${[["records","Records: generals lead bodyguards"],["romance","Romance: generals are heroes"]].map(([m,label])=>
        `<button class="${S.mode===m?"btn-primary":"btn-quiet"}" data-action="setMode" data-mode="${m}" aria-pressed="${S.mode===m}" ${S.installed||S.busy?"disabled":""}>${label}</button>`).join("")}
    </div>
    <div class="cols">${col(r.sides[0])}${col(r.sides[1])}</div>
    <p class="notice" style="margin-top:16px">${esc(r.note)}${S.health&&S.health.probe_installed&&!S.installed?" An earlier battle pack is installed; Prepare replaces it.":""}</p>
    ${prog}
    ${probeOk?"":`<p class="notice" style="margin-top:16px">Three Kingdoms or the RPFM tool is missing; go back to the first step.</p>`}
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}
    <div class="actions">
      ${S.installed
        ? `<button class="btn-primary" data-action="toBattle">Continue to battle</button>`
        : `<button class="btn-primary" data-action="install" ${S.busy||!probeOk?"disabled":""}>Prepare and install</button>
           <button class="btn-quiet" data-action="reroll" ${S.busy?"disabled":""}>Roll again</button>`}
    </div>`;
  },
  battle(){
    const r=S.result;
    const SRC={engine_callback:"engine callback",routing_state:"routing state at the results screen"};
    const res=r?`<p class="notice ${r.player_outcome==="victory"?"ok":""}" style="margin-top:20px">${esc(r.sides[r.player_side].name)}: ${r.player_outcome==="victory"?"victory":"not a victory (loss, draw or withdrawal)"}. Read from the ${esc(SRC[r.result_source]||r.result_source)}. ${esc(r.note)}</p>
    <div class="panel" style="margin-top:12px"><table>
      <thead><tr><th>Side</th><th>Unit</th><th class="num">Men</th><th class="num">Lost</th><th class="num">Survivors</th><th>State</th></tr></thead>
      <tbody>${r.sides.map((s,i)=>s.units.map((u,j)=>`<tr>
        ${j===0?`<td rowspan="${s.units.length}">${esc(s.name)}${r.winner===i?" (won)":""}</td>`:""}
        <td>${esc(u.unit_type)}</td><td class="num">${fmt(u.initial)}</td><td class="num">${fmt(u.lost)}</td>
        <td class="num">${fmt(u.survivors)}</td><td>${u.routing?"routing":"steady"}</td></tr>`).join("")).join("")}</tbody></table></div>`:"";
    return `<h2>Fight in Three Kingdoms</h2>
    <p class="lede">${S.launched
      ? "Three Kingdoms is launching. Enable crusader_wars_2 in the mod manager, open Historical Battles, pick Xingyang in Records mode and fight until one side breaks. Then come back and read the result."
      : "The battle pack is installed. Launch Three Kingdoms, enable crusader_wars_2 in the mod manager, then fight Xingyang in Records mode until one side breaks."}</p>
    <div class="actions">
      ${S.launched?"":`<button class="btn-primary" data-action="launch">Launch Three Kingdoms</button>`}
      ${S.launched&&!r?`<button class="btn-primary" data-action="readResult" ${S.busy?"disabled":""}>Read battle result</button>`:""}
      ${S.installed&&!S.removed?`<button class="btn-quiet" data-action="removeProbe" ${S.busy?"disabled":""}>Remove battle pack</button>`:""}
    </div>${res}
    ${S.removed?`<p class="notice ok" style="margin-top:16px">Battle pack removed. The game's own files were never touched.</p>`:""}
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}`;
  },
  return(){
    const d=S.diff;
    if(!d) return `<h2>Write back to your save</h2>
      ${S.error?`<p class="notice">${esc(S.error)}</p>`:`<p class="lede">Checking write-back...</p>`}
      <p class="lede">Your Three Kingdoms result is saved in the run folder.</p>
      <div class="actions"><button class="btn-primary" data-action="restart">Start a new battle</button></div>`;
    const cas=d.casualties;
    const diff_table=d.changes.length?`<div class="panel" style="margin-top:16px"><table class="diff">
      <thead><tr><th>Path</th><th class="num">Before</th><th class="num">After</th></tr></thead>
      <tbody>${d.changes.map(c=>`<tr><td><code style="font-size:.8rem;color:var(--bone-dim)">${esc(c.path)}</code></td>
        <td class="num before">${fmt(c.before)}</td><td class="num after">${fmt(c.after)}</td></tr>`).join("")}</tbody>
    </table></div>`:"";
    
    return `<h2>Write back to your save</h2>
    <p class="lede">The battle is resolved. These are the casualties calculated from the Three Kingdoms survivors, applied proportionally to the CK3 regiments.</p>
    <div class="cols">
      <section class="panel side">
        <p class="role">Attacker</p>
        <dl class="kv">
          <dt>CK3 Dead</dt><dd class="formula">${fmt(cas.attacker?.dead||0)}</dd>
        </dl>
      </section>
      <section class="panel side">
        <p class="role">Defender</p>
        <dl class="kv">
          <dt>CK3 Dead</dt><dd class="formula">${fmt(cas.defender?.dead||0)}</dd>
        </dl>
      </section>
    </div>
    ${diff_table}
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}
    <div class="actions">
      ${S.sealed
        ? `<button class="btn-primary" data-action="restart">Start a new battle</button>`
        : `<button class="btn-primary" data-action="applyWriteback" ${S.busy?"disabled":""}>Apply to save</button>
           <button class="btn-quiet" data-action="restart" ${S.busy?"disabled":""}>Discard and start over</button>`}
    </div>`;
  }
};

/* ---- actions ---- */
window.cw2.on("install",p=>{S.install[p.index]={label:p.label,status:p.status}; if(STEPS[S.view].id==="roster") render();});

const A={
  async recheck(){S.error=null;
    try{S.health=await call("get_health");
      log(`health probe_ready=${S.health.gates.probe} tk_running=${S.health.tk_running} ck3_running=${S.health.ck3_running}`);}
    catch(e){S.error=err(e);} render();},
  async launchCk3(){
    try{await call("launch_ck3"); log("CK3 launch requested via Steam");}
    catch(e){S.error=err(e);} render();},
  async toEncounter(){go(1); S.enc=null; S.roster=null; render();
    try{S.enc=await call("get_encounter"); log(`CK3 save ${S.enc.save_name}: battle ${S.enc.combat_id} of ${S.enc.battles.length}`);}
    catch(e){S.error=err(e); log(`save error: ${S.error}`);} render();},
  async pickBattle(b){S.error=null;
    try{S.enc=await call("get_encounter",S.enc.save,b.dataset.id); S.roster=null; log(`picked battle ${S.enc.combat_id}`);}
    catch(e){S.error=err(e);} render();},
  async toRoster(){go(2); await A.reroll();},
  async reroll(){S.error=null;
    try{S.roster=await call("roll_roster",S.enc,null,S.mode);
      log(`rolled ${S.roster.mode} seed=${S.roster.seed} cards=${S.roster.sides.map(s=>s.cards).join("v")}`);}
    catch(e){S.error=err(e);} render();},
  async setMode(b){S.mode=b.dataset.mode; await A.reroll();},
  async install(){S.busy=true;S.install=[];S.error=null;render();
    try{const r=await call("prepare_and_install",S.roster); S.installed=true;
      if(r.removed_previous) log(`replaced the previous battle pack (run: ${r.removed_previous})`);
      log(`installed ${r.pack} sha256=${r.sha256}`); log(`run evidence: ${r.run}`);}
    catch(e){S.error=err(e); log(`install error: ${S.error}`);}
    S.busy=false; render();},
  async toBattle(){go(3);},
  async launch(){
    try{await call("launch_3k"); S.launched=true; log("3K launch requested via Steam");}
    catch(e){S.error=err(e);} render();},
  async readResult(){S.busy=true;S.error=null;render();
    try{S.result=await call("read_result");
      log(`result outcome=${S.result.player_outcome} source=${S.result.result_source}`);}
    catch(e){S.error=err(e); log(`result error: ${S.error}`);}
    S.busy=false; render();},
  async removeProbe(){S.busy=true;S.error=null;render();
    try{const r=await call("remove_probe"); S.removed=true;
      log(`removed ${r.removed}${r.run?" (run: "+r.run+")":""}`);
      await A.recheck();}
    catch(e){S.error=err(e); log(`remove error: ${S.error}`);}
    S.busy=false; render();},
  async toReturn(){go(4); S.error=null; S.diff=null; S.busy=true; render();
    try{S.diff=await call("preview_writeback");
        log(`previewed writeback: ${S.diff.changes.length} changes`);}
    catch(e){S.error=err(e); log(`preview error: ${S.error}`);}
    S.busy=false; render();},
  async applyWriteback(){S.busy=true; S.error=null; render();
    try{const r=await call("apply_writeback");
        log(`writeback applied: ${r.after_save}`);
        S.sealed=true;}
    catch(e){S.error=err(e); log(`apply error: ${S.error}`);}
    S.busy=false; render();},
  async restart(){Object.assign(S,{view:0,reached:0,sealed:false,roster:null,enc:null,
      install:[],installed:false,launched:false,removed:false,result:null,diff:null,error:null});
    await A.recheck();}
};

document.addEventListener("click",async ev=>{
  const g=ev.target.closest("[data-go]"); if(g&&!g.disabled){go(+g.dataset.go);return;}
  const b=ev.target.closest("[data-action]"); if(b&&!b.disabled&&A[b.dataset.action]) await A[b.dataset.action](b);
});

window.addEventListener("pywebviewready",()=>{log("Python bridge ready"); render(); A.recheck();});
log("launcher booted; waiting for the Python bridge...");
render();



