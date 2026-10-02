"""Seeded roll of vanilla Three Kingdoms units onto a staged side's cards.

The pool is every non-general unit key in the two native historical battles the
probe extracts (Xingyang, Red Cliffs), so each key is a unit the game ships.
Only Ji Militia and Archer Militia have been staged by the probe so far; the
rest are unproven in our packs until the full-army spike (G3d).
"""
from __future__ import annotations
import math
import random

POOL = {
    'militia': ('3k_main_unit_wood_ji_militia', '3k_main_unit_water_archer_militia',
                '3k_main_unit_metal_sabre_militia', '3k_main_unit_wood_peasant_band',
                '3k_main_unit_metal_axe_band', '3k_main_unit_wood_spear_warriors',
                '3k_main_unit_earth_mounted_sabre_militia'),
    'line': ('3k_main_unit_wood_heavy_spear_guards', '3k_main_unit_water_repeating_crossbowmen',
             '3k_main_unit_metal_mercenary_infantry', '3k_main_unit_water_mercenary_archers',
             '3k_main_unit_fire_mercenary_cavalry', '3k_main_unit_fire_raider_cavalry',
             '3k_main_unit_earth_sabre_cavalry', '3k_main_unit_metal_jian_swordguards'),
    'elite': ('3k_main_unit_metal_pearl_dragons', '3k_main_unit_fire_jade_dragons',
              '3k_main_unit_earth_yellow_dragons', '3k_main_unit_fire_tiger_and_leopard_cavalry',
              '3k_main_unit_fire_heavy_tiger_and_leopard_cavalry'),
}
TIER_WEIGHTS = {'militia': 0.55, 'line': 0.35, 'elite': 0.10}  # draft; tune in playtests
GENERALS = ('3k_main_general_earth_generic', '3k_main_general_wood_generic')
# Romance heroes staged by the native Romance Xingyang battle (probe.py); that XML
# ships no generic earth hero, so the pool draws metal and wood generics.
HERO_GENERALS = ('3k_main_hero_metal_generic', '3k_main_hero_wood_generic')
# Records: each general leads a bodyguard card (21 men in G1 runs 1-3).
# Romance: each general is a single hero, staged on the Romance Xingyang map.
MODES = {'records': {'general_size': 21, 'general': 'bodyguard', 'keys': GENERALS},
         'romance': {'general_size': 1, 'general': 'hero', 'keys': HERO_GENERALS}}
PROVEN = {'3k_main_unit_wood_ji_militia', '3k_main_unit_water_archer_militia'}
RETINUE = 6
CAPTAIN_PROWESS = 5
BETA = 0.6
# DRAFT (playtest-verification pending): faction-unique units by owning faction.
# Unlisted keys are neutral and roll in every domain_focus.
FACTION_TAGS = {
    '3k_main_unit_fire_tiger_and_leopard_cavalry': 'wei',
    '3k_main_unit_fire_heavy_tiger_and_leopard_cavalry': 'wei',
    '3k_main_unit_metal_pearl_dragons': 'wu',
    '3k_main_unit_fire_jade_dragons': 'wu',
    '3k_main_unit_earth_yellow_dragons': 'shu',
}
OWN_FACTION_WEIGHT = 2.0  # own-faction uniques, relative to neutral keys in their tier

def unit_name(key):
    return key.split('_', 4)[-1].replace('_', ' ').title()

def pool_for(tier, domain_focus='custom'):
    """Rollable keys for a tier plus their weights.

    'custom' keeps the whole pool. A faction focus removes other factions'
    uniques and doubles its own within the tier; neutral keys always roll.
    """
    keys = POOL[tier]
    if domain_focus == 'custom':
        return keys, [1.0] * len(keys)
    allowed, weights = [], []
    for key in keys:
        tag = FACTION_TAGS.get(key)
        if tag is not None and tag != domain_focus:
            continue
        allowed.append(key)
        weights.append(OWN_FACTION_WEIGHT if tag == domain_focus else 1.0)
    return tuple(allowed), weights

def tier_probs(prowess: int) -> list[float]:
    p = min(max(prowess / 20, 0.0), 2.0)
    w = [pi * math.exp(BETA * p * k) for k, pi in enumerate(TIER_WEIGHTS.values())]
    s = sum(w)
    return [x / s for x in w]

def generals_of(commander: dict, knights: list[dict], g: int) -> list[dict]:
    ranked = sorted(knights, key=lambda k: k.get("prowess", 10), reverse=True)
    picks = ([commander] if commander else []) + ranked
    # Deduplicate in case commander is in knights
    seen = set()
    unique_picks = []
    for p in picks:
        if p["name"] not in seen:
            seen.add(p["name"])
            unique_picks.append(p)
    picks = unique_picks[:g]
    return picks + [{"name": f"Captain {i+1}", "prowess": CAPTAIN_PROWESS} for i in range(g - len(picks))]

def roll_side(side_spec, side, rng, mode='records', domain_focus='custom'):
    """Fill a scale.StagedSide's unit cards; generals lead six units each, in order."""
    kind = MODES[mode]['general']
    general_keys = MODES[mode]['keys']
    tiers = list(TIER_WEIGHTS.keys())
    
    commander = side_spec.get('commander')
    knights = side_spec.get('knights', [])
    gens = generals_of(commander, knights, side.generals)
    
    out = []
    unit_idx = side.generals
    for g, gen in enumerate(gens):
        probs = tier_probs(gen["prowess"])
        n = min(RETINUE, side.cards - unit_idx)
        units = []
        for _ in range(n):
            tier_idx = rng.choices(range(len(tiers)), probs)[0]
            tier = tiers[tier_idx]
            keys, weights = pool_for(tier, domain_focus)
            key = rng.choices(keys, weights)[0]
            units.append({'key': key, 'name': unit_name(key), 'tier': tier, 'men': side.card_men[unit_idx],
                          'proven': key in PROVEN})
            unit_idx += 1
        
        out.append({'key': general_keys[g % len(general_keys)], 'role': 'Commander' if g == 0 else 'Knight',
                    'name': gen['name'], 'prowess': gen['prowess'],
                    'kind': kind, 'men': side.card_men[g], 'units': units})
    return out

def roll(attacker_spec, defender_spec, attacker_staged, defender_staged, seed, mode='records',
         domain_focus='custom'):
    """Stage the sides with scale.stage(...) first.

    domain_focus: 'custom' rolls the whole pool; 'wei'/'shu'/'wu' drop other
    factions' unique units and favour their own.
    """
    if mode not in MODES:
        raise ValueError(f'Unknown mode {mode!r}; use records or romance.')
    rng = random.Random(seed)
    return (roll_side(attacker_spec, attacker_staged, rng, mode, domain_focus),
            roll_side(defender_spec, defender_staged, rng, mode, domain_focus))
