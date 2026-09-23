-- CW2 G1 experiment. Loaded only by our replacement historical battle XML.
-- API evidence: installed 3K lib_battle_manager, lib_battle_script_unit,
-- lib_generated_battle and lib_mod_loader. Runtime verification is still required.
-- Result capture (build 25370317): the engine sends a "Battle Results" command
-- once the results screen is shown (lib_battle_manager.lua:1063-1076); it never
-- arrived during the first live run, so a deferred Complete-phase fallback reads
-- the manager's engine-set battle_is_won flag (line 535). Each result records
-- its result_source; a late engine result becomes an engine_result event.
load_script_libraries();
bm = battle_manager:new(empire_battle:new());
local run_id = "@@RUN_ID@@";
local battle_id = "@@BATTLE@@";
local output_path = "@@OUTPUT_PATH@@";
local captured = {};
local result_emitted = false;
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
safe_emit('start');
bm:register_phase_change_callback('Deployed', function() safe_emit('deployed'); end);
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
bm:register_phase_change_callback('Complete', function()
    safe_emit('complete');
    -- Give a genuine results-screen Battle Results command the first chance; the
    -- engine sent none during our first live run on build 25370317.
    bm:callback(function()
        if not result_emitted then record_result(bm.battle_is_won == true, 'victory_countdown_fallback'); end;
    end, 5000);
end);
