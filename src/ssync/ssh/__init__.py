"""Native SSH implementation for ssync.

This module provides SSH connections using native SSH with ControlMaster
for improved performance with key-based authentication, and direct
connections with sshpass for password authentication.
"""

from .connection import SSHCommandResult, SSHConnection
from .helpers import get_file, send_file
from .manager import ConnectionManager
from .native import NativeSSH, SSHResult

__all__ = [
    "NativeSSH",
    "SSHResult",
    "SSHConnection",
    "SSHCommandResult",
    "ConnectionManager",
    "get_file",
    "send_file",
]
