local Vision=dofile("plugin/HarnessVision.lua")
for _,v in ipairs({{"",""},{"f","Zg=="},{"fo","Zm8="},{"foo","Zm9v"},{"\0\255\128","AP+A"}}) do assert(Vision.base64(v[1])==v[2]) end
local capture, options, ready, denied, fail, cancelled
local size={X=800,Y=600}
local service={CanCaptureScreenshot=function() return not denied end,
 RequestScreenshotPermissionAsync=function() return not denied end,
 CaptureScreenshot=function(_,p)
  options=p
  capture={BufferStatus=fail and "Error" or "Ready",BufferFormat="RGBA8",Resolution={X=p.OutputSize.X,Y=p.OutputSize.Y},
   GetBuffer=function() return string.rep("\0",p.OutputSize.X*p.OutputSize.Y*4) end,
   GetErrors=function() return {"test capture failed"} end,Destroy=function(self) self.destroyed=true end}
  return capture
 end}
game={GetService=function() return service end}
workspace={CurrentCamera={ViewportSize=size}}
Enum={ResamplerMode={Default="Default"},StudioCaptureScreenshotFormat={RGBA8="RGBA8"},UICaptureMode={None="None"},StudioCaptureBufferStatus={Ready="Ready",Error="Error"}}
Vector2={new=function(x,y) return {X=x,Y=y} end}
buffer={tostring=function(s) return s end}
local image=Vision.capture({width=64,height=64})
assert(image.width==64 and image.format=="rgba8" and capture.destroyed)
assert(options.Position.X==100 and options.CaptureSize.X==600 and options.UICaptureMode=="None")
fail=true
assert(not pcall(Vision.capture,{width=64,height=64}) and capture.destroyed)
fail=false
assert(not pcall(Vision.capture,{width=64,height=64},function() return true end) and capture.destroyed)
denied=true
assert(not Vision.permission().granted and not Vision.capabilities().canCaptureNow)
assert(not Vision.capabilities().nativeViewportCapture,"A false query result is not native capture support")
assert(not pcall(Vision.capture,{width=64,height=64}))
assert(not pcall(Vision.capture,{width=0,height=64}))
-- The API can exist and query false yet throw an unsupported-feature error on permission.
local permissionCalls=0
local originalPermission=service.RequestScreenshotPermissionAsync
service.RequestScreenshotPermissionAsync=function() permissionCalls=permissionCalls+1; error("Feature not supported yet") end
local fresh=dofile("plugin/HarnessVision.lua")
local ok,err=pcall(fresh.permission)
assert(not ok and err:find("vision.unsupported",1,true))
local report=fresh.capabilities()
assert(report.servicePresent and report.querySucceeded and report.status=="unsupported")
assert(not report.nativeViewportCapture and not report.permissionCommand)
assert(not pcall(fresh.permission) and permissionCalls==1,"Do not repeat unsupported permission requests")
denied=false
assert(not fresh.capabilities().canCaptureNow,"A later true query does not erase an observed unsupported failure")
assert(not pcall(fresh.capture,{width=64,height=64}))
service.RequestScreenshotPermissionAsync=originalPermission
local unverified=dofile("plugin/HarnessVision.lua")
assert(unverified.capabilities().status=="ready_unverified" and not unverified.capabilities().captureVerified)
unverified.capture({width=64,height=64})
assert(unverified.capabilities().status=="ready" and unverified.capabilities().captureVerified)
game.GetService=function() error("service unavailable") end
assert(not Vision.capabilities().nativeViewportCapture)
print("Native vision adapter tests passed")
