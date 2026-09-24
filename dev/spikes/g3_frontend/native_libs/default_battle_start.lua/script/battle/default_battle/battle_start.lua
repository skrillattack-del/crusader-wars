-- CUSTOM BATTLE - DEFAULT_BATTLE

load_script_libraries();
bm = battle_manager:new(empire_battle:new());

local file_name, file_path = get_file_name_and_path();

package.path = file_path .. "/?.lua;" .. package.path;

bm:out("");
bm:out("********************************************************************");
bm:out("*** No battle script defined - default script loaded *");
bm:out("********************************************************************");
bm:out("");


-- Show battle objectives.
if effect.get_advice_level() >= 2 then
	force_require("default_battle_objectives");
end;

-- Campaign Battle Tutorial
if core:is_tweaker_set("enable_experimental_lua") then -- Only load in custom battle if you have the special tweaker.
	bm:out("* Loading tutorial")

	force_require("3k_campaign_battle_tutorial");
else
	bm:out("* Not loading tutorial");

	-- We don't want advice in the tutorial.
	if core:is_tweaker_set("ALLOW_ADVICE_IN_CUSTOM_BATTLE") then
		force_require("3k_battle_advice");
	else
		bm:out("\tNot loading advice");
	end;
end;
