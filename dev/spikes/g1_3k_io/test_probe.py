import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import probe
import lobby  # lobby/lobby.py, on the path via probe

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

    def test_units_smaller_than_their_card_keep_their_real_strength(self):
        # 3K sizes units by type; trimming only removes surplus, so the real count stands.
        path = self.root / 'run.json'
        manifest = json.loads(path.read_text())
        manifest['expected_units'][0]['target_men'] = 120
        path.write_text(json.dumps(manifest))
        self.write([self.start, self.final])
        self.assertEqual(probe.read_result(self.root)['units'][0]['initial'], 100)

    def test_non_victory_is_not_assumed_defeat(self):
        self.final['player_won'] = False
        self.write([self.start, self.final])
        self.assertIsNone(probe.read_result(self.root)['winner'])

    def test_rejects_bad_correlation_roster_counts_and_replay(self):
        variants = []
        for field, value in [('run_id', 'foreign'), ('player_won', None)]:
            event = copy.deepcopy(self.final); event[field] = value; variants.append([self.start, event])
        for field, value in [('survivors', 101), ('survivors', -1), ('unit_type', 'foreign'), ('alliance', 2), ('script_name', 'u1')]:
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

    def test_destroyed_unit_is_injected(self):
        # 3K drops a completely destroyed unit from its final event capture
        self.final['units'].pop(0)  # remove u0
        self.write([self.start, self.final])
        result = probe.read_result(self.root)
        self.assertEqual(len(result['units']), 6)
        lost_unit = next(u for u in result['units'] if u['script_name'] == 'u0')
        self.assertEqual(lost_unit['survivors'], 0)
        self.assertTrue(lost_unit['routing'])

    def test_rejects_missing_unit_in_start(self):
        self.start['units'].pop(0)
        self.write([self.start, self.final])
        with self.assertRaisesRegex(ValueError, 'missing at start: u0'):
            probe.read_result(self.root)

    def test_rejects_an_unknown_unit_in_the_result(self):
        self.final['units'][0]['script_name'] = 'stranger'
        self.write([self.start, self.final])
        with self.assertRaisesRegex(ValueError, 'extra: stranger'):
            probe.read_result(self.root)

    def test_a_dead_hero_does_not_shift_starting_counts(self):
        # Run 20260929-103647 (Battle of Bouillon): the defender hero died and dropped out of
        # the list, so the logger's position-keyed 'initial' shifted onto the next units.
        for unit in self.start['units']:
            unit['initial'] = unit['survivors'] = 1 if unit['script_name'] == 'u3' else 80
        deployed = copy.deepcopy(self.start)
        deployed['phase'] = 'deployed'
        for unit in deployed['units']:
            if unit['script_name'] != 'u3': unit['survivors'] = 75  # trimmed to the rolled card
        self.final['units'] = [u for u in self.final['units'] if u['script_name'] != 'u3']
        shifted = [1, 80, 80]
        for unit in self.final['units']:
            unit['survivors'] = 60 if unit['alliance'] == 1 else 2
            if unit['alliance'] == 2: unit['initial'] = shifted.pop(0)
        self.write([self.start, deployed, self.final])
        units = {u['script_name']: u for u in probe.read_result(self.root)['units']}
        self.assertEqual((units['u0']['initial'], units['u0']['survivors']), (75, 60))
        self.assertEqual((units['u4']['initial'], units['u4']['survivors']), (75, 2))
        self.assertEqual((units['u3']['initial'], units['u3']['survivors']), (1, 0))

    def test_rejects_duplicate_units_in_a_capture(self):
        self.final['units'].append(copy.deepcopy(self.final['units'][0]))
        self.write([self.start, self.final])
        with self.assertRaisesRegex(ValueError, 'Duplicate unit'):
            probe.read_result(self.root)

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

GENERAL = ('<general><name>1</name><commander_type>commanding_general</commander_type>'
           '<commander_id>0</commander_id><game_mode>{game_mode}</game_mode></general>')

