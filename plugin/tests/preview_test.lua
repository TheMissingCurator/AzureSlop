-- Lifecycle/edit tests with a deterministic translation-only R6/Animator double.
-- These test orchestration, not Roblox's actual animation evaluator or renderer.
local objects,registered={},{}
local V,CF={},{}
local vm,cm={},{}
vm.__index=function(v,k)
 if k=="Magnitude" then return math.sqrt(v.X*v.X+v.Y*v.Y+v.Z*v.Z) end
 if k=="Unit" then return v/v.Magnitude end
end
vm.__add=function(a,b) return V.new(a.X+b.X,a.Y+b.Y,a.Z+b.Z) end
vm.__sub=function(a,b) return V.new(a.X-b.X,a.Y-b.Y,a.Z-b.Z) end
vm.__mul=function(a,b) return V.new(a.X*b,a.Y*b,a.Z*b) end
vm.__div=function(a,b) return a*(1/b) end
function V.new(x,y,z) return setmetatable({X=x or 0,Y=y or 0,Z=z or 0},vm) end
function CF.new(x,y,z)
 if type(x)=="table" then x,y,z=x.X,x.Y,x.Z end
 return setmetatable({X=x or 0,Y=y or 0,Z=z or 0,kind="CFrame"},cm)
end
cm.__mul=function(a,b) return CF.new(a.X+b.X,a.Y+b.Y,a.Z+b.Z) end
cm.__index=function(c,k)
 if k=="Position" then return V.new(c.X,c.Y,c.Z) end
 if k=="UpVector" then return V.new(0,1,0) end
 return CF[k]
