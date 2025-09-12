"""Native SSH implementation for ssync.

This module provides SSH connections using native SSH with ControlMaster
for improved performance with key-based authentication, and direct
connections with sshpass for password authentication.
"""

from .connection import SSHCommandResult, SSHConnection
from .native import NativeSSH, SSHResult

__all__ = [
    "NativeSSH",
    "SSHResult",
    "SSHConnection",
    "SSHCommandResult",
]
