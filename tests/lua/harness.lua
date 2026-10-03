--[[
KOReader's UI is faked; networking and JSON are real, so the plugin talks to a real server

    luajit harness.lua <plugin dir> <settings dir> <address that redirects to the server>
]]

local plugin_dir, settings_dir, redirecting_address = arg[1], arg[2], arg[3]
package.path = plugin_dir .. "/?.lua;" .. package.path

local shown = {}
local messages = {}

local function check(condition, message)
    if not condition then error("check failed: " .. message, 2) end
end

local function lastMessage()
    return messages[#messages] or ""
end

local function widget(kind)
    local class = { kind = kind }
    function class:new(o)
        o = setmetatable(o or {}, { __index = self })
        if o.kind == "InfoMessage" then table.insert(messages, o.text) end
        return o
    end
    return class
end

local InputDialog = widget("InputDialog")
function InputDialog:getInputText() return self.typed or self.input end
function InputDialog:onShowKeyboard() end

local MultiInputDialog = widget("MultiInputDialog")
function MultiInputDialog:getFields()
    local values = {}
    for i, field in ipairs(self.fields) do values[i] = field.text end
    return values
end
function MultiInputDialog:onShowKeyboard() end

local WidgetContainer = {}
function WidgetContainer:extend(o) return setmetatable(o or {}, { __index = self }) end
function WidgetContainer:new(o)
    o = setmetatable(o or {}, { __index = self })
    if o.init then o:init() end
    return o
end

local store = {}
local LuaSettings = {}
function LuaSettings:open(path)
    store[path] = store[path] or {}
    local data = store[path]
    return {
        readSetting = function(_, key) return data[key] end,
        saveSetting = function(_, key, value) data[key] = value end,
        flush = function() end,
    }
end

local fakes = {
    ["datastorage"] = { getSettingsDir = function() return settings_dir end },
    ["luasettings"] = LuaSettings,
    ["logger"] = { warn = function() end, info = function() end, dbg = function() end },
    ["gettext"] = setmetatable({
        ngettext = function(singular, plural, n) return n == 1 and singular or plural end,
    }, { __call = function(_, s) return s end }),
    ["ffi/util"] = {
        template = function(s, ...)
            local args = { ... }
            return (s:gsub("%%(%d)", function(n) return tostring(args[tonumber(n)]) end))
        end,
    },
    ["ffi/sha2"] = {
        md5 = function(s)
            local h = 0
            for i = 1, #s do h = (h * 31 + s:byte(i)) % 4294967296 end
            return string.format("%08x%d", h, #s)
        end,
    },
    ["socketutil"] = {
        LARGE_BLOCK_TIMEOUT = 10, LARGE_TOTAL_TIMEOUT = 30,
        set_timeout = function() end, reset_timeout = function() end,
    },
    ["json"] = require("dkjson"),
    ["ui/uimanager"] = {
        show = function(_, w) table.insert(shown, w) end,
        close = function() end,
        scheduleIn = function(_, _seconds, fn) fn() end,
    },
    ["ui/network/manager"] = {
        isConnected = function() return true end,
        runWhenOnline = function(_, fn) fn() end,
    },
    ["ui/widget/container/widgetcontainer"] = WidgetContainer,
    ["ui/widget/infomessage"] = widget("InfoMessage"),
    ["ui/widget/inputdialog"] = InputDialog,
    ["ui/widget/multiinputdialog"] = MultiInputDialog,
    ["ui/widget/confirmbox"] = widget("ConfirmBox"),
    ["ui/widget/menu"] = widget("Menu"),
}
for name, module in pairs(fakes) do
    package.preload[name] = function() return module end
end

local settings = {}
G_reader_settings = {
    readSetting = function(_, key) return settings[key] end,
    saveSetting = function(_, key, value) settings[key] = value end,
    delSetting = function(_, key) settings[key] = nil end,
}
-- Typed in by hand before this download was installed
settings.calibretypo_token = "ctd_from_an_old_download"

local POS0 = "/body/DocFragment[1]/body/p[2]/text().17"
local POS1 = "/body/DocFragment[1]/body/p[2]/text().23"

local document = {
    file = "/mnt/us/books/Fugitive Telemetry - Martha Wells.epub",
    getProps = function() return { title = "Fugitive Telemetry", authors = "Martha Wells" } end,
    getPrevVisibleWordStart = function(_, xp) if xp == POS0 then return "start" end end,
    getNextVisibleWordEnd = function(_, xp) if xp == POS1 then return "end" end end,
    getTextFromXPointers = function(_, from, to)
        if to == POS0 then return "A non-dead human " end
        if from == POS1 then return " into the lobby" end
        return ""
    end,
}

local highlight = { buttons = {}, closed = false }
function highlight:addToHighlightDialog(id, fn) self.buttons[id] = fn end
function highlight:onClose() self.closed = true end

local main_menu = {}
local ui = {
    document = document,
    doc_props = { title = "Fugitive Telemetry", authors = "Martha Wells" },
    rolling = {},
    highlight = highlight,
    menu = { registerToMainMenu = function(_, plugin) plugin:addToMainMenu(main_menu) end },
}
highlight.ui = ui

local Plugin = require("main")
Plugin:new{ ui = ui, path = plugin_dir }

check(main_menu.calibretypo, "main menu entry registered")
check(settings.calibretypo_token == nil, "a new download replaces a token typed in earlier")
local make_button = highlight.buttons["12_calibretypo"]
check(make_button, "highlight button registered")

-- 1. Select text, choose "Fix text", type a correction, save
highlight.selected_text = { text = "walked", pos0 = POS0, pos1 = POS1 }
make_button(highlight, nil).callback()
check(highlight.closed, "highlight menu closed")

local dialog = shown[#shown]
check(dialog.kind == "InputDialog" and dialog.input == "walked", "edit dialog prefilled with selection")
dialog.typed = "strolled"
dialog.buttons[1][2].callback()   -- "Save fix": queues, then syncs because we're online

check(lastMessage():find("Sent 1 fix", 1, true), "fix was sent: " .. lastMessage())
check(require("calibretypo/queue").count() == 0, "queue is empty after sync")

-- 2. Unchanged text isn't queued
make_button(highlight, nil).callback()
shown[#shown].buttons[1][2].callback()
check(require("calibretypo/queue").count() == 0, "unchanged text not queued")

-- 3. Server settings: Address, Device token, Test connection
local items = main_menu.calibretypo.sub_item_table
local server_items = items[3].sub_item_table
local edit_address, edit_token, test_connection =
    server_items[1].callback, server_items[2].callback, server_items[3].callback
local Settings = require("calibretypo/settings")
local bundled_server, bundled_token = Settings.server(), Settings.token()

local function typeInto(open, text)
    open()
    local field = shown[#shown]
    check(field.kind == "InputDialog", "settings dialog shown")
    field.typed = text
    field.buttons[1][2].callback()   -- "Save"
end

test_connection()
check(lastMessage():find("Connected as “Harness”", 1, true), "test connection: " .. lastMessage())

-- 4. A bad token is reported, and fixes stay queued
typeInto(edit_token, "ctd_wrong")
check(settings.calibretypo_token == "ctd_wrong", "typed token stored")
test_connection()
check(lastMessage():find("Invalid token", 1, true), "refused token: " .. lastMessage())
make_button(highlight, nil).callback()
local retry = shown[#shown]
retry.typed = "sauntered"
retry.buttons[1][2].callback()
check(require("calibretypo/queue").count() == 1, "fix kept while server refuses it")
items[1].callback()
check(lastMessage():find("Send failed: Invalid token", 1, true), "bad token on send: " .. lastMessage())

-- 5. Token: never shown, kept on an empty save, not stored if same as the download's
edit_token()
local token_dialog = shown[#shown]
check(token_dialog.input == "", "token not shown")
check(not token_dialog.description:find(bundled_token, 1, true), "token not in the description")
typeInto(edit_token, "  ")
check(settings.calibretypo_token == "ctd_wrong", "empty save keeps the current token")
typeInto(edit_token, bundled_token)
check(settings.calibretypo_token == nil and Settings.token() == bundled_token, "token matching the download not stored")

-- 6. An unreachable address is reported
typeInto(edit_address, "http://127.0.0.1:9")
check(settings.calibretypo_server == "http://127.0.0.1:9", "typed address stored")
test_connection()
check(lastMessage():find("Couldn't connect: ", 1, true), "unreachable: " .. lastMessage())

-- 7. A redirecting address says where to, when testing and sending
typeInto(edit_address, redirecting_address)
test_connection()
check(lastMessage():find("Redirects to " .. bundled_server, 1, true), "redirect: " .. lastMessage())
items[1].callback()
check(lastMessage():find("Send failed: Redirects to " .. bundled_server, 1, true), "redirect on send: " .. lastMessage())

typeInto(edit_address, bundled_server)
check(settings.calibretypo_server == nil, "address matching the download not stored")
test_connection()
check(lastMessage():find("Connected as", 1, true), "back to the download's settings: " .. lastMessage())

print("OK")
