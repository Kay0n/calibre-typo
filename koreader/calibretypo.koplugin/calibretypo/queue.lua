-- A file, so waiting fixes survive restarts

local DataStorage = require("datastorage")
local LuaSettings = require("luasettings")

local Queue = {}

local QUEUE_FILE = DataStorage:getSettingsDir() .. "/calibretypo_queue.lua"
local KEY = "edits"

-- Re-read every time: the reader and file browser each run their own copy
local function load()
    local store = LuaSettings:open(QUEUE_FILE)
    return store:readSetting(KEY) or {}, store
end

local function save(store, edits)
    store:saveSetting(KEY, edits)
    store:flush()
end

function Queue.all()
    return (load())
end

function Queue.count()
    return #(load())
end

function Queue.add(edit)
    local edits, store = load()
    table.insert(edits, edit)
    save(store, edits)
    return #edits
end

function Queue.remove(uids)
    local wanted = {}
    for _, uid in ipairs(uids) do
        wanted[uid] = true
    end
    local edits, store = load()
    local kept = {}
    for _, edit in ipairs(edits) do
        if not wanted[edit.uid] then
            table.insert(kept, edit)
        end
    end
    save(store, kept)
    return #edits - #kept
end

return Queue
