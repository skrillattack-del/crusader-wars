/* DOM-stub smoke test for dev/app/ui/index.html.
   Loads the real inline script, fakes the pywebview bridge, and drives the
   whole player flow end to end. Run: node index.smoke.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('no inline script found in index.html');

const els = {};
function el(id) {
  if (!els[id]) {
    const classes = new Set();
    els[id] = {innerHTML: '', textContent: '', scrollTop: 0, scrollHeight: 1,
      style: {}, value: '', checked: false, dataset: {}, attrs: {},
      setAttribute(k, v) { this.attrs[k] = String(v); },
      classList: {add(c) {classes.add(c);}, remove(c) {classes.delete(c);},
        toggle(c, force) {const on = force === undefined ? !classes.has(c) : !!force;
          on ? classes.add(c) : classes.delete(c);},
        contains(c) {return classes.has(c);}},
      focus() {}, appendChild() {}, addEventListener() {}};
  }
  return els[id];
}
const docHandlers = {};
global.document = {getElementById: el, documentElement: {dataset: {skin: 'ck3'}},
  addEventListener(type, fn) { docHandlers[type] = fn; }};
el('halfL').dataset.skin = 'ck3';   // the header plaques carry the look they select
el('halfR').dataset.skin = '3k';
const winHandlers = {};
global.window = global;
global.addEventListener = (type, fn) => { winHandlers[type] = fn; };

/* Controllable timers: the UI arms watch() (3000 ms) on the setup step and the
   auto-battle-report poll (4000 ms) on the fight step; the harness fires them
   by hand instead of waiting real seconds. */
const timers = {};
global.setInterval = (fn, ms) => { const id = {fn, ms}; timers[ms] = id; return id; };
global.clearInterval = id => { for (const k of Object.keys(timers)) if (timers[k] === id) delete timers[k]; };
const tick = ms => { const t = timers[ms]; return t ? t.fn() : null; };

let readAttempts = 0, seed = 1702900, ck3Launches = 0, lastMode = null, modInstalled = false, cw1Pages = 0, inPlayset = false;
let signal = null, tkLaunches = 0, lastSave, savedSkin = '3k';
let configDoc = {show_mode: 'tactical', army_scale_factor: 1.0, auto_battle_report: true,
  enable_tw3k_screenshots: false, domain_focus: 'custom', injectivity_strict: true, cut_3d_voice: true};
const side = (role, fighting, initial, armies, yours) => ({role, name: `${role} · army ${armies}`,
  army_ids: [armies], fighting, initial, yours});
const battles = {
  '1728053261': [side('Attacker', 666.2, 700, '111', true), side('Defender', 19.4, 60, '222', false)],
  '2717908992': [side('Attacker', 340.09632, 571, '570426519', false), side('Defender', 421.48395, 528, '503317436', false)]};
const encounter = id => ({ok: true, id: `ck3:${id}`, combat_id: id, save: 'C:/saves/latest.ck3',
  save_name: 'latest.ck3', date: '908.8.27', phase: 'main', yours: battles[id][0].yours,
  battles: [{combat_id: '1728053261', yours: true, phase: 'main', men: [666, 19]},
            {combat_id: '2717908992', yours: false, phase: 'main', men: [340, 421]}],
  sides: battles[id]});
const u = (name, tier, men) => ({key: `3k_main_unit_${name}`, name, tier, men, proven: false});
const general = (hero, units) => ({key: 'g', role: 'Commander', name: 'Captain 1', kind: hero ? 'hero' : 'bodyguard',
  men: hero ? 1 : 21, units});
