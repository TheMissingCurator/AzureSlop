# AzureSlop

AzureSlop moves Roblox Studio scripts between Studio and your filesystem with
explicit, Git-like operations. It infers the project structure from Studio's
instance hierarchy, so no Rojo project manifest is required.

It is deliberately not a live sync bridge:

- `azureslop sync` pulls one Studio snapshot to disk and exits.
- `azureslop test` applies disk changes to existing Studio scripts through
  `ScriptEditorService:UpdateSourceAsync`, which creates drafts when the place
  has Drafts mode enabled.
- `azureslop test --local` copies a configured `.rbxl` or `.rbxlx` baseline,
  opens the disposable copy, and can create or delete instances as well as
  update scripts.

## Setup

### 1. Install the CLI

```bash
cd cli
pip install -e .
```

### 2. Initialize a project

```bash
mkdir my-game
cd my-game
azureslop init
```

### 3. Install the Studio plugin

Copy `plugin/AzureSlop.lua` into the Roblox Studio plugins folder, or install it
as a local plugin from Studio. Enable **Allow HTTP Requests** in the place's
Game Settings so the plugin can reach the CLI on localhost.

## Workflow

### Pull from Studio

Open the source place in Studio, then run:

```bash
azureslop sync
```

Open the AzureSlop plugin panel and click **Pull into disk**. The CLI writes the
snapshot and exits. AzureSlop records pulled instance paths in
`.azureslop-state.json`; later pulls delete a missing file only if an earlier
pull tracked it. Local-only files are preserved.

### Test with Studio drafts

After editing on disk, run:

```bash
azureslop test
```

In the source Studio window, click **Apply drafts**. Existing scripts are
updated with Studio's draft-aware editor API. New scripts, deletions, values,
and events are skipped because those changes cannot be isolated as script
drafts. Review and commit or discard the resulting drafts in Studio.

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
```

The class-specific extensions are `.server.lua`, `.client.lua`, and
`.module.lua`. Legacy `.lua` files are read as `ModuleScript` files. AzureSlop
also maps supported value, remote, and bindable instances to dedicated file
extensions.

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

- Every command is one-shot and requires a click in the intended Studio window.
- The CLI binds only to `localhost` and uses a per-command session token.
- Draft mode never creates or deletes instances in a shared place.
- `.azureslop-local/` contains disposable place copies and is safe to add to
  your project's `.gitignore`.
