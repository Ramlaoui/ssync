"""SSH connection management using native SSH with ControlMaster."""

from typing import Dict

from .models.cluster import Host
from .ssh.connection import SSHConnection
from .utils.logging import setup_logger

logger = setup_logger(__name__, "INFO")


class ConnectionManager:
    """Manages SSH connections using native SSH with ControlMaster for key-based auth."""

    def __init__(self, use_ssh_config: bool = True, connection_timeout: int = 30):
        """Initialize connection manager.

        Args:
            use_ssh_config: Whether to use SSH config (always True now)
            connection_timeout: Connection timeout in seconds
        """
        self.connection_timeout = connection_timeout
        self._connections: Dict[str, SSHConnection] = {}
        logger.info("ConnectionManager initialized with native SSH")

    def get_connection(self, host: Host, force_refresh: bool = False):
        """Get SSH connection for a host.

        Args:
            host: Host configuration
            force_refresh: Force a new connection if True

        Returns:
            SSH connection object
        """
        host_string = self._get_host_string(host)

        # Force refresh: close existing connection and create new one
        if force_refresh and host_string in self._connections:
            try:
                # Try to close the existing connection gracefully
                logger.info(f"Force refreshing connection to {host_string}")
                del self._connections[host_string]
            except Exception as e:
                logger.warning(f"Error closing connection to {host_string}: {e}")

        # One connection per host (shared for all purposes)
        if host_string not in self._connections:
            host_config = self._host_to_config(host)
            self._connections[host_string] = SSHConnection(host_config, host_string)
            logger.debug(f"Created SSH connection for {host_string}")
        else:
            # Test existing connection health
            try:
                self._connections[host_string].run("echo 'test'", hide=True, timeout=5)
            except Exception as e:
                logger.warning(
                    f"Existing connection to {host_string} is unhealthy: {e}"
                )
                # Remove bad connection and create new one
                del self._connections[host_string]
                host_config = self._host_to_config(host)
                self._connections[host_string] = SSHConnection(host_config, host_string)
                logger.info(f"Recreated SSH connection for {host_string}")

        return self._connections[host_string]

    def _get_host_string(self, host: Host) -> str:
        """Build host string for identification."""
        host_string = host.hostname
        if host.username:
            host_string = f"{host.username}@{host_string}"
        if host.port and host.port != 22:
            host_string = f"{host_string}:{host.port}"
        return host_string

    def _host_to_config(self, host: Host):
        """Convert Host model to SSH configuration.

        Returns:
            String (SSH alias) or dict with connection details
        """
        # Check if this is an SSH config alias
        # (no username, standard port, no dots in hostname)
        is_ssh_alias = (
            not host.username
            and (not host.port or host.port == 22)
            and "." not in host.hostname
        )

        if is_ssh_alias and host.use_ssh_config:
            # If there's a password, return dict with password
            if host.password:
                return {
                    "hostname": host.hostname,
                    "connect_kwargs": {"password": host.password},
                }
            # Otherwise just return the alias
            return host.hostname

        # Build explicit configuration
        config = {"hostname": host.hostname}

        if host.username:
            config["user"] = host.username

        if host.port and host.port != 22:
            config["port"] = host.port

        if host.key_file:
            config["key_filename"] = host.key_file

        if host.password:
            config["connect_kwargs"] = {"password": host.password}

        return config

    def run_command(self, host: Host, command: str, **kwargs):
        """Run a command on a host.

        Args:
            host: Host to run command on
            command: Command to execute
            **kwargs: Additional arguments for run()

        Returns:
            Command result
        """
        connection = self.get_connection(host)

        # Set defaults for background processes
        if "pty" not in kwargs:
            kwargs["pty"] = False
        if "in_stream" not in kwargs:
            kwargs["in_stream"] = False

        return connection.run(command, **kwargs)

    def refresh_all_connections(self) -> int:
        """Note: ControlMasters persist, this just returns count."""
        count = len(self._connections)
        logger.info(
            f"Have {count} connections (ControlMasters persist between sessions)"
        )
        return count

    def close_all(self):
        """Clean up all connections and ControlMasters."""
        from .ssh.native import NativeSSH

        NativeSSH.cleanup_all()
        self._connections.clear()
        logger.info("All connections closed")

    def get_stats(self) -> Dict:
        """Get connection statistics."""
        from .ssh.native import NativeSSH

        return {
            "connections": len(self._connections),
            "control_masters": len(NativeSSH._control_masters),
        }

    def check_connection_health(self) -> int:
        """Check health of SSH connections and clean up stale ones.

        Returns:
            Number of unhealthy connections removed
        """
        unhealthy_count = 0
        to_remove = []

        for host_string, connection in self._connections.items():
            try:
                # Try a simple command to test connection with shorter timeout
                connection.run("echo 'health check'", hide=True, timeout=5)
            except Exception as e:
                logger.debug(f"Connection to {host_string} appears unhealthy: {e}")
                to_remove.append(host_string)
                unhealthy_count += 1

        # Remove unhealthy connections (they'll be recreated on next use)
        for host_string in to_remove:
            try:
                del self._connections[host_string]
                logger.info(f"Removed unhealthy connection to {host_string}")
            except Exception as e:
                logger.warning(f"Error removing connection {host_string}: {e}")

        return unhealthy_count

    def get_connection_stats(self) -> Dict:
        """Get connection statistics (alias for get_stats)."""
        return self.get_stats()

    def close_connections(self):
        """Close all connections (alias for close_all)."""
        self.close_all()
