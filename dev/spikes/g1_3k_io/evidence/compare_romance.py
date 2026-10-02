"""Phase 0 spike: compare the native Romance Xingyang battle.xml with the Records one."""
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / 'romance_native' / 'script' / 'battle' / 'historical_battle'
RECORDS = HERE.parent / 'generated' / 'native' / 'script' / 'battle' / 'historical_battle'


def load(path):
    return ET.parse(path).getroot()


def dump(root, label):
    print(f'== {label} ==')
    print('root tag:', root.tag, 'attrs:', dict(root.attrib))
    print('top children:', [c.tag for c in root])
    bd = root.find('battle_description')
    if bd is not None:
        print('battle_description children:', [(c.tag, dict(c.attrib), (c.text or '').strip()[:60]) for c in bd])
    for ai, alliance in enumerate(root.findall('alliance')):
        print(f'-- alliance {ai} children:', [c.tag for c in alliance])
        print('   alliance attrs:', dict(alliance.attrib))
        armies = alliance.findall('army')
        print('   armies:', len(armies))
        for u in armies[0].findall('unit'):
            ut = u.find('unit_type')
            g = u.find('general')
            gm = g.findtext('game_mode') if g is not None else None
            print('   unit script_name=', u.get('script_name'),
                  'type=', ut.get('type') if ut is not None else None,
                  'game_mode=', gm)
        for u in alliance.iter('unit'):
            g = u.find('general')
            if g is not None:
                ut = u.find('unit_type')
                print(f'   GENERAL: type={ut.get("type") if ut is not None else None}',
                      'game_mode=', g.findtext('game_mode'),
                      'subtype=', g.findtext('subtype_name'),
                      'commander_type=', g.findtext('commander_type'),
                      'commander_id=', g.findtext('commander_id'))
                print('      general children:', [c.tag for c in g])
    print()


rom = load(BASE / 'historical_battle_xinyang_romance' / 'battle.xml')
rec = load(RECORDS / 'historical_battle_xinyang' / 'battle.xml')
dump(rec, 'RECORDS xinyang battle.xml')
dump(rom, 'ROMANCE xinyang battle.xml')

print('== diff of unit_type keys per alliance ==')
for label, root in (('records', rec), ('romance', rom)):
    for ai, alliance in enumerate(root.findall('alliance')):
        types = []
        for u in alliance.iter('unit'):
            ut = u.find('unit_type')
            g = u.find('general')
            types.append((ut.get('type') if ut is not None else None,
                          'G' if g is not None else '',
                          g.findtext('game_mode') if g is not None else None))
        print(label, 'alliance', ai, types)