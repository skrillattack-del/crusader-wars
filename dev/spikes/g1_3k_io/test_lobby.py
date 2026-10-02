"""Lua 5.1 harness for the in-game lobby (frontend_lobby.lua). The mock UI tree mirrors 3K's
layout IDs (main.twui.xml, historical_battles.twui.xml) and the generated lobby layout; the
frontend's real UI calls, timer and event APIs are unverified until a live run."""
from pathlib import Path
import tempfile
import unittest
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None
import probe
import lobby  # lobby/lobby.py, on the path via probe

MOCK_FRONTEND = '''
    clicks, listeners, created = {}, {}, {}
    local function comp(id, kids, state, text)
        local c = {id=id, kids=kids or {}, state=state or 'active', text=text, texts={}, shown=true}
        for _, k in ipairs(c.kids) do k.parent = c end
        function c:Id() return self.id end
        function c:Address() return self end
        function c:Parent() return self.parent end
        function c:GetStateText() return self.text or '' end
        function c:SetStateText(t) self.text = t; self.texts[self.state] = t end
        function c:ChildCount() return #self.kids end
        function c:Find(i) return self.kids[i + 1] end
        function c:VisibleFromRoot()
            local node = self
            while node do if not node.shown then return false end; node = node.parent end
            return true
        end
        function c:SetVisible(v) self.shown = v end
        function c:CurrentState() return self.state end
        function c:SetState(s) self.state = s end
        function c:SetTooltipText(t) self.tooltip = t end
        function c:PropagatePriority() end
        function c:Divorce(child)
            for i, k in ipairs(self.kids) do if k == child then table.remove(self.kids, i); break end end
        end
        function c:Adopt(child) table.insert(self.kids, child); child.parent = self end
        function c:CreateComponent(name, path)
            if broken_layout and path:find(broken_layout, 1, true) == 1 then error('layout not found: ' .. path) end
            local kids = {}
            if path == lobby_layout then
                local parts = {}
                for _, part in ipairs(lobby_ids) do parts[#parts + 1] = comp(part) end
                kids = {comp('cw2_panel', parts)}
            end
            local made = comp(name, kids)
            created[#created + 1] = path
            self:Adopt(made)
            return made
        end
        function c:SimulateLClick()
            clicks[#clicks + 1] = self.id
            if self.on_click then self.on_click(self) end
            if click_events then listeners.FrontendScreenTransition() end
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
        if late_rows then late, list = list, {} end
        local info_kids = {comp('button_start_battle')}
        if not romance_missing then
            local romance = comp('checkbox_romance_mode', {}, romance_state or 'selected')
            romance.on_click = function(self) self.state = (self.state == 'selected') and 'active' or 'selected' end
            info_kids[#info_kids + 1] = romance
        end
        root.kids = {comp('historical_battles', {
            comp('battle_info', info_kids),
            comp('list_box', list)})}
        root.kids[1].parent = root
    end
    local historical = comp('button_historical_battle')
    historical.on_click = function() show_historical(rows) end
    local new_battle = comp('btn_new_battle')
    new_battle.on_click = function() root.kids = {comp('new_battle', {historical})}; root.kids[1].parent = root end
    menu = comp('optionsGroup', {comp('header_battle_parent'), new_battle, comp('btn_multiplayer_battle'),
                                 comp('btn_dynasty_mode'), comp('btn_replays'), comp('btn_options'), comp('btn_quit')})
    root.kids = {comp('main', {comp('menucontainer', {menu})})}
    root.kids[1].parent = root
    core = {get_ui_root=function() return root end,
            add_listener=function(self, name, event, condition, callback) listeners[event] = callback end}
    real_timer = {register_repeating=function(name, ms) end}
    function tick()
        if late then
            late_rows = late_rows - 1
            if late_rows <= 0 then
                local box = find_id(root, 'list_box')
                for _, row in ipairs(late) do box:Adopt(row) end
                late = nil
            end
        end
        listeners.RealTimeTrigger({string='cw2_lobby_tick'})
    end
    function press(id) listeners.ComponentLClickUp({string=id}) end
    function find_id(node, id)
        if node.id == id then return node end
        for _, k in ipairs(node.kids) do local hit = find_id(k, id); if hit then return hit end end
    end
    function text_of(id) local c = find_id(root, id); return c and c.text end
    function menu_order()
        local ids = {}
        for _, k in ipairs(menu.kids) do ids[#ids + 1] = k.id end
        return table.concat(ids, ',')
    end
'''

