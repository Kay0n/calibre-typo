local Client = require("calibretypo/client")
local Queue = require("calibretypo/queue")
local Settings = require("calibretypo/settings")
local _ = require("gettext")

local Sync = {}

local running = false

local function newClient()
    return Client.new(Settings.server(), Settings.token())
end

local NOT_CONFIGURED = _("Address or token not set")

function Sync.run()
    if running then
        return nil, _("Already sending")
    end
    if not Settings.isConfigured() then
        return nil, NOT_CONFIGURED
    end
    local edits = Queue.all()
    if #edits == 0 then
        return { sent = 0, remaining = 0 }
    end

    running = true
    local reply, err = newClient():sendEdits(edits)
    running = false
    if not reply then
        return nil, err.message
    end

    local sent = Queue.remove(reply.accepted or {})
    return { sent = sent, remaining = Queue.count(), plugin_version = reply.plugin_version }
end

function Sync.testConnection()
    if not Settings.isConfigured() then
        return nil, { kind = "config", message = NOT_CONFIGURED }
    end
    return newClient():ping()
end

return Sync
