import sys
import os
import json
import re
import hashlib
from pathlib import Path

# Add g2_ck3_writeback/patcher to sys.path to reuse preflight.py logic
_HERE = Path(__file__).resolve().parent
_PATCHER_DIR = _HERE.parents[0] / 'g2_ck3_writeback' / 'patcher'
if str(_PATCHER_DIR) not in sys.path:
    sys.path.insert(0, str(_PATCHER_DIR))

import preflight

def extract_prowess(text, char_id):
    """Extract the prowess skill for a given character ID from the gamestate."""
    # Characters in CK3 are usually indented with 0 or 1 tab in the gamestate.
    # We search for the block and look for 'skill='
    markers = [f"\n{char_id}={{", f"\n\t{char_id}={{"]
    for marker in markers:
        start = text.find(marker)
        while start != -1:
            block_start = start + len(marker) - 1
            try:
                end = preflight.block_end(text, block_start)
            except ValueError:
                break
            block = text[block_start:end]
            skills_match = re.search(r'skill=\{([^}]+)\}', block)
            if skills_match:
                skills = skills_match.group(1).strip().split()
                if len(skills) >= 6:
                    return int(skills[5])
            start = text.find(marker, start + 1)
    
    return 0

def extract_encounter(save_path, output_manifest, combat_id=None):
    save_path = Path(save_path)
    if not save_path.is_file():
        raise ValueError(f"Save file {save_path} does not exist.")
        
    save_fingerprint = preflight.sha(save_path)
    text, kind = preflight.read_gamestate(save_path)
    
    # Fast combat block extraction
    marker = '\ncombats={'
    start = text.find(marker)
    if start < 0 or text.find(marker, start + 1) >= 0:
        combats_block = preflight.unique(text, 'combats')
    else:
        start += len(marker) - 1
        combats_block = text[start:preflight.block_end(text, start)]
        
    combats = preflight.combat_rows(preflight.unique(combats_block, 'combats'))
    if not combats:
        raise ValueError("No active combats in save.")
        
    if combat_id:
        chosen = next((c for c in combats if c['combat_id'] == str(combat_id)), None)
        if not chosen:
            raise ValueError(f"Combat {combat_id} not found.")
    else:
        # Pick the largest combat
        chosen = max(combats, key=lambda c: float(c['attacker']['initial_men']) + float(c['defender']['initial_men']))
        
    sides = []
    for side_name in ('attacker', 'defender'):
        side_data = chosen[side_name]
        prowess_sources = []
        classified = set()
        
        commander = side_data.get('commander')
        if commander:
            prowess_sources.append({
                'id': commander,
                'role': 'commander',
                'prowess': extract_prowess(text, commander)
            })
            classified.add(commander)

        leader = side_data.get('leader')
        if leader and leader not in classified:
            prowess_sources.append({
                'id': leader,
                'role': 'leader',
                'prowess': extract_prowess(text, leader)
            })
            classified.add(leader)
            
        for cid in side_data.get('characters', []):
            if cid in classified:
                continue
            prowess_sources.append({
                'id': cid,
                # Save combat contribution records do not prove knight status.
                # The CW2 CK3 mod exports actual every_side_knight identities.
                'role': 'combat_participant_unclassified',
                'prowess': extract_prowess(text, cid)
            })
            classified.add(cid)
            
        sides.append({
            'role': side_name,
            'source_army_ids': side_data['army_ids'],
            'starting_strengths': float(side_data['initial_men']),
            'prowess': prowess_sources
        })
        
    # Generate seed from fingerprint + combat_id to ensure reproducible random rolls later
    seed_str = save_fingerprint + chosen['combat_id']
    seed = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    
    manifest = {
        'schema': 1,
        'kind': 'BattleManifest',
        'save_fingerprint': save_fingerprint,
        'encounter_id': f"ck3:{chosen['combat_id']}",
        'seed': seed,
        'sides': sides
    }
    
    if output_manifest:
        out_path = Path(output_manifest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    
    return manifest

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='CK3 Encounter Extractor (E1)')
    parser.add_argument('save', help='Path to CK3 save file')
    parser.add_argument('output', help='Path to output JSON manifest')
    parser.add_argument('--combat', help='Specific combat ID to extract', default=None)
    args = parser.parse_args()
    extract_encounter(args.save, args.output, args.combat)
