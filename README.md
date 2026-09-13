# AzureSlop

AzureSlop is a Roblox Studio plugin and Python CLI for file-based development
and local agent control. It has two workflows:

- **Pull, push, and test:** move scripts, supported values/events, and GUI
  definitions between Studio and disk, with baseline tracking and conflict checks.
- **Agent harness:** keep a local connection open for instance inspection,
  source editing, Luau execution, logs, and R6 animation preview tools.

No Rojo project manifest is required. The harness is model-agnostic: an agent
such as GPT-6/Codex can call the CLI, but AzureSlop does not run a model or require
an OpenAI API key. See the [harness guide](docs/harness.md).

## Current feature status

| Feature | State |
| --- | --- |
| File pull/push, conflict resolution, GUI sidecars | Implemented; explicit operations, not continuous sync. |
| Persistent local agent harness | Implemented; no manually configured pairing/bearer token. |
| R6 animation preview and scrubbing | Implemented in Edit mode on a duplicate rig. Basic forward/backward timestamp evaluation has been checked in Studio. |
| Keyframe editing, preview undo/export, motion diagnostics | Implemented; R6/clip constraints and diagnostic limitations apply. Not every clip or Studio environment has been validated. |
| Fixed preview cameras | Implemented; front, side, and angled views in Studio. |
| Native viewport screenshots and frame strips | Adapter and PNG/strip export code implemented, but **blocked by Roblox's not-yet-available capture functionality in the tested Studio build**. Not an established working feature. |

### Screenshots: waiting on Roblox

