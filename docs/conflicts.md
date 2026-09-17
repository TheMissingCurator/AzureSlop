# Resolve conflicts

Run `azureslop sync` before pushing changes to a Team Create place. Push checks
all watched Studio paths against the last successful sync. If a teammate made
an edit, push stops without applying your disk changes. Run sync and review the
new files before pushing again.

## If both sides changed the same file

Sync stops before writing any files and opens a conflict in the AzureSlop
panel. The panel shows each path and its reason, one at a time:

- **Keep local** preserves the disk version. After sync succeeds, that file is
  still pending for your next push.
- **Use Studio** replaces the local version with the current Studio version.
  AzureSlop saves your old local file under `.azureslop-conflicts/` first.

When you choose **Keep local**, AzureSlop also saves the Studio copy there.
Compare the two versions and incorporate your teammate's changes before the
next push. The folder is outside the watched services, so it is never pushed.
You can add `.azureslop-conflicts/` to your game's `.gitignore` after reviewing
the saved copies.

Choose a side for every path. The plugin sends the choices and retries the
sync automatically. If either copy changes meanwhile, the choice is rejected
and the new conflict is shown again.

## Duplicate Studio instances

Two same-named containers with same-named scripts map to one disk file. When
their sources differ, AzureSlop cannot safely choose one. Fix the duplicate
names or sources in Studio, then click **Fix duplicates, then retry**. The
plugin will not offer a blind overwrite for that case.

## Why a conflict can reappear

The baseline updates only after a successful sync. A teammate may edit again
while you review; the plugin then reports the new version rather than applying
your older choice. Keep the terminal command running while using the panel and
confirm you are in the intended Studio place.

The older `azureslop resolve` CLI remains as an advanced fallback, but the
normal workflow is entirely in the plugin panel.
