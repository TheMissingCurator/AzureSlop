# Install and update

AzureSlop needs two local pieces: the Python CLI in your terminal and the
`AzureSlop.rbxmx` package in Roblox Studio. Install them once, then each game
only needs `azureslop init`.

## Requirements

- Python 3.10 or newer.
- Roblox Studio on Windows or macOS. Linux use requires an unofficial Wine or
  Vinegar environment; the CLI itself is cross-platform.
- A local clone of this repository.

## Build the package

From the repository root:

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

The result is `dist/AzureSlop.rbxmx`. Do not install only
`plugin/AzureSlop.lua`; the packaged file includes its Lua modules.

## Put it in Studio

Copy `dist/AzureSlop.rbxmx` into the local Plugins folder used by your Studio
installation and restart Studio. The packager can do the copy when given the
full target path. It creates a timestamped backup before replacing an existing
package.

Windows example:

```powershell
py tools/package_plugin.py --install "$env:LOCALAPPDATA/Roblox/Plugins/AzureSlop.rbxmx"
```

On macOS, use Studio's local Plugins directory and `python3`. On Linux, use
the Plugins directory inside the Wine/Vinegar Studio prefix—not a native Linux
application directory. Quote paths that contain spaces.

If the command cannot find its target, create or locate the correct Plugins
directory first and pass the absolute package filename again.

## First Studio prompt

Open the AzureSlop panel after Studio restarts. When Studio requests access,
allow the plugin's localhost HTTP and script-editing permissions. The default
port is `25123`; leave the panel and project config at that value unless you
have a concrete port conflict.

## Updating

Pull the repository update, rebuild with `tools/package_plugin.py`, replace
the installed package, and restart Studio. Existing project folders and
`.azureslop` settings stay intact.

## Check the installation

In a game folder, run:

```sh
azureslop init
azureslop status
```

Then run `azureslop pull` and confirm it from the AzureSlop panel. See the
[quickstart](../README.md#get-your-first-pull) for the normal flow.
