"""
AzureSlop CLI
"""

import argparse
import sys

VERSION = "0.2.0"


def main():
    parser = argparse.ArgumentParser(
        prog="azureslop",
        description="Sync Roblox Studio scripts with your local filesystem.",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"azureslop {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # ── init ─────────────────────────────────────────────────────────────────
    init_p = subparsers.add_parser(
        "init",
        help="Initialize a new AzureSlop project in the current directory",
        description="Creates a .azureslop config file in the current directory.",
    )
    init_p.add_argument(
        "--name", "-n",
        metavar="NAME",
        help="Project name (skips the interactive prompt)",
    )

    # ── sync ─────────────────────────────────────────────────────────────────
    sync_p = subparsers.add_parser(
        "sync",
        help="Start the sync server",
        description=(
            "Starts the local HTTP server that the Studio plugin polls. "
            "VS Code edits win for existing scripts; new scripts created in "
            "Studio are pushed to disk automatically."
        ),
    )
    sync_p.add_argument(
        "--port", "-p",
        type=int,
        metavar="PORT",
        help="Port to listen on (overrides the value in .azureslop)",
    )

    # ── status ───────────────────────────────────────────────────────────────
    subparsers.add_parser(
        "status",
        help="Show project info and whether the sync server is running",
        description="Prints the current project config and pings the sync server.",
    )

    # ── config ───────────────────────────────────────────────────────────────
    config_p = subparsers.add_parser(
        "config",
        help="Show or edit project configuration",
        description="Manage the .azureslop project config file.",
    )
    config_sub = config_p.add_subparsers(dest="config_command", metavar="<subcommand>")

    config_sub.add_parser(
        "show",
        help="Print the current configuration",
    )

    config_set_p = config_sub.add_parser(
        "set",
        help="Set a configuration value",
        description=(
            "Supported keys: name (string), port (integer), "
            "services (comma-separated list, e.g. ServerScriptService,ReplicatedStorage)"
        ),
    )
    config_set_p.add_argument("key", help="Config key to update")
    config_set_p.add_argument("value", help="New value")

    # ─────────────────────────────────────────────────────────────────────────

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        from azureslop.commands.init import cmd_init
        cmd_init(name=args.name)

    elif args.command == "sync":
        from azureslop.commands.sync import cmd_sync
        cmd_sync(port_override=args.port)

    elif args.command == "status":
        from azureslop.commands.status import cmd_status
        cmd_status()

    elif args.command == "config":
        from azureslop.commands.config_cmd import cmd_config
        cmd_config(args)


if __name__ == "__main__":
    main()
