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
  if(/Loaded roster differs/.test(m)) return "Three Kingdoms loaded different units than expected. This usually means it was already running when the armies were sent. Close Three Kingdoms, go back to step 3, press \"Send to Three Kingdoms\" again, then re-launch.";
  if(/refused to close/.test(m)) return "Three Kingdoms refused to close. Please close it manually before continuing.";
  if(/already running/.test(m)) return "Three Kingdoms is already running. Close it first so it picks up the new battle pack.";
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
  launched:false, removed:false, result:null, error:null, packMismatch:false, returnedToCk3:false, ck3Continue:null,
  config:null, configPath:null, configSha:null,
  stage:null, sideOpen:null, watchResult:null, tkRunning:null, launchedAt:null};

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

/* launcher look: the header plaques switch it; the bridge remembers it */
function applySkin(skin){
  document.documentElement.dataset.skin=skin;
  for(const id of ["halfL","halfR"]){const b=document.getElementById(id);
    b.setAttribute("aria-pressed",String(b.dataset.skin===skin));}
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
function go(i){S.view=i; S.reached=Math.max(S.reached,i); S.error=null; render(); document.getElementById("main").focus(); armResultWatch();}

/* auto_battle_report: on the Fight step, poll the 3K battle log and advance by
   ourselves; off (or no ledger), the player presses Get the result. */
let resultTimer=null, liveTimer=null, liveTicks=0;
const watchOn=()=>S.watchResult!=null?S.watchResult:!!(S.config&&S.config.auto_battle_report===true);
function armResultWatch(){
  clearInterval(resultTimer); resultTimer=null;
  clearInterval(liveTimer); liveTimer=null;
  if(STEPS[S.view].id!=="battle"||!S.launched) return;
  liveTimer=setInterval(liveTick,1000);
  if(watchOn()) resultTimer=setInterval(pollResult,4000);
}
const elapsed=()=>{const s=Math.max(0,Math.floor((Date.now()-(S.launchedAt||Date.now()))/1000));
  return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;};
/* Every second: the clock. Every fifth: is Three Kingdoms still running? */
async function liveTick(){
  const clock=document.getElementById("fight-clock");
  if(clock) clock.textContent=elapsed();
  if(++liveTicks%5) return;
  try{const h=await call("get_health");
    if(h.tk_running!==S.tkRunning){S.tkRunning=h.tk_running;
      log(`Three Kingdoms ${h.tk_running?"is running":"is not running"}`);
      if(STEPS[S.view].id==="battle"&&!S.busy) render();}}
  catch(e){/* status only; the next tick retries */}
}
/* After launch: watch for the end of the battle. Once Three Kingdoms leaves its results
   screen (or closes), read the result, close 3K and start CK3 again. */
async function pollResult(){
  if(S.busy||STEPS[S.view].id!=="battle") return;
  let status;
  try{status=await call("battle_status");}catch(e){return;}
  if(!status.battle_over) return;
  clearInterval(resultTimer); resultTimer=null;
  try{S.result=await call("read_result");
    log(`battle over: outcome=${S.result.player_outcome}`);}
  catch(e){S.error=fail(e); render(); return;}
  go(4);
  await A.returnCk3();
}
const errorBox=()=>S.error?`<p class="notice" role="alert" style="margin-top:16px">${esc(S.error)}</p>`:"";
const check=(state,text,fix="")=>`<li><span class="dot ${state}" aria-label="${state==="bad"?"Needs fixing":state==="warn"?"Warning":"Ready"}"></span><span>${text}</span>${fix}</li>`;
const flowGlyph=kind=>({
  pack:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9Z"/><path d="m4.5 7.7 7.5 4.2 7.5-4.2M12 12v9M8 5.2l8 4.5"/></svg>`,
  play:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z"/></svg>`,
  swords:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2M14.5 6.5 18 3h3v3l-3.5 3.5M9 18l-4-4M7 17l-3 3M3 19l2 2"/></svg>`,
  file:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h5M9 12h6M9 16h6"/></svg>`,
  back:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 8 4 13l5 5"/><path d="M5 13h8a6 6 0 0 1 6 6M19 5v6"/></svg>`,
  eye:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>`,
  list:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>`,
  check:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 12 4 4 8-9"/></svg>`,
  x:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg>`
}[kind]||"");
const statusMark=state=>`<span class="fight-status-mark">${state==="done"?flowGlyph("check"):state==="error"?flowGlyph("x"):""}</span>`;
const FIGHT_STAGES=[["pack","Build pack","Prepare battle data"],["play","Launch 3K","Start the game"],
  ["swords","Fight battle","You play in 3K"],["file","Read result","Detect outcome"],["back","Return to CK3","Sync the result"]];
const fightStates=()=>[S.installed?"done":"current", S.launched?"done":S.installed?"current":"pending",
  S.launched?"current":"pending", S.launched&&S.busy?"current":"pending", "pending"];

/* The CK3 matchup: both sides as buttons that open their army, over a strength bar. */
function matchup(){
  const r=S.roster; if(!r||!r.sides||r.sides.length!==2) return "";
  const total=r.sides.reduce((n,s)=>n+(s.men||0),0)||1;
  const side=(s,i)=>`<button class="fm-side ${i?"d":"a"}" data-action="toggleSide" data-side="${i}" aria-expanded="${S.sideOpen===i}">
    <span class="fm-role">${esc(s.role)}${s.yours?" · your army":""}</span>
    <span class="fm-name">${esc(s.commander&&s.commander.name||s.name||s.role)}</span>
    <span class="fm-men">${fmt(s.men)} men · ${s.cards} unit cards</span></button>`;
  const open=S.sideOpen!=null?r.sides[S.sideOpen]:null;
  let units="";
  if(open){
    const kinds=new Map();
    for(const g of open.generals||[]) for(const u of g.units||[]){
      const k=kinds.get(u.name)||{cards:0,men:0}; k.cards+=1; k.men+=u.men; kinds.set(u.name,k);}
    units=`<ul class="fm-units" aria-label="${esc(open.role)} army">${(open.generals||[]).map(g=>
      `<li class="gen"><span>${esc(g.name||"General")} <small>${g.kind==="hero"?"hero":"general"}</small></span><span class="num">${fmt(g.men)}</span></li>`).join("")}${
      [...kinds].map(([n,k])=>`<li><span>${esc(n)}${k.cards>1?` ×${k.cards}`:""}</span><span class="num">${fmt(k.men)}</span></li>`).join("")}</ul>`;
  }
  return `<div class="fight-matchup">
    ${r.battle?`<p class="fm-title">${esc(r.battle)}${r.date?` · ${esc(r.date)}`:""}${r.season?` · ${esc(r.season)}`:""}</p>`:""}
    ${side(r.sides[0],0)}<span class="fm-vs" aria-hidden="true">vs</span>${side(r.sides[1],1)}
    <div class="fm-bar" role="img" aria-label="Strength ${fmt(r.sides[0].men)} against ${fmt(r.sides[1].men)}"><span style="width:${((r.sides[0].men||0)/total*100).toFixed(1)}%"></span></div>
    ${units}</div>`;
}

/* The panel under the stage tracker: what the selected stage is doing and what you can do there. */
function stageDetail(i,name,mode){
  const r=S.roster||{}, watching=watchOn();
  const btn=(action,label,off=false)=>`<button class="btn-quiet btn-sm" data-action="${action}" ${S.busy||off?"disabled":""}>${label}</button>`;
  const [title,body,actions]=[
    ["Battle pack", `<b>${name}</b>, ${mode} mode, seed ${esc(r.seed??"-")}: ${(r.sides||[]).map(s=>`${fmt(s.men)} men`).join(" against ")} staged in <b>crusader_wars_2</b>.`,
      btn("viewArmies","View armies")],
    ["Launch Three Kingdoms", !S.launched?`One click starts Three Kingdoms with only the battle pack.${S.roster&&S.roster.battle?" CK3 closes first; its battle save is already on disk.":""}`
      :S.tkRunning===false?"Three Kingdoms is not running. Relaunch it to fight this battle."
      :S.tkRunning?"Three Kingdoms is running with the battle pack.":"Launch requested through Steam.",
      S.launched?btn("resendAndRelaunch","Resend and relaunch"):btn("launch","Launch")],
    ["Fight the battle", `<b>In Three Kingdoms:</b> the CRUSADER WARS II lobby opens by itself. Review both armies and press <b>FIGHT</b>. Fight until one army breaks, stay on the results screen for a few seconds, and don't press Rematch.<br>If the lobby doesn't open: <b>Battle › Historical Battle › ${name}</b> (it replaces Xingyang; Romance box ${mode==="Romance"?"ticked":"<b>unticked</b>"}) <b>› Start</b>.`, ""],
    ["Read the result", watching?"CW2 checks for the result every few seconds and moves on by itself.":"Press Check now once the results screen shows in Three Kingdoms.",
      `<button class="switch" data-action="toggleAutoWatch" aria-pressed="${watching}">Watch automatically</button>${btn("readResult","Check now",!S.launched)}`],
    ["Return to CK3", watching?"When you leave the Three Kingdoms results screen, CW2 reads the result, closes Three Kingdoms and starts CK3. Press Continue in CK3 to resume."
      :"After the result is read, Return to CK3 closes Three Kingdoms and starts CK3 on your save.", ""]][i];
  return `<div class="fight-detail" aria-live="polite"><div><h3>${title}</h3><p>${body}</p></div>${actions?`<div class="fight-detail-actions">${actions}</div>`:""}</div>`;
}

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
    <ul class="panel checklist art">${items.join("")}</ul>
    ${h.config&&!h.config.valid?`<p class="notice" role="alert" style="margin-top:16px">The options ledger is invalid: ${esc(h.config.error||"unknown error")}. Defaults are in use.</p>`:""}
    ${S.cw1Hint?`<p class="notice ok" style="margin-top:16px">Steam is opening Crusader Wars 1's Workshop page. Click <b>Unsubscribe</b> there, then press Check again.</p>`:""}
    ${h.tk_running?`<p class="notice" style="margin-top:16px">Three Kingdoms is running. Close it before sending a battle.</p>`:""}
    <section class="panel parchment" style="margin-top:16px"><h3 class="panel-title">How a battle starts</h3>
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
        <span>${esc(p.label)}</span><code title="${esc(p.value)}">${esc(p.value)}</code></div>`).join("")}
      ${S.config?`<div class="pathrow"><span class="dot"></span><span>Options ledger</span>
        <code title="${esc(S.configPath||"")}">${esc(`show_mode ${S.config.show_mode} · scale ×${S.config.army_scale_factor} · domain ${S.config.domain_focus} · auto-report ${S.config.auto_battle_report?"on":"off"}`)}</code></div>`:""}
      </div>
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
    <p class="lede">${r.battle?`<b>${esc(r.battle)}</b>: both`:"Both"} CK3 armies, rebuilt from Three Kingdoms units at the same scale${r.scale<1?` (1 in 3K stands for ${(1/r.scale).toFixed(1)} in CK3)`:" (man for man)"}.</p>
    <div class="seg" role="group" aria-label="Battle mode">${modes.map(([m,t,d])=>
      `<button data-action="setMode" data-mode="${m}" aria-pressed="${S.mode===m}" ${S.installed||S.busy?"disabled":""}><b>${t}</b><small>${d}</small></button>`).join("")}</div>
    <div class="cols">${col(r.sides[0])}${col(r.sides[1])}</div>
    <p class="muted" style="margin-top:14px">${esc(r.note)}</p>
    ${r.applied?`<p class="muted" style="margin-top:8px">Options ledger: army scale ×${r.applied.army_scale_factor}, domain ${esc(r.applied.domain_focus)}.</p>`:""}
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
    const packWarn=S.packMismatch?`<p class="notice" role="alert" style="margin-top:16px">The installed battle pack doesn't match this run. <button class="btn-quiet btn-sm" data-action="resendAndRelaunch" ${S.busy?"disabled":""}>Resend and relaunch</button></p>`:"";
    const mode=S.roster&&S.roster.mode==="romance"?"Romance":"Records";
    const name=esc(S.roster&&S.roster.battle||"CK3 battle");
    const auto=watchOn();
    const states=fightStates();
    const launchState=states[1];
    const waitState=S.error?"error":S.launched?"current":"pending";
    const selected=S.stage??Math.max(0,states.indexOf("current"));
    const primary=!S.launched
      ?`<button class="btn-primary" data-action="launch" ${S.busy?"disabled":""}>${flowGlyph("play")}<span>Launch battle</span></button>`
      :`<button class="btn-primary" data-action="readResult" ${S.busy?"disabled":""}>${flowGlyph("file")}<span>${S.busy?"Reading result…":"Check for result"}</span></button>`;
    return `<section class="fight-screen" aria-labelledby="fight-title">
    <h2 id="fight-title">Launch and fight in Three Kingdoms</h2>
    <p class="lede">CW2 has prepared this battle. Launch Three Kingdoms, fight, and the launcher will bring the outcome home.</p>
    ${matchup()}
    <div class="fight-stage">
      <ol class="fight-flow" aria-label="Battle round trip">${FIGHT_STAGES.map(([icon,title,copy],i)=>`<li class="${states[i]}">
        <button data-action="pickStage" data-stage="${i}" aria-pressed="${selected===i}"><span class="fight-flow-icon">${flowGlyph(icon)}</span><strong>${title}</strong><small>${copy}</small></button></li>`).join("")}</ol>
      ${stageDetail(selected,name,mode)}
      <ul class="fight-status" aria-label="Launch status">
        <li class="done">${statusMark("done")}<span class="fight-status-copy"><strong>Battle pack ready</strong><small>Armies, generals and battle data prepared.</small></span><span class="fight-status-state">Ready</span></li>
        <li class="done">${statusMark("done")}<span class="fight-status-copy"><strong>Three Kingdoms profile armed</strong><small>CW2 will start with only its battle pack enabled.</small></span><span class="fight-status-state">Ready</span></li>
        <li class="${S.launched&&S.tkRunning===false?"error":launchState}">${statusMark(S.launched&&S.tkRunning===false?"error":launchState)}<span class="fight-status-copy"><strong>${S.launched?"Three Kingdoms launched":"Three Kingdoms ready to launch"}</strong><small>${!S.launched?"One click starts the staged battle.":S.tkRunning===false?"Three Kingdoms is not running. Relaunch it from the Launch 3K stage.":"The CRUSADER WARS II lobby opens on the main menu; press FIGHT there."}</small></span><span class="fight-status-state">${!S.launched?"Ready":S.tkRunning===false?"Not running":S.tkRunning?"Running":"Started"}</span></li>
        <li class="${waitState}">${statusMark(waitState)}<span class="fight-status-copy"><strong>Waiting for battle result</strong><small>${S.error?"The result was not ready; keep fighting or use the recovery action below.":S.launched?`${auto?"CW2 is watching the battle automatically":"Finish the battle, then check for the result"} · <span id="fight-clock">${elapsed()}</span> since launch`:"Begins after Three Kingdoms launches."}</small></span><span class="fight-status-state">${S.error?"Needs attention":S.launched?(auto?"Watching":"Waiting"):"Pending"}</span></li>
      </ul>
    </div>
    <div class="fight-actions">${primary}
      <button class="btn-quiet" data-action="toggleBattleGuide" aria-expanded="${selected===2}">${flowGlyph("eye")}<span>Battle instructions</span></button>
      <button class="btn-quiet" data-action="openLogs">${flowGlyph("list")}<span>Open logs</span></button>
    </div>
    ${packWarn}
    ${errorBox()}
    ${S.error&&/roster differs|already running/i.test(S.error)?`<div class="actions"><button class="btn-quiet" data-action="resendAndRelaunch" ${S.busy?"disabled":""}>Resend and relaunch</button></div>`:""}
    </section>`;
  },
  result(){
    const r=S.result;
    if(!r) return `<h2>Result</h2><p class="lede">No result yet.</p>
      <div class="actions"><button class="btn-primary" data-action="toBattle">Back to the fight</button></div>`;
    const won=r.player_outcome==="victory";
    const mode=S.config?S.config.show_mode:"tactical";
    const battle=r.battle||"the battle";
    const sub=mode==="dramatic"
      ?`${won?`Your side held the field at ${battle}.`:`Your side broke at ${battle}.`}`
      :(won?"Your side held the field.":"Your side broke first.");
    if(mode==="minimal")
      return `<h2>Result</h2>
      <p class="banner ${won?"win":"loss"}">${won?"Victory":"Defeat"}<small>${esc(sub)}</small></p>
      <p class="muted">${r.sides.map(s=>`${esc(s.role)}: ${fmt(s.men)} fought, ${fmt(s.lost)} lost.`).join(" ")}</p>
      <p class="muted">The result is saved in the run folder. Writing the losses into your CK3 save is off in this build.</p>
      ${S.removed?`<p class="notice ok" style="margin-top:16px">Battle pack removed. The game's own files were never touched.</p>`:""}
      ${S.returnedToCk3?`<p class="notice ok" style="margin-top:16px">Three Kingdoms is closed and CK3 is starting. In CK3, press <b>Continue</b>${S.ck3Continue&&S.ck3Continue.desc?` — <i>${esc(S.ck3Continue.desc)}</i>`:""} to go back to your save.</p>`:""}
      ${errorBox()}
      <div class="actions">
        <button class="btn-primary" data-action="returnCk3" ${S.busy?"disabled":""}>Return to CK3</button>
        <button class="btn-quiet" data-action="restart">Fight another battle</button>
        ${S.installed&&!S.removed?`<button class="btn-quiet" data-action="removeProbe" ${S.busy?"disabled":""}>Remove battle pack</button>`:""}
      </div>`;
    const rows=r.sides.map((s,i)=>`<tr><td>${esc(s.role)}${i===r.player_side?" (you)":""}${r.winner===i?" · won":""}</td>
      <td class="num">${fmt(s.men)}</td><td class="num">${fmt(s.lost)}</td><td class="num">${fmt(s.men-s.lost)}</td></tr>`).join("");
    return `<h2>Result</h2>
    <p class="banner ${won?"win":"loss"}">${won?"Victory":"Defeat"}<small>${esc(sub)}</small></p>
    <div class="panel"><table>
      <thead><tr><th>Side</th><th class="num">Fought</th><th class="num">Lost</th><th class="num">Left</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="muted" style="margin-top:14px">The result is saved in the run folder. Writing the losses into your CK3 save is off in this build.</p>
    ${S.removed?`<p class="notice ok" style="margin-top:16px">Battle pack removed. The game's own files were never touched.</p>`:""}
    ${S.returnedToCk3?`<p class="notice ok" style="margin-top:16px">Three Kingdoms is closed and CK3 is starting. In CK3, press <b>Continue</b>${S.ck3Continue&&S.ck3Continue.desc?` — <i>${esc(S.ck3Continue.desc)}</i>`:""} to go back to your save.</p>`:""}
    ${errorBox()}
    <div class="actions">
      <button class="btn-primary" data-action="returnCk3" ${S.busy?"disabled":""}>Return to CK3</button>
      <button class="btn-quiet" data-action="restart">Fight another battle</button>
      ${S.installed&&!S.removed?`<button class="btn-quiet" data-action="removeProbe" ${S.busy?"disabled":""}>Remove battle pack</button>`:""}
    </div>`;
  }
};

/* ---- options panel: edits the ledger through bridge.get_config/save_config ----
   One row per ledger key; cut_3d_voice is formally UNDEFINED (canon, turn-2 §4)
   and deliberately has no row. */
const OPT_FIELDS=[
  {key:"show_mode", label:"Presentation", kind:"seg", options:["dramatic","tactical","minimal"],
   desc:"How the result reads: dramatic adds the CK3 battle name, tactical shows the full table, minimal one line."},
  {key:"army_scale_factor", label:"Army scale", kind:"number",
   desc:"Multiplies both CK3 armies before staging; Three Kingdoms army caps still apply. Above 0, up to 10."},
  {key:"domain_focus", label:"Domain", kind:"seg", options:["wei","shu","wu","custom"],
   desc:"Faction focus for unit rolls: the other factions' unique units drop out. Custom keeps the whole pool."},
  {key:"auto_battle_report", label:"Automatic battle report", kind:"toggle",
   desc:"After the fight, advance to the result by yourself instead of waiting for the button."},
  {key:"enable_tw3k_screenshots", label:"Three Kingdoms screenshots", kind:"toggle",
   desc:"Request battle screenshots into the run folder. Only the request is recorded today; no capture backend yet."},
  {key:"injectivity_strict", label:"Strict unit mapping", kind:"toggle",
   desc:"Treat a non-injective config/slots.registry.json as an error instead of a warning."},
];
let settingsDraft=null;

function settingsOverlay(){return document.getElementById("settings-overlay");}

function setSettingsStatus(message, isErr){
  const el=document.getElementById("settings-status");
  el.textContent=message||"";
  el.classList.toggle("err", !!isErr);
}

/* Read the free-form controls (number, toggles) into the draft; segmented
   buttons write the draft directly. */
function collectSettings(){
  if(!settingsDraft) return;
  const num=document.getElementById("set-army_scale_factor");
  if(num){
    const raw=String(num.value).trim();
    settingsDraft.army_scale_factor=raw===""?null:Number(raw);
  }
  for(const f of OPT_FIELDS) if(f.kind==="toggle")
    settingsDraft[f.key]=!!document.getElementById("set-"+f.key).checked;
}

function renderSettingsBody(){
  document.getElementById("settings-body").innerHTML=OPT_FIELDS.map(f=>{
    const v=settingsDraft[f.key];
    const control=f.kind==="seg"
      ?`<div class="seg-sm">${f.options.map(o=>
          `<button data-action="optSeg" data-key="${f.key}" data-value="${o}" aria-pressed="${v===o}">${o}</button>`).join("")}</div>`
      :f.kind==="number"
      ?`<div class="num-row"><input id="set-${f.key}" type="number" min="0.1" max="10" step="0.1" value="${v}"></div>`
      :`<div class="toggle-row"><span class="toggle-chip"><input id="set-${f.key}" type="checkbox" ${v?"checked":""}><span class="track"></span><span class="thumb"></span></span></div>`;
    return `<div class="sfield"><span class="sfield-label">${f.label}</span>${control}<span class="sfield-desc">${f.desc}</span></div>`;
  }).join("");
}

window.cw2.on("install",p=>{S.install[p.index]={label:p.label,status:p.status}; if(STEPS[S.view].id==="roster") render();});

const A={
  async recheck(){S.error=null;
    try{S.health=await call("get_health");
      const c=await call("get_config");
      S.config=c.config; S.configPath=c.path; S.configSha=c.sha256;
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
  async openSettings(){
    setSettingsStatus("", false);
    try{
      const r=await call("get_config");
      if(!r.config||!Object.keys(r.config).length){
        settingsDraft=null;
        document.getElementById("settings-body").innerHTML=
          `<p class="notice" role="alert">The options ledger is not available (${esc(r.path||"not found")}). Fix it on disk and press Check again.</p>`;
      }else{
        settingsDraft=Object.fromEntries(OPT_FIELDS.map(f=>[f.key, r.config[f.key]]));
        renderSettingsBody();
      }
      settingsOverlay().classList.add("open");
      log(`options opened (ledger: ${r.path})`);
    }catch(e){S.error=fail(e); render();}
  },
  closeSettings(){settingsOverlay().classList.remove("open");},
  async setSkin(b){applySkin(b.dataset.skin);
    try{await call("set_skin",b.dataset.skin); log(`look: ${b.dataset.skin}`);}
    catch(e){log(`look not saved: ${err(e)}`);}},
  async saveSettings(){
    if(!settingsDraft) return;
    collectSettings();
    try{
      const r=await call("save_config", settingsDraft);
      S.config=r.config; S.configPath=r.path; S.configSha=r.sha256;
      log(`options saved: sha256=${r.sha256}`);
      A.closeSettings(); render(); armResultWatch();
    }catch(e){setSettingsStatus(err(e), true);}
  },
  optSeg(b){collectSettings(); settingsDraft[b.dataset.key]=b.dataset.value; renderSettingsBody();},
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
  async toBattle(){S.packMismatch=false;
    try{const v=await call("verify_pack"); if(v.match===false){S.packMismatch=true; log(`pack check: ${v.reason}`);}
    }catch(e){log(`pack check skipped: ${err(e)}`);}
    go(3);},
  async launch(){
    S.busy=true; S.error=null; render();
    try{const r=await call("launch_3k", !!(S.roster&&S.roster.battle));
      Object.assign(S,{launched:true,launchedAt:Date.now(),tkRunning:null,stage:null});
      log(r.ck3_closed?"CK3 closed after its battle save; Three Kingdoms is starting":"Three Kingdoms is starting");}
    catch(e){S.error=fail(e);}
    S.busy=false; render(); armResultWatch();},
  toggleBattleGuide(){S.stage=S.stage===2?null:2; render();},
  pickStage(b){S.stage=+b.dataset.stage; render();},
  toggleSide(b){const i=+b.dataset.side; S.sideOpen=S.sideOpen===i?null:i; render();},
  viewArmies(){go(2);},
  toggleAutoWatch(){S.watchResult=!watchOn(); log(`result watch ${S.watchResult?"on":"off"}`); render(); armResultWatch();},
  openLogs(){const drawer=document.getElementById("activity-drawer"); drawer.open=true; drawer.scrollIntoView({block:"end",behavior:"smooth"});},
  async readResult(){S.busy=true;S.error=null;render();
    try{S.result=await call("read_result");
      log(`result outcome=${S.result.player_outcome} source=${S.result.result_source}`);
      S.busy=false; go(4); return;}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async returnCk3(){S.busy=true;S.error=null;render();
    try{const r=await call("return_to_ck3"); S.returnedToCk3=true; S.ck3Continue=r.continue||null;
      log(`returned to CK3: ${r.note}${S.ck3Continue&&S.ck3Continue.desc?` — continue "${S.ck3Continue.desc}"`:""}`);}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async removeProbe(){S.busy=true;S.error=null;render();
    try{const r=await call("remove_probe"); S.removed=true;
      log(`removed ${r.removed}${r.run?" (run: "+r.run+")":""}`);
      await A.recheck();}
    catch(e){S.error=fail(e);}
    S.busy=false; render();},
  async restart(){clearInterval(resultTimer); resultTimer=null; clearInterval(liveTimer); liveTimer=null;
    Object.assign(S,{view:0,reached:0,sealed:false,roster:null,enc:null,cw1Hint:false,
      install:[],installed:false,launched:false,removed:false,result:null,error:null,packMismatch:false,returnedToCk3:false,ck3Continue:null,
      stage:null,sideOpen:null,watchResult:null,tkRunning:null,launchedAt:null});
    await A.recheck();},
  /* The CK3 button saved a battle: take it straight to Three Kingdoms, stopping at the first error. */
  async autoFight(sig){log(`CK3 battle button: ${sig.battle} (${sig.save_name})`);
    await A.toEncounter(null,sig.save); if(!S.enc) return;
    await A.toRoster(); if(!S.roster) return;
    await A.install(); if(!S.installed) return;
    go(3); await A.launch();},
  /* Recovery: resend the current roster and relaunch 3K in one click. */
  async resendAndRelaunch(){S.busy=true;S.error=null;S.packMismatch=false;render();
    log("resend: removing old pack, reinstalling, relaunching");
    try{await call("remove_probe");}catch(e){log(`resend remove: ${err(e)}`);}
    try{const r=await call("prepare_and_install",S.roster); S.installed=true;
      log(`resend installed ${r.pack} sha256=${r.sha256}`);}
    catch(e){S.error=fail(e); S.busy=false; render(); return;}
    S.launched=false;
    try{await call("launch_3k"); Object.assign(S,{launched:true,launchedAt:Date.now(),tkRunning:null}); log("resend: 3K relaunched");}
    catch(e){S.error=fail(e);}
    S.busy=false; render(); armResultWatch();}
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
  if(ev.target&&ev.target.id==="settings-overlay"){await A.closeSettings(); return;}
  const g=ev.target.closest("[data-go]"); if(g&&!g.disabled){go(+g.dataset.go);return;}
  const b=ev.target.closest("[data-action]"); if(b&&!b.disabled&&A[b.dataset.action]) await A[b.dataset.action](b);
});
document.addEventListener("keydown",ev=>{
  if(ev.key==="Escape"&&settingsOverlay().classList.contains("open")) A.closeSettings();
});

window.addEventListener("pywebviewready",async ()=>{log("Python bridge ready");
  try{applySkin((await call("get_skin")).skin);}catch(e){log(`look: ${err(e)}`);}
  render(); A.recheck(); setInterval(watch,3000);});
log("launcher started; waiting for the Python bridge...");
render();
