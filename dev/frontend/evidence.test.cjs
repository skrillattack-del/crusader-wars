const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { parse3KLog, parseG2Plan } = require('./evidence.js');

const evidencePath = path.join(__dirname, '..', 'spikes', 'g1_3k_io', 'evidence', 'frozen_records_run.jsonl');
const archivedLog = fs.readFileSync(evidencePath, 'utf8');

test('archived G1 run keeps its actual counts without inventing a winner', () => {
  const report = parse3KLog(archivedLog);
  assert.equal(report.phase, 'complete');
  assert.equal(report.resultCallbackPresent, false);
  assert.equal(report.outcome, 'unavailable');
  assert.deepEqual(report.totals, {
    attacker: { initial: 181, survivors: 143 },
    defender: { initial: 181, survivors: 106 },
  });
  assert.equal(report.units.length, 6);
});

test('a matching result callback reports only the callback outcome', () => {
  const events = archivedLog.trim().split('\n').map(JSON.parse);
  events.push({ ...events.at(-1), phase: 'result', player_won: true });
  const report = parse3KLog(events.map(JSON.stringify).join('\n'));
  assert.equal(report.outcome, 'player victory');
  assert.equal(report.resultCallbackPresent, true);
});

test('G1 rejects a replay and a changed unit identity', () => {
  const events = archivedLog.trim().split('\n').map(JSON.parse);
  assert.throws(() => parse3KLog([...events, ...events].map(JSON.stringify).join('\n')), /replayed runs/);
  events.at(-1).units[0].unit_type = 'unexpected';
  assert.throws(() => parse3KLog(events.map(JSON.stringify).join('\n')), /identity/);
});

test('a G2 plan is displayed as synthetic, not a completed write-back', () => {
  const plan = {
    schema: 1,
    kind: 'synthetic_g2_plan_not_applied',
    status: 'prepared_not_applied',
    battle_id: '2717908992',
    save_fingerprint: 'a'.repeat(64),
    result_id: 'b'.repeat(64),
    outcome: 'attacker',
    outcome_source: 'synthetic_not_3k_callback',
    sides: {
      attacker: { army_ids: ['570426519'], initial_men: '571', total_fighting_men: '340.09632', synthetic_casualties: 38 },
      defender: { army_ids: ['503317436'], initial_men: '528', total_fighting_men: '421.48395', synthetic_casualties: 75 },
    },
  };
  const report = parseG2Plan(JSON.stringify(plan));
  assert.equal(report.sides.attacker.loss, 38);
  assert.equal(report.sides.defender.loss, 75);
  assert.equal(report.outcome, 'attacker');
  assert.throws(() => parseG2Plan(JSON.stringify({ ...plan, kind: 'unbound_synthetic_fixture_not_applicable' })), /not a prepared/);
  assert.throws(() => parseG2Plan(JSON.stringify({ ...plan, sides: { ...plan.sides, defender: { ...plan.sides.defender, synthetic_casualties: 500 } } })), /strengths or casualties/);
});