ROSTER = {'battle': 'Battle of Hastings', 'date': '1066.10.14', 'season': 'Autumn', 'seed': 1702900, 'sides': [
    {'role': 'Attacker', 'yours': True, 'fighting': 5103.4,
     'commander': {'id': '1', 'name': 'William', 'martial': 21, 'prowess': 16},
     'generals': [{'name': 'Captain 1', 'men': 21, 'units': [
         {'key': 'a', 'name': 'Ji Militia', 'men': 160}, {'key': 'b', 'name': 'Archer Militia', 'men': 160},
         {'key': 'a', 'name': 'Ji Militia', 'men': 1074}]}]},
    {'role': 'Defender', 'fighting': 4821,
     'commander': None,
     'generals': [{'name': 'Captain 1', 'men': 21, 'units': [
         {'key': k, 'name': f'Unit {k}', 'men': 80} for k in 'abcdefgh']}]}]}


@unittest.skipIf(LuaRuntime is None, 'Install lupa to run the Lua 5.1 harness')
class LobbyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.battle_log = self.root / 'run.jsonl'
        self.frontend_log = self.root / 'frontend.log'

    def start(self, rows=('3k_main_historical_battle_xiapi', '3k_main_historical_battle_xinyang'),
              timer=True, broken_layout=False, mode='records', checkbox='selected', late_rows=0,
              click_events=False):
        lua = LuaRuntime()
        lua.execute(f'romance_state = "{checkbox}"; romance_missing = '
                    + ('true' if checkbox == 'missing' else 'false'))
        lua.execute(f'late_rows = {late_rows or "nil"}; click_events = {"true" if click_events else "false"}')
        lua.execute(MOCK_FRONTEND)
        layout = lobby.LAYOUT_PATH.removesuffix('.twui.xml')
        lua.execute(f'lobby_layout = "{layout}"; lobby_ids = {{'
                    + ', '.join(f'"{i}"' for i in [*lobby.TEXT, *lobby.BUTTONS]) + '}')
        if broken_layout:
            lua.execute(f'broken_layout = "{layout}"')
        if not timer:
            lua.execute('real_timer = nil')
        lua.execute('rows = {' + ', '.join(f'{{"{r[0]}", "{r[1]}"}}' if isinstance(r, tuple) else f'"{r}"'
                                           for r in rows) + '}')
        card = probe.lobby_card({**ROSTER, 'mode': mode}, 'run1')
        lua.execute(probe.lobby_script('run1', self.battle_log, self.frontend_log, card))
        self.lua = lua
        return lua

    def ticks(self, n=12):
        for _ in range(n):
            self.lua.execute('tick()')

    def log(self):
        return self.frontend_log.read_text(encoding='utf-8')

    def text(self, cid):
        return self.lua.eval(f'text_of("{cid}")')

    def clicks(self):
        return list(self.lua.eval('clicks').values())

    def test_adds_the_menu_entry_after_multiplayer_in_every_state(self):
        self.start()
        self.ticks(1)
        self.assertEqual(self.lua.eval('menu_order()'),
                         'header_battle_parent,btn_new_battle,btn_multiplayer_battle,cw2_menu_entry,'
                         'btn_dynasty_mode,btn_replays,btn_options,btn_quit')
        texts = self.lua.eval('find_id(root, "cw2_menu_entry").texts')
        self.assertEqual(set(texts.values()), {'CRUSADER WARS II'})
        self.assertEqual(len(list(texts.keys())), 7)
        self.assertEqual(self.lua.eval('find_id(root, "cw2_menu_entry").state'), 'active')

    def test_opens_by_itself_with_the_ck3_battle(self):
        self.start()
        self.ticks(1)
        self.assertIn('lobby opened (a staged battle is waiting)', self.log())
        self.assertEqual(self.text('cw2_battle'), 'Battle of Hastings')
        self.assertEqual((self.text('cw2_date'), self.text('cw2_season')), ('1066.10.14', 'Autumn'))
        self.assertEqual((self.text('cw2_a_name'), self.text('cw2_a_martial'), self.text('cw2_a_prowess')),
                         ('William', '21', '16'))
        self.assertEqual((self.text('cw2_a_men'), self.text('cw2_a_yours')), ('5,103', 'YOUR ARMY'))
        self.assertEqual(self.text('cw2_a_staged'), '1,415 in Three Kingdoms, 1 general')
        # Ji Militia rolled twice becomes one row; rows past the rolled kinds stay empty.
        self.assertEqual((self.text('cw2_a_u0_name'), self.text('cw2_a_u0_men')), ('Ji Militia x2', '1,234'))
        self.assertEqual((self.text('cw2_a_u2_name'), self.text('cw2_a_u2_men')), ('', ''))
        # No commander record: the role stands in and skills show a dash.
        self.assertEqual((self.text('cw2_d_name'), self.text('cw2_d_martial'), self.text('cw2_d_yours')),
                         ('Defender', '-', ''))
        # Eight kinds on six rows: five rows, then the rest summed.
        self.assertEqual((self.text('cw2_d_u5_name'), self.text('cw2_d_u5_men')), ('and 3 more kinds', '240'))
        self.assertEqual(self.lua.eval('find_id(root, "cw2_btn_shuffle").state'), 'inactive')
        self.assertEqual(self.lua.eval('find_id(root, "cw2_btn_fight").state'), 'active')

    def test_fight_closes_the_lobby_and_opens_records_xingyang(self):
        self.start()
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.assertFalse(self.lua.eval('find_id(root, "cw2_lobby").shown'))
        self.ticks(30)
        self.assertEqual(self.clicks(), ['btn_new_battle', 'button_historical_battle', '3k_main_historical_battle_xinyang',
                                         'checkbox_romance_mode', 'button_start_battle'])
        self.assertEqual(self.lua.eval('find_id(root, "checkbox_romance_mode").state'), 'active')
        self.assertIn('battle requested for run run1', self.log())

    def test_fight_leaves_romance_on_for_a_romance_run(self):
        # A Romance run stages the _romance Xingyang XML; the checkbox must stay on.
        self.start(mode='romance')  # the mock checkbox starts selected (on)
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(30)
        self.assertEqual(self.clicks(), ['btn_new_battle', 'button_historical_battle', '3k_main_historical_battle_xinyang',
                                         'button_start_battle'])
        self.assertEqual(self.lua.eval('find_id(root, "checkbox_romance_mode").state'), 'selected')

    def test_fight_ticks_romance_on_when_the_screen_left_it_off(self):
        self.start(mode='romance', checkbox='active')
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(30)
        self.assertEqual(self.clicks(), ['btn_new_battle', 'button_historical_battle', '3k_main_historical_battle_xinyang',
                                         'checkbox_romance_mode', 'button_start_battle'])
        self.assertEqual(self.lua.eval('find_id(root, "checkbox_romance_mode").state'), 'selected')

    def test_a_romance_run_without_the_checkbox_starts_nothing(self):
        # Without the checkbox the engine would load the Records battle this run
        # did not stage, so the lobby stops rather than start the wrong battle.
        self.start(mode='romance', checkbox='missing')
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(30)
        self.assertNotIn('button_start_battle', self.clicks())
        self.assertIn('tick Romance and open Xingyang by hand', self.log())

    def test_back_closes_and_the_menu_entry_reopens(self):
        self.start()
        self.ticks(1)
        self.lua.execute('press("cw2_btn_back")')
        self.assertFalse(self.lua.eval('find_id(root, "cw2_lobby").shown'))
        self.ticks(12)
        self.assertFalse(self.lua.eval('find_id(root, "cw2_lobby").shown'))  # no second auto-open
        self.lua.execute('press("cw2_menu_entry")')
        self.assertTrue(self.lua.eval('find_id(root, "cw2_lobby").shown'))
        self.assertEqual(self.clicks(), [])

    def test_a_fought_run_shows_the_lobby_only_on_request_and_cannot_fight(self):
        self.battle_log.write_text('{}')
        self.start()
        self.ticks(12)
        self.assertIsNone(self.lua.eval('find_id(root, "cw2_lobby")'))
        self.lua.execute('press("cw2_menu_entry")')
        self.assertIn('has been fought', self.text('cw2_status'))
        self.assertEqual(self.lua.eval('find_id(root, "cw2_btn_fight").state'), 'inactive')
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(12)
        self.assertEqual(self.clicks(), [])
        self.assertIn('FIGHT ignored', self.log())

    def test_a_missing_layout_is_logged_and_the_menu_survives(self):
        self.start(broken_layout=True)
        self.ticks(4)
        self.assertIn('lobby unavailable', self.log())
        self.assertIn('cw2_menu_entry', self.lua.eval('menu_order()'))

    def test_event_only_driver_still_fights(self):
        self.start(timer=False)
        self.lua.execute('listeners.FrontendScreenTransition()')
        self.assertIn('lobby opened', self.log())
        self.lua.execute('press("cw2_btn_fight")')
        for _ in range(8):
            self.lua.execute('listeners.FrontendScreenTransition()')
        self.assertEqual(self.clicks()[-1], 'button_start_battle')

    def test_never_starts_another_battle(self):
        self.start(rows=('3k_main_historical_battle_xiapi',))
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(30)
        self.assertNotIn('button_start_battle', self.clicks())
        self.assertIn('no Xingyang row', self.log())
        self.assertIn('3k_main_historical_battle_xiapi', self.log())  # the dumped tree names the rows

    def test_finds_xingyang_by_its_label_when_rows_share_the_template_id(self):
        # historical_battles.twui.xml labels each template_battle row "NAME (KEY)".
        self.start(rows=(('template_battle_0', 'BATTLE OF XIAPI (3K_MAIN_HISTORICAL_BATTLE_XIAPI)'),
                         ('template_battle_1', 'BATTLE OF XINGYANG (3K_MAIN_HISTORICAL_BATTLE_XINYANG)')))
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(30)
        self.assertEqual(self.clicks()[2:], ['template_battle_1', 'checkbox_romance_mode', 'button_start_battle'])

    def test_fight_survives_click_events_and_a_late_battle_list(self):
        # Live run 20260929-095044: clicks fire UI events synchronously and the list fills
        # after the screen opens; FIGHT gave up and the stock battle was fought instead.
        self.start(late_rows=4, click_events=True)
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(40)
        self.assertEqual(self.clicks(), ['btn_new_battle', 'button_historical_battle', '3k_main_historical_battle_xinyang',
                                         'checkbox_romance_mode', 'button_start_battle'])
        self.assertNotIn('no Xingyang row', self.log())

    def test_finds_the_row_renamed_to_the_ck3_battle(self):
        self.start(rows=(('template_battle_0', 'BATTLE OF XIAPI'), ('template_battle_1', 'BATTLE OF HASTINGS')))
        self.ticks(1)
        self.lua.execute('press("cw2_btn_fight")')
        self.ticks(30)
        self.assertEqual(self.clicks()[2:], ['template_battle_1', 'checkbox_romance_mode', 'button_start_battle'])


if __name__ == '__main__':
    unittest.main()
