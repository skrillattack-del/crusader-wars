import copy
import json
from pathlib import Path
import tempfile
import unittest
import probe

class ResultValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.expected = [{'script_name': f'u{i}', 'unit_type': f'type{i}', 'alliance': 1 if i < 3 else 2} for i in range(6)]
        manifest = {'schema': 1, 'run_id': 'run1', 'entry': probe.BATTLE, 'expected_units': self.expected, 'log_path': str(self.root / 'runtime.jsonl')}
        (self.root / 'run.json').write_text(json.dumps(manifest))
        units = [dict(u, army=1, index=i + 1, initial=100, survivors=100, routing=False) for i, u in enumerate(self.expected)]
        self.start = {'schema': 1, 'run_id': 'run1', 'battle': probe.BATTLE, 'phase': 'start', 'units': units, 'player_won': None}
        self.final = copy.deepcopy(self.start)
        self.final.update(phase='result', player_won=True, result_source='engine_callback')
        for unit in self.final['units']: unit['survivors'] = 50

    def write(self, events):
        (self.root / 'runtime.jsonl').write_text('\n'.join(json.dumps(e) for e in events))

    def test_valid_victory(self):
        self.write([self.start, self.final])
        self.assertEqual(probe.read_result(self.root)['winner'], 'attacker')

    def test_non_victory_is_not_assumed_defeat(self):
        self.final['player_won'] = False
        self.write([self.start, self.final])
        self.assertIsNone(probe.read_result(self.root)['winner'])

    def test_rejects_bad_correlation_roster_counts_and_replay(self):
        variants = []
        for field, value in [('run_id', 'foreign'), ('player_won', None)]:
            event = copy.deepcopy(self.final); event[field] = value; variants.append([self.start, event])
        for field, value in [('survivors', 101), ('survivors', -1), ('initial', 90), ('unit_type', 'foreign'), ('alliance', 2), ('script_name', 'u1')]:
            event = copy.deepcopy(self.final); event['units'][0][field] = value; variants.append([self.start, event])
        variants.extend([[self.start], [self.final, self.start], [self.start, self.final, self.start, self.final]])
        for events in variants:
            with self.subTest(events=events):
                self.write(events)
                with self.assertRaises(ValueError): probe.read_result(self.root)

    def test_records_result_source_and_battle(self):
        self.write([self.start, self.final])
        result = probe.read_result(self.root)
        self.assertEqual(result['result_source'], 'engine_callback')
        self.assertEqual(result['battle'], probe.BATTLE)

    def test_routing_source_is_labelled_not_authoritative(self):
        self.final['result_source'] = 'routing_state'
        self.write([self.start, self.final])
        result = probe.read_result(self.root)
        self.assertEqual(result['result_source'], 'routing_state')
        self.assertIn('routing or dead', result['limitation'])

    def test_rejects_side_agnostic_countdown_flag(self):
        # battle_is_won is set when either side's VictoryCountdown begins.
        self.final['result_source'] = 'victory_countdown_fallback'
        self.write([self.start, self.final])
        with self.assertRaises(ValueError): probe.read_result(self.root)

    def test_undetermined_outcome_is_rejected(self):
        self.final.update(player_won=None, result_source='routing_state')
        self.write([self.start, self.final])
        with self.assertRaisesRegex(ValueError, 'undetermined'): probe.read_result(self.root)

    def test_routing_defeat_names_the_enemy_winner(self):
        self.final.update(player_won=False, result_source='routing_state')
        self.write([self.start, self.final])
        self.assertEqual(probe.read_result(self.root)['winner'], 'defender')

    def test_player_side_comes_from_the_manifest(self):
        # CW2 seats a defending CK3 player in alliance 1, as at Kasr al-Kabir.
        manifest = json.loads((self.root / 'run.json').read_text())
        for unit in manifest['expected_units']:
            unit['side'] = 'defender' if unit['alliance'] == 1 else 'attacker'
        (self.root / 'run.json').write_text(json.dumps(manifest))
        self.write([self.start, self.final])
        result = probe.read_result(self.root)
        self.assertEqual((result['player_side'], result['winner']), ('defender', 'defender'))

    def test_late_engine_result_is_cross_checked(self):
        late = copy.deepcopy(self.final)
        late['phase'] = 'engine_result'
        self.write([self.start, self.final, late])
        self.assertEqual(probe.read_result(self.root)['winner'], 'attacker')
        late['player_won'] = False
        self.write([self.start, self.final, late])
        with self.assertRaises(ValueError): probe.read_result(self.root)

    def test_rejects_unknown_source_and_wrong_battle(self):
        for change in ({'result_source': 'guess'}, {'result_source': None}, {'battle': 'other_battle'}):
            event = copy.deepcopy(self.final); event.update(change)
            self.write([self.start, event])
            with self.assertRaises(ValueError): probe.read_result(self.root)

    def test_removal_refuses_changed_pack_and_preserves_other_files(self):
        game = self.root / 'game'
        (game / 'data').mkdir(parents=True)
        source = self.root / probe.PACK_NAME
        source.write_bytes(b'our probe')
        native = game / 'data/data.pack'
        native.write_bytes(b'native pack untouched')
        manifest = json.loads((self.root / 'run.json').read_text())
        manifest['pack_sha256'] = probe.digest(source)
        (self.root / 'run.json').write_text(json.dumps(manifest))
        target = probe.install(game, self.root)
        target.write_bytes(b'someone changed this')
        with self.assertRaises(ValueError): probe.uninstall(game, self.root)
        self.assertTrue(target.exists())
        target.write_bytes(source.read_bytes())
        probe.uninstall(game, self.root)
        self.assertFalse(target.exists())
        self.assertEqual(native.read_bytes(), b'native pack untouched')

if __name__ == '__main__': unittest.main()
