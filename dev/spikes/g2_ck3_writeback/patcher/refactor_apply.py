import re
import ast

def rewrite():
    with open('apply.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We will write the new file content directly
    new_content = """\"\"\"CK3 save mutation apply script.\"\"\"
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from decimal import Decimal
import decimal
from dataclasses import dataclass

import preflight

decimal.getcontext().prec = 28

@dataclass(frozen=True)
class Change:
    path: str
    span: tuple[int, int]
    before: int
    after: int

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
            
    journal[result_id] = {
        'battle_id': battle_id,
        'status': 'generated'
    }
    journal_path.write_text(json.dumps(journal, indent=2))
    return journal, journal_path

def record_bounds(text, key):
    pattern = re.compile(r'"(?:\\\\.|[^"\\\\])*"|#[^\\r\\n]*|(?P<key>[A-Za-z_0-9]+)\\s*=\\s*\\{|[{}]')
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
    pattern = re.compile(r'\\b' + str(id_str) + r'\\s*=\\s*\\{')
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

def plan_mutations(gamestate_text, synthetic_result, linked_records):
    combat_id = synthetic_result['battle_id']
    changes = []
    
    combats_manager_bounds = record_bounds(gamestate_text, 'combats')
    if len(combats_manager_bounds) != 1:
        raise ValueError("Expected exactly one combats manager")
    
    c_start, c_end = combats_manager_bounds[0]
    combats_text = gamestate_text[c_start:c_end]
    
    cb_start, cb_end = get_block_by_id(combats_text, 'combats', combat_id)
    combat_text = combats_text[cb_start:cb_end]
    
    regiment_losses = {} # army_reg_id -> Decimal(loss)
    
    for side in ['attacker', 'defender']:
        side_data = synthetic_result['sides'][side]
        total_loss = Decimal(str(side_data['synthetic_casualties']))
        if total_loss == 0: continue
            
        side_start, side_end = get_block_by_id(combat_text, 'combat_side', side)
        side_text = combat_text[side_start:side_end]
        side_offset = c_start + cb_start + side_start
        
        # Verify loss bounds (Defect 2)
        total_fighting_match = re.search(r'total_fighting_men=([0-9.]+)', side_text)
        if not total_fighting_match:
            raise ValueError(f"Could not find total_fighting_men for {side}")
        old_total = Decimal(total_fighting_match.group(1))
        if old_total < total_loss:
            raise ValueError(f"{side} total_fighting_men ({old_total}) is less than synthetic_casualties ({total_loss})")
            
        reg_pattern = re.compile(r'\\{\\s*regiment=(\\d+)\\s+starting=[0-9.]+\\s+current=([0-9.]+)\\s+soft_casualties=([0-9.]+)\\s*\\}')
        reg_matches = list(reg_pattern.finditer(side_text))
        
        total_current = sum(Decimal(m.group(2)) for m in reg_matches)
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
            current_start = side_offset + match.start(2)
            current_end = side_offset + match.end(2)
            changes.append(Change(f"combats › {combat_id} › {side} › levies › {reg_id} › current", (current_start, current_end), current_val, new_current))
            
        new_total = max(Decimal('0'), old_total - total_loss)
        tf_start = side_offset + total_fighting_match.start(1)
        tf_end = side_offset + total_fighting_match.end(1)
        changes.append(Change(f"combats › {combat_id} › {side} › total_fighting_men", (tf_start, tf_end), old_total, new_total))
            
        char_block_start = side_text.find('character={')
        if char_block_start != -1:
            cas_match = re.search(r'casualties=([0-9.]+)', side_text[char_block_start:])
            if cas_match:
                old_cas = Decimal(cas_match.group(1))
                new_cas = old_cas + total_loss
                cas_start = side_offset + char_block_start + cas_match.start(1)
                cas_end = side_offset + char_block_start + cas_match.end(1)
                changes.append(Change(f"combats › {combat_id} › {side} › character › casualties", (cas_start, cas_end), old_cas, new_cas))
        
    armies_manager_bounds = record_bounds(gamestate_text, 'armies')
    if not armies_manager_bounds:
        raise ValueError("Root armies block not found")
        
    am_start, am_end = armies_manager_bounds[0]
    armies_text = gamestate_text[am_start:am_end]
    
    ar_bounds = record_bounds(armies_text, 'army_regiments')
    if not ar_bounds:
        raise ValueError("army_regiments block not found inside armies")
        
    ar_start, ar_end = ar_bounds[0]
    ar_text = armies_text[ar_start:ar_end]
    ar_offset = am_start + ar_start
    
    for reg_id, loss in regiment_losses.items():
        if loss == 0: continue
        rb_start, rb_end = get_block_by_id(ar_text, 'army_regiments', reg_id)
        reg_text = ar_text[rb_start:rb_end]
        reg_offset = ar_offset + rb_start
        c_match = re.search(r'current=([0-9.]+)', reg_text)
        if c_match:
            old_c = Decimal(c_match.group(1))
            new_c = max(Decimal('0'), old_c - loss)
            c_start = reg_offset + c_match.start(1)
            c_end = reg_offset + c_match.end(1)
            changes.append(Change(f"armies › army_regiments › {reg_id} › cached › current", (c_start, c_end), old_c, new_c))
            
    r_bounds = record_bounds(armies_text, 'regiments')
    if not r_bounds:
        raise ValueError("regiments block not found inside armies")
        
    r_start, r_end = r_bounds[0]
    r_text = armies_text[r_start:r_end]
    r_offset = am_start + r_start
    
    for army_data in linked_records.get('armies', {}).values():
        for reg_id, reg_data in army_data.get('regiments', {}).items():
            loss = regiment_losses.get(reg_id, Decimal('0'))
            if loss == 0: continue
            
            for backing_id in reg_data.get('backing_records', {}).keys():
                rb_start, rb_end = get_block_by_id(r_text, 'regiments', backing_id)
                reg_text = r_text[rb_start:rb_end]
                reg_offset = r_offset + rb_start
                
                chunks_bounds = record_bounds(reg_text, 'chunks')
                if len(chunks_bounds) != 1:
                    raise ValueError(f'Expected one chunks block for backing regiment {backing_id}.')
                chunks_start, chunks_end = chunks_bounds[0]
                chunks_text = reg_text[chunks_start:chunks_end]
                chunks_offset = reg_offset + chunks_start
                
                chunk_matches = list(re.finditer(r'\\{[^{}]*current=([0-9.]+)[^{}]*\\}', chunks_text))
                
                if not chunk_matches:
                    raise ValueError(f'No soldiers found in backing regiment {backing_id}.')
                    
                chunks_data = [{'current': Decimal(m.group(1))} for m in chunk_matches]
                distributed = distribute_loss(chunks_data, loss)
                
                for i, (m, d_loss) in enumerate(zip(chunk_matches, distributed)):
                    if d_loss == 0: continue
                    old_c = Decimal(m.group(1))
                    new_c = old_c - d_loss
                    c_start = chunks_offset + m.start(1)
                    c_end = chunks_offset + m.end(1)
                    changes.append(Change(f"armies › regiments › {backing_id} › chunks › {i} › current", (c_start, c_end), old_c, new_c))
                
    return changes

def apply_mutations(text, changes):
    changes = sorted(changes, key=lambda c: c.span[0], reverse=True)
    mutated = text
    for change in changes:
        start, end = change.span
        mutated = mutated[:start] + str(change.after) + mutated[end:]
    return mutated

def mutate_gamestate(gamestate_text, synthetic_result, linked_records):
    changes = plan_mutations(gamestate_text, synthetic_result, linked_records)
    return apply_mutations(gamestate_text, changes)

def apply(run_dir):
    run_dir = Path(run_dir)
    inventory = json.loads((run_dir / 'inventory.json').read_text(encoding='utf-8'))
    synthetic_result = json.loads((run_dir / 'synthetic_result.json').read_text(encoding='utf-8'))
    linked_records = json.loads((run_dir / 'linked_records.json').read_text(encoding='utf-8'))
    
    before_path = run_dir / 'before.ck3'
    if sha(before_path) != inventory['save_fingerprint']:
        raise ValueError('Snapshot fingerprint changed or does not match inventory.')
    
    journal, journal_path = journal_check(run_dir, synthetic_result['result_id'], synthetic_result['battle_id'])
    
    gamestate_text, kind = preflight.read_gamestate(before_path)
    new_gamestate = mutate_gamestate(gamestate_text, synthetic_result, linked_records)
    
    tmp_out_path = run_dir / 'CW2_G2_AFTER.tmp.ck3'
    final_out_path = run_dir / 'CW2_G2_AFTER.ck3'
    
    if kind == 'zip':
        with zipfile.ZipFile(tmp_out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('gamestate', new_gamestate.encode('utf-8'))
    else:
        tmp_out_path.write_bytes(new_gamestate.encode('utf-8'))
        
    tmp_out_path.replace(final_out_path)
    
    journal[synthetic_result['result_id']] = {
        'battle_id': synthetic_result['battle_id'],
        'status': 'generated'
    }
    journal_path.write_text(json.dumps(journal, indent=2))
    
    return {'status': 'success', 'after_save': str(final_out_path)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.run), indent=2))
"""
    with open('apply_new.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == '__main__':
    rewrite()
