-- AzureSlop Plugin v0.3
-- Polls the CLI sync server every 5 seconds; disk is the sole source of truth

local HttpService = game:GetService("HttpService")

local POLL_INTERVAL = 5  -- seconds

-- ─── State ───────────────────────────────────────────────────────────────────

local serverUrl = nil
local lastSyncTime = 0
local connected = false
local services = {}

-- ─── Toolbar / Widget ────────────────────────────────────────────────────────

local toolbar = plugin:CreateToolbar("AzureSlop")
local toggleBtn = toolbar:CreateButton("AzureSlop", "Toggle AzureSlop panel", "rbxassetid://4458901886")

local widgetInfo = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Float, false, false, 220, 120, 220, 120)
local widget = plugin:CreateDockWidgetPluginGui("AzureSlopWidget", widgetInfo)
widget.Title = "AzureSlop"

local root = Instance.new("Frame")
root.Size = UDim2.new(1,0,1,0)
root.BackgroundColor3 = Color3.fromRGB(28,28,32)
root.BorderSizePixel = 0
root.Parent = widget

local statusDot = Instance.new("Frame")
statusDot.Size = UDim2.new(0,10,0,10)
statusDot.Position = UDim2.new(0,12,0,14)
statusDot.BackgroundColor3 = Color3.fromRGB(100,100,110)
statusDot.BorderSizePixel = 0
statusDot.Parent = root
local dotCorner = Instance.new("UICorner")
dotCorner.CornerRadius = UDim.new(1,0)
dotCorner.Parent = statusDot

local statusLabel = Instance.new("TextLabel")
statusLabel.Size = UDim2.new(1,-32,0,20)
statusLabel.Position = UDim2.new(0,28,0,10)
statusLabel.BackgroundTransparency = 1
statusLabel.Text = "Not connected"
statusLabel.TextColor3 = Color3.fromRGB(160,160,170)
statusLabel.Font = Enum.Font.GothamBold
statusLabel.TextSize = 12
statusLabel.TextXAlignment = Enum.TextXAlignment.Left
statusLabel.Parent = root

local subLabel = Instance.new("TextLabel")
subLabel.Size = UDim2.new(1,-20,0,16)
subLabel.Position = UDim2.new(0,12,0,34)
subLabel.BackgroundTransparency = 1
subLabel.Text = "Run `azureslop sync` in your project folder"
subLabel.TextColor3 = Color3.fromRGB(100,100,110)
subLabel.Font = Enum.Font.Gotham
subLabel.TextSize = 10
subLabel.TextWrapped = true
subLabel.TextXAlignment = Enum.TextXAlignment.Left
subLabel.Parent = root

local lastSyncLabel = Instance.new("TextLabel")
lastSyncLabel.Size = UDim2.new(1,-20,0,14)
lastSyncLabel.Position = UDim2.new(0,12,0,88)
lastSyncLabel.BackgroundTransparency = 1
lastSyncLabel.Text = ""
lastSyncLabel.TextColor3 = Color3.fromRGB(80,80,90)
lastSyncLabel.Font = Enum.Font.Gotham
lastSyncLabel.TextSize = 10
lastSyncLabel.TextXAlignment = Enum.TextXAlignment.Left
lastSyncLabel.Parent = root

local portInput
do
	local lbl = Instance.new("TextLabel")
	lbl.Size = UDim2.new(0,32,0,24)
	lbl.Position = UDim2.new(0,12,0,60)
	lbl.BackgroundTransparency = 1
	lbl.Text = "Port:"
	lbl.TextColor3 = Color3.fromRGB(120,120,130)
	lbl.Font = Enum.Font.Gotham
	lbl.TextSize = 11
	lbl.TextXAlignment = Enum.TextXAlignment.Left
	lbl.Parent = root

	portInput = Instance.new("TextBox")
	portInput.Size = UDim2.new(0,70,0,22)
	portInput.Position = UDim2.new(0,46,0,61)
	portInput.BackgroundColor3 = Color3.fromRGB(45,45,52)
	portInput.BorderSizePixel = 0
	portInput.Text = "25123"
	portInput.TextColor3 = Color3.fromRGB(200,200,210)
	portInput.Font = Enum.Font.Gotham
	portInput.TextSize = 11
	portInput.ClearTextOnFocus = false
	portInput.Parent = root
	local pc = Instance.new("UICorner")
	pc.CornerRadius = UDim.new(0,4)
	pc.Parent = portInput
