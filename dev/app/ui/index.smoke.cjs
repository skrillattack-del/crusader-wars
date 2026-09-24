/* DOM-stub smoke test for dev/app/ui/index.html.
   Loads the real inline script, fakes the pywebview bridge, and drives the
   whole operator flow end to end. Run: node index.smoke.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('no inline script found in index.html');

const els = {};
function el(id) {
  if (!els[id]) els[id] = {innerHTML: '', textContent: '', scrollTop: 0, scrollHeight: 1,
    style: {}, classList: {toggle() {}}, focus() {}, appendChild() {}, addEventListener() {}};
  return els[id];
}
const docHandlers = {};
global.document = {getElementById: el, addEventListener(type, fn) { docHandlers[type] = fn; }};
const winHandlers = {};
global.window = global;
global.addEventListener = (type, fn) => { winHandlers[type] = fn; };

let readAttempts = 0;
let probeInstalled = true;
const caoUnits = () => [
  {kind: 'general', key: '3k_main_general_earth_cao_cao', name: 'Cao Cao (Earth general)'},
  {kind: 'unit', key: '3k_main_unit_wood_ji_militia', name: 'Ji Militia'},
  {kind: 'unit', key: '3k_main_unit_water_archer_militia', name: 'Archer Militia'}];
const liuUnits = () => [
  {kind: 'general', key: '3k_main_general_earth_liu_bei', name: 'Liu Bei (Earth general)'},
  {kind: 'unit', key: '3k_main_unit_wood_ji_militia', name: 'Ji Militia'},
  {kind: 'unit', key: '3k_main_unit_water_archer_militia', name: 'Archer Militia'}];
const unit = (name, type, initial, survivors, routing) =>
  ({script_name: name, unit_type: type, initial, survivors, lost: initial - survivors, routing});
const resultSides = [
  {role: 'attacker', name: 'Cao Cao', men: 300, lost: 150, units: [
    unit('cw2_attacker_0', '3k_main_general_earth_cao_cao', 100, 50, false),
    unit('cw2_attacker_1', '3k_main_unit_wood_ji_militia', 100, 50, false),
    unit('cw2_attacker_2', '3k_main_unit_water_archer_militia', 100, 50, false)]},
  {role: 'defender', name: 'Liu Bei', men: 300, lost: 300, units: [
    unit('cw2_defender_0', '3k_main_general_earth_liu_bei', 100, 0, true),
    unit('cw2_defender_1', '3k_main_unit_wood_ji_militia', 100, 0, true),
    unit('cw2_defender_2', '3k_main_unit_water_archer_militia', 100, 0, true)]}];
const api = {
  async get_health() { return {ok: true, ck3_running: false, tk_running: false, probe_installed: probeInstalled,
    paths: [{key: 'ck3_exe', label: 'Crusader Kings III', value: 'C:/ck3.exe', ok: true},
            {key: 'tk_exe', label: 'Three Kingdoms', value: 'C:/3k.exe', ok: true},
            {key: 'ck3_saves', label: 'CK3 save folder', value: 'C:/saves', ok: true},
            {key: 'rpfm_cli', label: 'RPFM command line', value: 'tools/rpfm/rpfm_cli.exe', ok: true}],
    gates: {probe: true}}; },
  async get_encounter() { return {ok: true, id: 'g1-xinyang-records', location: 'Xingyang',
    mode: 'Records historical battle', note: 'G1 staged probe battle.',
    sides: [{role: 'Attacker', name: 'Cao Cao', cards: 3, retinue: 2, units: caoUnits()},
            {role: 'Defender', name: 'Liu Bei', cards: 3, retinue: 2, units: liuUnits()}]}; },
  async roll_roster() { return {ok: true, seed: null, deterministic: true, note: 'fixed by the probe',
    sides: [{role: 'Attacker', name: 'Cao Cao', retinue: 2, cards: 3,
             generals: [{name: 'Cao Cao', role: 'Commander', prowess: null, retinue: 2, units: caoUnits()}]},
            {role: 'Defender', name: 'Liu Bei', retinue: 2, cards: 3,
             generals: [{name: 'Liu Bei', role: 'Commander', prowess: null, retinue: 2, units: liuUnits()}]}]}; },
  async prepare_and_install() { return {ok: true, pack: 'cw2_g1_probe.pack', sha256: '9f2c', run: 'C:/runs/x'}; },
  async launch_3k() { return {ok: true, pid: null}; },
  async read_result() {
    readAttempts += 1;
    if (readAttempts === 1) return {error: 'Need exactly one start and one result; rebuild for each battle attempt.'};
    return {ok: true, winner: 0, player_side: 0, player_outcome: 'victory', result_source: 'routing_state',
      note: 'derived from unit state at Complete', battle: 'b', run_id: 'r',
      sides: resultSides}; },
  async remove_probe() { probeInstalled = false; return {ok: true, removed: 'cw2_g1_probe.pack', was_installed: true, run: 'C:/runs/orphan'}; },
  async preview_writeback() { return {error: 'CK3 write-back is not integrated into the launcher yet.'}; },
  async apply_writeback() { return {error: 'CK3 write-back is not integrated into the launcher yet.'}; }
};
window.pywebview = {api};
vm.runInThisContext(match[1]);

let passed = 0, failed = 0;
function expect(label, condition, detail) {
  if (condition) { passed += 1; console.log(`ok - ${label}`); }
  else { failed += 1; console.error(`FAIL - ${label}: ${detail || ''}`); }
}
const settle = () => new Promise(resolve => setTimeout(resolve, 10));
async function click(action) {
  docHandlers.click({target: {closest: sel => sel === '[data-go]' ? null
    : (sel === '[data-action]' ? {dataset: {action}, disabled: false} : null)}});
  await settle();
}

(async () => {
  winHandlers.pywebviewready();
  await settle();
  const main = () => els.main.innerHTML;
  expect('setup screen renders after bridge ready', main().includes('Check setup') && main().includes('Continue to the staged battle'));
  await click('toEncounter');
  expect('staged battle shows both commanders', main().includes('Battle of Xingyang') && main().includes('Cao Cao') && main().includes('Liu Bei'));
  await click('toRoster');
  expect('roster screen shows the staged units', main().includes('Prepare the pack') && main().includes('Archer Militia') && main().includes('Prepare and install'));
  expect('stale installed pack blocks prepare but offers removal',
    main().includes('A probe pack from an earlier run is installed') && main().includes('Remove installed probe pack'));
  await click('removeProbe');
  expect('orphaned pack removed, prepare is available again',
    !main().includes('A probe pack from an earlier run is installed') && main().includes('Prepare and install')
    && els.log.textContent.includes('C:/runs/orphan'));
  await click('install');
  expect('install completes and continues to battle', main().includes('Continue to battle') && els.log.textContent.includes('installed cw2_g1_probe.pack'));
  await click('toBattle');
  expect('battle screen prompts the launch', main().includes('Fight in Three Kingdoms') && main().includes('Launch Three Kingdoms'));
  await click('launch');
  expect('after launch the result can be read', main().includes('Read battle result'));
  await click('readResult');
  expect('first read fails with the real strict-reader message', main().includes('Need exactly one start and one result'));
  await click('readResult');
  expect('decisive result renders outcome, source and survivors',
    main().includes('victory') && main().includes('(won)') && main().includes('routing')
    && els.log.textContent.includes('source=routing_state'));
  await click('removeProbe');
  expect('probe removal is confirmed', main().includes('Probe pack removed') && els.log.textContent.includes('removed cw2_g1_probe.pack'));
  await click('restart');
  expect('restart returns to setup', main().includes('Check setup') && !main().includes('Prepare the pack'));
  console.log(`\nsmoke ${passed}/${passed + failed} ok`);
  process.exit(failed ? 1 : 0);
})().catch(error => { console.error('smoke crashed:', error); process.exit(1); });

