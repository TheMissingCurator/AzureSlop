-- AzureSlop Plugin v0.7.0
-- One-shot Studio pull, guarded push, and draft/local test actions.

local HttpService = game:GetService("HttpService")
local ScriptEditorService = game:GetService("ScriptEditorService")

local POLL_INTERVAL = 2
local PULL_CHUNK_SIZE = 400 * 1024
local services = {}
local pendingConfig = nil
local completedSession = nil
local conflictSession = nil
local active = false
local polling = false

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
local GUI_TYPES = {
	ScreenGui = true,
	SurfaceGui = true,
	BillboardGui = true,
	Frame = true,
	ScrollingFrame = true,
	CanvasGroup = true,
	TextLabel = true,
	TextButton = true,
	TextBox = true,
	ImageLabel = true,
	ImageButton = true,
	ViewportFrame = true,
	VideoFrame = true,
	UICorner = true,
	UIStroke = true,
	UIPadding = true,
	UIListLayout = true,
	UIGridLayout = true,
	UIPageLayout = true,
	UITableLayout = true,
	UIAspectRatioConstraint = true,
	UISizeConstraint = true,
	UITextSizeConstraint = true,
	UIScale = true,
	UIGradient = true,
	UIFlexItem = true,
}

local GUI_OBJECT_PROPERTIES = {
	"Active", "AnchorPoint", "AutomaticSize", "BackgroundColor3",
	"BackgroundTransparency", "BorderColor3", "BorderMode", "BorderSizePixel",
	"ClipsDescendants", "Interactable", "LayoutOrder", "Position", "Rotation",
	"Selectable", "SelectionOrder", "Size", "SizeConstraint", "Visible", "ZIndex",
}
local LAYER_COLLECTOR_PROPERTIES = {
	"Enabled", "ResetOnSpawn", "ZIndexBehavior",
}
local TEXT_PROPERTIES = {
	"Font", "FontFace", "LineHeight", "MaxVisibleGraphemes", "RichText", "Text", "TextColor3",
	"TextDirection", "TextScaled", "TextSize", "TextStrokeColor3",
	"TextStrokeTransparency", "TextTransparency", "TextTruncate", "TextWrapped",
	"TextXAlignment", "TextYAlignment",
}
local IMAGE_PROPERTIES = {
	"Image", "ImageColor3", "ImageRectOffset", "ImageRectSize", "ImageTransparency",
	"ResampleMode", "ScaleType", "SliceCenter", "SliceScale", "TileSize",
}
local BUTTON_PROPERTIES = {
	"AutoButtonColor", "Modal", "Selected", "Style",
}
local CLASS_PROPERTIES = {
	ScreenGui = { "ClipToDeviceSafeArea", "DisplayOrder", "IgnoreGuiInset", "SafeAreaCompatibility", "ScreenInsets" },
	SurfaceGui = { "Active", "AlwaysOnTop", "Brightness", "CanvasSize", "ClipsDescendants", "Face", "LightInfluence", "MaxDistance", "PixelsPerStud", "SizingMode", "ToolPunchThroughDistance", "ZOffset" },
	BillboardGui = { "Active", "AlwaysOnTop", "Brightness", "ClipsDescendants", "ExtentsOffset", "ExtentsOffsetWorldSpace", "LightInfluence", "MaxDistance", "Size", "SizeOffset", "StudsOffset", "StudsOffsetWorldSpace" },
	Frame = { "Style" },
	ScrollingFrame = { "AutomaticCanvasSize", "BottomImage", "CanvasPosition", "CanvasSize", "ElasticBehavior", "HorizontalScrollBarInset", "MidImage", "ScrollBarImageColor3", "ScrollBarImageTransparency", "ScrollBarThickness", "ScrollingDirection", "ScrollingEnabled", "TopImage", "VerticalScrollBarInset", "VerticalScrollBarPosition" },
	CanvasGroup = { "GroupColor3", "GroupTransparency" },
	TextBox = { "ClearTextOnFocus", "MultiLine", "PlaceholderColor3", "PlaceholderText", "ShowNativeInput", "TextEditable" },
	ViewportFrame = { "Ambient", "ImageColor3", "ImageTransparency", "LightColor", "LightDirection" },
	VideoFrame = { "Looped", "Playing", "TimePosition", "Video", "Volume" },
	UICorner = { "CornerRadius", "BottomLeftRadius", "BottomRightRadius", "TopLeftRadius", "TopRightRadius" },
	UIStroke = { "ApplyStrokeMode", "Color", "Enabled", "LineJoinMode", "Thickness", "Transparency" },
	UIPadding = { "PaddingBottom", "PaddingLeft", "PaddingRight", "PaddingTop" },
	UIListLayout = { "FillDirection", "HorizontalAlignment", "SortOrder", "VerticalAlignment", "Padding", "HorizontalFlex", "VerticalFlex", "ItemLineAlignment", "Wraps" },
	UIGridLayout = { "FillDirection", "FillDirectionMaxCells", "HorizontalAlignment", "SortOrder", "StartCorner", "VerticalAlignment", "CellPadding", "CellSize" },
	UIPageLayout = { "Animated", "Circular", "EasingDirection", "EasingStyle", "GamepadInputEnabled", "Padding", "ScrollWheelInputEnabled", "TouchInputEnabled", "TweenTime" },
	UITableLayout = { "FillEmptySpaceColumns", "FillEmptySpaceRows", "MajorAxis", "Padding" },
	UIAspectRatioConstraint = { "AspectRatio", "AspectType", "DominantAxis" },
	UISizeConstraint = { "MaxSize", "MinSize" },
	UITextSizeConstraint = { "MaxTextSize", "MinTextSize" },
	UIScale = { "Scale" },
	UIGradient = { "Color", "Enabled", "Offset", "Rotation", "Transparency" },
	UIFlexItem = { "FlexMode", "GrowRatio", "ItemLineAlignment", "ShrinkRatio" },
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
local widget = plugin:CreateDockWidgetPluginGuiAsync("AzureSlopWidget", widgetInfo)
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
subLabel.Text = "Run azureslop pull, push, or test"
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

local forceButton = Instance.new("TextButton")
forceButton.Size = UDim2.new(0.5, -18, 0, 32)
forceButton.Position = UDim2.new(0.5, 6, 1, -44)
forceButton.BackgroundColor3 = Color3.fromRGB(175, 75, 55)
forceButton.BorderSizePixel = 0
forceButton.Text = "Push anyway"
forceButton.TextColor3 = Color3.fromRGB(245, 245, 250)
forceButton.Font = Enum.Font.GothamBold
forceButton.TextSize = 10
forceButton.AutoButtonColor = true
forceButton.Active = false
forceButton.Visible = false
forceButton.Parent = root
local forceCorner = Instance.new("UICorner")
forceCorner.CornerRadius = UDim.new(0, 5)
forceCorner.Parent = forceButton

local forceArmed = false

local function setStatus(text, sub, color)
	statusLabel.Text = text
	subLabel.Text = sub or ""
	statusDot.BackgroundColor3 = color or Color3.fromRGB(100, 100, 110)
end

local function setButton(text, enabled)
	forceArmed = false
	forceButton.Active = false
	forceButton.Visible = false
	actionButton.Size = UDim2.new(1, -24, 0, 32)
	actionButton.TextSize = 12
	actionButton.Text = text
	actionButton.Active = enabled
	if enabled then
		actionButton.BackgroundColor3 = Color3.fromRGB(35, 120, 210)
	else
		actionButton.BackgroundColor3 = Color3.fromRGB(60, 60, 68)
	end
end

local function showConflictButtons(action)
	actionButton.Size = UDim2.new(0.5, -18, 0, 32)
	actionButton.TextSize = 10
	forceButton.Text = action == "pull" and "Pull anyway" or "Push anyway"
	forceButton.Active = true
	forceButton.Visible = true
end

-- ─── Instance mapping ───────────────────────────────────────────────────────

local function serializeValue(value)
	local valueType = typeof(value)
	if valueType == "string" or valueType == "number" or valueType == "boolean" then
		return value
	elseif valueType == "Color3" then
		return { ["$type"] = "Color3", r = value.R, g = value.G, b = value.B }
	elseif valueType == "Vector2" then
		return { ["$type"] = "Vector2", x = value.X, y = value.Y }
	elseif valueType == "Vector3" then
		return { ["$type"] = "Vector3", x = value.X, y = value.Y, z = value.Z }
	elseif valueType == "UDim" then
		return { ["$type"] = "UDim", scale = value.Scale, offset = value.Offset }
	elseif valueType == "UDim2" then
		return {
			["$type"] = "UDim2",
			x = { scale = value.X.Scale, offset = value.X.Offset },
			y = { scale = value.Y.Scale, offset = value.Y.Offset },
		}
	elseif valueType == "Rect" then
		return {
			["$type"] = "Rect",
			min = { x = value.Min.X, y = value.Min.Y },
			max = { x = value.Max.X, y = value.Max.Y },
		}
	elseif valueType == "EnumItem" then
		return {
			["$type"] = "Enum",
			enum = string.gsub(tostring(value.EnumType), "^Enum%.", ""),
			value = value.Name,
		}
	elseif valueType == "Font" then
		return {
			["$type"] = "Font",
			family = value.Family,
			weight = value.Weight.Name,
			style = value.Style.Name,
		}
	elseif valueType == "ColorSequence" then
		local keypoints = {}
		for _, keypoint in ipairs(value.Keypoints) do
			table.insert(keypoints, {
				time = keypoint.Time,
				value = serializeValue(keypoint.Value),
			})
		end
		return { ["$type"] = "ColorSequence", keypoints = keypoints }
	elseif valueType == "NumberSequence" then
		local keypoints = {}
		for _, keypoint in ipairs(value.Keypoints) do
			table.insert(keypoints, {
				time = keypoint.Time,
				value = keypoint.Value,
				envelope = keypoint.Envelope,
			})
		end
		return { ["$type"] = "NumberSequence", keypoints = keypoints }
	end
	return nil
end

local function deserializeValue(data)
	if type(data) ~= "table" then
		return data, true
	end
	local valueType = data["$type"]
	if valueType == "Color3" then
		return Color3.new(data.r, data.g, data.b), true
	elseif valueType == "Vector2" then
		return Vector2.new(data.x, data.y), true
	elseif valueType == "Vector3" then
		return Vector3.new(data.x, data.y, data.z), true
	elseif valueType == "UDim" then
		return UDim.new(data.scale, data.offset), true
	elseif valueType == "UDim2" then
		return UDim2.new(data.x.scale, data.x.offset, data.y.scale, data.y.offset), true
	elseif valueType == "Rect" then
		return Rect.new(data.min.x, data.min.y, data.max.x, data.max.y), true
	elseif valueType == "Enum" then
		local enumOk, enumValue = pcall(function()
			return Enum[data.enum][data.value]
		end)
		return enumValue, enumOk
	elseif valueType == "Font" then
		local fontOk, fontValue = pcall(function()
			return Font.new(data.family, Enum.FontWeight[data.weight], Enum.FontStyle[data.style])
		end)
		return fontValue, fontOk
	elseif valueType == "ColorSequence" then
		local keypoints = {}
		for _, keypoint in ipairs(data.keypoints or {}) do
			local color, colorOk = deserializeValue(keypoint.value)
			if not colorOk or typeof(color) ~= "Color3" then
				return nil, false
			end
			table.insert(keypoints, ColorSequenceKeypoint.new(keypoint.time, color))
		end
		return ColorSequence.new(keypoints), true
	elseif valueType == "NumberSequence" then
		local keypoints = {}
		for _, keypoint in ipairs(data.keypoints or {}) do
			table.insert(keypoints, NumberSequenceKeypoint.new(
				keypoint.time,
				keypoint.value,
				keypoint.envelope or 0
			))
		end
		return NumberSequence.new(keypoints), true
	end
	return nil, false
end

local function guiPropertyNames(instance)
	local names = {}
	local seen = {}
	local function add(properties)
		for _, propertyName in ipairs(properties or {}) do
			if not seen[propertyName] then
				seen[propertyName] = true
				table.insert(names, propertyName)
			end
		end
	end

	if instance:IsA("GuiObject") then
		add(GUI_OBJECT_PROPERTIES)
	end
	if instance:IsA("LayerCollector") then
		add(LAYER_COLLECTOR_PROPERTIES)
	end
	if instance:IsA("TextLabel") or instance:IsA("TextButton") or instance:IsA("TextBox") then
		add(TEXT_PROPERTIES)
	end
	if instance:IsA("ImageLabel") or instance:IsA("ImageButton") then
		add(IMAGE_PROPERTIES)
	end
	if instance:IsA("GuiButton") then
		add(BUTTON_PROPERTIES)
	end
	add(CLASS_PROPERTIES[instance.ClassName])
	return names
end

local function serializeGui(instance)
	local properties = {}
	for _, propertyName in ipairs(guiPropertyNames(instance)) do
		local readOk, value = pcall(function()
			return instance[propertyName]
		end)
		if readOk then
			local encoded = serializeValue(value)
			if encoded ~= nil then
				properties[propertyName] = encoded
			end
		end
	end
	return HttpService:JSONEncode({
		["$schema"] = "azureslop-gui/v1",
		className = instance.ClassName,
		properties = properties,
	})
end

local function applyGuiDocument(instance, source)
	local document = HttpService:JSONDecode(source)
	if type(document) ~= "table" or type(document.properties) ~= "table" then
		error("invalid GUI document")
	end
	if document.className ~= instance.ClassName then
		error("className is " .. tostring(document.className) .. ", but Studio has " .. instance.ClassName)
	end
	local allowed = {}
	for _, propertyName in ipairs(guiPropertyNames(instance)) do
		allowed[propertyName] = true
	end
	local pending = {}
	local originals = {}
	for propertyName, encoded in pairs(document.properties) do
		if not allowed[propertyName] then
			error("unsupported or non-writable GUI property " .. tostring(propertyName))
		end
		local value, valueOk = deserializeValue(encoded)
		if not valueOk then
			error(propertyName .. " has an unsupported value")
		end
		local readOk, original = pcall(function()
			return instance[propertyName]
		end)
		if not readOk then
			error("GUI property is unavailable in this Studio version: " .. propertyName)
		end
		originals[propertyName] = original
		table.insert(pending, { name = propertyName, value = value })
	end

	local applied = {}
	for _, property in ipairs(pending) do
		local writeOk, writeError = pcall(function()
			instance[property.name] = property.value
		end)
		if not writeOk then
			for _, appliedName in ipairs(applied) do
				pcall(function()
					instance[appliedName] = originals[appliedName]
				end)
			end
			error(property.name .. ": " .. tostring(writeError))
		end
		table.insert(applied, property.name)
	end
end

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
		or GUI_TYPES[instance.ClassName]
end

local function instanceKind(instance)
	if GUI_TYPES[instance.ClassName] then
		return "gui"
	end
	return "source"
end

local function entryKey(path, kind)
	return (kind or "source") .. ":" .. path
end

local function deletionPathAndKind(deletion)
	if type(deletion) == "table" then
		return deletion.path, deletion.kind or "source"
	end
	return deletion, "source"
end

local function deepEqual(left, right)
	if type(left) ~= type(right) then
		return false
	end
	if type(left) ~= "table" then
		return left == right
	end
	for key, value in pairs(left) do
		if not deepEqual(value, right[key]) then
			return false
		end
	end
	for key in pairs(right) do
		if left[key] == nil then
			return false
		end
	end
	return true
end

local function sourcesEqual(kind, left, right)
	if kind ~= "gui" then
		return left == right
	end
	local leftOk, leftDocument = pcall(function()
		return HttpService:JSONDecode(left)
	end)
	local rightOk, rightDocument = pcall(function()
		return HttpService:JSONDecode(right)
	end)
	return leftOk and rightOk and deepEqual(leftDocument, rightDocument)
end

local function collectAll(strict)
	local results = {}
	local ambiguous = {}
	for _, serviceName in ipairs(services) do
		local ok, service = pcall(function()
			return game:GetService(serviceName)
		end)
		if ok and service then
			local function recurse(instance)
				if instance:GetAttribute("AzureSlopPreview") == true then return end
				if isTracked(instance) then
					local source = ""
					local sourceOk = true
					local kind = instanceKind(instance)
					if kind == "gui" then
						sourceOk, source = pcall(function()
							return serializeGui(instance)
						end)
					elseif instance:IsA("LuaSourceContainer") then
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
						local key = entryKey(path, kind)
						if results[key] and (
							results[key].type ~= instance.ClassName
							or not sourcesEqual(kind, results[key].source, source)
						) then
							warn("[AzureSlop] Multiple instances at " .. path .. " have different values; the last one will be pulled")
							ambiguous[key] = { path = path, kind = kind }
						end
						results[key] = {
							path = path,
							source = source,
							type = instance.ClassName,
							kind = kind,
						}
					else
						if strict then
							error("Incomplete snapshot: could not read " .. getInstancePath(instance) .. ": " .. tostring(source))
						end
						warn("[AzureSlop] Could not read " .. getInstancePath(instance) .. ": " .. tostring(source))
					end
				end
				for _, child in ipairs(instance:GetChildren()) do
					recurse(child)
				end
			end
			recurse(service)
		elseif strict then
			error("Incomplete snapshot: unavailable service " .. serviceName)
		end
	end

	local snapshot = {}
	for _, entry in pairs(results) do
		table.insert(snapshot, entry)
	end
	return snapshot, ambiguous
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
					local key = entryKey(path, instanceKind(instance))
					instanceMap[key] = instanceMap[key] or {}
					table.insert(instanceMap[key], instance)
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

local function applyChanges(changes, deletions, allowStructuralChanges)
	local instanceMap = buildInstanceMap()
	local stats = { updated = 0, created = 0, deleted = 0, unchanged = 0, skipped = 0, errors = {} }

	for _, change in ipairs(changes) do
		local kind = change.kind or "source"
		local key = entryKey(change.path, kind)
		local instances = instanceMap[key]
		local createdForChange = false
		if not instances or #instances == 0 then
			if allowStructuralChanges then
				local instance, createError = createInstance(change)
				if instance then
					instances = { instance }
					instanceMap[key] = instances
					stats.created = stats.created + 1
					createdForChange = true
				else
					table.insert(stats.errors, createError)
					stats.skipped = stats.skipped + 1
				end
			else
				stats.skipped = stats.skipped + 1
				table.insert(stats.errors, "no existing script for " .. change.path)
			end
		end
		local function discardCreated(instance)
			if createdForChange then
				pcall(function()
					instance:Destroy()
				end)
				stats.created = stats.created - 1
				createdForChange = false
				instanceMap[key] = nil
			end
		end

		if instances then
			for _, instance in ipairs(instances) do
				if instance.ClassName ~= change.type then
					stats.skipped = stats.skipped + 1
					table.insert(
						stats.errors,
						change.path .. ": class change from " .. instance.ClassName
							.. " to " .. tostring(change.type) .. " is not supported"
					)
				elseif kind == "gui" and allowStructuralChanges then
					local guiOk, guiError = pcall(function()
						applyGuiDocument(instance, change.source or "")
					end)
					if guiOk then
						stats.updated = stats.updated + 1
					else
						stats.skipped = stats.skipped + 1
						table.insert(stats.errors, change.path .. ": " .. tostring(guiError))
						discardCreated(instance)
					end
				elseif kind == "gui" then
					stats.skipped = stats.skipped + 1
					table.insert(stats.errors, "GUI changes are not draftable: " .. change.path)
				elseif instance:IsA("LuaSourceContainer") then
					local readOk, editorSource = pcall(function()
						return ScriptEditorService:GetEditorSource(instance)
					end)
					if readOk and editorSource == (change.source or "") then
						stats.unchanged = stats.unchanged + 1
					else
						local updateOk, updateError = pcall(function()
							ScriptEditorService:UpdateSourceAsync(instance, function()
								return change.source or ""
							end)
						end)
						if updateOk then
							stats.updated = stats.updated + 1
						else
							stats.skipped = stats.skipped + 1
							table.insert(stats.errors, change.path .. ": " .. tostring(updateError))
							discardCreated(instance)
						end
					end
				elseif allowStructuralChanges then
					local valueOk, valueError = pcall(function()
						applyValue(instance, change.source or "")
					end)
					if valueOk then
						stats.updated = stats.updated + 1
					else
						stats.skipped = stats.skipped + 1
						table.insert(stats.errors, change.path .. ": " .. tostring(valueError))
						discardCreated(instance)
					end
				else
					-- Value and event changes are not drafts; do not mutate the shared place.
					stats.skipped = stats.skipped + 1
				end
			end
		end
	end

	for _, deletion in ipairs(deletions) do
		local path, kind = deletionPathAndKind(deletion)
		local instances = instanceMap[entryKey(path, kind)]
		if allowStructuralChanges and instances then
			for _, instance in ipairs(instances) do
				local deleteOk, deleteError = pcall(function()
					instance:Destroy()
				end)
				if deleteOk then
					stats.deleted = stats.deleted + 1
				else
					table.insert(stats.errors, path .. ": " .. tostring(deleteError))
				end
			end
		elseif instances then
			stats.skipped = stats.skipped + #instances
			table.insert(stats.errors, "deletion is not draftable: " .. path)
		end
	end

	return stats
end

local function collectCurrentForOperations(changes, deletions)
	local needed = {}
	for _, change in ipairs(changes) do
		needed[entryKey(change.path, change.kind or "source")] = true
	end
	for _, deletion in ipairs(deletions) do
		local path, kind = deletionPathAndKind(deletion)
		needed[entryKey(path, kind)] = true
	end

	local current = {}
	local allEntries, allAmbiguous = collectAll()
	for _, entry in ipairs(allEntries) do
		if needed[entryKey(entry.path, entry.kind)] then
			table.insert(current, entry)
		end
	end
	local ambiguous = {}
	for key, entry in pairs(allAmbiguous) do
		if needed[key] then
			table.insert(ambiguous, entry)
		end
	end
	return current, ambiguous
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

local function postRaw(path, data)
	return HttpService:PostAsync(
		serverUrl() .. path,
		data,
		Enum.HttpContentType.TextPlain,
		false
	)
end

local function uploadPullSnapshot(snapshot, ambiguous, session)
	local encoded = HttpService:JSONEncode({ changes = snapshot, ambiguous = ambiguous })
	local total = math.max(1, math.ceil(#encoded / PULL_CHUNK_SIZE))
	local encodedSession = HttpService:UrlEncode(session)
	for index = 1, total do
		local firstByte = ((index - 1) * PULL_CHUNK_SIZE) + 1
		local lastByte = math.min(index * PULL_CHUNK_SIZE, #encoded)
		local chunk = string.sub(encoded, firstByte, lastByte)
		setStatus(
			"Pulling",
			string.format("Sending batch %d of %d", index, total),
			Color3.fromRGB(230, 170, 45)
		)
		postRaw(
			string.format(
				"/pull/chunk?session=%s&index=%d&total=%d",
				encodedSession,
				index,
				total
			),
			chunk
		)
	end
	local completion = HttpService:JSONDecode(postJson("/pull/complete", {
		session = session,
		total = total,
	}))
	return total, #encoded, completion
end

-- ─── Agent harness (no pairing token; enabled explicitly in this window) ───
local Harness = { enabled = false, busy = false, pending = nil, generation = 0 }
do
	local History = game:GetService("ChangeHistoryService")
	local Selection = game:GetService("Selection")
	local RunService = game:GetService("RunService")
	local LogService = game:GetService("LogService")
	local refs = setmetatable({}, { __mode = "v" })
	local ids = setmetatable({}, { __mode = "k" })
	local logs = {}
	local logIndex = 0
	local logConnection = LogService.MessageOut:Connect(function(message, messageType)
		logIndex = logIndex + 1
		table.insert(logs, { id = logIndex, message = string.sub(message, 1, 8000),
			level = messageType.Name, time = os.time() })
		if #logs > 200 then table.remove(logs, 1) end
	end)

	local function describe(obj)
		if not ids[obj] then
			ids[obj] = HttpService:GenerateGUID(false)
			refs[ids[obj]] = obj
		end
		return { id = ids[obj], name = obj.Name, class = obj.ClassName, path = obj:GetFullName() }
	end

	local function resolve(ref)
		assert(type(ref) == "table", "Use {id=...} or a path array such as [Workspace, Part]")
		if ref.id then
			local obj = refs[ref.id]
			assert(obj and (obj == game or obj:IsDescendantOf(game)), "Instance ID is stale; inspect again")
			return obj
		end
		for key, name in pairs(ref) do
			assert(type(key) == "number" and key % 1 == 0 and key >= 1 and key <= #ref
				and type(name) == "string", "Expected an array of exact instance names")
		end
		local obj = game
		for _, name in ipairs(ref) do
			local match = nil
			for _, child in ipairs(obj:GetChildren()) do
				if child.Name == name then
					assert(not match, "Ambiguous path; inspect the parent tree and use an instance ID")
					match = child
				end
			end
			assert(match, "Path segment not found: " .. name)
			obj = match
		end
		return obj
	end

	local function encode(value, depth, seen)
		depth, seen = depth or 0, seen or {}
		assert(depth <= 32, "Result nesting exceeds 32 levels")
		local kind = typeof(value)
		if kind == "Instance" then return describe(value) end
		if kind == "CFrame" then return { ["$type"] = "CFrame", components = { value:GetComponents() } } end
		if kind == "number" then
			assert(value == value and math.abs(value) ~= math.huge, "Result contains a non-finite number")
		end
		if kind == "table" then
			assert(not seen[value], "Result contains a table cycle")
			seen[value] = true
			local result = {}
			for key, item in pairs(value) do result[key] = encode(item, depth + 1, seen) end
			seen[value] = nil
			return result
		end
		local serialized = serializeValue(value)
		if serialized ~= nil then return serialized end
		return value ~= nil and tostring(value) or nil
	end

	local function decode(value)
		if type(value) == "table" and value["$type"] == "Instance" then return resolve(value.target) end
		if type(value) == "table" and value["$type"] == "CFrame" then
			return CFrame.new(table.unpack(value.components))
		end
		local decoded, ok = deserializeValue(value)
		assert(ok, "Unsupported property value; use AzureSlop $type encoding")
		return decoded
	end

	local function properties(obj, values)
		for key, value in pairs(values or {}) do
			assert(key ~= "Source" and key ~= "Parent", "Use write_source or the parent parameter")
			obj[key] = decode(value)
		end
	end

	local handlers = {}
	local preview
	local runStateConnection
	local previewMethods = {
		"preview_start", "preview_status", "preview_seek", "preview_step", "preview_camera",
		"preview_capture", "preview_keyframes", "preview_edit", "preview_undo", "preview_export",
		"preview_diagnose", "preview_stop", "vision_capabilities", "vision_permission", "viewport_capture",
	}
	for _, method in ipairs(previewMethods) do
		handlers[method] = function(p)
			if not preview then
				local module = assert(script:FindFirstChild("HarnessPreview"), "Reinstall the packaged AzureSlop.rbxmx; preview modules are missing")
				preview = require(module)({ resolve = resolve, describe = describe, decode = decode,
					isEnabled = function() return Harness.enabled end })
			end
			return preview.handlers[method](p)
		end
	end
	handlers.ping = function()
		return { place = game.Name, placeId = tostring(game.PlaceId), running = RunService:IsRunning(),
			protocol = 2, services = services, previewMethods = previewMethods }
	end
	handlers.tree = function(p)
		local maxDepth = math.clamp(tonumber(p.depth) or 2, 0, 8)
		local limit = math.clamp(tonumber(p.limit) or 200, 1, 2000)
		local count, truncated = 0, false
		local function visit(obj, depth)
			count = count + 1
			local out = describe(obj)
			local children = obj:GetChildren()
			out.childCount = #children
			out.children = {}
			if depth < maxDepth then
				for _, child in ipairs(children) do
					if count >= limit then truncated = true break end
					table.insert(out.children, visit(child, depth + 1))
				end
			elseif #children > 0 then
				truncated = true
			end
			return out
		end
		local tree = visit(resolve(p.target or { "Workspace" }), 0)
		return { tree = tree, count = count, truncated = truncated }
	end
	handlers.get = function(p)
		local obj = resolve(p.target)
		local result = describe(obj)
		result.properties = {}
		for _, key in ipairs(p.properties or { "Name", "ClassName", "Parent" }) do
			assert(key ~= "Source", "Use read_source")
			local ok, value = pcall(function() return encode(obj[key]) end)
			if ok then result.properties[key] = value
			else result.properties[key] = { error = tostring(value) } end
		end
		result.attributes = encode(obj:GetAttributes())
		return result
	end
	handlers.selection = function(p)
		if p.targets then
			local selected = {}
			for _, ref in ipairs(p.targets) do table.insert(selected, resolve(ref)) end
			Selection:Set(selected)
		end
		local result = {}
		for _, obj in ipairs(Selection:Get()) do table.insert(result, describe(obj)) end
		return result
	end
	handlers.create = function(p)
		local parent = resolve(p.parent or { "Workspace" })
		local obj = Instance.new(p.class or "Part")
		local ok, err = pcall(function()
			obj.Name = p.name or obj.ClassName
			properties(obj, p.properties)
			obj.Parent = parent
		end)
		if not ok then obj:Destroy() error(err) end
		return describe(obj)
	end
	handlers.set = function(p)
		local obj = resolve(p.target)
		properties(obj, p.properties)
		if p.parent then
			assert(obj ~= game and obj.Parent ~= game, "Cannot reparent root services")
			obj.Parent = resolve(p.parent)
		end
		for key, value in pairs(p.attributes or {}) do obj:SetAttribute(key, decode(value)) end
		return describe(obj)
	end
	handlers.delete = function(p)
		local obj = resolve(p.target)
		assert(obj ~= game and obj.Parent ~= game, "Cannot delete root services")
		local result = describe(obj)
		obj.Parent = nil -- detach so Studio Undo can restore it
		return result
	end
	handlers.read_source = function(p)
		local obj = resolve(p.target)
		assert(obj:IsA("LuaSourceContainer"), "Target must be a script")
		return { instance = describe(obj), source = ScriptEditorService:GetEditorSource(obj) }
	end
	handlers.write_source = function(p)
		local obj = resolve(p.target)
		assert(obj:IsA("LuaSourceContainer") and type(p.source) == "string", "Expected script and source")
		ScriptEditorService:UpdateSourceAsync(obj, function(old)
			if p.expected ~= nil then assert(old == p.expected, "Source changed; read it again before editing") end
			return p.source
		end)
		return { instance = describe(obj), bytes = #p.source }
	end
	handlers.execute = function(p)
		assert(type(p.source) == "string", "Expected Luau source")
		local temp = Instance.new("ModuleScript")
		temp.Name = "AzureSlopCommand_" .. HttpService:GenerateGUID(false)
		temp.Parent = script
		local ok, result = pcall(function()
			ScriptEditorService:UpdateSourceAsync(temp, function()
				return "return function(context)\n" .. p.source .. "\nend"
			end)
			return require(temp)({ resolve = resolve, selection = Selection:Get() })
		end)
		temp:Destroy()
		if not ok then error(result) end
		return result
	end
	handlers.logs = function(p)
		local result = {}
		for _, entry in ipairs(logs) do
			if entry.id > (tonumber(p.after) or 0) then table.insert(result, entry) end
		end
		return { entries = result, cursor = logIndex }
	end
	handlers.snapshot = function()
		assert(not RunService:IsRunning(), "Stop Play/Run before taking a disk snapshot")
		local changes, ambiguousMap = collectAll(true)
		local ambiguous = {}
		for _, entry in pairs(ambiguousMap) do table.insert(ambiguous, entry) end
		return { changes = changes, ambiguous = ambiguous }
	end
	local mutations = { create = true, set = true, delete = true, write_source = true, execute = true, preview_export = true }
	local function run(job)
		local handler = handlers[job.method]
		assert(handler, "Unknown command")
		local recording
		if mutations[job.method] then
			assert(not RunService:IsRunning(), "Stop Play/Run before editing")
			recording = History:TryBeginRecording("AzureSlop_" .. job.id, "AzureSlop: " .. job.method)
			assert(recording, "Studio could not begin an undo recording")
		end
		local ok, result = pcall(handler, job.params)
		if recording then
			-- Failed commands can leave partial edits; commit the undo record too.
			History:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
		end
		if ok then return { ok = true, value = encode(result) } end
		return { ok = false, error = tostring(result), partialEditsPossible = recording ~= nil }
	end

	local function request(endpoint, path, data, raw)
		local response = HttpService:RequestAsync({
			Url = endpoint .. path, Method = "POST",
			Headers = { ["Content-Type"] = raw and "text/plain" or "application/json" },
			Body = raw and data or HttpService:JSONEncode(data),
		})
		if response.StatusCode == 400 then
			-- The backend has forgotten this epoch/job or rejected the protocol.
			-- Do not keep retrying a result against an unrelated server forever.
			Harness.enabled = false
			Harness.pending = nil
			Harness.generation = Harness.generation + 1
			if preview then preview.cleanup() end
		end
		assert(response.Success, "Harness HTTP " .. response.StatusCode .. ": " .. response.Body)
		return HttpService:JSONDecode(response.Body)
	end

	function Harness.disable()
		Harness.enabled = false
		Harness.generation = Harness.generation + 1
		if preview then preview.cleanup() end
		local endpoint, epoch, session = Harness.endpoint, Harness.epoch, Harness.session
		if endpoint then
			task.spawn(function()
				pcall(request, endpoint, "/harness/disconnect", { epoch = epoch, session = session })
			end)
		end
	end
	function Harness.enable(config)
		assert(not Harness.busy and not Harness.pending, "Previous command is still finishing; wait for its result")
		Harness.endpoint = serverUrl()
		Harness.epoch = config.session
		Harness.session = HttpService:GenerateGUID(false)
		Harness.generation = Harness.generation + 1
		Harness.enabled = true
	end
	function Harness.tick()
		if Harness.pending then
			local pending = Harness.pending
			while pending.index <= pending.total do
				local chunk = string.sub(pending.encoded, (pending.index - 1) * PULL_CHUNK_SIZE + 1,
					pending.index * PULL_CHUNK_SIZE)
				request(pending.endpoint, string.format(
					"/harness/result/chunk?epoch=%s&session=%s&id=%s&index=%d&total=%d",
					pending.epoch, pending.session, pending.id, pending.index, pending.total), chunk, true)
				pending.index = pending.index + 1
			end
			request(pending.endpoint, "/harness/result/complete", {
				epoch = pending.epoch, session = pending.session, id = pending.id,
			})
			Harness.pending = nil
		end
		if not Harness.enabled then return end
		local generation = Harness.generation
		local endpoint, epoch, session = Harness.endpoint, Harness.epoch, Harness.session
		local response = request(endpoint, "/harness/poll", {
			epoch = epoch, session = session, place = game.Name, placeId = tostring(game.PlaceId),
		})
		if generation == Harness.generation then
			setStatus("Harness connected", game.Name .. " • " .. string.sub(session, 1, 8), Color3.fromRGB(30, 200, 100))
			setButton("Disable harness", true)
		end
		if response.job then
			local job = response.job
			Harness.busy = true
			task.spawn(function()
				local result
				if generation ~= Harness.generation or not Harness.enabled then
					result = { ok = false, error = "Harness disabled before execution" }
				else
					local ok, value = pcall(run, job)
					result = ok and value or { ok = false, error = tostring(value), partialEditsPossible = true }
				end
				local ok, encoded = pcall(function() return HttpService:JSONEncode(result) end)
				if not ok or #encoded > PULL_CHUNK_SIZE * 64 then
					encoded = HttpService:JSONEncode({ ok = false,
						error = "Result exceeds JSON/batch limits; edits may have completed" })
				end
				Harness.pending = { encoded = encoded, index = 1, total = math.max(1, math.ceil(#encoded / PULL_CHUNK_SIZE)),
					endpoint = endpoint, epoch = epoch, session = session, id = job.id }
				Harness.busy = false
			end)
		end
	end
	plugin.Unloading:Connect(function()
		Harness.disable()
		logConnection:Disconnect()
		if runStateConnection then runStateConnection:Disconnect() end
		active = false
	end)
	-- Feature-detected for older Studio versions and the minimal protocol mocks.
	pcall(function()
		runStateConnection = RunService:GetPropertyChangedSignal("RunState"):Connect(function()
			if RunService:IsRunning() and preview then preview.cleanup() end
		end)
	end)
end

local function runPendingAction()
	local config = pendingConfig
	if not config then
		return
	end
	if config.action == "harness" then
		if Harness.enabled then
			Harness.disable()
			setStatus("Harness disabled", "Click Enable harness to accept agent commands", Color3.fromRGB(100, 100, 110))
			setButton("Enable harness", true)
		else
			Harness.enable(config)
			setStatus("Harness connecting", "Agent commands have plugin access to this place", Color3.fromRGB(230, 170, 45))
			setButton("Disable harness", true)
		end
		return
	end
	conflictSession = nil
	setButton("Working...", false)
	setStatus("Working", "Keep this Studio window open", Color3.fromRGB(230, 170, 45))

	if config.action == "pull" then
		local snapshot, ambiguousMap = collectAll()
		local ambiguous = {}
		for _, entry in pairs(ambiguousMap) do
			table.insert(ambiguous, entry)
		end
		local batchCount, byteCount, completion = uploadPullSnapshot(snapshot, ambiguous, config.session)
		if completion.ok == false then
			local conflictCount = #(completion.conflicts or {})
			conflictSession = config.session
			setStatus(
				"Pull blocked",
				string.format("%d conflict(s); resolve a side, then retry", conflictCount),
				Color3.fromRGB(190, 60, 60)
			)
			setButton("Apply resolution", true)
			showConflictButtons(config.action)
			return
		end
		completedSession = config.session
		pendingConfig = nil
		setStatus(
			"Pull complete",
			string.format("Sent %d instance(s), %d bytes in %d batch(es)", #snapshot, byteCount, batchCount),
			Color3.fromRGB(30, 200, 100)
		)
		setButton("Complete", false)
		return
	end

	if config.action == "push" or config.action == "test" then
		local response = HttpService:GetAsync(serverUrl() .. "/changes", false)
		local data = HttpService:JSONDecode(response)
		if data.error then
			error(data.error)
		end
		local changes = data.changes
		if type(changes) ~= "table" then
			changes = {}
		end
		local deletions = data.deletions
		if type(deletions) ~= "table" then
			deletions = {}
		end
		if not (config.action == "test" and config["local"] == true) then
			local current, ambiguous = collectCurrentForOperations(changes, deletions)
			local comparison = HttpService:JSONDecode(postJson("/compare", {
				session = config.session,
				current = current,
				ambiguous = ambiguous,
			}))
			if comparison.ok == false then
				conflictSession = config.session
				setStatus(
					"Version conflict",
					string.format("%d path(s); resolve a side, then retry", #(comparison.conflicts or {})),
					Color3.fromRGB(190, 60, 60)
				)
				setButton("Apply resolution", true)
				showConflictButtons(config.action)
				return
			end
			if type(comparison.changes) == "table" then
				changes = comparison.changes
			end
			if type(comparison.deletions) == "table" then
				deletions = comparison.deletions
			end
		end
		local allowStructuralChanges = config.action == "push" or config["local"] == true
		local stats = applyChanges(changes, deletions, allowStructuralChanges)
		stats.session = config.session
		postJson("/complete", stats)
		completedSession = config.session
		pendingConfig = nil
		local completedTitle = "Test ready"
		if config.action == "push" then
			completedTitle = "Push complete"
		end
		setStatus(
			completedTitle,
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
		if pendingConfig then
			conflictSession = pendingConfig.session
		end
		warn("[AzureSlop] Action failed: " .. tostring(actionError))
		setStatus("Action failed", tostring(actionError), Color3.fromRGB(190, 60, 60))
		setButton("Retry", true)
	end
end)

forceButton.Activated:Connect(function()
	if not pendingConfig then
		return
	end
	if not forceArmed then
		forceArmed = true
		forceButton.Text = pendingConfig.action == "pull"
			and "Confirm pull"
			or "Confirm push"
		setStatus(
			"Confirm overwrite",
			pendingConfig.action == "pull"
				and "Studio wins every conflict; click again to confirm"
				or "Disk wins every conflict; click again to confirm",
			Color3.fromRGB(210, 110, 55)
		)
		return
	end

	local ok, forceError = pcall(function()
		local response = HttpService:JSONDecode(postJson("/force", {
			session = pendingConfig.session,
		}))
		if response.ok == false or response.error then
			error(response.error or "the resolution override was rejected")
		end
		runPendingAction()
	end)
	if not ok then
		warn("[AzureSlop] Force action failed: " .. tostring(forceError))
		if pendingConfig then
			conflictSession = pendingConfig.session
		end
		setStatus("Override failed", tostring(forceError), Color3.fromRGB(190, 60, 60))
		setButton("Apply resolution", true)
		showConflictButtons(pendingConfig and pendingConfig.action or "push")
	end
end)

local function checkForAction()
	if Harness.enabled or Harness.busy or Harness.pending then
		Harness.tick()
		return
	end
	local response = HttpService:GetAsync(serverUrl() .. "/config", false)
	if not active then return end
	local config = HttpService:JSONDecode(response)
	services = config.services or services

	if config.session == completedSession or config.session == conflictSession then
		return
	end
	pendingConfig = config
	if config.action == "harness" then
		setStatus("Harness available", "Enable agent access to this Studio window • " .. (config.name or "AzureSlop"), Color3.fromRGB(35, 140, 230))
		setButton("Enable harness", true)
	elseif config.action == "pull" then
		setStatus("Pull requested", config.name or "AzureSlop project", Color3.fromRGB(35, 140, 230))
		setButton("Pull into disk", true)
	elseif config.action == "push" then
		setStatus("Push requested", "Creates, updates, and applies tracked deletions", Color3.fromRGB(35, 140, 230))
		setButton("Push into Studio", true)
	elseif config.action == "test" and config["local"] then
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
	-- Closing/reopening while GetAsync yields must not spawn another poller.
	if polling then return end
	polling = true
	task.spawn(function()
		while active do
			local ok, pollError = pcall(checkForAction)
			if not active then break end
			if not ok and Harness.enabled then
				setStatus("Harness reconnecting", string.sub(tostring(pollError), 1, 200), Color3.fromRGB(230, 170, 45))
			elseif not ok and not completedSession then
				pendingConfig = nil
				setStatus("Not connected", "Run azureslop pull, push, or test", Color3.fromRGB(150, 70, 70))
				setButton("Waiting for command...", false)
			end
			task.wait(POLL_INTERVAL)
		end
		polling = false
	end)
end

local function stopPolling()
	Harness.disable()
	active = false
	pendingConfig = nil
	completedSession = nil
	conflictSession = nil
	setStatus("Not connected", "Open the panel to look for a command", Color3.fromRGB(100, 100, 110))
	setButton("Waiting for command...", false)
end

toggleBtn.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

widget:GetPropertyChangedSignal("Enabled"):Connect(function()
	if widget.Enabled then
		startPolling()
	else
		stopPolling()
	end
end)

if widget.Enabled then startPolling() end

print("[AzureSlop] Plugin loaded. Click AzureSlop in the toolbar to connect.")
