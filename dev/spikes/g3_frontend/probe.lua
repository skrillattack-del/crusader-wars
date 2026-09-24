-- CW2 G1 experiment. Loaded only by our replacement historical battle XML.
-- API evidence: installed 3K lib_battle_manager, lib_battle_script_unit,
-- lib_generated_battle and lib_mod_loader. Runtime verification is still required.
-- Result capture: the engine's "Battle Results" command (lib_battle_manager.lua:
-- 1067) never arrived in three live runs. battle_is_won (line 535) only means a
-- VictoryCountdown began, for either side, and bm:callback timers stop at
-- Complete, so neither can serve as a fallback. At Complete we derive the outcome
-- from unit state: the side whose every unit is routing or dead lost. Anything
-- else stays undetermined (null). A late engine result becomes engine_result.
load_script_libraries();
bm = battle_manager:new(empire_battle:new());
local run_id = "@@RUN_ID@@";
local battle_id = "@@BATTLE@@";
local output_path = "@@OUTPUT_PATH@@";
local captured = {};
local result_emitted = false;

local function lock_rematch()
    local root = core:get_ui_root()
    local rematch_btn = find_uicomponent(root, "results_screen", "button_rematch") or find_uicomponent(root, "button_rematch")
    if rematch_btn then rematch_btn:SetState("inactive") end
end
core:add_listener("cw2_rematch_lock", "BattleResultsScreenOpened", true, lock_rematch, true)

local function quote(s)
    return '"' .. tostring(s):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t') .. '"';
end;
local function emit(phase, player_won, result_source)
    local rows = {};
    local alliances = bm:alliances();
    for a = 1, alliances:count() do
        local armies = alliances:item(a):armies();
        for r = 1, armies:count() do
            local units = armies:item(r):units();
            for u = 1, units:count() do
                local unit = units:item(u);
                local name = unit:name();
                local key = tostring(a) .. ':' .. tostring(r) .. ':' .. tostring(u);
                if phase == 'start' then captured[key] = unit:number_of_men_alive(); end;
                table.insert(rows, '{"alliance":' .. a .. ',"army":' .. r .. ',"index":' .. u ..
                    ',"script_name":' .. quote(name) .. ',"unit_type":' .. quote(unit:type()) ..
                    ',"initial":' .. tostring(captured[key] or -1) ..
                    ',"survivors":' .. unit:number_of_men_alive() ..
                    ',"routing":' .. tostring(unit:is_routing()) .. '}');
            end;
        end;
    end;
    local file, err = io.open(output_path, 'a');
    if not file then error('CW2 cannot open output: ' .. tostring(err)); end;
    file:write('{"schema":1,"run_id":' .. quote(run_id) .. ',"battle":' .. quote(battle_id) ..
        ',"phase":' .. quote(phase) ..
        ',"player_won":' .. tostring(player_won == nil and 'null' or player_won) ..
        ',"result_source":' .. (result_source == nil and 'null' or quote(result_source)) ..
        ',"units":[' .. table.concat(rows, ',') .. ']}\n');
    file:flush();
    file:close();
end;
local function safe_emit(phase, won, source)
    local ok, err = pcall(emit, phase, won, source);
    if not ok then ModLog('CW2_G1_ERROR ' .. tostring(err)); end;
end;
local function trim_unit(unit, target_men)
    local initial = unit:initial_number_of_men()
    if target_men < initial and target_men > 0 then
        -- Try to kill the difference instantly
        local kill_ratio = (initial - target_men) / initial
        unit:kill_proportion_over_time(kill_ratio, 0, false)
    end
end

safe_emit('start');
bm:register_phase_change_callback('Deployed', function() 
    safe_emit('deployed'); 
    local alliances = bm:alliances();
    for a = 1, alliances:count() do
        local armies = alliances:item(a):armies();
        for r = 1, armies:count() do
            local units = armies:item(r):units();
            for u = 1, units:count() do
                local unit = units:item(u);
                local name = unit:name();
@@TRIM_LOGIC@@
            end;
        end;
    end;
end);
bm:register_phase_change_callback('VictoryCountdown', function() safe_emit('victory_countdown'); end);
local function record_result(won, source)
    if result_emitted then
        -- A late authoritative engine result is kept for cross-checking, never a second result.
        safe_emit('engine_result', won, source);
    else
        result_emitted = true;
        safe_emit('result', won, source);
    end;
end;
bm:register_results_callbacks(
    function() record_result(true, 'engine_callback'); end,
    function() record_result(false, 'engine_callback'); end
);
local function broken(alliance)
    local armies = alliance:armies();
    for r = 1, armies:count() do
        local units = armies:item(r):units();
        for u = 1, units:count() do
            local unit = units:item(u);
            if unit:number_of_men_alive() > 0 and not unit:is_routing() then return false; end;
        end;
    end;
    return true;
end;
local function routing_outcome()
    local alliances = bm:alliances();
    local losers = {};
    for a = 1, alliances:count() do
        if broken(alliances:item(a)) then losers[#losers + 1] = a; end;
    end;
    if #losers ~= 1 then return nil; end;
    return losers[1] ~= bm:get_player_alliance_num();
end;
bm:register_phase_change_callback('Complete', function()
    safe_emit('complete');
    -- Decide synchronously: battle timers no longer run once the battle is complete.
    if not result_emitted then
        local ok, won = pcall(routing_outcome);
        if not ok then ModLog('CW2_G1_ERROR ' .. tostring(won)); won = nil; end;
        record_result(won, 'routing_state');
    end;
end);
