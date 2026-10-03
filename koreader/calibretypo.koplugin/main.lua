local NetworkMgr = require("ui/network/manager")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local logger = require("logger")
local _ = require("gettext")
local N_ = _.ngettext
local T = require("ffi/util").template

local Edit = require("calibretypo/edit")
local EditDialog = require("calibretypo/ui/editdialog")
local MainMenu = require("calibretypo/ui/mainmenu")
local Notify = require("calibretypo/ui/notify")
local Queue = require("calibretypo/queue")
local QueueView = require("calibretypo/ui/queueview")
local Selection = require("calibretypo/selection")
local Settings = require("calibretypo/settings")
local SettingsDialog = require("calibretypo/ui/settingsdialog")
local Sync = require("calibretypo/sync")
local VERSION = require("calibretypo/version")

local CONTEXT_WORDS = 12
local HIGHLIGHT_BUTTON_ID = "12_calibretypo"
local UPDATE_NOTICE_KEY = "calibretypo_update_notice"

local CalibreTypo = WidgetContainer:extend{
    name = "calibretypo",
    is_doc_only = false,
}

function CalibreTypo:init()
    Settings.adoptNewDownload()
    self.ui.menu:registerToMainMenu(self)
    -- Only reflowable documents have stable text positions
    if self.ui.highlight and self.ui.rolling then
        self.ui.highlight:addToHighlightDialog(HIGHLIGHT_BUTTON_ID, function(highlight, index)
            return {
                text = _("Fix text"),
                callback = function()
                    self:startFix(highlight, index)
                end,
            }
        end)
    end
end

function CalibreTypo:addToMainMenu(menu_items)
    menu_items.calibretypo = MainMenu.build{
        sync = function()
            NetworkMgr:runWhenOnline(function() self:sync(true) end)
        end,
        showQueue = QueueView.show,
        editAddress = SettingsDialog.editAddress,
        editToken = SettingsDialog.editToken,
        testConnection = function()
            NetworkMgr:runWhenOnline(function() self:testConnection() end)
        end,
    }
end

function CalibreTypo:startFix(highlight, index)
    local selection = Selection.fromHighlight(highlight, index)
    if not selection then
        return
    end
    selection.before, selection.after =
        Selection.context(self.ui.document, selection.pos0, selection.pos1, CONTEXT_WORDS)
    highlight:onClose()

    EditDialog.show(selection.text, function(replacement)
        self:saveFix(selection, replacement)
    end)
end

function CalibreTypo:saveFix(selection, replacement)
    local waiting = Queue.add(Edit.new(selection, replacement, Selection.bookInfo(self.ui)))
    Notify.show(T(_("Fix saved (%1 waiting)"), waiting), 2)
    self:syncSoon()
end

-- Only when online, so saving a fix never brings up a Wi-Fi prompt
function CalibreTypo:syncSoon()
    UIManager:scheduleIn(1, function()
        if Queue.count() == 0 or not Settings.isConfigured() then
            return
        end
        local ok, connected = pcall(NetworkMgr.isConnected, NetworkMgr)
        if ok and connected then
            self:sync(false)
        end
    end)
end

function CalibreTypo:onNetworkConnected()
    self:syncSoon()
end

function CalibreTypo:onReaderReady()
    self:syncSoon()
end

function CalibreTypo:sync(interactive)
    local result, err = Sync.run()
    if not result then
        logger.warn("calibretypo: sync failed:", err)
        if interactive then
            Notify.show(T(_("Send failed: %1"), err))
        end
        return
    end
    if result.sent > 0 then
        Notify.show(T(N_("Sent 1 fix", "Sent %1 fixes", result.sent), result.sent), 2)
    elseif interactive then
        Notify.show(_("No waiting fixes"), 2)
    end
    self:announceUpdate(result.plugin_version)
end

function CalibreTypo:testConnection()
    local reply, err = Sync.testConnection()
    if reply then
        Notify.show(T(_("Connected as “%1”"), reply.device or "?"))
        self:announceUpdate(reply.plugin_version)
    elseif err.kind == "network" then
        Notify.show(T(_("Couldn't connect: %1"), err.message))
    else
        Notify.show(err.message)
    end
end

local function parseVersion(text)
    local parts = {}
    for number in tostring(text or ""):gmatch("%d+") do
        table.insert(parts, tonumber(number))
    end
    return parts
end

local function isNewer(candidate, current)
    local a, b = parseVersion(candidate), parseVersion(current)
    for i = 1, math.max(#a, #b) do
        local x, y = a[i] or 0, b[i] or 0
        if x ~= y then
            return x > y
        end
    end
    return false
end

function CalibreTypo:announceUpdate(server_version)
    if not isNewer(server_version, VERSION)
        or G_reader_settings:readSetting(UPDATE_NOTICE_KEY) == server_version then
        return
    end
    G_reader_settings:saveSetting(UPDATE_NOTICE_KEY, server_version)
    Notify.show(T(_("Plugin update available: %1"), server_version))
end

return CalibreTypo
