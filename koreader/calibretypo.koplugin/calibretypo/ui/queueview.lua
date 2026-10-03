local ConfirmBox = require("ui/widget/confirmbox")
local Menu = require("ui/widget/menu")
local UIManager = require("ui/uimanager")
local _ = require("gettext")
local T = require("ffi/util").template

local Notify = require("calibretypo/ui/notify")
local Queue = require("calibretypo/queue")

local QueueView = {}

local function describe(edit)
    return T(_("%1: “%2” to “%3”"), edit.title or _("Unknown title"), edit.original, edit.replacement)
end

local function confirmDiscard(item, on_discarded)
    UIManager:show(ConfirmBox:new{
        text = T(_("Discard fix?\n\n%1"), item.text),
        ok_text = _("Discard"),
        ok_callback = function()
            Queue.remove({ item.uid })
            on_discarded()
        end,
    })
end

function QueueView.show()
    local edits = Queue.all()
    if #edits == 0 then
        Notify.show(_("No waiting fixes"), 2)
        return
    end

    local items = {}
    for _i, edit in ipairs(edits) do
        table.insert(items, { text = describe(edit), uid = edit.uid })
    end

    local menu
    menu = Menu:new{
        title = _("Waiting fixes (tap to discard)"),
        item_table = items,
        covers_fullscreen = true,
        is_borderless = true,
        is_popout = false,
        onMenuChoice = function(_menu, item)
            confirmDiscard(item, function()
                UIManager:close(menu)
                QueueView.show()
            end)
        end,
    }
    UIManager:show(menu)
end

return QueueView
