-------------------------------------------------------------------------------------------------
------------------------------------------- KEY INFO --------------------------------------------
-------------------------------------------------------------------------------------------------

-- Battle of Xiangyang
-- Defender

-------------------------------------------------------------------------------------------------
----------------------------------------- DECLARATIONS ------------------------------------------
-------------------------------------------------------------------------------------------------

cam = bm:camera();

gb = generated_battle:new(
	true, 															-- screen starts black
	true, 															-- prevent deployment for player
	false, 															-- prevent deployment for ai
	function() play_intro_cutscene() end, 							-- intro cutscene function
	true															-- debug mode
);

gb:set_end_deployment_phase_after_loading_screen(true);

-------------------------------------------------------------------------------------------------
-------------------------------------------- ARMY SETUP -----------------------------------------
-------------------------------------------------------------------------------------------------

ga_player_main_01 = gb:get_army(gb:get_player_alliance_num(), 1, "player_01");
ga_player_reinforcements_01 = gb:get_army(gb:get_player_alliance_num(), 1, "player_02");
ga_player_reinforcements_02 = gb:get_army(gb:get_player_alliance_num(), 1, "player_03");

ga_ai_main_01 = gb:get_army(gb:get_non_player_alliance_num(), 1, "enemy_01");
ga_ai_reinforcements_01 = gb:get_army(gb:get_non_player_alliance_num(), 1, "enemy_04");
ga_ai_reinforcements_02 = gb:get_army(gb:get_non_player_alliance_num(), 1, "enemy_05");


-------------------------------------------------------------------------------------------------
--------------------------------------- LOCAL ---------------------------------------------------
-------------------------------------------------------------------------------------------------

local intro_cinematic_file =  "script\\battle\\historical_battle\\_cutscene\\managers\\xinyang.CindySceneManager";
local intro_cindy_length = 45000;


-------------------------------------------------------------------------------------------------
---------------------------------------- INTRO CUTSCENE -----------------------------------------
-------------------------------------------------------------------------------------------------

function play_intro_cutscene()
	
	-- declare cutscene
	local intro_cutscene = cutscene:new(
		"xiangyang_cutscene_intro", 				-- unique string name for cutscene
		ga_player_main_01.sunits,				-- unitcontroller over player's army
		intro_cindy_length,						-- duration of cutscene in ms
        function()
			end_intro_cutscene();
		end										-- what to call when cutscene is finished
    );
    
	intro_cutscene:set_skippable(true, function() skip_intro_cutscene() end);
	
	--local end_camera_pos = v(-145, 605.5, 10.7);
	--local base_pos = v(-148.4, 603.3, 25.8);

    --intro_cutscene:set_skip_camera(end_camera_pos, base_pos);
	
	-- set camera end position when cutscene finishes
	--intro_cutscene:set_restore_cam(0, end_camera_pos, base_pos);
	
	-- Play the cindy scene
	intro_cutscene:cindy_action(intro_cinematic_file, 0, 0, 2);
	
	
	-- intro fade-in
	intro_cutscene:action(
		function() 
			cam:fade(false, 1); 
		end, 
		0
	);
	
	
	-- cinematic trigger listeners
	intro_cutscene:add_cinematic_trigger_listener(
		"change_me", 
		function()
			-- intro_cutscene:play_sound(sfx_intro_01);						-- CHANGE ME
			-- bm:show_subtitle("");
		end
	);
	
	intro_cutscene:add_cinematic_trigger_listener(
		"hide_subtitles", 
		function()
			bm:hide_subtitles()
		end
	);
	
	intro_cutscene:add_cinematic_trigger_listener(
		"end_cinematic", 
		function()
			intro_cutscene:finish()
		end
	);
	
	intro_cutscene:action(
		function()
			start_enemy_behaviour()
		end,
		intro_cindy_length - 10000
	);
	
	intro_cutscene:start();
end;


function skip_intro_cutscene()
	cam:fade(true, 0);
	
	start_enemy_behaviour();
	
	bm:callback(
		function() 
			bm:stop_cindy_playback(true)
			cam:fade(false, 0.3) 
		end, 
		200
	);
end;


function start_enemy_behaviour()
	gb.sm:trigger_message("start_enemy_behaviour");
end;


function end_intro_cutscene()

	gb.sm:trigger_message("intro_cutscene_end");
end;


-------------------------------------------------------------------------------------------------
-------------------------------------------- EVENTS ---------------------------------------------
-------------------------------------------------------------------------------------------------

--start of battle, attack only with main force--
ga_ai_main_01:attack_on_message("start_enemy_behaviour");


--first wave of reinforcements for both sides--
ga_ai_main_01:message_on_casualties("reinforce_01", 0.3);
ga_player_reinforcements_01:reinforce_on_message("reinforce_01", 30000);
ga_ai_reinforcements_01:reinforce_on_message("reinforce_01");


--second wave of reinforcements for both sides--
ga_ai_main_01:message_on_casualties("reinforce_02", 0.6);
ga_ai_reinforcements_01:message_on_casualties("reinforce_02", 0.4);
ga_player_reinforcements_02:reinforce_on_message("reinforce_02", 50000);
ga_ai_reinforcements_02:reinforce_on_message("reinforce_02");



-------------------------------------------------------------------------------------------------
-------------------------------------------- OBJECTIVES -----------------------------------------
-------------------------------------------------------------------------------------------------
gb:set_objective_on_message("intro_cutscene_end", "3k_main_battle_historical_scripted_objective_xingyang_1", 1000);

gb:remove_objective_on_message("reinforce_01", "3k_main_battle_historical_scripted_objective_xingyang_1", 30000);
gb:set_objective_on_message("reinforce_01", "3k_main_battle_historical_scripted_objective_xingyang_2", 31000);

gb:remove_objective_on_message("reinforce_02", "3k_main_battle_historical_scripted_objective_xingyang_2", 50000);
gb:set_objective_on_message("reinforce_02", "3k_main_battle_historical_scripted_objective_xingyang_3", 51000);

--safeguard in case player is wiped, but there are still reinforcements waiting to come onto the battlefield, rout these so game ends properly--
ga_player_main_01:message_on_alliance_not_active_on_battlefield("player_loses");
ga_ai_main_01:force_victory_on_message("player_loses");
