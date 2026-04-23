"""
AzureSlop CLI
Usage:
  azureslop init   - initialize a project in the current directory
  azureslop sync   - start the sync server
"""

import sys
from azureslop.commands.init import cmd_init
from azureslop.commands.sync import cmd_sync


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: azureslop <command>")
        print("Commands:")
        print("  init   Initialize a new AzureSlop project in the current directory")
        print("  sync   Start the sync server")
        sys.exit(0)

    command = args[0]

    if command == "init":
        cmd_init()
    elif command == "sync":
        cmd_sync()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
