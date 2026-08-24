-- AzureSlop Plugin v0.5
-- One-shot Studio pull and draft/local test actions.

local HttpService = game:GetService("HttpService")
local ScriptEditorService = game:GetService("ScriptEditorService")

local POLL_INTERVAL = 2
local services = {}
local pendingConfig = nil
local completedSession = nil
local active = false

local VALUE_TYPES = {
	StringValue = true,
	NumberValue = true,
	IntValue = true,
	BoolValue = true,
}
local EVENT_TYPES = {
	RemoteEvent = true,
	RemoteFunction = true,
	BindableEvent = true,
	BindableFunction = true,
}

-- ─── Toolbar / widget ───────────────────────────────────────────────────────

local toolbar = plugin:CreateToolbar("AzureSlop")
local toggleBtn = toolbar:CreateButton(
	"AzureSlop",
	"Toggle AzureSlop panel",
	"rbxassetid://4458901886"
)

local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Float,
	false,
	false,
	300,
	180,
	260,
	160
)
local widget = plugin:CreateDockWidgetPluginGui("AzureSlopWidget", widgetInfo)
widget.Title = "AzureSlop"

local root = Instance.new("Frame")
root.Size = UDim2.fromScale(1, 1)
root.BackgroundColor3 = Color3.fromRGB(28, 28, 32)
root.BorderSizePixel = 0
root.Parent = widget

local statusDot = Instance.new("Frame")
statusDot.Size = UDim2.fromOffset(10, 10)
statusDot.Position = UDim2.fromOffset(12, 14)
statusDot.BackgroundColor3 = Color3.fromRGB(100, 100, 110)
statusDot.BorderSizePixel = 0
statusDot.Parent = root
local dotCorner = Instance.new("UICorner")
dotCorner.CornerRadius = UDim.new(1, 0)
dotCorner.Parent = statusDot

local statusLabel = Instance.new("TextLabel")
statusLabel.Size = UDim2.new(1, -40, 0, 20)
statusLabel.Position = UDim2.fromOffset(28, 10)
statusLabel.BackgroundTransparency = 1
statusLabel.Text = "Not connected"
statusLabel.TextColor3 = Color3.fromRGB(190, 190, 200)
statusLabel.Font = Enum.Font.GothamBold
statusLabel.TextSize = 12
statusLabel.TextXAlignment = Enum.TextXAlignment.Left
statusLabel.Parent = root

local subLabel = Instance.new("TextLabel")
subLabel.Size = UDim2.new(1, -24, 0, 38)
subLabel.Position = UDim2.fromOffset(12, 34)
subLabel.BackgroundTransparency = 1
subLabel.Text = "Run azureslop sync or azureslop test"
subLabel.TextColor3 = Color3.fromRGB(120, 120, 130)
subLabel.Font = Enum.Font.Gotham
subLabel.TextSize = 10
subLabel.TextWrapped = true
subLabel.TextXAlignment = Enum.TextXAlignment.Left
subLabel.TextYAlignment = Enum.TextYAlignment.Top
subLabel.Parent = root

local portLabel = Instance.new("TextLabel")
portLabel.Size = UDim2.fromOffset(34, 24)
portLabel.Position = UDim2.fromOffset(12, 76)
portLabel.BackgroundTransparency = 1
portLabel.Text = "Port:"
portLabel.TextColor3 = Color3.fromRGB(120, 120, 130)
portLabel.Font = Enum.Font.Gotham
portLabel.TextSize = 11
portLabel.TextXAlignment = Enum.TextXAlignment.Left
portLabel.Parent = root

local portInput = Instance.new("TextBox")
portInput.Size = UDim2.fromOffset(72, 22)
portInput.Position = UDim2.fromOffset(48, 77)
portInput.BackgroundColor3 = Color3.fromRGB(45, 45, 52)
portInput.BorderSizePixel = 0
portInput.Text = "25123"
portInput.TextColor3 = Color3.fromRGB(210, 210, 220)
portInput.Font = Enum.Font.Gotham
portInput.TextSize = 11
portInput.ClearTextOnFocus = false
portInput.Parent = root
local portCorner = Instance.new("UICorner")
portCorner.CornerRadius = UDim.new(0, 4)
portCorner.Parent = portInput

local actionButton = Instance.new("TextButton")
actionButton.Size = UDim2.new(1, -24, 0, 32)
actionButton.Position = UDim2.new(0, 12, 1, -44)
actionButton.BackgroundColor3 = Color3.fromRGB(35, 120, 210)
actionButton.BorderSizePixel = 0
actionButton.Text = "Waiting for command..."
actionButton.TextColor3 = Color3.fromRGB(245, 245, 250)
actionButton.Font = Enum.Font.GothamBold
actionButton.TextSize = 12
actionButton.AutoButtonColor = true
actionButton.Active = false
actionButton.Parent = root
local actionCorner = Instance.new("UICorner")
actionCorner.CornerRadius = UDim.new(0, 5)
actionCorner.Parent = actionButton

