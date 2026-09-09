-- DCS RADIO VOICE CONTROL HOOK BEGIN
-- Appended to the user's own DCS RadioCommandDialogsPanel.lua at installation time.
-- It exports and executes the initial WWII command scope: Wingman, Flight,
-- Second Element, ATC, and mission-generated F10 entries.

do
    -- RadioCommandDialogsPanel switches into a Lua module environment where _G
    -- is not exposed.  The host panel's lexical `base` points at DCS's real
    -- global environment and is also the route used by VAICOM's appended code.
    local drvc_base = base
    drvc_base.package.path = drvc_base.package.path .. ";.\\LuaSocket\\?.lua;"
    drvc_base.package.cpath = drvc_base.package.cpath .. ";.\\LuaSocket\\?.dll;"

    local drvc_socket = drvc_base.require("socket")
    local drvc_json = drvc_base.require("JSON")
    local drvc_gui = drvc_base.require("dxgui")

    local drvc_protocol_version = 1
    local drvc_hook_version = 2
    local drvc_capabilities = {
        "guided_selection",
        "menu_control",
        "staged_transactions",
    }
    local drvc_receive_port = 34383
    local drvc_send_port = 34384
    local drvc_max_datagram = 60000
    local drvc_poll_interval = 0.50
    local drvc_heartbeat_interval = 2.0
    local drvc_max_requests_per_update = 8
    local drvc_transaction_timeout = 1.50

    local drvc_state = {
        revision = 0,
        signature = nil,
        items = {},
        actions = {},
        menus = {},
        last_poll = 0,
        last_heartbeat = 0,
        recent_results = {},
        transaction = nil,
        guided_indexes = nil,
    }

    local function drvc_log(message)
        drvc_base.print("DCS Radio Voice Control: " .. drvc_base.tostring(message))
    end

    local function drvc_now()
        return drvc_socket.gettime()
    end

    local function drvc_send(message)
        message.v = drvc_protocol_version
        local ok, payload = drvc_base.pcall(function()
            return drvc_json:encode(message)
        end)
        if not ok or not payload or #payload > drvc_max_datagram then
            return false
        end
        local sent = drvc_state.sender:send(payload)
        return sent ~= nil
    end

    local function drvc_label(value)
        local label = drvc_base.tostring(value or "")
        if #label > 512 then
            label = drvc_base.string.sub(label, 1, 512)
        end
        return label
    end

    local function drvc_copy_path(path, label)
        local result = {}
        for index = 1, #path do
            result[index] = path[index]
        end
        result[#result + 1] = label
        return result
    end

    local function drvc_condition_allows(item)
        if drvc_base.type(item.condition) ~= "table" or
           drvc_base.type(item.condition.check) ~= "function" then
            return true
        end
        local ok, allowed = drvc_base.pcall(item.condition.check, item.condition)
        return ok and allowed ~= false
    end

    local function drvc_submenu(item)
        if drvc_base.type(item.submenu) == "table" then
            return item.submenu
        end
        if drvc_base.type(item.getSubmenu) == "function" then
            local ok, submenu = drvc_base.pcall(item.getSubmenu, item)
            if ok and drvc_base.type(submenu) == "table" then
                return submenu
            end
        end
        return nil
    end

    local function drvc_numeric_keys(items)
        local keys = {}
        for key, _ in drvc_base.pairs(items) do
            if drvc_base.type(key) == "number" then
                keys[#keys + 1] = key
            end
        end
        drvc_base.table.sort(keys)
        return keys
    end

    local function drvc_copy_indexes(indexes, index)
        local result = {}
        for position = 1, #indexes do
            result[position] = indexes[position]
        end
        result[#result + 1] = index
        return result
    end

    local function drvc_record_menu(path, indexes, items, menus, signature_parts)
        local menu_id = "menu." .. drvc_base.table.concat(indexes, ".")
        menus[menu_id] = {indexes = indexes}
        items[#items + 1] = {
            action_id = menu_id,
            label = path[#path],
            path = path,
            executable = false,
        }
        signature_parts[#signature_parts + 1] =
            menu_id .. "\30" .. drvc_base.table.concat(path, "\31") .. "\30false"
    end

    local function drvc_walk_menu(menu, path, indexes, scope, items, actions, menus, signature_parts)
        if not menu or drvc_base.type(menu.items) ~= "table" then
            return
        end
        for _, index in drvc_base.ipairs(drvc_numeric_keys(menu.items)) do
            local item = menu.items[index]
            if drvc_base.type(item) == "table" and drvc_condition_allows(item) then
                local label = drvc_label(item.name)
                local item_path = drvc_copy_path(path, label)
                local item_indexes = drvc_copy_indexes(indexes, index)
                local submenu = drvc_submenu(item)
                if submenu then
                    drvc_record_menu(item_path, item_indexes, items, menus, signature_parts)
                    drvc_walk_menu(
                        submenu,
                        item_path,
                        item_indexes,
                        scope,
                        items,
                        actions,
                        menus,
                        signature_parts
                    )
                elseif drvc_base.type(item.command) == "table" then
                    local executable = true
                    local action_id
                    if scope == "f10" and item.command.actionIndex ~= nil then
                        action_id = "f10." .. drvc_base.table.concat(item_indexes, ".")
                        actions[action_id] = {
                            kind = "f10",
                            action_index = item.command.actionIndex,
                            indexes = item_indexes,
                        }
                    else
                        action_id = "radio." .. drvc_base.table.concat(item_indexes, ".")
                        actions[action_id] = {
                            kind = "radio",
                            indexes = item_indexes,
                        }
                    end
                    items[#items + 1] = {
                        action_id = action_id,
                        label = label,
                        path = item_path,
                        executable = executable,
                    }
                    signature_parts[#signature_parts + 1] =
                        action_id .. "\30" ..
                        drvc_base.table.concat(item_path, "\31") .. "\30" ..
                        drvc_base.tostring(executable)
                end
            end
        end
    end

    local function drvc_capture_menu(force_send)
        local items = {}
        local actions = {}
        local menus = {
            ["menu.root"] = {indexes = {}},
        }
        local signature_parts = {}
        if data and data.initialized and data.rootItem then
            local root = drvc_submenu(data.rootItem)
            if root and drvc_base.type(root.items) == "table" then
                local included_slots = {1, 2, 3, 5, 8, 10}
                for _, slot in drvc_base.ipairs(included_slots) do
                    local item = root.items[slot]
                    if drvc_base.type(item) == "table" and drvc_condition_allows(item) then
                        local label = drvc_label(item.name)
                        local submenu = drvc_submenu(item)
                        if submenu then
                            drvc_record_menu({label}, {slot}, items, menus, signature_parts)
                            drvc_walk_menu(
                                submenu,
                                {label},
                                {slot},
                                slot == 10 and "f10" or "radio",
                                items,
                                actions,
                                menus,
                                signature_parts
                            )
                        end
                    end
                end
            end
        end

        local signature = drvc_base.table.concat(signature_parts, "\29")
        if signature ~= drvc_state.signature then
            drvc_state.revision = drvc_state.revision + 1
            drvc_state.signature = signature
            drvc_state.items = items
            drvc_state.actions = actions
            drvc_state.menus = menus
            force_send = true
        end

        if force_send then
            if not drvc_send({
                type = "menu_snapshot",
                revision = drvc_state.revision,
                items = drvc_state.items,
                hook_version = drvc_hook_version,
                capabilities = drvc_capabilities,
            }) then
                drvc_send({
                    type = "status",
                    state = "error",
                    code = "menu_too_large_or_send_failed",
                })
            end
        end
    end

    local function drvc_result(request_id, accepted, code, detail)
        local result = {
            type = "result",
            request_id = request_id,
            accepted = accepted,
            code = code,
            detail = detail or "",
        }
        if request_id then
            drvc_state.recent_results[request_id] = {message = result, created = drvc_now()}
        end
        drvc_send(result)
    end

    local function drvc_copy_index_path(indexes)
        local result = {}
        for position = 1, #indexes do
            result[position] = indexes[position]
        end
        return result
    end

    local function drvc_begin_transaction(
        request_id,
        revision,
        indexes,
        show_after,
        accepted_code,
        accepted_detail,
        guided_indexes
    )
        if drvc_base.type(indexes) ~= "table" then
            drvc_result(request_id, false, "invalid_path", "Invalid DCS Radio Voice Control menu path")
            return false
        end
        if drvc_state.transaction ~= nil then
            drvc_result(request_id, false, "busy", "Another DCS menu transaction is active")
            return false
        end
        drvc_state.transaction = {
            request_id = request_id,
            revision = revision,
            indexes = drvc_copy_index_path(indexes),
            position = 1,
            stage = "close",
            show_after = show_after,
            accepted_code = accepted_code,
            accepted_detail = accepted_detail,
            guided_indexes = guided_indexes,
            started = drvc_now(),
        }
        return true
    end

    local function drvc_complete_transaction(transaction)
        drvc_state.guided_indexes = transaction.guided_indexes and
            drvc_copy_index_path(transaction.guided_indexes) or nil
        drvc_state.transaction = nil
        drvc_result(
            transaction.request_id,
            true,
            transaction.accepted_code,
            transaction.accepted_detail
        )
        drvc_capture_menu(false)
    end

    local function drvc_fail_transaction(transaction, code, detail)
        setShowMenu(false)
        drvc_state.guided_indexes = nil
        drvc_state.transaction = nil
        drvc_result(transaction.request_id, false, code, detail)
        drvc_capture_menu(false)
    end

    local function drvc_advance_transaction(now)
        local transaction = drvc_state.transaction
        if transaction == nil then
            return
        end
        if now - transaction.started > drvc_transaction_timeout then
            drvc_fail_transaction(
                transaction,
                "transaction_timeout",
                "DCS menu traversal did not complete in time"
            )
            return
        end
        if transaction.revision ~= drvc_state.revision then
            drvc_fail_transaction(
                transaction,
                "stale_revision",
                "The live radio menu changed during traversal"
            )
            drvc_capture_menu(true)
            return
        end

        local advanced, error_message = drvc_base.pcall(function()
            if transaction.stage == "close" then
                -- Hiding the panel and yielding an update prevents an existing
                -- submenu from becoming the origin of an absolute F-key path.
                setShowMenu(false)
                transaction.stage = "reset"
                return
            end
            if transaction.stage == "reset" then
                commandDialogsPanel.switchToMainMenu(self)
                transaction.stage = "select"
                return
            end
            if transaction.stage == "select" then
                local index = transaction.indexes[transaction.position]
                if index ~= nil then
                    -- Advance only one item per DCS update so each submenu has
                    -- become current before the next F-key is interpreted.
                    commandDialogsPanel.selectMenuItem(self, index)
                    transaction.position = transaction.position + 1
                    return
                end
                transaction.stage = "finish"
                return
            end
            if transaction.stage == "finish" then
                if transaction.show_after then
                    setShowMenu(true)
                end
                drvc_complete_transaction(transaction)
                return
            end
            drvc_base.error("invalid DCS Radio Voice Control transaction stage")
        end)
        if not advanced and drvc_state.transaction ~= nil then
            drvc_fail_transaction(transaction, "dcs_error", drvc_base.tostring(error_message))
        end
    end

    local function drvc_control_menu(operation)
        if operation == "previous" then
            -- F11 is DCS's own Previous Menu item in the currently displayed tree.
            commandDialogsPanel.selectMenuItem(self, 11)
            setShowMenu(true)
            if drvc_state.guided_indexes ~= nil and #drvc_state.guided_indexes > 0 then
                drvc_base.table.remove(drvc_state.guided_indexes)
            end
            return
        end
        if operation == "exit" then
            -- F12 closes the radio menu without selecting an executable action.
            setShowMenu(false)
            drvc_state.guided_indexes = nil
            return
        end
        drvc_base.error("invalid DCS Radio Voice Control menu control")
    end

    local function drvc_same_indexes(left, right)
        if drvc_base.type(left) ~= "table" or drvc_base.type(right) ~= "table" or
           #left ~= #right then
            return false
        end
        for position = 1, #left do
            if left[position] ~= right[position] then
                return false
            end
        end
        return true
    end

    local function drvc_select_visible(request_id, item_id)
        if drvc_state.transaction ~= nil then
            drvc_result(request_id, false, "busy", "Another DCS menu transaction is active")
            return
        end
        if drvc_state.guided_indexes == nil then
            drvc_result(request_id, false, "guided_menu_not_active", "No guided menu is active")
            return
        end

        local target = drvc_state.menus[item_id]
        local executable = false
        if target == nil then
            target = drvc_state.actions[item_id]
            executable = true
        end
        if target == nil or drvc_base.type(target.indexes) ~= "table" or #target.indexes < 1 then
            drvc_result(request_id, false, "unknown_visible_item", "Item is not in the current catalogue")
            return
        end

        local parent_indexes = drvc_copy_index_path(target.indexes)
        local index = drvc_base.table.remove(parent_indexes)
        if not drvc_same_indexes(parent_indexes, drvc_state.guided_indexes) then
            drvc_result(request_id, false, "not_visible", "Item is not on the displayed menu")
            return
        end

        local selected, error_message = drvc_base.pcall(function()
            commandDialogsPanel.selectMenuItem(self, index)
            if executable then
                drvc_state.guided_indexes = nil
            else
                drvc_state.guided_indexes = drvc_copy_index_path(target.indexes)
                setShowMenu(true)
            end
        end)
        if not selected then
            drvc_result(request_id, false, "dcs_error", drvc_base.tostring(error_message))
            return
        end
        drvc_result(
            request_id,
            true,
            executable and "accepted" or "menu_opened",
            executable and "DCS selected the displayed command" or
                "DCS selected the displayed submenu"
        )
        drvc_capture_menu(false)
    end

    local function drvc_process(raw)
        if not raw or #raw > drvc_max_datagram then
            return
        end
        local ok, message = drvc_base.pcall(function()
            return drvc_json:decode(raw)
        end)
        if not ok or drvc_base.type(message) ~= "table" then
            return
        end
        local request_id = message.request_id
        if drvc_base.type(request_id) ~= "string" or #request_id < 1 or #request_id > 128 then
            return
        end

        local cached = drvc_state.recent_results[request_id]
        if cached then
            drvc_send(cached.message)
            return
        end
        if drvc_state.transaction ~= nil and
           drvc_state.transaction.request_id == request_id then
            -- The Python client retries UDP with the same request ID.  The
            -- in-flight traversal already owns it and will send one final result.
            return
        end
        if message.v ~= drvc_protocol_version then
            drvc_result(request_id, false, "unsupported_version", "Expected protocol version 1")
            return
        end
        if message.type == "get_menu" then
            drvc_capture_menu(true)
            return
        end
        if message.type ~= "execute" and
           message.type ~= "open_menu" and
           message.type ~= "select_visible" and
           message.type ~= "menu_control" then
            drvc_result(request_id, false, "unknown_message", "Unsupported request type")
            return
        end
        -- Close the polling race: rebuild the catalogue immediately before
        -- validating the revision and action identifier.
        drvc_capture_menu(false)
        if message.revision ~= drvc_state.revision then
            drvc_result(request_id, false, "stale_revision", "The live radio menu has changed")
            drvc_capture_menu(true)
            return
        end
        if message.type == "menu_control" then
            if message.operation ~= "previous" and message.operation ~= "exit" then
                drvc_result(request_id, false, "unknown_menu_control", "Unsupported menu control")
                return
            end
            if drvc_state.transaction ~= nil then
                drvc_result(request_id, false, "busy", "Another DCS menu transaction is active")
                return
            end
            local executed, error_message = drvc_base.pcall(function()
                drvc_control_menu(message.operation)
            end)
            if not executed then
                drvc_result(request_id, false, "dcs_error", drvc_base.tostring(error_message))
                return
            end
            local accepted_code = message.operation == "previous" and
                "previous_menu" or "menu_closed"
            local accepted_detail = message.operation == "previous" and
                "DCS selected F11 Previous Menu" or "DCS closed the radio menu"
            drvc_result(request_id, true, accepted_code, accepted_detail)
            drvc_capture_menu(false)
            return
        end
        if message.type == "select_visible" then
            if drvc_base.type(message.item_id) ~= "string" then
                drvc_result(request_id, false, "invalid_visible_item", "Missing visible item ID")
                return
            end
            drvc_select_visible(request_id, message.item_id)
            return
        end
        if message.type == "open_menu" then
            local menu = drvc_state.menus[message.menu_id]
            if menu == nil then
                drvc_result(request_id, false, "unknown_menu", "Menu is not in the current catalogue")
                return
            end
            drvc_begin_transaction(
                request_id,
                message.revision,
                menu.indexes,
                true,
                "menu_opened",
                "DCS completed the current radio submenu traversal",
                menu.indexes
            )
            return
        end

        local action = drvc_state.actions[message.action_id]
        if action == nil then
            drvc_result(request_id, false, "unknown_action", "Action is not in the current menu")
            return
        end
        if action.kind == "f10" then
            if drvc_state.transaction ~= nil then
                drvc_result(request_id, false, "busy", "Another DCS menu transaction is active")
                return
            end
            local executed, error_message = drvc_base.pcall(function()
                setShowMenu(false)
                drvc_state.guided_indexes = nil
                drvc_base.missionCommands.doAction(action.action_index)
            end)
            if not executed then
                drvc_result(request_id, false, "dcs_error", drvc_base.tostring(error_message))
                return
            end
            drvc_result(
                request_id,
                true,
                "accepted",
                "DCS accepted the current mission action; downstream effects are not observable"
            )
            drvc_capture_menu(false)
            return
        end
        if action.kind ~= "radio" then
            drvc_result(request_id, false, "invalid_action", "Invalid DCS Radio Voice Control action")
            return
        end
        -- Standard radio actions deliberately traverse DCS's own menus so
        -- recipient, radio tuning, and inherited parameters retain stock behaviour.
        drvc_begin_transaction(
            request_id,
            message.revision,
            action.indexes,
            false,
            "accepted",
            "DCS completed the current radio action traversal; downstream effects are not observable",
            nil
        )
    end

    local function drvc_prune_results(now)
        for request_id, cached in drvc_base.pairs(drvc_state.recent_results) do
            if now - cached.created > 30 then
                drvc_state.recent_results[request_id] = nil
            end
        end
    end

    local function drvc_update()
        local now = drvc_now()
        for _ = 1, drvc_max_requests_per_update do
            local raw = drvc_state.receiver:receive()
            if not raw then
                break
            end
            drvc_process(raw)
        end
        drvc_advance_transaction(now)
        if now - drvc_state.last_poll >= drvc_poll_interval then
            drvc_state.last_poll = now
            drvc_capture_menu(false)
            drvc_prune_results(now)
        end
        if now - drvc_state.last_heartbeat >= drvc_heartbeat_interval then
            drvc_state.last_heartbeat = now
            drvc_send({
                type = "status",
                state = data and data.initialized and "mission_active" or "waiting_for_mission",
                revision = drvc_state.revision,
                hook_version = drvc_hook_version,
                capabilities = drvc_capabilities,
            })
        end
    end

    -- VAICOM replaces initialize() and calls SetupApplicationUpdateCallback() from
    -- inside it. That reset removes callbacks registered while this file is first
    -- loaded. Wrap the final implementation and add DCS Radio Voice Control only after VAICOM (or
    -- the stock DCS implementation) has completed radio initialization.
    local drvc_previous_initialize = initialize
    function initialize(...)
        drvc_previous_initialize(...)
        drvc_gui.AddUpdateCallback(drvc_update)
        drvc_log("radio callback registered after mission initialization")
        drvc_capture_menu(true)
    end

    drvc_state.sender = drvc_socket.udp()
    drvc_state.sender:setpeername("127.0.0.1", drvc_send_port)
    drvc_state.sender:settimeout(0)
    drvc_state.receiver = drvc_socket.udp()
    drvc_state.receiver:setsockname("127.0.0.1", drvc_receive_port)
    drvc_state.receiver:settimeout(0)

    drvc_gui.SetupApplicationUpdateCallback()
    drvc_log("radio hook loaded; waiting for mission initialization")
end
-- DCS RADIO VOICE CONTROL HOOK END
