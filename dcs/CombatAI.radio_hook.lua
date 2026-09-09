-- COMBATAI RADIO HOOK BEGIN
-- Appended to the user's own DCS RadioCommandDialogsPanel.lua at installation time.
-- It exports and executes the initial WWII command scope: Wingman, Flight,
-- Second Element, ATC, and mission-generated F10 entries.

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
    local cai_hook_version = 2
    local cai_capabilities = {
        "guided_selection",
        "menu_control",
        "staged_transactions",
    }
    local cai_receive_port = 34383
    local cai_send_port = 34384
    local cai_max_datagram = 60000
    local cai_poll_interval = 0.50
    local cai_heartbeat_interval = 2.0
    local cai_max_requests_per_update = 8
    local cai_transaction_timeout = 1.50

    local cai_state = {
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

    local function cai_condition_allows(item)
        if cai_base.type(item.condition) ~= "table" or
           cai_base.type(item.condition.check) ~= "function" then
            return true
        end
        local ok, allowed = cai_base.pcall(item.condition.check, item.condition)
        return ok and allowed ~= false
    end

    local function cai_submenu(item)
        if cai_base.type(item.submenu) == "table" then
            return item.submenu
        end
        if cai_base.type(item.getSubmenu) == "function" then
            local ok, submenu = cai_base.pcall(item.getSubmenu, item)
            if ok and cai_base.type(submenu) == "table" then
                return submenu
            end
        end
        return nil
    end

    local function cai_numeric_keys(items)
        local keys = {}
        for key, _ in cai_base.pairs(items) do
            if cai_base.type(key) == "number" then
                keys[#keys + 1] = key
            end
        end
        cai_base.table.sort(keys)
        return keys
    end

    local function cai_copy_indexes(indexes, index)
        local result = {}
        for position = 1, #indexes do
            result[position] = indexes[position]
        end
        result[#result + 1] = index
        return result
    end

    local function cai_record_menu(path, indexes, items, menus, signature_parts)
        local menu_id = "menu." .. cai_base.table.concat(indexes, ".")
        menus[menu_id] = {indexes = indexes}
        items[#items + 1] = {
            action_id = menu_id,
            label = path[#path],
            path = path,
            executable = false,
        }
        signature_parts[#signature_parts + 1] =
            menu_id .. "\30" .. cai_base.table.concat(path, "\31") .. "\30false"
    end

    local function cai_walk_menu(menu, path, indexes, scope, items, actions, menus, signature_parts)
        if not menu or cai_base.type(menu.items) ~= "table" then
            return
        end
        for _, index in cai_base.ipairs(cai_numeric_keys(menu.items)) do
            local item = menu.items[index]
            if cai_base.type(item) == "table" and cai_condition_allows(item) then
                local label = cai_label(item.name)
                local item_path = cai_copy_path(path, label)
                local item_indexes = cai_copy_indexes(indexes, index)
                local submenu = cai_submenu(item)
                if submenu then
                    cai_record_menu(item_path, item_indexes, items, menus, signature_parts)
                    cai_walk_menu(
                        submenu,
                        item_path,
                        item_indexes,
                        scope,
                        items,
                        actions,
                        menus,
                        signature_parts
                    )
                elseif cai_base.type(item.command) == "table" then
                    local executable = true
                    local action_id
                    if scope == "f10" and item.command.actionIndex ~= nil then
                        action_id = "f10." .. cai_base.table.concat(item_indexes, ".")
                        actions[action_id] = {
                            kind = "f10",
                            action_index = item.command.actionIndex,
                            indexes = item_indexes,
                        }
                    else
                        action_id = "radio." .. cai_base.table.concat(item_indexes, ".")
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
                        cai_base.table.concat(item_path, "\31") .. "\30" ..
                        cai_base.tostring(executable)
                end
            end
        end
    end

    local function cai_capture_menu(force_send)
        local items = {}
        local actions = {}
        local menus = {
            ["menu.root"] = {indexes = {}},
        }
        local signature_parts = {}
        if data and data.initialized and data.rootItem then
            local root = cai_submenu(data.rootItem)
            if root and cai_base.type(root.items) == "table" then
                local included_slots = {1, 2, 3, 5, 8, 10}
                for _, slot in cai_base.ipairs(included_slots) do
                    local item = root.items[slot]
                    if cai_base.type(item) == "table" and cai_condition_allows(item) then
                        local label = cai_label(item.name)
                        local submenu = cai_submenu(item)
                        if submenu then
                            cai_record_menu({label}, {slot}, items, menus, signature_parts)
                            cai_walk_menu(
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

        local signature = cai_base.table.concat(signature_parts, "\29")
        if signature ~= cai_state.signature then
            cai_state.revision = cai_state.revision + 1
            cai_state.signature = signature
            cai_state.items = items
            cai_state.actions = actions
            cai_state.menus = menus
            force_send = true
        end

        if force_send then
            if not cai_send({
                type = "menu_snapshot",
                revision = cai_state.revision,
                items = cai_state.items,
                hook_version = cai_hook_version,
                capabilities = cai_capabilities,
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

    local function cai_copy_index_path(indexes)
        local result = {}
        for position = 1, #indexes do
            result[position] = indexes[position]
        end
        return result
    end

    local function cai_begin_transaction(
        request_id,
        revision,
        indexes,
        show_after,
        accepted_code,
        accepted_detail,
        guided_indexes
    )
        if cai_base.type(indexes) ~= "table" then
            cai_result(request_id, false, "invalid_path", "Invalid CombatAI menu path")
            return false
        end
        if cai_state.transaction ~= nil then
            cai_result(request_id, false, "busy", "Another DCS menu transaction is active")
            return false
        end
        cai_state.transaction = {
            request_id = request_id,
            revision = revision,
            indexes = cai_copy_index_path(indexes),
            position = 1,
            stage = "close",
            show_after = show_after,
            accepted_code = accepted_code,
            accepted_detail = accepted_detail,
            guided_indexes = guided_indexes,
            started = cai_now(),
        }
        return true
    end

    local function cai_complete_transaction(transaction)
        cai_state.guided_indexes = transaction.guided_indexes and
            cai_copy_index_path(transaction.guided_indexes) or nil
        cai_state.transaction = nil
        cai_result(
            transaction.request_id,
            true,
            transaction.accepted_code,
            transaction.accepted_detail
        )
        cai_capture_menu(false)
    end

    local function cai_fail_transaction(transaction, code, detail)
        setShowMenu(false)
        cai_state.guided_indexes = nil
        cai_state.transaction = nil
        cai_result(transaction.request_id, false, code, detail)
        cai_capture_menu(false)
    end

    local function cai_advance_transaction(now)
        local transaction = cai_state.transaction
        if transaction == nil then
            return
        end
        if now - transaction.started > cai_transaction_timeout then
            cai_fail_transaction(
                transaction,
                "transaction_timeout",
                "DCS menu traversal did not complete in time"
            )
            return
        end
        if transaction.revision ~= cai_state.revision then
            cai_fail_transaction(
                transaction,
                "stale_revision",
                "The live radio menu changed during traversal"
            )
            cai_capture_menu(true)
            return
        end

        local advanced, error_message = cai_base.pcall(function()
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
                cai_complete_transaction(transaction)
                return
            end
            cai_base.error("invalid CombatAI transaction stage")
        end)
        if not advanced and cai_state.transaction ~= nil then
            cai_fail_transaction(transaction, "dcs_error", cai_base.tostring(error_message))
        end
    end

    local function cai_control_menu(operation)
        if operation == "previous" then
            -- F11 is DCS's own Previous Menu item in the currently displayed tree.
            commandDialogsPanel.selectMenuItem(self, 11)
            setShowMenu(true)
            if cai_state.guided_indexes ~= nil and #cai_state.guided_indexes > 0 then
                cai_base.table.remove(cai_state.guided_indexes)
            end
            return
        end
        if operation == "exit" then
            -- F12 closes the radio menu without selecting an executable action.
            setShowMenu(false)
            cai_state.guided_indexes = nil
            return
        end
        cai_base.error("invalid CombatAI menu control")
    end

    local function cai_same_indexes(left, right)
        if cai_base.type(left) ~= "table" or cai_base.type(right) ~= "table" or
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

    local function cai_select_visible(request_id, item_id)
        if cai_state.transaction ~= nil then
            cai_result(request_id, false, "busy", "Another DCS menu transaction is active")
            return
        end
        if cai_state.guided_indexes == nil then
            cai_result(request_id, false, "guided_menu_not_active", "No guided menu is active")
            return
        end

        local target = cai_state.menus[item_id]
        local executable = false
        if target == nil then
            target = cai_state.actions[item_id]
            executable = true
        end
        if target == nil or cai_base.type(target.indexes) ~= "table" or #target.indexes < 1 then
            cai_result(request_id, false, "unknown_visible_item", "Item is not in the current catalogue")
            return
        end

        local parent_indexes = cai_copy_index_path(target.indexes)
        local index = cai_base.table.remove(parent_indexes)
        if not cai_same_indexes(parent_indexes, cai_state.guided_indexes) then
            cai_result(request_id, false, "not_visible", "Item is not on the displayed menu")
            return
        end

        local selected, error_message = cai_base.pcall(function()
            commandDialogsPanel.selectMenuItem(self, index)
            if executable then
                cai_state.guided_indexes = nil
            else
                cai_state.guided_indexes = cai_copy_index_path(target.indexes)
                setShowMenu(true)
            end
        end)
        if not selected then
            cai_result(request_id, false, "dcs_error", cai_base.tostring(error_message))
            return
        end
        cai_result(
            request_id,
            true,
            executable and "accepted" or "menu_opened",
            executable and "DCS selected the displayed command" or
                "DCS selected the displayed submenu"
        )
        cai_capture_menu(false)
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
        if cai_state.transaction ~= nil and
           cai_state.transaction.request_id == request_id then
            -- The Python client retries UDP with the same request ID.  The
            -- in-flight traversal already owns it and will send one final result.
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
        if message.type ~= "execute" and
           message.type ~= "open_menu" and
           message.type ~= "select_visible" and
           message.type ~= "menu_control" then
            cai_result(request_id, false, "unknown_message", "Unsupported request type")
            return
        end
        -- Close the polling race: rebuild the catalogue immediately before
        -- validating the revision and action identifier.
        cai_capture_menu(false)
        if message.revision ~= cai_state.revision then
            cai_result(request_id, false, "stale_revision", "The live radio menu has changed")
            cai_capture_menu(true)
            return
        end
        if message.type == "menu_control" then
            if message.operation ~= "previous" and message.operation ~= "exit" then
                cai_result(request_id, false, "unknown_menu_control", "Unsupported menu control")
                return
            end
            if cai_state.transaction ~= nil then
                cai_result(request_id, false, "busy", "Another DCS menu transaction is active")
                return
            end
            local executed, error_message = cai_base.pcall(function()
                cai_control_menu(message.operation)
            end)
            if not executed then
                cai_result(request_id, false, "dcs_error", cai_base.tostring(error_message))
                return
            end
            local accepted_code = message.operation == "previous" and
                "previous_menu" or "menu_closed"
            local accepted_detail = message.operation == "previous" and
                "DCS selected F11 Previous Menu" or "DCS closed the radio menu"
            cai_result(request_id, true, accepted_code, accepted_detail)
            cai_capture_menu(false)
            return
        end
        if message.type == "select_visible" then
            if cai_base.type(message.item_id) ~= "string" then
                cai_result(request_id, false, "invalid_visible_item", "Missing visible item ID")
                return
            end
            cai_select_visible(request_id, message.item_id)
            return
        end
        if message.type == "open_menu" then
            local menu = cai_state.menus[message.menu_id]
            if menu == nil then
                cai_result(request_id, false, "unknown_menu", "Menu is not in the current catalogue")
                return
            end
            cai_begin_transaction(
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

        local action = cai_state.actions[message.action_id]
        if action == nil then
            cai_result(request_id, false, "unknown_action", "Action is not in the current menu")
            return
        end
        if action.kind == "f10" then
            if cai_state.transaction ~= nil then
                cai_result(request_id, false, "busy", "Another DCS menu transaction is active")
                return
            end
            local executed, error_message = cai_base.pcall(function()
                setShowMenu(false)
                cai_state.guided_indexes = nil
                cai_base.missionCommands.doAction(action.action_index)
            end)
            if not executed then
                cai_result(request_id, false, "dcs_error", cai_base.tostring(error_message))
                return
            end
            cai_result(
                request_id,
                true,
                "accepted",
                "DCS accepted the current mission action; downstream effects are not observable"
            )
            cai_capture_menu(false)
            return
        end
        if action.kind ~= "radio" then
            cai_result(request_id, false, "invalid_action", "Invalid CombatAI action")
            return
        end
        -- Standard radio actions deliberately traverse DCS's own menus so
        -- recipient, radio tuning, and inherited parameters retain stock behaviour.
        cai_begin_transaction(
            request_id,
            message.revision,
            action.indexes,
            false,
            "accepted",
            "DCS completed the current radio action traversal; downstream effects are not observable",
            nil
        )
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
        cai_advance_transaction(now)
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
                hook_version = cai_hook_version,
                capabilities = cai_capabilities,
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