local function setStatus(text, sub, color)
	statusLabel.Text = text
	subLabel.Text = sub or ""
	statusDot.BackgroundColor3 = color or Color3.fromRGB(100, 100, 110)
end

local function setButton(text, enabled)
	actionButton.Text = text
	actionButton.Active = enabled
	actionButton.BackgroundColor3 = if enabled
		then Color3.fromRGB(35, 120, 210)
		else Color3.fromRGB(60, 60, 68)
end

-- ─── Instance mapping ───────────────────────────────────────────────────────

local function getInstancePath(instance)
	local parts = { instance.Name }
	local current = instance.Parent
	while current do
		local isService = false
		for _, serviceName in ipairs(services) do
			if current.Name == serviceName and current.Parent == game then
				isService = true
				break
			end
		end
		if isService then
			table.insert(parts, 1, current.Name)
			break
		end
		if current == game then
			break
		end
		table.insert(parts, 1, current.Name)
		current = current.Parent
	end
	return table.concat(parts, "/")
end

local function isTracked(instance)
	return instance:IsA("LuaSourceContainer")
		or VALUE_TYPES[instance.ClassName]
		or EVENT_TYPES[instance.ClassName]
end

local function collectAll()
	local results = {}
	for _, serviceName in ipairs(services) do
		local ok, service = pcall(function()
			return game:GetService(serviceName)
		end)
		if ok and service then
			local function recurse(instance)
				if isTracked(instance) then
					local source = ""
					local sourceOk = true
					if instance:IsA("LuaSourceContainer") then
						sourceOk, source = pcall(function()
							return ScriptEditorService:GetEditorSource(instance)
						end)
					elseif VALUE_TYPES[instance.ClassName] then
						sourceOk, source = pcall(function()
							return tostring(instance.Value)
						end)
					end
					if sourceOk then
						local path = getInstancePath(instance)
						if results[path] and results[path].source ~= source then
							warn("[AzureSlop] Multiple instances at " .. path .. " have different values; the last one will be pulled")
						end
						results[path] = {
							path = path,
							source = source,
							type = instance.ClassName,
						}
					end
				end
				for _, child in ipairs(instance:GetChildren()) do
					recurse(child)
				end
			end
			recurse(service)
		end
	end

	local snapshot = {}
	for _, entry in pairs(results) do
		table.insert(snapshot, entry)
	end
	return snapshot
end

local function buildInstanceMap()
	local instanceMap = {}
	for _, serviceName in ipairs(services) do
		local ok, service = pcall(function()
			return game:GetService(serviceName)
		end)
		if ok and service then
			local function recurse(instance)
				if isTracked(instance) then
					local path = getInstancePath(instance)
					instanceMap[path] = instanceMap[path] or {}
					table.insert(instanceMap[path], instance)
				end
				for _, child in ipairs(instance:GetChildren()) do
					recurse(child)
				end
			end
			recurse(service)
		end
	end
	return instanceMap
end

