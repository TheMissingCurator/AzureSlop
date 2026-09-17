# AzureSlop documentation

Start here only after completing the short [README quickstart](../README.md#get-your-first-sync).
The README is intentionally the fast path; these pages explain behavior when
you need more than the normal sync, edit, push loop.

| If you want to… | Read… |
| --- | --- |
| Install or update the plugin | [Install and update](installation.md) |
| Know exactly what reaches disk or Studio | [File workflow](file-workflow.md) |
| Recover when Studio and disk both changed | [Resolve conflicts](conflicts.md) |
| Change services, port, or test a disposable place copy | [Configuration](configuration.md) |
| Connect an AI client to Studio | [Roblox Studio MCP](https://create.roblox.com/docs/studio/mcp) |
| Find the removed agent harness source | [Legacy archive](../legacy/README.md) |

## Scope

AzureSlop transfers script sources, supported values/events, and supported GUI
definitions. It is not a replacement for saving a Roblox place: geometry,
terrain, arbitrary Models/Parts, and unsupported properties remain in Studio.

For a new AI-assisted workflow, prefer Studio MCP. AzureSlop's harness docs are
preserved under `legacy/`, outside the release package.
