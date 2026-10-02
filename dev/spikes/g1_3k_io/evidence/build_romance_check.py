"""Phase validation: build a real Romance battle pack from the installed game.

Stages a hand-rolled romance roster (hero generals, militia units) through
probe.build with native=None, so the romance Xingyang XML is extracted from the
real data.pack, staged, and packed with the real RPFM CLI. Nothing is installed.
"""
import json
import tempfile
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent          # .../dev/spikes/g1_3k_io/evidence
sys.path.insert(0, str(HERE.parent))            # probe.py lives one folder up
import probe

GAME = probe.GAME
CLI = HERE.parents[2] / 'tools' / 'rpfm' / 'rpfm_cli.exe'

ROSTER = {'mode': 'romance', 'battle': 'Validation battle', 'seed': 424242, 'sides': [
    {'role': 'Attacker', 'name': 'Attacker', 'yours': True, 'fighting': 340.0, 'generals': [
        {'key': '3k_main_hero_metal_generic', 'name': 'Captain 1', 'men': 1, 'units': [
            {'key': '3k_main_unit_wood_ji_militia', 'name': 'Ji Militia', 'men': 80},
            {'key': '3k_main_unit_water_archer_militia', 'name': 'Archer Militia', 'men': 80}]}]},
    {'role': 'Defender', 'name': 'Defender', 'yours': False, 'fighting': 421.0, 'generals': [
        {'key': '3k_main_hero_wood_generic', 'name': 'Captain 1', 'men': 1, 'units': [
            {'key': '3k_main_unit_wood_ji_militia', 'name': 'Ji Militia', 'men': 80},
            {'key': '3k_main_unit_water_archer_militia', 'name': 'Archer Militia', 'men': 80}]}]}]}

with tempfile.TemporaryDirectory() as temp:
    output = Path(temp) / 'run'
    manifest = probe.build(GAME, CLI, output, roster=ROSTER)
    print('mode:', manifest['mode'])
    print('entry:', manifest['entry'])
    print('sides:', [(s['role'], s['men']) for s in manifest['sides']])
    print('units:', [(u['script_name'], u['unit_type'], u['target_men'], u['general'])
                      for u in manifest['expected_units']])
    print('pack sha256:', manifest['pack_sha256'])
    print('lobby mode:', manifest['lobby']['mode'])
    lobby = (output / 'pack' / probe.LOBBY).read_text(encoding='utf-8')
    print('lobby romance flag:', 'local ROMANCE = true;' in lobby)
    battle = (output / 'pack' / probe.BATTLE_ROMANCE / 'battle.xml').read_text(encoding='utf-8')
    print('romance xml game_mode tags:', battle.count('<game_mode>romance</game_mode>'))
    print('records path staged:', (output / 'pack' / probe.BATTLE).exists())