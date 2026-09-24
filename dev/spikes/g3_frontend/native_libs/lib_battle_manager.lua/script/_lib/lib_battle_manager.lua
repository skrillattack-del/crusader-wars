



----------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------
--
--	BATTLE MANAGER
--
--- @loaded_in_battle
--- @c battle_manager Battle Manager
--- @desc The <code>battle_manager</code> object is a lua wrapper for the <code>battle</code> object provided by the game code. The <code>battle_manager</code> provides access to all functionality provided by <code>battle</code> as well as numerous enhancements and extensions.
--- @desc Any calls made to a <code>battle_manager</code> which aren't recognised as functions are passed to the underlying <code>battle</code> object. In this way, the <code>battle_manager</code> object automatically provides the full interface of a <code>battle</code> object.
--
----------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------


__battle_manager = nil;

battle_manager = {
	watch_list = {},
	phase_change_callback_list = {},
	unit_selection_callback_list = {},
	esc_key_steal_list = {},
	advisor_list = {},
	cutscene_list = {},
	battle = nil,
	tm = nil,
	battle_ui_manager = nil,
	should_close_queue_advice = false,			-- if true, advice will close when it's finished playing
	advice_is_playing = false,
	advisor_force_playing = false,
	advisor_stopping = false,
	advisor_last_action_was_stop = false,
	advice_has_played_this_battle = false,
	advice_dont_play = false,
	notify_of_next_advice = false,
	battle_phase_change_handler_registered = false,
	player_victory_callback = nil,
	player_defeat_callback = nil,
	debug_angles = false,
	load_balancing = true,
	watch_timer_running = false,
	help_messages = {},
	help_messages_showing = false,
	advisor_reopen_wait = 500,
	objectives = false,
	infotext = false,
	--hpm = false,  HACK - Disabling help page manager while we decide if we'll do it or not. Re-enable here.
	battle_is_won = false,
	pos_origin = false,
	subtitles_visible = false,
	spell_browser_button_text = "",
	progress_on_advice_dismissed_str = "progress_on_advice_dismissed",
	progress_on_advice_finished_str = "progress_on_advice_finished",
	modify_advice_str = "modify_advice",
	PROGRESS_ON_ADVICE_FINISHED_REPOLL_TIME = 200,
	ui_hiding_enabled = true,
	keep_unit_selection_handler_active = false,
	default_unit_selection_handler_registered = false,
	
	-- camera movement tracker
	camera_tracker_active = false,
	camera_tracker_distance_travelled = 0,
	original_cached_camera_pos = false,
	last_cached_camera_pos = false,
	
	-- engagement monitor
	engagement_monitor_started = false,
	cached_distance_between_forces = 2000,
	cached_num_units_engaged = 0,
	cached_proportion_engaged = 0,
	cached_num_units_under_fire = 0,
	cached_proportion_under_fire = 0,
	main_player_army_altitude = 0,
	main_enemy_army_altitude = 0,

	-- ping icon store
	ping_data_list = {}
};


-- allow battle_manager to properly inherit from battle
function battle_manager:__index(key)
 	local field = rawget(getmetatable(self), key);
	local retval = nil;
	
	if type(field) == "nil" then
		-- key doesn't exist in self, look for it in the prototype object
		local proto = rawget(self, "battle");
		field = proto and proto[key];
				
		if type(field) == "function" then
			-- key exists as a function on the prototype object
			retval = function(obj, ...)
				return field(proto, ...);
			end;
		else
			-- return whatever this key refers to on the prototype object
			retval = field;
		end;
	else
		-- key exists in self
		if type(field) == "function" then
			-- key exists as a function on the self object
			retval = function(obj, ...)
				return field(self, ...);
			end;
		else
			-- return whatever this key refers to on the self object
			retval = field;
		end;
	end;
	
	return retval;
end;


function battle_manager:__tostring()
	return TYPE_BATTLE_MANAGER;
end;


function battle_manager:__type()
	return TYPE_BATTLE_MANAGER;
end;




----------------------------------------------------------------------------
--- @section Creation
----------------------------------------------------------------------------

--- @function new
--- @desc Creates a battle_manager object. The single parameter should be an <code>battle</code> code object, which can be created with <code>empire_battle:new()</code>. Only one battle_manager object may be created in a session - attempting to create a second just returns the first.
--- @r battle_manager
function battle_manager:new(b)
	if __battle_manager then		
		return __battle_manager;
	end;
	if not b then
		script_error("WARNING: No battle object supplied to battle_manager - creating one, but this should really be fixed.");
		b = empire_battle:new();
	end;
	
	local bm = {
		battle = b,
		watch_list = {},
		phase_change_callback_list = {},
		unit_selection_callback_list = {},
		command_handler_callback_list = {},
		input_handler_callback_list = {},
		esc_key_steal_list = {},
		advisor_list = {},
		cutscene_list = {},
		help_messages = {}
	};
	
	setmetatable(bm, battle_manager);
	
	__battle_manager = bm;
	
	bm.tm = timer_manager:new(bm:model_tick_time_ms());
	
	bm.pos_origin = v(0, 0);
	
	-- starts infotext and objectives managers automatically
	bm.infotext = infotext_manager:new();
	bm.objectives = objectives_manager:new();
	
	-- set the ui root on the core object
	core:set_ui_root( UIComponent( bm:ui_component("hud_battle"):Parent() ) );
	
	-- Establish a listener for AdviceDismissedEvent, then register a short callback before triggering
	-- a ScriptEventAdviceDismissed event. The AdviceDismissedEvent is triggered outside of the model update 
	-- loop, so calls made to the model within listener functions triggered by it will often return
	-- nonsense values. Instead we register a timer to return as soon as possible and trigger the
	-- ScriptEventAdviceDismissed event within that. Listening scripts can listen to this second event instead
	-- of the first, and are then free to make whatever calls to the model they like. This means that there will
	-- be a short delay between the advice being dismissed and the script being notified of it, but in most
	-- cases this is okay.
	core:add_listener(
		"battle_advice_dismissed_listener",
		"AdviceDismissedEvent",
		true,
		function(context)
			local advice_str = context.string;
			bm:out("* AdviceDismissedEvent received, advice is " .. advice_str);
			bm:callback(
				function()
					bm:out("* triggering event ScriptEventAdviceDismissed received for advice " .. advice_str);
					core:trigger_event("ScriptEventAdviceDismissed", advice_str);
				end,
				100
			);
		end,
		true
	);
	
	package.path = package.path .. ";" .. bm:get_battle_folder() .. "/?.lua";			-- needed for advice script
	
	bm:out("battle_manager started, model tick time is " .. bm:model_tick_time_ms() .. "ms");

	-- create links to the battle and battlemanager objects in the global registry so that other environments (e.g. autotesting) can access them
	_G.battle_env = core:get_env();
	
	return bm;
end;








----------------------------------------------------------------------------
--- @end_class
--- @section Battle Manager
----------------------------------------------------------------------------


--- @function get_bm
--- @desc Global function to get a battle manager from anywhere (battle only, obviously).
--- @r battle_manager
function get_bm()
	if __battle_manager then
		return __battle_manager;
	end;
	
	return battle_manager:new(empire_battle:new());
end;
--- @c battle_manager








----------------------------------------------------------------------------
--- @section Console Output
----------------------------------------------------------------------------


--- @function out
--- @desc Prints a string to the console for debug purposes. The string is prepended with a timestamp.
function battle_manager:out(msg)
	local str = get_timestamp() .. "<" .. tostring(timestamp_tick) .. "ms> " .. msg;
	print(str);
	
	-- logfile output
	if __write_output_to_logfile then
		local file = io.open(__logfile_path, "a");
		if file then
			file:write(str .. "\n");
			file:close();
		end;
	end;
end;







----------------------------------------------------------------------------
--- @section Miscellaneous Querying
----------------------------------------------------------------------------


--- @function get_tm
--- @desc Directly access the timer_manager object the battle manager creates and stores internally. It shouldn't be necessary to do this too often, as the battle manager exposes its most useful functions.
--- @r timer_manager
function battle_manager:get_tm()
	return self.tm;
end;


--- @function get_battle_ui_manager
--- @desc Retrieves a handle to a @battle_ui_manager object from the battle manager. One is created if it hasn't been created before.
--- @r battle_ui_manager
function battle_manager:get_battle_ui_manager()
	if not self.battle_ui_manager then
		-- this will create a self.battle_ui_manager record
		return battle_ui_manager:new();
	end;
	
	return self.battle_ui_manager;
end;


--- @function get_battle_folder
--- @desc Returns the path to the battle script folder.
--- @r string path
function battle_manager:get_battle_folder()
	return "data/script/battle";
end;


--- @function get_origin
--- @desc Returns a vector position at the world origin.
--- @r vector origin
function battle_manager:get_origin()
	return self.pos_origin;
end;


--- @function ui_component
--- @desc A wrapper for ui_component. Searches the UI heirarchy and returns a uicomponent object with the supplied name. This overrides the base ui_component function provided by the underlying <code>battle</code> object, which returns a component object (which must be converted to be a UIComponent before use).
--- @r uicomponent ui component, or false if not found
function battle_manager:ui_component(component_name)
	if not is_string(component_name) then
		script_error("ERROR: ui_component() called but supplied component name [" .. tostring(component_name) .. "] is not a string");
		return false;
	end;
	
	if component_name == "" then
		script_error("ERROR: ui_component() called but supplied component name is empty");
		return false;
	end;
	
	local retval = self.battle:ui_component(component_name);
	
	if is_component(retval) then
		return UIComponent(retval);
	elseif not retval then
		return false;
	else
		script_error("ERROR: ui_component() called to search for a component called [" .. component_name .. "] and is prepared to return an object [" .. tostring(retval) .. "] of type [" .. type(retval) .. "] but this is not a component, something bad has happened!");
	end;
	
	return false;
end;


function battle_manager:register_cutscene(cutscene)
	if not is_cutscene(cutscene) then
		script_error("ERROR: register_cutscene() called but supplied object [" .. tostring(cutscene) .. "] is not a cutscene");
		return false;
	end;
	
	table.insert(self.cutscene_list, cutscene);
end;


--- @function is_any_cutscene_running
--- @desc Returns true if any cutscene object is currently showing a cutscene.
--- @r boolean is cutscene running
function battle_manager:is_any_cutscene_running()
	if #self.cutscene_list == 0 then
		return false;
	end;
	
	for i = 1, #self.cutscene_list do
		if self.cutscene_list[i]:is_active() then
			return true;
		end;
	end;
	
	return false;
end;


--- @function is_any_unit_selected
--- @desc Queries the UI and returns true if any selectable units are selected. (Ignoring shattered, pending reinforcements, etc.)
--- @r boolean any unit selected
function battle_manager:is_any_unit_selected()
	return effect.get_context_value("CcoBattleSelection", "", "AnyUnitSelected");
end;


--- @function are_all_units_selected
--- @desc Queries the UI and returns true if all selectable units are selected. (Ignoring shattered, pending reinforcements, etc.)
--- @r boolean all units selected
function battle_manager:are_all_units_selected()
	return effect.get_context_value("CcoBattleSelection", "", "AllUnitsSelected")
end;


--- @function num_units_selected
--- @desc Queries the UI and returns the number of units selected.
--- @r number the amount of units selected
function battle_manager:num_units_selected()
	return effect.get_context_value("CcoBattleSelection", "", "NumUnits");
end;


--- @function get_player_alliance_num
--- @desc Returns the alliance number of the player's alliance.
--- @r integer alliance number
function battle_manager:get_player_alliance_num()
	return self:local_alliance();
end;


--- @function get_non_player_alliance_num
--- @desc Returns the alliance number of the non-player alliance.
--- @r integer alliance number
function battle_manager:get_non_player_alliance_num()
	if self:local_alliance() == 1 then
		return 2;
	else
		return 1;
	end;
end;


--- @function get_player_alliance
--- @desc Returns the local player's alliance object.
--- @r alliance player alliance
function battle_manager:get_player_alliance()
	return self:alliances():item(self:get_player_alliance_num());
end;


--- @function get_non_player_alliance
--- @desc Returns the alliance object of the local player's enemy.
--- @r alliance enemy alliance
function battle_manager:get_non_player_alliance()
	return self:alliances():item(self:get_non_player_alliance_num());
end;


--- @function player_is_attacker
--- @desc Returns true if the local player is the attacker in the battle.
--- @r boolean player is attacker
function battle_manager:player_is_attacker()
	return effect.get_context_value("CcoBattleRoot", "", "SetupContext.IsPlayerAttacker");
end;


--- @function get_player_army
--- @desc Returns the local player's army object.
--- @r army player's army
function battle_manager:get_player_army()
	return self:get_player_alliance():armies():item(1);
end;


--- @function get_first_non_player_army
--- @desc Returns the first army of the enemy alliance to the local player.
--- @r army enemy army
function battle_manager:get_first_non_player_army()
	return self:get_non_player_alliance():armies():item(1);
end;











----------------------------------------------------------------------------
--- @section Random Numbers
----------------------------------------------------------------------------


--- @function random_number
--- @desc Returns a random number. If no max value is supplied then the value returned is a float between 0 and 1. If a max value is supplied, then the value returned is an integer value from 1 to the max value. This is safe to use in multiplayer.
--- @p [opt=nil] number max value
--- @r random number
function battle_manager:random_number(max_value)
	-- if no max_value is supplied then just return what the underlying battle:random_number() returns
	if not max_value then
		return self.battle:random_number();
	end;
	
	local bm = get_bm();
	
	return math.floor(bm:random_number() * max_value) + 1;
end;


