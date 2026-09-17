# Archived agent harness

This directory preserves the old AzureSlop agent bridge and its offline tests.
The release CLI no longer exposes `azureslop harness`, and the release plugin
does not contain its preview, motion, or vision modules.

The original plugin source is [plugin/AzureSlop.lua](plugin/AzureSlop.lua).
The Python bridge code is under [cli](cli/), and its test doubles are under
[tests](tests/). It is kept for reference, not maintained as a runnable release.
For a current agent connection, use
[Roblox Studio MCP](https://create.roblox.com/docs/studio/mcp).
