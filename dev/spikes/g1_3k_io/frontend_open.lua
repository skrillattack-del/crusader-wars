-- CW2: open the staged battle as soon as Three Kingdoms reaches its main menu.
-- Loaded by 3K's script/frontend_mod_scripting.lua, only while CW2's pack is enabled.
-- Click path, from the game's own layouts (ui/frontend ui/*.twui.xml):
--   main.twui.xml               btn_new_battle
--   new_battle.twui.xml         button_historical_battle
--   historical_battles.twui.xml list_box row for Xingyang (the screen opens on Xiapi),
--                               checkbox_romance_mode off (the pack replaces Records only),
--                               button_start_battle
-- The frontend's timer and event names are not in any pack, so every engine call is
-- guarded and every step is logged to the run folder. If a step fails, the player can
-- still open the battle by hand.
local run_id = "@@RUN_ID@@";
local battle_log = "@@OUTPUT_PATH@@";
local log_path = "@@FRONTEND_LOG@@";
local TICK_MS = 500;
local MAX_TICKS = 240;       -- two minutes of polling
local COOLDOWN_TICKS = 3;    -- let a screen transition finish after a click

local finished = false;
local ticks, cooldown = 0, 0;
local has_timer = false;
local row_clicked = false;

local function log(text)
    local ok, stamp = pcall(os.date, "%H:%M:%S ");
    local file = io.open(log_path, "a");
    if file then
        file:write((ok and stamp or "") .. tostring(text) .. "\n");
        file:close();
    end;
end;

local function exists(path)
    local file = io.open(path, "r");
    if file then file:close(); return true; end;
    return false;
end;

local function ui_root()
    if core and core.get_ui_root then
        local ok, root = pcall(core.get_ui_root, core);
        if ok and root then return root; end;
    end;
    return rawget(_G, "m_root");
end;

local function child(uic, i)
    return UIComponent(uic:Find(i));
end;

local function find(uic, id)
    if uic:Id() == id then return uic; end;
    for i = 0, uic:ChildCount() - 1 do
        local hit = find(child(uic, i), id);
        if hit then return hit; end;
    end;
    return nil;
end;

local function visible(uic)
    local ok, shown = pcall(function() return uic:VisibleFromRoot(); end);
    if ok then return shown; end;
    ok, shown = pcall(function() return uic:Visible(); end);
    return ok and shown;
end;

local function dump(uic, depth, lines)
    if depth > 8 then return; end;
    table.insert(lines, string.rep("  ", depth) .. uic:Id() .. (visible(uic) and "" or " (hidden)"));
    for i = 0, uic:ChildCount() - 1 do dump(child(uic, i), depth + 1, lines); end;
end;

local function dump_tree(reason)
    local root = ui_root();
    if not root then log("dump skipped: no UI root"); return; end;
    local lines = {};
    local ok, err = pcall(dump, root, 0, lines);
    log(reason .. "; component tree follows" .. (ok and "" or (" (partial: " .. tostring(err) .. ")")));
    log(table.concat(lines, "\n"));
end;

local function click(uic, what)
    uic:SimulateLClick();
    cooldown = has_timer and COOLDOWN_TICKS or 0;
    log("clicked " .. what);
end;

local function stop(text)
    finished = true;
    log(text);
end;

local function label(uic)
    local ok, text = pcall(function() return uic:GetStateText(); end);
    return ok and text or "";
end;

local function xinyang_row(root)
    local list = find(root, "list_box");
    if not list then return nil; end;
    for i = 0, list:ChildCount() - 1 do
        local row = child(list, i);
        -- Rows are built from template_battle and labelled "NAME (KEY)".
        if string.find(string.lower(row:Id() .. " " .. label(row)), "xinyang", 1, true) then return row; end;
    end;
    return nil;
end;

local function romance_on(box)
    local ok, state = pcall(function() return box:CurrentState(); end);
    return ok and state and string.find(string.lower(state), "selected", 1, true) ~= nil;
end;

-- The historical battles screen: pick Xingyang, force Records, start.
local function historical_screen(root, start)
    if not row_clicked then
        local row = xinyang_row(root);
        if not row then
            dump_tree("no Xingyang row in list_box");
            stop("stopped: will not start another battle; open Xingyang by hand");
            return;
        end;
        click(row, "Xingyang row " .. row:Id());
        row_clicked = true;
        return;
    end;
    local box = find(root, "checkbox_romance_mode");
    if box and visible(box) and romance_on(box) then
        click(box, "romance checkbox off");
        return;
    end;
    click(start, "button_start_battle");
    stop("battle requested for run " .. run_id);
end;

local function step()
    if finished then return; end;
    if exists(battle_log) then
        stop("run " .. run_id .. " already fought; staying idle");
        return;
    end;
    ticks = ticks + 1;
    if ticks > MAX_TICKS then
        dump_tree("gave up after " .. MAX_TICKS .. " polls");
        stop("stopped: open Historical Battles > Xingyang by hand");
        return;
    end;
    if cooldown > 0 then cooldown = cooldown - 1; return; end;
    local root = ui_root();
    if not root then return; end;
    local start = find(root, "button_start_battle");
    if start and visible(start) then historical_screen(root, start); return; end;
    local historical = find(root, "button_historical_battle");
    if historical and visible(historical) then click(historical, "button_historical_battle"); return; end;
    local new_battle = find(root, "btn_new_battle");
    if new_battle and visible(new_battle) then click(new_battle, "btn_new_battle"); return; end;
end;

local function safe_step()
    local ok, err = pcall(step);
    if not ok then log("error: " .. tostring(err)); end;
end;

log("CW2 opener loaded for run " .. run_id);
if exists(battle_log) then
    stop("run " .. run_id .. " already fought; staying idle");
    return;
end;

-- Drivers: a repeating real-time timer when the frontend has one, plus UI events.
if core and core.add_listener then
    pcall(function()
        core:add_listener("cw2_open_battle_tick", "RealTimeTrigger",
            function(context) return context.string == "cw2_open_battle_tick"; end,
            safe_step, true);
    end);
    if real_timer and real_timer.register_repeating then
        has_timer = pcall(real_timer.register_repeating, "cw2_open_battle_tick", TICK_MS);
    end;
    for _, event in ipairs({"UICreated", "FrontendScreenTransition"}) do
        pcall(function()
            core:add_listener("cw2_open_battle_" .. event, event, true, safe_step, true);
        end);
    end;
end;
if not has_timer and tm and tm.repeat_callback then
    has_timer = pcall(function() tm:repeat_callback(safe_step, TICK_MS, "cw2_open_battle_tick"); end);
end;
log(has_timer and "polling every " .. TICK_MS .. " ms" or "no frontend timer; acting on UI events only");
