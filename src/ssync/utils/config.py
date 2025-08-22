import os
import re
from pathlib import Path

import yaml

from ..models.cluster import Host, SlurmHost

XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.environ.get("SSYNC_CONFIG", ""))
XDG_CACHE = os.environ.get("XDG_CACHE_HOME", os.environ.get("SSYNC_CACHE", ""))


class ConfigError(Exception):
    """Configuration loading error."""

    pass


class Config:
    def __init__(self):
        self.config_path = self.get_default_config_path()
        self.cache_path = self.get_default_cache_path()

        self.config = self.load_config()

    def get_default_config_path(self) -> Path:
        """Get the default configuration file path."""
        if not XDG_CONFIG:
            home = Path.home()

            # Check XDG config directory first
            xdg_config = Path(home / ".config")
        else:
            xdg_config = Path(XDG_CONFIG)

        xdg_config = Path(xdg_config / "ssync" / "config.yaml")

        if xdg_config.exists():
            return xdg_config

        # Fall back to home directory
        home_config = Path(home / ".ssync.yaml")
        if home_config.exists():
            return home_config

        # Return XDG path as default (for creation)
        return xdg_config

    def get_default_cache_path(self) -> Path:
        """Get the default cache directory path."""
        xdg_cache = XDG_CACHE
        if not XDG_CACHE:
            home = Path.home()
            xdg_cache = Path(home / ".cache" / "ssync")

        os.makedirs(xdg_cache, exist_ok=True)

        return xdg_cache

    def load_config(self) -> list[SlurmHost]:
        """Load SLURM hosts configuration from YAML file.

        Expected format (with SSH config support):
        hosts:
        - hostname: cluster1  # Can be SSH config alias
            work_dir: /home/myuser/work
            scratch_dir: /scratch/myuser
        - hostname: cluster2
            username: myuser  # Optional if in SSH config
            work_dir: /home/myuser/work
            scratch_dir: /tmp/myuser

        Or full manual config:
        hosts:
        - hostname: cluster1.university.edu
            username: myuser
            port: 22
            key_file: ~/.ssh/id_rsa
            work_dir: /home/myuser/work
            scratch_dir: /scratch/myuser
        """
        config_path = Path(self.config_path)
        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "r") as f:
                content = f.read()
                # Simple environment variable substitution: ${VAR_NAME}
                content = re.sub(
                    r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), content
                )
                data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")

        if not isinstance(data, dict) or "hosts" not in data:
            raise ConfigError("Config must contain 'hosts' key")

        hosts = []
        for host_config in data["hosts"]:
            try:
                # hostname is always required
                hostname = host_config["hostname"]

                # username is optional if using SSH config
                username = host_config.get("username", "")

                host = Host(
                    hostname=hostname,
                    username=username,
                    port=host_config.get("port", 22),
                    password=host_config.get("password"),
                    key_file=host_config.get("key_file"),
                    use_ssh_config=host_config.get("use_ssh_config", True),
                )

                slurm_host = SlurmHost(
                    host=host,
                    work_dir=Path(host_config["work_dir"]),
                    scratch_dir=Path(host_config["scratch_dir"]),
                )
                hosts.append(slurm_host)

            except KeyError as e:
                raise ConfigError(f"Missing required field in host config: {e}")
            except Exception as e:
                raise ConfigError(f"Error creating host config: {e}")

        return hosts


config = Config()