end

local function setStatus(text, sub, color)
	statusLabel.Text = text
	subLabel.Text = sub or ""
	statusDot.BackgroundColor3 = color or Color3.fromRGB(100,100,110)
end

local function setLastSync()
	lastSyncLabel.Text = "Last sync: " .. os.date("%H:%M:%S")
end

-- ─── Build path from instance up to service ──────────────────────────────────

local function getScriptPath(instance)
	local parts = { instance.Name }
	local current = instance.Parent
	while current and not current:IsA("ServiceProvider") do
		local isService = false
		for _, svcName in ipairs(services) do
			if current.Name == svcName and current.Parent == game then
				isService = true
				break
			end
		end
		if isService then break end
		table.insert(parts, 1, current.Name)
		current = current.Parent
	end
	if current then
		table.insert(parts, 1, current.Name)
	end
	return table.concat(parts, "/")
end

-- ─── Collect all scripts from watched services ───────────────────────────────

local function collectAllScripts()
	local results = {}
	local conflicts = {}  -- paths where siblings disagree on source

	for _, svcName in ipairs(services) do
		local ok, svc = pcall(function() return game:GetService(svcName) end)
		if ok and svc then
			local function recurse(inst)
				if inst:IsA("LuaSourceContainer") then
					local ok2, src = pcall(function() return inst.Source end)
					if ok2 then
						local path = getScriptPath(inst)
						if results[path] and results[path].source ~= src then
							-- Two same-named siblings with different sources.
							-- Last one wins on disk; flag for the user so they know.
							conflicts[path] = true
						end
						results[path] = {
							path = path,
							source = src,
							type = inst.ClassName,
							timestamp = os.time(),
						}
					end
				end
				for _, child in ipairs(inst:GetChildren()) do
					recurse(child)
				end
			end
			recurse(svc)
		end
	end

	for path in pairs(conflicts) do
		warn(string.format(
			"[AzureSlop] Dedup conflict: multiple scripts at '%s' have different sources — last-write wins on disk",
			path
		))
	end

	local arr = {}
	for _, v in pairs(results) do
		table.insert(arr, v)
	end
	return arr
end

-- ─── Apply incoming changes from disk to Studio ──────────────────────────────

-- Disk is the sole source of truth. For each incoming change:
--   1. Matching instances exist → update Source on ALL of them (dedup propagation)
--   2. No instance found → create a new script in the hierarchy
-- For each incoming deletion:
--   3. Matching instances exist → destroy all of them

