/* DOM-stub smoke test for dev/app/ui/index.html.
   Loads the real inline script, fakes the pywebview bridge, and drives the
   whole operator flow end to end, CK3 first. Run: node index.smoke.cjs */
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
    style: {}, classList: {toggle() {}, contains() { return true; }}, focus() {}, appendChild() {}, addEventListener() {}};
  return els[id];
}
const docHandlers = {};
global.document = {getElementById: el, addEventListener(type, fn) { docHandlers[type] = fn; }};
const winHandlers = {};
global.window = global;
global.addEventListener = (type, fn) => { winHandlers[type] = fn; };

let readAttempts = 0, seed = 1702900, ck3Launches = 0, lastMode = null;
const side = (role, fighting, initial, armies, yours) => ({role, name: `${role} · army ${armies}`,
  army_ids: [armies], fighting, initial, yours});
const battles = {
  '1728053261': [side('Attacker', 666.2, 700, '111', true), side('Defender', 19.4, 60, '222', false)],
  '2717908992': [side('Attacker', 340.09632, 571, '570426519', false), side('Defender', 421.48395, 528, '503317436', false)]};
const encounter = id => ({ok: true, id: `ck3:${id}`, combat_id: id, save: 'C:/saves/CW2_G2_BEFORE.ck3',
  save_name: 'CW2_G2_BEFORE.ck3', date: '908.8.27', phase: 'main', yours: battles[id][0].yours,
  battles: [{combat_id: '1728053261', yours: true, phase: 'main', men: [666, 19]},
            {combat_id: '2717908992', yours: false, phase: 'main', men: [340, 421]}],
  sides: battles[id]});
