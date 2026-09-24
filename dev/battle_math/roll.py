"""Seeded roll of vanilla Three Kingdoms units onto a staged side's cards.

The pool is every non-general unit key in the two native historical battles the
probe extracts (Xingyang, Red Cliffs), so each key is a unit the game ships.
Only Ji Militia and Archer Militia have been staged by the probe so far; the
rest are unproven in our packs until the full-army spike (G3d).
"""
from __future__ import annotations
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
# Records: each general leads a bodyguard card (21 men in G1 runs 1-3).
# Romance: each general is a single hero. Untested in our packs: the probe
# replaces only the Records version of Xingyang.
MODES = {'records': {'general_size': 21, 'general': 'bodyguard'},
         'romance': {'general_size': 1, 'general': 'hero'}}
PROVEN = {'3k_main_unit_wood_ji_militia', '3k_main_unit_water_archer_militia'}
RETINUE = 6

def unit_name(key):
    return key.split('_', 4)[-1].replace('_', ' ').title()

def roll_side(side, rng, mode='records'):
    """Fill a scale.StagedSide's unit cards; generals lead six units each, in order."""
    kind = MODES[mode]['general']
    tiers = list(TIER_WEIGHTS)
    units = []
    for men in side.card_men[side.generals:]:
        tier = rng.choices(tiers, [TIER_WEIGHTS[t] for t in tiers])[0]
        key = rng.choice(POOL[tier])
        units.append({'key': key, 'name': unit_name(key), 'tier': tier, 'men': men,
                      'proven': key in PROVEN})
    return [{'key': GENERALS[g % len(GENERALS)], 'role': 'Commander' if g == 0 else 'Knight',
             'kind': kind, 'men': side.card_men[g], 'units': units[g * RETINUE:(g + 1) * RETINUE]}
            for g in range(side.generals)]

def roll(attacker, defender, seed, mode='records'):
    """Stage the sides with scale.stage(..., general_size=MODES[mode]['general_size']) first."""
    if mode not in MODES:
        raise ValueError(f'Unknown mode {mode!r}; use records or romance.')
    rng = random.Random(seed)
    return roll_side(attacker, rng, mode), roll_side(defender, rng, mode)
