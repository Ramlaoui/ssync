#!/usr/bin/env python3
"""Manage SSH ControlMaster connections."""

import subprocess
from pathlib import Path


def list_control_masters():
    """List all active ControlMaster sockets."""
    control_dir = Path("/run/user/1000/ssync_ssh")
    if not control_dir.exists():
        print("No control directory found")
        return

    sockets = list(control_dir.glob("control_*.sock"))
    if not sockets:
        print("No ControlMaster sockets found")
        return

    print(f"Found {len(sockets)} ControlMaster socket(s):")
    for sock in sockets:
        # Try to check if it's active
        check_result = subprocess.run(
            ["ssh", "-S", str(sock), "-O", "check", "dummy"],
            capture_output=True,
            text=True,
        )

        if "Master running" in check_result.stderr:
            pid = check_result.stderr.strip().split("pid=")[1].rstrip(")")
            print(f"  ✓ {sock.name} - Active (PID: {pid})")
        else:
            print(f"  ✗ {sock.name} - Stale (can be removed)")


def stop_control_master(socket_path):
    """Stop a specific ControlMaster."""
    sock = Path(socket_path)
    if not sock.exists():
        print(f"Socket not found: {socket_path}")
        return

    result = subprocess.run(
        ["ssh", "-S", str(sock), "-O", "exit", "dummy"], capture_output=True, text=True
    )

    if result.returncode == 0:
        print(f"Stopped ControlMaster: {sock.name}")
    else:
        print(f"Failed to stop: {result.stderr}")


def stop_all_control_masters():
    """Stop all ControlMaster connections."""
    control_dir = Path("/run/user/1000/ssync_ssh")
    if not control_dir.exists():
        print("No control directory found")
        return

    sockets = list(control_dir.glob("control_*.sock"))
    if not sockets:
        print("No ControlMaster sockets found")
        return

    for sock in sockets:
        stop_control_master(str(sock))


def adjust_persist_time(socket_path, seconds):
    """Adjust ControlPersist time for a running ControlMaster."""
    # Note: This doesn't work with OpenSSH - ControlPersist is set at creation
    print("Note: ControlPersist is set when creating the ControlMaster")
    print("Current connections will timeout after their original persist time")
    print(f"New connections will use: ControlPersist={seconds}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage SSH ControlMaster connections")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    subparsers.add_parser("list", help="List all ControlMaster sockets")

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop ControlMaster(s)")
    stop_parser.add_argument("socket", nargs="?", help="Socket path (or 'all' for all)")

    # Parse args
    args = parser.parse_args()

    if args.command == "list":
        list_control_masters()
    elif args.command == "stop":
        if args.socket == "all":
            stop_all_control_masters()
        elif args.socket:
            stop_control_master(args.socket)
        else:
            print("Specify a socket path or 'all'")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
