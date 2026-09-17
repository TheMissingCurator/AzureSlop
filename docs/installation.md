# Install and update

AzureSlop has a Python CLI and one Roblox Studio plugin. The ready-made
[plugin package](../releases/AzureSlop.rbxmx) means users do not need to run
the source packager.

## Install the CLI

Python 3.10+ and Git are required for the current direct GitHub install:

```powershell
# Windows PowerShell
py -m pip install "git+https://github.com/TheMissingCurator/AzureSlop.git#subdirectory=cli"
```

```sh
# macOS or Linux
python3 -m pip install "git+https://github.com/TheMissingCurator/AzureSlop.git#subdirectory=cli"
```

From a cloned repository, use `py -m pip install -e ./cli` or
`python3 -m pip install -e ./cli` instead. Ensure your Python scripts directory
is on `PATH` so the `azureslop` command is available.

## Install the plugin

Download [releases/AzureSlop.rbxmx](../releases/AzureSlop.rbxmx) (on GitHub,
use **Download raw**) and put it
in Studio's local Plugins folder. Restart Studio. On Windows the folder is
usually `%LOCALAPPDATA%\Roblox\Plugins`. On macOS use Studio's local Plugins
folder. Linux users running Studio via Wine or Vinegar should use the Plugins
folder inside that Studio prefix.

In Studio, open the AzureSlop panel. Grant localhost HTTP and script-editing
permissions when Studio asks. The default port is `25123`; keep the panel and
project configuration at the same value.

## Verify

Open a place, then in a game folder run:

```sh
azureslop init
azureslop sync
```

Click **Sync from Studio** in the docked AzureSlop panel. The command should
finish and create files under the configured services. See the
[README](../README.md#get-your-first-sync) for the edit and push loop.

## Update or develop from source

Users of the local plugin should download the latest ready-made package and
replace the old file. If building from a clone, run:

```sh
python3 tools/package_plugin.py
```

The output is `dist/AzureSlop.rbxmx`. Install an exact target with a backup:

```powershell
py tools/package_plugin.py --install "$env:LOCALAPPDATA/Roblox/Plugins/AzureSlop.rbxmx"
```

Restart Studio after replacing a local plugin. The release plugin has no
harness ModuleScripts; those sources live in [legacy](../legacy/README.md).

When preparing a repository release, also rebuild the tracked download with
`python3 tools/package_plugin.py --output releases/AzureSlop.rbxmx`. The package
test checks that this file matches the current plugin source.

For a downloadable GitHub Release package, push a new `v*` tag. The
[release workflow](../.github/workflows/release.yml) builds the plugin and
attaches `AzureSlop.rbxmx` to that tag's GitHub Release.