const api = {
  async get_health() { return {ok: true, ck3_running: false, tk_running: false, probe_installed: true,
    ck3_mod: modInstalled, in_playset: inPlayset, mod_source: true, cw1_installed: true,
    config: {path: 'C:/config/cw2_config.json', sha256: 'x', valid: true, error: null, slots_violations: []},
    paths: [{key: 'ck3_exe', label: 'Crusader Kings III', value: 'C:/ck3.exe', ok: true},
            {key: 'tk_exe', label: 'Three Kingdoms', value: 'C:/3k.exe', ok: true},
            {key: 'ck3_saves', label: 'CK3 save folder', value: 'C:/saves', ok: true},
            {key: 'rpfm_cli', label: 'RPFM command line', value: 'tools/rpfm/rpfm_cli.exe', ok: true}],
    gates: {ck3: true, probe: true}}; },
  async get_config() { return {ok: true, config: configDoc, path: 'C:/config/cw2_config.json', sha256: 'x', slots_ok: true}; },
  async save_config(patch) {
    if (patch.army_scale_factor !== undefined && !(patch.army_scale_factor > 0))
      return {error: 'Invalid config: $.army_scale_factor must be above 0'};
    configDoc = {...configDoc, ...patch};
    return {ok: true, config: configDoc, path: 'C:/config/cw2_config.json', sha256: 'x'}; },
  async get_skin() { return {ok: true, skin: savedSkin, skins: ['ck3', '3k']}; },
  async set_skin(skin) { savedSkin = skin; return {ok: true, skin}; },
  async install_ck3_mod() { modInstalled = true; return {ok: true, mod_file: 'C:/mod/cw2_ck3_bridge.mod'}; },
  async add_to_playset() { inPlayset = true; return {ok: true, playset: 'Initial playset', cw1_disabled: 1, backup: 'C:/dist/backups/x.sqlite'}; },
  async open_cw1_page() { cw1Pages += 1; return {ok: true}; },
  async launch_ck3() { ck3Launches += 1; return {ok: true}; },
  async get_encounter(save, id) { lastSave = save; return encounter(id || '1728053261'); },
  async roll_roster(enc, s, mode) { seed += 1; lastMode = mode; const hero = mode === 'romance';
    return {ok: true, seed, mode, deterministic: false, scale: 1,
      note: 'Three Kingdoms fights exactly this roll on the Records Xingyang map.' + (hero ? ' Romance battles are not staged yet.' : ''),
      applied: {army_scale_factor: 1, domain_focus: 'custom', show_mode: configDoc.show_mode},
      sides: [{role: 'Attacker', fighting: 340.09, men: 340, trim: 1, cards: 5, retinue: 4, generals: [general(hero,
                [u('Jian Swordguards', 'line', 80), u('Ji Militia', 'militia', 80), u('Raider Cavalry', 'line', 80), u('Axe Band', 'militia', 79)])]},
              {role: 'Defender', fighting: 421.48, men: 421, trim: 0, cards: 6, retinue: 5, generals: [general(hero,
                [u('Pearl Dragons', 'elite', 80), u('Archer Militia', 'militia', 80), u('Ji Militia', 'militia', 80),
                 u('Spear Warriors', 'militia', 80), u('Sabre Cavalry', 'line', 80)])]}]}; },
  async prepare_and_install() { return {ok: true, pack: 'crusader_wars_2.pack', sha256: '9f2c', run: 'C:/runs/x',
    removed_previous: 'C:/dist/runs/old'}; },
  async launch_3k() { tkLaunches += 1; return {ok: true, pid: null}; },
  async poll_battle() { const s = signal; signal = null; return s || {ok: true, save: null}; },
  async read_result() {
    readAttempts += 1;
    if (readAttempts === 1) return {error: 'No runtime log yet. The probe has not demonstrated that it loaded.'};
    return {ok: true, winner: 0, player_side: 0, player_outcome: 'victory', result_source: 'routing_state',
      note: 'derived from unit state', battle: 'Hastings', run_id: 'r',
      sides: [{role: 'attacker', name: 'Cao Cao', men: 181, lost: 18, units: []},
              {role: 'defender', name: 'Liu Bei', men: 181, lost: 113, units: []}]}; },
  async remove_probe() { return {ok: true, removed: 'crusader_wars_2.pack', was_installed: true, run: 'C:/runs/x'}; }
};
window.pywebview = {api};
vm.runInThisContext(match[1]);

