import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
for _p in (str(HERE.parents[0] / 'spikes' / 'g1_3k_io'), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import probe
from bridge import Bridge

INDEX = HERE / 'ui' / 'index.html'


class FakeTasklist:
    def __init__(self, names=()):
        self.names = list(names)

    def __call__(self, cmd):
        rows = '\n'.join(f'"{name}","1","Console"' for name in self.names)
        return 0, rows + '\r\n'


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        (self.game / 'data').mkdir(parents=True)
        (self.root / 'tools' / 'rpfm').mkdir(parents=True)
        (self.root / 'tools' / 'rpfm' / 'rpfm_cli.exe').write_bytes(b'cli')
        self.bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist())

    def make_run(self, player_won=True, source='engine_callback', survivors=50, run=None):
        run = run or self.root / 'run'
        expected = [{'script_name': f'cw2_{side}_{i}', 'unit_type': f'type_{i}', 'alliance': a}
                    for a, side in ((1, 'attacker'), (2, 'defender')) for i in range(3)]
        manifest = {'schema': 1, 'run_id': 'run1', 'entry': probe.BATTLE,
                    'expected_units': expected, 'log_path': str(run / 'runtime.jsonl')}
        run.mkdir(parents=True)
        units = [dict(u, army=1, index=i + 1, initial=100, survivors=100, routing=False)
                 for i, u in enumerate(expected)]
        start = {'schema': 1, 'run_id': 'run1', 'battle': probe.BATTLE, 'phase': 'start',
                 'units': units, 'player_won': None}
        final = copy.deepcopy(start)
        final.update(phase='result', player_won=player_won, result_source=source)
        for unit in final['units']:
            unit['survivors'] = survivors
        (run / 'runtime.jsonl').write_text('\n'.join(json.dumps(e) for e in (start, final)))
        (run / 'run.json').write_text(json.dumps(manifest))
        return run

    # ---- health ----

    def test_health_reports_paths_and_gates(self):
        health = self.bridge.get_health()
        self.assertTrue(health['ok'])
        self.assertFalse(health['ck3_running'])
        self.assertFalse(health['tk_running'])
        by_key = {p['key']: p['ok'] for p in health['paths']}
        self.assertTrue(by_key['rpfm_cli'])
        self.assertFalse(by_key['tk_exe'])
        self.assertFalse(health['gates']['probe'])
        (self.game / 'Three_Kingdoms.exe').write_bytes(b'exe')
        health = self.bridge.get_health()
        self.assertTrue(health['gates']['probe'])

    def test_health_detects_running_games(self):
        bridge = Bridge(base=self.root, game=self.game,
                        tasklist=FakeTasklist(['ck3.exe', 'Three_Kingdoms.exe']))
        health = bridge.get_health()
        self.assertTrue(health['ck3_running'])
        self.assertTrue(health['tk_running'])

    def test_health_gate_ignores_missing_ck3(self):
        # CK3 is installed on this machine, so point the checks at a fake miss.
        (self.game / 'Three_Kingdoms.exe').write_bytes(b'exe')
        import bridge as bridge_module
        from unittest import mock
        with mock.patch.object(bridge_module, 'CK3_EXE', self.root / 'missing' / 'ck3.exe'), \
             mock.patch.object(bridge_module, 'CK3_SAVES', self.root / 'missing' / 'saves'):
            health = self.bridge.get_health()
        by_key = {p['key']: p['ok'] for p in health['paths']}
        self.assertFalse(by_key['ck3_exe'])
        self.assertFalse(by_key['ck3_saves'])
        self.assertTrue(health['gates']['probe'])

    # ---- staged encounter and roster ----

    def test_staged_encounter_and_roster(self):
        encounter = self.bridge.get_encounter()
        self.assertTrue(encounter['ok'])
        self.assertEqual(encounter['entry'], probe.BATTLE)
        self.assertEqual(len(encounter['sides']), 2)
        for side in encounter['sides']:
            generals = [u for u in side['units'] if u['kind'] == 'general']
            units = [u for u in side['units'] if u['kind'] == 'unit']
            self.assertEqual(len(generals), 1)
            self.assertEqual(len(units), 2)
            self.assertEqual(side['cards'], 3)
            self.assertEqual(side['retinue'], 2)
        roster_a = self.bridge.roll_roster(encounter, 1)
        roster_b = self.bridge.roll_roster(encounter, 999)
        self.assertTrue(roster_a['ok'] and roster_b['ok'])
        self.assertTrue(roster_a['deterministic'])
        self.assertEqual(roster_a, roster_b)  # fixed by the probe, seed ignored
        for side in roster_a['sides']:
            self.assertEqual(len(side['generals']), 1)
            general = side['generals'][0]
            self.assertEqual(general['role'], 'Commander')
            self.assertIsNone(general['prowess'])
            self.assertEqual(len(general['units']), 3)
            self.assertEqual(side['retinue'], 2)
            self.assertEqual(side['cards'], 3)

    def test_staged_roster_matches_probe_unit_types(self):
        roster = self.bridge.roll_roster()
        types = {u['key'] for side in roster['sides']
                 for g in side['generals'] for u in g['units']}
        for faction in ('cao_cao', 'liu_bei'):
            self.assertIn(f'3k_main_general_earth_{faction}', types)
        self.assertEqual(types - {f'3k_main_general_earth_{f}' for f in ('cao_cao', 'liu_bei')},
                         {'3k_main_unit_wood_ji_militia', '3k_main_unit_water_archer_militia'})

    # ---- prepare guards (no RPFM run happens here) ----

    def test_prepare_refuses_while_3k_runs(self):
        bridge = Bridge(base=self.root, game=self.game,
                        tasklist=FakeTasklist(['Three_Kingdoms.exe']))
        result = bridge.prepare_and_install()
        self.assertIn('Close Three Kingdoms', result['error'])
        self.assertNotIn('ok', result)

    def test_prepare_refuses_existing_pack(self):
        (self.game / 'data' / probe.PACK_NAME).write_bytes(b'stale pack')
        result = self.bridge.prepare_and_install()
        self.assertIn('Remove the installed probe', result['error'])

    # ---- read result ----

    def test_read_result_requires_prepared_run(self):
        self.assertIn('Prepare a run first', self.bridge.read_result()['error'])

    def test_read_result_groups_units_and_sums(self):
        run = self.make_run()
        self.bridge.session.update(output=str(run), game=str(self.game))
        result = self.bridge.read_result()
        self.assertTrue(result['ok'])
        self.assertEqual(result['winner'], 0)
        self.assertEqual(result['player_outcome'], 'victory')
        self.assertEqual(result['result_source'], 'engine_callback')
        self.assertEqual(result['player_side'], 0)
        self.assertEqual([s['name'] for s in result['sides']], ['Cao Cao', 'Liu Bei'])
        self.assertEqual(len(result['sides']), 2)
        for side in result['sides']:
            self.assertEqual(side['men'], 300)
            self.assertEqual(side['lost'], 150)
            self.assertEqual(len(side['units']), 3)
            for unit in side['units']:
                self.assertEqual(unit['lost'], unit['initial'] - unit['survivors'])
        self.assertEqual(result['sides'][0]['role'], 'attacker')
        self.assertEqual(result['sides'][1]['role'], 'defender')

    def test_read_result_rejects_undetermined(self):
        run = self.make_run(player_won=None, source='routing_state')
        self.bridge.session.update(output=str(run), game=str(self.game))
        self.assertIn('undetermined', self.bridge.read_result()['error'])

    def test_read_result_rejects_falsified_fallback_source(self):
        run = self.make_run(source='victory_countdown_fallback')
        self.bridge.session.update(output=str(run), game=str(self.game))
        self.assertTrue(self.bridge.read_result()['error'])

    def test_non_victory_has_no_winner(self):
        run = self.make_run(player_won=False)
        self.bridge.session.update(output=str(run), game=str(self.game))
        result = self.bridge.read_result()
        self.assertTrue(result['ok'])
        self.assertIsNone(result['winner'])
        self.assertEqual(result['player_outcome'], 'non_victory')

    # ---- remove probe ----

    def install_fake_pack(self):
        run = self.make_run()
        source = run / probe.PACK_NAME
        source.write_bytes(b'our probe')
        manifest = json.loads((run / 'run.json').read_text())
        manifest['pack_sha256'] = probe.digest(source)
        (run / 'run.json').write_text(json.dumps(manifest))
        target = probe.install(self.game, run)
        native = self.game / 'data' / 'data.pack'
        native.write_bytes(b'native pack untouched')
        self.bridge.session.update(output=str(run), game=str(self.game))
        return run, target, native

    def test_remove_probe_roundtrip(self):
        run, target, native = self.install_fake_pack()
        self.assertTrue(target.exists())
        result = self.bridge.remove_probe()
        self.assertTrue(result['ok'])
        self.assertTrue(result['was_installed'])
        self.assertFalse(target.exists())
        self.assertEqual(native.read_bytes(), b'native pack untouched')

    def test_remove_probe_refuses_changed_pack(self):
        run, target, native = self.install_fake_pack()
        target.write_bytes(b'someone changed this')
        self.assertIn('refusing', self.bridge.remove_probe()['error'])
        self.assertTrue(target.exists())

    def test_remove_probe_refuses_while_3k_runs(self):
        self.install_fake_pack()
        bridge = Bridge(base=self.root, game=self.game,
                        tasklist=FakeTasklist(['Three_Kingdoms.exe']))
        bridge.session.update(output=self.bridge.session['output'], game=str(self.game))
        self.assertIn('Close Three Kingdoms', bridge.remove_probe()['error'])

    def test_health_reports_installed_pack(self):
        self.assertFalse(self.bridge.get_health()['probe_installed'])
        (self.game / 'data' / probe.PACK_NAME).write_bytes(b'pack')
        self.assertTrue(self.bridge.get_health()['probe_installed'])

    def test_remove_adopts_orphaned_pack_from_runs_folder(self):
        run = self.make_run(run=self.root / 'runs' / 'orphan')
        source = run / probe.PACK_NAME
        source.write_bytes(b'orphan pack')
        manifest = json.loads((run / 'run.json').read_text())
        manifest['pack_sha256'] = probe.digest(source)
        (run / 'run.json').write_text(json.dumps(manifest))
        target = probe.install(self.game, run)
        native = self.game / 'data' / 'data.pack'
        native.write_bytes(b'native pack untouched')
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist())
        self.assertIsNone(bridge.session.get('output'))
        result = bridge.remove_probe()
        self.assertTrue(result['ok'])
        self.assertTrue(result['was_installed'])
        self.assertEqual(result['run'], str(run))
        self.assertFalse(target.exists())
        self.assertEqual(native.read_bytes(), b'native pack untouched')

    def test_remove_falls_back_to_scan_when_session_points_elsewhere(self):
        run = self.make_run(run=self.root / 'runs' / 'orphan')
        source = run / probe.PACK_NAME
        source.write_bytes(b'orphan pack')
        manifest = json.loads((run / 'run.json').read_text())
        manifest['pack_sha256'] = probe.digest(source)
        (run / 'run.json').write_text(json.dumps(manifest))
        target = probe.install(self.game, run)
        other = self.make_run(run=self.root / 'other')  # this session recorded a different run
        self.bridge.session.update(output=str(other), game=str(self.game))
        result = self.bridge.remove_probe()
        self.assertTrue(result['ok'])
        self.assertEqual(result['run'], str(run))
        self.assertFalse(target.exists())

    def test_remove_refuses_pack_matching_no_recorded_run(self):
        (self.game / 'data' / probe.PACK_NAME).write_bytes(b'mystery pack')
        result = self.bridge.remove_probe()
        self.assertIn('refusing', result['error'])

    def test_remove_is_a_noop_when_nothing_is_installed(self):
        result = self.bridge.remove_probe()
        self.assertTrue(result['ok'])
        self.assertFalse(result['was_installed'])
        self.assertIsNone(result['run'])

    # ---- not integrated ----

    def test_writeback_reports_not_integrated(self):
        for method in ('preview_writeback', 'apply_writeback'):
            with self.subTest(method=method):
                self.assertIn('not integrated', getattr(self.bridge, method)()['error'])

    # ---- session and assets ----

    def test_session_persists_between_launches(self):
        self.bridge.session.update(output=str(self.root / 'run'), game=str(self.game))
        self.bridge._save_session()
        reloaded = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist())
        self.assertEqual(reloaded.session['output'], str(self.root / 'run'))

    def test_ui_assets(self):
        text = INDEX.read_text(encoding='utf-8')
        self.assertIn('pywebviewready', text)
        self.assertIn('removeProbe', text)
        self.assertIn('<title>Crusader Wars 2 launcher</title>', text)
        for absent in ('MockBridge', 'simCk3', 'fonts.googleapis'):
            self.assertNotIn(absent, text, f'{absent} should not ship in the app UI')

    def test_ui_preserves_tally_glyphs(self):
        text = INDEX.read_text(encoding='utf-8')
        for glyph in (0x5DE6, 0x53F3, 0x5408):  # tally halves and the seal
            self.assertIn(chr(glyph), text)


if __name__ == '__main__':
    unittest.main()