local function applyChanges(changes, deletions)
	-- Build a lookup: path -> all matching script instances
	local scriptMap = {}
	for _, svcName in ipairs(services) do
		local ok, svc = pcall(function() return game:GetService(svcName) end)
		if ok and svc then
			local function recurse(inst)
				if inst:IsA("LuaSourceContainer") then
					local path = getScriptPath(inst)
					if not scriptMap[path] then scriptMap[path] = {} end
					table.insert(scriptMap[path], inst)
				end
				for _, child in ipairs(inst:GetChildren()) do
					recurse(child)
				end
			end
			recurse(svc)
		end
	end

	-- Handle deletions from disk
	for _, path in ipairs(deletions) do
		local instances = scriptMap[path]
		if instances then
			for _, inst in ipairs(instances) do
				pcall(function() inst:Destroy() end)
			end
			print(string.format("[AzureSlop] Disk → Studio: deleted %s", path))
		end
	end

	if #changes == 0 then return end

	local updated = 0
	local created = 0

	for _, change in ipairs(changes) do
		local path = change.path
		local source = change.source
		local instances = scriptMap[path]

		if instances and #instances > 0 then
			-- Update every instance that shares this path (e.g. all Door/DoorScript)
			for _, inst in ipairs(instances) do
				pcall(function() inst.Source = source end)
			end
			updated = updated + #instances
		else
			-- New file on disk — create the corresponding script instance
			local parts = {}
			for part in path:gmatch("[^/]+") do
				table.insert(parts, part)
			end
			if #parts >= 2 then
				local svcName = parts[1]
				local ok, svc = pcall(function() return game:GetService(svcName) end)
				if ok and svc then
					local parent = svc
					for i = 2, #parts - 1 do
						local folderName = parts[i]
						local existing = parent:FindFirstChild(folderName)
						if not existing then
							local folder = Instance.new("Folder")
							folder.Name = folderName
							folder.Parent = parent
							existing = folder
						end
						parent = existing
					end
					local scriptType = change.type or "ModuleScript"
					local scriptName = parts[#parts]
					local newScript = Instance.new(scriptType)
					newScript.Name = scriptName
					newScript.Source = source
					newScript.Parent = parent
					created = created + 1
				end
			end
		end
	end

	if updated > 0 then
		print(string.format("[AzureSlop] Disk → Studio: %d instance(s) updated", updated))
	end
	if created > 0 then
		print(string.format("[AzureSlop] Disk → Studio: %d script(s) created", created))
	end
end

-- ─── Main sync loop ──────────────────────────────────────────────────────────

local firstConnect = true

local function syncLoop()
	local port = tonumber(portInput.Text) or 25123
	serverUrl = "http://localhost:" .. port

	-- Try to fetch config
	local ok, response = pcall(function()
		return HttpService:GetAsync(serverUrl .. "/config", false)
	end)

	if not ok then
		connected = false
		setStatus("Not connected", "Run `azureslop sync` in your project folder", Color3.fromRGB(180,60,60))
		return
	end

	local config = HttpService:JSONDecode(response)
	services = config.services or services

	if not connected then
		connected = true
		setStatus("Connected", config.name or "AzureSlop project", Color3.fromRGB(30,200,100))
		print("[AzureSlop] Connected to " .. (config.name or "project") .. " on port " .. port)
	end

	-- On first connect, snapshot Studio → disk so VS Code has a starting state
	if firstConnect then
		firstConnect = false
		print("[AzureSlop] First connect — pushing all scripts to disk...")
		local allScripts = collectAllScripts()
		if #allScripts > 0 then
			local payload = HttpService:JSONEncode({ changes = allScripts })
			pcall(function()
				HttpService:PostAsync(serverUrl .. "/update", payload, Enum.HttpContentType.ApplicationJson, false)
			end)
			print(string.format("[AzureSlop] Pushed %d script(s) to disk", #allScripts))
		end
		lastSyncTime = os.time()
		setLastSync()
		return
	end

	-- Pull changes from disk and apply to Studio (disk is sole source of truth)
	local ok2, resp2 = pcall(function()
		return HttpService:GetAsync(serverUrl .. "/changes?since=" .. lastSyncTime, false)
	end)
	if ok2 then
		local data = HttpService:JSONDecode(resp2)
		applyChanges(data.changes or {}, data.deletions or {})
	end

	lastSyncTime = os.time()
	setLastSync()
end

-- ─── Poll timer ──────────────────────────────────────────────────────────────

local active = false

local function startPolling()
	active = true
	task.spawn(function()
		while active do
			local ok, err = pcall(syncLoop)
			if not ok then
				warn("[AzureSlop] Sync error: " .. tostring(err))
			end
			task.wait(POLL_INTERVAL)
		end
	end)
end

local function stopPolling()
	active = false
	connected = false
	firstConnect = true
	lastSyncTime = 0
	setStatus("Not connected", "Run `azureslop sync` in your project folder", Color3.fromRGB(100,100,110))
end

-- ─── Widget toggle + auto-start ──────────────────────────────────────────────

toggleBtn.Click:Connect(function()
	widget.Enabled = not widget.Enabled
	if widget.Enabled and not active then
		startPolling()
	elseif not widget.Enabled and active then
		stopPolling()
	end
end)

print("[AzureSlop] Plugin loaded. Click AzureSlop in the toolbar to connect.")
