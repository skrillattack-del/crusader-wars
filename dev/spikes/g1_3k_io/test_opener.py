"""Optional Lua 5.1 harness for the frontend opener. The UI tree mirrors 3K's layout IDs;
the frontend's real timer and event APIs are unverified until a live run."""
from pathlib import Path
import tempfile
import unittest
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None
import probe

MOCK_FRONTEND = '''
    clicks, listeners = {}, {}
    local function comp(id, kids, state, text)
        local c = {id=id, kids=kids or {}, state=state or 'active', text=text}
        function c:Id() return self.id end
        function c:GetStateText() return self.text or '' end
        function c:ChildCount() return #self.kids end
        function c:Find(i) return self.kids[i + 1] end
        function c:VisibleFromRoot() return true end
        function c:CurrentState() return self.state end
        function c:SimulateLClick()
            clicks[#clicks + 1] = self.id
            if self.on_click then self.on_click(self) end
        end
        return c
    end
    UIComponent = function(address) return address end
    root = comp('root')
    function show_historical(rows)
        local list = {}
        for _, row in ipairs(rows) do
            list[#list + 1] = type(row) == 'table' and comp(row[1], {}, nil, row[2]) or comp(row)
        end
        local romance = comp('checkbox_romance_mode', {}, 'selected')
        romance.on_click = function(self) self.state = 'active' end
        root.kids = {comp('historical_battles', {
            comp('battle_info', {comp('button_start_battle'), romance}),
            comp('list_box', list)})}
    end
    local historical = comp('button_historical_battle')
    historical.on_click = function() show_historical(rows) end
    local new_battle = comp('btn_new_battle')
    new_battle.on_click = function() root.kids = {comp('new_battle', {historical})} end
    root.kids = {comp('main', {comp('menucontainer', {new_battle})})}
    core = {get_ui_root=function() return root end,
            add_listener=function(self, name, event, condition, callback) listeners[event] = callback end}
    real_timer = {register_repeating=function(name, ms) end}
    function tick() listeners.RealTimeTrigger({string='cw2_open_battle_tick'}) end
'''

@unittest.skipIf(LuaRuntime is None, 'Install lupa to run the Lua 5.1 harness')
class OpenerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.battle_log = self.root / 'run.jsonl'
        self.frontend_log = self.root / 'frontend.log'

    def run_opener(self, rows=('3k_main_historical_battle_xiapi', '3k_main_historical_battle_xinyang'), ticks=40, timer=True):
        lua = LuaRuntime()
        lua.execute(MOCK_FRONTEND)
        if not timer:
            lua.execute('real_timer = nil')
        lua.execute('rows = {' + ', '.join(f'{{"{r[0]}", "{r[1]}"}}' if isinstance(r, tuple) else f'"{r}"'
                                           for r in rows) + '}')
        script = (probe.HERE / 'frontend_open.lua').read_text(encoding='utf-8')
        script = (script.replace('@@RUN_ID@@', 'run1').replace('@@OUTPUT_PATH@@', self.battle_log.as_posix())
                  .replace('@@FRONTEND_LOG@@', self.frontend_log.as_posix()))
        lua.execute(script)
        for _ in range(ticks):
            if lua.eval('listeners.RealTimeTrigger') is None:
                break
            lua.execute('tick()' if timer else 'listeners.FrontendScreenTransition()')
        return list(lua.eval('clicks').values()), self.frontend_log.read_text(encoding='utf-8')

    def test_clicks_through_to_records_xingyang(self):
        clicks, log = self.run_opener()
        self.assertEqual(clicks, ['btn_new_battle', 'button_historical_battle', '3k_main_historical_battle_xinyang',
                                  'checkbox_romance_mode', 'button_start_battle'])
        self.assertIn('battle requested for run run1', log)

    def test_stays_idle_once_the_run_was_fought(self):
        self.battle_log.write_text('{}')
        clicks, log = self.run_opener()
        self.assertEqual(clicks, [])
        self.assertIn('already fought', log)

    def test_event_only_driver_waits_between_actions_without_cooldown(self):
        clicks, _ = self.run_opener(ticks=3, timer=False)
        self.assertEqual(clicks, ['btn_new_battle', 'button_historical_battle',
                                  '3k_main_historical_battle_xinyang'])
        clicks, log = self.run_opener(ticks=5, timer=False)
        self.assertEqual(clicks[-2:], ['checkbox_romance_mode', 'button_start_battle'])
        self.assertIn('battle requested', log)

    def test_finds_xingyang_by_its_label_when_rows_share_the_template_id(self):
        # historical_battles.twui.xml labels each template_battle row "NAME (KEY)".
        clicks, _ = self.run_opener(rows=(('template_battle_0', 'BATTLE OF XIAPI (3K_MAIN_HISTORICAL_BATTLE_XIAPI)'),
                                          ('template_battle_1', 'BATTLE OF XINGYANG (3K_MAIN_HISTORICAL_BATTLE_XINYANG)')))
        self.assertEqual(clicks[2:], ['template_battle_1', 'checkbox_romance_mode', 'button_start_battle'])

    def test_never_starts_another_battle(self):
        clicks, log = self.run_opener(rows=('3k_main_historical_battle_xiapi',))
        self.assertNotIn('button_start_battle', clicks)
        self.assertIn('no Xingyang row', log)
        self.assertIn('3k_main_historical_battle_xiapi', log)  # the dumped tree names the rows

if __name__ == '__main__': unittest.main()
