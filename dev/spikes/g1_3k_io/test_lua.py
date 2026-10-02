"""Optional Lua 5.1 harness. This tests our logger, not the game's runtime APIs."""
import json
from pathlib import Path
import tempfile
import unittest
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None
import probe

MOCK_ENV = '''
    function load_script_libraries() end
    function ModLog(s) error(s) end
    empire_battle = {new=function() return {} end}
    local function collection(items)
        return {count=function() return #items end, item=function(self,i) return items[i] end}
    end
    local alliance_list = {}
    alive = 100
    men = {}
    routing = {false, false}
    unit_lists = {}
    for a=1,2 do
        local units = {}
        unit_lists[a] = units
        for i=0,2 do
            local name = 'cw2_' .. (a==1 and 'attacker' or 'defender') .. '_' .. i
            units[#units+1] = {name=function() return name end,
                type=function() return 'native_unit' end,
                number_of_men_alive=function() return men[name] or alive end,
                kill_number_of_men=function(self, n, hide) men[name] = (men[name] or alive) - n end,
                is_routing=function() return routing[a] end}
        end
        local army = {units=function() return collection(units) end}
        alliance_list[a] = {armies=function() return collection({army}) end}
    end
    phases = {}
    pending = {}
    manager = {alliances=function() return collection(alliance_list) end,
        get_player_alliance_num=function() return 1 end,
        register_phase_change_callback=function(self,name,fn) phases[name]=fn end,
        register_results_callbacks=function(self,win,lose) victory=win; defeat=lose end,
        callback=function(self, fn, delay) pending[#pending+1]=fn end}
    battle_manager = {new=function() return manager end}
'''

def load(temp, trim='{}'):
    path = Path(temp) / 'result.jsonl'
    lua = LuaRuntime()
    lua.execute(MOCK_ENV)
    script = (probe.HERE / 'probe.lua').read_text(encoding='utf-8')
    script = script.replace('@@RUN_ID@@', 'mock-only').replace('@@BATTLE@@', probe.BATTLE).replace('@@OUTPUT_PATH@@', path.as_posix())
    script = script.replace('@@TRIM@@', trim)
    lua.execute(script)
    return lua, path

@unittest.skipIf(LuaRuntime is None, 'Install lupa to run the Lua 5.1 harness')
class LuaLoggerTests(unittest.TestCase):
    def test_phase_callbacks_emit_real_json_and_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            lua, path = load(temp)
            lua.execute('alive=42; victory(); phases.Complete()')
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([e['phase'] for e in events], ['start', 'result', 'complete'])
            self.assertIsNone(events[0]['player_won'])
            self.assertTrue(events[1]['player_won'])
            self.assertEqual(events[1]['result_source'], 'engine_callback')
            self.assertEqual(events[1]['battle'], probe.BATTLE)
            self.assertEqual(len(events[1]['units']), 6)
            self.assertEqual(events[1]['units'][0]['initial'], 100)
            self.assertEqual(events[2]['units'][0]['survivors'], 42)

    def test_cards_are_trimmed_before_the_start_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            lua, path = load(temp, '{["cw2_attacker_0"] = 21, ["cw2_defender_2"] = 39, ["cw2_defender_1"] = 500}')
            lua.execute('victory()')
            start = json.loads(path.read_text().splitlines()[0])
            men = {u['script_name']: u['initial'] for u in start['units']}
            self.assertEqual(start['phase'], 'start')
            self.assertEqual((men['cw2_attacker_0'], men['cw2_defender_2']), (21, 39))
            self.assertEqual((men['cw2_attacker_1'], men['cw2_defender_1']), (100, 100))  # never grown

    def test_starting_counts_follow_the_unit_when_3k_drops_a_dead_one(self):
        with tempfile.TemporaryDirectory() as temp:
            lua, path = load(temp, '{["cw2_defender_0"] = 1}')
            lua.execute('phases.Deployed(); table.remove(unit_lists[2], 1); routing[2] = true; phases.Complete()')
            complete = [json.loads(line) for line in path.read_text().splitlines()][2]
            men = {u['script_name']: u['initial'] for u in complete['units']}
            self.assertEqual(complete['phase'], 'complete')
            self.assertNotIn('cw2_defender_0', men)
            self.assertEqual((men['cw2_defender_1'], men['cw2_defender_2']), (100, 100))

@unittest.skipIf(LuaRuntime is None, 'Install lupa to run the Lua 5.1 harness')
class LuaResultFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lua, self.path = load(self.temp.name)

    def events(self):
        return [json.loads(line) for line in Path(self.path).read_text().splitlines()]

    def test_broken_enemy_is_player_victory_without_timers(self):
        self.lua.execute('alive=42; routing[2] = true; phases.Complete()')
        events = self.events()
        self.assertEqual([e['phase'] for e in events], ['start', 'complete', 'result'])
        self.assertTrue(events[2]['player_won'])
        self.assertEqual(events[2]['result_source'], 'routing_state')
        self.assertEqual(events[2]['units'][0]['survivors'], 42)
        self.assertEqual(len(self.lua.eval('pending')), 0)

    def test_broken_player_is_non_victory(self):
        self.lua.execute('routing[1] = true; phases.Complete()')
        self.assertFalse(self.events()[2]['player_won'])

    def test_dead_units_count_as_broken(self):
        self.lua.execute('alive=0; phases.Complete()')
        # Both sides at zero men: no single loser, so the outcome stays undetermined.
        self.assertIsNone(self.events()[2]['player_won'])

    def test_no_broken_side_is_undetermined(self):
        self.lua.execute('phases.Complete()')
        self.assertIsNone(self.events()[2]['player_won'])

    def test_late_engine_result_is_not_a_second_result(self):
        self.lua.execute('routing[2] = true; phases.Complete(); defeat()')
        events = self.events()
        self.assertEqual([e['phase'] for e in events], ['start', 'complete', 'result', 'engine_result'])
        self.assertFalse(events[3]['player_won'])

if __name__ == '__main__': unittest.main()
