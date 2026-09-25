/* Crusader Wars 2 launcher UI. Python side: bridge.py via pywebview js_api.
   Flow: get ready -> choose the CK3 battle -> your armies -> fight in 3K -> result. */
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
/* Plain-language versions of the errors a player can actually hit. */
function friendly(m){
  if(/No runtime log/.test(m)) return "No battle has been fought with this pack yet. Finish the battle in Three Kingdoms, then try again.";
  if(/exactly one start/.test(m)) return "This battle was restarted or replayed, so its result can't be used. Send the armies again and fight it once.";
  if(/undetermined/.test(m)) return "Neither side fully broke, so there's no winner yet. Fight until one army routs.";
  if(/Close Three Kingdoms/.test(m)) return "Close Three Kingdoms first, then try again.";
  if(/No \.ck3 saves/.test(m)) return "No CK3 saves found yet. In CK3, open a battle and press the crossed swords (or save by hand), then try again.";
  if(/no battle in progress/.test(m)) return "Your latest save has no battle in progress. Save while your armies are fighting.";
  return m;
}
const fail = e => { const m = err(e); log(`error: ${m}`); return friendly(m); };

/* ---- state ---- */
const STEPS=[
  {id:"setup",  title:"Get ready"},
  {id:"enc",    title:"Choose battle"},
  {id:"roster", title:"Your armies"},
  {id:"battle", title:"Fight"},
  {id:"result", title:"Result"}
];
const S={view:0, reached:0, sealed:false, busy:false, mode:"records", cw1Hint:false,
  health:null, enc:null, roster:null, install:[], installed:false,
  launched:false, removed:false, result:null, error:null};

function log(msg){const el=document.getElementById("log");
  el.textContent+=`[${new Date().toLocaleTimeString("en-CA",{hour12:false})}] ${msg}\n`;el.scrollTop=el.scrollHeight;}

