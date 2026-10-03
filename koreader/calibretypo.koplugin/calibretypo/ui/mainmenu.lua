local _ = require("gettext")
local T = require("ffi/util").template

local Queue = require("calibretypo/queue")

local MainMenu = {}

function MainMenu.build(actions)
    return {
        text = _("Calibre typo fixes"),
        sorting_hint = "tools",
        sub_item_table = {
            {
                text_func = function()
                    return T(_("Send fixes now (%1 waiting)"), Queue.count())
                end,
                keep_menu_open = true,
                callback = actions.sync,
            },
            {
                text = _("Waiting fixes"),
                callback = actions.showQueue,
                separator = true,
            },
            {
                text = _("Server settings"),
                sub_item_table = {
                    {
                        text = _("Address"),
                        keep_menu_open = true,
                        callback = actions.editAddress,
                    },
                    {
                        text = _("Device token"),
                        keep_menu_open = true,
                        callback = actions.editToken,
                        separator = true,
                    },
                    {
                        text = _("Test connection"),
                        keep_menu_open = true,
                        callback = actions.testConnection,
                    },
                },
            },
        },
    }
end

return MainMenu
