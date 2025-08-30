"""SSH connection management utilities."""

from typing import Dict

from fabric import Config, Connection

from .models.cluster import Host
from .utils.logging import setup_logger

logger = setup_logger(__name__, "DEBUG")


class ConnectionManager:
    """Manages SSH connections with caching and health checks."""

    def __init__(self, use_ssh_config: bool = True, connection_timeout: int = 30):
        self.use_ssh_config = use_ssh_config
        self.connection_timeout = connection_timeout
        self._connections: Dict[str, Connection] = {}

        self.default_timeouts = {
            "timeout": connection_timeout,
            "banner_timeout": connection_timeout,
            "auth_timeout": connection_timeout,
        }

        if use_ssh_config:
            self._fabric_config = Config()
            self._fabric_config.connect_kwargs.update(self.default_timeouts)
        else:
            self._fabric_config = None

    def get_connection(self, host: Host, force_refresh: bool = False) -> Connection:
        """Get or create a fabric connection with caching.

        Args:
            host: Host configuration
            force_refresh: If True, close existing connection and create new one

        Returns:
            Connection object
        """
        host_string = host.hostname
        if host.username:
            host_string = f"{host.username}@{host_string}"
        if host.port and host.port != 22:
            host_string = f"{host_string}:{host.port}"

        logger.debug(f"Requesting connection to: {host_string}")

        # Force refresh if requested
        if force_refresh and host_string in self._connections:
            logger.debug(f"Force refreshing connection to {host_string}")
            try:
                self._connections[host_string].close()
            except Exception:
                pass
            del self._connections[host_string]

        if host_string in self._connections:
            try:
                result = self._connections[host_string].run(
                    "echo 1", hide=True, timeout=3
                )
                if result.ok:
                    logger.debug(f"✓ Reused EXISTING connection to {host_string}")
                    return self._connections[host_string]
            except Exception as e:
                logger.debug(f"✗ Connection health check failed for {host_string}: {e}")
                try:
                    self._connections[host_string].close()
                except Exception:
                    pass
                del self._connections[host_string]

        connect_kwargs = self.default_timeouts.copy()

        if host.username:
            if host.key_file:
                connect_kwargs["key_filename"] = host.key_file
            if host.password:
                connect_kwargs["password"] = host.password

            logger.debug(
                f"Attempting connection to {host_string} (timeout: {self.connection_timeout}s)"
            )
            connection = Connection(
                host=host.hostname,
                user=host.username,
                port=host.port,
                connect_kwargs=connect_kwargs,
            )
        else:
            if host.key_file:
                connect_kwargs["key_filename"] = host.key_file
            if host.password:
                connect_kwargs["password"] = host.password

            logger.debug(
                f"Attempting connection to {host_string} (timeout: {self.connection_timeout}s)"
            )
            connection = Connection(
                host=host.hostname,
                connect_kwargs=connect_kwargs,
                config=self._fabric_config,
            )

        self._connections[host_string] = connection
        logger.debug(f"✓ Created NEW connection to {host_string}")

        return connection

    def _get_host_string(self, host: Host) -> str:
        """Build host string in format: [user@]hostname[:port]."""
        host_string = host.hostname
        if host.username:
            host_string = f"{host.username}@{host_string}"
        if host.port and host.port != 22:
            host_string = f"{host_string}:{host.port}"
        return host_string

    def run_command(self, host: Host, command: str, **kwargs):
        """Run a command on a host with automatic retry on connection failure."""
        connection = self.get_connection(host)

        try:
            result = connection.run(command, **kwargs)
            if hasattr(result, "ok") and not result.ok:
                return result
            return result
        except Exception as e:
            logger.debug(
                f"Command failed on {host.hostname}, retrying with new connection: {e}"
            )

            host_string = self._get_host_string(host)
            if host_string in self._connections:
                try:
                    self._connections[host_string].close()
                except Exception:
                    pass
                del self._connections[host_string]
                logger.debug(f"Removed stale connection to {host_string}")

            fresh_connection = self.get_connection(host)
            return fresh_connection.run(command, **kwargs)

    def check_connection_health(self) -> int:
        """Check health of all connections and remove unhealthy ones.

        Returns:
            Number of unhealthy connections removed
        """
        unhealthy_connections = []

        for host_string, conn in self._connections.items():
            try:
                result = conn.run("echo 'test' && pwd", hide=True, timeout=5)
                if not result.ok or not result.stdout.strip():
                    logger.debug(
                        f"✗ Connection health check failed for {host_string}: exit code {result.exited}"
                    )
                    unhealthy_connections.append(host_string)
            except Exception as e:
                logger.debug(f"✗ Connection health check failed for {host_string}: {e}")
                unhealthy_connections.append(host_string)

        for host_string in unhealthy_connections:
            try:
                self._connections[host_string].close()
            except Exception:
                pass
            del self._connections[host_string]
            logger.debug(f"Removed unhealthy connection to {host_string}")

        return len(unhealthy_connections)

    def get_connection_stats(self) -> dict:
        """Get statistics about current connections."""
        return {
            "total_connections": len(self._connections),
            "active_hosts": list(self._connections.keys()),
        }

    def refresh_all_connections(self):
        """Close and refresh all SSH connections.

        Returns:
            Number of connections refreshed
        """
        logger.info(f"Refreshing all {len(self._connections)} cached connections...")
        count = len(self._connections)
        for host_string, conn in list(self._connections.items()):
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"Error closing connection to {host_string}: {e}")
        self._connections.clear()
        logger.info(f"Refreshed {count} connections")
        return count

    def close_connections(self):
        """Close all SSH connections and cache."""
        logger.debug(f"Closing {len(self._connections)} cached connections...")
        for host_string, conn in self._connections.items():
            try:
                logger.debug(f"Closing connection to {host_string}")
                conn.close()
            except Exception as e:
                logger.debug(f"Error closing connection to {host_string}: {e}")
        self._connections.clear()
