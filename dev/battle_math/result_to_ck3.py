"""Carry Three Kingdoms casualty rates back to CK3 men, per side.

The rate crosses, not the head count: a side that lost 65% of its 3K men loses
65% of its CK3 fighting men. `started` must be the count logged at battle
start, because unit size follows the player's graphics setting. Splitting a
side's total across regiments stays with the G2 patcher (distribute_loss).
"""
from __future__ import annotations
import math
from scale import round_half_up

def side_dead(fighting, started, survived):
    if started <= 0 or not 0 <= survived <= started:
        raise ValueError('Survivors must lie between 0 and the logged start count.')
    return min(math.floor(fighting), round_half_up(fighting * (started - survived) / started))

def ck3_casualties(fighting, tk, winner=None):
    """fighting: {side: CK3 fighting men}; tk: {side: (started, survived)}.

    With a winner, the loser's remaining men are listed as routed_to_soft: the
    Defect 6 proposal, so CK3 ends the battle for the 3K winner. Untested in CK3.
    """
    if set(fighting) != set(tk):
        raise ValueError('CK3 and 3K sides differ.')
    if winner is not None and winner not in fighting:
        raise ValueError('Winner is not one of the sides.')
    out = {}
    for side, men in fighting.items():
        dead = side_dead(men, *tk[side])
        out[side] = {'dead': dead}
        if winner is not None and side != winner:
            out[side]['routed_to_soft'] = round_half_up(men - dead)
    return out
