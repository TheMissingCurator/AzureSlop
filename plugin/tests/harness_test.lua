-- Execute the real harness block against a small Studio API test double.
-- Run from repository root: lua plugin/tests/harness_test.lua
local file = assert(io.open("plugin/AzureSlop.lua"))
local source = file:read("*a")
file:close()
assert(load(source)) -- the distributed plugin also parses as Lua
local first = assert(source:find("local Harness =", 1, true))
local last = assert(source:find("local function runPendingAction()", first, true))
local harnessSource = source:sub(first, last - 1) .. "\nreturn Harness"

local guid = 0
local sent = {}
local jsonValues = {}
local nextJob = nil
local failChunk = false
local model = {}
local selection = {}
local playing = false
local recordings, finishes = 0, 0
local function instance(class, name, parent)
    local obj = { ClassName = class, Name = name or class, Parent = parent, children = {}, attributes = {} }
    if parent then table.insert(parent.children, obj) end
    function obj:GetChildren()
        local out = {}
        for _, child in ipairs(self.children) do
            if child.Parent == self then table.insert(out, child) end
        end
        return out
    end
    function obj:GetFullName() return self.Name end
    function obj:IsDescendantOf(other)
        local ancestor = self.Parent
        while ancestor do
            if ancestor == other then return true end
            ancestor = ancestor.Parent
        end
        return false
    end
    function obj:IsA(wanted)
        return self.ClassName == wanted or (wanted == "LuaSourceContainer" and
            (self.ClassName == "Script" or self.ClassName == "ModuleScript"))
    end
    function obj:GetAttributes() return self.attributes end
    function obj:SetAttribute(key, value) self.attributes[key] = value end
    function obj:Destroy() self.Parent = nil self.destroyed = true end
    return obj
end
model.game = instance("DataModel", "Test Place")
model.game.PlaceId = 123
model.workspace = instance("Workspace", "Workspace", model.game)
model.part = instance("Part", "Duplicate", model.workspace)
model.part.Anchored = false
model.duplicate = instance("Part", "Duplicate", model.workspace)
model.script = instance("Script", "Main", model.workspace)
model.script.Source = "original"
local Http = {}
function Http:GenerateGUID()
    guid = guid + 1
    return "id-" .. guid
end
function Http:JSONEncode(value)
    local id = "encoded-" .. (#jsonValues + 1)
    jsonValues[#jsonValues + 1] = value
    jsonValues[id] = value
    return id
end
function Http:JSONDecode(value) return assert(jsonValues[value]) end
function Http:RequestAsync(req)
    if req.Url:find("/result/chunk", 1, true) then
        if failChunk then
            failChunk = false
            return { Success = false, StatusCode = 503, Body = "test network failure" }
        end
        sent[#sent+1] = self:JSONDecode(req.Body)
    elseif req.Url:find("/poll", 1, true) then
        local job = nextJob
        nextJob = nil
        return { Success = true, StatusCode = 200, Body = self:JSONEncode({ job = job }) }
    end
    return { Success = true, StatusCode = 200, Body = self:JSONEncode({ ok = true }) }
end
local event = { Connect = function(_, callback)
    return { Disconnect = function() end, callback = callback }
end }
local service = {
    ChangeHistoryService = {
        TryBeginRecording = function() recordings = recordings + 1 return "recording" end,
        FinishRecording = function() finishes = finishes + 1 end,
    },
    Selection = {
        Get = function() return selection end,
        Set = function(_, value) selection = value end,
    },
    RunService = { IsRunning = function() return playing end },
    LogService = { MessageOut = event },
}
function model.game:GetService(name) return assert(service[name], name) end
local env = setmetatable({
    game = model.game, HttpService = Http,
    ScriptEditorService = {
        GetEditorSource = function(_, obj) return obj.Source end,
        UpdateSourceAsync = function(_, obj, fn) obj.Source = fn(obj.Source) end,
    },
    Instance = { new = function(class) return instance(class) end },
    script = instance("Script", "Plugin"),
    plugin = { Unloading = event },
    task = { spawn = function(fn) fn() end },
    typeof = function(value) return type(value) == "table" and value.ClassName and "Instance" or type(value) end,
    Enum = { FinishRecordingOperation = { Commit = "Commit" } },
    services = { "Workspace" },
    PULL_CHUNK_SIZE = 400 * 1024,
    serializeValue = function(v) return v end,
    deserializeValue = function(v) return v, true end,
    setStatus = function() end,
    setButton = function() end,
    Color3 = { fromRGB = function() end },
    serverUrl = function() return "http://127.0.0.1:25123" end,
    collectAll = function(strict)
        assert(strict, "Harness snapshots must fail on unreadable sources")
        return { { path = "Workspace/Main", source = model.script.Source, type = "Script" } }, {}
    end,
}, { __index = _G })
math.clamp = function(value, low, high) return math.max(low, math.min(high, value)) end
env.require = function(module)
    return assert(load(module.Source, "command", "t", env))()
end
local Harness = assert(load(harnessSource, "harness", "t", env))()
Harness.enable({ session = "epoch" })
local function call(method, params)
    nextJob = { id = Http:GenerateGUID(), method = method, params = params or {} }
    Harness.tick()
    assert(Harness.pending, "Expected a result after execution")
    Harness.tick()
    return sent[#sent]
end

local tree = call("tree", { target = { "Workspace" }, depth = 1 })
assert(tree.ok and tree.value.count == 4)
local target = { id = tree.value.tree.children[1].id }
local ambiguous = call("get", { target = { "Workspace", "Duplicate" } })
assert(not ambiguous.ok and ambiguous.error:find("Ambiguous", 1, true))
local properties = call("get", { target = target, properties = { "Anchored" } })
assert(properties.ok and properties.value.properties.Anchored == false, "False must remain a boolean")

local changed = call("set", { target = target, properties = { Anchored = true } })
assert(changed.ok and model.part.Anchored == true)
local sourceResult = call("write_source", { target = { "Workspace", "Main" }, source = "new", expected = "wrong" })
assert(not sourceResult.ok and model.script.Source == "original")
assert(sourceResult.partialEditsPossible)
assert(call("write_source", { target = { "Workspace", "Main" }, source = "new", expected = "original" }).ok)
assert(call("read_source", { target = { "Workspace", "Main" } }).value.source == "new")
playing = true
assert(not call("delete", { target = target }).ok)
assert(model.part.Parent == model.workspace)
assert(not call("snapshot").ok)
playing = false
assert(call("snapshot").ok)
assert(not call("delete", { target = { "Workspace" } }).ok)

-- A failed result upload must not rerun an already completed mutation.
nextJob = { id = "once", method = "execute", params = { source = "workspace.executions = (workspace.executions or 0) + 1; return false" } }
env.workspace = model.workspace
Harness.tick()
failChunk = true
assert(not pcall(Harness.tick))
assert(Harness.pending and model.workspace.executions == 1)
Harness.tick()
assert(model.workspace.executions == 1)
assert(sent[#sent].ok and sent[#sent].value == false)
assert(recordings == finishes, "Undo recordings must finish, including command errors")

assert(call("delete", { target = target }).ok)
assert(model.part.Parent == nil)
assert(not call("get", { target = target }).ok, "Detached IDs must be rejected")
Harness.disable()
assert(not Harness.enabled)
print("Harness Studio mock tests passed")
