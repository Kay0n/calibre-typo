-- Typed values override config.lua until a new download (new token) arrives

local sha2 = require("ffi/sha2")

local Settings = {}

local KEY_SERVER = "calibretypo_server"
local KEY_TOKEN = "calibretypo_token"
-- Fingerprint of the last bundled token, to spot a new download
local KEY_BUNDLE = "calibretypo_bundle_seen"

local function bundled()
    local ok, config = pcall(require, "calibretypo/config")
    if ok and type(config) == "table" then
        return config
    end
    return {}
end

local function trim(s)
    return ((s or ""):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function nonEmpty(s)
    if s and s ~= "" then return s end
end

-- Not stored if empty or same as the download's, so the download stays in charge
local function store(key, value, bundled_value)
    if value == "" or value == bundled_value then
        G_reader_settings:delSetting(key)
    else
        G_reader_settings:saveSetting(key, value)
    end
end

function Settings.adoptNewDownload()
    local token = nonEmpty(bundled().token)
    if not token then return end
    local fingerprint = sha2.md5(token)
    if G_reader_settings:readSetting(KEY_BUNDLE) ~= fingerprint then
        G_reader_settings:delSetting(KEY_SERVER)
        G_reader_settings:delSetting(KEY_TOKEN)
        G_reader_settings:saveSetting(KEY_BUNDLE, fingerprint)
    end
end

function Settings.server()
    return nonEmpty(G_reader_settings:readSetting(KEY_SERVER)) or nonEmpty(bundled().server)
end

function Settings.token()
    return nonEmpty(G_reader_settings:readSetting(KEY_TOKEN)) or nonEmpty(bundled().token)
end

function Settings.isConfigured()
    return Settings.server() ~= nil and Settings.token() ~= nil
end

function Settings.saveServer(server)
    store(KEY_SERVER, trim(server), bundled().server)
end

function Settings.saveToken(token)
    store(KEY_TOKEN, (trim(token):gsub("%s+", "")), bundled().token)
end

return Settings