Roblox documents [StudioCaptureService](https://create.roblox.com/docs/reference/engine/classes/StudioCaptureService),
but the tested Studio build exposes the API and throws **Feature not supported
yet** from `RequestScreenshotPermissionAsync()`, before an image is captured.
This is an upstream implementation/availability limitation, not a token setup
problem or evidence that the user denied permission. It is not established as
a Linux/Flatpak-specific problem either. AzureSlop cannot enable functionality
Roblox has not made available, and restarting or retrying permission is not a fix.

`vision_capabilities` distinguishes API presence from capture availability and
successful image capture. A false capability query no longer reports native
capture as available. Unsupported failures prevent repeated permission requests
for that plugin session. There is no desktop-capture fallback or fabricated image.
The [animation and vision guide](docs/animation-preview.md) documents the commands
and the remaining live-validation requirements.

## Platforms

Windows is the primary setup target. The Python CLI and plugin package are
intended to work across Windows, macOS, and Linux, but intended portability is
not the same as completed end-to-end testing.

| Platform | Studio and verification status |
| --- | --- |
| Windows | Native Studio platform and primary target; full AzureSlop end-to-end validation is still needed. |
| macOS | Native Studio platform; full AzureSlop end-to-end validation is still needed. |
| Linux | CLI runs locally; Studio requires an unofficial compatibility environment such as Vinegar/Wine. Development checks have used a Vinegar Flatpak installation. |

Roblox distributes Studio for [Windows and macOS](https://create.roblox.com/docs/studio/setup),
not native Linux. AzureSlop's Python test/build CI is configured for all three
operating systems; that does not test Studio, Wine, screenshot availability, or
every platform's filesystem behavior. See [Verification](#verification).

## File operations and conflicts

File transfer is deliberately not a live sync bridge:

- `azureslop pull` pulls one Studio snapshot to disk in safe-sized batches and exits.
- `azureslop push` applies only added, modified, and deleted disk paths to Studio.
- `azureslop test` applies disk changes to existing Studio scripts through
  `ScriptEditorService:UpdateSourceAsync`, which creates drafts when the place
  has Drafts mode enabled.
- `azureslop test --local` copies a configured `.rbxl` or `.rbxlx` baseline,
  opens the disposable copy, and can create or delete instances as well as
  update scripts.

Pull, push, and non-local test compare Studio, disk, and the last successful
AzureSlop snapshot before overwriting anything. A path changed on both sides is
reported as a version conflict and the operation is stopped.

When that happens, the CLI prints every conflicting path and remains running.
The plugin presents two choices:

- **Apply resolution** retries after a manual edit or applies choices prepared
  with `azureslop resolve`.
- **Pull anyway** keeps Studio for every pull conflict. **Push anyway** keeps
  disk for every push/test conflict. The override requires a second confirmation
  click so it cannot be triggered accidentally.

For a path-by-path choice, leave the original command running and open another
terminal in the same project:

```bash
azureslop resolve
```

The resolver asks whether disk or Studio should win for every conflicting path.
After answering, return to Studio and click **Apply resolution**. AzureSlop
checks that neither version changed after the choice; if one did, that path is
presented as a fresh conflict instead of applying a stale resolution.

## Setup

### 1. Install the CLI

Requires Python 3.10 or newer. From the repository root, on Windows (PowerShell):

```powershell
py -m pip install -e ./cli
py tools/package_plugin.py
```

On macOS or Linux:

```sh
python3 -m pip install -e ./cli
python3 tools/package_plugin.py
```

Use a virtual environment if your Python installation requires one. Make sure
its scripts directory is on PATH when running `azureslop`. The CLI and PNG
exporter have no third-party Python runtime dependencies.

### 2. Initialize a project

```bash
mkdir my-game
cd my-game
azureslop init
```

### 3. Install the Studio plugin

Install the generated **`dist/AzureSlop.rbxmx`** as a local Studio plugin.
It contains the main script and the `HarnessPreview`, `HarnessVision`, and
`HarnessMotion` modules. **Do not install only `plugin/AzureSlop.lua`**: the
animation/vision commands require the bundled modules.

Copy the package into the local plugins folder used by your Studio installation,
replacing the old AzureSlop package. On Windows this is normally
`%LOCALAPPDATA%\Roblox\Plugins`. On macOS, use Studio's local plugins folder;
on Linux, use the Plugins directory inside the Studio Wine/Vinegar prefix,
not a native Linux application directory. The plugin is the same package on
each platform; Flatpak is not a requirement.

Alternatively, the packager installs to an **explicit existing directory** and
backs up the old package. For example, in Windows PowerShell:

```powershell
py tools/package_plugin.py --install "$env:LOCALAPPDATA/Roblox/Plugins/AzureSlop.rbxmx"
```

On macOS/Linux use `python3` and the actual absolute installation path with the
same `--install` option. Paths with spaces should be quoted.

Restart Studio after replacing the plugin. Grant Studio's localhost HTTP and
script-editing permissions when prompted, and match the plugin's port to the
CLI (default `25123`). No pairing token needs to be copied.

### 4. Choose a workflow

For file transfer, run `azureslop pull` or `azureslop push` in the game project
and confirm the operation in the intended Studio window.

For persistent agent control:

```sh
azureslop harness serve
```

Click **Enable harness** in Studio, then use another terminal in the same project:

```sh
azureslop harness status
azureslop harness call ping
```

The enabled harness accepts subsequent commands without a click for each one.
Use `--session ID` when more than one Studio window is connected. Stop the
harness server before using one-shot pull/push/test on the same port. Unlike
one-shot pull, `azureslop harness pull` uses the persistent connection and returns
conflicts for review without offering a force override.

For commands with JSON parameters, a UTF-8 parameter file avoids shell-specific
quoting, especially in Windows PowerShell:

```sh
azureslop harness call tree --params "@parameters.json"
```

For example, `parameters.json` can contain `{"target":["Workspace"],"depth":2}`.

The harness can inspect/edit general instances directly, but file pull/push is
**not a complete map or place serializer**. Geometry and arbitrary Model/Part
properties do not round-trip through the file workflow.

## How Studio instances map to files

AzureSlop tracks scripts by their **complete name path inside a configured
service**. Ancestor names become directories and the script name becomes the
file name. The ancestor's class does not become part of the path.

For example, consider two parts in Studio:

```text
Workspace
├── Door (Part)
│   └── Controller (Script)
└── Door (Part)
    └── Controller (Script)
```

Both scripts have the same AzureSlop path:

```text
Workspace/Door/Controller
```

They therefore share one disk file:

```text
Workspace/Door/Controller.server.lua
```

When you push or test that file, AzureSlop updates **every existing script**
with the matching path. Deleting the tracked file and pushing deletes every
matching script. This is intentional: duplicate named parts can share one
behavior implementation.

The complete path must match. These scripts do not share a file:

```text
Workspace/RoomA/Door/Controller
Workspace/RoomB/Door/Controller
```

Likewise, `Door/Controller` and `Door/OpenSound` are separate because their
script names differ. Paths are also service-scoped, so
`Workspace/Door/Controller` and `ServerStorage/Door/Controller` are unrelated.

### GUI elements and properties

Supported GUI instances are represented by `.gui.json` sidecars. The filename
is the link to the Studio instance; no separate generated ID is needed:

```text
StarterGui/HUD.gui.json                 -> StarterGui/HUD (ScreenGui)
StarterGui/HUD/Menu.gui.json            -> StarterGui/HUD/Menu (Frame)
StarterGui/HUD/Menu/Play.gui.json       -> StarterGui/HUD/Menu/Play (TextButton)
```

A sidecar is ordinary editable JSON:

```json
{
  "$schema": "azureslop-gui/v1",
  "className": "TextButton",
  "properties": {
    "BackgroundColor3": {
      "$type": "Color3",
      "r": 0.137,
      "g": 0.549,
      "b": 0.902
    },
    "Position": {
      "$type": "UDim2",
      "x": { "scale": 0.5, "offset": -80 },
      "y": { "scale": 0.5, "offset": -24 }
    },
    "Size": {
      "$type": "UDim2",
      "x": { "scale": 0, "offset": 160 },
      "y": { "scale": 0, "offset": 48 }
    },
    "Text": "Play"
  }
}
```

AzureSlop uses explicit type tags for Roblox values including `Color3`,
`Vector2`, `Vector3`, `UDim`, `UDim2`, `Rect`, enums, `ColorSequence`, and
`NumberSequence`, plus custom `Font` values. Pull formats sidecars consistently,
while comparisons ignore JSON whitespace and key order.

The supported set includes screen, surface, and billboard GUIs; common frame,
text, image, scrolling, viewport, and video objects; and common UI layout,
constraint, stroke, corner, padding, scale, gradient, and flex objects. The
plugin serializes a curated set of writable visual/layout properties. Runtime
state and Instance-reference properties such as `Adornee`, `CurrentCamera`, and
`SelectionImageObject` are intentionally omitted. Changing the class of an
existing disk entry is rejected during push; replace it in Studio and pull when
the instance class itself needs to change.

### What happens during pull

- A Part, Model, or Folder is represented only by the directory names leading
  to a tracked descendant. AzureSlop does not serialize the container itself,
  its class, or properties such as position, size, and color. Supported GUI
  instances are the exception and receive their own `.gui.json` sidecars.
- Containers without tracked scripts, values, remotes, bindables, or supported
  GUI descendants produce no files and are ignored.
- If duplicate matching scripts or GUI instances contain identical content,
  they collapse cleanly into one file.
- If duplicates contain different content, the plugin warns and blocks an
  operation that could choose or overwrite one of those versions.

### What happens during push or test

- Existing matching scripts are all updated from their shared file.
- Existing matching GUI elements are all updated from their shared sidecar
  during `push` or `test --local`.
- During `push` or `test --local`, a tracked deletion affects all existing
  instances with that same path.
- If a script file is new and its named container already exists, AzureSlop can
  create the script inside that container during `push` or `test --local`.
- If an ancestor is missing, AzureSlop creates a **Folder**, not a Part or
  Model. The filesystem does not contain enough information to reconstruct
  those instance classes or properties.
- If several same-named containers exist but none already contains the new
  script, AzureSlop creates one script under the first matching container. Add
  the scripts in Studio first if a new shared script must exist under every
  duplicate part.
- Plain `azureslop test` only updates existing scripts because its purpose is
  draft-based testing; it does not apply GUI/value changes or create/delete
  instances.

`Workspace` is not watched by the default configuration. To work with scripts
inside Workspace parts, add it to the services list:

```bash
azureslop config set services Workspace,ServerScriptService,ReplicatedStorage,StarterGui,StarterPlayer,StarterPack,ServerStorage
```

## Workflow

### Pull from Studio

Open the source place in Studio, then run:

```bash
azureslop pull
```

Open the AzureSlop plugin panel and click **Pull into disk**. The CLI writes the
snapshot and exits. AzureSlop records pulled instance paths and content hashes in
`.azureslop-state.json`; later pulls delete a missing file only if an earlier
pull tracked it. Local-only files are preserved.

Before writing, pull performs a three-way comparison for every tracked path:
the last successful snapshot, the current disk file, and the incoming Studio
version. If only Studio changed, disk is updated. If only disk changed, the
local file is preserved and remains pending for a later push. If both changed
differently, the entire pull is blocked before any project file is written.

Large pulls are encoded once and uploaded in 400 KiB batches. The CLI assembles
and validates every batch before changing any files, so an interrupted upload
does not apply a partial Studio snapshot.

`azureslop sync` remains available as a deprecated alias for `azureslop pull`.

### Push into Studio

To apply the disk snapshot to the open place, run:

```bash
azureslop push
```

In the intended Studio window, click **Push into Studio**. AzureSlop compares
the current disk files with content hashes from the last successful pull or
push. It sends only added or modified scripts, values, and GUI sidecars, plus deletions
recorded against that baseline. Unchanged files are not included. Push can
create missing tracked instances, so review the target window carefully before
confirming it.

Immediately before applying that delta, the plugin sends the current Studio
version of every affected path back to the CLI. If Studio no longer matches the
baseline, push stops without applying any change. Unrelated Studio edits do not
block a push because they are not part of the disk delta.

Older `.azureslop-state.json` files contain paths but no content hashes. The
first push after upgrading can send all existing tracked files once, but it is
accepted only when the disk and Studio content agree or Studio has no matching
instance. Successful completion upgrades the state file and later pushes are
delta-only.

Script source is still written through Studio's supported
`ScriptEditorService:UpdateSourceAsync` API. If the place has Drafts mode
enabled, those script edits can appear as drafts; structural creation and
deletion are applied directly because Roblox does not expose those as drafts.

### Test with Studio drafts

After editing on disk, run:

```bash
azureslop test
```

In the source Studio window, click **Apply drafts**. Existing scripts are
updated with Studio's draft-aware editor API. New scripts, deletions, values,
events, and GUI sidecars are skipped because those changes cannot be isolated
as script drafts. The same pre-apply version comparison protects existing
scripts. Review and commit or discard the resulting drafts in Studio.

If Drafts mode is disabled, Studio's same API updates the editor source without
the draft review layer. AzureSlop cannot enable Drafts mode for a place.

### Test in a disposable local place

First save or download a baseline place file and configure it:

```bash
azureslop config set place path/to/MyGame.rbxl
azureslop test --local
```

You can also provide a one-off baseline:

```bash
azureslop test --local path/to/MyGame.rbxlx
```

AzureSlop copies the baseline into `.azureslop-local/` and opens it. In that
new Studio window, click **Apply to local copy**. Local mode applies source
updates and also creates or removes tracked instances, making it suitable for
testing changes that do not fit Studio's existing-script draft model.

Roblox does not currently give third-party plugins a supported API to save and
open the active cloud place as a new local file. For that reason, `--local`
uses the configured baseline rather than silently cloning the active session.

## Project structure

```text
my-game/
  .azureslop
  .azureslop-state.json
  ServerScriptService/
    GameManager.server.lua
    Light1/
      ControlScript.server.lua
  ReplicatedStorage/
    Shared/
      Utils.module.lua
  StarterGui/
    HUD.gui.json
    HUD/
      Menu.gui.json
      Menu/
        Play.gui.json
```

The class-specific extensions are `.server.lua`, `.client.lua`, and
`.module.lua`. Legacy `.lua` files are read as `ModuleScript` files. AzureSlop
also maps supported value, remote, and bindable instances to dedicated file
extensions. Supported GUI instances use `.gui.json`.

## Configuration

`.azureslop` is JSON:

```json
{
  "name": "MyGame",
  "port": 25123,
  "place": "places/MyGame.rbxl",
  "services": [
    "ServerScriptService",
    "ReplicatedStorage",
    "StarterGui",
    "StarterPlayer",
    "StarterPack",
    "ServerStorage"
  ]
}
```

The `place` entry is optional unless you use `azureslop test --local` without
passing a place path on the command line.

## Safety notes

- One-shot pull/push/test require confirmation in Studio. The persistent harness
  is enabled once and can then execute commands with plugin permissions; disable
  it when not in use.
- File-workflow version conflicts block the operation before target changes.
  Direct harness edits are not a three-way merge; use guarded source writes,
  inspect results, and use Undo when appropriate.
- Servers listen on loopback. One-shot operations exchange a session token
  automatically; the harness uses window IDs and a server epoch, not bearer
  authentication. Other local processes can access an enabled harness.
- Harness timeouts do not cancel an in-flight Studio operation. Retrieve its
  job result before resubmitting a mutation. Failed mutations may leave partial
  edits recorded for Studio Undo.
- Draft mode never creates or deletes instances in a shared place.
- `.azureslop-local/` contains disposable place copies and is safe to add to
  your project's `.gitignore`.

## Verification

From the repository root (use `python3` on macOS/Linux or `py` on Windows if
`python` is not available):

```sh
python -m unittest discover -s cli/tests -v
python tools/package_plugin.py
```

With Lua 5.4 installed, run the plugin's offline tests:

```sh
lua plugin/tests/harness_test.lua
lua plugin/tests/preview_test.lua
lua plugin/tests/motion_test.lua
lua plugin/tests/vision_test.lua
```

The [CI workflow](.github/workflows/ci.yml) runs Python tests and packaging on
Windows, macOS, and Linux, plus the Lua doubles on Linux. It is configured
coverage, not a claim that remote CI has already passed. These checks cannot
verify Roblox's renderer or feature rollout. Studio validation is a separate
manual step; see the [live checklist](docs/animation-preview.md#cleanup-and-live-validation).