const u = (name, tier, men, proven) => ({key: `3k_main_unit_${name}`, name, tier, men, proven});
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
  async get_health() { return {ok: true, ck3_running: false, tk_running: false, probe_installed: true,
    paths: [{key: 'ck3_exe', label: 'Crusader Kings III', value: 'C:/ck3.exe', ok: true},
            {key: 'tk_exe', label: 'Three Kingdoms', value: 'C:/3k.exe', ok: true},
            {key: 'ck3_saves', label: 'CK3 save folder', value: 'C:/saves', ok: true},
            {key: 'rpfm_cli', label: 'RPFM command line', value: 'tools/rpfm/rpfm_cli.exe', ok: true}],
    gates: {ck3: true, probe: true}}; },
  async launch_ck3() { ck3Launches += 1; return {ok: true}; },
  async get_encounter(save, id) { return encounter(id || '1728053261'); },
  async roll_roster(enc, s, mode) { seed += 1; lastMode = mode; const hero = mode === 'romance';
    return {ok: true, seed, mode, deterministic: false, scale: 1,
    note: 'Prepare and install still stages the proven probe roster.' + (hero ? ' Romance staging is untested.' : ''),
    sides: [{role: 'Attacker', fighting: 340.09, men: 340, trim: 1, cards: 5, retinue: 4, generals: [
              {key: 'g', role: 'Commander', kind: hero ? 'hero' : 'bodyguard', men: hero ? 1 : 21,
               units: [u('Jian Swordguards', 'line', 80, false),
                u('Ji Militia', 'militia', 80, true), u('Raider Cavalry', 'line', 80, false), u('Axe Band', 'militia', 79, false)]}]},
            {role: 'Defender', fighting: 421.48, men: 421, trim: 0, cards: 6, retinue: 5, generals: [
              {key: 'g', role: 'Commander', men: 21, units: [u('Pearl Dragons', 'elite', 80, false),
                u('Archer Militia', 'militia', 80, true), u('Ji Militia', 'militia', 80, true),
                u('Spear Warriors', 'militia', 80, false), u('Sabre Cavalry', 'line', 80, false)]}]}]}; },
  async prepare_and_install() { return {ok: true, pack: 'cw2_g1_probe.pack', sha256: '9f2c', run: 'C:/runs/x',
    removed_previous: 'C:/dist/runs/20260923-175132-201712'}; },
  async launch_3k() { return {ok: true, pid: null}; },
  async read_result() {
    readAttempts += 1;
    if (readAttempts === 1) return {error: 'Need exactly one start and one result; rebuild for each battle attempt.'};
    return {ok: true, winner: 0, player_side: 0, player_outcome: 'victory', result_source: 'routing_state',
      note: 'derived from unit state at Complete', battle: 'b', run_id: 'r', sides: resultSides}; },
  async remove_probe() { return {ok: true, removed: 'cw2_g1_probe.pack', was_installed: true, run: 'C:/runs/x'}; },
  async preview_writeback() {
    return {error: 'CK3 write-back is disabled until G2 reload persistence is verified.'};
  },
  async apply_writeback() { return {error: 'CK3 write-back is disabled.'}; }
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
  const log = () => els.log.textContent;
  expect('CK3 is the starting point', main().includes('Start in Crusader Kings III')
    && main().includes('Load my latest CK3 save') && main().includes('Open Crusader Kings III'));
  await click('launchCk3');
  expect('CK3 can be opened from the launcher', ck3Launches === 1 && log().includes('CK3 launch requested'));
  await click('toEncounter');
  expect('latest save lists its battles and marks yours', main().includes('Pick the CK3 battle')
    && main().includes('CW2_G2_BEFORE.ck3') && main().includes('666 v 19 · yours') && main().includes('340 v 421'));
  await click('pickBattle', {id: '2717908992'});
  expect('picking a battle shows its fighting men', main().includes('421 fighting men') && main().includes('503317436'));
  await click('toRoster');
  const firstSeed = seed;
  expect('roll shows cards, men and vanilla units', main().includes('Roll armies') && main().includes('Pearl Dragons')
    && main().includes('5 cards') && main().includes('(1 trimmed)') && main().includes(`seed <code>${firstSeed}</code>`));
  expect('roll is honest about what gets staged', main().includes('proven probe roster')
    && main().includes('Prepare removes it first'));
  await click('reroll');
  expect('roll again draws a new seed', seed === firstSeed + 1 && main().includes(`seed <code>${seed}</code>`));
  expect('Records mode is the default', lastMode === 'records' && main().includes('general with bodyguard, 21 men'));
  await click('setMode', {mode: 'romance'});
  expect('Romance mode re-rolls with hero generals', lastMode === 'romance' && main().includes('hero, 1 man')
    && main().includes('Romance staging is untested') && log().includes('rolled romance'));
  await click('setMode', {mode: 'records'});
  await click('install');
  expect('install removes the recorded previous pack automatically', main().includes('Continue to battle')
    && log().includes('removed the previous probe pack') && log().includes('installed cw2_g1_probe.pack'));
  await click('toBattle');
  expect('battle screen prompts the launch', main().includes('Fight in Three Kingdoms') && main().includes('Launch Three Kingdoms'));
  await click('launch');
  expect('after launch the result can be read', main().includes('Read battle result'));
  await click('readResult');
  expect('first read fails with the real strict-reader message', main().includes('Need exactly one start and one result'));
  await click('readResult');
  expect('decisive result renders outcome, source and survivors',
    main().includes('victory') && main().includes('(won)') && main().includes('routing') && log().includes('source=routing_state'));
  await click('removeProbe');
  expect('probe removal is confirmed', main().includes('Probe pack removed') && log().includes('removed cw2_g1_probe.pack'));
  await click('toReturn');
  expect('writeback gate explains why CK3 mutation is disabled', main().includes('write-back is disabled') && main().includes('reload and time-advance'));
  expect('writeback gate does not claim the result is sealed', !document.getElementById('stepline').innerHTML.includes('Sealed.'));
  await click('restart');
  expect('restart returns to CK3', main().includes('Start in Crusader Kings III') && !main().includes('Roll armies'));
  console.log(`\nsmoke ${passed}/${passed + failed} ok`);
  process.exit(failed ? 1 : 0);
})().catch(error => { console.error('smoke crashed:', error); process.exit(1); });
