# AzureSlop

Edit Roblox scripts on disk, then sync and push them from a small Studio
plugin. No Rojo manifest, project generator, or always-running process.

AzureSlop is for a simple loop:

1. Sync the scripts and supported GUI data from an open place into normal files.
2. Edit those files in the editor you already use.
3. Push only your changed files back to that Studio place.

It is deliberately an on-demand file workflow, not a full place serializer.
Models, Parts, terrain, and arbitrary instance properties stay in Studio.

> For AI-agent control, use [Roblox Studio's built-in MCP server](https://create.roblox.com/docs/studio/mcp).
> The former AzureSlop harness is [archived](legacy/README.md) and absent from
> the release plugin and CLI.

## Get your first sync

You need [Roblox Studio](https://create.roblox.com/docs/studio/setup) and Python
3.10+. Open the place you want to work on in Studio before step 3.

### 1. Install the CLI

Install directly from GitHub (Git must be installed):

```powershell
py -m pip install "git+https://github.com/TheMissingCurator/AzureSlop.git#subdirectory=cli"
```

```sh
python3 -m pip install "git+https://github.com/TheMissingCurator/AzureSlop.git#subdirectory=cli"
```

If you're working from a clone, `py -m pip install -e ./cli` (or `python3`)
also works.

### 2. Install the plugin once

Download the ready-made [AzureSlop.rbxmx](releases/AzureSlop.rbxmx) package.
Put it in Studio's local Plugins folder, then restart
Studio. On Windows, that folder is normally `%LOCALAPPDATA%\Roblox\Plugins`.
Detailed Windows, macOS, Linux/Vinegar, and update instructions are in
[Install the plugin](docs/installation.md).

### 3. Create a folder for your game and sync

```sh
mkdir my-game
cd my-game
azureslop init
azureslop sync
```

While `azureslop sync` is waiting, open the **AzureSlop** panel in the already
open Studio window and click **Sync from Studio**. The command finishes and your
files appear in `my-game/`.

### 4. Edit, then push

Edit a pulled `.server.lua`, `.client.lua`, `.module.lua`, or supported
`.gui.json` file. Then run:

```sh
azureslop push
```

Click **Push into Studio** in that same Studio window. AzureSlop sends only
the changed files. That is the entire normal loop.

## What to know before the second sync

- Sync and push are explicit commands; nothing continuously runs in the
  background.
- The plugin asks for confirmation before each file operation. Grant Studio's
  localhost HTTP and script-editing permissions if it prompts you.
- Push checks the whole watched Studio snapshot against your last sync. If a
  teammate changed something, run `azureslop sync` first. If both sides changed
  the same file, choose **Keep local** or **Use Studio** in the plugin panel.
  See [Resolve conflicts](docs/conflicts.md).
- `Workspace` is not included by default. Add it only when you need scripts
  beneath Workspace objects:

  ```sh
  azureslop config set services Workspace,ServerScriptService,ReplicatedStorage,StarterGui,StarterPlayer,StarterPack,ServerStorage
  ```

## Documentation

- [Documentation home](docs/README.md) — choose the topic you need.
- [Install and update](docs/installation.md) — platforms, permissions, and
  replacing the plugin.
- [File workflow](docs/file-workflow.md) — what pulls, pushes, tests, and how
  Studio instances map to files.
- [Resolve conflicts](docs/conflicts.md) — safe recovery when both sides changed.
- [Configuration](docs/configuration.md) — services, ports, and disposable
  local-place testing.
- [Studio MCP](https://create.roblox.com/docs/studio/mcp) — recommended agent
  connection.
- [Archived harness](legacy/README.md) — source retained for reference.

## License

Copyright (c) 2026 Slop Enterprises. AzureSlop is licensed under
[GPL-3.0-only](License.md).
