"""Read-only CK3 save intake and synthetic-result planning. No save edits yet."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|#[^\r\n]*|[{}]')
SECTIONS = ('combats', 'armies', 'army_regiments', 'regiments', 'combat_results')

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def block_end(text, start):
    depth = 0
    for match in TOKENS.finditer(text, start):
        if match.group() == '{': depth += 1
        elif match.group() == '}':
            depth -= 1
            if depth == 0: return match.end()
    raise ValueError('Unclosed save block; refusing to interpret it.')

def blocks(text, key):
    # Only direct children: CK3 has armies.armies and combats.combats, plus
    # many nested regiment/army lists with the same names.
    pattern = re.compile(r'"(?:\\.|[^"\\])*"|#[^\r\n]*|(?P<key>[A-Za-z_0-9]+)\s*=\s*\{|[{}]')
    level = 1 if text.lstrip().startswith('{') else 0
    depth = 0
    found = []
    for match in pattern.finditer(text):
        if match.group('key'):
            if depth == level and match.group('key') == key:
                found.append(text[match.end()-1:block_end(text, match.end()-1)])
            depth += 1
        elif match.group() == '{': depth += 1
        elif match.group() == '}': depth -= 1
    return found

def unique(text, key):
    found = blocks(text, key)
    if len(found) != 1: raise ValueError(f'Expected one {key} block, found {len(found)}.')
    return found[0]

def scalar(text, key):
    matches = re.findall(r'(?m)^\s*' + re.escape(key) + r'\s*=\s*([^\s{}]+)', text)
    if len(matches) != 1: raise ValueError(f'Expected one scalar {key}.')
    return matches[0]

def read_gamestate(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries = [e for e in archive.infolist() if e.filename == 'gamestate']
            if len(entries) != 1: raise ValueError('Archive must contain exactly one gamestate member.')
            if entries[0].file_size > 512 * 1024 * 1024: raise ValueError('Gamestate exceeds spike size limit.')
            data = archive.read(entries[0])
        kind = 'zip'
    else:
        data = Path(path).read_bytes()
        kind = 'plain'
    if b'\x00' in data[:65536]:
        raise ValueError('Binary/tokenized save unsupported. Supply a plaintext/debug save; do not guess token mappings.')
    try: text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc: raise ValueError('Save is not supported UTF-8 plaintext.') from exc
    if 'meta_data={' not in text and 'meta_data = {' not in text:
        raise ValueError('No recognized CK3 text metadata.')
    return text, kind

def inventory(text):
    army_manager, combat_manager = unique(text, 'armies'), unique(text, 'combats')
    sections = {key: unique(combat_manager if key in ('combats', 'combat_results') else army_manager, key) for key in SECTIONS}
    return {'combats': combat_rows(sections['combats']),
            'section_characters': {k: len(v) for k, v in sections.items()}}, sections

def combat_rows(combat):
    # Match only immediate child records, skipping their nested blocks intact.
    records = []
    pos = 1
    record_re = re.compile(r'\s*(\d+)\s*=\s*(\{|none)')
    while pos < len(combat)-1:
        match = record_re.match(combat, pos)
        if not match:
            if not combat[pos:-1].strip(): break
            raise ValueError('Unexpected combat-table syntax.')
        pos = match.end()
        if match[2] == 'none': continue
        end = block_end(combat, pos-1)
        record = combat[pos-1:end]
        row = {'combat_id': match[1]}
        for side in ('attacker', 'defender'):
            body = unique(record, side)
            army_ids = unique(body, 'armies')[1:-1].split()
            if not army_ids or any(not x.isdecimal() for x in army_ids):
                raise ValueError('Unsupported combat army list.')
            
            commander_match = re.search(r'(?m)^\s*commander=(\d+)', body)
            commander = commander_match.group(1) if commander_match else None
            leader_match = re.search(r'(?m)^\s*leader=(\d+)', body)
            leader = leader_match.group(1) if leader_match else None
            char_ids = re.findall(r'(?m)character=\{\s*character=(\d+)', body)
            
            row[side] = {'army_ids': army_ids,
                         'initial_men': scalar(body, 'initial_men'),
                         'total_fighting_men': scalar(body, 'total_fighting_men'),
                         'commander': commander,
                         'leader': leader,
                         'characters': char_ids}
        row['phase'] = scalar(record, 'phase')
        records.append(row)
        pos = end
    return records

def intake(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file(): raise ValueError('Save does not exist.')
    # Exclusive directory creation prevents overwriting or silently reusing evidence.
    destination.mkdir(parents=True, exist_ok=False)
    snapshot = destination / 'before.ck3'
    first_hash = sha(source)
    with source.open('rb') as src, snapshot.open('xb') as dst:
        while chunk := src.read(1024 * 1024): dst.write(chunk)
    fingerprint = sha(snapshot)
    if fingerprint != first_hash or sha(source) != first_hash:
        raise ValueError('Source changed during capture. Retain this failed attempt and use a new directory.')
    text, kind = read_gamestate(snapshot)
    report, sections = inventory(text)
    (destination / 'sections').mkdir()
    for key, value in sections.items():
        (destination / 'sections' / f'{key}.txt').write_text(value, encoding='utf-8')
    report.update(schema=1, status='inspection_only_no_patch', source_path=str(source),
                  save_fingerprint=fingerprint, container=kind,
                  warning='Combat totals and cached counts are observations, not proven writable authorities.')
    (destination / 'inventory.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report

def plan(directory, combat_id):
    directory = Path(directory)
    report = json.loads((directory / 'inventory.json').read_text(encoding='utf-8'))
    if sha(directory / 'before.ck3') != report['save_fingerprint']:
        raise ValueError('Snapshot fingerprint changed.')
    # Re-derive identities from the snapshot, not an editable inventory file.
    actual, _ = inventory(read_gamestate(directory / 'before.ck3')[0])
    matches = [c for c in actual['combats'] if c['combat_id'] == combat_id]
    if len(matches) != 1: raise ValueError('Combat not found in snapshot.')
    combat = matches[0]
    if set(combat['attacker']['army_ids']) & set(combat['defender']['army_ids']):
        raise ValueError('Same army appears on both sides.')
    result = {'schema': 1, 'kind': 'synthetic_g2_plan_not_applied',
              'save_fingerprint': report['save_fingerprint'], 'battle_id': combat_id,
              'outcome': 'attacker', 'outcome_source': 'synthetic_not_3k_callback',
              'sides': {}, 'status': 'prepared_not_applied'}
    for side, loss in [('attacker', 38), ('defender', 75)]:
        from decimal import Decimal
        observed = Decimal(combat[side]['total_fighting_men'])
        if not observed.is_finite() or observed < loss:
            raise ValueError(f'{side} has insufficient observed fighting strength for this fixture.')
        result['sides'][side] = dict(combat[side], synthetic_casualties=loss)
    # Semantic identity excludes arbitrary user-supplied result IDs.
    result['result_id'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    path = directory / 'synthetic_result.json'
    with path.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2); output.write('\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    capture = sub.add_parser('intake'); capture.add_argument('--save', required=True, type=Path); capture.add_argument('--out', required=True, type=Path)
    prepare = sub.add_parser('plan'); prepare.add_argument('--run', required=True, type=Path); prepare.add_argument('--combat-id', required=True)
    args = parser.parse_args()
    value = intake(args.save, args.out) if args.action == 'intake' else plan(args.run, args.combat_id)
    print(json.dumps(value, indent=2))

if __name__ == '__main__': main()
