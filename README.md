# AzureSlop

Edit Roblox scripts on disk, then pull and push them from a small Studio
plugin. No Rojo manifest, project generator, or always-running sync process.

AzureSlop is for a simple loop:

1. Pull the scripts and supported GUI data from an open place into normal files.
2. Edit those files in the editor you already use.
3. Push only your changed files back to that Studio place.

It is deliberately an on-demand file workflow, not a full place serializer.
Models, Parts, terrain, and arbitrary instance properties stay in Studio.

> For AI-agent control, use [Roblox Studio's built-in MCP server](https://create.roblox.com/docs/studio/mcp).
> AzureSlop's old harness is retained for existing users but is not needed for
> a new agent setup.

## Get your first pull

You need [Roblox Studio](https://create.roblox.com/docs/studio/setup), Python
3.10+, and this repository. Open the place you want to work on in Studio before
starting step 3.

### 1. Install the CLI and build the plugin

From the AzureSlop repository root, use one of these:

```powershell
# Windows PowerShell
py -m pip install -e ./cli
py tools/package_plugin.py
```

```sh
# macOS or Linux
python3 -m pip install -e ./cli
python3 tools/package_plugin.py
```

This creates `dist/AzureSlop.rbxmx`.

### 2. Install the plugin once

Put `dist/AzureSlop.rbxmx` in Studio's local Plugins folder, then restart
Studio. On Windows, that folder is normally `%LOCALAPPDATA%\Roblox\Plugins`.
The packager can replace an existing installed copy and save a backup:

```powershell
py tools/package_plugin.py --install "$env:LOCALAPPDATA/Roblox/Plugins/AzureSlop.rbxmx"
```

Detailed Windows, macOS, Linux/Vinegar, and update instructions are in
[Install the plugin](docs/installation.md).

### 3. Create a folder for your game and pull

```sh
mkdir my-game
cd my-game
azureslop init
azureslop pull
```

While `azureslop pull` is waiting, open the **AzureSlop** panel in the already
open Studio window and click **Pull into disk**. The command finishes and your
files appear in `my-game/`.

### 4. Edit, then push

Edit a pulled `.server.lua`, `.client.lua`, `.module.lua`, or supported
`.gui.json` file. Then run:

```sh
azureslop push
```

Click **Push into Studio** in that same Studio window. AzureSlop sends only
the changed files. That is the entire normal loop.

## What to know before the second pull

- Pull and push are explicit commands; nothing continuously syncs in the
  background.
- The plugin asks for confirmation before each file operation. Grant Studio's
  localhost HTTP and script-editing permissions if it prompts you.
- AzureSlop stops if a file changed both on disk and in Studio. See
  [Resolve conflicts](docs/conflicts.md); do not retry or force an operation
  blindly.
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
- [Legacy harness](docs/harness.md) and [animation preview](docs/animation-preview.md)
  — kept for existing installations.

## License

Copyright (c) 2026 Slop Enterprises. AzureSlop is licensed under
[GPL-3.0-only](License.md).
