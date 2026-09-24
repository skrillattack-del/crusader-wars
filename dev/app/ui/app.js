/* ============================================================
   CW2 launcher, G1 scope. The screens are the V1 mockup's; the
   bridge is the real Python side (pywebview js_api -> bridge.py).
   Integrated: pack build/install, 3K launch, strict result read,
   probe removal. Not integrated (honest errors on screen): CK3
   encounter extraction, roster roll, CK3 write-back.
   ============================================================ */
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
  {id:"setup",   title:"Check setup"},
  {id:"enc",     title:"Review staged battle"},
  {id:"roster",  title:"Prepare the pack"},
  {id:"battle",  title:"Fight in 3K"},
  {id:"return",  title:"Write back"}
];
const S={view:0, reached:0, sealed:false, busy:false,
  health:null, enc:null, roster:null, install:[], installed:false,
  launched:false, removed:false, result:null, diff:null, error:null};

function log(msg){const el=document.getElementById("log");
  el.textContent+=`[${new Date().toLocaleTimeString("en-CA",{hour12:false})}] ${msg}\n`;el.scrollTop=el.scrollHeight;}

/* tally gap: 5 finished steps closes it; seal only after write-back (not integrated yet) */
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
    if(!h) return `<h2>Check setup</h2><p class="lede">Checking game paths and tools...</p>`;
    const probeOk=h.gates && h.gates.probe;
    return `<h2>Check setup</h2>
    <p class="lede">The G1 probe needs your Three Kingdoms install and the RPFM command-line tool. CK3 paths are checked now because write-back will need them later.</p>
    <div class="panel paths">${h.paths.map(p=>`
      <div class="pathrow"><span class="dot ${p.ok?"":"bad"}" aria-label="${p.ok?"Found":"Missing"}"></span>
        <span>${esc(p.label)}</span><code title="${esc(p.value)}">${esc(p.value)}</code></div>`).join("")}
    </div>
    <div class="stack" style="margin-top:16px">
      ${h.tk_running
        ? `<p class="notice">Three Kingdoms is running. Close it before preparing or removing the probe pack.</p>`
        : `<p class="notice ok">Three Kingdoms is closed. Pack operations are available.</p>`}
      ${h.ck3_running
        ? `<p class="notice">Crusader Kings III is running. Informational only: write-back is not integrated yet.</p>`
        : ``}
    </div>
    <div class="actions">
      <button class="btn-primary" data-action="toEncounter" ${probeOk?"":"disabled"}>Continue to the staged battle</button>
      <button class="btn-quiet" data-action="recheck">Check again</button>
    </div>`;
  },
  enc(){
    const e=S.enc; if(!e) return `<h2>Review staged battle</h2><p class="lede">Reading the staged probe battle...</p>`;
    const side=s=>`<section class="panel side" aria-label="${s.role}">
      <p class="role">${s.role}</p><h3>${esc(s.name)}</h3>
      <dl class="kv" style="margin-top:12px">
        <dt>Commander</dt><dd>${esc(s.name)} (Earth general)</dd>
        ${s.units.map(u=>`<dt>${u.kind==="general"?"General":"Unit"}</dt>
          <dd>${esc(u.name)} <code style="font-size:.75rem">${esc(u.key)}</code></dd>`).join("")}
        <dt>3K army</dt><dd><b>1</b> general + <b>${s.cards-1}</b> units = ${s.cards} cards</dd>
      </dl></section>`;
    return `<h2>Battle of ${esc(e.location)}</h2>
    <p class="lede">${esc(e.mode)}. ${esc(e.note)}</p>
    <div class="faceoff">${side(e.sides[0])}<div class="vs" aria-hidden="true">vs</div>${side(e.sides[1])}</div>
    <div class="actions"><button class="btn-primary" data-action="toRoster">Review the staged roster</button></div>`;
  },
  roster(){
    const r=S.roster, e=S.enc; if(!r) return `<h2>Prepare the pack</h2><p class="lede">Loading the staged roster...</p>`;
    const col=(enc,side)=>`<section class="panel"><h3 style="font-family:var(--display);font-weight:400;margin:0">${esc(side.name)}</h3>
      <p style="color:var(--bone-dim);margin:2px 0 8px">${side.generals.length} general + ${side.retinue} units = ${side.cards} cards</p>
      ${side.generals.map(g=>`<div class="general">
        <p class="gname"><b>${esc(g.name)}</b> <span>${esc(g.role)}, leads ${g.retinue}</span></p>
        <table><tbody>${g.units.map(u=>`<tr><td>${esc(u.name)}</td><td>${u.kind}</td><td class="num">1</td></tr>`).join("")}</tbody></table>
      </div>`).join("")}</section>`;
    const prog=S.install.length?`<ul class="progress">${S.install.map(x=>`<li data-s="${x.status}"><span class="dot"></span>${esc(x.label)}</li>`).join("")}</ul>`:"";
    const stale=S.health && S.health.probe_installed && !S.installed;
    return `<h2>Prepare the pack</h2>
    <p class="lede">${esc(r.note)} The pack replaces only the Records version of Xingyang; original CA packs are never modified.</p>
    <div class="cols">${col(e,r.sides[0])}${col(e,r.sides[1])}</div>
    ${prog}
    ${stale?`<p class="notice" style="margin-top:16px">A probe pack from an earlier run is installed. Remove it before preparing a fresh one.</p>`:""}
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}
    <div class="actions">
      ${S.installed
        ? `<button class="btn-primary" data-action="toBattle">Continue to battle</button>`
        : `<button class="btn-primary" data-action="install" ${S.busy?"disabled":""}>Prepare and install</button>`}
      ${stale?`<button class="btn-quiet" data-action="removeProbe" ${S.busy?"disabled":""}>Remove installed probe pack</button>`:""}
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
      ? "Three Kingdoms is launching. Enable cw2_g1_probe in its mod manager, select Historical Battles - Xingyang in Records mode, and fight to a decisive finish (fully rout the enemy). Come back once the results screen has appeared."
      : "The probe pack is installed. Launch Three Kingdoms, enable cw2_g1_probe in the mod manager, then fight the Records Xingyang battle to a decisive finish."}</p>
    <div class="actions">
      ${S.launched?"":`<button class="btn-primary" data-action="launch">Launch Three Kingdoms</button>`}
      ${S.launched&&!r?`<button class="btn-primary" data-action="readResult" ${S.busy?"disabled":""}>Read battle result</button>`:""}
      ${S.installed&&!S.removed?`<button class="btn-quiet" data-action="removeProbe" ${S.busy?"disabled":""}>Remove probe pack</button>`:""}
    </div>${res}
    ${S.removed?`<p class="notice ok" style="margin-top:16px">Probe pack removed. Original CA packs were never modified.</p>`:""}
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}`;
  },
  return(){
    return `<h2>Write back to your save</h2>
    <p class="lede">CK3 write-back is not integrated into the launcher yet. The verified battle result is preserved as <code>observed_result.json</code> in the run folder; the G2 spike applies save changes from a separate pre-integration tool. The tally seal waits for the write-back step.</p>
    ${S.error?`<p class="notice" style="margin-top:16px">${esc(S.error)}</p>`:""}
    <div class="actions"><button class="btn-quiet" data-action="restart">Start over</button></div>`;
  }
};

/* ---- actions ---- */
window.cw2.on("install",p=>{S.install[p.index]={label:p.label,status:p.status}; if(STEPS[S.view].id==="roster") render();});

const A={
  async recheck(){S.error=null;
    try{S.health=await call("get_health");
      log(`health probe_ready=${S.health.gates.probe} tk_running=${S.health.tk_running} ck3_running=${S.health.ck3_running}`);}
    catch(e){S.error=err(e);} render();},
  async toEncounter(){go(1);
    try{S.enc=await call("get_encounter"); log(`staged battle ${S.enc.id}`);}
    catch(e){S.error=err(e);} render();},
  async toRoster(){go(2);
    try{S.roster=await call("roll_roster",S.enc,null); log("staged roster loaded (fixed by the probe)");}
    catch(e){S.error=err(e);} render();},
  async install(){S.busy=true;S.install=[];S.error=null;render();
    try{const r=await call("prepare_and_install",S.roster); S.installed=true;
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
  async toReturn(){go(4);
    try{await call("preview_writeback");}
    catch(e){S.error=err(e);} render();},
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