def native_unit(kind, x, y, radians, general=False, game_mode='historical'):
    return (f'<unit script_name="n"><unit_type type="{kind}"/><retinue id="0"/>'
            f'<position x="{x}" y="{y}"/><orientation radians="{radians}"/><width metres="20"/>'
            f'<unit_experience level="5"/>{GENERAL.format(game_mode=game_mode) if general else ""}</unit>')

def native_battle(armies):
    alliances = ''.join(f'<alliance><army><faction>f</faction>{"".join(units)}</army>'
                        f'<army><faction>reinforcements</faction></army>'
                        f'<victory_condition><kill_or_rout_enemy/></victory_condition></alliance>'
                        for units in armies)
    return (f'<battle><battle_description><battle_script prepare_for_fade_in="true">x</battle_script>'
            f'</battle_description>{alliances}</battle>')

class GenerateTests(unittest.TestCase):
    ROSTER = {'mode': 'records', 'sides': [
        {'role': 'Attacker', 'name': 'Gharb', 'fighting': 3785.0, 'generals': [
            {'key': '3k_main_general_earth_generic', 'name': 'Captain 1', 'men': 21,
             'units': [{'key': f'unit_a{i}', 'name': f'A{i}', 'men': 80 - i} for i in range(6)]},
            {'key': '3k_main_general_wood_generic', 'name': 'Captain 2', 'men': 21,
             'units': [{'key': 'unit_b', 'name': 'B', 'men': 75}]}]},
        {'role': 'Defender', 'name': 'Kru', 'fighting': 152.0, 'generals': [
            {'key': '3k_main_general_earth_generic', 'name': 'Captain 1', 'men': 21,
             'units': [{'key': 'unit_c', 'name': 'C', 'men': 39}]}]}]}

    ROMANCE_ROSTER = {'mode': 'romance', 'sides': [
        {'role': 'Attacker', 'name': 'Gharb', 'fighting': 3785.0, 'generals': [
            {'key': '3k_main_hero_metal_generic', 'name': 'Captain 1', 'men': 1,
             'units': [{'key': 'unit_a', 'name': 'A', 'men': 80}, {'key': 'unit_b', 'name': 'B', 'men': 75}]}]},
        {'role': 'Defender', 'name': 'Kru', 'fighting': 152.0, 'generals': [
            {'key': '3k_main_hero_wood_generic', 'name': 'Captain 1', 'men': 1,
             'units': [{'key': 'unit_c', 'name': 'C', 'men': 39}]}]}]}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = self.root / 'native'
        battles = self.native / 'script/battle/historical_battle'
        (battles / 'historical_battle_xinyang').mkdir(parents=True)
        (battles / 'historical_battle_red_cliff').mkdir(parents=True)
        (battles / 'historical_battle_xinyang/battle.xml').write_text(native_battle([
            [native_unit('3k_main_general_earth_cao_cao', -400, -150, 0.74, True), native_unit('u', -380, -140, 0.74)],
            [native_unit('3k_main_general_metal_generic', 100, 350, 3.87, True), native_unit('u', 120, 300, 3.87)]]))
        (battles / 'historical_battle_red_cliff/battle.xml').write_text(native_battle([
            [native_unit('3k_main_general_earth_liu_bei', 0, 0, 0, True),
             native_unit('3k_main_general_earth_generic', 0, 0, 0, True)],
            [native_unit('3k_main_general_wood_generic', 0, 0, 0, True)]]))
        (battles / 'historical_battle_xinyang_romance').mkdir(parents=True)
        (battles / 'historical_battle_xinyang_romance/battle.xml').write_text(native_battle([
            [native_unit('3k_main_hero_earth_cao_cao', -400, -150, 0.74, True, 'romance'),
             native_unit('u', -380, -140, 0.74)],
            [native_unit('3k_main_hero_metal_generic', 100, 350, 3.87, True, 'romance'),
             native_unit('3k_main_hero_wood_generic', 120, 300, 3.87, True, 'romance'),
             native_unit('u', 140, 320, 3.87)]]))
        self.output = self.root / 'out'
        self.output.mkdir()

    def generate(self, roster):
        return probe.generate(self.native, self.output, probe.HERE / 'probe.lua', roster)

    def staged_armies(self, entry=probe.BATTLE):
        import xml.etree.ElementTree as ET
        root = ET.parse(self.output / 'pack' / entry / 'battle.xml').getroot()
        return [alliance.findall('army') for alliance in root.findall('alliance')]

    def test_stages_the_rolled_roster(self):
        manifest = self.generate(self.ROSTER)
        armies = self.staged_armies()
        self.assertEqual([len(a) for a in armies], [1, 1])  # reinforcement armies dropped
        attacker, defender = (a[0].findall('unit') for a in armies)
        self.assertEqual(len(attacker), 2 + 7)
        self.assertEqual(len(defender), 1 + 1)
        self.assertEqual([u.find('unit_type').get('type') for u in attacker[:3]],
                         ['3k_main_general_earth_generic', '3k_main_general_wood_generic', 'unit_a0'])
        self.assertEqual([u.find('retinue').get('id') for u in attacker],
                         ['0', '1'] + ['0'] * 6 + ['1'])
        self.assertEqual([u.findtext('general/commander_type') for u in attacker[:2]],
                         ['commanding_general', 'non_commanding_general'])
        self.assertEqual([u.findtext('general/commander_id') for u in attacker[:2]], ['0', '1'])
        self.assertTrue(all(u.find('general') is None for u in attacker[2:]))
        spots = {(u.find('position').get('x'), u.find('position').get('y')) for u in attacker + defender}
        self.assertEqual(len(spots), len(attacker) + len(defender))
        self.assertEqual([u.find('orientation').get('radians') for u in (attacker[0], defender[0])], ['0.74', '3.87'])
        self.assertEqual([s['men'] for s in manifest['sides']], [21 + 21 + sum(80 - i for i in range(6)) + 75, 60])
        self.assertEqual([s['name'] for s in manifest['sides']], ['Gharb', 'Kru'])
        self.assertEqual(len(manifest['expected_units']), 11)

    def test_generals_stand_behind_their_units(self):
        self.generate(self.ROSTER)
        attacker = self.staged_armies()[0][0].findall('unit')
        enemy = (110.0, 325.0)  # native defender centre
        def distance(unit):
            p = unit.find('position')
            return ((float(p.get('x')) - enemy[0]) ** 2 + (float(p.get('y')) - enemy[1]) ** 2) ** 0.5
        self.assertGreater(min(map(distance, attacker[:2])), max(map(distance, attacker[2:])))

    def test_stages_a_romance_roster_on_the_romance_xingyang_path(self):
        manifest = self.generate(self.ROMANCE_ROSTER)
        self.assertEqual((manifest['mode'], manifest['entry']), ('Romance', probe.BATTLE_ROMANCE))
        self.assertFalse((self.output / 'pack' / probe.BATTLE).exists())  # the Records path is untouched
        armies = self.staged_armies(probe.BATTLE_ROMANCE)
        attacker, defender = (a[0].findall('unit') for a in armies)
        # Heroes are general units of their own: single men, romance metadata.
        self.assertEqual(attacker[0].find('unit_type').get('type'), '3k_main_hero_metal_generic')
        self.assertEqual(attacker[0].findtext('general/game_mode'), 'romance')
        self.assertEqual(attacker[0].findtext('general/commander_type'), 'commanding_general')
        self.assertEqual(attacker[0].findtext('general/commander_id'), '0')
        self.assertTrue(all(u.find('general') is None for u in attacker[1:]))
        self.assertEqual([u['target_men'] for u in manifest['expected_units']],
                         [1, 80, 75, 1, 39])
        self.assertTrue(all(u['general'] == (i in (0, 3)) for i, u in enumerate(manifest['expected_units'])))
        # The battle script is staged at the romance entry and reports it as the battle.
        script = (self.output / 'pack' / probe.BATTLE_ROMANCE / 'battle_script.lua').read_text(encoding='utf-8')
        self.assertNotIn('@@', script)
        self.assertIn(f'"{probe.BATTLE_ROMANCE}"', script)
        # The in-game lobby ticks the Romance checkbox for this run.
        self.assertEqual(manifest['lobby']['mode'], 'Romance')
        lobby_script = (self.output / 'pack' / probe.LOBBY).read_text(encoding='utf-8')
        self.assertIn('local ROMANCE = true;', lobby_script)

    def test_records_runs_leave_the_romance_checkbox_off(self):
        manifest = self.generate(self.ROSTER)
        self.assertEqual((manifest['mode'], manifest['entry']), ('Records', probe.BATTLE))
        lobby_script = (self.output / 'pack' / probe.LOBBY).read_text(encoding='utf-8')
        self.assertIn('local ROMANCE = false;', lobby_script)

    def test_battle_script_trims_every_card_to_its_rolled_size(self):
        manifest = self.generate(self.ROSTER)
        lua = (self.output / 'pack' / probe.BATTLE / 'battle_script.lua').read_text(encoding='utf-8')
        self.assertNotIn('@@', lua)
        for unit in manifest['expected_units']:
            self.assertIn(f'["{unit["script_name"]}"] = {unit["target_men"]}', lua)

    def test_a_defending_player_takes_the_player_slot(self):
        roster = copy.deepcopy(self.ROSTER)
        roster['sides'][1]['yours'] = True
        manifest = self.generate(roster)
        player, enemy = (a[0].findall('unit') for a in self.staged_armies())
        self.assertEqual((len(player), len(enemy)), (1 + 1, 2 + 7))
        self.assertEqual(player[0].find('orientation').get('radians'), '0.74')  # the native player slot
        self.assertEqual({(u['alliance'], u['side']) for u in manifest['expected_units']},
                         {(1, 'defender'), (2, 'attacker')})
        self.assertEqual([s['name'] for s in manifest['sides']], ['Kru', 'Gharb'])

    def test_frontend_lobby_is_bound_to_this_run(self):
        manifest = self.generate(self.ROSTER)
        script = (self.output / 'pack' / probe.LOBBY).read_text(encoding='utf-8')
        self.assertNotIn('@@', script)
        self.assertIn(manifest['run_id'], script)
        self.assertIn(manifest['log_path'].replace('\\', '/'), script)
        self.assertIn('"ui/cw2/cw2_lobby"', script)
        self.assertTrue(probe.LOBBY.startswith('script/frontend/mod/'))
        self.assertEqual(manifest['lobby']['run_id'], manifest['run_id'])
        for name in (lobby.LAYOUT_PATH, *lobby.ART):
            self.assertTrue((self.output / 'pack' / name).is_file(), name)

    def test_lobby_layout_is_well_formed_with_unique_ids(self):
        text = lobby.layout_xml()
        root = ET.fromstring(text.split('\n', 1)[1])
        ids = [c.get('id') for c in root.find('components')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids) - {'root', 'cw2_lobby', 'cw2_panel'}, {*lobby.TEXT, *lobby.BUTTONS})
        # every GUID is defined once; the hierarchy places defined components; references resolve
        components = text.split('<components>', 1)[1]
        defined = re.findall(r'\bthis="([0-9A-F-]+)"', components)
        self.assertEqual(len(defined), len(set(defined)))
        placed = re.findall(r'\bthis="([0-9A-F-]+)"', text.split('<components>', 1)[0])
        self.assertEqual(set(placed), set(re.findall(r'<\w+ this="([0-9A-F-]+)" id=', components)))
        states = set(re.findall(r'<\w+ this="([0-9A-F-]+)" name=', components))
        self.assertLessEqual(set(re.findall(r'transition_m_target_state="([0-9A-F-]+)"', text)), states)
        self.assertLessEqual(set(re.findall(r'currentstate="([0-9A-F-]+)"', text)), states)
        images = set(re.findall(r'<component_image this="([0-9A-F-]+)"', text))
        self.assertLessEqual(set(re.findall(r'componentimage="([0-9A-F-]+)"', text)), images)
        self.assertLessEqual({p for p in re.findall(r'imagepath="([^"]+)"', text)}, set(lobby.ART))

    def test_lobby_card_merges_units_and_reads_the_commander(self):
        roster = copy.deepcopy(self.ROSTER)
        roster['battle'] = 'Battle of "Hastings"'
        roster['sides'][0]['commander'] = {'name': 'William', 'martial': 21, 'prowess': 16}
        card = probe.lobby_card(roster, 'r1')
        self.assertEqual(card['battle'], 'Battle of "Hastings"')
        self.assertEqual(card['sides'][0]['commander'], 'William')
        self.assertIsNone(card['sides'][1]['commander'])
        self.assertEqual(sum(u['cards'] for u in card['sides'][1]['units']),
                         sum(len(g['units']) for g in roster['sides'][1]['generals']))
        self.assertIn('[\"battle\"] = \"Battle of \\\"Hastings\\\"\"', probe._lua(card))

    def test_the_staged_battle_takes_the_ck3_battle_name(self):
        import struct
        roster = dict(copy.deepcopy(self.ROSTER), battle='Battle of Bouillon', date='867.4.12', season='Spring')
        roster['sides'][0]['commander'] = {'name': 'Count John-Matux of Liege'}
        self.generate(roster)
        data = (self.output / 'pack' / probe.LOC).read_bytes()
        self.assertEqual(data[:6], b'\xff\xfeLOC\x00')
        count, pos, rows = struct.unpack_from('<i', data, 10)[0], 14, {}
        for _ in range(count):
            key_len = struct.unpack_from('<H', data, pos)[0]
            key = data[pos + 2:pos + 2 + 2 * key_len].decode('utf-16-le')
            pos += 2 + 2 * key_len
            text_len = struct.unpack_from('<H', data, pos)[0]
            rows[key] = data[pos + 2:pos + 2 + 2 * text_len].decode('utf-16-le')
            pos += 3 + 2 * text_len
        self.assertEqual(pos, len(data))
        self.assertEqual(rows['battles_localised_name_3k_main_historical_battle_xinyang'], 'Battle of Bouillon')
        self.assertEqual(rows['battles_description_3k_main_historical_battle_xinyang'],
                         'Battle of Bouillon (867.4.12, Spring): Count John-Matux of Liege against Defender. '
                         'Crusader Wars 2, Records mode.')

    def test_default_roster_is_the_g1_three_cards(self):
        manifest = self.generate(None)
        self.assertEqual([u['unit_type'] for u in manifest['expected_units']],
                         ['3k_main_general_earth_cao_cao', '3k_main_unit_wood_ji_militia',
                          '3k_main_unit_water_archer_militia', '3k_main_general_earth_liu_bei',
                          '3k_main_unit_wood_ji_militia', '3k_main_unit_water_archer_militia'])

    def test_refuses_unknown_modes_and_generals(self):
        with self.assertRaisesRegex(ValueError, 'Unknown mode'):
            self.generate(dict(self.ROSTER, mode='arcade'))
        # Records general keys are not heroes: staging them in Romance must fail.
        with self.assertRaisesRegex(ValueError, 'not a Romance general'):
            self.generate(dict(self.ROSTER, mode='romance'))
        # Hero keys from the native Romance battle are not Records generals.
        with self.assertRaisesRegex(ValueError, 'not a Records general'):
            self.generate(dict(self.ROMANCE_ROSTER, mode='records'))
        roster = copy.deepcopy(self.ROSTER)
        roster['sides'][1]['generals'][0]['key'] = '3k_main_general_fire_nobody'
        with self.assertRaisesRegex(ValueError, 'not a Records general'):
            self.generate(roster)
        with self.assertRaisesRegex(ValueError, 'two sides'):
            self.generate({'mode': 'records', 'sides': self.ROSTER['sides'][:1]})

if __name__ == '__main__': unittest.main()
