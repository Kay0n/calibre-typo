local http = require("socket.http")
local json = require("json")
local ltn12 = require("ltn12")
local socket = require("socket")
local socketutil = require("socketutil")
local _ = require("gettext")
local T = require("ffi/util").template

local VERSION = require("calibretypo/version")

local Client = {}
Client.__index = Client

function Client.new(server, token)
    return setmetatable({ server = (server:gsub("/+$", "")), token = token }, Client)
end

local function failure(code, headers)
    if type(code) == "number" and code >= 300 and code < 400 then
        -- Not followed: LuaSocket can't resend a POST body
        local location = headers and headers.location or ""
        local target = location:match("^(%a+://[^/]+)") or location
        return { kind = "redirect",
                 message = T(_("Redirects to %1"), target) }
    elseif code == 401 then
        return { kind = "auth",
                 message = _("Invalid token") }
    elseif type(code) == "number" then
        return { kind = "server",
                 message = T(_("Unexpected response (HTTP %1)"), code) }
    end
    return { kind = "network", message = tostring(code or _("no response")) }
end

function Client:request(method, path, payload)
    local body = payload and json.encode(payload) or nil
    local response = {}
    local headers = {
        ["Authorization"] = "Bearer " .. self.token,
        ["Accept"] = "application/json",
        ["X-Calibre-Typo-Plugin"] = VERSION,
    }
    if body then
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = tostring(#body)
    end

    socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
    local ok, code, reply_headers = pcall(function()
        return socket.skip(1, http.request{
            url = self.server .. path,
            method = method,
            headers = headers,
            source = body and ltn12.source.string(body) or nil,
            sink = ltn12.sink.table(response),
            redirect = false,
        })
    end)
    socketutil:reset_timeout()

    if not ok or code ~= 200 then
        return nil, failure(code, ok and reply_headers)
    end
    local decoded_ok, decoded = pcall(json.decode, table.concat(response))
    if not decoded_ok or type(decoded) ~= "table" then
        return nil, { kind = "server", message = _("Unexpected response") }
    end
    return decoded
end

function Client:ping()
    return self:request("GET", "/api/v1/ping")
end

function Client:sendEdits(edits)
    return self:request("POST", "/api/v1/edits", { edits = edits })
end

return Client