/* tally gap: closes one notch per finished step */
function setTally(){
  const done=S.sealed?5:S.reached; const g=(5-done)*7;
  document.getElementById("halfL").style.transform=`translateX(${-g}px)`;
  document.getElementById("halfR").style.transform=`translateX(${g}px)`;
  document.getElementById("seal").classList.toggle("on",S.sealed);
  document.getElementById("stepline").innerHTML=`Step <b>${S.view+1}</b> of 5: ${STEPS[S.view].title}`;
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
const errorBox=()=>S.error?`<p class="notice" role="alert" style="margin-top:16px">${esc(S.error)}</p>`:"";
const check=(state,text,fix="")=>`<li><span class="dot ${state}" aria-label="${state==="bad"?"Needs fixing":state==="warn"?"Warning":"Ready"}"></span><span>${text}</span>${fix}</li>`;

/* ---- screens ---- */
const V={
  setup(){
    const h=S.health;
    if(!h) return `<h2>Get ready</h2><p class="lede">Checking your games...</p>`;
    const ok=k=>(h.paths.find(p=>p.key===k)||{}).ok;
    const items=[
      check(ok("ck3_exe")?"":"bad", ok("ck3_exe")?"Crusader Kings III is installed":"Crusader Kings III was not found"),
      check(ok("tk_exe")?"":"bad", ok("tk_exe")?"Three Kingdoms is installed":"Three Kingdoms was not found"),
      !h.ck3_mod
        ? check("bad", "The CW2 battle button is not installed in CK3",
            h.mod_source?`<button class="btn-quiet btn-sm" data-action="installMod" ${S.busy?"disabled":""}>Install</button>`:`<span class="muted">mod files missing</span>`)
        : h.in_playset
          ? check("", "The CW2 battle button is installed and in your CK3 playset")
          : check("bad", "The CW2 battle button is installed but not in your CK3 playset. Close the Paradox launcher, then add it.",
              `<button class="btn-quiet btn-sm" data-action="addToPlayset" ${S.busy?"disabled":""}>Add to playset</button>`),
      h.cw1_installed
        ? check("warn", "Crusader Wars 1 is still installed. It replaces the same CK3 battle window, so the CW2 button won't show while it's on.",
            `<button class="btn-quiet btn-sm" data-action="removeCw1">Remove it</button>`)
        : check("", "Crusader Wars 1 is gone"),
      check(ok("rpfm_cli")?"":"bad", ok("rpfm_cli")?"The battle pack builder is ready":"The battle pack builder (RPFM) is missing")];
    return `<h2>Get ready</h2>
    <p class="lede">Fight your Crusader Kings III battles in Three Kingdoms. Check the list, then start a battle in CK3.</p>
    <ul class="panel checklist">${items.join("")}</ul>
    ${S.cw1Hint?`<p class="notice ok" style="margin-top:16px">Steam is opening Crusader Wars 1's Workshop page. Click <b>Unsubscribe</b> there, then press Check again.</p>`:""}
    ${h.tk_running?`<p class="notice" style="margin-top:16px">Three Kingdoms is running. Close it before sending a battle.</p>`:""}
    <section class="panel" style="margin-top:16px"><h3 class="panel-title">How a battle starts</h3>
      <ol class="howto">
        <li>Get every line above ready. <b>Add to playset</b> puts the CW2 mod last in your active playset for you.</li>
        <li>Play CK3. When your armies meet, open the battle and press the <b>crossed swords</b>. The game pauses and saves.</li>
        <li>Keep this window open: it spots the save, builds both armies and starts Three Kingdoms. To choose by hand, press <b>Find my battle</b>.</li>
      </ol></section>
    ${errorBox()}
    <div class="actions">
      <button class="btn-primary" data-action="toEncounter" ${ok("ck3_saves")?"":"disabled"}>Find my battle</button>
      ${h.ck3_running?"":`<button class="btn-quiet" data-action="launchCk3">Open Crusader Kings III</button>`}
      <button class="btn-quiet" data-action="recheck">Check again</button>
    </div>
    <details class="more"><summary>File locations</summary>
      <div class="paths">${h.paths.map(p=>`<div class="pathrow"><span class="dot ${p.ok?"":"bad"}"></span>
        <span>${esc(p.label)}</span><code title="${esc(p.value)}">${esc(p.value)}</code></div>`).join("")}</div>
    </details>`;
  },
  enc(){
    const e=S.enc;
    if(!e) return `<h2>Choose battle</h2>${S.error?`${errorBox()}
      <div class="actions"><button class="btn-quiet" data-action="toEncounter">Try again</button></div>`
      :`<p class="lede">Reading your latest CK3 save...</p>`}`;
    const side=s=>`<section class="panel side" aria-label="${s.role}">
      <p class="role">${s.role}${s.yours?` <span class="yours">your army</span>`:""}</p>
      <p class="big">${fmt(Math.round(s.fighting))}</p>
      <p class="muted">men still fighting, of ${fmt(Math.round(s.initial))}</p></section>`;
    const cards=e.battles.map(b=>`<li><button data-action="pickBattle" data-id="${esc(b.combat_id)}" aria-pressed="${b.combat_id===e.combat_id}">
      <b>${fmt(b.men[0])} v ${fmt(b.men[1])}</b><small>${esc(b.phase||"")}${b.yours?` · <span class="yours">yours</span>`:""}</small></button></li>`).join("");
    return `<h2>Choose battle</h2>
    <p class="lede">${e.battles.length} battle${e.battles.length===1?"":"s"} in progress in your latest save. Battles with your own army are marked; if you fought through a vassal or ally, pick that one.</p>
    <ul class="battles">${cards}</ul>
    <div class="faceoff">${side(e.sides[0])}<div class="vs" aria-hidden="true">vs</div>${side(e.sides[1])}</div>
    ${errorBox()}
    <div class="actions">
      <button class="btn-primary" data-action="toRoster">Build the armies</button>
      <button class="btn-quiet" data-action="toEncounter">Look again</button>
    </div>
    <details class="more"><summary>Save details</summary>
      <dl class="kv"><dt>Save</dt><dd><code>${esc(e.save_name)}</code></dd><dt>Date</dt><dd>${esc(e.date||"unknown")}</dd>
      <dt>Battle id</dt><dd><code>${esc(e.combat_id)}</code></dd>
      ${e.sides.map(s=>`<dt>${s.role} armies</dt><dd><code>${esc(s.army_ids.join(", "))}</code></dd>`).join("")}</dl>
    </details>`;
  },
  roster(){
    const r=S.roster;
    if(!r) return `<h2>Your armies</h2>${S.error?errorBox():`<p class="lede">Building the armies...</p>`}`;
    const modes=[["records","Records","Generals lead a bodyguard. Grounded, historical battles."],
                 ["romance","Romance","Generals are single heroes who duel and inspire."]];
    const col=side=>`<section class="panel"><h3 class="panel-title">${esc(side.role)}</h3>
      <p class="muted" style="margin:0 0 8px">${fmt(side.men)} men · ${side.cards} unit cards</p>
      ${side.generals.map(g=>`<div class="general">
        <p class="gname"><b>${esc(g.name||(g.role==="Commander"?"Commander":"Knight"))}</b>
          <span>${g.kind==="hero"?"hero":"general and bodyguard"}${g.men>1?`, ${g.men} men`:""}</span></p>
        <ul class="units">${g.units.map(u=>`<li><span>${esc(u.name)}</span><span class="tier-tag">${esc(u.tier)}</span><span class="num">${u.men}</span></li>`).join("")}</ul>
      </div>`).join("")}</section>`;
    const prog=S.install.length?`<ul class="progress">${S.install.map(x=>x?`<li data-s="${x.status}"><span class="dot"></span>${esc(x.label)}</li>`:"").join("")}</ul>`:"";
    const packOk=S.health&&S.health.gates&&S.health.gates.probe;
    return `<h2>Your armies</h2>
    <p class="lede">Both CK3 armies, rebuilt from Three Kingdoms units at the same scale${r.scale<1?` (1 in 3K stands for ${(1/r.scale).toFixed(1)} in CK3)`:" (man for man)"}.</p>
    <div class="seg" role="group" aria-label="Battle mode">${modes.map(([m,t,d])=>
      `<button data-action="setMode" data-mode="${m}" aria-pressed="${S.mode===m}" ${S.installed||S.busy?"disabled":""}><b>${t}</b><small>${d}</small></button>`).join("")}</div>
    <div class="cols">${col(r.sides[0])}${col(r.sides[1])}</div>
    <p class="muted" style="margin-top:14px">${esc(r.note)}</p>
    ${prog}
    ${packOk?"":`<p class="notice" style="margin-top:16px">Three Kingdoms or the battle pack builder is missing. Check the first step.</p>`}
    ${errorBox()}
    <div class="actions">
      ${S.installed
        ? `<button class="btn-primary" data-action="toBattle">Next: fight</button>`
        : `<button class="btn-primary" data-action="install" ${S.busy||!packOk?"disabled":""}>Send to Three Kingdoms</button>
           <button class="btn-quiet" data-action="reroll" ${S.busy?"disabled":""}>Shuffle units</button>`}
    </div>
    <details class="more"><summary>Roll details</summary><p class="muted">Seed <code>${r.seed}</code>, mode ${esc(r.mode||S.mode)}.</p></details>`;
  },
  battle(){
    return `<h2>Fight in Three Kingdoms</h2>
    <p class="lede">The battle is ready. Follow these steps, then come back for the result.</p>
    <ol class="howto panel">
      <li>${S.launched?"Three Kingdoms is starting with only the <b>crusader_wars_2</b> battle pack on.":`<button class="btn-quiet btn-sm" data-action="launch">Launch Three Kingdoms</button>`}</li>
      <li>Open <b>Historical Battles</b>, choose <b>Battle of Xingyang</b> in Records mode, and start it.</li>
      <li>Fight until one army breaks. Stay on the results screen for a few seconds, and don't press Rematch.</li>
    </ol>
    ${errorBox()}
    <div class="actions">
      <button class="btn-primary" data-action="readResult" ${S.busy?"disabled":""}>Get the result</button>
    </div>`;
  },
  result(){
    const r=S.result;
    if(!r) return `<h2>Result</h2><p class="lede">No result yet.</p>
      <div class="actions"><button class="btn-primary" data-action="toBattle">Back to the fight</button></div>`;
    const won=r.player_outcome==="victory";
    const rows=r.sides.map((s,i)=>`<tr><td>${esc(s.role)}${i===r.player_side?" (you)":""}${r.winner===i?" · won":""}</td>
      <td class="num">${fmt(s.men)}</td><td class="num">${fmt(s.lost)}</td><td class="num">${fmt(s.men-s.lost)}</td></tr>`).join("");
    return `<h2>Result</h2>
    <p class="banner ${won?"win":"loss"}">${won?"Victory":"Defeat"}<small>${won?"Your side held the field.":"Your side broke first."}</small></p>
    <div class="panel"><table>
      <thead><tr><th>Side</th><th class="num">Fought</th><th class="num">Lost</th><th class="num">Left</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="muted" style="margin-top:14px">The result is saved in the run folder. Writing the losses into your CK3 save is off in this build.</p>
    ${S.removed?`<p class="notice ok" style="margin-top:16px">Battle pack removed. The game's own files were never touched.</p>`:""}
    ${errorBox()}
    <div class="actions">
      <button class="btn-primary" data-action="restart">Fight another battle</button>
      ${S.installed&&!S.removed?`<button class="btn-quiet" data-action="removeProbe" ${S.busy?"disabled":""}>Remove battle pack</button>`:""}
    </div>`;
  }
};

/* ---- actions ---- */
window.cw2.on("install",p=>{S.install[p.index]={label:p.label,status:p.status}; if(STEPS[S.view].id==="roster") render();});

const A={
  async recheck(){S.error=null;
    try{S.health=await call("get_health");
      log(`checked: ck3_mod=${S.health.ck3_mod} cw1=${S.health.cw1_installed} pack_ready=${S.health.gates.probe}`);}
    catch(e){S.error=fail(e);} render();},
  async installMod(){S.busy=true; S.error=null; render();
    try{const r=await call("install_ck3_mod"); log(`CK3 mod registered: ${r.mod_file}`); await A.recheck();}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async addToPlayset(){S.busy=true; S.error=null; render();
    try{const r=await call("add_to_playset");
      log(`added to playset "${r.playset}"${r.cw1_disabled?", Crusader Wars 1 switched off":""}; backup: ${r.backup}`);
      await A.recheck();}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async removeCw1(){S.error=null;
    try{await call("open_cw1_page"); S.cw1Hint=true; log("opened Crusader Wars 1's Workshop page");}
    catch(e){S.error=fail(e);} render();},
  async launchCk3(){
    try{await call("launch_ck3"); log("CK3 launch requested via Steam");}
    catch(e){S.error=fail(e);} render();},
  async toEncounter(_,save=null){go(1); S.enc=null; S.roster=null; render();
    try{S.enc=await call("get_encounter",save); log(`CK3 save ${S.enc.save_name}: battle ${S.enc.combat_id} of ${S.enc.battles.length}`);}
    catch(e){S.error=fail(e);} render();},
  async pickBattle(b){S.error=null;
    try{S.enc=await call("get_encounter",S.enc.save,b.dataset.id); S.roster=null; log(`picked battle ${S.enc.combat_id}`);}
    catch(e){S.error=fail(e);} render();},
  async toRoster(){go(2); await A.reroll();},
  async reroll(){S.error=null;
    try{S.roster=await call("roll_roster",S.enc,null,S.mode);
      log(`rolled ${S.roster.mode} seed=${S.roster.seed} cards=${S.roster.sides.map(s=>s.cards).join("v")}`);}
    catch(e){S.error=fail(e);} render();},
  async setMode(b){S.mode=b.dataset.mode; await A.reroll();},
  async install(){S.busy=true;S.install=[];S.error=null;render();
    try{const r=await call("prepare_and_install",S.roster); S.installed=true;
      if(r.removed_previous) log(`replaced the previous battle pack (run: ${r.removed_previous})`);
      log(`installed ${r.pack} sha256=${r.sha256}`); log(`run folder: ${r.run}`);}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async toBattle(){go(3);},
  async launch(){
    try{await call("launch_3k"); S.launched=true; log("3K launch requested via Steam");}
    catch(e){S.error=fail(e);} render();},
  async readResult(){S.busy=true;S.error=null;render();
    try{S.result=await call("read_result");
      log(`result outcome=${S.result.player_outcome} source=${S.result.result_source}`);
      S.busy=false; go(4); return;}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async removeProbe(){S.busy=true;S.error=null;render();
    try{const r=await call("remove_probe"); S.removed=true;
      log(`removed ${r.removed}${r.run?" (run: "+r.run+")":""}`);
      await A.recheck();}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async restart(){Object.assign(S,{view:0,reached:0,sealed:false,roster:null,enc:null,cw1Hint:false,
      install:[],installed:false,launched:false,removed:false,result:null,error:null});
    await A.recheck();},
  /* The CK3 button saved a battle: take it straight to Three Kingdoms, stopping at the first error. */
  async autoFight(sig){log(`CK3 battle button: ${sig.battle} (${sig.save_name})`);
    await A.toEncounter(null,sig.save); if(!S.enc) return;
    await A.toRoster(); if(!S.roster) return;
    await A.install(); if(!S.installed) return;
    go(3); await A.launch();}
};

let watching=false;
async function watch(){
  if(watching||S.busy||S.view!==0) return;
  watching=true;
  try{const sig=await call("poll_battle"); if(sig.save&&!S.busy&&S.view===0) await A.autoFight(sig);}
  catch(e){log(`watch: ${err(e)}`);}
  watching=false;
}

document.addEventListener("click",async ev=>{
  const g=ev.target.closest("[data-go]"); if(g&&!g.disabled){go(+g.dataset.go);return;}
  const b=ev.target.closest("[data-action]"); if(b&&!b.disabled&&A[b.dataset.action]) await A[b.dataset.action](b);
});

window.addEventListener("pywebviewready",()=>{log("Python bridge ready"); render(); A.recheck(); setInterval(watch,3000);});
log("launcher started; waiting for the Python bridge...");
render();
