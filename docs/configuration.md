# Configuration and local testing

`azureslop init` creates `.azureslop` in the game folder:

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

Use `azureslop config show` to inspect it and `azureslop config set KEY VALUE`
to update a value.

## Services

Only configured services are pulled. Add `Workspace` to include scripts under
parts and models:

```sh
azureslop config set services Workspace,ServerScriptService,ReplicatedStorage,StarterGui,StarterPlayer,StarterPack,ServerStorage
```

This still does not serialize Part/Model classes or properties; it tracks their
descendant scripts by name path.

## Local copy testing

Regular `azureslop test` updates existing Studio scripts using the draft-aware
editor API. It does not create or delete instances.

To test structural changes safely, point AzureSlop at a saved `.rbxl` or
`.rbxlx` baseline:

```sh
azureslop config set place path/to/MyGame.rbxl
azureslop test --local
```

Or supply the baseline for a single run:

```sh
azureslop test --local path/to/MyGame.rbxlx
```

AzureSlop copies that place into `.azureslop-local/`, opens the disposable
copy, and can create or remove tracked instances there. Add `.azureslop-local/`
to your project's `.gitignore` if it is not already ignored.

Roblox does not expose a supported third-party-plugin API to duplicate the
active cloud place into a new local file, so you provide the saved baseline.
