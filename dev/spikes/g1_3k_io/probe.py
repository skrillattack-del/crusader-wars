"""Build the crusader_wars_2 battle pack: a rolled roster staged on the Records Xingyang map."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'lobby'))
import lobby  # the in-game lobby's twui layout and art (lobby/lobby.py)
GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Total War THREE KINGDOMS')
PACK_NAME = 'crusader_wars_2.pack'
BATTLE = 'script/battle/historical_battle/historical_battle_xinyang'
# 3K's frontend loader (script/frontend_mod_scripting.lua) runs every Lua file here.
# The lobby script adds BATTLE > CRUSADER WARS II and opens the staged battle on FIGHT.
LOBBY = 'script/frontend/mod/cw2_lobby.lua'
ROW = 6          # unit cards per formation row
SPACING = 30.0   # metres between cards, across and between rows
CARD_WIDTH = '25.00'
# Staged when no roster is given (the probe CLI): 1 general + 2 units a side, as in G1 runs 1-3.
DEFAULT_ROSTER = {'mode': 'records', 'sides': [
    {'role': 'Attacker', 'name': 'Cao Cao', 'generals': [
        {'key': '3k_main_general_earth_cao_cao', 'name': 'Cao Cao', 'men': 21, 'units': [
            {'key': '3k_main_unit_wood_ji_militia', 'name': 'Ji Militia', 'men': 80},
            {'key': '3k_main_unit_water_archer_militia', 'name': 'Archer Militia', 'men': 80}]}]},
    {'role': 'Defender', 'name': 'Liu Bei', 'generals': [
        {'key': '3k_main_general_earth_liu_bei', 'name': 'Liu Bei', 'men': 21, 'units': [
            {'key': '3k_main_unit_wood_ji_militia', 'name': 'Ji Militia', 'men': 80},
            {'key': '3k_main_unit_water_archer_militia', 'name': 'Archer Militia', 'men': 80}]}]}]}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run_cli(cli, *args):
    result = subprocess.run([str(cli), '--game', 'three_kingdoms', 'pack', *map(str, args)],
                            capture_output=True, text=True, timeout=180,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout or f'RPFM exit {result.returncode}')
    return result.stdout

def _centre(units):
    points = [(float(u.find('position').get('x')), float(u.find('position').get('y'))) for u in units]
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)

def formation(units, generals, centre, facing):
    """Card positions: unit cards in rows of ROW facing the enemy, then the generals in a row behind."""
    fx, fy = facing
    spots = []
    def row(count, depth):
        for c in range(count):
            across = (c - (count - 1) / 2) * SPACING
            spots.append((centre[0] + fy * across - fx * depth, centre[1] - fx * across - fy * depth))
    for first in range(0, units, ROW):
        row(min(ROW, units - first), first // ROW * SPACING)
    row(generals, math.ceil(units / ROW) * SPACING)
    return spots

def _lua_string(text):
    return '"' + str(text).replace('\\', '/').replace('"', '\\"') + '"'

def _lua(value):
    """A Lua 5.1 literal for JSON-like data (the lobby's battle card)."""
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value) if math.isfinite(value) else 'nil'
    if isinstance(value, str):
        escaped = ''.join({'\\': '\\\\', '"': '\\"', '\n': '\\n', '\r': '\\r'}.get(c, c) for c in value)
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return '{' + ', '.join(_lua(v) for v in value) + '}'
    if isinstance(value, dict):
        return '{' + ', '.join(f'[{_lua(str(k))}] = {_lua(v)}' for k, v in value.items()) + '}'
    raise TypeError(f'cannot write {type(value).__name__} as Lua')

def lobby_card(roster, run_id):
    """What the in-game lobby shows: the CK3 battle and the staged roll, per side.

    Units of the same kind are merged into one row (cards and men summed) in
    the order they were rolled.
    """
    sides = []
    for side in roster.get('sides') or []:
        commander = side.get('commander') or {}
        units = {}
        for general in side.get('generals') or []:
            for unit in general.get('units') or []:
                row = units.setdefault(unit.get('name') or unit['key'], {'name': unit.get('name') or unit['key'],
                                                                         'cards': 0, 'men': 0})
                row['cards'] += 1
                row['men'] += int(unit['men'])
        sides.append({'role': side.get('role') or 'Side', 'yours': bool(side.get('yours')),
                      'commander': commander.get('name'), 'martial': commander.get('martial'),
                      'prowess': commander.get('prowess'),
                      'ck3_men': round(float(side['fighting'])) if side.get('fighting') is not None else None,
                      'men': sum(g.get('men', 0) for g in side.get('generals') or [])
                             + sum(u['men'] for u in units.values()),
                      'generals': [g.get('name') for g in side.get('generals') or []],
                      'units': list(units.values())})
    return {'run_id': run_id, 'battle': roster.get('battle') or 'CK3 battle', 'date': roster.get('date'),
            'season': roster.get('season'), 'mode': 'Records', 'seed': roster.get('seed'), 'sides': sides}

