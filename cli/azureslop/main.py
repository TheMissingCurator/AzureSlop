"""
AzureSlop CLI
"""

import argparse
import sys

VERSION = "0.7.0"


def main():
    parser = argparse.ArgumentParser(
        prog="azureslop",
        description="Push and pull Roblox Studio sources and GUI definitions on demand.",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"azureslop {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    from azureslop.commands.harness import add_parser
    add_parser(subparsers)

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

    # ── pull / sync ──────────────────────────────────────────────────────────
    pull_p = subparsers.add_parser(
        "pull",
        help="Pull the active Studio place into the current project",
        description=(
            "Waits for the Studio plugin, pulls one snapshot into the current "
            "project, then exits."
        ),
    )
    pull_p.add_argument(
        "--port", "-p",
        type=int,
        metavar="PORT",
        help="Port to listen on (overrides the value in .azureslop)",
    )

    sync_p = subparsers.add_parser(
        "sync",
        help="Deprecated alias for `azureslop pull`",
        description="Backward-compatible alias for `azureslop pull`.",
    )

    # ── push ─────────────────────────────────────────────────────────────────
    push_p = subparsers.add_parser(
        "push",
        help="Push added and changed files into the active Studio place",
        description=(
            "Applies files added or modified since the last pull/push to the "
            "selected Studio window, plus tracked deletions, then exits."
        ),
    )
    push_p.add_argument(
        "--port", "-p",
        type=int,
        metavar="PORT",
        help="Port to listen on (overrides the value in .azureslop)",
    )
    sync_p.add_argument(
        "--port", "-p",
        type=int,
        metavar="PORT",
        help="Port to listen on (overrides the value in .azureslop)",
    )

    # ── test ─────────────────────────────────────────────────────────────────
    test_p = subparsers.add_parser(
        "test",
        help="Apply local sources to Studio for testing",
        description=(
            "Applies local sources to existing scripts through Studio's draft-aware "
            "script editor API. With --local, copies and opens a configured place "
            "file and allows instance creation and deletion in that disposable copy."
        ),
    )
    test_p.add_argument(
        "--local",
        nargs="?",
        const="",
        metavar="PLACE",
        help=(
            "test in a disposable copy; optionally provide the .rbxl/.rbxlx baseline "
            "instead of the configured 'place' value"
        ),
    )

    # ── resolve ──────────────────────────────────────────────────────────────────────────────
    resolve_p = subparsers.add_parser(
        "resolve",
        help="Resolve a waiting pull/push conflict path by path",
        description=(
            "Connects to a running AzureSlop command and asks whether disk or "
            "Studio should win for each conflicting path."
        ),
    )
    resolve_p.add_argument(
        "--port", "-p",
        type=int,
        metavar="PORT",
        help="Port used by the waiting command (overrides the value in .azureslop)",
    )
    test_p.add_argument(
        "--port", "-p",
        type=int,
        metavar="PORT",
        help="Port to listen on (overrides the value in .azureslop)",
    )

    # ── status ───────────────────────────────────────────────────────────────
    subparsers.add_parser(
        "status",
        help="Show project info and whether an action is waiting",
        description="Prints the current project config and pings the action server.",
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
            "Supported keys: name (string), port (integer), place (path), "
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

    if args.command == "harness":
        from azureslop.commands.harness import cmd_harness
        cmd_harness(args)

    elif args.command == "init":
        from azureslop.commands.init import cmd_init
        cmd_init(name=args.name)

    elif args.command in {"pull", "sync"}:
        from azureslop.commands.sync import cmd_pull, cmd_sync
        command = cmd_pull if args.command == "pull" else cmd_sync
        command(port_override=args.port)

    elif args.command == "push":
        from azureslop.commands.push import cmd_push
        cmd_push(port_override=args.port)

    elif args.command == "test":
        from azureslop.commands.test import cmd_test
        cmd_test(
            local=args.local is not None,
            place_override=args.local or None,
            port_override=args.port,
        )

    elif args.command == "resolve":
        from azureslop.commands.resolve import cmd_resolve
        cmd_resolve(port_override=args.port)

    elif args.command == "status":
        from azureslop.commands.status import cmd_status
        cmd_status()

    elif args.command == "config":
        from azureslop.commands.config_cmd import cmd_config
        cmd_config(args)


if __name__ == "__main__":
    main()
