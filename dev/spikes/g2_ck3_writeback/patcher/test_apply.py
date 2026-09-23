from decimal import Decimal
import unittest

import apply as patcher
import preflight


GAMESTATE = '''meta_data={ ironman=no }
armies={
 regiments={
  101={ chunks={ { max=12 current=10 } { max=4 current=2 } } }
  102={ chunks={ { max=12 current=12 } } }
 }
 army_regiments={
  201={ chunks={ { regiment=101 } } cached={ current=12 max=16 } army=301 }
  202={ chunks={ { regiment=102 } } cached={ current=12 max=12 } army=302 }
 }
 armies={ 301={ regiments={ 201 } } 302={ regiments={ 202 } } }
}
combats={
 combat_results={ 42=none }
 combats={
  42={
   attacker={ armies={ 301 } levies={ { regiment=201 starting=16 current=12 soft_casualties=0 } }
              total_fighting_men=12 total_levy_men=12 initial_men=16 initial_levies=16 }
   defender={ armies={ 302 } levies={ { regiment=202 starting=12 current=12 soft_casualties=0 } }
              total_fighting_men=12 total_levy_men=12 initial_men=12 initial_levies=12 }
   phase=main
  }
 }
}
'''


class ApplyTests(unittest.TestCase):
    def test_nested_backing_chunks_follow_combat_losses(self):
        plan = {'battle_id': '42', 'sides': {
            'attacker': {'synthetic_casualties': 2},
            'defender': {'synthetic_casualties': 3},
        }}
        links = {'armies': {
            '301': {'regiments': {'201': {'backing_records': {'101': '{}'}}}},
            '302': {'regiments': {'202': {'backing_records': {'102': '{}'}}}},
        }}

        changed = patcher.mutate_gamestate(GAMESTATE, plan, links)
        army_manager = preflight.unique(changed, 'armies')
        backing = preflight.unique(army_manager, 'regiments')
        caches = preflight.unique(army_manager, 'army_regiments')

        first_start, first_end = patcher.get_block_by_id(backing, 'regiments', '101')
        second_start, second_end = patcher.get_block_by_id(backing, 'regiments', '102')
        self.assertIn('current=8', backing[first_start:first_end])
        self.assertIn('current=9', backing[second_start:second_end])
        self.assertIn('current=10', caches)
        self.assertIn('phase=main', changed)

    def test_allocation_conserves_loss_and_rejects_overdraw(self):
        counts = [{'current': 7}, {'current': 2}, {'current': 1}]
        self.assertEqual(patcher.distribute_loss(counts, 6),
                         [Decimal(4), Decimal(1), Decimal(1)])
        with self.assertRaises(ValueError):
            patcher.distribute_loss(counts, 11)
        with self.assertRaises(ValueError):
            patcher.distribute_loss(counts, Decimal('1.5'))


if __name__ == '__main__':
    unittest.main()