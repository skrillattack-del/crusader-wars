import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import time
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


class FakePopen:
    def __init__(self):
        self.calls = []

    def __call__(self, args, cwd=None):
        self.calls.append((args, cwd))
        return type('Process', (), {'pid': 4242})()


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
                    'sides': [{'role': 'Attacker', 'name': 'Gharb'}, {'role': 'Defender', 'name': 'Kru'}],
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
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(),
                        saves=self.root / 'missing' / 'saves')
        with mock.patch.object(bridge_module, 'CK3_EXE', self.root / 'missing' / 'ck3.exe'):
            health = bridge.get_health()
        by_key = {p['key']: p['ok'] for p in health['paths']}
        self.assertFalse(by_key['ck3_exe'])
        self.assertFalse(by_key['ck3_saves'])
        self.assertFalse(health['gates']['ck3'])
        self.assertTrue(health['gates']['probe'])

    # ---- staged encounter and roster ----

    # ---- CK3 mod and Crusader Wars 1 ----

    def test_install_ck3_mod_registers_it_and_health_sees_it(self):
        source = self.root / 'mod_src' / 'cw2_ck3_mod'
        source.mkdir(parents=True)
        (source / 'descriptor.mod').write_text(
            'version="1.0"\nname="Crusader Wars 2: CK3 Bridge"\nsupported_version="1.19.*"\n')
        mods = self.root / 'ck3' / 'mod'
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), saves=self.root / 'ck3' / 'save games',
                        cw1_dir=self.root / 'no_cw1', mod_source=source)
        self.assertFalse(bridge.get_health()['ck3_mod'])
        result = bridge.install_ck3_mod()
        self.assertTrue(result['ok'], result)
        text = (mods / 'cw2_ck3_bridge.mod').read_text()
        self.assertIn('name="Crusader Wars 2: CK3 Bridge"', text)
        self.assertIn(f'path="{source.as_posix()}"', text)
        self.assertTrue(bridge.get_health()['ck3_mod'])

    def test_crusader_wars_1_is_detected(self):
        cw1 = self.root / 'workshop' / '2977969008'
        mods = self.root / 'mods'
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), cw1_dir=cw1, ck3_mods=mods)
        self.assertFalse(bridge.get_health()['cw1_installed'])
        cw1.mkdir(parents=True)
        self.assertTrue(bridge.get_health()['cw1_installed'])
        cw1.rmdir()
        mods.mkdir()
        (mods / 'ugc_2977969008.mod').write_text('name="Crusader Wars"\n')  # launcher descriptor alone counts too
        self.assertTrue(bridge.get_health()['cw1_installed'])

    def test_install_ck3_mod_without_files_explains(self):
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), mod_source=self.root / 'x')
        bridge.mod_source = None
        self.assertIn('mod files are missing', bridge.install_ck3_mod()['error'])

    def make_launcher_db(self, with_cw2=True):
        """Minimal copy of the Paradox launcher's playset tables, plus dlc_load.json."""
        import sqlite3
        docs = self.root / 'ck3docs'
        (docs / 'mod').mkdir(parents=True)
        con = sqlite3.connect(docs / 'launcher-v2.sqlite')
        con.executescript("""
            create table playsets (id text primary key, name text, isActive boolean);
            create table mods (id text primary key, gameRegistryId text, steamId text, displayName text);
            create table playsets_mods (playsetId text, modId text, enabled boolean, position integer);
            insert into playsets values ('p1', 'Initial playset', 1), ('p2', 'Other', 0);
            insert into mods values ('m1', 'mod/ugc_1.mod', '1', 'Some mod'),
                                    ('cw1', 'mod/ugc_2977969008.mod', '2977969008', 'Crusader Wars');
            insert into playsets_mods values ('p1', 'm1', 1, 0), ('p1', 'cw1', 1, 1);""")
        if with_cw2:
            con.execute("insert into mods values ('cw2', 'mod/cw2_ck3_bridge.mod', null, 'Crusader Wars 2: CK3 Bridge')")
        con.commit(); con.close()
        (docs / 'dlc_load.json').write_text('{"enabled_mods":["mod/ugc_1.mod","mod/ugc_2977969008.mod"],"disabled_dlcs":[]}')
        return docs

    def playset_rows(self, docs):
        import sqlite3
        con = sqlite3.connect(docs / 'launcher-v2.sqlite')
        rows = con.execute("select modId, enabled, position from playsets_mods where playsetId='p1' order by position").fetchall()
        con.close()
        return rows

    def test_add_to_playset_enables_cw2_last_and_turns_cw1_off(self):
        docs = self.make_launcher_db()
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), ck3_mods=docs / 'mod')
        self.assertFalse(bridge.get_health()['in_playset'])
        result = bridge.add_to_playset()
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['playset'], result['cw1_disabled']), ('Initial playset', 1))
        self.assertEqual(self.playset_rows(docs), [('m1', 1, 0), ('cw1', 0, 1), ('cw2', 1, 2)])
        self.assertTrue(Path(result['backup']).is_file())
        load = json.loads((docs / 'dlc_load.json').read_text())
        self.assertEqual(load['enabled_mods'], ['mod/ugc_1.mod', 'mod/cw2_ck3_bridge.mod'])
        self.assertTrue(bridge.get_health()['in_playset'])
        bridge.add_to_playset()  # a second run changes nothing
        self.assertEqual(self.playset_rows(docs), [('m1', 1, 0), ('cw1', 0, 1), ('cw2', 1, 2)])

    def test_add_to_playset_refuses_while_paradox_launcher_runs(self):
        docs = self.make_launcher_db()
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(['Paradox Launcher.exe']),
                        ck3_mods=docs / 'mod')
        self.assertIn('Close the Paradox launcher', bridge.add_to_playset()['error'])
        self.assertEqual(self.playset_rows(docs), [('m1', 1, 0), ('cw1', 1, 1)])

    def test_add_to_playset_waits_for_the_launcher_to_list_the_mod(self):
        docs = self.make_launcher_db(with_cw2=False)
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), ck3_mods=docs / 'mod')
        self.assertIn('has not listed the CW2 mod yet', bridge.add_to_playset()['error'])
        self.assertEqual(self.playset_rows(docs), [('m1', 1, 0), ('cw1', 1, 1)])

    # ---- CK3 encounter and roll ----

    def write_save(self, name='battle.ck3'):
        """Plaintext CK3 save with the Kasr al-Kabir strengths and a smaller skirmish.

        Army 1001 is the player's own; 1002 belongs to someone else, as in the real fixture.
        """
        saves = self.root / 'saves'
        saves.mkdir(exist_ok=True)
        side = lambda army, initial, fighting: (  # one scalar per line, as in real saves
            f'{{\n\t\tarmies={{ {army} }}\n\t\tinitial_men={initial}\n\t\ttotal_fighting_men={fighting}\n\t}}')
        text = '\n'.join([
            'meta_data={ meta_date=908.8.27 }', 'date=908.8.27',
            'currently_played_characters={ 59850 }',
            'armies={ regiments={ } army_regiments={ } armies={ } }',
            'units={', '\t2001={ type=army location=1 owner=77 army=1001 }',
            '\t2002={ type=army location=1 owner=59850 army=1003 }', '}',
            'combats={ combats={',
            f'\t500={{ attacker={side(1002, 571, 340.09632)} defender={side(1001, 528, 421.48395)}\n\tphase=main\n\t}}',
            '\t501=none',
            f'\t502={{ attacker={side(1003, 90, 60)} defender={side(1004, 80, 50)}\n\tphase=maneuver\n\t}}',
            '} combat_results={ } }'])
        path = saves / name
        path.write_text(text, encoding='utf-8')
        return Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), saves=saves), path

    def test_encounter_reads_newest_save_and_prefers_your_battle(self):
        bridge, path = self.write_save()
        encounter = bridge.get_encounter()
        self.assertTrue(encounter['ok'], encounter)
        self.assertEqual((encounter['save_name'], encounter['date']), (path.name, '908.8.27'))
        self.assertEqual(encounter['combat_id'], '502')  # the only one with an army you own
        self.assertEqual([b['combat_id'] for b in encounter['battles']], ['500', '502'])
        self.assertEqual([b['men'] for b in encounter['battles']], [[340, 421], [60, 50]])
        picked = bridge.get_encounter(combat_id='500')
        self.assertEqual([s['fighting'] for s in picked['sides']], [340.09632, 421.48395])
        self.assertFalse(picked['yours'])  # a vassal's army is not detected as yours
        self.assertTrue(all(side['commander'] is None and side['knights'] == []
                            for side in picked['sides']))
        self.assertIn('not in', bridge.get_encounter(combat_id='999')['error'])

    def test_encounter_without_saves_or_battles_explains(self):
        empty = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), saves=self.root)
        self.assertIn('No .ck3 saves', empty.get_encounter()['error'])

    def write_debug_log(self, bridge, stamp):
        logs = bridge.saves.parent / 'logs'
        logs.mkdir(exist_ok=True)
        (logs / 'debug.log').write_text(
            f'[{stamp:%H:%M:%S}][D][jomini_effect_impl.cpp:450]: file: common/scripted_guis/01_battle_info.txt '
            'line: 82 (CW2_Battle:effect): BATTLE_NAME:Battle of Muluya\n', encoding='utf-8')

    def test_poll_battle_reports_a_cw2_button_save_once_it_settles(self):
        import os
        bridge, path = self.write_save()
        saved = time.time() - 10
        os.utime(path, (saved, saved))
        self.write_debug_log(bridge, datetime.fromtimestamp(saved - 20))
        self.assertIsNone(bridge.poll_battle()['save'])  # first sight: wait for it to stop changing
        signal = bridge.poll_battle()
        self.assertEqual((signal['save'], signal['battle']), (str(path), 'Battle of Muluya'))
        self.assertIsNone(bridge.poll_battle()['save'])  # reported once

    def test_poll_battle_ignores_saves_the_button_did_not_trigger(self):
        import os
        bridge, path = self.write_save()
        saved = time.time() - 10
        os.utime(path, (saved, saved))
        self.write_debug_log(bridge, datetime.fromtimestamp(saved - 3600))  # an old button press
        bridge.poll_battle()
        self.assertIsNone(bridge.poll_battle()['save'])
        old = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), saves=path.parent)
        os.utime(path, (saved - 3600, saved - 3600))  # written before the launcher opened
        old.poll_battle()
        self.assertIsNone(old.poll_battle()['save'])

    def test_roll_scales_both_sides_and_repeats_by_seed(self):
        bridge, _ = self.write_save()
        encounter = bridge.get_encounter(combat_id='500')
        first, again = bridge.roll_roster(encounter, 1702901), bridge.roll_roster(encounter, 1702901)
        self.assertTrue(first['ok'], first)
        self.assertEqual(first, again)
        self.assertEqual(first['scale'], 1.0)
        self.assertEqual([(s['cards'], s['men'], s['trim']) for s in first['sides']], [(5, 340, 1), (6, 421, 0)])
        self.assertIn('fights exactly this roll', first['note'])
        self.assertIsInstance(bridge.roll_roster(encounter)['seed'], int)
        romance = bridge.roll_roster(encounter, 1702901, 'romance')
        self.assertEqual([s['generals'][0]['kind'] for s in romance['sides']], ['hero', 'hero'])
        self.assertEqual([s['men'] for s in romance['sides']], [340, 421])
        self.assertIn('Romance battles are not staged yet', romance['note'])
        self.assertIn('Unknown mode', bridge.roll_roster(encounter, 1, 'arcade')['error'])
        self.assertIn('Pick a CK3 battle', bridge.roll_roster(None)['error'])

    # ---- prepare guards (no RPFM run happens here) ----

    ROSTER = {'mode': 'records', 'sides': probe.DEFAULT_ROSTER['sides']}

    def test_prepare_needs_a_rolled_roster(self):
        for roster in (None, {}, {'sides': [{}]}):
            self.assertIn('Roll the armies first', self.bridge.prepare_and_install(roster)['error'])

    def test_prepare_refuses_while_3k_runs(self):
        bridge = Bridge(base=self.root, game=self.game,
                        tasklist=FakeTasklist(['Three_Kingdoms.exe']))
        result = bridge.prepare_and_install(self.ROSTER)
        self.assertIn('Close Three Kingdoms', result['error'])
        self.assertNotIn('ok', result)

    def test_prepare_refuses_unrecognised_pack(self):
        (self.game / 'Three_Kingdoms.exe').write_bytes(b'exe')
        target = self.game / 'data' / probe.PACK_NAME
        target.write_bytes(b'stale pack')
        result = self.bridge.prepare_and_install(self.ROSTER)
        self.assertIn('unrecognised battle pack', result['error'])
        self.assertTrue(target.exists())

    def test_prepare_removes_a_recorded_pack_before_building(self):
        (self.game / 'Three_Kingdoms.exe').write_bytes(b'exe')
        run = self.make_run(run=self.root / 'runs' / 'orphan')
        source = run / probe.PACK_NAME
        source.write_bytes(b'orphan pack')
        manifest = json.loads((run / 'run.json').read_text())
        manifest['pack_sha256'] = probe.digest(source)
        (run / 'run.json').write_text(json.dumps(manifest))
        target = probe.install(self.game, run)
        result = self.bridge.prepare_and_install(self.ROSTER)  # the fake RPFM then fails the build
        self.assertFalse(target.exists())
        self.assertIn('error', result)

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
        self.assertEqual([s['name'] for s in result['sides']], ['Gharb', 'Kru'])
        self.assertEqual(len(result['sides']), 2)
        for side in result['sides']:
            self.assertEqual(side['men'], 300)
            self.assertEqual(side['lost'], 150)
            self.assertEqual(len(side['units']), 3)
            for unit in side['units']:
                self.assertEqual(unit['lost'], unit['initial'] - unit['survivors'])
        self.assertEqual(result['sides'][0]['role'], 'attacker')
        self.assertEqual(result['sides'][1]['role'], 'defender')

    def test_a_defending_player_reads_as_the_defender(self):
        run = self.make_run()
        manifest = json.loads((run / 'run.json').read_text())
        for unit in manifest['expected_units']:  # the player's alliance 1 is the CK3 defender
            unit['side'] = 'defender' if unit['alliance'] == 1 else 'attacker'
        (run / 'run.json').write_text(json.dumps(manifest))
        self.bridge.session.update(output=str(run), game=str(self.game))
        result = self.bridge.read_result()
        self.assertEqual((result['player_side'], result['winner']), (1, 1))
        self.assertEqual([s['name'] for s in result['sides']], ['Gharb', 'Kru'])
        self.assertTrue(all(u['script_name'].startswith('cw2_attacker') for u in result['sides'][1]['units']))

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

    # ---- write-back ----

    def test_writeback_is_off_and_writes_no_save(self):
        preview = self.bridge.preview_writeback()
        apply = self.bridge.apply_writeback()
        self.assertIn('off in this build', preview['error'])
        self.assertIn('off in this build', apply['error'])
        self.assertFalse(list(self.root.rglob('CW2_*_AFTER.ck3')))


    # ---- session and assets ----

    def test_launch_3k_starts_the_game_with_only_the_battle_pack(self):
        popen = FakePopen()
        bridge = Bridge(base=self.root, game=self.game, tasklist=FakeTasklist(), popen=popen)
        self.assertIn('not installed', bridge.launch_3k()['error'])
        self.assertEqual(popen.calls, [])
        (self.game / 'data' / probe.PACK_NAME).write_bytes(b'pack')
        (self.game / 'used_mods.txt').write_text('mod "someone_elses.pack";', encoding='utf-8')
        launched = bridge.launch_3k()
        self.assertEqual(launched['pid'], 4242)
        self.assertEqual(popen.calls, [([str(self.game / 'Three_Kingdoms.exe'), 'used_mods_cw2.txt;'], str(self.game))])
        self.assertEqual((self.game / 'used_mods_cw2.txt').read_text(encoding='utf-8'), f'mod "{probe.PACK_NAME}";\n')
        self.assertEqual((self.game / 'used_mods.txt').read_text(encoding='utf-8'), 'mod "someone_elses.pack";')

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


