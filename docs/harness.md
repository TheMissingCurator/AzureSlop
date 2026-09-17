# AzureSlop Studio harness

> **Archived reference for AzureSlop 0.7.** The commands below are absent from
> the current CLI and plugin. The old source is in [legacy](../legacy/README.md).
> For a current agent connection, use
> [Roblox Studio's built-in MCP server](https://create.roblox.com/docs/studio/mcp).

The harness lets GPT-6 in Codex (or another agent with terminal access) inspect
and edit a local Roblox Studio place. It is part of the existing AzureSlop CLI
and plugin, with no additional Python dependencies, API keys, pairing tokens,
or `.bridge.json` file. The agent uses its existing terminal tool; this is not
a separate OpenAI model runner or an MCP server.

## Start

Install the CLI from this repository with `pip install -e ./cli`. Build the
updated plugin from the repository root:

```sh
python tools/package_plugin.py
```

Install `dist/AzureSlop.rbxmx` as a local Studio plugin, replacing the existing
AzureSlop plugin. The packager can also update an exact existing installation
path and save a timestamped backup:

```sh
python tools/package_plugin.py --install /absolute/path/to/Plugins/AzureSlop.rbxmx
```

Restart Studio to load the updated plugin. In your game project directory:

```sh
azureslop init --name MyGame   # only if this directory has no .azureslop yet
azureslop harness serve
```

Leave that terminal running. Open the AzureSlop panel in the intended Studio
window and click **Enable harness**. The port is the existing `.azureslop`
port (25123 by default); match it in the panel. Grant Studio's localhost HTTP
and script-editing permissions if prompted. There is no token to copy.

In another terminal, from the same game directory:

```sh
azureslop harness status
azureslop harness call ping
azureslop harness call tree --params '{"target":["Workspace"],"depth":2,"limit":200}'
```

The server keeps running after each command. **Disable harness**, closing the
panel, or closing Studio stops that window accepting new commands. Restarting
the server requires enabling the harness again. `--port NUMBER` is available
on each harness subcommand.

Two enabled Studio windows require an explicit `--session ID` on calls and
pulls; IDs and place names appear in `harness status`. These IDs route commands
to a window. The automatically exchanged server epoch detects restarts; it is
not an authentication token.

## Agent workflow

Give the agent the project directory and this document. Example instruction:

> Use the AzureSlop harness in this project to inspect my open Studio place.
> Start with `azureslop harness status` and `call tree`. Use returned instance
> IDs for ambiguous names. Read scripts before editing, check their previous
> source with `expected`, and verify changes by reading them back. Do not
> resubmit an uncertain mutation: inspect its job result first.

The normal loop is inspect, change, read back, then test in Studio. No specific
model name or OpenAI API credentials belong in the bridge or Roblox plugin.
Codex can run these commands using its terminal access; see the official
[Codex documentation](https://developers.openai.com/codex/).

## Commands

All calls print one JSON result to stdout. A job ID and retrieval command go to
stderr before submission. Exit codes are 0 for success, 1 for errors, and 2
for pending, expired, or uncertain execution. Arguments accept JSON inline or
`--params @parameters.json`. For `execute` and `write_source`, use
`--source path/to/code.luau` to load UTF-8 source without shell escaping.

| Method | Parameters | Result |
| --- | --- | --- |
| `ping` | none | Place, play state, protocol, watched services |
| `tree` | `target` (default Workspace), `depth` (0–8), `limit` (1–2000) | Instance tree with IDs, child counts, truncation flag |
| `get` | `target`, optional `properties` array | Properties and attributes |
| `selection` | optional `targets` array | Current selection; sets it when targets are supplied |
| `create` | `class`, `name`, `parent`, `properties` | Created instance ID |
| `set` | `target`, `properties`, optional `parent`, `attributes` | Updated instance |
| `delete` | `target` | Detached instance, restorable with Studio Undo |
| `read_source` | `target` | Current editor source, including drafts |
| `write_source` | `target`, `source`, optional `expected` | Bytes written; rejects a mismatched expected source |
| `execute` | `source` | Return value from Luau executed in plugin context |
| `logs` | optional `after` cursor | Up to 200 recent output messages, next cursor |
| `snapshot` | none | AzureSlop scripts, values, events and GUI snapshot plus ambiguous paths |

Protocol 2 adds R6 animation previews, reversible keyframe edits, motion
diagnostics, and native viewport images. See [Animation preview and vision](animation-preview.md)
for the full command reference and offline/live validation boundaries.

`target` and `parent` are either exact name arrays such as
`["Workspace","Model","Part"]`, or ID objects such as `{"id":"..."}`.
An empty path addresses the DataModel. Names containing dots or slashes remain
single array elements. Duplicate names are rejected by path; use IDs from the
parent's tree. IDs last for the plugin lifetime and fail when the instance is
removed. Selection changes do not create a place undo recording.

Properties use AzureSlop's existing JSON types:

```sh
azureslop harness call create --params '{"class":"Part","name":"HarnessDemo","parent":["Workspace"],"properties":{"Anchored":true,"Size":{"$type":"Vector3","x":12,"y":1,"z":12},"Position":{"$type":"Vector3","x":0,"y":5,"z":0}}}'
azureslop harness call get --params '{"target":["Workspace","HarnessDemo"],"properties":["Anchored","Size","Position"]}'
azureslop harness call selection --params '{"targets":[["Workspace","HarnessDemo"]]}'
```

Other supported values include Color3 (`r/g/b`, 0–1), Vector2 (`x/y`),
UDim (`scale/offset`), UDim2 (`x/y` UDim objects), Rect (`min/max` vectors),
Enum (`enum/value`, e.g. `{"$type":"Enum","enum":"Material","value":"Neon"}`),
Font, ColorSequence, NumberSequence, CFrame (`components` from GetComponents),
and Instance (`{"$type":"Instance","target":{"id":"..."}}`).

Luau execution runs inside a temporary ModuleScript with `context.resolve(ref)`
and `context.selection` available, along with normal Roblox globals:

```lua
local part = context.resolve({"Workspace", "HarnessDemo"})
part.Material = Enum.Material.Neon
return {name = part.Name, position = part.Position}
```

Save this to `demo.luau` and run `azureslop harness call execute --source demo.luau`.
The temporary module is removed after return or error; LoadStringEnabled is
not required. This executes with plugin permissions. Finish synchronously;
background tasks can outlive the command and its undo recording. Infinite
loops can stall Studio and cannot be forcibly cancelled by the Python bridge.

## Pull to disk and existing sync commands

```sh
azureslop harness pull
```

This requests a complete Studio snapshot and applies AzureSlop's existing
three-way merge and baseline tracking in the harness's project directory.
It preserves disk-only edits and blocks all writes on conflicting or ambiguous
paths. Unreadable sources fail the snapshot so they cannot be mistaken for
deletions. Results upload in 400 KiB batches and are reassembled before merging.
The limit is 64 batches (25 MiB of JSON); an oversized result fails without
applying a partial snapshot.

Harness pull reports conflicts as JSON; it does not silently force them. To use
the existing interactive resolver or **Pull anyway** workflow, stop
`harness serve` with Ctrl+C and run normal `azureslop pull`. Likewise, stop
the harness before using normal `push` or `test` on the same port. The harness
provides direct source edits while connected; it does not replace guarded
disk-to-Studio push or change the baseline on every direct Studio edit.

## Recovery and boundaries

Jobs are delivered at most once within a server lifetime. The plugin retains
completed results and retries their upload without rerunning the command. Use
`azureslop harness result JOB_ID` after a lost response or CLI timeout.
`call --id JOB_ID` can retry a lost submission with identical arguments while
the server still retains that ID. Never reuse an ID after server restart or
result expiry to assume an edit is deduplicated.

The default CLI wait is 30 seconds (`--timeout 90` overrides it). Timeout stops
waiting; it does not cancel the command. Queued jobs expire after 120 seconds.
Dispatched jobs become `unknown` after 120 seconds and keep blocking subsequent
jobs in that window until a late result arrives. Inspect Studio before starting
a fresh session. Completed/expired jobs remain in memory until an hour after
their original deadline; restart loses the queue and results.

Editing methods require Edit mode and use Studio undo recordings. Partial
changes after an error may remain and are recorded for Undo; this is not an
atomic rollback. Disposable preview edits use their own revision-guarded undo
stack; `preview_export` creates a normal Studio undo recording. Native screenshots
require Studio's screenshot permission. Save/publish, mouse/keyboard input, and
starting Play are outside this version's command set. The harness does not expose an
internet endpoint: it binds to `127.0.0.1`, rejects browser Origin headers and
unexpected Host headers, and uses no bearer authentication. Other processes
on your computer can call it while enabled.

## Verification

```sh
python -m unittest discover -s cli/tests -v
lua plugin/tests/harness_test.lua
lua plugin/tests/preview_test.lua
lua plugin/tests/motion_test.lua
lua plugin/tests/vision_test.lua
python tools/package_plugin.py
```

Tests exercise real HTTP with simulated Studio peers, batched results,
deduplication, expiry, session routing, and pull conflict protection. The Lua
test runs the actual harness block with Studio API mocks, including source
guards, undo, duplicate instance names, and dropped-result retries. Live Studio
validation still requires the plugin to be loaded and enabled: run the create,
get, and selection example, use Undo, and verify that the part disappears.

Studio API references: [ScriptEditorService](https://create.roblox.com/docs/reference/engine/classes/ScriptEditorService)
and [ChangeHistoryService](https://create.roblox.com/docs/reference/engine/classes/ChangeHistoryService).