end
function CF:Inverse() return CF.new(-self.X,-self.Y,-self.Z) end
function CF:PointToWorldSpace(v) return self.Position+v end
function CF:VectorToWorldSpace(v) return v end
function CF:GetComponents() return self.X,self.Y,self.Z,1,0,0,0,1,0,0,0,1 end
function CF.lookAt(pos) return CF.new(pos) end
local methods={}
local mt={__index=function(o,k)
 if methods[k] then return methods[k] end
 if k=="Position" and rawget(o,"CFrame") then return o.CFrame.Position end
 for _,child in ipairs(objects) do if rawget(child,"Parent")==o and not rawget(child,"destroyed") and child.Name==k then return child end end
end}
local function new(class)
 local o=setmetatable({ClassName=class,Name=class,Archivable=true,attributes={},CFrame=CF.new(),Size=V.new(2,2,1),Time=0,
  C0=CF.new(),C1=CF.new(),Transform=CF.new(),Weight=1,EasingStyle={Name="Linear"},EasingDirection={Name="In"}},mt)
 objects[#objects+1]=o; return o
end
function methods:IsA(c)
 return self.ClassName==c or (c=="BasePart" and self.ClassName=="Part") or
  (c=="JointInstance" and self.ClassName=="Motor6D") or (c=="AnimationClip" and self.ClassName=="KeyframeSequence") or
  (c=="LuaSourceContainer" and self.ClassName=="Script")
end
function methods:GetChildren()
 local a={}; for _,o in ipairs(objects) do if o.Parent==self and not o.destroyed then a[#a+1]=o end end; return a
end
function methods:GetDescendants()
 local a={}; for _,o in ipairs(self:GetChildren()) do a[#a+1]=o; for _,d in ipairs(o:GetDescendants()) do a[#a+1]=d end end; return a
end
function methods:FindFirstChild(n) for _,o in ipairs(self:GetChildren()) do if o.Name==n then return o end end end
function methods:FindFirstChildOfClass(c) for _,o in ipairs(self:GetChildren()) do if o.ClassName==c then return o end end end
function methods:IsDescendantOf(o) local p=self.Parent; while p do if p==o then return true end; p=p.Parent end; return false end
function methods:Destroy() for _,o in ipairs(self:GetChildren()) do o:Destroy() end; self.Parent=nil; self.destroyed=true end
function methods:SetAttribute(k,v) self.attributes[k]=v end
function methods:GetAttribute(k) return self.attributes[k] end
function methods:Clone()
 assert(self.Archivable)
 local map={}
 local function copy(o)
  local c=new(o.ClassName); map[o]=c
  for k,v in pairs(o) do if k~="Parent" and k~="attributes" then c[k]=v end end
  for _,child in ipairs(o:GetChildren()) do copy(child).Parent=c end
  return c
 end
 local result=copy(self)
 for _,c in pairs(map) do for k,v in pairs(c) do if map[v] then c[k]=map[v] end end end
 return result
end
function methods:GetKeyframes() local a={}; for _,c in ipairs(self:GetChildren()) do if c:IsA("Keyframe") then a[#a+1]=c end end; return a end
function methods:GetPivot() return self.HumanoidRootPart.CFrame end
function methods:PivotTo(cf)
 local delta=cf*self:GetPivot():Inverse()
 for _,p in ipairs(self:GetDescendants()) do if p:IsA("BasePart") then p.CFrame=delta*p.CFrame end end
end
function methods:GetBoundingBox() return self:GetPivot(),V.new(4,6,2) end
local failLoad=false
function methods:LoadAnimation(a)
 if failLoad then error("simulated load failure") end
 local clip=registered[a.AnimationId]; local keys=clip:GetKeyframes(); table.sort(keys,function(x,y) return x.Time<y.Time end)
 local t={Length=keys[#keys].Time,TimePosition=0,IsPlaying=false,clip=clip}
 function t:Play() self.IsPlaying=true end
 function t:Stop() self.IsPlaying=false end
 function t:Destroy() self.destroyed=true end
 function t:AdjustSpeed(speed) self.speed=speed end
 self.tracks=self.tracks or {}; table.insert(self.tracks,t); return t
end
function methods:StepAnimations(dt)
 assert(dt==0)
 for _,t in ipairs(self.tracks or {}) do if t.IsPlaying then
  assert(t.speed==0 and t.Looped==false)
  local keys=t.clip:GetKeyframes(); table.sort(keys,function(a,b) return a.Time<b.Time end)
  local last=keys[#keys]; local ratio=t.TimePosition/t.Length
  for _,j in ipairs(self.Parent.Parent:GetDescendants()) do if j:IsA("Motor6D") then
   j.Transform=CF.new()
   for _,pose in ipairs(last:GetDescendants()) do if pose:IsA("Pose") and pose.Name==j.Part1.Name then j.Transform=CF.new(pose.CFrame.X*ratio,pose.CFrame.Y*ratio,pose.CFrame.Z*ratio) end end
  end end
 end end
end
local game=new("DataModel"); local workspace=new("Workspace"); workspace.Parent=game
local rig=new("Model"); rig.Name="SourceRig"; rig.Parent=workspace
local originalScript=new("Script"); originalScript.Parent=rig
for _,name in ipairs({"HumanoidRootPart","Torso","Head","Left Arm","Right Arm","Left Leg","Right Leg"}) do local p=new("Part"); p.Name=name; p.Parent=rig end
for _,name in ipairs({"Torso","Head","Left Arm","Right Arm","Left Leg","Right Leg"}) do
 local j=new("Motor6D"); j.Part0=name=="Torso" and rig.HumanoidRootPart or rig.Torso; j.Part1=rig[name]; j.Parent=j.Part0
 if name:find("Leg") then j.C0=CF.new(name=="Left Leg" and -1 or 1,-2,0) end
end
local clip=new("KeyframeSequence"); clip.Name="SourceClip"; clip.Parent=workspace
for i=0,1 do
 local f=new("Keyframe"); f.Time=i; f.Parent=clip
 local root=new("Pose"); root.Name="HumanoidRootPart"; root.Parent=f
 local torso=new("Pose"); torso.Name="Torso"; torso.CFrame=CF.new(i,0,0); torso.Parent=root
end
local selected={rig}; local playing,enabled,paused=false,true,false
workspace.CurrentCamera={CFrame=CF.new(10,10,10),Focus=CF.new(),CameraType="Custom",FieldOfView=70,ViewportSize=V.new(800,600,0)}
local savedCamera=workspace.CurrentCamera.CFrame
local guid=0
local services={RunService={IsRunning=function() return playing end,IsEdit=function() return not playing and not paused end},Selection={Get=function() return selected end,Set=function(_,s) selected=s end},
 HttpService={GenerateGUID=function() guid=guid+1; return "preview-"..guid end},AnimationClipProvider={RegisterAnimationClip=function(_,c) local id=tostring(c); registered[id]=c; return id end}}
function game:GetService(n) return assert(services[n],n) end
local function enum(t) return setmetatable(t or {},{__index=function(_,k) error("Unknown enum "..k) end}) end
local env=setmetatable({game=game,workspace=workspace,Instance={new=new},Vector3=V,CFrame=CF,
 Color3={fromRGB=function() return {} end},Enum={HumanoidRigType={R6="R6"},Material={SmoothPlastic="SmoothPlastic"},CameraType={Scriptable="Scriptable"},PoseEasingStyle=enum({Linear={Name="Linear"}}),PoseEasingDirection=enum({In={Name="In"}})},
 task={wait=function() end},typeof=function(v) return type(v)=="table" and v.kind or type(v) end,
 script={Parent={HarnessVision="vision",HarnessMotion="motion"}},
 require=function(name) if name=="motion" then return dofile("plugin/HarnessMotion.lua") end; return {preflight=function() return {} end,capture=function() error("simulated screenshot failure") end} end}, {__index=_G})
local factory=assert(loadfile("plugin/HarnessPreview.lua","t",env))()
local preview=factory({resolve=function(ref) return ref end,describe=function(o) return {name=o.Name} end,decode=function(v) return v end,isEnabled=function() return enabled end})
local H=preview.handlers
local s=H.preview_start({rig=rig,clip=clip})
local id=s.preview
assert(s.revision==1 and s.length==1 and s.paused)
local duplicate=workspace:FindFirstChild("AzureSlopPreview_"..id).R6Preview
assert(not duplicate:FindFirstChildOfClass("Script") and originalScript.Parent==rig)
assert(rig.Torso.CFrame.X==0 and duplicate.Torso.CFrame.X==12)
H.preview_seek({preview=id,time=.5}); assert(duplicate.Torso.CFrame.X==12.5)
assert(H.preview_step({preview=id,frames=-1,fps=2}).time==0)
assert(not pcall(H.preview_seek,{preview="old",time=0}))
assert(not pcall(H.preview_seek,{preview=id,time=2}))
assert(not pcall(H.preview_start,{rig=rig,clip=clip}))
local result=H.preview_edit({preview=id,expectedRevision=1,operations={{op="time",frame=2,time=2}}})
assert(result.revision==2 and result.length==2 and clip:GetKeyframes()[2].Time==1)
assert(not pcall(H.preview_edit,{preview=id,expectedRevision=1,operations={{op="time",frame=2,time=3}}}))
assert(not pcall(H.preview_edit,{preview=id,expectedRevision=2,operations={{op="time",frame=2,time=0}}}))
assert(H.preview_status({preview=id}).revision==2)
failLoad=true
assert(not pcall(H.preview_edit,{preview=id,expectedRevision=2,operations={{op="time",frame=2,time=3}}}))
failLoad=false
assert(H.preview_status({preview=id}).length==2)
assert(H.preview_undo({preview=id,expectedRevision=2}).length==1)
assert(not pcall(H.preview_edit,{preview=id,expectedRevision=3,operations={{op="pose",frame=2,pose={"HumanoidRootPart","Torso"},easingStyle="NotAStyle"}}}))
assert(not pcall(H.preview_seek,{preview=id,time=0/0}))
H.preview_edit({preview=id,expectedRevision=3,operations={{op="pose",frame=2,pose={"HumanoidRootPart","Torso"},cframe=CF.new(3,0,0),easingStyle="Linear"}}})
H.preview_seek({preview=id,time=1}); assert(duplicate.Torso.CFrame.X==15)
H.preview_export({preview=id,expectedRevision=4,parent=workspace,name="EditedClip"})
assert(workspace.EditedClip and clip:GetKeyframes()[2].Torso==nil)
assert(not pcall(H.preview_export,{preview=id,expectedRevision=4,parent=workspace,name="EditedClip"}))
local oldTime=H.preview_status({preview=id}).time
assert(not pcall(H.preview_capture,{preview=id,time=.2,view="front",width=512,height=512}))
assert(H.preview_status({preview=id}).time==oldTime and workspace.CurrentCamera.CFrame==savedCamera)
local diagnostics=H.preview_diagnose({preview=id,fps=2})
assert(diagnostics.sampleCount==3 and H.preview_status({preview=id}).time==oldTime)
playing=true; assert(not pcall(H.preview_seek,{preview=id,time=0})); playing=false
paused=true; assert(not pcall(H.preview_seek,{preview=id,time=0})); paused=false
assert(H.preview_stop({preview=id}).stopped)
assert(not duplicate.Parent and selected[1]==rig and workspace.EditedClip)
assert(not H.preview_stop({}).stopped)
failLoad=true
assert(not pcall(H.preview_start,{rig=rig,clip=clip}))
assert(not workspace:FindFirstChild("AzureSlopPreview_preview-2"))
failLoad=false
s=H.preview_start({rig=rig,clip=clip}); preview.cleanup()
assert(not workspace:FindFirstChild("AzureSlopPreview_"..s.preview))
print("Preview lifecycle, editing, restoration and failure tests passed")