def lobby_script(run_id, battle_log, frontend_log, card, template=None):
    """frontend_lobby.lua bound to one run: its logs, the lobby layout and its battle card."""
    path = lambda p: str(p).replace('\\', '/').replace('"', '\\"')
    script = Path(template or HERE / 'frontend_lobby.lua').read_text(encoding='utf-8')
    return (script.replace('@@RUN_ID@@', run_id)
            .replace('@@OUTPUT_PATH@@', path(battle_log))
            .replace('@@FRONTEND_LOG@@', path(frontend_log))
            .replace('@@LAYOUT@@', lobby.LAYOUT_PATH.removesuffix('.twui.xml'))
            .replace('@@LOBBY@@', _lua(card)))

def generate(native, output, lua_template, roster=None, lobby_template=None):
    """Stage `roster` (bridge.roll_roster's result) on the natively installed Records Xingyang map."""
    roster = roster or DEFAULT_ROSTER
    if roster.get('mode', 'records') != 'records':
        raise ValueError('Romance battles are not staged yet; roll the armies in Records mode.')
    sides = roster.get('sides') or []
    if len(sides) != 2 or not all(s.get('generals') for s in sides):
        raise ValueError('The roster needs two sides, each led by at least one general.')
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
    alliances = root.findall('alliance')[:2]
    centres = [_centre(alliance.find('army').findall('unit')) for alliance in alliances]
    expected, staged = [], []
    # 3K seats the player in the first alliance, so the CK3 player's side goes there.
    order = sorted(range(2), key=lambda i: not sides[i].get('yours'))
    for a, (i, alliance) in enumerate(zip(order, alliances)):
        side, spec = ('attacker', 'defender')[i], sides[i]
        army = alliance.find('army')
        orientation = army.find('unit/orientation')
        faction = 'cao_cao' if a == 0 else 'liu_bei'  # the faction only picks banner colours
        army.find('faction').text = '3k_main_faction_' + faction
        for child in list(army):
            if child.tag in ('unit', 'reinforcement_army'):
                army.remove(child)
        generals = spec['generals']
        cards = ([(g, general, True) for g, general in enumerate(generals)]
                 + [(g, unit, False) for g, general in enumerate(generals) for unit in general.get('units', [])])
        (cx, cy), (ex, ey) = centres[a], centres[1 - a]
        distance = math.hypot(ex - cx, ey - cy)
        spots = formation(len(cards) - len(generals), len(generals), centres[a],
                          ((ex - cx) / distance, (ey - cy) / distance))
        spots = spots[len(cards) - len(generals):] + spots[:len(cards) - len(generals)]  # generals first
        for n, ((g, card, is_general), (x, y)) in enumerate(zip(cards, spots)):
            key, men = card['key'], int(card['men'])
            if men <= 0:
                raise ValueError(f'{card.get("name", key)} has no men.')
            if is_general and key not in general_sources:
                raise ValueError(f'{key} is not a Records general in the native battles.')
            unit = ET.Element('unit', script_name=f'cw2_{side}_{n}')
            ET.SubElement(unit, 'unit_type', type=key)
            ET.SubElement(unit, 'retinue', id=str(g))
            ET.SubElement(unit, 'position', x=f'{x:.2f}', y=f'{y:.2f}')
            unit.append(copy.deepcopy(orientation))
            ET.SubElement(unit, 'width', metres=CARD_WIDTH)
            ET.SubElement(unit, 'unit_experience', level='0')
            if is_general:
                general = copy.deepcopy(general_sources[key].find('general'))
                general.find('commander_type').text = 'commanding_general' if g == 0 else 'non_commanding_general'
                general.find('commander_id').text = str(g)
                unit.append(general)
            army.append(unit)
            expected.append({'script_name': unit.get('script_name'), 'unit_type': key,
                             'name': card.get('name', key), 'alliance': a + 1, 'side': side,
                             'general': is_general, 'general_index': g, 'target_men': men})
        staged.append({'role': spec.get('role', side.title()), 'name': spec.get('name', side.title()),
                       'fighting': spec.get('fighting'),
                       'men': sum(u['target_men'] for u in expected if u['alliance'] == a + 1)})
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
    # A stale log from a previous run at this output path must not survive;
    # read_result compares the log's units against the new manifest.
    if log.exists():
        log.unlink()
    trim = '{' + ', '.join(f'[{_lua_string(u["script_name"])}] = {u["target_men"]}' for u in expected) + '}'
    lua = lua_template.read_text(encoding='utf-8').replace('@@RUN_ID@@', run_id).replace('@@BATTLE@@', BATTLE)
    # JSON quoting yields Lua-compatible escaping for an ASCII Windows path.
    lua = lua.replace('@@OUTPUT_PATH@@', str(log).replace('\\', '/').replace('"', '\\"'))
    lua = lua.replace('@@TRIM@@', trim)
    (stage / 'battle_script.lua').write_text(lua, encoding='utf-8')
    card = lobby_card(roster, run_id)
    script = lobby_script(run_id, log, output.resolve() / 'frontend.log', card,
                          lobby_template or lua_template.parent / 'frontend_lobby.lua')
    (output / 'pack' / LOBBY).parent.mkdir(parents=True, exist_ok=True)
    (output / 'pack' / LOBBY).write_text(script, encoding='utf-8')
    lobby.stage(output / 'pack')
    manifest = {'schema': 1, 'kind': 'g1_runtime_unverified', 'run_id': run_id,
                'mode': 'Records', 'entry': BATTLE, 'source_sha256': digest(source),
                'log_path': str(log), 'sides': staged, 'expected_units': expected, 'lobby': card}
    (output / 'run.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest

def build(game, cli, output, native=None, roster=None):
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
    manifest = generate(Path(native), output, HERE / 'probe.lua', roster)
    pack = output / PACK_NAME
    run_cli(cli, 'create', '--pack-path', pack)
    # Bundled RPFM creates PFH5 mod packs (type 3). Its set-file-type command
    # panics in this old build; validate the newly created header instead.
    if pack.read_bytes()[:8] != b'PFH5\x03\x00\x00\x00':
        raise ValueError('RPFM did not create the expected PFH5 mod pack.')
    files = [f'{BATTLE}/battle.xml', f'{BATTLE}/battle_script.lua', LOBBY, lobby.LAYOUT_PATH, *lobby.ART]
    for name in files:
        run_cli(cli, 'add', '--pack-path', pack, '--file-path', f'{output / "pack" / name};{name}')
    listed = run_cli(cli, 'list', '--pack-path', pack).splitlines()
    if sorted(listed) != sorted(files):
        raise ValueError('Pack contents do not match the staged battle files.')
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
        units = list(event['units'])
        loaded_names = {u['script_name'] for u in units}
        expected_names = set(expected)
        is_start = event is starts[0]
        extra = loaded_names - expected_names
        if len(units) != len(loaded_names):
            raise ValueError('Duplicate unit in the battle capture.')
        if extra:
            raise ValueError(f'Loaded roster differs from the staged roster '
                             f'(extra: {", ".join(sorted(extra))}). '
                             'Close Three Kingdoms, send the armies again, and re-launch.')
        if is_start:
            # The start capture must match the staged roster exactly.
            if loaded_names != expected_names:
                missing = expected_names - loaded_names
                raise ValueError(f'Loaded roster differs from the staged roster '
                                 f'(missing at start: {", ".join(sorted(missing))}). '
                                 'Close Three Kingdoms, send the armies again, and re-launch.')
        else:
            # Final capture: 3K drops units destroyed in battle (0 survivors).
            # Inject them back as fully lost so the report counts every staged unit.
            for name in sorted(expected_names - loaded_names):
                match = expected[name]
                units.append({'script_name': name, 'unit_type': match['unit_type'],
                              'alliance': match['alliance'], 'army': 1,
                              'initial': start_counts[name], 'survivors': 0, 'routing': True})
            event['units'] = units
        for unit in units:
            match = expected[unit['script_name']]
            if unit['unit_type'] != match['unit_type'] or unit['alliance'] != match['alliance'] or unit['army'] != 1:
                raise ValueError('Unit type, side or army mismatch.')
            initial, alive = unit['initial'], unit['survivors']
            if type(unit.get('routing')) is not bool:
                raise ValueError('Missing routing state.')
            if type(initial) is not int or type(alive) is not int or not 0 <= alive <= initial or initial <= 0:
                raise ValueError('Invalid soldier counts.')
            if is_start:
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
