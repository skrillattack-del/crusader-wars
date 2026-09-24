"""Stage CK3 armies as Three Kingdoms unit cards at one shared scale.

Nothing shrinks until a side outgrows a full 3K army (three generals with six
units each), and both sides always share the scale, so the odds survive.
Rule and worked examples: docs/design/cw2_bridge_blueprint.html#army.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

MAX_GENERALS = 3
UNITS_PER_GENERAL = 6
UNIT_SIZE = 80      # militia card at the unit size observed in G1 runs 1-3
GENERAL_SIZE = 21   # general's card, same runs

def round_half_up(value):
    return math.floor(value + 0.5)

def army_cap(unit_size=UNIT_SIZE, general_size=GENERAL_SIZE):
    return MAX_GENERALS * (general_size + UNITS_PER_GENERAL * unit_size)

@dataclass(frozen=True)
class StagedSide:
    fighting: float     # CK3 fighting men at export
    generals: int
    units: int
    trim: int           # men removed at deployment so the side matches its target
    card_men: tuple     # generals first, then units after trimming
    untrimmed: int      # men if trimming turns out not to work in 3K

    @property
    def cards(self):
        return self.generals + self.units

    @property
    def men(self):
        return sum(self.card_men)

def shared_scale(attacker, defender, unit_size=UNIT_SIZE, general_size=GENERAL_SIZE):
    if attacker <= 0 or defender <= 0:
        raise ValueError('Both sides need fighting men.')
    cap = army_cap(unit_size, general_size)
    return min(1.0, cap / attacker, cap / defender)

def stage_side(fighting, scale, unit_size=UNIT_SIZE, general_size=GENERAL_SIZE):
    target = round_half_up(fighting * scale)
    if target <= general_size:
        raise ValueError("Side is no bigger than a general's card; let CK3 resolve this battle.")
    # Fewest generals whose retinues (six units each) hold the side:
    # commander first, then the best knights.
    for generals in range(1, MAX_GENERALS + 1):
        units = max(1, math.ceil((target - generals * general_size) / unit_size))
        if units <= generals * UNITS_PER_GENERAL:
            break
    else:
        raise ValueError('Side exceeds a full Three Kingdoms army at this scale; use shared_scale.')
    # Units round up, then the surplus (under one card) is trimmed at deployment,
    # spread over the last unit cards so general cards keep full strength.
    trim = generals * general_size + units * unit_size - target
    base, extra = divmod(trim, units)
    unit_men = tuple(unit_size - base - (1 if i >= units - extra else 0) for i in range(units))
    rounded = max(1, min(generals * UNITS_PER_GENERAL,
                         round_half_up((fighting * scale - generals * general_size) / unit_size)))
    return StagedSide(fighting, generals, units, trim, (general_size,) * generals + unit_men,
                      generals * general_size + rounded * unit_size)

def stage(attacker, defender, unit_size=UNIT_SIZE, general_size=GENERAL_SIZE):
    scale = shared_scale(attacker, defender, unit_size, general_size)
    return (scale, stage_side(attacker, scale, unit_size, general_size),
            stage_side(defender, scale, unit_size, general_size))
