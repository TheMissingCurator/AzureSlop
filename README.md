# AzureSlop

A Rojo alternative that infers your Roblox project structure from Studio's instance hierarchy — no JSON manifests required.

## How it works

- **Same name = same behavior.** Multiple parts named `Light1` in the same service all share one script on disk. Edit once, update everywhere.
- **Service-scoped.** `ServerScriptService/Light1` and `ReplicatedStorage/Light1` are treated as completely separate things.
- **Only scripts matter.** Instances with no scripts anywhere in their descendants are ignored entirely.
- **Last write wins.** Edit in VS Code or Studio — whichever saved most recently wins on the next sync cycle (~5 seconds).

## Setup

### 1. Install the CLI

```bash
cd cli
pip install -e .
```

### 2. Init a project

```bash
mkdir my-game
cd my-game
azureslop init
```

This drops a `.azureslop` config file. Edit it to choose which services to watch.

### 3. Start syncing

```bash
azureslop sync
```

Starts the local HTTP server on `localhost:25123`.

### 4. Install the plugin

Copy `plugin/AzureSlop.lua` into your Roblox Studio plugins folder:

```
~/.local/share/Roblox/Plugins/AzureSlop.lua
```

Activate it in Studio. On first connect it will dump all watched services to disk and build the folder structure automatically.

Open your editor of choice and start working. Changes in either Studio or your editor will propagate within ~5 seconds.

## Project structure

```
my-game/
  .azureslop                  ← project config
  ServerScriptService/
    GameManager.server.lua
    Light1/
      ControlScript.server.lua
  ReplicatedStorage/
    Shared/
      Utils.lua
  StarterGui/
    MainMenu/
      ButtonHandler.client.lua
```

## Config (.azureslop)

```json
{
  "name": "MyGame",
  "port": 25123,
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

## Architecture

- **CLI** — Python HTTP server + filesystem watcher. Two endpoints: `GET /changes` and `POST /update`.
- **Plugin** — Lua plugin that polls the CLI every 5 seconds. On first connect, pushes all scripts to disk.

## Contributing

This is early-stage. The core sync loop, conflict handling, and edge cases around deeply nested hierarchies are all areas that need work.
