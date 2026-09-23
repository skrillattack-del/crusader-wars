(function (root, createEvidence) {
  const evidence = createEvidence();
  if (typeof module === 'object' && module.exports) module.exports = evidence;
  if (root && root.document) root.CW2Evidence = evidence;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';

  function requireValue(condition, message) {
    if (!condition) throw new Error(message);
  }

  function parse3KLog(text) {
    const lines = text.split(/\r?\n/).filter((line) => line.trim());
    requireValue(lines.length > 0 && lines.length <= 1000, 'Expected a nonempty G1 JSONL run.');
    const events = lines.map((line, index) => {
      try {
        return JSON.parse(line);
      } catch {
        throw new Error(`Invalid JSON on log line ${index + 1}.`);
      }
    });
    const runId = events[0]?.run_id;
    requireValue(typeof runId === 'string' && runId.length > 0, 'Missing G1 run ID.');
    requireValue(events.every((event) => event && event.schema === 1 && event.run_id === runId && typeof event.phase === 'string'), 'G1 events have inconsistent run IDs or schemas.');
    const starts = events.filter((event) => event.phase === 'start');
    const completes = events.filter((event) => event.phase === 'complete');
    const results = events.filter((event) => event.phase === 'result');
    requireValue(starts.length === 1 && completes.length <= 1 && results.length <= 1, 'Expected one start and at most one complete/result; replayed runs are not comparable.');
    requireValue(events.indexOf(starts[0]) < events.indexOf(completes[0] || results[0] || events[events.length - 1]) || events.length === 1, 'Final G1 event precedes the start.');

    const startingRows = starts[0].units;
    requireValue(Array.isArray(startingRows) && startingRows.length === 6, 'G1 run must contain six starting units.');
    const expected = new Map();
    for (const unit of startingRows) {
      validateUnit(unit, true);
      requireValue(!expected.has(unit.script_name), 'G1 starting unit names must be unique.');
      expected.set(unit.script_name, unit);
    }
    requireValue(startingRows.filter((unit) => unit.alliance === 1).length === 3 && startingRows.filter((unit) => unit.alliance === 2).length === 3, 'G1 run must have three units per alliance.');

    for (const event of events) {
      requireValue(Array.isArray(event.units) && event.units.length === 6, 'G1 event has a different roster size.');
      const seen = new Set();
      for (const unit of event.units) {
        validateUnit(unit, false);
        const startingUnit = expected.get(unit.script_name);
        requireValue(startingUnit && !seen.has(unit.script_name), 'G1 event has an unknown or repeated unit.');
        requireValue(unit.unit_type === startingUnit.unit_type && unit.alliance === startingUnit.alliance && unit.army === startingUnit.army && unit.index === startingUnit.index && unit.initial === startingUnit.initial, 'G1 unit identity or starting strength changed.');
        seen.add(unit.script_name);
      }
    }
    const result = results[0];
    requireValue(!result || (events.indexOf(result) > events.indexOf(starts[0]) && typeof result.player_won === 'boolean'), 'G1 result callback is missing a valid outcome.');
    const complete = completes[0];
    requireValue(!complete || events.indexOf(complete) > events.indexOf(starts[0]), 'G1 completion precedes the start.');
    const final = result || complete;

    function totals(alliance) {
      const initial = startingRows.filter((unit) => unit.alliance === alliance).reduce((sum, unit) => sum + unit.initial, 0);
      const survivors = final?.units.filter((unit) => unit.alliance === alliance).reduce((sum, unit) => sum + unit.survivors, 0);
      return { initial, survivors: survivors ?? null };
    }

    return {
      runId,
      phase: final?.phase || events[events.length - 1].phase,
      resultCallbackPresent: Boolean(result),
      outcome: result ? (result.player_won ? 'player victory' : 'player non-victory') : 'unavailable',
      totals: { attacker: totals(1), defender: totals(2) },
      units: final ? final.units.map((unit) => ({ ...unit })) : [],
    };
  }

  function validateUnit(unit, start) {
    requireValue(unit && typeof unit.script_name === 'string' && unit.script_name.length > 0 && typeof unit.unit_type === 'string' && unit.unit_type.length > 0, 'G1 unit identity is missing.');
    requireValue((unit.alliance === 1 || unit.alliance === 2) && unit.army === 1 && Number.isSafeInteger(unit.index) && unit.index > 0, 'G1 unit position or alliance is invalid.');
    requireValue(Number.isSafeInteger(unit.initial) && unit.initial > 0 && Number.isSafeInteger(unit.survivors) && unit.survivors >= 0 && unit.survivors <= unit.initial, 'G1 soldier counts are invalid.');
    requireValue(typeof unit.routing === 'boolean' && (!start || unit.survivors === unit.initial), 'G1 routing state or starting count is invalid.');
  }

  function parseG2Plan(text) {
    let plan;
    try {
      plan = JSON.parse(text);
    } catch {
      throw new Error('Invalid G2 plan JSON.');
    }
    requireValue(plan && plan.schema === 1 && plan.kind === 'synthetic_g2_plan_not_applied' && plan.status === 'prepared_not_applied', 'G2 file is not a prepared, unapplied synthetic plan.');
    requireValue(/^[a-f\d]{64}$/i.test(plan.save_fingerprint) && /^[a-f\d]{64}$/i.test(plan.result_id), 'G2 plan fingerprint or result ID is invalid.');
    requireValue(/^\d+$/.test(plan.battle_id) && (plan.outcome === 'attacker' || plan.outcome === 'defender') && plan.outcome_source === 'synthetic_not_3k_callback', 'G2 battle ID or synthetic outcome is invalid.');
    const sides = {};
    for (const side of ['attacker', 'defender']) {
      const value = plan.sides?.[side];
      requireValue(Array.isArray(value?.army_ids) && value.army_ids.length > 0 && value.army_ids.every((id) => typeof id === 'string' && /^\d+$/.test(id)), `G2 ${side} army IDs are invalid.`);
      const initial = Number(value.initial_men);
      const fighting = Number(value.total_fighting_men);
      const loss = value.synthetic_casualties;
      requireValue(Number.isFinite(initial) && initial > 0 && Number.isFinite(fighting) && fighting >= 0 && fighting <= initial && Number.isSafeInteger(loss) && loss >= 0 && loss <= fighting, `G2 ${side} strengths or casualties are invalid.`);
      sides[side] = { armyIds: [...value.army_ids], initial, fighting, loss };
    }
    requireValue(!sides.attacker.armyIds.some((id) => sides.defender.armyIds.includes(id)), 'G2 sides share an army ID.');
    return { battleId: plan.battle_id, fingerprint: plan.save_fingerprint, resultId: plan.result_id, outcome: plan.outcome, sides };
  }

  return { parse3KLog, parseG2Plan };
});