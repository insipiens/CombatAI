-- COMBATAI RADIO HOOK BEGIN
-- Appended to the user's own DCS RadioCommandDialogsPanel.lua at installation time.
-- It deliberately exports only the live F10 menu and accepts only validated menu actions.

do
    -- RadioCommandDialogsPanel switches into a Lua module environment where _G
    -- is not exposed.  The host panel's lexical `base` points at DCS's real
    -- global environment and is also the route used by VAICOM's appended code.
    local cai_base = base
    cai_base.package.path = cai_base.package.path .. ";.\\LuaSocket\\?.lua;"
    cai_base.package.cpath = cai_base.package.cpath .. ";.\\LuaSocket\\?.dll;"

    local cai_socket = cai_base.require("socket")
    local cai_json = cai_base.require("JSON")
    local cai_gui = cai_base.require("dxgui")

    local cai_protocol_version = 1
    local cai_receive_port = 34383
    local cai_send_port = 34384
    local cai_max_datagram = 60000
    local cai_poll_interval = 0.50
    local cai_heartbeat_interval = 2.0
    local cai_max_requests_per_update = 8

    local cai_state = {
        revision = 0,
        signature = nil,
        items = {},
        actions = {},
        last_poll = 0,
        last_heartbeat = 0,
        recent_results = {},
    }

    local function cai_log(message)
        cai_base.print("CombatAI: " .. cai_base.tostring(message))
    end

    local function cai_now()
        return cai_socket.gettime()
    end

    local function cai_send(message)
        message.v = cai_protocol_version
        local ok, payload = cai_base.pcall(function()
            return cai_json:encode(message)
        end)
        if not ok or not payload or #payload > cai_max_datagram then
            return false
        end
        local sent = cai_state.sender:send(payload)
        return sent ~= nil
    end

    local function cai_label(value)
        local label = cai_base.tostring(value or "")
        if #label > 512 then
            label = cai_base.string.sub(label, 1, 512)
        end
        return label
    end

    local function cai_copy_path(path, label)
        local result = {}
        for index = 1, #path do
            result[index] = path[index]
        end
        result[#result + 1] = label
        return result
    end

    local function cai_walk_menu(menu, path, items, actions, signature_parts)
        if not menu or cai_base.type(menu.items) ~= "table" then
            return
        end
        for index = 1, #menu.items do
            local item = menu.items[index]
            if cai_base.type(item) == "table" then
                local label = cai_label(item.name)
                local item_path = cai_copy_path(path, label)
                if cai_base.type(item.submenu) == "table" then
                    cai_walk_menu(item.submenu, item_path, items, actions, signature_parts)
                elseif cai_base.type(item.command) == "table" and item.command.actionIndex ~= nil then
                    local action_id = "f10." .. cai_base.tostring(#items + 1)
                    items[#items + 1] = {
                        action_id = action_id,
                        label = label,
                        path = item_path,
                    }
                    actions[action_id] = item.command.actionIndex
                    signature_parts[#signature_parts + 1] =
                        cai_base.table.concat(item_path, "\31") .. "\30" .. cai_base.tostring(item.command.actionIndex)
                end
            end
        end
    end

    local function cai_capture_menu(force_send)
        local items = {}
        local actions = {}
        local signature_parts = {}
        if data and data.initialized and data.menuOther then
            local root = data.menuOther.submenu or data.menuOther
            cai_walk_menu(root, {}, items, actions, signature_parts)
        end

        local signature = cai_base.table.concat(signature_parts, "\29")
        if signature ~= cai_state.signature then
            cai_state.revision = cai_state.revision + 1
            cai_state.signature = signature
            cai_state.items = items
            cai_state.actions = actions
            force_send = true
        end

        if force_send then
            if not cai_send({
                type = "menu_snapshot",
                revision = cai_state.revision,
                items = cai_state.items,
            }) then
                cai_send({
                    type = "status",
                    state = "error",
                    code = "menu_too_large_or_send_failed",
                })
            end
        end
    end

    local function cai_result(request_id, accepted, code, detail)
        local result = {
            type = "result",
            request_id = request_id,
            accepted = accepted,
            code = code,
            detail = detail or "",
        }
        if request_id then
            cai_state.recent_results[request_id] = {message = result, created = cai_now()}
        end
        cai_send(result)
    end

    local function cai_process(raw)
        if not raw or #raw > cai_max_datagram then
            return
        end
        local ok, message = cai_base.pcall(function()
            return cai_json:decode(raw)
        end)
        if not ok or cai_base.type(message) ~= "table" then
            return
        end
        local request_id = message.request_id
        if cai_base.type(request_id) ~= "string" or #request_id < 1 or #request_id > 128 then
            return
        end

        local cached = cai_state.recent_results[request_id]
        if cached then
            cai_send(cached.message)
            return
        end
        if message.v ~= cai_protocol_version then
            cai_result(request_id, false, "unsupported_version", "Expected protocol version 1")
            return
        end
        if message.type == "get_menu" then
            cai_capture_menu(true)
            return
        end
        if message.type ~= "execute" then
            cai_result(request_id, false, "unknown_message", "Unsupported request type")
            return
        end
        if message.revision ~= cai_state.revision then
            cai_result(request_id, false, "stale_revision", "The live F10 menu has changed")
            cai_capture_menu(true)
            return
        end
        local action = cai_state.actions[message.action_id]
        if action == nil then
            cai_result(request_id, false, "unknown_action", "Action is not in the current F10 menu")
            return
        end

        local executed, error_message = cai_base.pcall(function()
            cai_base.missionCommands.doAction(action)
        end)
        if executed then
            cai_result(
                request_id,
                true,
                "accepted",
                "DCS accepted the current menu action; downstream mission effects are not observable"
            )
            cai_capture_menu(false)
        else
            cai_result(request_id, false, "dcs_error", cai_base.tostring(error_message))
        end
    end

    local function cai_prune_results(now)
        for request_id, cached in cai_base.pairs(cai_state.recent_results) do
            if now - cached.created > 30 then
                cai_state.recent_results[request_id] = nil
            end
        end
    end

    local function cai_update()
        local now = cai_now()
        for _ = 1, cai_max_requests_per_update do
            local raw = cai_state.receiver:receive()
            if not raw then
                break
            end
            cai_process(raw)
        end
        if now - cai_state.last_poll >= cai_poll_interval then
            cai_state.last_poll = now
            cai_capture_menu(false)
            cai_prune_results(now)
        end
        if now - cai_state.last_heartbeat >= cai_heartbeat_interval then
            cai_state.last_heartbeat = now
            cai_send({
                type = "status",
                state = data and data.initialized and "mission_active" or "waiting_for_mission",
                revision = cai_state.revision,
            })
        end
    end

    -- VAICOM replaces initialize() and calls SetupApplicationUpdateCallback() from
    -- inside it. That reset removes callbacks registered while this file is first
    -- loaded. Wrap the final implementation and add CombatAI only after VAICOM (or
    -- the stock DCS implementation) has completed radio initialization.
    local cai_previous_initialize = initialize
    function initialize(...)
        cai_previous_initialize(...)
        cai_gui.AddUpdateCallback(cai_update)
        cai_log("radio callback registered after mission initialization")
        cai_capture_menu(true)
    end

    cai_state.sender = cai_socket.udp()
    cai_state.sender:setpeername("127.0.0.1", cai_send_port)
    cai_state.sender:settimeout(0)
    cai_state.receiver = cai_socket.udp()
    cai_state.receiver:setsockname("127.0.0.1", cai_receive_port)
    cai_state.receiver:settimeout(0)

    cai_gui.SetupApplicationUpdateCallback()
    cai_log("radio hook loaded; waiting for mission initialization")
end
-- COMBATAI RADIO HOOK END