--- @function random_sort
--- @desc Randomly sorts a numerically-indexed table and returns the result. Note that this doesn't modify the original table. This is safe to use in multiplayer.
--- @p table table, Table input. Must be indexed by number.
--- @r randomly-sorted table
function battle_manager:random_sort(t)
	local retval = {};
	local table_size = #t;
	local n = 0;
			
	for i = 1, table_size do
			
		-- pick an entry from t, add it to retval, then remove it from t
		n = self:random_number(#t);
				
		table.insert(retval, t[n]);
		table.remove(t, n);
	end;
	
	return retval;
end;









----------------------------------------------------------------------------
--- @section Battle Startup and Phases
----------------------------------------------------------------------------


--- @function setup_battle
--- @desc Packaged function to set up a scripted battle on startup, and register a function to be called when the deployment phase ends (i.e. when battle starts). <code>setup_battle</code> will suppress a variety of unit sounds and steal input focus until the combat phase begins.
--- @p function deployment end callback
function battle_manager:setup_battle(new_deployment_end_callback)
	
	self.battle:suspend_contextual_advice(true);
	self.battle:suppress_unit_voices(true);
	self.battle:suppress_unit_musicians(true);
	self.battle:steal_input_focus();
	
	self:register_phase_change_callback(
		"Deployed", 
		function() 
			self:end_deployment();
			new_deployment_end_callback();
		end
	);
	
	self:register_phase_change_callback("VictoryCountdown", function() self.battle_is_won = true end);
	
	self:register_phase_change_callback("Complete", function() self:suspend_contextual_advice(false) end);
end;


function battle_manager:end_deployment()
	self.battle:release_input_focus();
	self.battle:suppress_unit_voices(false);
	self.battle:suppress_unit_musicians(false);
end;


--- @function register_phase_change_callback
--- @desc Registers a function to be called when a specified phase change occurs. Phase change notifications are sent to the script by the game when the battle changes phases, from 'Deployment' to 'Deployed' and on to 'VictoryCountdown' and 'Complete'. The battle manager writes output to the console whenever a phase change occurs, regardless of whether any callback has been registered for it.
--- @p string phase change name
--- @p function callback
function battle_manager:register_phase_change_callback(new_event, new_callback)
	if not is_string(new_event) then
		script_error("ERROR: battle_manager:register_phase_change_callback() event " .. tostring(new_event) .. " given that is not a string!");
		
		return false;
	end;

	if not is_function(new_callback) then
		script_error("ERROR: battle_manager:register_phase_change_callback() callback " .. tostring(new_callback) .. " given that is not a function!");
		
		return false;
	end;
	
	local new_phase_change_callback = {
		event = new_event,
		callback = new_callback
	};
	
	table.insert(self.phase_change_callback_list, new_phase_change_callback);
		
	if not self.battle_phase_change_handler_registered then		
		self:register_battle_phase_handler("battle_manager_phase_change");
		self.battle_phase_change_handler_registered = true;
	end;
end;


function battle_manager_phase_change(event)
	__battle_manager:out("\t\tEvent triggered :: " .. event:get_name());

	for i = 1, #__battle_manager.phase_change_callback_list do	
		if __battle_manager.phase_change_callback_list[i].event == event:get_name() then
			__battle_manager.phase_change_callback_list[i].callback();
		end;
	end;
end;









----------------------------------------------------------------------------
--- @section Unit Selection Callbacks
----------------------------------------------------------------------------


--- @function force_unit_selection_handler_active
--- @desc Forces the unit selection handler to be active and to receive notifications about unit selection events, even when no listeners are active. By default this is disabled, but in certain circumstances (when subject units are selected while battle is paused) it can be advantageous to keep this on.
--- @p [opt=true] boolean set active
function battle_manager:force_unit_selection_handler_active(value)
	if value == false then
		self.keep_unit_selection_handler_active = false;
		self:unregister_default_unit_selection_handler();
	else
		self.keep_unit_selection_handler_active = true;
		self:register_default_unit_selection_handler();
	end;
end;


--- @function register_unit_selection_callback
--- @desc Registers a function to be called when a specified unit is selected by the player.
--- @p unit subject unit
--- @p function callback
function battle_manager:register_unit_selection_callback(unit, callback)
	if not is_unit(unit) then
		script_error("ERROR: battle_manager:register_unit_selection_callback() called but supplied unit " .. tostring(unit) .. " is not a unit");
		return false;
	end;

	if not is_function(callback) then
		script_error("ERROR: battle_manager:register_unit_selection_callback() called but supplied callback " .. tostring(callback) .. " is not a function");
		return false;
	end;
	
	local unit_selection_callback = {
		unit = unit,
		callback = callback
	};
	
	if #self.unit_selection_callback_list == 0 then	
		-- register the default unit selection handler, if it's not already
		self:register_default_unit_selection_handler();
	end;
	
	table.insert(self.unit_selection_callback_list, unit_selection_callback);
end;


--- @function unregister_unit_selection_callback
--- @desc Unregisters a function registered with @battle_manager:register_unit_selection_callback.
--- @p unit subject unit
function battle_manager:unregister_unit_selection_callback(unit)
	for i = 1, #self.unit_selection_callback_list do
		if self.unit_selection_callback_list[i].unit == unit then
			table.remove(self.unit_selection_callback_list, i);
			
			if not self.keep_unit_selection_handler_active and #self.unit_selection_callback_list == 0 then
				self:unregister_default_unit_selection_handler();
			end;
			return;
		end;
	end;
end;


-- default unit selection handler
function battle_manager_unit_selection_handler(unit, selected)	
	for i = 1, #__battle_manager.unit_selection_callback_list do
		local current_unit_selection_callback_entry = __battle_manager.unit_selection_callback_list[i];
	
		if current_unit_selection_callback_entry and current_unit_selection_callback_entry.unit == unit then
			current_unit_selection_callback_entry.callback(unit, selected);
		end;
	end;
end;


-- internal function to register the default unit selection handler, causing the function battle_manager_unit_selection_handler to receive unit selection events
function battle_manager:register_default_unit_selection_handler()
	if not self.default_unit_selection_handler_registered then
		self.default_unit_selection_handler_registered = true;
		self:register_unit_selection_handler("battle_manager_unit_selection_handler");
	end;
end;


-- internal function to unregister the default unit selection handler if it's registered
function battle_manager:unregister_default_unit_selection_handler()
	if self.default_unit_selection_handler_registered then
		self.default_unit_selection_handler_registered = false;
		self:unregister_unit_selection_handler();
	end;
end;










----------------------------------------------------------------------------
--- @section Command Handler Callbacks
----------------------------------------------------------------------------

--- @function register_command_handler_callback
--- @desc Registers a function to be called when a command event is issued by the game. The function will be called with the command handler context supplied as a single argument, which can be queried for further information depending upon the command.
--- @p string command, Command name to listen for.
--- @p function callback, Callback to call when the command is triggered by the game.
--- @p [opt=nil] string callback name, Optional name by which this callback handler can be removed.
function battle_manager:register_command_handler_callback(command_name, callback, callback_name)
	if not is_string(command_name) then
		script_error("ERROR: battle_manager:register_command_handler_callback() called but supplied command name " .. tostring(command_name) .. " is not a string");
		return false;
	end;

	if not is_function(callback) then
		script_error("ERROR: battle_manager:register_command_handler_callback() called but supplied callback " .. tostring(callback) .. " is not a function");
		return false;
	end;
	
	if callback_name and not is_string(callback_name) then
		script_error("ERROR: battle_manager:register_command_handler_callback() called but supplied callback_name " .. tostring(callback_name) .. " is not a string");
		return false;
	end;
	
	-- work out whether to register the command handler
	if not self:are_any_command_handlers_registered() then
		self:register_command_handler("battle_manager_command_handler");
	end;
	
	-- add a table for this command if one does not already exist
	if not self.command_handler_callback_list[command_name] then
		self.command_handler_callback_list[command_name] = {};
	end;
	
	-- build a callback record
	local callback_record = {
		callback = callback,
		callback_name = callback_name
	};
	
	-- add the callback record to the relevant command table
	table.insert(self.command_handler_callback_list[command_name], callback_record);
end;


-- internal function
function battle_manager:are_any_command_handlers_registered()
	for command_name, handler_callbacks in pairs(self.command_handler_callback_list) do
		if #handler_callbacks > 0 then
			return true;
		end;
	end;
	return false;
end;


--- @function unregister_command_handler_callback
--- @desc Unregisters a callback function registered with @battle_manager:register_command_handler_callback. The callback function is specified by the command name and callback name specified when setting the callback up.
--- @p string command name
--- @p string callback name
function battle_manager:unregister_command_handler_callback(command_name, callback_name)
	if not is_string(command_name) then
		script_error("ERROR: battle_manager:unregister_command_handler_callback() called but supplied command name " .. tostring(command_name) .. " is not a string");
		return false;
	end;
	
	if not is_string(callback_name) then
		script_error("ERROR: battle_manager:unregister_command_handler_callback() called but supplied callback name " .. tostring(callback_name) .. " is not a string");
		return false;
	end;

	local command_table = self.command_handler_callback_list[command_name];
	
	if command_table then
		for i = #command_table, 1, -1 do
			if command_table[i].callback_name == callback_name then
				table.remove(command_table, i);
			end;
		end;
	end;
	
	-- unregister the command handler if we aren't using it any more
	if not self:are_any_command_handlers_registered() then
		self:unregister_command_handler();
	end;
end;


function battle_manager_command_handler(command_context)
	local command_records = get_bm().command_handler_callback_list[command_context:get_name()];
	
	if not command_records then
		return;
	end;
	
	-- push the commands into another table so the commands can't alter the table as we're walking over it
	local commands_to_call = {};
	for i = 1, #command_records do
		table.insert(commands_to_call, command_records[i].callback);
	end;
	
	for i = 1, #commands_to_call do
		commands_to_call[i](command_context);
	end;
end;










----------------------------------------------------------------------------
--- @section Input Handler Callbacks
----------------------------------------------------------------------------

--- @function register_input_handler_callback
--- @desc Registers a function to be called when an input event is issued by the game.
--- @p string input, Input name to listen for.
--- @p function callback, Callback to call when the input is triggered by the game.
--- @p [opt=nil] string callback name, Optional name by which this input handler can be removed.
function battle_manager:register_input_handler_callback(input_name, callback, callback_name)
	if not is_string(input_name) then
		script_error("ERROR: battle_manager:register_input_handler_callback() called but supplied input name " .. tostring(input_name) .. " is not a string");
		return false;
	end;

	if not is_function(callback) then
		script_error("ERROR: battle_manager:register_input_handler_callback() called but supplied callback " .. tostring(callback) .. " is not a function");
		return false;
	end;
	
	if callback_name and not is_string(callback_name) then
		script_error("ERROR: battle_manager:register_input_handler_callback() called but supplied callback_name " .. tostring(callback_name) .. " is not a string");
		return false;
	end;
	
	-- work out whether to register the input handler
	if not self:are_any_input_handlers_registered() then
		self:register_input_handler("battle_manager_input_handler");
	end;
	
	-- add a table for this input if one does not already exist
	if not self.input_handler_callback_list[input_name] then
		self.input_handler_callback_list[input_name] = {};
	end;
	
	-- build a callback record
	local callback_record = {
		callback = callback,
		callback_name = callback_name
	};
	
	-- add the callback record to the relevant input table
	table.insert(self.input_handler_callback_list[input_name], callback_record);
end;


-- internal function
function battle_manager:are_any_input_handlers_registered()
	for input_name, handler_callbacks in pairs(self.input_handler_callback_list) do
		if #handler_callbacks > 0 then
			return true;
		end;
	end;
	return false;
end;


--- @function unregister_input_handler_callback
--- @desc Unregisters a callback function registered with @battle_manager:register_input_handler_callback. The callback function is specified by the input name and callback name specified when setting the callback up.
--- @p string command name
--- @p string callback name
function battle_manager:unregister_input_handler_callback(input_name, callback_name)
	if not is_string(input_name) then
		script_error("ERROR: battle_manager:unregister_input_handler_callback() called but supplied input name " .. tostring(input_name) .. " is not a string");
		return false;
	end;
	
	if not is_string(callback_name) then
		script_error("ERROR: battle_manager:unregister_input_handler_callback() called but supplied callback name " .. tostring(callback_name) .. " is not a string");
		return false;
	end;

	local input_table = self.input_handler_callback_list[input_name];
	
	if input_table then
		for i = #input_table, 1, -1 do
			if input_table[i].callback_name == callback_name then
				table.remove(input_table, i);
			end;
		end;
	end;
	
	-- unregister the input handler if we aren't using it any more
	if not self:are_any_input_handlers_registered() then
		self:unregister_input_handler();
	end;
end;


function battle_manager_input_handler(input_name)
	local input_records = get_bm().input_handler_callback_list[input_name];
	
	if not input_records then
		return;
	end;
	
	-- push the inputs into another table so the commands can't alter the table as we're walking over it
	local commands_to_call = {};
	for i = 1, #input_records do
		table.insert(commands_to_call, input_records[i].callback);
	end;
	
	for i = 1, #commands_to_call do
		commands_to_call[i]();
	end;
end;











----------------------------------------------------------------------------
--- @section ESC Key Callback Queue
----------------------------------------------------------------------------

--- @function steal_escape_key_with_callback
--- @desc Steals the escape key if it wasn't stolen before, and registers a callback to be called if the player presses it. The callback entry must be registered with a unique string name, by which it may be cancelled later if desired.
--- @desc Multiple escape key callbacks may be registered at one time, although only the most recently-registered callback is notified when the ESC key is pressed. Once an ESC key callback is called it is removed from the list, and the next ESC key press causes the next most recent callback to be notified, and so-on.
--- @p string callback name
--- @p function callback
function battle_manager:steal_escape_key_with_callback(name, callback)
	if not is_string(name) then
		script_error("ERROR: steal_escape_key_with_callback() called but supplied name [" .. tostring(name) .. "] is not a string");
		return false;
	end;
	
	if not is_function(callback) then
		script_error("ERROR: steal_escape_key_with_callback() called but supplied callback [" .. tostring(callback) .. "] is not a function");
		return false;
	end;
	
	local esc_key_steal_list = self.esc_key_steal_list;
	
	-- don't proceed if a keysteal entry with this name currently exists in the list
	for i = 1, #esc_key_steal_list do
		if esc_key_steal_list[i].name == name then
			script_error("ERROR: steal_escape_key_with_callback() called but another process has already stolen the esc key with name [" .. name .. "]");
			return false;
		end;
	end;
	
	-- create a key steal entry
	local key_steal_entry = {
		["name"] = name,
		["callback"] = callback
	};
	
	-- add this key steal entry at the end of the list
	table.insert(esc_key_steal_list, key_steal_entry);
	
	-- steal the esc key if it wasn't previously
	if #esc_key_steal_list == 1 then
		self:steal_escape_key();
	end;
	
	return true;
end;


--- @function release_escape_key_with_callback
--- @desc Cancels an escape key callback registered with @battle_manager:steal_escape_key_with_callback by name.
--- @p string callback name to cancel
function battle_manager:release_escape_key_with_callback(name)
	if not is_string(name) then
		script_error("ERROR: release_escape_key_with_callback() called but supplied name [" .. tostring(name) .. "] is not a string");
		return false;
	end;
	
	local esc_key_steal_list = self.esc_key_steal_list;
	
	for i = 1, #esc_key_steal_list do
		if esc_key_steal_list[i].name == name then
			table.remove(esc_key_steal_list, i);
			break;
		end;
	end;
	
	-- release the esc key if the list is now empty
	if #esc_key_steal_list == 0 then
		self:release_escape_key();
	end;
end;


function battle_manager:escape_key_pressed()
	local esc_key_steal_list = self.esc_key_steal_list;

	if #esc_key_steal_list == 0 then
		return;
	end;
	
	-- cache callback to call
	local callback = esc_key_steal_list[#esc_key_steal_list].callback;
	
	-- remove callback entry from list
	table.remove(esc_key_steal_list);
	
	-- if list is now empty, release the escape key
	if #esc_key_steal_list == 0 then
		self:release_escape_key();
	end;
	
	-- call the callback
	callback();
end;


function Esc_Key_Pressed()
	get_bm():escape_key_pressed();
end;






----------------------------------------------------------------------------
--- @section Victory Callbacks
----------------------------------------------------------------------------

--- @function setup_victory_callback
--- @desc Establishes a function to be called when the battle enters VictoryCountdown phase i.e. someone has won. This function also sets the duration of the victory countdown to infinite, meaning the battle will never end until @battle_manager:end_battle is called. This allows calling scripts to do things like set up an outro cutscene or play some advice that wouldn't fit into the standard victory countdown duration (10 seconds).
--- @p function callback to call
function battle_manager:setup_victory_callback(callback)
	self:register_victory_countdown_callback(callback);
	self:change_victory_countdown_limit(-1);
end;


function battle_manager:register_victory_countdown_callback(callback)
	self:register_phase_change_callback("VictoryCountdown", callback);
end;


--- @function end_battle
--- @desc Causes a battle to immediately end when it enters the VictoryCountdown phase, or to immediately end if it is already in that phase. This function is most commonly used to end a battle that has entered the VictoryCountdown phase after @battle_manager:setup_victory_callback has been called.
function battle_manager:end_battle()
	self:change_victory_countdown_limit(0);
end;


--- @function register_results_callbacks
--- @desc Old-style battle-ending handlers. These can still be used but won't get called until the battle results screen is shown. Registers player victory and player defeat callbacks to be called at the end of the battle.
--- @p function player victory callback
--- @p function player defeat callback
function battle_manager:register_results_callbacks(player_victory_callback, player_defeat_callback)
	self.player_victory_callback = player_victory_callback;
	self.player_defeat_callback = player_defeat_callback;
	
	self:register_command_handler_callback(
		"Battle Results",
		function(command_context)
			self:process_results(command_context)
		end,
		"battle_manager_battle_results"
	);
end;


function battle_manager:process_results(command_context)
	local result = command_context:get_bool1();
	if result then
		self:out("The Player has won the battle!");
		if self.player_victory_callback then
			self.player_victory_callback();
		else
			script_error("No victory callback was present? If you're not seeing outro advice and you expected to then something broke.");
		end;
	else
		self:out("The Player has lost the battle!");
		if self.player_defeat_callback then
			self.player_defeat_callback();
		else
			script_error("No defeat callback was present? If you're not seeing outro advice and you expected to then something broke.");
		end;
	end;
end;







----------------------------------------------------------------------------
--- @section Time Manipulation
----------------------------------------------------------------------------

--- @function slow_game_over_time
--- @desc Changes game speed from one value to another over a total time (note that this will be elongated by the slowing action) over a given number of steps. Note that the script engine only updates once every 1/10th of a second so specifying steps of less than this will have weird results. Speeds are specified as multiples of normal game speed, so a value of 2 would be twice normal speed, 0.5 would be half, and so on.
--- @p number start game speed
--- @p number target game speed
--- @p number duration in ms
--- @p number steps
function battle_manager:slow_game_over_time(start_game_speed, target_game_speed, total_time, steps)

	if not is_number(start_game_speed) then
		script_error("ERROR: slow_game_over_time() called but supplied start game speed [" .. tostring(start_game_speed) .. "] is not a number");
		return false;
	end;
	
	if not is_number(target_game_speed) then
		script_error("ERROR: slow_game_over_time() called but supplied target game speed [" .. tostring(target_game_speed) .. "] is not a number");
		return false;
	end;
	
	if not is_number(total_time) or total_time <= 0 then
		script_error("ERROR: slow_game_over_time() called but supplied time [" .. tostring(total_time) .. "] is not a number > 0");
		return false;
	end;
	
	if not is_number(steps) or steps <= 0 then
		script_error("ERROR: slow_game_over_time() called but supplied steps [" .. tostring(steps) .. "] is not a number > 0");
		return false;
	end;
	
	local speed_interval = (target_game_speed - start_game_speed) / steps;

	for i = 1, steps do
		self:callback(
			function()
				local new_speed = math.floor((start_game_speed + speed_interval * i) * 10 + 0.5) / 10;		-- precise to only one decimal place
				self:out("::: slow_game_over_time() changing battle speed to " .. new_speed);
				self:modify_battle_speed(new_speed)
			end, 
			(total_time / steps) * i,
			"battle_manager_slow_game_over_time"
		);
	end;
end;


--- @function pause
--- @desc Pauses the battle.
function battle_manager:pause()
	self.battle:modify_battle_speed(0);
end;

--- @function is_historical_mode
--- @desc Returns if the game is running in historical mode.
--- @r boolean whether or not game is running in historical mode
function battle_manager:is_historical_mode()
	return self.battle:is_historical_mode();
end;

--- @function is_romance_mode
--- @desc Returns if the game is running in historical mode.
--- @r boolean whether or not game is running in romance mode
function battle_manager:is_romance_mode()
	return self.battle:is_romance_mode();
end;

-----------------------------------------------------------------------------
-- Achievements :: needs filling in for each game :<
-----------------------------------------------------------------------------

--[[
function battle_manager:unlock_achievement(key)
	if not is_string(key) then
		script_error("ERROR: unlock_achievement() called but achievement given [" .. tostring(key) .. "] is not a string");	
		return false;
	end;
	
	if key == "ACHIEVEMENT_ATT_COMPLETE_PROLOGUE" then
		self:out("\tUNLOCKING ACHIEVEMENT :: ACHIEVEMENT_ATT_COMPLETE_PROLOGUE :: The Gothic War :: Complete the prologue campaign."); 
		return self.battle:unlock_achievement("ACHIEVEMENT_ATT_COMPLETE_PROLOGUE");
	else
		script_error("unlock_achievement() called but supplied key is not a recognised achievement!");
	end;
	
	if key == "ACHIEVEMENT_HISTORICAL_BATTLE_2" then
		self:out("\tUNLOCKING ACHIEVEMENT :: ACHIEVEMENT_HISTORICAL_BATTLE_2 :: Alesia achievement :: Alesia achievement description."); 
		return self.battle:unlock_achievement("ACHIEVEMENT_HISTORICAL_BATTLE_2");
	else
		self:out("unlock_achievement() called but supplied key is not a recognised achievement!");
	end;
end;
]]








----------------------------------------------------------------------------
--- @section Timer Manager
--- @desc These wrapper functions expose functionality provided by the @timer_manager. It is highly recommended to use @battle_manager:callback or @battle_manager:repeat_callback in place of <code>register_singleshot_timer</code> and <code>register_repeating_timer</code>, the latter are mainly provided for legacy support.
----------------------------------------------------------------------------


--- @function callback
--- @desc Exposes the callback function from the @timer_manager object. Instructs the timer manager to call a supplied function after a supplied delay. A string name for the callback may also be supplied with which the callback may be later cancelled using @battle_manager:remove_process.
--- @p function callback to call
--- @p number delay in ms
--- @p [opt=nil] string callback name
function battle_manager:callback(new_callback, new_time_offset, new_entryname)
	return self.tm:callback(new_callback, new_time_offset, new_entryname);
end;


--- @function repeat_callback
--- @desc Exposes the repeat_callback function from the @timer_manager object. Instructs the timer manager to call a supplied function after a supplied delay, and then repeatedly after the same delay. A string name for the callback may also be supplied with which the callback may be later cancelled using @battle_manager:remove_process.
--- @p function callback to call
--- @p number delay in ms
--- @p [opt=nil] string callback name
function battle_manager:repeat_callback(new_callback, new_time_offset, new_entryname)
	return self.tm:repeat_callback(new_callback, new_time_offset, new_entryname);
end;


--- @function register_singleshot_timer
--- @desc Exposes the register_singleshot_timer function from the @timer_manager object.
--- @p string function name
--- @p number time in ms
function battle_manager:register_singleshot_timer(name, t)
	return self.tm:register_singleshot_timer(name, t);
end;


--- @function register_repeating_timer
--- @desc Exposes the register_repeating_timer function from the @timer_manager object.
--- @p string function name
--- @p number time in ms
function battle_manager:register_repeating_timer(name, t)
	return self.tm:register_repeating_timer(name, t);
end;


--- @function unregister_timer
--- @desc Exposes the unregister_timer function from the @timer_manager object.
--- @p string function name
function battle_manager:unregister_timer(name)
	return self.tm:unregister_timer(name);
end;










-----------------------------------------------------------------------------
--- @section Watches
--- @desc A watch is a process that continually polls a supplied condition. When it is true, the watch process waits for a supplied period, and then calls a supplied target function. Watches provide battle scripts with a fire-and-forget method of polling the state of the battle, and of being notified when that state changes in some crucial way.
-----------------------------------------------------------------------------

--- @function watch
--- @desc Establishes a new watch. A supplied condition function is repeated tested and, when it returns true, a supplied target function is called. A wait period between the condition being met and the target being called must also be specified. A name for the watch may optionally be specified to allow other scripts to cancel it.
--- @desc The condition must be a function that returns a value - when that value is true (or evaluates to true) then the watch condition is met. The watch then waits the supplied time offset, which is specified in ms as the second parameter, before calling the callback supplied in the third parameter.
--- @p function condition
--- @p function condition, Condition. Must be a function that returns a value. When the returned value is true, or evaluates to true, then the watch condition is met.
--- @p number wait time, Time in ms that the watch waits once the condition is met before triggering the target callback
--- @p function target callback, Target callback
--- @p [opt=nil] string watch name, Name for this watch process. Giving a watch a name allows it to be stopped/cancelled with @battle_manager:remove_process.
function battle_manager:watch(new_condition, new_time_offset, new_callback, new_entryname)
	if not is_function(new_condition) then
		script_error("ERROR: battle_manager:watch() called but supplied condition " .. tostring(new_condition) .. " is not a function!");
		
		return false;
	end;
	
	if not is_number(new_time_offset) or new_time_offset < 0 then
		script_error("ERROR: battle_manager:watch() called but supplied time offset " .. tostring(new_time_offset) .. " is not a positive number!");
		
		return false;
	end;
	
	if not is_function(new_callback) then
		script_error("ERROR: battle_manager:watch() called but supplied callback " .. tostring(new_callback) .. " is not a function!");
		
		return false;
	end;
	
	local new_entryname = new_entryname or "";
	
	local new_watch_entry = {
		condition = new_condition, 
		time_offset = new_time_offset, 
		callback = new_callback, 
		entryname = new_entryname, 
		last_check = 0
	};
		
	table.insert(self.watch_list, new_watch_entry);
	
	if #self.watch_list == 1 then
		self:register_repeating_timer("battle_manager_tick_watch_counter", 2000);
		self.watch_timer_running = true;
	end;
end;


function battle_manager_tick_watch_counter()
	__battle_manager:tick_watch_counter();
end;


function battle_manager:tick_watch_counter()
	if #self.watch_list == 0 then
		return false;
	end;
	
	if not self.load_balancing then
		-- old non-load-balancing script

		local i = 1;
		local j = #self.watch_list;
		local result = false;
		local should_rescan = false;
		
		while i <= j do
			-- process the next watch entry, get back the result and whether it was processed immediately
			result, should_rescan = self:check_watch_entry(i);

			if should_rescan then
				self:tick_watch_counter(); -- rescan the whole list
				
				return false;
			elseif result then
				j = j - 1;
			else
				i = i + 1;
			end;			
		end;
	else
		-- load-balancing script
		
		-- stop the regular watch timer if it's running
		if self.watch_timer_running then
			self.watch_timer_running = false;
			self:unregister_timer("battle_manager_tick_watch_counter");
		end;
		
		-- work out how many watch entries to scan this tick
		local watch_entries_per_tick = math.ceil(#self.watch_list / 20);
				
		local next_watch = false;
		
		for i = 1, watch_entries_per_tick do
			-- find watch entry with lowest last_check value
			next_watch = self:get_next_watch_entry();
			
			if next_watch then
				-- check it
				local result, need_to_rescan = self:check_watch_entry(next_watch);				
				
				if need_to_rescan then
					self:tick_watch_counter(); -- rescan the whole list
				
					return false;
				end;
			end;			
		end;
		
		self:callback(function() self:tick_watch_counter() end, 100, "tick_watch_counter");
	end;
	
end;

-- go through all the watches and return the one that happened the longest time ago
function battle_manager:get_next_watch_entry()
	if #self.watch_list == 0 then
		return false;
	end;

	local lowest_check = timestamp_tick + 100;
	local next_watch = 0;
	local next_watch_last_check = 0;
	
	for i = 1, #self.watch_list do
		next_watch_last_check = self.watch_list[i].last_check;
	
		if next_watch_last_check < lowest_check then
			next_watch = i;
			lowest_check = next_watch_last_check;
		end;
	end;
	
	return next_watch;
end;


-- check the result of a particular watch, takes an entry number in the 
-- battle manager watch list as parameter
function battle_manager:check_watch_entry(entry_number)
	local w = self.watch_list[entry_number];

	w.last_check = timestamp_tick;
	
	-- determine the result of the condition
	local result = w.condition();
		
	-- if the callback happened immediately then we need to rescan the 
	-- whole list as it could have been mangled by whatever the callback did
	local need_to_rescan = false;
	
	-- if it succeeded then we need to call the callback, either now or in the future
	-- (depending on the offset) and also remove the current watch from the watch list
	if result then
		if w.time_offset == 0 then
			local callback = w.callback;
			table.remove(self.watch_list, entry_number);
			
			-- REMOVE
			-- out.design("\tgoing to call callback");
			
			callback();
			
			-- REMOVE
			-- out.design("\tcallback call completed");
			need_to_rescan = true;
		else
			self:callback(w.callback, w.time_offset, w.entryname);
			table.remove(self.watch_list, entry_number);
		end;
	end;
	
	return result, need_to_rescan;
end;


--- @function remove_process
--- @desc Stops and removes any watch OR callback with the supplied name. Returns true if any were found, false otherwise.
--- @p string name
--- @r boolean any removed
function battle_manager:remove_process(key)
	-- make sure it does both
	local retval = self:remove_process_from_watch_list(key);
	
	return self.tm:remove_callback(key) or retval;
end;


--- @function remove_process_from_watch_list
--- @desc Stops and removes any watch with the supplied name. Returns true if any were found, false otherwise. Best practice is to use remove_process instead of this.
--- @p string name
--- @r boolean any removed
function battle_manager:remove_process_from_watch_list(key)
	if #self.watch_list == 0 then
		return false;
	end;
	
	local i = 1;
	local j = #self.watch_list;
	local have_removed_entry = false;
	
	-- walk through the watch list looking for watches with the given key
	while i <= j do
		if self.watch_list[i].entryname == key then
			table.remove(self.watch_list, i);
			have_removed_entry = true;
			j = j - 1;
		else
			i = i + 1;
		end;
	end;
	
	return have_removed_entry;
end;


--- @function print_watch_list
--- @desc Debug command to dump the watch list to the console.
function battle_manager:print_watch_list()
	if #self.watch_list == 0 then
		self:out("Watch list is empty");
		return;
	end;
	
	self:out("Watch list now looks like:");
	for i = 1, #self.watch_list do
		self:out(i .. ":  " .. tostring(self.watch_list[i].entryname));
	end;
end;


--- @function clear_watches_and_callbacks
--- @desc Cancels all running watches and callbacks. It's highly recommend to not call this except for debug purposes (and rarely, even then).
function battle_manager:clear_watches_and_callbacks()
	self.tm:clear_callback_list();
	
	self.watch_list = {};
	
	-- stop the regular watch timer if it's running (load-balanced watch timer is already cancelled by blanking the callback list)
	if self.watch_timer_running then
		self.watch_timer_running = false;
		self:unregister_timer("battle_manager_tick_watch_counter");
	end;
end;


--- @function set_load_balancing
--- @desc By default the watch system performs load balancing, where it tries to stagger its running watches so they don't all process on the same tick. If this is causes problems for any reason it can be disabled with <code>set_load_balancing</code>. Supply a boolean parameter to enable or disable load balancing.
--- @dp boolean enable load balancing
function battle_manager:set_load_balancing(value)
	if not is_boolean(value) then 
		value = true;
	end;

	self.load_balancing = value;
end;








-----------------------------------------------------------------------------
--- @section Advisor Queue
--- @desc The advisor queueing functionality allows the calling script to queue advisor messages so they don't clumsily collide with each other during playback.
-----------------------------------------------------------------------------


--- @function queue_advisor
--- @desc Enqueues a line of advice for delivery to the player. If there is no other advice playing, or nothing is blocking the advisor system, then the advice gets delivered immediately. Otherwise, the supplied advice will be queued and shown at an appropriate time.
--- @desc The function must be supplied an advice key from the advice_levels/advice_threads tables as its first parameter, unless the advisor entry is set to be debug (see below). 
--- @desc The third parameter 
--- @p string advice key, Advice key from the advice_levels/advice_threads table.
--- @p_long_desc If the advice entry is set to be debug (see third parameter) the text supplied here will instead be shown directly in the advisor window (debug only)
--- @p [opt=0] number forced duration, Forced duration in ms. This is a period that this advice must play for before another item of advice is allowed to start. By default, items of advice will only remain queued while the active advice is actually audibly playing, but by setting a duration the active advice can be held on-screen for longer than the length of its associated soundfile (unless it is closed by the player). This is useful during development to hold advice on-screen when no soundfile yet exists, and also for tutorial scripts which often wish to ensure that an item of advice is shown on-screen for a certain duration.
--- @p [opt=false] boolean debug, Sets whether the advice line is debug. If set to true, the text supplied as the first parameter is displayed in the advisor window as-is, without using it as a lookup key in the advice_levels table.
--- @p [opt=nil] function start callback, Start callback. If a function is supplied here it is called when the advice is actually played.
--- @p [opt=0] number start callback wait, Start callback wait period in ms. If a duration is specified it causes a delay between the advice being played and the start callback being called.
--- @p [opt=nil] playback condition, Playback condition. If specified, it compels the advisor system to check this condition immediately before playing the advisor entry to decide whether to actually proceed. This must be supplied as a function block that returns a result. If this result evaluates to true, the advice is played.
function battle_manager:queue_advisor(new_advisor_string, 
									  new_duration, 
									  new_is_debug, 
									  new_callback, 
									  new_callback_offset, 
									  new_advice_offset, 
									  new_condition, 
									  new_location,
									  new_context_object)
									  
	if self.advice_dont_play then
		return;
	end;
	
	if not is_string(new_advisor_string) then
		script_error("ERROR :: queue_advisor called with non-string parameter (" .. tostring(new_advisor_string) .. "), cannot queue this!");
		return false;
	end;
	
	-- if the advisor system was manually stopped in the last 500ms (usually this same tick), wait for a little bit to allow the system to clear
	if self.advisor_stopping then
		self:callback(function() self:queue_advisor(
			new_advisor_string, 
			new_duration, 
			new_is_debug, 
			new_callback,
			new_callback_offset,
			new_advice_offset,
			new_condition,
			new_location,
			new_context_object) end, self.advisor_reopen_wait, "battle_manager_advisor_stopping");
		return false;
	end
	
	if not is_number(new_duration) then
		new_duration = 0;
	end;
	
	if not is_function(new_callback) then
		new_callback = nil;
	end;
	
	if not is_number(new_callback_offset) then
		new_callback_offset = 0;
	elseif new_callback_offset < 0 then
		script_error("WARNING: battle_manager:queue_advisor called but a negative callback offset [" .. tostring(new_callback_offset) .. "] was specified, setting to 0");
		new_callback_offset = 0;
	end;
	
	if not is_number(new_advice_offset) then
		new_advice_offset = 0;
	elseif new_advice_offset < 0 then
		script_error("WARNING: battle_manager:queue_advisor called but a negative callback offset [" .. tostring(new_advice_offset) .. "] was specified, setting to 0");
		new_advice_offset = 0;
	end;
	
	local new_is_debug = new_is_debug or false;

	if new_context_object then 
		battleAdviceLogger:log("[INFO] battle_manager:queue_advisor(): A context object set: " .. new_context_object .. " - advice: " .. new_advisor_string);
	else
		battleAdviceLogger:log("[INFO] battle_manager:queue_advisor(): No advice context object set - advice: " .. new_advisor_string);
	end

	local advisor_entry = {
		advisor_string = new_advisor_string, 
		duration = new_duration, 
		is_debug = new_is_debug,
		callback = new_callback,
		callback_offset = new_callback_offset,
		advice_offset = new_advice_offset,
		condition = new_condition,
		location = new_location,
		context_object = new_context_object
	};

	table.insert(self.advisor_list, advisor_entry);

	if not self.advice_is_playing then
		self:play_next_advice();
	end;
end;


-- plays the next queued advice
function battle_manager:play_next_advice()

	if self.advice_dont_play then
		return;
	end;

	-- the game reckons it's still playing some advice, so try again later
	-- if the last advisor action was to stop advice, then don't bother with this as the next advisor should just override it
	if not self.advisor_last_action_was_stop and not self:advice_finished() then	
		self:remove_process("battle_manager_advisor_queue");
		self:callback(function() self:watch_advice_queue() end, 500, "battle_manager_advisor_queue");
		
		return false;
	end;
	
	self.advisor_last_action_was_stop = false;
	
	-- if we have no more advice to play, stop
	if #self.advisor_list == 0 then
		if self.should_close_queue_advice then
			self:close_advisor();
		end;
		
		self.advice_is_playing = false;
		
		return false;
	end;
		
	local current_advice = self.advisor_list[1];
	
	if is_function(current_advice.condition) then
		if not current_advice.condition() then
			self:out("Tried to play advice [" .. current_advice.advisor_string .. "] but condition failed, skipping");
			table.remove(self.advisor_list, 1);
			self:play_next_advice();
			return;
		end;		
	end;
	
	self.advice_is_playing = true;
	self.advice_has_played_this_battle = true;
	
	local advice_offset = current_advice.advice_offset;
	
	-- play first bit of advice in the list
	if current_advice.is_debug then
		self:callback(function() effect.advice(current_advice.advisor_string) end, advice_offset);
	else	
		self:callback(
			function()
				if current_advice.context_object then
					battleAdviceLogger:log("[INFO] battle_manager:play_next_advice(): Advancing advice " .. current_advice.advisor_string .. " with context object " .. tostring(current_advice.context_object));
					self:out("Advancing advice " .. current_advice.advisor_string .. " with context object " .. tostring(current_advice.context_object));
					effect.advance_scripted_advice_thread_context(current_advice.advisor_string, 1, current_advice.context_object);
				elseif current_advice.location then 
					battleAdviceLogger:log("[INFO] battle_manager:play_next_advice(): Advancing advice " .. current_advice.advisor_string .. " with location [" .. tostring(current_advice.location:get_x()) .. ", " .. current_advice.location:get_y() .. "]");
					self:out("Advancing advice " .. current_advice.advisor_string .. " with location [" .. tostring(current_advice.location:get_x()) .. ", " .. current_advice.location:get_y() .. "]");
					effect.advance_scripted_advice_thread_located(current_advice.advisor_string, 1, current_advice.location:get_x(), current_advice.location:get_y());
				else
					battleAdviceLogger:log("[INFO] battle_manager:play_next_advice(): Advancing advice " .. current_advice.advisor_string);
					self:out("Advancing advice " .. current_advice.advisor_string);
					effect.advance_scripted_advice_thread(current_advice.advisor_string, 1);
				end 
			end, 
			advice_offset, 
			"battle_manager_pending_advice"
		);
	end;
	
	self:remove_process("battle_manager_advisor_queue");
	
	-- prevent the advisor from closing or progressing until after the allotted duration is over
	-- note that if the player closes the advisor dialog this isn't picked up on 
	if current_advice.duration > 0 then
		self.advisor_force_playing = true;
		self:callback(function() self.advisor_force_playing = false end, current_advice.duration, "battle_manager_advisor_queue");
	end;
	
	-- call callback if there is one
	if is_function(current_advice.callback) then
		if current_advice.callback_offset == 0 then
			current_advice.callback();
		else
			-- offset the call by the supplied offset if there is one
			self:callback(function() current_advice.callback() end, current_advice.callback_offset, "battle_manager_advisor_queue");
		end;
	end;
	
	-- remove first element in the table now that it's being played
	table.remove(self.advisor_list, 1);
	
	self:callback(function() self:watch_advice_queue() end, 500, "battle_manager_advisor_queue");
end;


function battle_manager:watch_advice_queue()
	-- if the current bit of advice has finished playing then wait a bit and try to play the next, else re-check in 500ms
	if self:advice_finished() then
		self:callback(function() self:play_next_advice() end, 2000, "battle_manager_advisor_queue");
	else
		self:callback(function() self:watch_advice_queue() end, 500, "battle_manager_advisor_queue");
	end;
end;


--- @function stop_advisor_queue
--- @desc Cancels any running advice, and clears any subsequent advice that may be queued.
--- @p [opt=false] boolean close advisor, Closes the advisor if it's open
--- @p [opt=false] boolean force immediate stop, Forces immediate stop. By default the stopping action takes a short amount of time - the game seems happier with this. If set to true, this flag bypasses this behaviour. User beware.
function battle_manager:stop_advisor_queue(should_close, force_immediate_stop)
	if should_close then
		self:close_advisor();
	end;
	self:remove_process("battle_manager_advisor_queue");
	self.advisor_queue = {};
	self.advice_is_playing = false;
	self.advisor_force_playing = false;
	self.advisor_last_action_was_stop = true;
	
	-- take a note that the advisor is stopping, and delay and queueing for a bit if so - the game doesn't
	-- seem to like stopping and then immediately re-queueing
	-- The force_immediate_stop flag bypasses this, which can be useful when time is being manipulated. Buyer beware in this case etc.
	if not force_immediate_stop then
		self.advisor_stopping = true;
		self:callback(function() self.advisor_stopping = false end, self.advisor_reopen_wait, "battle_manager_stop_advisor_queue");
	end;
end;


--- @function advice_cease
--- @desc Stops the advisor queue and prevents any more advice from being queued. The advice system will only subsequently restart if @battle_manager:advice_resume is called.
function battle_manager:advice_cease()
	self:out("Ceasing all advice");
	self:stop_advisor_queue(true);
	self.advice_dont_play = true;
end;


--- @function advice_resume
--- @desc Allows advice to resume after @battle_manager:advice_cease called.
function battle_manager:advice_resume()
	self.advice_dont_play = false;
end;


--- @function stop_advice_on_battle_end
--- @desc Establishes a listener which stops the advice system as soon as the battle results panel appears.
function battle_manager:stop_advice_on_battle_end()
	core:add_listener(
		"bm_stop_advice_on_battle_end",
		"PanelOpenedBattle",
		function(context) return context.string == "in_battle_results_popup" end,
		function() self:advice_cease() end,
		false
	);
end;


function battle_manager:advice_finished()
	if self.battle:advice_finished() and not self.advisor_force_playing then
		return true;
	end;
	
	return false;
end;


--- @function set_close_queue_advice
--- @desc Sets whether the advisor system should close the advisor panel once an item of advice has finished playing. By default this is set to false, so use this function to turn this behaviour on.
--- @p [opt=true] boolean value
function battle_manager:set_close_queue_advice(value)
	if value == false then
		self.should_close_queue_advice = false;
	else
		self.should_close_queue_advice = true;
	end;
end;


--- @function has_advice_played_this_battle
--- @desc Returns true if any advice has played in this battle session
--- @r boolean advice has played
function battle_manager:has_advice_played_this_battle()
	return self.advice_has_played_this_battle;
end;


--- @function modify_advice
--- @desc Modifies the advisor panel to show the progress/close button in the bottom right, and also to highlight this button with an animated ring around it. This setting will persist across subsequent items of advice in a battle session until modified again.
--- @p [opt=false] boolean show button, Show progress/close button.
--- @p [opt=false] boolean show highlight, Show highlight on close button.
function battle_manager:modify_advice(progress_button, highlight)
	-- if the component doesn't exist yet, wait a little bit as it's probably in the process of being created
	if not find_uicomponent(core:get_ui_root(), "advice_interface") then
		self:callback(function() self:modify_advice(progress_button, highlight) end, 200, self.modify_advice_str);
		return;
	end;

	self:remove_process(self.modify_advice_str);

	if progress_button then
		show_advisor_progress_button();
		
		local dismiss_advice_str = "dismiss_advice_str";
		
		core:remove_listener(dismiss_advice_str);
		
		core:add_listener(
			dismiss_advice_str,
			"ComponentLClickUp", 
			function(context) return context.string == "button_show_advice" end,
			function(context) self:close_advisor() end, 
			false
		);
	else
		show_advisor_progress_button(false);
	end;
	
	if highlight then
		highlight_advisor_progress_button(true);
	else
		highlight_advisor_progress_button(false);
	end;
end;













-----------------------------------------------------------------------------
--- @section Progress on Advice Actions
-----------------------------------------------------------------------------


--- @function progress_on_advice_dismissed
--- @desc Calls a supplied callback when the advisor panel is closed for any reason.
--- @p function callback to call, Callback to call.
--- @p [opt=0] number delay, Delay in ms after the adisor closes before calling the callback.
--- @p [opt=false] boolean highlight on finish, Highlight the advisor close button upon finishing the currently-playing advice. This is useful for script that knows the advisor is playing, wants to highlight the close button when it finishes and be notified of when the player closes the advisor in any case.
function battle_manager:progress_on_advice_dismissed(callback, delay, highlight_on_finish)
	if not is_function(callback) then
		script_error("ERROR: progress_on_advice_dismissed() called but supplied callback [" .. tostring(callback) .. "] is not a function");
		return false;
	end;
	
	if not is_number(delay) or delay < 0 then
		delay = 0;
	end;
	
	bm:out("progress_on_advice_dismissed() called");
	
	-- a test to see if the advisor is visible on-screen at this moment
	local advisor_open_test = function()
		local uic_advisor = find_uicomponent(core:get_ui_root(), "advice_interface");
		
		return uic_advisor and uic_advisor:Visible(true) and uic_advisor:CurrentAnimationId() == "";
	end;
	
	-- a function to set up listeners for the advisor closing
	local progress_func = function()
		local is_dismissed = false;
		local is_highlighted = false;
	
		core:add_listener(
			self.progress_on_advice_dismissed_str,
			"AdviceDismissed",
			true,
			function()			
				is_dismissed = true;
				
				if highlight_on_finish then
					self:cancel_progress_on_advice_finished();
				end;
			
				-- remove the highlight if it's applied
				if is_highlighted then
					self:modify_advice(true, false);
				end;
			
				if delay > 0 then
					self:callback(function() callback() end, delay);
				else
					callback();
				end;
			end,
			false
		);
		
		-- if the highlight_on_finish flag is set, we highlight the advisor close button when the 
		if highlight_on_finish then
			local highlight_dismiss_button_func = function()
				self:remove_process(self.progress_on_advice_dismissed_str .. "_immediate_highlight");
			
				if not is_dismissed then
					is_highlighted = true;
					self:modify_advice(true, true);
				end;
			end;
			
			-- highlight dismiss button if advice is finished
			self:progress_on_advice_finished(
				function()
					highlight_dismiss_button_func()
				end
			);
			
			-- listen for a message to say that we should immediately highlight (usually sent if cutscene has been skipped)
			core:add_listener(
				self.progress_on_advice_dismissed_str .. "_immediate_highlight",
				"ScriptEventProgressOnAdviceDismissedImmediateHighlight",
				true,
				function() highlight_dismiss_button_func() end,
				false
			);
		end;
	end;
	
	-- If the advisor open test passes then set up the progress listener, otherwise wait 0.5 seconds and try it again.
	-- If the advisor fails this test three times (i.e over the course of a second) then automatically progress
	if advisor_open_test() then
		progress_func();
	else
		self:callback(
			function()
				if advisor_open_test() then
					progress_func();
				else
					self:callback(
						function()
							if advisor_open_test() then
								progress_func();
							else
								if delay > 0 then
									self:callback(function() callback() end, delay);
								else
									callback();
								end;
							end;
						end,
						500,
						self.progress_on_advice_dismissed_str
					);
				end;
			end,
			500,
			self.progress_on_advice_dismissed_str
		);
	end;
end;


--- @function cancel_progress_on_advice_dismissed
--- @desc Cancels a running @battle_manager:progress_on_advice_dismissed process.
function battle_manager:cancel_progress_on_advice_dismissed()
	core:remove_listener(self.progress_on_advice_dismissed_str);
	self:remove_process(self.progress_on_advice_dismissed_str);
	self:remove_process(self.progress_on_advice_dismissed_str .. "_immediate_highlight");
end;


--- @function progress_on_advice_dismissed_immediate_highlight
--- @desc Causes a @battle_manager:progress_on_advice_dismissed process that is listening for the advice to finish so that it can highlight the close button (i.e. the third parameter was set to true) to cancel this listener.
function battle_manager:progress_on_advice_dismissed_immediate_highlight()
	core:trigger_event("ScriptEventProgressOnAdviceDismissedImmediateHighlight");
end;


--- @function progress_on_advice_finished
--- @desc Calls a supplied callback when the advisor has stopped playing an audible sound.
--- @p function callback to call, Callback to call.
--- @p [opt=0] number delay, Delay in ms after the adisor stops before calling the callback.
--- @p [opt=5000] number playtime, Playing time for the advice item. This sets a time after which @battle_manager:progress_on_advice_finished will begin to actively poll whether the advice is still playing, as well as listening for the finish event. This is useful as it ensure this function works even during development when the advisor sound files have not yet been recorded.
function battle_manager:progress_on_advice_finished(callback, delay, playtime)
	if not is_function(callback) then
		script_error("ERROR: progress_on_advice_finished() called but supplied callback [" .. tostring(callback) .. "] is not a function");
		return false;
	end;
	
	local callback_function = function()
		self:cancel_progress_on_advice_finished();
		
		-- do the given callback
		if is_number(delay) and delay > 0 then
			self:callback(function() callback() end, delay, self.progress_on_advice_finished_str);
		else
			callback();
		end;
	end;
	
	if effect.is_advice_audio_playing() then
		-- advice is currently playing
		core:add_listener(
			self.progress_on_advice_finished_str,
			"AdviceFinishedTrigger",
			true,
			function()
				callback_function();
			end,
			false
		);
	end;
	
	playtime = playtime or 5000;
	
	-- for if sound is disabled
	self:callback(function() self:progress_on_advice_finished_poll(callback, delay, playtime, 0) end, playtime, self.progress_on_advice_finished_str);
end;


function battle_manager:progress_on_advice_finished_poll(callback, delay, playtime, count)
	count = count or 0;
	
	if not effect.is_advice_audio_playing() then
		self:cancel_progress_on_advice_finished();
		
		self:out("progress_on_advice_finished is progressing as no advice sound is playing after playtime of " .. playtime + (count * self.PROGRESS_ON_ADVICE_FINISHED_REPOLL_TIME) .. "ms");
		
		-- do the given callback
		if is_number(delay) then
			self:callback(function() callback() end, delay, self.progress_on_advice_finished_str);
		else
			callback();
		end;
		return;
	end;
	
	count = count + 1;
	
	-- sound is still playing, check again in a bit
	self:callback(function() self:progress_on_advice_finished_poll(callback, delay, playtime, count) end, self.PROGRESS_ON_ADVICE_FINISHED_REPOLL_TIME, self.progress_on_advice_finished_str);
end;


--- @function cancel_progress_on_advice_finished
--- @desc Cancels a running @battle_manager:progress_on_advice_finished process.
function battle_manager:cancel_progress_on_advice_finished()
	core:remove_listener(self.progress_on_advice_finished_str);
	self:remove_process(self.progress_on_advice_finished_str);
end;











----------------------------------------------------------------------------
--- @section Objectives
--- @desc Upon creation, the battle manager automatically creates an objectives manager object which it stores internally. Most of these functions provide a passthrough interface to the most commonly-used functions on the objectives manager. See the documentation on the @objectives_manager page for more details.
--- @desc Note that @battle_manager:set_locatable_objective is native to the battle manager and is not related to the objectives manager.
----------------------------------------------------------------------------


--- @function set_objective
--- @desc Pass-through function for @objectives_manager:set_objective on the objectives manager. Sets up a scripted objective for the player, which appears in the scripted objectives panel. This objective can then be updated, removed, or marked as completed or failed by the script at a later time.
--- @desc A key to the scripted_objectives table must be supplied with set_objective, and optionally one or two numeric parameters to show some running count related to the objective. To update these parameter values later, <code>set_objective</code> may be re-called with the same objective key and updated values.
--- @p string objective key, Objective key, from the scripted_objectives table.
--- @p [opt=nil] number param a, First numeric objective parameter. If set, the objective will be presented to the player in the form [objective text]: [param a]. Useful for showing a running count of something related to the objective.
--- @p [opt=nil] number param b, Second numeric objective parameter. A value for the first must be set if this is used. If set, the objective will be presented to the player in the form [objective text]: [param a] / [param b]. Useful for showing a running count of something related to the objective.
function battle_manager:set_objective(...)
	return self.objectives:set_objective(...);
end;


--- @function complete_objective
--- @desc Pass-through function for @objectives_manager:complete_objective on the objectives manager. Marks a scripted objective as completed for the player to see. Note that it will remain on the scripted objectives panel until removed with @battle_manager:remove_objective.
--- @desc Note also that is possible to mark an objective as complete before it has been registered with @battle_manager:set_objective - in this case, it is marked as complete as soon as @battle_manager:set_objective is called.
--- @p string objective key, Objective key, from the scripted_objectives table.
function battle_manager:complete_objective(...)
	return self.objectives:complete_objective(...);
end;


--- @function fail_objective
--- @desc Pass-through function for @objectives_manager:fail_objective on the objectives manager. Marks a scripted objective as failed for the player to see. Note that it will remain on the scripted objectives panel until removed with @battle_manager:remove_objective.
--- @p string objective key, Objective key, from the scripted_objectives table.
function battle_manager:fail_objective(...)
	return self.objectives:fail_objective(...);
end;


--- @function remove_objective
--- @desc Pass-through function for @objectives_manager:remove_objective on the objectives manager. Removes a scripted objective from the scripted objectives panel.
--- @p string objective key, Objective key, from the scripted_objectives table.
function battle_manager:remove_objective(...)
	return self.objectives:remove_objective(...);
end;


--- @function activate_objective_chain
--- @desc Pass-through function for @objectives_manager:activate_objective_chain. Starts a new objective chain - see the documentation on the @objectives_manager page for more details.
--- @p string chain name, Objective chain name.
--- @p string objective key, Key of initial objective, from the scripted_objectives table.
--- @p [opt=nil] number number param a, First numeric parameter - see the documentation for @battle_manager:set_objective for more details
--- @p [opt=nil] number number param b, Second numeric parameter - see the documentation for @battle_manager:set_objective for more details
function battle_manager:activate_objective_chain(...)
	return self.objectives:activate_objective_chain(...);
end;


--- @function update_objective_chain
--- @desc Pass-through function for @objectives_manager:update_objective_chain. Updates an existing objective chain - see the documentation on the @objectives_manager page for more details.
--- @p string chain name, Objective chain name.
--- @p string objective key, Key of initial objective, from the scripted_objectives table.
--- @p [opt=nil] number number param a, First numeric parameter - see the documentation for @battle_manager:set_objective for more details
--- @p [opt=nil] number number param b, Second numeric parameter - see the documentation for @battle_manager:set_objective for more details
function battle_manager:update_objective_chain(...)
	return self.objectives:update_objective_chain(...);
end;


--- @function end_objective_chain
--- @desc Pass-through function for @objectives_manager:end_objective_chain. Ends an existing objective chain - see the documentation on the @objectives_manager page for more details.
--- @p string chain name, Objective chain name.
function battle_manager:end_objective_chain(...)
	return self.objectives:end_objective_chain(...);
end;


--- @function reset_objective_chain
--- @desc Pass-through function for @objectives_manager:reset_objective_chain. Resets an objective chain so that it may be called again - see the documentation on the @objectives_manager page for more details.
--- @p string chain name, Objective chain name.
function battle_manager:reset_objective_chain(...)
	return self.objectives:reset_objective_chain(...);
end;


--- @function set_locatable_objective
--- @desc Sets up a locatable objective in battle. This will appear in the scripted objectives list alongside a zoom-to button which, when clicked, will zoom the camera to a location on the battlefield. The key of the objective text, as well as the camera position/target and zoom duration must all be supplied. The button visibility, on-click listener, and camera movements are all handled in script (which means the camera movement doesn't work when paused..)
--- @p string objective key, Objective key, from the scripted_objectives table.
--- @p vector camera position, Final camera position.
--- @p vector camera target, Final camera target.
--- @p number zoom duration, Duration of camera movement in seconds.
function battle_manager:set_locatable_objective(obj_key, cam_pos, cam_targ, duration)
	if not is_string(obj_key) then
		script_error("ERROR: set_locatable_objective() called but supplied objective key [" .. tostring(obj_key) .. "] is not a string");
		return false;
	end;
	
	if not is_vector(cam_pos) then
		script_error("ERROR: set_locatable_objective() called but supplied camera position [" .. tostring(cam_pos) .. "] is not a vector");
		return false;
	end;
	
	if not is_vector(cam_targ) then
		script_error("ERROR: set_locatable_objective() called but supplied camera position [" .. tostring(cam_targ) .. "] is not a vector");
		return false;
	end;
	
	if not is_number(duration) or duration <= 0 then
		script_error("ERROR: set_locatable_objective() called but supplied zoom duration [" .. tostring(duration) .. "] is not a number > 0");
		return false;
	end;
	
	-- show objective
	self.objectives:set_objective(obj_key);
	
	-- find and show the zoom button
	-- note: in 3K the objectives are now show separately to the objectives panel, so we no longer use that as a stepping-stone to finding them
	local uic_button_zoom = find_uicomponent(core:get_ui_root(), obj_key, "button_zoom");
	if not uic_button_zoom then
		script_error("ERROR: set_locatable_objective() called but couldn't find uic_button_zoom");
		return false;
	end;
	
	uic_button_zoom:SetVisible(true);
	
	core:add_listener(
		obj_key,
		"ComponentLClickUp",
		function(context)
			return UIComponent(context.component) == uic_button_zoom;
		end,
		function()
			self:out("* set_locatable_objective() is scrolling the camera to pos: " .. v_to_s(cam_pos) .. ", targ: " .. v_to_s(cam_targ) .. " over duration " .. duration .. "ms as zoom button has been clicked");
			self.battle:camera():move_to(cam_pos, cam_targ, duration, false, 0);
		end,
		true
	);
end;








----------------------------------------------------------------------------
--- @section Infotext
--- @desc These functions provide a passthrough interface to the most commonly-used functions on the infotext manager, which the battle manager creates automatically.
----------------------------------------------------------------------------


--- @function add_infotext
--- @desc Pass-through function for @infotext_manager:add_infotext. Adds one or more lines of infotext to the infotext panel - see the documentation on the @infotext_manager page for more details.
--- @p object first param, Can be a string key from the advice_info_texts table, or a number specifying an initial delay in ms after the panel animates onscreen and the first infotext item is shown.
--- @p ... additional infotext strings, Additional infotext strings to be shown. <code>add_infotext</code> fades each of them on to the infotext panel in a visually-pleasing sequence.
function battle_manager:add_infotext(...)
	return self.infotext:add_infotext(...);
end;


--- @function remove_infotext
--- @desc Pass-through function for @infotext_manager:remove_infotext. Removes a line of infotext from the infotext panel.
--- @p string infotext key
function battle_manager:remove_infotext(...)
	return self.infotext:remove_infotext(...);
end;


--- @function clear_infotext
--- @desc Pass-through function for @infotext_manager:clear_infotext. Clears the infotext panel.
function battle_manager:clear_infotext(...)
	return self.infotext:clear_infotext(...);
end;









-----------------------------------------------------------------------------
--- @section Subtitles
-----------------------------------------------------------------------------

--- @function show_subtitle
--- @desc Shows a cutscene subtitle on-screen.
--- @p string subtitle key
--- @p [opt=false] boolean full key supplied, Full localised key supplied. If false, or if no value supplied, the script assumes that the key is from the scripted_subtitles table and pads the supplied key out accordingly.
--- @p_long_desc If the key has been supplied in the full localisation format (i.e. <code>[table]_[field_of_text]_[key_from_table]</code>), set this to true.
--- @p [opt=false] boolean force subtitle on, Forces the subtitle to display, overriding the user's preferences.
function battle_manager:show_subtitle(key, full_key_supplied, should_force)
	
	if not is_string(key) then
		script_error("ERROR: show_subtitle() called but supplied key [" .. tostring(key) .. "] is not a string");
		return false;
	end;
	
	-- only proceed if we're forcing the subtitle to play, or if the subtitle preferences setting is on
	if not should_force and not effect.subtitles_enabled() then
	 	return;
	end;
	
	local full_key;
	
	if not full_key_supplied then
		full_key = "scripted_subtitles_localised_text_" .. key;
	else
		full_key = key;
	end;
	
	local localised_text = effect.get_localised_string(full_key);
	
	if not is_string(localised_text) then
		script_error("ERROR: show_subtitle() called but could not find any localised text corresponding with supplied key [" .. tostring(key) .. "] in scripted_subtitles table");
		return false;
	end;

	local ui_root = core:get_ui_root();
	
	self:out("show_subtitle() called, supplied key is [" .. key .. "] and localised text is [" .. localised_text .. "]");

	-- create the subtitles component if it doesn't already exist
	if not self.subtitles_component_created then
		ui_root:CreateComponent("scripted_subtitles", "UI/Campaign UI/scripted_subtitles.twui.xml");
		self.subtitles_component_created = true;
	end;
	
	-- find the subtitles component
	local uic_subtitles = find_uicomponent(ui_root, "scripted_subtitles", "text_child");
	
	if not uic_subtitles then
		script_error("ERROR: show_subtitles() could not find the scripted_subtitles uicomponent");
		return false;
	end;
	
	-- set the text on it
	uic_subtitles:SetStateText(localised_text, full_key);
	
	-- make the subtitles component visible if it's not already
	if not self.subtitles_visible then
		uic_subtitles:SetVisible(true);
		uic_subtitles:RegisterTopMost();
		self.subtitles_visible = true;
	end;
end;


--- @function hide_subtitles
--- @desc Hides any currently-shown subtitle.
function battle_manager:hide_subtitles()

	self:out("hide_subtitles() called");

	if self.subtitles_visible then
		-- find the subtitles component
		local uic_subtitles = find_uicomponent(core:get_ui_root(), "scripted_subtitles", "text_child");
		if uic_subtitles then
			uic_subtitles:RemoveTopMost();
			uic_subtitles:SetVisible(false);
		end;
		self.subtitles_visible = false;
	end;
end;










-----------------------------------------------------------------------------
--- @section Help Message Queue
--- @desc Help messages are used primarily in quest battles. They are text messages faded onto the HUD above the army panel, that persist for a time and then fade off. The battle manager queues them so they don't overwrite one another.
-----------------------------------------------------------------------------


--- @function queue_help_message
--- @desc Enqueues a help message for showing on-screen.
--- @p string key, Help message key, from the scripted_objectives table.
--- @p [opt=5000] number duration, Duration that the message will persist on-screen for in ms. If this is specified then a fade time must also be set.
--- @p [opt=2000] number fade time, Time that the message will take to fade on/fade off in ms. If this is specified then a duration must also be set.
--- @p [opt=false] boolean high priority, Set this to true to set this message to high priority. High priority messages are bumped to the top of the queue.
--- @p [opt=false] boolean play after battle victory, By default, help messages won't play after the battle has been won. Set this to true to allow this message to play after this point.
--- @p [opt=nil] function callback, Callback to call when the message actually starts to show on-screen.
function battle_manager:queue_help_message(key, duration, fade_time, high_priority, play_after_battle_victory, callback)

	if not is_string(key) then
		script_error("ERROR: queue_help_message() called but supplied message key [" .. tostring(key) .. "] is not a string");
		return false;
	end;
	
	if not is_number(duration) or duration <= 0 then
		script_error("ERROR: queue_help_message() called but supplied duration [" .. tostring(duration) .. "] is not a number greater than zero");
		return false;
	end;
	
	if not is_number(fade_time) or fade_time <= 0 then
		script_error("ERROR: queue_help_message() called but supplied fade time [" .. tostring(fade_time) .. "] is not a number greater than zero");
		return false;
	end;
	
	if duration and not fade_time then
		script_error("WARNING: queue_help_message() called and duration has been specified but no fade time was also supplied - both must be supplied, or neither. Discarding them.");
		return false;
	end;

	-- if the battle is won then don't bother showing any more messages (unless we are told to)
	if self.battle_is_won and not play_after_battle_victory then
		return;
	end;
	
	local help_message_record = {};
	help_message_record.key = key;
	help_message_record.duration = duration;
	help_message_record.fade_time = fade_time;
	help_message_record.high_priority = high_priority;
	help_message_record.play_after_battle_victory = play_after_battle_victory;
	help_message_record.callback = callback;
	
	if high_priority then
		table.insert(self.help_messages, 1, help_message_record);
	else
		table.insert(self.help_messages, help_message_record);
	end;
	
	-- if no help messages are playing then try and play one
	if not self.help_messages_showing then
		self:show_next_help_message();
	end;
end;


function battle_manager:show_next_help_message()
	
	local help_messages = self.help_messages;

	-- if we have no more help messages then exit
	if #help_messages == 0 then
		self.help_messages_showing = false;
		return;
	end;
	
	-- get the first help message
	local help_message_record = help_messages[1];
	
	
	-- if the battle is won then don't bother showing any more messages (unless we are told to)
	if self.battle_is_won and not help_message_record.play_after_battle_victory then
		self.help_messages_showing = false;
		return;
	end;
	
	-- remove the message from our table
	table.remove(help_messages, 1);
	
	-- show the message
	bm:show_objective(help_message_record.key, help_message_record.duration, help_message_record.fade_time);
	self.help_messages_showing = true;
	
	-- find the message panel and reposition it so that it appears about the army panel (its default position is to work with the black cinematic borders)	
	local uic_help_panel = find_uicomponent(core:get_ui_root(), "objective_panel");
	
	if not uic_help_panel then
		script_error("ERROR: show_help_msg() couldn't find objective_panel");
		return false;
	end;
	
	local screen_x, screen_y = core:get_screen_resolution();
	local component_x, component_y = uic_help_panel:Position();

	uic_help_panel:MoveTo(component_x, screen_y - 410);
	
	-- if we have a callback, call it
	if help_message_record.callback then
		help_message_record.callback();
	end;
	
	-- we calculate the time at which this message will have expired based on the game running time, as the message runs by this rather than model time
	local help_message_expiry_time = os.clock() + (help_message_record.duration + help_message_record.fade_time * 2) / 1000;
	
	-- watch the time and show the next help message when this one has expired
	bm:watch(
		function() return os.clock() >= help_message_expiry_time end,
		0,
		function()
			self:show_next_help_message()
		end,
		"battle_manager_help_message_queue"
	);
end;













-----------------------------------------------------------------------------
--- @section Camera
-----------------------------------------------------------------------------


--- @function enable_camera_movement
--- @desc Allows script to prevents player movement of the camera without stealing input - other game interactions are still permitted. Supply false as an argument to disable camera movement.
--- @p [opt=true] boolean enable movement
function battle_manager:enable_camera_movement(value)
	local cam = self:camera();
	
	if value == false then
		cam:disable_functionality("CAMERA_ALL_FUNCTIONS");
	else
		cam:enable_functionality("CAMERA_ALL_FUNCTIONS");
	end;
end;


--- @function cache_camera
--- @desc Caches the current position/target of the camera for later retrieval.
function battle_manager:cache_camera()
	local cam = self:camera();
	self.cached_camera_pos = cam:position();
	self.cached_camera_targ = cam:target();
end;


--- @function get_cached_camera_pos
--- @desc Gets the cached position of the camera. This must be called after the position has been cached with @battle_manager:cache_camera (else it will return false).
function battle_manager:get_cached_camera_pos()
	return self.cached_camera_pos;
end;


--- @function get_cached_camera_targ
--- @desc Gets the cached target of the camera. This must be called after the position has been cached with @battle_manager:cache_camera (else it will return false).
function battle_manager:get_cached_camera_targ()
	return self.cached_camera_targ;
end;










-----------------------------------------------------------------------------
--- @section Camera Movement Tracker
--- @desc The camera movement tracker is used by some tutorial scripts to track how the player is moving the camera.
-----------------------------------------------------------------------------


--- @function start_camera_movement_tracker
--- @desc Starts the camera movement tracker. Only tutorial scripts which need to query camera tracker information need to do this.
function battle_manager:start_camera_movement_tracker()
	self.camera_tracker_active = true;
	self.original_cached_camera_pos = self:camera():position();
	self.last_cached_camera_pos = self.original_cached_camera_pos;
	self.camera_tracker_distance_travelled = 0;

	self:repeat_callback(function() self:update_camera_movement_tracker() end, 200, "battle_manager_camera_movement_tracker");
end;


--- @function stop_camera_movement_tracker
--- @desc Stops the camera movement tracker.
function battle_manager:stop_camera_movement_tracker()
	self:remove_process("battle_manager_camera_movement_tracker");
end;


function battle_manager:update_camera_movement_tracker()
	local cam = self:camera();
	local cam_position = cam:position();
	
	self.camera_tracker_distance_travelled = self.camera_tracker_distance_travelled + cam_position:distance_xz(self.last_cached_camera_pos);
	
	self.last_cached_camera_pos = cam_position;
end;


--- @function get_camera_altitude_change
--- @desc Gets the difference in camera altitude between now and when the tracker was started. The returned value is absolute (always positive).
--- @r number difference in m
function battle_manager:get_camera_altitude_change()
	if not is_vector(self.original_cached_camera_pos) then
		script_error("ERROR: get_camera_altitude_change() called but no camera position cached - call start_camera_movement_tracker() first");
		return 0;
	end;
	
	local cam = self:camera();
	
	return math.abs(cam:position():get_y() - self.original_cached_camera_pos:get_y());
end;


--- @function get_camera_distance_travelled
--- @desc Gets the total distance the camera has travelled between now and when the tracker was started. This distance is not exact, but gives the calling script an indication of how much the player is moving the camera.
--- @r number distance in m
function battle_manager:get_camera_distance_travelled()
	return self.camera_tracker_distance_travelled;
end;












-----------------------------------------------------------------------------
--- @section Ping Icons
--- @desc Encapsulated functions to give control over ping icon display
-----------------------------------------------------------------------------


--- @function add_ping_icon
--- @desc Wrapper for code functionality for adding ping icons.
--- @p number pos_x
--- @p number pos_y
--- @p number pos_z
--- @p number ping_type index based off MULTIPLAYER_PING_TYPE code enum
--- @p boolean Is this ping a waypoint
--- @p number Rotation of the ping in degrees
--- @p number [Opt = 0] A terrain projected ring under the ping. 0 will equal no ring.
function battle_manager:add_ping_icon(pos_x, pos_y, pos_z, ping_type, is_waypoint, rotation, optional_ring_radius)
	optional_ring_radius = optional_ring_radius or 0;

	self:out("* adding ping icon at [" .. tostring(pos_x) .. ", " .. tostring(pos_y) .. ", " .. tostring(pos_z) .. "], type [" .. tostring(ping_type) .. "], is_waypoint [" .. tostring(is_waypoint) .. "], rotation [" .. tostring(rotation) .. "]");
	return self.battle:add_ping_icon(pos_x, pos_y, pos_z, ping_type, is_waypoint, rotation, optional_ring_radius);
end;


--- @function remove_ping_icon
--- @desc Wrapper for code functionality for removing ping icons. Must match position of an existing ping icon.
--- @p number pos_x
--- @p number pos_y
--- @p number pos_z
function battle_manager:remove_ping_icon(pos_x, pos_y, pos_z)
	self:out("* removing ping icon at [" .. tostring(pos_x) .. ", " .. tostring(pos_y) .. ", " .. tostring(pos_z) .. "]");
	return self.battle:remove_ping_icon(pos_x, pos_y, pos_z);
end;


--- @function add_named_ping_icon
--- @desc Shows/hides the battle UI from script.
--- @p string a unique name of the ping, to allow it to be added/removed without knowing the position.
--- @p number pos_x
--- @p number pos_y
--- @p number pos_z
--- @p number ping_type index based off MULTIPLAYER_PING_TYPE code enum
--- @p boolean Is this ping a waypoint
--- @p number Rotation of the ping in degrees
function battle_manager:add_named_ping_icon(name, pos_x, pos_y, pos_z, ping_type, is_waypoint, rotation, optional_ring_radius)
	-- Only add our ping if it was able to register otherwise it can never be removed by name!
	if self:int_register_ping_data(name, pos_x, pos_y, pos_z) then
		self:add_ping_icon(pos_x, pos_y, pos_z, ping_type, is_waypoint, rotation, optional_ring_radius);
	end;
end;


--- @function add_named_terrain_offset_ping_icon
--- @desc Creates a ping icon at the XZ position, with a set terrain heigh offset.
--- @p string a unique name of the ping, to allow it to be added/removed without knowing the position.
--- @p number pos_x
--- @p number the height off the terrain in m
--- @p number pos_z
--- @p number ping_type index based off MULTIPLAYER_PING_TYPE code enum
--- @p boolean Is this ping a waypoint
--- @p number Rotation of the ping in degrees
function battle_manager:add_named_terrain_offset_ping_icon(name, pos_x, height_offset, pos_z, ping_type, is_waypoint, rotation, optional_ring_radius)
	-- Get the terrain height at the specified position and offset it by our amount.
	local pos_y = self:get_terrain_height(pos_x, pos_z);
	pos_y = pos_y + height_offset;

	self:add_named_ping_icon(name, pos_x, pos_y, pos_z, ping_type, is_waypoint, rotation, optional_ring_radius);
end;


--- @function remove_named_ping_icon
--- @desc Removes a ping icon by name.
--- @p string a unique name of the ping, to allow it to be added/removed without knowing the position.
function battle_manager:remove_named_ping_icon(name)
	local ping_data = self:int_get_ping_data(name);

	if ping_data then
		self:remove_ping_icon(ping_data.position:get_x(), ping_data.position:get_y(), ping_data.position:get_z());
		self:int_deregister_ping_data(name);
	end;
end;


--- @function int_register_ping_data
--- @desc Shows/hides the battle UI from script.
--- @p string a unique name of the ping, to allow it to be added/removed without knowing the position.
--- @p number pos_x
--- @p number pos_y
--- @p number pos_z
--- @r bool Did it register.
function battle_manager:int_register_ping_data(name, pos_x, pos_y, pos_z)
	if self:int_get_ping_data(name, true) then
		script_error("ERROR: int_register_ping_data() trying to register a ping which already exists. This is not supported. " .. tostring(name));
		return false;
	end;

	table.insert(
		self.ping_data_list, 
		{ 
			name = name, 
			position = v(pos_x, pos_y, pos_z) 
		}
	);

	return true;
end;

--- @function int_deregister_ping_data
--- @desc Removes a ping data from the list.
--- @p string name of the ping
--- @r bool Did it deregister?
function battle_manager:int_deregister_ping_data(name)
	for i, v in ipairs(self.ping_data_list) do
		if v.name == name then
			table.remove(self.ping_data_list, i);
			return true;
		end;
	end;

	return false;
end;


--- @function int_get_ping_data
--- @desc Tries to find a ping data with the matching name.
--- @p string name of the ping
--- @r ping_data or nil.
function battle_manager:int_get_ping_data(name, suppress_errors)
	suppress_errors = suppress_errors or false;

	for i, v in ipairs(self.ping_data_list) do
		if v.name == name then
			return v;
		end;
	end;

	if not suppress_errors then
		script_error("ERROR: int_get_ping_data() no ping with name [" .. tostring(name) .. "] found.")
	end;

	return nil;
end;




-----------------------------------------------------------------------------
--- @section Showing/Hiding UI
-----------------------------------------------------------------------------


--- @function show_ui
--- @desc Shows/hides the battle UI from script.
--- @p [opt=true] boolean should show
function battle_manager:show_ui(value)

	if value == nil then
		value = true;
	else
		value = not not value;
	end;

	self:show_army_panel(value);
	self:show_winds_of_magic_panel(value);
	self:show_portrait_panel(value);
	self:show_top_bar(value);
	self:show_radar_frame(value);
end;


--- @function show_army
--- @desc Shows/hides the army panel.
--- @p [opt=true] boolean should show, Should show.
--- @p [opt=false] boolean immediate, Hide immediately. If the first parameter is false and this is true, the panel will not animate offscreen but will instead immediately disappear.
function battle_manager:show_army_panel(value, immediate)
	local uic = bm:ui_component("battle_orders");
	
	if not uic then
		script_error("ERROR: show_army_panel() called but could not find uicomponent");
		return false;
	end;
	
	if value == false then
		if immediate then
			uic:SetVisible(false);
		end;
		uic:TriggerAnimation("tut_hide");
	else
		uic:SetVisible(true);
		uic:TriggerAnimation("tut_show");
	end;
end;


--- @function show_winds_of_magic_panel
--- @desc Shows/hides the winds of magic panel
--- @p [opt=true] boolean should show, Should show.
--- @p [opt=false] boolean immediate, Hide immediately. If the first parameter is false and this is true, the panel will not animate offscreen but will instead immediately disappear.
function battle_manager:show_winds_of_magic_panel(value, immediate)
	local uic = bm:ui_component("winds_of_magic");
	
	if not uic then
		script_error("ERROR: show_winds_of_magic_panel() called but could not find uicomponent");
		return false;
	end;
	
	if value == false then
		if immediate then
			uic:SetVisible(false);
		end;
		uic:TriggerAnimation("tut_hide");
	else
		uic:SetVisible(true);
		uic:TriggerAnimation("tut_show");
	end;
end;


--- @function show_portrait_panel
--- @desc Shows/hides the unit portrait panel.
--- @p [opt=true] boolean should show, Should show.
--- @p [opt=false] boolean immediate, Hide immediately. If the first parameter is false and this is true, the panel will not animate offscreen but will instead immediately disappear.
function battle_manager:show_portrait_panel(value, immediate)
	local uic = bm:ui_component("porthole_parent");
	
	if not uic then
		script_error("ERROR: show_portrait_panel() called but could not find uicomponent");
		return false;
	end;
	
	if value == false then
		if immediate then
			uic:SetVisible(false);
		end;
		uic:TriggerAnimation("tut_hide");
	else
		uic:SetVisible(true);
		uic:TriggerAnimation("tut_show");
	end;
end;


--- @function show_top_bar
--- @desc Shows/hides the top bar on the battle interface.
--- @p [opt=true] boolean should show, Should show.
--- @p [opt=false] boolean immediate, Hide immediately. If the first parameter is false and this is true, the panel will not animate offscreen but will instead immediately disappear.
function battle_manager:show_top_bar(value, immediate)
	local uic = bm:ui_component("BOP_frame");
	
	if not uic then
		script_error("ERROR: show_top_bar() called but could not find uicomponent");
		return false;
	end;
	
	if value == false then
		if immediate then
			uic:SetVisible(false);
		end;
		uic:TriggerAnimation("tut_hide");
	else
		uic:SetVisible(true);
		uic:TriggerAnimation("tut_show");
	end;
end;


--- @function show_radar_frame
--- @desc Shows/hides the radar.
--- @p [opt=true] boolean should show, Should show.
--- @p [opt=false] boolean immediate, Hide immediately. If the first parameter is false and this is true, the panel will not animate offscreen but will instead immediately disappear.
function battle_manager:show_radar_frame(value, immediate)
	local uic = bm:ui_component("radar_holder");
	
	if not uic then
		script_error("ERROR: show_radar_frame() called but could not find uicomponent");
		return false;
	end;
	
	if value == false then
		if immediate then
			uic:SetVisible(false);
		end;
		uic:TriggerAnimation("tut_hide");
	else
		uic:SetVisible(true);
		uic:TriggerAnimation("tut_show");
	end;		
end;


--- @function show_start_battle_button
--- @desc Shows/hides the start battle button.
--- @p [opt=true] boolean should show, Should show.
--- @p [opt=false] boolean is multiplayer, Set this to true if this is a multiplayer battle.
function battle_manager:show_start_battle_button(value, is_multiplayer)
	if value ~= false then
		value = true;
	end;
	
	local uic_finish_deployment = bm:ui_component("finish_deployment");
	
	if uic_finish_deployment then
		uic_finish_deployment:SetVisible(value);
		
		if is_multiplayer then
			local uic_mp = find_uicomponent(uic_finish_deployment, "deployment_end_mp");
			if uic_mp then
				uic_mp:SetVisible(value);
			end;
		else
			local uic_sp = find_uicomponent(uic_finish_deployment, "deployment_end_sp");
			if uic_sp then
				uic_sp:SetVisible(value);
			end;
		end;
	end;
end;


--- @function show_ui_options_panel
--- @desc Shows/hides the ui options rollout panel.
--- @p [opt=true] boolean should show
function battle_manager:show_ui_options_panel(value)
	local uic_spacebar_options = bm:ui_component("spacebar_options");
	
	if not uic_spacebar_options then
		script_error("ERROR: show_ui_options_panel() called but could not find uicomponent uic_spacebar_options");
		return false;
	end;
	
	local uic_panel = UIComponent(uic_spacebar_options:Find(0));
	
	if not uic_panel then
		script_error("ERROR: show_ui_options_panel() called but could not find uicomponent uic_spacebar_options");
		return false;
	end;
	
	if value == false then
		uic_panel:SetVisible(false);
	else
		uic_panel:SetVisible(true);
	end;
end;


--- @function enable_spell_browser_button
--- @desc Enables/disables the spell browser button on the battle interface. A disabled button will still be visible, but greyed-out.
--- @p [opt=true] boolean should enable
function battle_manager:enable_spell_browser_button(value)
	local uic_spell_browser_button = bm:ui_component("button_spell_browser");
	
	if not uic_spell_browser_button then
		script_error("ERROR: enable_spell_browser_button() called but could not find uicomponent uic_button_spell_browser");
		return false;
	end;
	
	if value == false then
		uic_spell_browser_button:SetState("inactive");
		self.spell_browser_button_text = uic_spell_browser_button:GetTooltipText();
		uic_spell_browser_button:SetTooltipText("", true);
	else
		uic_spell_browser_button:SetState("active");
		
		if self.spell_browser_button_text then
			uic:SetTooltipText(self.spell_browser_button_text, true);
		end;
	end;
end;


--- @function enable_ui_hiding
--- @desc Enables/disables UI hiding. With UI hiding disabled the player will not be able to hide the UI by pressing K or alt-K. This function does not prevent the script from being able to hide or show the UI.
--- @p [opt=true] boolean should enable
function battle_manager:enable_ui_hiding(value)
	if value ~= false then
		value = true;
	end;

	self.ui_hiding_enabled = value;

	self.battle:disable_shortcut("toggle_ui", not value);
	self.battle:disable_shortcut("toggle_ui_with_borders", not value);
end;


--- @function is_ui_hiding_enabled
--- @desc Returns false if UI hiding has been disabled with @battle_manager:enable_ui_hiding, otherwise true.
function battle_manager:is_ui_hiding_enabled()
	return self.ui_hiding_enabled;
end;










-----------------------------------------------------------------------------
--- @section Engagement Monitor
--- @desc The Engagement monitor is a set of processes that continually query the battle state and either store information for other scripts to look up or trigger events for other scripts to listen to. The engagement monitor doesn't start automatically, but must be started by scripts that need the processing and information that it requires, mostly advice/tutorial scripts.
--- @desc The Engagement monitor tracks the following information:
--- @desc &emsp;- the distance between the two alliances on the battlefield, which other scripts can query instead of continually working it out themselves which is potentially expensive.
--- @desc &emsp;- the number/proportion of the player's alliance that is engaged in melee/under fire.
--- @desc &emsp;- the average altitude of both the player and enemy alliance.
--- @desc The Engagement monitor also triggers the following events:
--- @desc &emsp;- ScriptEventBattleArmiesEngaging, when the two sides close to within 100m or once more than 40% of the player's army is under fire.
--- @desc &emsp;- ScriptEventPlayerGeneralWounded, if the player's general is wounded (they must be invincible).
--- @desc &emsp;- ScriptEventPlayerGeneralDies, if the player's general dies (not invincible).
--- @desc &emsp;- ScriptEventEnemyGeneralWounded, if the enemy general is wounded (they must be invincible).
--- @desc &emsp;- ScriptEventEnemyGeneralDies, if the enemy general dies (not invincible).
--- @desc &emsp;- ScriptEventPlayerGeneralRouts, if the player's general routs.
--- @desc &emsp;- ScriptEventEnemyGeneralRouts, if the enemy general routs.
--- @desc &emsp;- ScriptEventPlayerUnitRouts, if one of the player's units routs.
--- @desc &emsp;- ScriptEventPlayerUnitRallies, if one of the player's units rallies.
--- @desc &emsp;- ScriptEventEnemyUnitRouts, if one of the enemy units routs.
--- @desc It also triggers ScriptEventPlayerApproachingVictoryPoint as an approximation of the player approaching a victory point. The implementation for this can charitably be described as a best guess - it happens two minutes after the player docks to the walls or the gate.
-----------------------------------------------------------------------------

--- @function start_engagement_monitor
--- @desc Starts the engagement monitor. This must be called before the "Deployed" phase change occurs (i.e. before the end of deployment).
function battle_manager:start_engagement_monitor()
	if self.engagement_monitor_started then
		script_error("WARNING: start_engagement_monitor() called engagement monitor is already started, disregarding");
		return false;
	end;
	
	self.engagement_monitor_started = true;
	
	-- start live condition listeners when the battle proper starts
	bm:register_phase_change_callback("Deployed", function() self:engagement_monitor_battle_starts() end);
end;


function battle_manager:engagement_monitor_battle_starts()

	local player_alliance = self:get_player_alliance();
	local enemy_alliance = self:get_non_player_alliance();
	
	local num_units_player_alliance = num_units_in_collection(player_alliance);
	local num_units_enemy_alliance = num_units_in_collection(enemy_alliance);
	
	local main_player_army = self:get_player_army();
	local main_enemy_army = self:get_first_non_player_army();
	
	local player_units_routing = {};

	local player_pending_duelists = {};
	local player_active_duelists = {};
	local player_duelists_won = {};
	local player_duelists_lost = {};

	-- poll the distance between the two forces and cache the result so other scripts can look it up (intended for advice)
	self.cached_distance_between_forces = distance_between_forces(player_alliance, enemy_alliance, true);
	self:repeat_callback(
		function()
			self.cached_distance_between_forces = distance_between_forces(player_alliance, enemy_alliance, true);
		end,
		1100,
		"battle_manager_engagement_monitor"
	);
	
	-- divide-by-zero check
	if num_units_player_alliance == 0 then
		script_error("ERROR: engagement_monitor_battle_starts() called but the number of units in the player's alliance seems to be zero, how can this be?");
		return false;
	end;
	
	-- poll the number of units engaged between the two forces and cache the result so other scripts can look it up (intended for advice)
	local cache_num_units_engaged = function()
		self.cached_num_units_engaged = num_units_engaged(player_alliance);
		self.cached_proportion_engaged = self.cached_num_units_engaged / num_units_player_alliance;
		self.cached_num_units_under_fire = num_units_under_fire(player_alliance);
		self.cached_proportion_under_fire = self.cached_num_units_under_fire / num_units_player_alliance;
	end;
	
	cache_num_units_engaged();
	
	self:repeat_callback(
		function()
			cache_num_units_engaged();
		end,
		1000,
		"battle_manager_engagement_monitor"
	);
	
	
	--
	-- watch for the two sides engaging
	--
	self:watch(
		function()
			local distance_between_forces = self:get_distance_between_forces();
			local proportion_under_fire = self:get_proportion_under_fire();
			
			return self:get_distance_between_forces() < 100 or self:get_proportion_under_fire() > 0.4
		end,
		0,
		function()
			self:out("ScriptEventBattleArmiesEngaging event triggered, distance between forces is " .. tostring(self:get_distance_between_forces()) .. " and proportion under fire is " .. tostring(self:get_proportion_under_fire()));
			core:trigger_event("ScriptEventBattleArmiesEngaging");
		end,
		"engagement_monitor_two_sides_engaging_watch"
	);
	
	
	--
	-- work out the altitude of the main player and main enemy army
	--
	
	self.main_player_army_altitude = get_average_altitude(main_player_army);
	self.main_enemy_army_altitude = get_average_altitude(main_enemy_army);
	self:repeat_callback(
		function()
			self.main_player_army_altitude = get_average_altitude(main_player_army);
			self.main_enemy_army_altitude = get_average_altitude(main_enemy_army);
		end,
		4900,
		"battle_manager_altitude_monitor"
	);
	
	
	--
	-- watch for the main player and enemy generals dying and trigger events
	--
	
	-- player
	self:watch(
		function()
			return not main_player_army:is_commander_alive();
		end,
		0,
		function()
			if main_player_army:is_commander_invincible() then
				core:trigger_event("ScriptEventPlayerGeneralWounded");
			else
				core:trigger_event("ScriptEventPlayerGeneralDies");
			end;
		end,
		"engagement_monitor_player_commander_alive_watch"
	);
	
	-- enemy
	self:watch(
		function()
			return not main_enemy_army:is_commander_alive();
		end,
		0,
		function()
			if main_enemy_army:is_commander_invincible() then
				core:trigger_event("ScriptEventEnemyGeneralWounded");
			else
				core:trigger_event("ScriptEventEnemyGeneralDies");
			end;
		end,
		"engagement_monitor_enemy_commander_alive_watch"
	);

	
	--
	-- listen for units and commanders routing
	--
	
	-- listener for player commmander routing
	core:add_listener(
		"player_commander_routs_watch",
		"BattleCommandingUnitRouts",
		true,
		function()
			self:callback(
				function()
					local player_units = main_player_army:units();
					
					for i = 1, player_units:count() do
						local current_unit = player_units:item(i);
						
						if current_unit:is_commanding_unit() then
							if current_unit:is_routing() or current_unit:is_shattered() then
								core:remove_listener("player_commander_routs_watch");
								self:out("<<< triggering event ScriptEventPlayerGeneralRouts >>>");
								core:trigger_event("ScriptEventPlayerGeneralRouts");
								return true;
							else
								return false;
							end;
						end;
					end;
					return false;
				end,
				500,
				"player_commander_routs_watch"
			);
		end,
		true
	);
	
	-- listener for enemy commmander routing
	core:add_listener(
		"enemy_commander_routs_watch",
		"BattleCommandingUnitRouts",
		true,
		function()
			self:callback(
				function()
					local enemy_units = main_enemy_army:units();
					
					for i = 1, enemy_units:count() do
						local current_unit = enemy_units:item(i);
						
						if current_unit:is_commanding_unit() then
							if current_unit:is_routing() or current_unit:is_shattered() then
								core:remove_listener("enemy_commander_routs_watch");
								self:out("<<< triggering event ScriptEventMainEnemyGeneralRouts >>>");
								core:trigger_event("ScriptEventMainEnemyGeneralRouts");
								return true;
							else
								return false;
							end;
						end;
					end;
					return false;
				end,
				500,
				"enemy_commander_routs_watch"
			);
		end,
		true
	);
	
	
	-- listener for player units routing
	core:add_listener(
		"player_unit_routs_watch",
		"BattleUnitRouts",
		true,
		function()
			self:callback(
				function()
					local player_units = main_player_army:units();
					
					for i = 1, player_units:count() do
						local current_unit = player_units:item(i);
						
						if not current_unit:is_commanding_unit() then
							if current_unit:is_routing() or current_unit:is_shattered() then
								
								-- trigger an event message if we haven't seen this unit routing before
								if not player_units_routing[current_unit] then
									player_units_routing[current_unit] = true;
									self:out("<<< triggering event ScriptEventPlayerUnitRouts >>>");
									core:trigger_event("ScriptEventPlayerUnitRouts");
								end;
							end;
						end;
					end
				end,
				500,
				"engagement_monitor_unit_routs"
			);
		end,
		true
	);

	--
	--
	--
	-- [[ START OF DUEL LISTENERS ]] --

	-- listener for pending duel
	core:add_listener(
		"pending_duel_watch",
		"BattleDuelPending",
		true,
		function()
			self:callback(
				function()
					local player_units = main_player_army:units();
					
					for i = 1, player_units:count() do
						local current_unit = player_units:item(i);
						
						if current_unit:can_duel() then
							if current_unit:is_pending_duelist() then
								
								-- trigger an event message if we haven't seen this unit routing before
								if not player_pending_duelists[current_unit] then
									player_pending_duelists[current_unit] = true;
									self:out("<<< triggering event ScriptEventPendingDuel >>>");
									core:trigger_event("ScriptEventPendingDuel");
								end;
							end;
						end;
					end
				end,
				500,
				"engagement_monitor_pending_duel"
			);
		end,
		true
	);

	-- listener for active duel
	core:add_listener(
		"active_duel_watch",
		"BattleDuelStarted",
		true,
		function()
			self:callback(
				function()
					local player_units = main_player_army:units();
					
					for i = 1, player_units:count() do
						local current_unit = player_units:item(i);
						
						if current_unit:can_duel() then
							if current_unit:is_dueling() then
								
								-- trigger an event message if we haven't seen this unit routing before
								if not player_active_duelists[current_unit] then
									player_active_duelists[current_unit] = true;
									self:out("<<< triggering event ScriptEventActiveDuel >>>");
									core:trigger_event("ScriptEventActiveDuel");
								end;
							end;
						end;
					end
				end,
				500,
				"engagement_monitor_active_duel"
			);
		end,
		true
	);

	-- listener for duel won
	core:add_listener(
		"duel_won_watch",
		"BattleDuelEnded",
		true,
		function()
			self:callback(
				function()
					local player_units = main_player_army:units();
					
					for i = 1, player_units:count() do
						local current_unit = player_units:item(i);
						
						if current_unit:can_duel() then
							if current_unit:has_won_duel() then
								
								-- trigger an event message if we haven't seen this unit routing before
								if not player_duelists_won[current_unit] then
									player_duelists_won[current_unit] = true;
									self:out("<<< triggering event ScriptEventPlayerDuelWon >>>");
									core:trigger_event("ScriptEventPlayerDuelWon");
								end;
							end;
						end;
					end
				end,
				500,
				"engagement_monitor_duel_won"
			);
		end,
		true
	);

	-- listener for duel lost
	core:add_listener(
		"duel_lost_watch",
		"BattleDuelEnded",
		true,
		function()
			self:callback(
				function()
					local player_units = main_player_army:units();
					
					for i = 1, player_units:count() do
						local current_unit = player_units:item(i);
						
						if current_unit:can_duel() then
							if current_unit:has_lost_duel() then
								
								-- trigger an event message if we haven't seen this unit routing before
								if not player_duelists_lost[current_unit] then
									player_duelists_lost[current_unit] = true;
									self:out("<<< triggering event ScriptEventPlayerDuelLost >>>");
									core:trigger_event("ScriptEventPlayerDuelLost");
								end;
							end;
						end;
					end
				end,
				500,
				"engagement_monitor_duel_lost"
			);
		end,
		true
	);
	
	-- [[ END OF DUEL LISTENERS ]] --
	--
	--
	--

	-- listener for charging or being charged
	core:add_listener(
		"unit_being_charged",
		"UnitBeingCharged",
		true,
		function()
			self:callback(
				function()
					core:trigger_event("ScriptEventUnitCharged");
				end,
				500,
				"engagement_monitor_unit_being_charged"
			);
		end,
		true
	);
	
	-- listener for flanking or being flanked
	core:add_listener(
		"unit_being_flanked",
		"UnitBeingFlanked",
		true,
		function()
			self:callback(
				function()
					core:trigger_event("ScriptEventUnitFlanked");
				end,
				500,
				"engagement_monitor_unit_being_flanked"
			);
		end,
		true
	);
	
	
	-- check for routing player units rallying
	self:repeat_callback(
		function()
			for unit in pairs(player_units_routing) do
				if is_unit(unit) and not unit:is_routing() and not unit:is_shattered() then
					player_units_routing[unit] = nil;
					self:out("<<< triggering event ScriptEventPlayerUnitRallies >>>");
					core:trigger_event("ScriptEventPlayerUnitRallies");
				end;
			end;
		end,
		1000,
		"engagement_monitor_rallying_check"
	);
	
	
	-- listener for first enemy unit routing
	core:add_listener(
		"enemy_unit_routs_watch",
		"BattleUnitRouts",
		true,
		function()
			self:callback(
				function()				
					local enemy_armies = enemy_alliance:armies();
					
					for i = 1, enemy_armies:count() do
						local enemy_units = enemy_armies:item(i):units();
					
						for j = 1, enemy_units:count() do
							local current_unit = enemy_units:item(j);
							
							if not current_unit:is_commanding_unit() then
								if current_unit:is_routing() or current_unit:is_shattered() then
									self:out("<<< triggering event ScriptEventEnemyUnitRouts >>>");
									core:trigger_event("ScriptEventEnemyUnitRouts");
									core:remove_listener("enemy_unit_routs_watch");
									return true;
								end;
							end;
						end;
					end;
				end,
				500,
				"engagement_monitor_first_enemy_unit_routs"
			);
		end,
		true
	);
	
	
	
	--
	-- very hacky/fudgy listener for the player getting into the city/close to the victory point. Rewrite all this when we get a better interface.
	--
	local victory_point_approach_event_approach_event_triggered = false;
	
	local attempt_to_trigger_victory_point_approach_event = function()
		if victory_point_approach_event_approach_event_triggered then
			return;
		end;
		
		victory_point_approach_event_approach_event_triggered = true;
		
		core:remove_listener("victory_point_approach_watch");
		
		local countdown_time = 120000;
		
		self:out("<<< starting " .. countdown_time .. "ms countdown to triggering event ScriptEventPlayerApproachingVictoryPoint >>>");
		
		self:callback(
			function()
				self:out("<<< triggering event ScriptEventPlayerApproachingVictoryPoint >>>");
				core:trigger_event("ScriptEventPlayerApproachingVictoryPoint");
			end,
			countdown_time
		);
	end;
	
	core:add_listener(
		"victory_point_approach_watch",
		"BattleAideDeCampEvent",
		function(context) return context.string == "adc_own_ladders_docked" end,
		function()
			self:out("Received BattleAideDeCampEvent, context is adc_own_ladders_docked, calling attempt_to_trigger_victory_point_approach_event()");
			attempt_to_trigger_victory_point_approach_event();
			self:out("attempt_to_trigger_victory_point_approach_event() call completed");
		end,
		false
	);
	
	core:add_listener(
		"victory_point_approach_watch",
		"BattleAideDeCampEvent",
		function(context) return context.string == "adc_own_attacking_gates" end,
		function()
			self:out("Received BattleAideDeCampEvent, context is adc_own_attacking_gates, calling attempt_to_trigger_victory_point_approach_event()");
			attempt_to_trigger_victory_point_approach_event();
			self:out("attempt_to_trigger_victory_point_approach_event() call completed");
		end,
		false
	);
end;


-- No longer required. Calls for this function are being passed through to the underlying code function of the battle interface.
--[[ function battle_manager:is_siege_battle()
	if not self.engagement_monitor_started then
		script_error("ERROR: is_siege_battle() called but engagement monitor has not been started");
		return false;
	end;
	return self.battle_is_siege;
end; ]]

--- @function is_land_ambush
--- @desc Returns a boolean for whether or not the current battle is a land ambush.
--- @r boolean is land ambush battle
function battle_manager:is_land_ambush()
	local battle_type = effect.get_context_value("CcoBattleRoot", "", "BattleTypeState");

	if not battle_type then
		script_error("ERROR: is_land_ambush() called but battle type returned from CcoBattleRoot object is nil - how can this be?");
		return false;
	end

	if battle_type == "land_ambush" then 
		return true;
	end

	return false;
end


--- @function get_distance_between_forces
--- @desc Returns the cached distance between the two alliances. @battle_manager:start_engagement_monitor must have been called before the battle started for this to work.
--- @r number distance
function battle_manager:get_distance_between_forces()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_distance_between_forces() called but engagement monitor has not been started");
		return false;
	end;
	return self.cached_distance_between_forces;
end;


--- @function get_num_units_engaged
--- @desc Returns the number of units in the player's alliance engaged in melee. @battle_manager:start_engagement_monitor must have been called before the battle started for this to work.
--- @r number engaged
function battle_manager:get_num_units_engaged()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_num_units_engaged() called but engagement monitor has not been started");
		return false;
	end;
	return self.cached_num_units_engaged;
end;


--- @function get_proportion_engaged
--- @desc Returns the proportion of units in the player's alliance engaged in melee. This proportion will be a unary value (0 - 1). @battle_manager:start_engagement_monitor must have been called before the battle started for this to work.
--- @r number proportion engaged
function battle_manager:get_proportion_engaged()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_proportion_engaged() called but engagement monitor has not been started");
		return false;
	end;
	return self.cached_proportion_engaged;
end;


--- @function get_num_units_under_fire
--- @desc Returns the number of units in the player's alliance under missile fire. @battle_manager:start_engagement_monitor must have been called before the battle started for this to work.
--- @r number under fire
function battle_manager:get_num_units_under_fire()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_num_units_under_fire() called but engagement monitor has not been started");
		return false;
	end;
	return self.cached_num_units_under_fire;
end;


--- @function get_proportion_under_fire
--- @desc Returns the proportion of units in the player's alliance engaged in melee. This proportion will be a unary value (0 - 1). @battle_manager:start_engagement_monitor must have been called before the battle started for this to work.
--- @r number proportion engaged
function battle_manager:get_proportion_under_fire()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_proportion_under_fire() called but engagement monitor has not been started");
		return false;
	end;
	return self.cached_proportion_under_fire;
end;


--- @function get_player_army_altitude
--- @desc Returns the average altitude of the player's army in m.
--- @r number average altitude
function battle_manager:get_player_army_altitude()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_player_army_altitude() called but engagement monitor has not been started");
		return false;
	end;
	return self.main_player_army_altitude;
end;


--- @function get_enemy_army_altitude
--- @desc Returns the average altitude of the enemy army in m.
--- @r number average altitude
function battle_manager:get_enemy_army_altitude()
	if not self.engagement_monitor_started then
		script_error("ERROR: get_enemy_army_altitude() called but engagement monitor has not been started");
		return false;
	end;
	return self.main_enemy_army_altitude;
end;


--- @function stop_engagement_monitor
--- @desc Stops the engagement monitor.
function battle_manager:stop_engagement_monitor()
	self.engagement_monitor_started = false;
	self:remove_process("battle_manager_engagement_monitor");
end;















----------------------------------------------------------------------------
-- progress on loading screen dismissed
----------------------------------------------------------------------------

function battle_manager:progress_on_loading_screen_dismissed(callback)
	core:progress_on_loading_screen_dismissed(callback);
end;







function battle_manager:enable_cinematic_ui(enable_cinematic_ui, enable_cursor, enable_cinematic_bars)
	local out_str = false;
	
	if enable_cinematic_ui then
		out_str = "enable_cinematic_ui() called, enabling cinematic ui";
		
		if enable_cursor then
			out_str = out_str .. ", enabling the cursor";
		elseif enable_cursor == false then
			out_str = out_str .. ", disabling the cursor";
		else
			out_str = out_str .. ", leaving the cursor state unchanged";
		end;
		
		if enable_cinematic_bars then
			out_str = out_str .. " and enabling the cinematic bars";
		elseif enable_cinematic_bars == false then
			out_str = out_str .. " and disabling the cinematic bars";
		else
			out_str = out_str .. " and leaving the cinematic bar state unchanged";
		end;
	else
		out_str = "enable_cinematic_ui() called, disabling cinematic ui";
	end;
	
	self:out(out_str);
	self.battle:enable_cinematic_ui(enable_cinematic_ui, enable_cursor, enable_cinematic_bars);
end;



