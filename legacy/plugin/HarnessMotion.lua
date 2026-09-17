-- Pure numeric diagnostics. Inputs are sampled by the Studio preview adapter.
local Motion = {}
local function distance(a, b, horizontal)
 local x, y, z = a[1]-b[1], a[2]-b[2], a[3]-b[3]
 return math.sqrt(x*x + (horizontal and 0 or y*y) + z*z)
end
local function angle(a, b)
 local trace = 0
 for i=4,12 do trace = trace + a[i]*b[i] end
 return math.deg(math.acos(math.max(-1, math.min(1, (trace-1)/2))))
end
function Motion.analyze(samples, contactHeight)
 assert(#samples >= 2, "At least two samples required")
 local out = { feet = {}, head = { travel = 0, maxSpeed = 0, maxAngularSpeedDegrees = 0 },
  loop = {}, sampleCount = #samples, duration = samples[#samples].time-samples[1].time,
  caveat = "Foot sliding uses a floor-distance contact heuristic, not authored stance markers. Loop metrics compare endpoint poses; preview root is stationary unless animated by the clip." }
 for _,name in ipairs({"Left Leg", "Right Leg"}) do
  local foot = { slidingDistance = 0, maxSlidingSpeed = 0, maxPenetration = 0, contactIntervals = 0 }
  for i,s in ipairs(samples) do
   local now = assert(s.parts[name], "Missing R6 foot")
   foot.maxPenetration = math.max(foot.maxPenetration, -now.bottom)
   if i > 1 then
    local before = samples[i-1].parts[name]
    local dt = s.time-samples[i-1].time
    assert(dt > 0, "Sample times must increase")
    if math.abs(now.bottom) <= contactHeight and math.abs(before.bottom) <= contactHeight then
     local step = distance(now.sole, before.sole, true)
     foot.slidingDistance = foot.slidingDistance + step
     foot.maxSlidingSpeed = math.max(foot.maxSlidingSpeed, step/dt)
     foot.contactIntervals = foot.contactIntervals + 1
    end
   end
  end
  out.feet[name] = foot
 end
 local low, high = math.huge, -math.huge
 for i,s in ipairs(samples) do
  local head = s.parts.Head.cf
  low, high = math.min(low,head[2]), math.max(high,head[2])
  if i > 1 then
   local before = samples[i-1].parts.Head.cf
   local dt = s.time-samples[i-1].time
   local step = distance(head,before)
   out.head.travel = out.head.travel + step
   out.head.maxSpeed = math.max(out.head.maxSpeed,step/dt)
   out.head.maxAngularSpeedDegrees = math.max(out.head.maxAngularSpeedDegrees,angle(head,before)/dt)
  end
 end
 out.head.verticalRange = high-low
 for name,first in pairs(samples[1].parts) do
  local last = samples[#samples].parts[name]
  out.loop[name] = { positionDelta = distance(first.cf,last.cf), angleDeltaDegrees = angle(first.cf,last.cf) }
 end
 return out
end
return Motion
