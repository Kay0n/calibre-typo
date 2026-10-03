local InputDialog = require("ui/widget/inputdialog")
local UIManager = require("ui/uimanager")
local _ = require("gettext")

local Settings = require("calibretypo/settings")

local SettingsDialog = {}

local function edit(title, value, hint, description, on_save)
    local dialog
    dialog = InputDialog:new{
        title = title,
        input = value or "",
        input_hint = hint,
        description = description,
        allow_newline = false,
        buttons = {{
            {
                text = _("Cancel"),
                id = "close",
                callback = function()
                    UIManager:close(dialog)
                end,
            },
            {
                text = _("Save"),
                is_enter_default = true,
                callback = function()
                    on_save(dialog:getInputText())
                    UIManager:close(dialog)
                end,
            },
        }},
    }
    UIManager:show(dialog)
    dialog:onShowKeyboard()
end

function SettingsDialog.editAddress()
    edit(_("Server address"), Settings.server(), "https://typo.example.com",
        _("Leave empty to use the downloaded value."), Settings.saveServer)
end

-- Never shown, so an empty save keeps the current token
function SettingsDialog.editToken()
    local status = Settings.token() and _("A token is set. Enter a new one to replace it.") or _("No token set.")
    edit(_("Device token"), "", _("from the Devices page"), status, function(token)
        if token:match("%S") then
            Settings.saveToken(token)
        end
    end)
end

return SettingsDialog
