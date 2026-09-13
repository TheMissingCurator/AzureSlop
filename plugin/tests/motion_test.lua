local Motion=dofile("plugin/HarnessMotion.lua")
local function sample(time,x,y,angle)
 local c,s=math.cos(angle or 0),math.sin(angle or 0)
 local cf={x,y,0,c,-s,0,s,c,0,0,0,1}
 local part={cf=cf,bottom=y,sole={x,y,0}}
 return {time=time,parts={["Left Leg"]=part,["Right Leg"]=part,Head=part}}
end
local still=Motion.analyze({sample(0,0,0),sample(1,0,0)},.15)
assert(still.feet["Left Leg"].slidingDistance==0)
assert(still.head.travel==0 and still.loop.Head.angleDeltaDegrees==0)
local moving=Motion.analyze({sample(0,0,0),sample(.5,1,-.1),sample(1,2,0,math.pi/2)},.15)
assert(moving.feet["Left Leg"].slidingDistance==2)
assert(moving.feet["Left Leg"].maxSlidingSpeed==2)
assert(moving.feet["Left Leg"].maxPenetration==.1)
assert(math.abs(moving.loop.Head.angleDeltaDegrees-90)<.000001)
assert(moving.head.verticalRange==.1)
local airborne=Motion.analyze({sample(0,0,1),sample(1,4,1)},.15)
assert(airborne.feet["Left Leg"].contactIntervals==0)
assert(not pcall(Motion.analyze,{sample(0,0,0)},.15))
assert(not pcall(Motion.analyze,{sample(0,0,0),sample(0,0,0)},.15))
print("Motion diagnostics tests passed")