local function createInstance(change)
	local parts = string.split(change.path, "/")
	if #parts < 2 then
		return nil, "invalid path " .. change.path
	end

	local ok, service = pcall(function()
		return game:GetService(parts[1])
	end)
	if not ok or not service then
		return nil, "service unavailable for " .. change.path
	end

	local parent = service
	for index = 2, #parts - 1 do
		local child = parent:FindFirstChild(parts[index])
		if not child then
			child = Instance.new("Folder")
			child.Name = parts[index]
			child.Parent = parent
		end
		parent = child
	end

	local createdOk, instance = pcall(function()
		local newInstance = Instance.new(change.type or "ModuleScript")
		newInstance.Name = parts[#parts]
		-- Parent before UpdateSourceAsync so Drafts mode can create its draft.
		newInstance.Parent = parent
		return newInstance
	end)
	if not createdOk then
		return nil, "could not create " .. change.path .. ": " .. tostring(instance)
	end
	return instance, nil
end

local function applyValue(instance, source)
	if instance.ClassName == "StringValue" then
		instance.Value = source
	elseif instance.ClassName == "NumberValue" then
		instance.Value = tonumber(source) or 0
	elseif instance.ClassName == "IntValue" then
		instance.Value = math.floor(tonumber(source) or 0)
	elseif instance.ClassName == "BoolValue" then
		instance.Value = source == "true"
	end
end

local function applyTest(changes, deletions, localMode)
	local instanceMap = buildInstanceMap()
	local stats = { updated = 0, created = 0, deleted = 0, unchanged = 0, skipped = 0, errors = {} }

	for _, change in ipairs(changes) do
		local instances = instanceMap[change.path]
		if not instances or #instances == 0 then
			if localMode then
				local instance, createError = createInstance(change)
				if instance then
					instances = { instance }
					instanceMap[change.path] = instances
					stats.created += 1
				else
					table.insert(stats.errors, createError)
					stats.skipped += 1
				end
			else
				stats.skipped += 1
				table.insert(stats.errors, "no existing script for " .. change.path)
			end
		end

		if instances then
			for _, instance in ipairs(instances) do
				if instance:IsA("LuaSourceContainer") then
					local readOk, editorSource = pcall(function()
						return ScriptEditorService:GetEditorSource(instance)
					end)
					if readOk and editorSource == (change.source or "") then
						stats.unchanged += 1
					else
						local updateOk, updateError = pcall(function()
							ScriptEditorService:UpdateSourceAsync(instance, function()
								return change.source or ""
							end)
						end)
						if updateOk then
							stats.updated += 1
						else
							stats.skipped += 1
							table.insert(stats.errors, change.path .. ": " .. tostring(updateError))
						end
					end
				elseif localMode then
					local valueOk, valueError = pcall(function()
						applyValue(instance, change.source or "")
					end)
					if valueOk then
						stats.updated += 1
					else
						stats.skipped += 1
						table.insert(stats.errors, change.path .. ": " .. tostring(valueError))
					end
				else
					-- Value and event changes are not drafts; do not mutate the shared place.
					stats.skipped += 1
				end
			end
		end
	end

	for _, path in ipairs(deletions) do
		local instances = instanceMap[path]
		if localMode and instances then
			for _, instance in ipairs(instances) do
				local deleteOk, deleteError = pcall(function()
					instance:Destroy()
				end)
				if deleteOk then
					stats.deleted += 1
				else
					table.insert(stats.errors, path .. ": " .. tostring(deleteError))
				end
			end
		elseif instances then
			stats.skipped += #instances
			table.insert(stats.errors, "deletion is not draftable: " .. path)
		end
	end

	return stats
end

-- ─── One-shot actions ───────────────────────────────────────────────────────

local function serverUrl()
	return "http://localhost:" .. (tonumber(portInput.Text) or 25123)
end

local function postJson(path, data)
	return HttpService:PostAsync(
		serverUrl() .. path,
		HttpService:JSONEncode(data),
		Enum.HttpContentType.ApplicationJson,
		false
	)
end

local function runPendingAction()
	local config = pendingConfig
	if not config then
		return
	end
	setButton("Working...", false)
	setStatus("Working", "Keep this Studio window open", Color3.fromRGB(230, 170, 45))

	if config.action == "pull" then
		local snapshot = collectAll()
		postJson("/pull", {
			session = config.session,
			changes = snapshot,
		})
		completedSession = config.session
		pendingConfig = nil
		setStatus("Pull complete", string.format("Sent %d instance(s) to disk", #snapshot), Color3.fromRGB(30, 200, 100))
		setButton("Complete", false)
		return
	end

	if config.action == "test" then
		local response = HttpService:GetAsync(serverUrl() .. "/changes", false)
		local data = HttpService:JSONDecode(response)
		local stats = applyTest(data.changes or {}, data.deletions or {}, config.local == true)
		stats.session = config.session
		postJson("/complete", stats)
		completedSession = config.session
		pendingConfig = nil
		setStatus(
			"Test ready",
			string.format("%d updated, %d created, %d skipped", stats.updated, stats.created, stats.skipped),
			Color3.fromRGB(30, 200, 100)
		)
		setButton("Complete", false)
	end
end

actionButton.Activated:Connect(function()
	if not pendingConfig then
		return
	end
	local ok, actionError = pcall(runPendingAction)
	if not ok then
		warn("[AzureSlop] Action failed: " .. tostring(actionError))
		setStatus("Action failed", tostring(actionError), Color3.fromRGB(190, 60, 60))
		setButton("Retry", true)
	end
end)

local function checkForAction()
	local response = HttpService:GetAsync(serverUrl() .. "/config", false)
	local config = HttpService:JSONDecode(response)
	services = config.services or services

	if config.session == completedSession then
		return
	end
	pendingConfig = config
	if config.action == "pull" then
		setStatus("Pull requested", config.name or "AzureSlop project", Color3.fromRGB(35, 140, 230))
		setButton("Pull into disk", true)
	elseif config.action == "test" and config.local then
		setStatus("Local test requested", "Apply only in the disposable place window", Color3.fromRGB(35, 140, 230))
		setButton("Apply to local copy", true)
	elseif config.action == "test" then
		setStatus("Draft test requested", "Existing scripts only; review drafts before committing", Color3.fromRGB(35, 140, 230))
		setButton("Apply drafts", true)
	end
end

local function startPolling()
	if active then
		return
	end
	active = true
	task.spawn(function()
		while active do
			local ok = pcall(checkForAction)
			if not ok and not completedSession then
				pendingConfig = nil
				setStatus("Not connected", "Run azureslop sync or azureslop test", Color3.fromRGB(150, 70, 70))
				setButton("Waiting for command...", false)
			end
			task.wait(POLL_INTERVAL)
		end
	end)
end

local function stopPolling()
	active = false
	pendingConfig = nil
	completedSession = nil
	setStatus("Not connected", "Open the panel to look for a command", Color3.fromRGB(100, 100, 110))
	setButton("Waiting for command...", false)
end

toggleBtn.Click:Connect(function()
	widget.Enabled = not widget.Enabled
	if widget.Enabled then
		startPolling()
	else
		stopPolling()
	end
end)

print("[AzureSlop] Plugin loaded. Click AzureSlop in the toolbar to connect.")
