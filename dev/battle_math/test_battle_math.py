"""Worked examples (Kasr al-Kabir, a large war, G2's synthetic plan) plus the rule's invariants."""
import unittest
from scale import GENERAL_SIZE, UNIT_SIZE, army_cap, round_half_up, shared_scale, stage, stage_side
from result_to_ck3 import ck3_casualties, side_dead
from roll import FACTION_TAGS, MODES, POOL, RETINUE, pool_for, roll, unit_name

KASR = (340.09632, 421.48395)  # run-002 inventory.json: fighting men, attacker and defender

class StagingTests(unittest.TestCase):
    def test_kasr_al_kabir_stays_one_to_one(self):
        scale, attacker, defender = stage(*KASR)
        self.assertEqual(scale, 1.0)
        self.assertEqual((attacker.generals, attacker.units, attacker.men, attacker.trim), (1, 4, 340, 1))
        self.assertEqual(attacker.card_men, (21, 80, 80, 80, 79))
        self.assertEqual(attacker.untrimmed, 341)
        self.assertEqual((defender.generals, defender.units, defender.men, defender.trim), (1, 5, 421, 0))
        self.assertEqual((attacker.cards, defender.cards), (5, 6))

    def test_large_war_shrinks_both_sides_together(self):
        scale, attacker, defender = stage(12400, 7900)
        self.assertAlmostEqual(1 / scale, 8.25, places=2)
        self.assertEqual((attacker.generals, attacker.cards, attacker.men, attacker.trim), (3, 21, 1503, 0))
        self.assertEqual((defender.generals, defender.units, defender.men, defender.trim), (2, 12, 958, 44))
        self.assertEqual(defender.untrimmed, 922)
        drift = (attacker.untrimmed / defender.untrimmed) / (12400 / 7900) - 1
        self.assertAlmostEqual(drift, 0.039, places=3)

    def test_invariants_across_sizes(self):
        sizes = [22, 60, 101, 102, 500, 501, 502, 981, 982, 1002, 1003, 1502, 1503, 1504, 3000, 12400, 250000]
        for a in sizes:
            for d in sizes:
                with self.subTest(attacker=a, defender=d):
                    scale = shared_scale(a, d)
                    if min(round_half_up(a * scale), round_half_up(d * scale)) <= GENERAL_SIZE:
                        with self.assertRaises(ValueError): stage(a, d)
                        continue
                    _, *sides = stage(a, d)
                    for side, men in zip(sides, (a, d)):
                        self.assertEqual(side.men, round_half_up(men * scale))
                        self.assertLessEqual(side.units, 6 * side.generals)
                        if side.generals > 1:  # one general fewer could not hold this side
                            fewer = side.generals - 1
                            self.assertGreater(-(-(side.men - fewer * GENERAL_SIZE) // UNIT_SIZE), 6 * fewer)
                        self.assertTrue(all(1 <= m <= UNIT_SIZE for m in side.card_men[side.generals:]))
                        self.assertLess(side.trim, UNIT_SIZE)
                    self.assertLessEqual(max(s.men for s in sides), army_cap())

    def test_rejects_sides_too_small_or_unscaled(self):
        with self.assertRaises(ValueError): stage_side(GENERAL_SIZE, 1.0)
        with self.assertRaises(ValueError): stage_side(5000, 1.0)
        with self.assertRaises(ValueError): shared_scale(0, 100)

class ReturnTests(unittest.TestCase):
    def test_g2_synthetic_losses_become_rates(self):
        # G1 run 1 lost 38 and 75 of 181 a side; G2 applies those counts raw today.
        self.assertEqual(side_dead(KASR[0], 181, 143), 71)
        self.assertEqual(side_dead(KASR[1], 181, 106), 175)

    def test_kasr_al_kabir_illustrative_outcome(self):
        out = ck3_casualties({'attacker': KASR[0], 'defender': KASR[1]},
                             {'attacker': (340, 118), 'defender': (421, 356)}, winner='defender')
        self.assertEqual(out, {'attacker': {'dead': 222, 'routed_to_soft': 118}, 'defender': {'dead': 65}})

    def test_whole_side_lost_never_exceeds_ck3_men(self):
        self.assertEqual(side_dead(340.6, 341, 0), 340)

    def test_rejects_impossible_counts(self):
        for started, survived in ((0, 0), (80, 81), (80, -1)):
            with self.assertRaises(ValueError): side_dead(100, started, survived)
        with self.assertRaises(ValueError): ck3_casualties({'attacker': 1}, {'defender': (1, 1)})
        with self.assertRaises(ValueError): ck3_casualties({'attacker': 1}, {'attacker': (1, 1)}, winner='defender')

class RollTests(unittest.TestCase):
    def test_same_seed_same_armies_and_cards_match_the_stage(self):
        _, attacker, defender = stage(12400, 7900)
        first, second = roll({}, {}, attacker, defender, 1702901), roll({}, {}, attacker, defender, 1702901)
        self.assertEqual(first, second)
        self.assertNotEqual(first, roll({}, {}, attacker, defender, 7))
        for side, generals in zip((attacker, defender), first):
            self.assertEqual(len(generals), side.generals)
            units = [u for g in generals for u in g['units']]
            self.assertEqual([g['men'] for g in generals] + [u['men'] for u in units], list(side.card_men))
            self.assertTrue(all(len(g['units']) <= RETINUE for g in generals))
            self.assertTrue(all(u['key'] in POOL[u['tier']] for u in units))
            self.assertEqual(generals[0]['role'], 'Commander')

    def test_romance_generals_are_single_heroes(self):
        size = MODES['romance']['general_size']
        scale, attacker, defender = stage(*KASR, general_size=size)
        self.assertEqual(scale, 1.0)
        self.assertEqual((attacker.men, attacker.card_men[0], attacker.units), (340, 1, 5))
        generals = roll({}, {}, attacker, defender, 1, mode='romance')[0]
        self.assertEqual((generals[0]['kind'], generals[0]['men']), ('hero', 1))
        self.assertTrue(all(g['key'] in MODES['romance']['keys'] for side in
                            roll({}, {}, attacker, defender, 1, mode='romance') for g in side))
        self.assertTrue(all(g['key'].startswith('3k_main_hero_') for g in generals))
        self.assertEqual(army_cap(general_size=size), 1443)
        with self.assertRaises(ValueError): roll({}, {}, attacker, defender, 1, mode='arcade')

    def test_unit_names_read_like_the_game(self):
        self.assertEqual(unit_name('3k_main_unit_wood_ji_militia'), 'Ji Militia')
        self.assertEqual(unit_name('3k_main_unit_fire_tiger_and_leopard_cavalry'), 'Tiger And Leopard Cavalry')

    def test_pool_for_filters_other_factions_and_keeps_neutral_tiers(self):
        keys, weights = pool_for('elite', 'wei')
        self.assertEqual(keys, ('3k_main_unit_fire_tiger_and_leopard_cavalry',
                                '3k_main_unit_fire_heavy_tiger_and_leopard_cavalry'))
        self.assertEqual(weights, [2.0, 2.0])
        neutral_keys, neutral_weights = pool_for('militia', 'wu')
        self.assertEqual(neutral_keys, POOL['militia'])
        self.assertEqual(neutral_weights, [1.0] * len(neutral_keys))
        self.assertEqual(pool_for('elite', 'custom'), (POOL['elite'], [1.0] * len(POOL['elite'])))

    def test_pool_for_bumps_own_faction_within_a_mixed_tier(self):
        original = dict(POOL)
        try:
            POOL['mixed'] = ('3k_main_unit_fire_tiger_and_leopard_cavalry', '3k_main_unit_wood_ji_militia')
            keys, weights = pool_for('mixed', 'wei')
            self.assertEqual(keys, ('3k_main_unit_fire_tiger_and_leopard_cavalry', '3k_main_unit_wood_ji_militia'))
            self.assertEqual(weights, [2.0, 1.0])
        finally:
            POOL.clear()
            POOL.update(original)

    def test_domain_focus_never_rolls_another_factions_uniques(self):
        _, attacker, defender = stage(12400, 7900)
        self.assertEqual(roll({}, {}, attacker, defender, 1702901),
                         roll({}, {}, attacker, defender, 1702901, domain_focus='custom'))
        for focus in ('wei', 'shu', 'wu'):
            rolled = roll({}, {}, attacker, defender, 1702901, domain_focus=focus)
            self.assertEqual(rolled, roll({}, {}, attacker, defender, 1702901, domain_focus=focus))
            keys = {u['key'] for side in rolled for g in side for u in g['units']}
            for key in keys:
                self.assertIn(FACTION_TAGS.get(key, focus), (focus, None), f'{key} leaked into {focus}')

if __name__ == '__main__': unittest.main()
