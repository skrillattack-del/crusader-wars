"""Build a reversible 3K-native historical-battle experiment, not a CK3 port."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Total War THREE KINGDOMS')
PACK_NAME = 'cw2_g1_probe.pack'
BATTLE = 'script/battle/historical_battle/historical_battle_xinyang'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run_cli(cli, *args):
    result = subprocess.run([str(cli), '--game', 'three_kingdoms', 'pack', *map(str, args)],
                            capture_output=True, text=True, timeout=180,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout or f'RPFM exit {result.returncode}')
    return result.stdout

def generate(native, output, lua_template):
    """Reuse only locally installed native metadata and map; emit six unique units."""
    source = native / BATTLE / 'battle.xml'
    root = ET.parse(source).getroot()
    general_sources = {}
    for name in ('historical_battle_xinyang', 'historical_battle_red_cliff'):
        path = native / 'script/battle/historical_battle' / name / 'battle.xml'
        for unit in ET.parse(path).getroot().iter('unit'):
            kind = unit.find('unit_type')
            if kind is not None and unit.findtext('general/game_mode') == 'historical':
                general_sources.setdefault(kind.get('type'), unit)
    run_id = uuid.uuid4().hex
    expected = []
    for a, side in enumerate(('attacker', 'defender')):
        alliance = root.findall('alliance')[a]
        army = alliance.find('army')
        originals = army.findall('unit')
        faction = 'cao_cao' if a == 0 else 'liu_bei'
        army.find('faction').text = '3k_main_faction_' + faction
        for child in list(army):
            if child.tag in ('unit', 'reinforcement_army'):
                army.remove(child)
        types = ['3k_main_general_earth_' + faction,
                 '3k_main_unit_wood_ji_militia', '3k_main_unit_water_archer_militia']
        for i, kind in enumerate(types):
            unit = ET.Element('unit', script_name=f'cw2_{side}_{i}')
            ET.SubElement(unit, 'unit_type', type=kind)
            ET.SubElement(unit, 'retinue', id='0')
            for tag in ('position', 'orientation', 'width'):
                unit.append(copy.deepcopy(originals[i].find(tag)))
            ET.SubElement(unit, 'unit_experience', level='0')
            if i == 0:
                general = copy.deepcopy(general_sources[kind].find('general'))
                general.find('commander_type').text = 'commanding_general'
                general.find('commander_id').text = '0'
                unit.append(general)
            army.append(unit)
            expected.append({'script_name': unit.get('script_name'), 'unit_type': kind,
                             'alliance': a + 1, 'side': side, 'general': i == 0})
        for other in list(alliance.findall('army'))[1:]:
            alliance.remove(other)
        victory = alliance.find('victory_condition')
        if victory is not None:
            alliance.remove(victory)
        ET.SubElement(ET.SubElement(alliance, 'victory_condition'), 'kill_or_rout_enemy')
    root.find('battle_description/battle_script').set('prepare_for_fade_in', 'false')
    stage = output / 'pack' / BATTLE
    stage.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(stage / 'battle.xml', encoding='utf-8', xml_declaration=True)
    log = output.resolve() / f'{run_id}.jsonl'
    lua = lua_template.read_text(encoding='utf-8').replace('@@RUN_ID@@', run_id).replace('@@BATTLE@@', BATTLE)
    # JSON quoting yields Lua-compatible escaping for an ASCII Windows path.
    lua = lua.replace('@@OUTPUT_PATH@@', str(log).replace('\\', '/').replace('"', '\\"'))
    (stage / 'battle_script.lua').write_text(lua, encoding='utf-8')
    manifest = {'schema': 1, 'kind': 'g1_runtime_unverified', 'run_id': run_id,
                'mode': 'Records', 'entry': BATTLE, 'source_sha256': digest(source),
                'log_path': str(log), 'expected_units': expected,
                'candidate_change': 'Liu Bei uses native Records general instead of original hero candidate.'}
    (output / 'run.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest

def build(game, cli, output, native=None):
    game, cli, output = Path(game), Path(cli), Path(output)
    if not (game / 'Three_Kingdoms.exe').is_file() or not cli.is_file():
        raise ValueError('Select the installed Three Kingdoms folder and rpfm_cli.exe.')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'run.json').exists():
        raise ValueError('Choose a fresh output directory; existing run evidence is immutable.')
    if native is None:
        native = output / 'native'
        run_cli(cli, 'extract', '--pack-path', game / 'data/data.pack',
                '--file-path', f'{BATTLE}/battle.xml;{native}',
                '--file-path', f'script/battle/historical_battle/historical_battle_red_cliff/battle.xml;{native}')
    manifest = generate(Path(native), output, HERE / 'probe.lua')
    pack = output / PACK_NAME
    run_cli(cli, 'create', '--pack-path', pack)
    # Bundled RPFM creates PFH5 mod packs (type 3). Its set-file-type command
    # panics in this old build; validate the newly created header instead.
    if pack.read_bytes()[:8] != b'PFH5\x03\x00\x00\x00':
        raise ValueError('RPFM did not create the expected PFH5 mod pack.')
    for name in ('battle.xml', 'battle_script.lua'):
        run_cli(cli, 'add', '--pack-path', pack, '--file-path', f'{output / "pack" / BATTLE / name};{BATTLE}/{name}')
    listed = run_cli(cli, 'list', '--pack-path', pack).splitlines()
    if sorted(listed) != sorted(f'{BATTLE}/{n}' for n in ('battle.xml', 'battle_script.lua')):
        raise ValueError('Pack contents do not match the two-file experiment.')
    manifest['pack_sha256'] = digest(pack)
    (output / 'run.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest

def install(game, output):
    source, target = Path(output) / PACK_NAME, Path(game) / 'data' / PACK_NAME
    manifest = json.loads((Path(output) / 'run.json').read_text(encoding='utf-8'))
    if digest(source) != manifest['pack_sha256']:
        raise ValueError('Built pack differs from the run manifest.')
    if target.exists() and digest(target) != digest(source):
        raise ValueError('A different probe pack is installed. Remove it with its original run first.')
    shutil.copy2(source, target)
    return target

def uninstall(game, output):
    target = Path(game) / 'data' / PACK_NAME
    if target.exists():
        manifest = json.loads((Path(output) / 'run.json').read_text(encoding='utf-8'))
        if digest(target) != manifest['pack_sha256']:
            raise ValueError('Installed pack differs from this run; refusing to remove it.')
        target.unlink()

def read_result(output):
    manifest = json.loads((Path(output) / 'run.json').read_text(encoding='utf-8'))
    path = Path(manifest['log_path'])
    if not path.exists():
        raise ValueError('No runtime log yet. The probe has not demonstrated that it loaded.')
    events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(e.get('run_id') != manifest['run_id'] or e.get('schema') != 1 for e in events):
        raise ValueError('Foreign or unsupported runtime event.')
    starts = [e for e in events if e.get('phase') == 'start']
    finals = [e for e in events if e.get('phase') in ('result', 'complete', 'routing_state')]
    if len(starts) != 1 or not finals or events.index(starts[0]) >= events.index(finals[-1]):
        raise ValueError('Need exactly one start and one result; rebuild for each battle attempt.')
    expected = {u['script_name']: u for u in manifest['expected_units']}
    start_counts = {}
    for event in (starts[0], finals[-1]):
        if event.get('battle') != manifest['entry']:
            raise ValueError('Event battle identifier differs from the staged battle.')
        units = event['units']
        if len(units) != len(expected) or {u['script_name'] for u in units} != set(expected):
            raise ValueError('Loaded roster differs from the staged six unique units.')
        for unit in units:
            match = expected[unit['script_name']]
            if unit['unit_type'] != match['unit_type'] or unit['alliance'] != match['alliance'] or unit['army'] != 1:
                raise ValueError('Unit type, side or army mismatch.')
            initial, alive = unit['initial'], unit['survivors']
            if type(unit.get('routing')) is not bool:
                raise ValueError('Missing routing state.')
            if type(initial) is not int or type(alive) is not int or not 0 <= alive <= initial or initial <= 0:
                raise ValueError('Invalid soldier counts.')
            if event is starts[0]:
                if alive != initial:
                    raise ValueError('Initial capture is inconsistent.')
                start_counts[unit['script_name']] = initial
            elif initial != start_counts[unit['script_name']]:
                raise ValueError('Starting count changed between captures.')
    won = finals[-1].get('player_won')
    source = finals[-1].get('result_source') or finals[-1].get('phase')
    if source == 'complete':
        source = 'routing_state'
    if won is None:
        alliance_1_routing = all(u['routing'] for u in finals[-1]['units'] if u['alliance'] == 1)
        alliance_2_routing = all(u['routing'] for u in finals[-1]['units'] if u['alliance'] == 2)
        if alliance_2_routing and not alliance_1_routing:
            won = True
        elif alliance_1_routing and not alliance_2_routing:
            won = False
    
    if type(won) is not bool:
        raise ValueError('Outcome undetermined: no engine result and no single fully broken side.')
    if source not in ('engine_callback', 'routing_state'):
        raise ValueError('Unknown or missing result source.')
    late = [e for e in events if e.get('phase') == 'engine_result']
    if late and (len(late) > 1 or late[0].get('player_won') != won
                 or late[0].get('battle') != manifest['entry']):
        raise ValueError('Late engine result contradicts the recorded outcome.')
    # The historical slot seats the player in alliance 1; the manifest says which side that is.
    side_of = {1: 'attacker', 2: 'defender'}
    side_of.update({u['alliance']: u['side'] for u in manifest['expected_units'] if 'side' in u})
    player, enemy = side_of[1], side_of[2]
    if source == 'routing_state':
        # Non-victory here means the player's side was the one fully broken.
        limitation = 'Outcome derived from unit state at Complete (every unit of one side routing or dead), not the Battle Results command.'
        winner = player if won else enemy
    else:
        # The engine reports a bool, not a draw enum. Preserve that limitation.
        limitation = 'Non-victory does not distinguish defeat, draw or abandonment.'
        winner = player if won else None
    result = {'kind': 'g1_observation_not_ck3_result', 'run_id': manifest['run_id'],
              'battle': manifest['entry'],
              'player_side': player,
              'player_outcome': 'victory' if won else 'non_victory',
              'winner': winner,
              'result_source': source,
              'limitation': limitation,
              'units': finals[-1]['units']}
    (Path(output) / 'observed_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'install', 'uninstall', 'read'])
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--cli', type=Path, default=HERE.parents[1] / 'tools/rpfm/rpfm_cli.exe')
    parser.add_argument('--output', type=Path, default=HERE / 'generated')
    parser.add_argument('--native', type=Path)
    args = parser.parse_args()
    if args.action == 'build': result = build(args.game, args.cli, args.output, args.native)
    elif args.action == 'install': result = str(install(args.game, args.output))
    elif args.action == 'uninstall': result = uninstall(args.game, args.output)
    else: result = read_result(args.output)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
