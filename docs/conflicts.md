# Resolve conflicts

AzureSlop compares the last successful snapshot with the current disk and
Studio versions before a pull, push, or regular test. If the same tracked path
changed differently on both sides, it stops before applying any change.

This is expected protection, not a failed sync. Do not keep rerunning a force
operation: decide which version should win first.

## Choose a version for each path

Leave the original `azureslop pull`, `push`, or `test` command running. In a
second terminal in the same project, run:

```sh
azureslop resolve
```

Choose **disk** or **Studio** for every listed path, then return to Studio and
click **Apply resolution**. AzureSlop verifies neither side changed after your
choice. A new edit becomes a new conflict instead of applying a stale choice.

## Make all conflicts choose one side

The Studio panel offers a deliberate override:

- **Pull anyway** keeps Studio's version for every pull conflict.
- **Push anyway** keeps disk's version for every push or test conflict.

Each requires a second confirmation. Use it only when every conflicting path
really should have the same winner.

## Why conflicts can return

The command's baseline is updated only after a successful operation. If an
operation is interrupted, targets a different Studio window, or changes occur
again before resolution, AzureSlop must re-check and can report a conflict
again. Confirm the correct Studio place and finish one guarded operation before
starting the next one.

## Duplicate names

AzureSlop maps scripts by their complete name path inside a service. Two
same-named containers with same-named scripts map to one disk file. If their
contents differ, the plugin blocks the operation rather than selecting one.
Rename or reorganize them in Studio if they must have independent sources.
