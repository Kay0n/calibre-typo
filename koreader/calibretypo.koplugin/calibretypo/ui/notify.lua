local InfoMessage = require("ui/widget/infomessage")
local UIManager = require("ui/uimanager")

local Notify = {}

function Notify.show(text, timeout)
    UIManager:show(InfoMessage:new{ text = text, timeout = timeout })
end

return Notify
