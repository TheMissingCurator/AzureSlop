# Animation preview and vision

> **Legacy harness feature.** New AI-agent setups should use
> [Roblox Studio MCP](https://create.roblox.com/docs/studio/mcp). This page
> documents AzureSlop's retained harness preview tools for existing users.

AzureSlop previews an animation on a **duplicate R6 rig in Edit mode**. It does
not start your game, pose the original rig, publish animations, or require a
token. Source clips remain untouched; editing works on a disposable copy.

## Install and capability check

Rebuild with `python tools/package_plugin.py` and install the complete
`dist/AzureSlop.rbxmx`. The plugin now includes three ModuleScripts; replacing
only the main Lua source is not sufficient. Restart the harness server as well
as Studio so both sides recognize the new methods.

```sh
azureslop harness status
azureslop harness call ping
azureslop harness call vision_capabilities
azureslop harness call vision_permission
```

`vision_permission` explicitly requests Roblox's screenshot permission. Capture
commands never prompt automatically. Studio must support `StudioCaptureService`,
permit screenshots, and have the requested place active. An unavailable API or
denied permission produces an error; there is no desktop-capture fallback.
API presence is **not** proof of runtime support. `vision_capabilities` reports
`servicePresent` and `querySucceeded` separately from `canCaptureNow` and
`nativeViewportCapture`. A false query never sets either availability flag true.
`ready_unverified` means the query returned true, not that an image was produced;
`captureVerified` becomes true only after reading a valid image buffer.

Some Studio builds expose the service but throw **Feature not supported yet**
from the permission method. This is classified as `vision.unsupported`, with the
failing stage and original error retained. AzureSlop remembers that failure for
the plugin session and will not keep requesting permission or moving the preview
camera for a known-unavailable capture backend. Restarting or updating Studio is
not a guaranteed fix for a platform/rollout restriction. No image is fabricated
or substituted when capture is unavailable.
The renderer returns the actual 3D viewport, without CoreGui/PlayerGui UI. This
is not a synthetic rendering or a screenshot of the entire desktop.

All examples below omit `--session` for readability. With multiple windows,
pass the same explicit `--session ID` from `harness status` to every command.

## Start, scrub, inspect

Create/import an R6 rig and a local KeyframeSequence in Studio, then:

```sh
azureslop harness call preview_start --params '{"rig":["Workspace","R6"],"clip":["Workspace","Walk"],"fps":30}'
```

Copy the returned `preview` ID into subsequent commands. To fetch an uploaded
clip instead, replace `clip` with `"assetId":"rbxassetid://123456789"`.
Asset loading still depends on Roblox connectivity and asset permissions.
KeyframeSequence clips are editable; CurveAnimation clips are preview-only.
The supplied rig must have the seven standard R6 parts and a Motor6D tree rooted
at HumanoidRootPart. Its Archivable property must be true.
Keyframe pose paths are checked against that tree before loading, so mismatched
R15/renamed/incorrectly nested poses report `animation.bindings` instead of
silently appearing to play. Errors identify registration (`register_clip`),
loading (`load_track`), readiness (`wait_for_track`), or evaluation (`evaluate`).
Paused Play mode is rejected too: it is not Edit mode. Status includes the actual
track timestamp and playing state, independently from the harness's paused pose.

```sh
azureslop harness call preview_seek --params '{"preview":"PREVIEW_ID","time":0.25}'
azureslop harness call preview_step --params '{"preview":"PREVIEW_ID","frames":1}'
azureslop harness call preview_step --params '{"preview":"PREVIEW_ID","frames":-1,"fps":60}'
azureslop harness call preview_status --params '{"preview":"PREVIEW_ID"}'
azureslop harness call preview_camera --params '{"preview":"PREVIEW_ID","view":"side"}'
```

All poses are paused (`Animator:StepAnimations(0)` after setting TimePosition).
`preview_step` adds `frames/fps` seconds, clamped to the clip endpoints. Seek
rejects out-of-range or non-finite timestamps. The clip's loop flag is preserved
for export, but preview playback does not wrap, allowing endpoint comparison.
Maximum clip duration is 600 seconds. A track that has not loaded after ten
seconds fails with a cleanup attempt; Roblox asset-fetch calls themselves can
yield longer, so normal harness uncertain-job recovery rules still apply.

The duplicate is offset 12 studs along the source rig's local X axis by default.
Supply an AzureSlop `$type: CFrame` as `origin` to choose an isolated staging
location. The floor is a horizontal reference plane at the neutral rig's lowest
leg corner; supply `floorY` to override it. Preview parts are anchored and
noncolliding. Joint transforms are applied explicitly in motor-tree order, so
physics simulation is unnecessary. Scripts/controllers from the clone are
removed before it enters Workspace. A temporary controller handles animation.

## Viewport images and frame strips

Capture the current Studio view (no preview needed):

```sh
azureslop harness capture --output /tmp/studio-shot
```

Capture fixed views at several timestamps:

```sh
azureslop harness capture --preview PREVIEW_ID --times 0,0.2,0.4,0.6 --views front,side,angled --width 512 --height 512 --output /tmp/walk-review
```

The output directory must be new. It contains:

- Individual PNG frames.
- `strip.png`: rows are views, columns are timestamps, in argument order.
- `manifest.json`: exact timestamps, preview revision, camera settings, job IDs,
  and frame filenames. Use this for labels and reproducibility.

An agent can open the local PNGs using its image-viewing tool. No OpenAI API
credentials or extra Python imaging dependencies are used. Dimensions are
64–1024 pixels per side, with at most 24 frames per strip. Each frame is a
separate bounded job using the existing result batching. Already captured frames
are preserved with `incomplete.json` if a later job fails or times out. Do not
blindly repeat an uncertain job; retrieve its ID first.

Without `--times`, the first frame's current timestamp is reused for every view.
Edits during capture invalidate the strip rather than mixing clip revisions.
Camera framing is fixed against the neutral rig, not recomputed at each pose,
so movement remains visible. Front is the rig root's local negative Z, side is
positive X, and angled is front-right. Long root-motion clips may require a
larger `distance` in direct `preview_capture` calls. Captures center-crop to the
output aspect ratio instead of stretching the image.

Direct calls expose more framing controls:

```sh
azureslop harness call preview_capture --params '{"preview":"PREVIEW_ID","time":0.25,"view":"angled","distance":20,"fov":35,"width":512,"height":512}' --output /tmp/one-frame
azureslop harness result JOB_ID --output /tmp/recovered-frame
```

Each preview capture restores the prior time, camera, and selection on success
or error. `preview_camera` intentionally leaves the selected view in Studio
until another camera command or cleanup. The raw capture result contains
base64 RGBA8 pixels; `--output` writes PNGs and removes that large field from
printed JSON. Output paths are chosen locally by the caller, never by Studio.

## Edit keyframes without replacing the source clip

```sh
azureslop harness call preview_keyframes --params '{"preview":"PREVIEW_ID"}'
```

This returns sorted, **1-based** keyframe indices, exact pose name paths,
transforms, weights, easing, and a revision number. Edit batches require that
revision. Example parameters for `preview_edit`:

```json
{
  "preview": "PREVIEW_ID",
  "expectedRevision": 1,
  "operations": [
    {"op": "time", "frame": 2, "time": 0.3},
    {
      "op": "pose",
      "frame": 2,
      "pose": ["HumanoidRootPart", "Torso", "Left Leg"],
      "cframe": {"$type":"CFrame","components":[0,0,0,1,0,0,0,1,0,0,0,1]},
      "easingStyle": "CubicV2",
      "easingDirection": "InOut",
      "weight": 1
    }
  ]
}
```

Use actual pose paths from `preview_keyframes`, not this example blindly. Fields
omitted from a pose operation are preserved. The matrix example is identity
and resets that pose's animation offset; it is not a world-space part CFrame.

Supported operations:

| Operation | Fields |
| --- | --- |
| `pose` | `frame`, `pose` path; optional `cframe`, `weight`, `easingStyle`, `easingDirection` |
| `time` | `frame`, new nonnegative `time` |
| `insert` | `time`; optional `copyFrame` to duplicate an existing pose hierarchy/markers |
| `remove` | `frame` |
| `loop` | boolean `value` |

A batch has 1–100 operations. Frame indices always refer to the sorted list at
the start of that batch, even after retiming. Duplicate timestamps, missing
poses, invalid enums, or clips outside 2–2000 keyframes are rejected. A candidate
copy is validated and loaded before replacing the working clip. Existing poses,
markers, and untouched properties are retained. The evaluator's track is
reloaded to pick up edits; the authored clip is not reconstructed frame by frame.

Undo the most recent working-copy edit:

```sh
azureslop harness call preview_undo --params '{"preview":"PREVIEW_ID","expectedRevision":2}'
```

Up to 20 edits are retained. Undo increments the revision too. To keep the result,
export a new named clip outside the temporary preview:

```sh
azureslop harness call preview_export --params '{"preview":"PREVIEW_ID","expectedRevision":3,"parent":["ReplicatedStorage"],"name":"WalkReviewed"}'
```

Export refuses an existing name and uses Studio's undo recording. It never
overwrites the source or publishes an asset. Normal Studio Undo removes the
export; `preview_undo` handles disposable working-copy edits separately.

## Motion diagnostics

```sh
azureslop harness call preview_diagnose --params '{"preview":"PREVIEW_ID","fps":30,"contactHeight":0.15}'
```

Results include:

- Each leg's horizontal sole travel and maximum speed during inferred contact.
- Maximum floor penetration, using all eight corners of each oriented leg box.
- Endpoint position/rotation differences per R6 body part.
- Head travel, maximum linear/angular speed, and vertical range.

Units are studs, seconds, and degrees. Contact is inferred when **both** adjacent
samples are within `contactHeight` studs of the reference floor. This is a
heuristic, not a guarantee that a foot is intended to be planted. It uses the
R6 leg box, not mesh silhouettes or actual ground collision. Head metrics are
potential camera-motion indicators, not a simulation of your camera script.

Use `start`/`finish` to restrict a range, `fps` to change sampling, and `samples:true`
to return underlying world-space measurements. At most 601 samples are allowed.
The last endpoint is always sampled even if it is between frame intervals.
For a partial range, loop metrics compare that range's endpoints and `fullClip`
is false. The preview root stays stationary unless root motion is authored in
the clip. Diagnosis restores the previous pose even on failure.

## Cleanup and live validation

```sh
azureslop harness call preview_stop --params '{"preview":"PREVIEW_ID"}'
```

This removes only the owned preview, destroys its working clips/tracks and undo
copies, and restores the original camera/selection where still valid. Exported
clips survive. Cleanup also runs when disabling/unloading the harness or entering
Play when the Studio RunState signal is available. The preview root is
non-archivable and excluded from AzureSlop snapshots; stop it before saving a
place as an extra precaution. Manually deleting the preview is not a substitute
for `preview_stop` (which also releases tracks and restores the camera).

Offline tests exercise orchestration using Studio doubles, numeric diagnostics,
image decoding, PNG pixels, packaging, and the real loopback protocol. They do
**not** prove Roblox's renderer, animation evaluator, or permissions work on your
installed build. Before relying on the feature, validate in Studio:

1. Preview a known R6 clip, seek to first/middle/last poses, step both directions.
2. Grant screenshot permission; inspect all three views and a short strip.
3. Edit a limb/time/easing, undo it, export, and undo the export in Studio.
4. Inspect diagnostics on a known stationary and sliding-foot clip.
5. Stop/disable preview and check that rig count, camera, selection, and source
   clip/rig match their original state; repeat after a capture error.

Implementation references: Roblox's [Animator:StepAnimations](https://create.roblox.com/docs/reference/engine/classes/Animator/StepAnimations),
[AnimationClipProvider](https://create.roblox.com/docs/reference/engine/classes/AnimationClipProvider),
[StudioCaptureService](https://create.roblox.com/docs/reference/engine/classes/StudioCaptureService),
and [StudioScreenshotCapture](https://create.roblox.com/docs/reference/engine/classes/StudioScreenshotCapture).
