-- CW2 G1 experiment. Loaded only by our replacement historical battle XML.
-- API evidence: installed 3K lib_battle_manager, lib_battle_script_unit,
-- lib_generated_battle and lib_mod_loader. Runtime verification is still required.
load_script_libraries();
bm = battle_manager:new(empire_battle:new());
local run_id = "9ce5f8c1f80046d392113783e6b9160b";
local output_path = "C:/Users/Matux/OneDrive/Desktop/CANON-SCIENCE/crusader wars/dev/spikes/g1_3k_io/generated/9ce5f8c1f80046d392113783e6b9160b.jsonl";
local captured = {};
local function quote(s)
    return '"' .. tostring(s):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t') .. '"';
end;
local function emit(phase, player_won)
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
    file:write('{"schema":1,"run_id":' .. quote(run_id) .. ',"phase":' .. quote(phase) ..
        ',"player_won":' .. tostring(player_won == nil and 'null' or player_won) ..
        ',"units":[' .. table.concat(rows, ',') .. ']}\n');
    file:flush();
    file:close();
end;
local function safe_emit(phase, won)
    local ok, err = pcall(emit, phase, won);
    if not ok then ModLog('CW2_G1_ERROR ' .. tostring(err)); end;
end;
safe_emit('start');
bm:register_phase_change_callback('Deployed', function() safe_emit('deployed'); end);
bm:register_phase_change_callback('VictoryCountdown', function() safe_emit('victory_countdown'); end);
bm:register_phase_change_callback('Complete', function() safe_emit('complete'); end);
bm:register_results_callbacks(
    function() safe_emit('result', true); end,
    function() safe_emit('result', false); end
);
