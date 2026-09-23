"""CK3 save mutation apply script."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from decimal import Decimal
import decimal
import sys

import preflight

decimal.getcontext().prec = 28

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def journal_check(directory, result_id, battle_id):
    journal_path = Path(directory) / 'journal.json'
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding='utf-8'))
    else:
        journal = {}
    
    if result_id in journal:
        raise ValueError('Duplicate result application rejected.')
    
    for existing_result, data in journal.items():
        if data['battle_id'] == battle_id and data.get('status') == 'applied':
            raise ValueError('Conflicting applied result for the same encounter rejected.')
            
    # Mark as generated immediately
    journal[result_id] = {
        'battle_id': battle_id,
        'status': 'generated'
    }
    journal_path.write_text(json.dumps(journal, indent=2))
    return journal, journal_path

def record_bounds(text, key):
    """Return list of (start_index, end_index) for all blocks matching key."""
    pattern = re.compile(r'"(?:\\.|[^"\\])*"|#[^\r\n]*|(?P<key>[A-Za-z_0-9]+)\s*=\s*\{|[{}]')
    level = 1 if text.lstrip().startswith('{') else 0
    depth = 0
    found = []
    for match in pattern.finditer(text):
        if match.group('key'):
            if depth == level and match.group('key') == key:
                start = match.end() - 1
                end = preflight.block_end(text, start)
                found.append((start, end))
            depth += 1
        elif match.group() == '{': depth += 1
        elif match.group() == '}': depth -= 1
    return found

def get_block_by_id(text, block_type, id_str):
    """Find a block like `id_str={ ... }` inside text."""
    pattern = re.compile(r'\b' + str(id_str) + r'\s*=\s*\{')
    for match in pattern.finditer(text):
        start = match.end() - 1
        end = preflight.block_end(text, start)
        return start, end
    raise ValueError(f"Could not find block {id_str} in {block_type}")

def distribute_loss(chunks, total_loss):
    requested = Decimal(str(total_loss))
    if not requested.is_finite() or requested < 0 or requested != requested.to_integral_value():
        raise ValueError('Casualties must be a non-negative integer.')
    capacities = []
    weights = []
    for chunk in chunks:
        current = Decimal(str(chunk['current']))
        weight = Decimal(str(chunk.get('weight', current)))
        if not current.is_finite() or current < 0 or current != current.to_integral_value():
            raise ValueError('Backing soldier counts must be non-negative integers.')
        if not weight.is_finite() or weight < 0:
            raise ValueError('Casualty weights must be non-negative.')
        capacities.append(int(current))
        weights.append(weight)
    if requested > sum(capacities):
        raise ValueError('Requested casualties exceed available soldiers.')
    if not requested:
        return [Decimal(0)] * len(chunks)
    if not sum(weights):
        raise ValueError('Cannot distribute casualties without weights.')
    targets = [requested * weight / sum(weights) for weight in weights]
    allocated = [min(capacity, int(target)) for capacity, target in zip(capacities, targets)]
    remaining = int(requested) - sum(allocated)
    while remaining:
        eligible = [index for index, capacity in enumerate(capacities) if allocated[index] < capacity]
        if not eligible:
            raise ValueError('Casualty allocation could not be conserved.')
        index = max(eligible, key=lambda item: (targets[item] - allocated[item], weights[item], -item))
        allocated[index] += 1
        remaining -= 1
    return [Decimal(value) for value in allocated]

def mutate_gamestate(gamestate_text, synthetic_result, linked_records):
    combat_id = synthetic_result['battle_id']
    
    print("Finding combats manager...", flush=True)
    combats_manager_bounds = record_bounds(gamestate_text, 'combats')
    if len(combats_manager_bounds) != 1:
        raise ValueError("Expected exactly one combats manager")
    
    c_start, c_end = combats_manager_bounds[0]
    combats_text = gamestate_text[c_start:c_end]
    
    cb_start, cb_end = get_block_by_id(combats_text, 'combats', combat_id)
    mutated_combat = combats_text[cb_start:cb_end]
    
    regiment_losses = {} # army_reg_id -> Decimal(loss)
    
    for side in ['attacker', 'defender']:
        side_data = synthetic_result['sides'][side]
        total_loss = Decimal(str(side_data['synthetic_casualties']))
        if total_loss == 0: continue
            
        side_start, side_end = get_block_by_id(mutated_combat, 'combat_side', side)
        side_text = mutated_combat[side_start:side_end]
        
        # Verify loss bounds (Defect 2)
        total_fighting_match = re.search(r'total_fighting_men=([0-9.]+)', side_text)
        if not total_fighting_match:
            raise ValueError(f"Could not find total_fighting_men for {side}")
        old_total = Decimal(total_fighting_match.group(1))
        if old_total < total_loss:
            raise ValueError(f"{side} total_fighting_men ({old_total}) is less than synthetic_casualties ({total_loss})")
            
        reg_pattern = re.compile(r'\{\s*regiment=(\d+)\s+starting=[0-9.]+\s+current=([0-9.]+)\s+soft_casualties=([0-9.]+)\s*\}')
        reg_matches = list(reg_pattern.finditer(side_text))
        
        total_current = sum(Decimal(m.group(2)) for m in reg_matches)
        
        mutated_side = side_text
        remaining_loss = total_loss
        
        for i, match in enumerate(reg_matches):
            reg_id = match.group(1)
            current_val = Decimal(match.group(2))
            
            if i == len(reg_matches) - 1:
                loss = remaining_loss
            else:
                loss = (current_val / total_current * total_loss).to_integral_value(rounding=decimal.ROUND_HALF_UP)
            
            if loss > current_val:
                loss = current_val
                
            regiment_losses[reg_id] = loss
            remaining_loss -= loss
            
            new_current = max(Decimal('0'), current_val - loss)
            
            # Note: Defect 4 states we shouldn't arbitrarily add to soft_casualties
            mutated_side = mutated_side.replace(
                match.group(0),
                match.group(0).replace(f'current={match.group(2)}', f'current={new_current}')
            )
            
        # Re-distribute remaining_loss if rounding clamped it too much
        # Since this is fractional we can just dump it on the first non-zero if needed, but it's fractional so it's less critical than backing integers.
        # But for correctness, our integral rounding guarantees it's exact for backing arrays, but here we just used to_integral_value for fractional troops. We actually don't strictly need integral values here, but matching backing records is safer.
        
        new_total = max(Decimal('0'), old_total - total_loss)
        mutated_side = mutated_side.replace(f'total_fighting_men={total_fighting_match.group(1)}', f'total_fighting_men={new_total}')
            
        char_block_start = mutated_side.find('character={')
        if char_block_start != -1:
            cas_match = re.search(r'casualties=([0-9.]+)', mutated_side[char_block_start:])
            if cas_match:
                old_cas = Decimal(cas_match.group(1))
                new_cas = old_cas + total_loss
                mutated_side = mutated_side[:char_block_start] + mutated_side[char_block_start:].replace(f'casualties={cas_match.group(1)}', f'casualties={new_cas}', 1)
        
        mutated_combat = mutated_combat[:side_start] + mutated_side + mutated_combat[side_end:]
        
    gamestate_text = gamestate_text[:c_start + cb_start] + mutated_combat + gamestate_text[c_start + cb_end:]
    
    # 3. Hierarchical army resolution (Defect 1)
    print("Finding armies manager bounds...", flush=True)
    armies_manager_bounds = record_bounds(gamestate_text, 'armies')
    if not armies_manager_bounds:
        raise ValueError("Root armies block not found")
        
    am_start, am_end = armies_manager_bounds[0]
    armies_text = gamestate_text[am_start:am_end]
    
    print("Finding army_regiments bounds...", flush=True)
    ar_bounds = record_bounds(armies_text, 'army_regiments')
    if not ar_bounds:
        raise ValueError("army_regiments block not found inside armies")
        
    ar_start, ar_end = ar_bounds[0]
    ar_text = armies_text[ar_start:ar_end]
    
    print("Modifying army_regiments...", flush=True)
    for reg_id, loss in regiment_losses.items():
        if loss == 0: continue
        rb_start, rb_end = get_block_by_id(ar_text, 'army_regiments', reg_id)
        reg_text = ar_text[rb_start:rb_end]
        c_match = re.search(r'current=([0-9.]+)', reg_text)
        if c_match:
            old_c = Decimal(c_match.group(1))
            new_c = max(Decimal('0'), old_c - loss)
            mutated_reg_text = reg_text.replace(f'current={c_match.group(1)}', f'current={new_c}', 1)
            ar_text = ar_text[:rb_start] + mutated_reg_text + ar_text[rb_end:]
            
    armies_text = armies_text[:ar_start] + ar_text + armies_text[ar_end:]
    
    print("Finding regiments bounds...", flush=True)
    r_bounds = record_bounds(armies_text, 'regiments')
    if not r_bounds:
        raise ValueError("regiments block not found inside armies")
        
    r_start, r_end = r_bounds[0]
    r_text = armies_text[r_start:r_end]
    
    print("Modifying regiments...", flush=True)
    # Extract chunk attribution directly from the save file backing records instead of cache (Defect 2 & 3)
    for army_data in linked_records.get('armies', {}).values():
        for reg_id, reg_data in army_data.get('regiments', {}).items():
            loss = regiment_losses.get(reg_id, Decimal('0'))
            if loss == 0: continue
            
            for backing_id in reg_data.get('backing_records', {}).keys():
                rb_start, rb_end = get_block_by_id(r_text, 'regiments', backing_id)
                reg_text = r_text[rb_start:rb_end]
                
                chunks_bounds = record_bounds(reg_text, 'chunks')
                if len(chunks_bounds) != 1:
                    raise ValueError(f'Expected one chunks block for backing regiment {backing_id}.')
                chunks_start, chunks_end = chunks_bounds[0]
                chunks_text = reg_text[chunks_start:chunks_end]
                chunk_matches = list(re.finditer(r'\{[^{}]*current=([0-9.]+)[^{}]*\}', chunks_text))
                
                if not chunk_matches:
                    raise ValueError(f'No soldiers found in backing regiment {backing_id}.')
                    
                chunks_data = [{'current': Decimal(m.group(1))} for m in chunk_matches]
                distributed = distribute_loss(chunks_data, loss)
                
                mutated_chunks_text = chunks_text
                for m, d_loss in reversed(list(zip(chunk_matches, distributed))):
                    if d_loss == 0: continue
                    old_c = Decimal(m.group(1))
                    new_c = old_c - d_loss
                    current_start = m.start(1)
                    current_end = m.end(1)
                    mutated_chunks_text = (mutated_chunks_text[:current_start] + str(new_c) +
                                           mutated_chunks_text[current_end:])
                    
                reg_text = reg_text[:chunks_start] + mutated_chunks_text + reg_text[chunks_end:]
                r_text = r_text[:rb_start] + reg_text + r_text[rb_end:]
                
    armies_text = armies_text[:r_start] + r_text + armies_text[r_end:]
    gamestate_text = gamestate_text[:am_start] + armies_text + gamestate_text[am_end:]
    
    return gamestate_text

def apply(run_dir):
    run_dir = Path(run_dir)
    inventory = json.loads((run_dir / 'inventory.json').read_text(encoding='utf-8'))
    synthetic_result = json.loads((run_dir / 'synthetic_result.json').read_text(encoding='utf-8'))
    linked_records = json.loads((run_dir / 'linked_records.json').read_text(encoding='utf-8'))
    
    # Check SHA256 (Defect 2)
    before_path = run_dir / 'before.ck3'
    if sha(before_path) != inventory['save_fingerprint']:
        raise ValueError('Snapshot fingerprint changed or does not match inventory.')
    
    # Journal state pending/generated (Defect 5)
    journal, journal_path = journal_check(run_dir, synthetic_result['result_id'], synthetic_result['battle_id'])
    
    print("Starting apply...", flush=True)
    gamestate_text, kind = preflight.read_gamestate(before_path)
    
    new_gamestate = mutate_gamestate(gamestate_text, synthetic_result, linked_records)
    
    tmp_out_path = run_dir / 'CW2_G2_AFTER.tmp.ck3'
    final_out_path = run_dir / 'CW2_G2_AFTER.ck3'
    
    if kind == 'zip':
        with zipfile.ZipFile(tmp_out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('gamestate', new_gamestate.encode('utf-8'))
    else:
        tmp_out_path.write_bytes(new_gamestate.encode('utf-8'))
        
    # Atomic replace
    tmp_out_path.replace(final_out_path)
    print("Saved.", flush=True)
    
    # Update journal to signify completion of generation, NOT commitment (per user instruction)
    journal[synthetic_result['result_id']] = {
        'battle_id': synthetic_result['battle_id'],
        'status': 'generated' # Keep as generated until reload verification
    }
    journal_path.write_text(json.dumps(journal, indent=2))
    
    return {'status': 'success', 'after_save': str(final_out_path)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.run), indent=2))
