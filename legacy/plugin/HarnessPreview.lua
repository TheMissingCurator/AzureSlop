-- One disposable R6 preview per Studio window. Source rigs/clips are never posed.
return function(ctx)
 local Vision = require(script.Parent.HarnessVision)
 local Motion = require(script.Parent.HarnessMotion)
 local Run = game:GetService("RunService")
 local Selection = game:GetService("Selection")
 local state
 local H = {}
 local names = {"HumanoidRootPart","Torso","Head","Left Arm","Right Arm","Left Leg","Right Leg"}
 local function number(v, name, low, high)
  assert(type(v)=="number" and v==v and v>=low and v<=high,name.." out of range")
  return v
 end
 local function integer(v,name,low,high)
  number(v,name,low,high); assert(v%1==0,name.." must be an integer"); return v
 end
 local function editMode() assert(Run:IsEdit(),"Stop Play/Run before using animation previews (paused simulation is not Edit mode)") end
 local function active(p)
  editMode()
  assert(state and not state.cancelled and state.container.Parent,"No active preview")
  assert(p.preview==state.id,"Pass the current preview ID; stale previews are rejected")
  return state
 end
 local function check(s)
  assert(not s.cancelled and ctx.isEnabled(),"Preview cancelled or harness disabled")
  editMode()
 end
 local function frames(clip)
  assert(clip:IsA("KeyframeSequence"),"Keyframe editing requires a KeyframeSequence (CurveAnimation is preview-only)")
  local list=clip:GetKeyframes()
  table.sort(list,function(a,b) return a.Time<b.Time end)
  return list
 end
 local function validateClip(clip)
  if not clip:IsA("KeyframeSequence") then return end
  local list=frames(clip)
  assert(#list>=2 and #list<=2000,"Clip must contain 2..2000 keyframes")
  local previous=-1
  for _,f in ipairs(list) do
   number(f.Time,"Keyframe time",0,600)
   assert(f.Time>previous,"Keyframe times must be unique")
   previous=f.Time
  end
  assert(previous>0,"Clip must have positive duration")
 end
 local function cameraSave()
  local c=assert(workspace.CurrentCamera,"No Studio camera")
  return {camera=c,cf=c.CFrame,focus=c.Focus,kind=c.CameraType,subject=c.CameraSubject,fov=c.FieldOfView}
 end
 local function cameraRestore(saved)
  if not saved or workspace.CurrentCamera~=saved.camera then return end
  local c=saved.camera
  c.CameraType=saved.kind; c.CameraSubject=saved.subject
  c.FieldOfView=saved.fov; c.CFrame=saved.cf; c.Focus=saved.focus
 end
 local function trackDestroy(t)
  if t then pcall(function() t:Stop(0); t:Destroy() end) end
 end
 local function dispose(s)
  s.cancelled=true
  trackDestroy(s.track)
  if s.clip then s.clip:Destroy() end
  for _,clip in ipairs(s.undo or {}) do clip:Destroy() end
  if s.container then s.container:Destroy() end
  pcall(cameraRestore,s.savedCamera)
  if s.savedSelection then
   local valid={}
   for _,obj in ipairs(s.savedSelection) do if obj:IsDescendantOf(game) then table.insert(valid,obj) end end
   pcall(function() Selection:Set(valid) end)
  end
 end
 local function cleanup()
  local s=state; state=nil
  if s then dispose(s) end
  return {stopped=s~=nil,cameraRestored=s~=nil}
 end
 local function loadTrack(s,clip)
  validateClip(clip)
  if clip:IsA("KeyframeSequence") then
   local parents={}
   for _,joint in ipairs(s.orderedJoints) do parents[joint.Part1.Name]=joint.Part0.Name end
   local bound=0
   local function visit(parent,expectedParent)
    for _,child in ipairs(parent:GetChildren()) do
     if child:IsA("Pose") then
      if expectedParent==nil then
       assert(child.Name==s.root.Name,"[animation.bindings] Root pose must be "..s.root.Name..", found "..child.Name)
      else
       assert(parents[child.Name]==expectedParent,
        "[animation.bindings] Pose "..expectedParent.."/"..child.Name.." does not match the duplicate's Motor6D hierarchy")
       bound=bound+1
      end
      visit(child,child.Name)
     end
    end
   end
   for _,frame in ipairs(frames(clip)) do visit(frame,nil) end
   assert(bound>0,"[animation.bindings] Clip has no poses bound to the R6 motors")
  end
  local animation=Instance.new("Animation")
  local track
  local stage="register_clip"
  local ok,err=pcall(function()
   animation.AnimationId=game:GetService("AnimationClipProvider"):RegisterAnimationClip(clip)
   check(s)
   stage="load_track"
   track=s.animator:LoadAnimation(animation)
   stage="wait_for_track"
   local deadline=os.clock()+10
   while track.Length<=0 do
    check(s); assert(os.clock()<deadline,"Animation failed to load in 10 seconds; check permissions and clip contents")
    task.wait(.03)
   end
   number(track.Length,"Clip duration",.000001,600)
   -- Preserve the endpoint for loop comparisons instead of wrapping to zero.
   track.Looped=false
  end)
  animation:Destroy()
  if not ok then trackDestroy(track); error("[animation."..stage.."] "..tostring(err),0) end
  return track
 end
 local function pose(s,time)
  check(s)
  number(time,"time",0,s.track.Length)
  for _,j in ipairs(s.joints) do j.Transform=CFrame.new() end
  -- StepAnimations applies the animation in edit mode. Speed zero keeps it paused.
  if not s.track.IsPlaying then s.track:Play(0,1,0) end
  s.track:AdjustSpeed(0)
  s.track.TimePosition=time
  local evaluated,err=pcall(function() s.animator:StepAnimations(0) end)
  if not evaluated then error("[animation.evaluate] Animator:StepAnimations failed: "..tostring(err),0) end
  -- Anchored preview parts need explicit FK; never rely on running physics.
  s.root.CFrame=s.rootFrame
  for _,j in ipairs(s.orderedJoints) do j.Part1.CFrame=j.Part0.CFrame*j.C0*j.Transform*j.C1:Inverse() end
  for _,j in ipairs(s.welds) do j.Part1.CFrame=j.Part0.CFrame*j.C0*j.C1:Inverse() end
  s.time=time
 end
 local function bottom(part)
  local low=math.huge
  for _,x in ipairs({-1,1}) do for _,y in ipairs({-1,1}) do for _,z in ipairs({-1,1}) do
   low=math.min(low,part.CFrame:PointToWorldSpace(Vector3.new(x*part.Size.X/2,y*part.Size.Y/2,z*part.Size.Z/2)).Y)
  end end end
  return low
 end
 local function status(s)
  return {preview=s.id,revision=s.revision,time=s.time,length=s.track.Length,fps=s.fps,
   trackTime=s.track.TimePosition,trackPlaying=s.track.IsPlaying,evaluator="Animator.StepAnimations",
   editable=s.clip:IsA("KeyframeSequence"),rig=ctx.describe(s.rig),clip=ctx.describe(s.clip),
   floorY=s.floorY,undoDepth=#s.undo,paused=true}
 end
 H.preview_start=function(p)
  editMode(); assert(not state,"Stop the existing preview before starting another")
  local rig=ctx.resolve(p.rig)
  assert(rig:IsA("Model") and rig.Archivable,"rig must be an archivable R6 Model")
  local human=rig:FindFirstChildOfClass("Humanoid")
  assert(not human or human.RigType==Enum.HumanoidRigType.R6,"Only R6 rigs are supported")
  for _,name in ipairs(names) do assert(rig:FindFirstChild(name) and rig[name]:IsA("BasePart"),"Missing R6 part: "..name) end
  assert((p.clip~=nil)~=(p.assetId~=nil),"Supply exactly one of clip or assetId")
  local fps=integer(p.fps or 30,"fps",1,240)
  local s={id=game:GetService("HttpService"):GenerateGUID(false),revision=1,fps=fps,time=0,undo={},
   savedCamera=cameraSave(),savedSelection=Selection:Get()}
  s.container=Instance.new("Model"); s.container.Name="AzureSlopPreview_"..s.id
  s.container.Archivable=false; s.container:SetAttribute("AzureSlopPreview",true)
  state=s
  local ok,err=pcall(function()
   s.rig=assert(rig:Clone(),"Could not duplicate rig")
   s.rig.Name="R6Preview"; s.rig.Parent=s.container
   for _,obj in ipairs(s.rig:GetDescendants()) do
    if obj:IsA("LuaSourceContainer") or obj:IsA("Humanoid") or obj:IsA("AnimationController") or obj:IsA("Animator") then obj:Destroy()
    elseif obj:IsA("BasePart") then obj.Anchored=true; obj.CanCollide=false; obj.CanTouch=false; obj.CanQuery=false
    elseif obj:IsA("Constraint") then obj.Enabled=false end
   end
   local dest=p.origin and ctx.decode(p.origin) or rig:GetPivot()*CFrame.new(12,0,0)
   assert(typeof(dest)=="CFrame","origin must be a CFrame")
   s.rig:PivotTo(dest)
   s.root=s.rig.HumanoidRootPart; s.rootFrame=s.root.CFrame
   s.joints={}; s.welds={}; s.orderedJoints={}
   for _,obj in ipairs(s.rig:GetDescendants()) do
    if obj:IsA("JointInstance") then
     assert(obj.Part0 and obj.Part1 and obj.Part0:IsDescendantOf(s.rig) and obj.Part1:IsDescendantOf(s.rig),"Rig joint references parts outside the duplicate")
     if obj:IsA("Motor6D") then table.insert(s.joints,obj)
     elseif obj:IsA("Weld") then table.insert(s.welds,obj) end
    end
   end
   local reached={[s.root]=true}
   for _=1,#s.joints do
    for _,j in ipairs(s.joints) do
     if reached[j.Part0] and not reached[j.Part1] then
      reached[j.Part1]=true; table.insert(s.orderedJoints,j)
     end
    end
   end
   assert(#s.orderedJoints==#s.joints,"Rig motors must form a rooted tree")
   for _,name in ipairs(names) do assert(reached[s.rig[name]],"R6 part is not connected to root: "..name) end
   -- Establish a neutral baseline even if the source was left posed in Studio.
   for _,j in ipairs(s.orderedJoints) do
    j.Transform=CFrame.new(); j.Part1.CFrame=j.Part0.CFrame*j.C0*j.C1:Inverse()
   end
   for _,j in ipairs(s.welds) do j.Part1.CFrame=j.Part0.CFrame*j.C0*j.C1:Inverse() end
   local controller=Instance.new("AnimationController"); controller.Parent=s.rig
   s.animator=Instance.new("Animator"); s.animator.Parent=controller
   s.container.Parent=workspace
   if p.clip then
    local original=ctx.resolve(p.clip)
    assert(original:IsA("AnimationClip") and original.Archivable,"clip must be an archivable AnimationClip")
    s.clip=assert(original:Clone(),"Could not copy animation clip")
   else
    assert(type(p.assetId)=="string" and string.match(p.assetId,"^rbxassetid://%d+$"),"assetId must be rbxassetid://NUMBER")
    s.clip=game:GetService("AnimationClipProvider"):GetAnimationClipAsync(p.assetId)
   end
   check(s); s.clip.Name="WorkingClip"; s.clip.Parent=s.container
   s.track=loadTrack(s,s.clip)
   s.floorY=p.floorY and number(p.floorY,"floorY",-1000000,1000000) or math.min(bottom(s.rig["Left Leg"]),bottom(s.rig["Right Leg"]))
   local floor=Instance.new("Part"); floor.Name="PreviewFloor"; floor.Anchored=true
   floor.Size=Vector3.new(40,.2,40); floor.Position=Vector3.new(s.rootFrame.X,s.floorY-.1,s.rootFrame.Z)
   floor.Color=Color3.fromRGB(74,78,87); floor.Material=Enum.Material.SmoothPlastic
   floor.CanCollide=false; floor.CanTouch=false; floor.Parent=s.container
   local cf,size=s.rig:GetBoundingBox(); s.cameraCenter=cf.Position; s.cameraRadius=math.max(size.Magnitude/2,3)
   pose(s,0); Selection:Set({})
  end)
  if not ok then
   if state==s then state=nil end
   dispose(s); error(err)
  end
  return status(s)
 end
 H.preview_status=function(p) return status(active(p)) end
 H.preview_seek=function(p)
  local s=active(p); pose(s,number(p.time,"time",0,s.track.Length)); return status(s)
 end
 H.preview_step=function(p)
  local s=active(p); local count=integer(p.frames or 1,"frames",-10000,10000)
  local fps=integer(p.fps or s.fps,"fps",1,240)
  local t=math.max(0,math.min(s.track.Length,s.time+count/fps)); pose(s,t); return status(s)
 end
 local function camera(s,p)
  local directions={front=Vector3.new(0,0,-1),side=Vector3.new(1,0,0),angled=Vector3.new(1,.5,-1).Unit}
  local direction=assert(directions[p.view or "angled"],"view must be front, side, or angled")
  local c=assert(workspace.CurrentCamera)
  local fov=number(p.fov or 35,"fov",10,90)
  local aspect=(p.width or c.ViewportSize.X)/math.max(1,p.height or c.ViewportSize.Y)
  local distance=p.distance and number(p.distance,"distance",1,10000) or s.cameraRadius/math.sin(math.rad(fov/2))*1.25/math.min(1,aspect)
  local focus=s.cameraCenter
  c.CameraType=Enum.CameraType.Scriptable; c.FieldOfView=fov
  c.CFrame=CFrame.lookAt(focus+s.rootFrame:VectorToWorldSpace(direction)*distance,focus,s.rootFrame.UpVector)
  c.Focus=CFrame.new(focus)
  return {view=p.view or "angled",cframe=c.CFrame,focus=c.Focus,fov=fov,distance=distance}
 end
 H.preview_camera=function(p) return camera(active(p),p) end
 H.preview_capture=function(p)
  local s=active(p); local saved=cameraSave(); local oldTime=s.time; local selected=Selection:Get()
  assert(p.expectedRevision==nil or p.expectedRevision==s.revision,"Revision changed before capture")
  Vision.preflight() -- Do not move the camera or pose for a known-unavailable backend.
  local ok,result=pcall(function()
   if p.time~=nil then pose(s,number(p.time,"time",0,s.track.Length)) end
   local framing=camera(s,p); Selection:Set({})
   -- Yield to rendering, with a bounded wait even if Studio is minimized.
   task.wait(.1); check(s)
   local image=Vision.capture(p,function() return s.cancelled or not ctx.isEnabled() end)
   return {image=image,preview=s.id,revision=s.revision,time=s.time,camera=framing}
  end)
  local restored,restoreError=pcall(function()
   if not s.cancelled then
    -- Restore the camera even if restoring the animation itself fails.
    cameraRestore(saved); Selection:Set(selected); pose(s,oldTime)
   end
  end)
  if not restored then cleanup(); error("Preview restoration failed: "..tostring(restoreError)) end
  if not ok then error(result) end
  return result
 end
 H.preview_keyframes=function(p)
  local s=active(p); local result={}
  for i,f in ipairs(frames(s.clip)) do
   local poses={}
   local function visit(parent,path)
    for _,obj in ipairs(parent:GetChildren()) do
     if obj:IsA("Pose") then
      local nextPath={table.unpack(path)}; table.insert(nextPath,obj.Name)
      table.insert(poses,{path=nextPath,cframe=obj.CFrame,weight=obj.Weight,easingStyle=obj.EasingStyle.Name,easingDirection=obj.EasingDirection.Name})
      visit(obj,nextPath)
     end
    end
   end
   visit(f,{})
   table.insert(result,{frame=i,time=f.Time,name=f.Name,poses=poses})
  end
  return {preview=s.id,revision=s.revision,loop=s.clip.Loop,frames=result}
 end
 local function findPose(frame,path)
  assert(type(path)=="table" and #path>0,"pose must be a nonempty name path from the keyframe")
  local obj=frame
  for _,name in ipairs(path) do
   local match
   for _,child in ipairs(obj:GetChildren()) do
    if child:IsA("Pose") and child.Name==name then assert(not match,"Ambiguous pose name"); match=child end
   end
   obj=assert(match,"Pose path not found: "..tostring(name))
  end
  return obj
 end
 local function replace(s,clip)
  local nextTrack=loadTrack(s,clip)
  local oldTrack,oldClip,oldTime=s.track,s.clip,s.time
  s.track=nextTrack; s.clip=clip
  oldTrack:Stop(0)
  local ok,err=pcall(pose,s,math.min(oldTime,nextTrack.Length))
  if not ok then s.track=oldTrack; s.clip=oldClip; trackDestroy(nextTrack); pcall(pose,s,oldTime); error(err) end
  trackDestroy(oldTrack); clip.Parent=s.container; oldClip.Parent=nil; s.revision=s.revision+1
  return oldClip
 end
 H.preview_edit=function(p)
  local s=active(p); assert(p.expectedRevision==s.revision,"Revision changed; inspect keyframes again")
  assert(type(p.operations)=="table" and #p.operations>=1 and #p.operations<=100,"Supply 1..100 edit operations")
  frames(s.clip)
  local candidate=s.clip:Clone()
  local ok,result=pcall(function()
   -- Frame indices in a batch always refer to the original sorted frame list.
   local list=frames(candidate)
   for _,op in ipairs(p.operations) do
    if op.op=="loop" then assert(type(op.value)=="boolean","loop value must be boolean"); candidate.Loop=op.value
    elseif op.op=="insert" then
     local f
     if op.copyFrame then f=list[integer(op.copyFrame,"copyFrame",1,#list)]:Clone()
     else f=Instance.new("Keyframe") end
     f.Parent=candidate; f.Time=number(op.time,"time",0,600)
    else
     local f=list[integer(op.frame,"frame",1,#list)]
     assert(f.Parent==candidate,"Frame already removed in this batch")
     if op.op=="remove" then f:Destroy()
     elseif op.op=="time" then f.Time=number(op.time,"time",0,600)
     elseif op.op=="pose" then
      local obj=findPose(f,op.pose)
      if op.cframe then local cf=ctx.decode(op.cframe); assert(typeof(cf)=="CFrame","cframe must be a CFrame"); obj.CFrame=cf end
      if op.weight~=nil then obj.Weight=number(op.weight,"weight",0,1) end
      if op.easingStyle then obj.EasingStyle=Enum.PoseEasingStyle[op.easingStyle] end
      if op.easingDirection then obj.EasingDirection=Enum.PoseEasingDirection[op.easingDirection] end
     else error("Unknown edit operation: "..tostring(op.op)) end
    end
   end
   validateClip(candidate)
   local old=replace(s,candidate); table.insert(s.undo,old)
   if #s.undo>20 then table.remove(s.undo,1):Destroy() end
   return status(s)
  end)
  if not ok then candidate:Destroy(); error(result) end
  return result
 end
 H.preview_undo=function(p)
  local s=active(p); assert(p.expectedRevision==s.revision,"Revision changed; inspect again")
  local clip=assert(s.undo[#s.undo],"No preview edit to undo")
  local old=replace(s,clip); table.remove(s.undo); old:Destroy()
  return status(s)
 end
 H.preview_export=function(p)
  local s=active(p); assert(p.expectedRevision==s.revision,"Revision changed; inspect again")
  local parent=ctx.resolve(p.parent)
  assert(parent~=s.container and not parent:IsDescendantOf(s.container),"Export outside the disposable preview")
  assert(type(p.name)=="string" and #p.name>0 and #p.name<=100,"Supply an export name")
  assert(not parent:FindFirstChild(p.name),"Export name already exists; choose a new name")
  local copy=s.clip:Clone(); copy.Name=p.name; copy.Archivable=true
  local ok,err=pcall(function() copy.Parent=parent end)
  if not ok then copy:Destroy(); error(err) end
  return {clip=ctx.describe(copy),published=false}
 end
 H.preview_diagnose=function(p)
  local s=active(p); local fps=integer(p.fps or s.fps,"fps",1,240)
  local start=number(p.start or 0,"start",0,s.track.Length)
  local finish=number(p.finish or s.track.Length,"finish",start,s.track.Length)
  assert(finish>start,"finish must exceed start")
  local intervals=math.ceil((finish-start)*fps); assert(intervals<=600,"At most 601 samples; reduce fps or time range")
  local threshold=number(p.contactHeight or .15,"contactHeight",0,5)
  local saved=s.time
  local ok,result=pcall(function()
   local samples={}
   for i=0,intervals do
    local time=math.min(finish,start+i/fps); pose(s,time)
    local sample={time=time,parts={}}
    for _,name in ipairs(names) do
     local part=s.rig[name]; local sole=part.CFrame:PointToWorldSpace(Vector3.new(0,-part.Size.Y/2,0))
     sample.parts[name]={cf={part.CFrame:GetComponents()},bottom=bottom(part)-s.floorY,sole={sole.X,sole.Y,sole.Z}}
    end
    table.insert(samples,sample)
    if i%30==0 then task.wait(); check(s) end
   end
   local report=Motion.analyze(samples,threshold)
   report.preview=s.id; report.revision=s.revision; report.floorY=s.floorY; report.fps=fps
   report.start=start; report.finish=finish; report.fullClip=start==0 and finish==s.track.Length
   if p.samples==true then report.samples=samples end
   return report
  end)
  local restored,err=pcall(function() if not s.cancelled then pose(s,saved) end end)
  if not restored then cleanup(); error("Preview restoration failed: "..tostring(err)) end
  if not ok then error(result) end
  return result
 end
 H.preview_stop=function(p)
  if state then assert(p.preview==state.id,"Pass the current preview ID") end
  return cleanup()
 end
 H.vision_capabilities=function() return Vision.capabilities() end
 H.vision_permission=function() return Vision.permission() end
 H.viewport_capture=function(p) editMode(); return {image=Vision.capture(p,function() return not ctx.isEnabled() end)} end
 return {handlers=H,cleanup=cleanup}
end
