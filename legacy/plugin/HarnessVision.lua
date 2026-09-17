-- Native Studio viewport capture only; no desktop capture or external upload.
local Vision = {}
local lastFailure
local captureVerified = false
local function failure(stage, err)
 local raw=tostring(err)
 local lower=string.lower(raw)
 local unsupported=string.find(lower,"feature not supported",1,true) or string.find(lower,"not implemented",1,true)
  or string.find(lower,"studiocaptureservice not available",1,true) or string.find(lower,"not a valid member",1,true)
 local code=unsupported and "unsupported" or "api_error"
 lastFailure={stage=stage,code=code,raw=raw}
 return "[vision."..code.."] "..stage..": "..raw..(unsupported and
  ". This Studio build/platform exposes an unavailable API. Retrying permission will not enable it; no screenshot was captured."
  or ". Check the active Studio viewport and screenshot settings.")
end
local alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
function Vision.base64(data)
 local out = {}
 for i=1,#data,3 do
  local a,b,c = string.byte(data,i,i+2)
  local n = a*65536+(b or 0)*256+(c or 0)
  out[#out+1] = string.sub(alphabet,math.floor(n/262144)%64+1,math.floor(n/262144)%64+1)
   ..string.sub(alphabet,math.floor(n/4096)%64+1,math.floor(n/4096)%64+1)
   ..(b and string.sub(alphabet,math.floor(n/64)%64+1,math.floor(n/64)%64+1) or "=")
   ..(c and string.sub(alphabet,n%64+1,n%64+1) or "=")
 end
 return table.concat(out)
end
local function service()
 local ok,s = pcall(function() return game:GetService("StudioCaptureService") end)
 if not ok or not s then error(failure("GetService", "StudioCaptureService not available: "..tostring(s)),0) end
 return s
end
function Vision.capabilities()
 local got,s=pcall(service)
 local ok,result=false,nil
 if got then ok,result=pcall(function() return s:CanCaptureScreenshot() end) end
 if got and not ok then failure("CanCaptureScreenshot",result) end
 local blocked=lastFailure and lastFailure.code=="unsupported"
 local available=ok and result==true and not blocked
 return { servicePresent=got, querySucceeded=ok, nativeViewportCapture=available==true,
  canCaptureNow=available==true, captureVerified=captureVerified,
  status=blocked and "unsupported" or (not ok and "api_error" or (available and (captureVerified and "ready" or "ready_unverified") or "unavailable")),
  reason=blocked and "Native capture is unsupported in this Studio session; permission retries will not fix it."
   or (not ok and tostring(result or s) or (not available and "CanCaptureScreenshot returned false: permission, inactive viewport, or unsupported build; support is not established." or nil)),
  lastFailure=lastFailure, permissionCommand=not blocked and "vision_permission" or nil }
end
function Vision.permission()
 assert(not lastFailure or lastFailure.code~="unsupported",
  "[vision.unsupported] Native capture already reported unsupported in this Studio session; permission was not requested again")
 local s=service()
 local ok,result=pcall(function() return s:RequestScreenshotPermissionAsync() end)
 if not ok then error(failure("RequestScreenshotPermissionAsync",result),0) end
 if result==true then lastFailure=nil end
 return { granted=result==true, status=result==true and "granted" or "denied_or_disabled" }
end
function Vision.preflight()
 local report=Vision.capabilities()
 assert(report.canCaptureNow,"[vision."..report.status.."] "..tostring(report.reason))
 return report
end
function Vision.capture(p, cancelled)
 local w,h = p.width or 512,p.height or 512
 assert(type(w)=="number" and w%1==0 and w>=64 and w<=1024, "width must be an integer 64..1024")
 assert(type(h)=="number" and h%1==0 and h>=64 and h<=1024, "height must be an integer 64..1024")
 Vision.preflight()
 local s = service()
 local camera = assert(workspace.CurrentCamera,"No viewport camera")
 local size = camera.ViewportSize
 assert(size.X>0 and size.Y>0,"Studio viewport has zero size")
 -- Center crop to output aspect ratio instead of stretching posture measurements.
 local cw,ch = size.X,size.Y
 if cw/ch > w/h then cw=math.floor(ch*w/h) else ch=math.floor(cw*h/w) end
 local started,capture = pcall(function() return s:CaptureScreenshot({ Position=Vector2.new(math.floor((size.X-cw)/2),math.floor((size.Y-ch)/2)),
  CaptureSize=Vector2.new(cw,ch), OutputSize=Vector2.new(w,h), ResampleMode=Enum.ResamplerMode.Default,
  Format=Enum.StudioCaptureScreenshotFormat.RGBA8, UICaptureMode=Enum.UICaptureMode.None }) end)
 if not started then error(failure("CaptureScreenshot",capture),0) end
 local ok,result = pcall(function()
  local deadline = os.clock()+15
  while capture.BufferStatus ~= Enum.StudioCaptureBufferStatus.Ready do
   assert(not cancelled or not cancelled(),"Preview cancelled during capture")
   assert(capture.BufferStatus ~= Enum.StudioCaptureBufferStatus.Error,table.concat(capture:GetErrors(),"; "))
   assert(os.clock()<deadline,"Viewport capture timed out")
   task.wait(.03)
  end
  assert(not cancelled or not cancelled(),"Preview cancelled during capture")
  assert(capture.Resolution.X==w and capture.Resolution.Y==h,"Unexpected capture resolution")
  assert(capture.BufferFormat==Enum.StudioCaptureScreenshotFormat.RGBA8,"Unexpected capture format")
  local data = buffer.tostring(capture:GetBuffer())
  assert(#data==w*h*4,"Invalid RGBA viewport buffer length")
  return { format="rgba8", encoding="base64", width=w, height=h, data=Vision.base64(data),
   source="StudioCaptureService", uiIncluded=false }
 end)
 capture:Destroy()
 if not ok then error(failure("ReadCapture",result),0) end
 captureVerified=true; lastFailure=nil
 return result
end
return Vision
