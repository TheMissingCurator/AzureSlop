# File workflow

The normal workflow is:

```text
Studio place → azureslop sync → edit files → azureslop push → Studio place
```

Each operation is one-shot and confirmed in Studio. AzureSlop is not a live
sync process.

## Sync from Studio

`azureslop sync` reads one snapshot from the Studio window you confirm and
writes it to disk. It records the result in `.azureslop-state.json`; later
syncs delete a missing file only when AzureSlop previously tracked it.
Local-only files are preserved.

Large snapshots are uploaded in safe-sized batches and assembled before files
change, so an interrupted upload does not write a partial snapshot.

## Push

`azureslop push` sends additions, modifications, and tracked deletions since
the last successful sync or push. Unchanged files are not sent. Before sending,
it checks the complete watched Studio snapshot against that baseline. If any
watched path changed in Studio, including one unrelated to your local edit,
push stops and asks you to sync first. It can create missing tracked instances,
so confirm the intended Studio window carefully.

Script source is written through Studio's `ScriptEditorService:UpdateSourceAsync`.
With Drafts mode, those script edits can appear as drafts. Structural changes
are direct because Roblox does not expose structural drafts.

## Test

`azureslop test` applies disk changes only to existing scripts through the
draft-aware editor API. It does not create/delete instances or apply GUI/value
changes. Use `azureslop test --local` for a disposable saved-place copy; see
[Configuration](configuration.md#local-copy-testing).
After applying or reviewing drafts in the shared place, run `azureslop sync`
before the next push or regular test so the baseline includes Studio's current
editor source.

## What becomes files

Scripts map to their complete name path inside a configured service:

```text
ServerScriptService/GameManager.server.lua
ReplicatedStorage/Shared/Utils.module.lua
StarterGui/HUD.gui.json
```

The script extensions are `.server.lua`, `.client.lua`, and `.module.lua`.
Supported GUI instances receive `.gui.json` sidecars containing curated visual
and layout properties. Supported values, remotes, and bindables use dedicated
file extensions.

A Part, Model, or Folder is only represented by directories leading to a
tracked descendant. AzureSlop does not save its class, geometry, position,
size, color, terrain, or arbitrary properties.

## Duplicate paths

The container's class is not in the path. Therefore two `Workspace/Door`
objects that both contain `Controller` scripts map to the same file:

```text
Workspace/Door/Controller.server.lua
```

Pushing it updates every matching existing script. If the duplicates have
different source, AzureSlop blocks rather than silently choosing one. See
[Resolve conflicts](conflicts.md).

## Guardrails

Before any write, AzureSlop compares the prior snapshot, disk, and Studio.
Changes on both sides stop the operation. Read [Resolve conflicts](conflicts.md)
to understand the per-file choices in the panel. `azureslop pull` remains an
alias for `azureslop sync` for existing projects.
