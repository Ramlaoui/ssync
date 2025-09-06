import os
import re
from pathlib import Path

import yaml

from ..models.cluster import CacheSettings, Host, SlurmDefaults, SlurmHost

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
        self.cache_settings = self.load_cache_settings()
        self.api_key = self.load_api_key()

    def get_default_config_path(self) -> Path:
        """Get the default configuration file path."""
        home = Path.home()

        if not XDG_CONFIG:
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

                slurm_defaults_config = host_config.get("slurm_defaults")
                slurm_defaults = (
                    SlurmDefaults(**slurm_defaults_config)
                    if slurm_defaults_config
                    else None
                )

                slurm_host = SlurmHost(
                    host=host,
                    work_dir=Path(host_config["work_dir"]),
                    scratch_dir=Path(host_config["scratch_dir"]),
                    slurm_defaults=slurm_defaults,
                )
                hosts.append(slurm_host)

            except KeyError as e:
                raise ConfigError(f"Missing required field in host config: {e}")
            except Exception as e:
                raise ConfigError(f"Error creating host config: {e}")

        return hosts

    def get_remote_cache_path(self, host: SlurmHost) -> Path:
        """Get the remote cache directory path for a given host."""
        remote_cache = host.scratch_dir / ".cache" / "ssync"
        return remote_cache

    def load_cache_settings(self) -> CacheSettings:
        """Load cache settings from config file with environment variable overrides."""
        # Default settings
        settings = CacheSettings()

        # Try to load from config file
        config_path = Path(self.config_path)
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    content = f.read()
                    # Environment variable substitution
                    content = re.sub(
                        r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), content
                    )
                    data = yaml.safe_load(content)

                if data and "cache" in data:
                    cache_config = data["cache"]
                    settings = CacheSettings(
                        enabled=cache_config.get("enabled", settings.enabled),
                        cache_dir=cache_config.get("cache_dir", settings.cache_dir),
                        max_age_days=cache_config.get(
                            "max_age_days", settings.max_age_days
                        ),
                        script_max_age_days=cache_config.get(
                            "script_max_age_days", settings.script_max_age_days
                        ),
                        cleanup_interval_hours=cache_config.get(
                            "cleanup_interval_hours", settings.cleanup_interval_hours
                        ),
                        max_size_mb=cache_config.get(
                            "max_size_mb", settings.max_size_mb
                        ),
                        auto_cleanup=cache_config.get(
                            "auto_cleanup", settings.auto_cleanup
                        ),
                    )
            except Exception:
                # If there's any error loading cache settings, use defaults
                pass

        # Environment variable overrides (for backward compatibility)
        if os.getenv("SSYNC_CACHE_ENABLED"):
            settings.enabled = os.getenv("SSYNC_CACHE_ENABLED", "true").lower() in (
                "true",
                "1",
                "yes",
            )
        if os.getenv("SSYNC_CACHE_DIR"):
            settings.cache_dir = os.getenv("SSYNC_CACHE_DIR")
        if os.getenv("SSYNC_CACHE_MAX_AGE_DAYS"):
            settings.max_age_days = int(os.getenv("SSYNC_CACHE_MAX_AGE_DAYS"))
        if os.getenv("SSYNC_CACHE_SCRIPT_MAX_AGE_DAYS"):
            settings.script_max_age_days = int(
                os.getenv("SSYNC_CACHE_SCRIPT_MAX_AGE_DAYS")
            )
        if os.getenv("SSYNC_CACHE_CLEANUP_INTERVAL_HOURS"):
            settings.cleanup_interval_hours = int(
                os.getenv("SSYNC_CACHE_CLEANUP_INTERVAL_HOURS")
            )
        if os.getenv("SSYNC_CACHE_MAX_SIZE_MB"):
            settings.max_size_mb = int(os.getenv("SSYNC_CACHE_MAX_SIZE_MB"))
        if os.getenv("SSYNC_CACHE_AUTO_CLEANUP"):
            settings.auto_cleanup = os.getenv(
                "SSYNC_CACHE_AUTO_CLEANUP", "false"
            ).lower() in ("true", "1", "yes")

        return settings

    def load_api_key(self) -> str:
        """Load API key from config file or environment variable."""
        api_key = ""

        # Try to load from config file
        config_path = Path(self.config_path)
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    content = f.read()
                    # Environment variable substitution
                    content = re.sub(
                        r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), content
                    )
                    data = yaml.safe_load(content)

                if data and "api_key" in data:
                    api_key = data["api_key"]
            except Exception:
                pass

        # Environment variable override
        if os.getenv("SSYNC_API_KEY"):
            api_key = os.getenv("SSYNC_API_KEY")

        return api_key


config = Config()
