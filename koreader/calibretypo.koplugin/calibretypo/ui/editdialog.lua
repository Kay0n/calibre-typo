local InputDialog = require("ui/widget/inputdialog")
local UIManager = require("ui/uimanager")
local _ = require("gettext")

local EditDialog = {}

-- Full screen keeps long selections readable
local FULLSCREEN_FROM_CHARS = 300

function EditDialog.show(original, on_save)
    local dialog
    dialog = InputDialog:new{
        title = _("Fix text"),
        input = original,
        allow_newline = false,
        fullscreen = #original > FULLSCREEN_FROM_CHARS,
        buttons = {{
            {
                text = _("Cancel"),
                id = "close",
                callback = function()
                    UIManager:close(dialog)
                end,
            },
            {
                text = _("Save fix"),
                is_enter_default = true,
                callback = function()
                    local corrected = dialog:getInputText()
                    UIManager:close(dialog)
                    if corrected ~= original then
                        on_save(corrected)
                    end
                end,
            },
        }},
    }
    UIManager:show(dialog)
    dialog:onShowKeyboard()
end

return EditDialog