let passed = 0, failed = 0;
function expect(label, condition, detail) {
  if (condition) { passed += 1; console.log(`ok - ${label}`); }
  else { failed += 1; console.error(`FAIL - ${label}: ${detail || ''}`); }
}
const settle = () => new Promise(resolve => setTimeout(resolve, 10));
async function click(action, data = {}) {
  docHandlers.click({target: {closest: sel => sel === '[data-go]' ? null
    : (sel === '[data-action]' ? {dataset: {action, ...data}, disabled: false} : null)}});
  await settle();
}

(async () => {
  winHandlers.pywebviewready();
  await settle();
  const main = () => els.main.innerHTML;
  expect('the remembered look is applied at startup', document.documentElement.dataset.skin === '3k'
    && els.halfR.attrs['aria-pressed'] === 'true' && els.halfL.attrs['aria-pressed'] === 'false');
  await click('setSkin', {skin: 'ck3'});
  expect('a header plaque switches the look and the bridge remembers it', document.documentElement.dataset.skin === 'ck3'
    && savedSkin === 'ck3' && els.halfL.attrs['aria-pressed'] === 'true' && els.halfR.attrs['aria-pressed'] === 'false');
  const log = () => els.log.textContent;
  expect('first screen is a plain checklist', main().includes('Get ready') && main().includes('Crusader Kings III is installed')
    && main().includes('Find my battle'));
  expect('missing CK3 mod offers Install', main().includes('The CW2 battle button is not installed in CK3') && main().includes('data-action="installMod"'));
  expect('Crusader Wars 1 is flagged with a Remove button', main().includes('Crusader Wars 1 is still installed') && main().includes('data-action="removeCw1"'));
  expect('file paths are tucked away', main().includes('<details class="more"><summary>File locations</summary>'));
  expect('the options ledger is listed with its effective values', main().includes('Options ledger')
    && main().includes('show_mode tactical') && main().includes('domain custom'));
  await click('openSettings');
  expect('options panel opens with the ledger values', els['settings-overlay'].classList.contains('open')
    && els['settings-body'].innerHTML.includes('Army scale') && els['settings-body'].innerHTML.includes('aria-pressed="true">custom<'));
  expect('the reserved cut_3d_voice key gets no row', !els['settings-body'].innerHTML.includes('cut_3d_voice'));
  els['set-army_scale_factor'] = el('set-army_scale_factor');
  els['set-army_scale_factor'].value = '2';
  el('set-auto_battle_report').checked = true;         // mirrors the rendered checked attributes
  el('set-enable_tw3k_screenshots').checked = false;
  el('set-injectivity_strict').checked = true;
  await click('optSeg', {key: 'domain_focus', value: 'shu'});
  expect('segmented controls update and keep the typed scale', els['settings-body'].innerHTML.includes('aria-pressed="true">shu<')
    && String(els['set-army_scale_factor'].value) === '2');
  await click('saveSettings');
  expect('saving closes the panel and updates the ledger', !els['settings-overlay'].classList.contains('open')
    && configDoc.army_scale_factor === 2 && configDoc.domain_focus === 'shu' && log().includes('options saved'));
  await click('openSettings');
  els['set-army_scale_factor'].value = '0';
  await click('saveSettings');
  expect('a rejected value stays open with its error', els['settings-overlay'].classList.contains('open')
    && els['settings-status'].textContent.includes('army_scale_factor') && configDoc.army_scale_factor === 2);
  await click('closeSettings');
  expect('cancel closes without saving', !els['settings-overlay'].classList.contains('open'));
  configDoc.army_scale_factor = 1; configDoc.domain_focus = 'custom';
  await click('installMod');
  expect('Install registers the CK3 mod, then offers Add to playset', main().includes('not in your CK3 playset') && main().includes('data-action="addToPlayset"') && log().includes('CK3 mod registered'));
  await click('addToPlayset');
  expect('Add to playset finishes the CK3 setup', main().includes('installed and in your CK3 playset') && log().includes('added to playset "Initial playset"'));
  await click('removeCw1');
  expect('Remove opens the Workshop page with an Unsubscribe hint', cw1Pages === 1 && main().includes('Unsubscribe'));
  await click('launchCk3');
  expect('CK3 can be opened from the launcher', ck3Launches === 1);
  await click('toEncounter');
  expect('battles show as cards, yours marked', main().includes('Choose battle') && main().includes('666 v 19')
    && main().includes('<span class="yours">yours</span>') && main().includes('340 v 421'));
  await click('pickBattle', {id: '2717908992'});
  expect('picked battle shows men still fighting', main().includes('421') && main().includes('men still fighting'));
  await click('toRoster');
  const firstSeed = seed;
  expect('armies list units and men', main().includes('Your armies') && main().includes('Pearl Dragons') && main().includes('340 men · 5 unit cards'));
  expect('the roster names the ledger values it rolled with', main().includes('Options ledger: army scale ×1, domain custom'));
  expect('Records is the default mode', lastMode === 'records' && main().includes('general and bodyguard, 21 men'));
  await click('setMode', {mode: 'romance'});
  expect('Romance shows hero generals', lastMode === 'romance' && main().includes('<span>hero</span>') && main().includes('Romance battles are not staged yet'));
  await click('setMode', {mode: 'records'});
  await click('reroll');
  expect('Shuffle draws new units', seed === firstSeed + 3);
  await click('install');
  expect('Send to Three Kingdoms installs the pack', main().includes('Next: fight') && log().includes('installed crusader_wars_2.pack')
    && log().includes('replaced the previous battle pack'));
  await click('toBattle');
  expect('fight screen is a step-by-step checklist', main().includes('lobby by itself') && main().includes('FIGHT') && main().includes('Battle of Xingyang') && main().includes('Launch Three Kingdoms') && main().includes('Get the result'));
  expect('auto battle report arms a poll on the fight step', !!timers[4000]);
  await click('launch');
  expect('after launch the checklist says so', main().includes('Three Kingdoms is starting') && main().includes('crusader_wars_2'));
  await click('readResult');
  expect('no battle yet reads as plain language', main().includes('No battle has been fought with this pack yet'));
  await click('readResult');
  expect('result screen shows a victory banner and losses', main().includes('banner win') && main().includes('Victory')
    && main().includes('(you)') && main().includes('113'));
  configDoc.show_mode = 'minimal'; await click('recheck');
  expect('minimal show mode collapses the result to a summary', main().includes('banner win')
    && !main().includes('<th>Side</th>') && main().includes('fought,'));
  configDoc.show_mode = 'dramatic'; await click('recheck');
  expect('dramatic show mode names the CK3 battle', main().includes('held the field at Hastings'));
  configDoc.show_mode = 'tactical'; await click('recheck');
  expect('tactical show mode restores the full table', main().includes('<th>Side</th>'));
  await click('removeProbe');
  expect('pack removal is confirmed', main().includes('Battle pack removed') && log().includes('removed crusader_wars_2.pack'));
  await click('restart');
  expect('Fight another battle returns to Get ready', main().includes('Get ready') && !main().includes('Your armies'));
  const signal_save = 'C:/saves/King_Matuxia_of_Badajoz_911_09_02.ck3';
  signal = {ok: true, save: signal_save, save_name: 'King_Matuxia_of_Badajoz_911_09_02.ck3', battle: 'Battle of Muluya'};
  const launchesBefore = tkLaunches;
  await watch();
  await settle();
  expect('the CK3 button save goes straight to Three Kingdoms', tkLaunches === launchesBefore + 1 && lastSave === signal_save
    && main().includes('Three Kingdoms is starting') && log().includes('CK3 battle button: Battle of Muluya'));
  expect('auto battle report is armed after the auto-fight', !!timers[4000]);
  tick(4000); await settle();
  expect('auto battle report advances to the result by itself', main().includes('Victory')
    && log().includes('result arrived on its own'));
  console.log(`\nsmoke ${passed}/${passed + failed} ok`);
  process.exit(failed ? 1 : 0);
})().catch(error => { console.error('smoke crashed:', error); process.exit(1); });
