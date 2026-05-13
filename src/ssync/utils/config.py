import os
from pathlib import Path
from typing import Any, Dict

import yaml

from ..models.cluster import (
    APISettings,
    CacheSettings,
    Host,
    NotificationSettings,
    PathRestrictions,
    SlurmDefaults,
    SlurmHost,
)

XDG_CACHE = os.environ.get("XDG_CACHE_HOME", os.environ.get("SSYNC_CACHE", ""))
REPO_CONFIG_NAMES = ("config.yaml", "config.yml", "ssync.yaml", "ssync.yml")
LOCAL_OVERLAY_NAMES = (
    ".ssync.local.yaml",
    ".ssync.local.yml",
    ".ssync/local.yaml",
    ".ssync/local.yml",
)


def get_user_config_dir() -> Path:
    """Return the user-level ssync config directory."""
    explicit_path = os.environ.get("SSYNC_CONFIG_PATH")
    if explicit_path:
        return Path(explicit_path).expanduser().parent

    legacy_config = os.environ.get("SSYNC_CONFIG")
    if legacy_config:
        legacy_path = Path(legacy_config).expanduser()
        if legacy_path.suffix in {".yaml", ".yml"} or legacy_path.is_file():
            return legacy_path.parent
        if not os.environ.get("XDG_CONFIG_HOME"):
            return legacy_path / "ssync"

    xdg_config_env = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_env:
        return Path(xdg_config_env).expanduser() / "ssync"

    return Path.home() / ".config" / "ssync"


def get_user_config_path() -> Path:
    """Return the canonical user-level ssync config file path."""
    explicit_path = os.environ.get("SSYNC_CONFIG_PATH")
    if explicit_path:
        return Path(explicit_path).expanduser()

    legacy_config = os.environ.get("SSYNC_CONFIG")
    if legacy_config:
        legacy_path = Path(legacy_config).expanduser()
        if legacy_path.suffix in {".yaml", ".yml"} or legacy_path.is_file():
            return legacy_path

    return get_user_config_dir() / "config.yaml"


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("true", "1", "yes")


def _resolve_env_reference(value: Any) -> Any:
    """Resolve a whole-string ${VAR} reference without touching shell fragments.

    Config files may still point secret-like local settings such as passwords at
    environment variables. Partial strings are left untouched so remote shell
    values like ${SCRATCHDIR}/runs survive until the cluster evaluates them.
    """
    if not isinstance(value, str):
        return value

    if not (value.startswith("${") and value.endswith("}")):
        return value

    env_name = value[2:-1]
    if not env_name.isidentifier():
        return value

    return os.getenv(env_name, "")


def _deep_merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge config maps, replacing lists and scalars with overlay values."""
    merged = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = _deep_merge_config(base_value, overlay_value)
        else:
            merged[key] = overlay_value
    return merged


class ConfigError(Exception):
    """Configuration loading error."""

    pass


class Config:
    def __init__(
        self,
        config_path: str | Path | None = None,
        cache_path: str | Path | None = None,
    ):
        self.config_path = (
            Path(config_path) if config_path else self.get_default_config_path()
        )
        self.cache_path = (
            Path(cache_path) if cache_path else self.get_default_cache_path()
        )
        self.raw_config = self.load_raw_config()
        self.overlay_paths = self.get_overlay_paths()
        for overlay_path in self.overlay_paths:
            self.raw_config = _deep_merge_config(
                self.raw_config,
                self.load_raw_config_file(overlay_path),
            )

        self.config = self.load_config()
        self.cache_settings = self.load_cache_settings()
        self.api_key = self.load_api_key()
        self.api_settings = self.load_api_settings()
        self.path_restrictions = self.load_path_restrictions()
        self.connection_settings = self.load_connection_settings()
        self.notification_settings = self.load_notification_settings()

    def get_default_config_path(self) -> Path:
        """Get the default configuration file path."""
        explicit_path = os.environ.get("SSYNC_CONFIG_PATH")
        if explicit_path:
            return Path(explicit_path).expanduser()

        repo_config = self.find_repo_config_path()
        if repo_config:
            return repo_config

        xdg_config = get_user_config_path()

        if xdg_config.exists():
            return xdg_config

        # Fall back to home directory
        home_config = Path.home() / ".ssync.yaml"
        if home_config.exists():
            return home_config

        # Return XDG path as default (for creation)
        return xdg_config

    def find_repo_config_path(self, start: str | Path | None = None) -> Path | None:
        """Find a repo-local ssync config by walking upward from start."""
        current = Path(start or os.getcwd()).resolve()
        if current.is_file():
            current = current.parent

        for directory in (current, *current.parents):
            ssync_dir = directory / ".ssync"
            for name in REPO_CONFIG_NAMES:
                candidate = ssync_dir / name
                if candidate.exists():
                    return candidate

        return None

    def get_overlay_paths(self) -> list[Path]:
        """Return user-local overlay files adjacent to the selected repo config."""
        config_path = Path(self.config_path).expanduser().resolve()
        config_parent = config_path.parent
        repo_root = config_parent.parent if config_parent.name == ".ssync" else None
        if repo_root is None:
            return []

        overlays = []
        for name in LOCAL_OVERLAY_NAMES:
            candidate = repo_root / name
            if candidate.exists() and candidate.resolve() != config_path:
                overlays.append(candidate)
        return overlays

    def get_default_cache_path(self) -> Path:
        """Get the default cache directory path."""
        xdg_cache = XDG_CACHE
        if not XDG_CACHE:
            home = Path.home()
            xdg_cache = Path(home / ".cache" / "ssync")

        os.makedirs(xdg_cache, exist_ok=True)

        return xdg_cache

    def load_raw_config_file(self, config_path: str | Path) -> dict[str, Any]:
        """Load the YAML config exactly as written.

        Do not perform broad ${VAR} substitution here. Repo-local recipes and
        cluster-side shell fragments often contain variables that must remain
        available to the remote shell at runtime.
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")

        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError("Config must be a YAML mapping")

        return data

    def load_raw_config(self) -> dict[str, Any]:
        return self.load_raw_config_file(self.config_path)

    def load_config(self) -> list[SlurmHost]:
        """Load Slurm hosts configuration from YAML file.

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
        data = self.raw_config

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
                    password=_resolve_env_reference(host_config.get("password")),
                    key_file=_resolve_env_reference(host_config.get("key_file")),
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
        cache_config = self.raw_config.get("cache")
        if isinstance(cache_config, dict):
            settings = CacheSettings(
                enabled=cache_config.get("enabled", settings.enabled),
                cache_dir=cache_config.get("cache_dir", settings.cache_dir),
                max_age_days=cache_config.get("max_age_days", settings.max_age_days),
                script_max_age_days=cache_config.get(
                    "script_max_age_days", settings.script_max_age_days
                ),
                recycled_id_max_age_days=cache_config.get(
                    "recycled_id_max_age_days",
                    settings.recycled_id_max_age_days,
                ),
                cleanup_interval_hours=cache_config.get(
                    "cleanup_interval_hours", settings.cleanup_interval_hours
                ),
                max_size_mb=cache_config.get("max_size_mb", settings.max_size_mb),
                auto_cleanup=cache_config.get("auto_cleanup", settings.auto_cleanup),
            )

        # Environment variable overrides (for backward compatibility)
        if os.getenv("SSYNC_CACHE_ENABLED"):
            settings.enabled = _env_flag("SSYNC_CACHE_ENABLED", "true")
        if os.getenv("SSYNC_CACHE_DIR"):
            settings.cache_dir = os.getenv("SSYNC_CACHE_DIR")
        if os.getenv("SSYNC_CACHE_MAX_AGE_DAYS"):
            settings.max_age_days = int(os.getenv("SSYNC_CACHE_MAX_AGE_DAYS"))
        if os.getenv("SSYNC_CACHE_SCRIPT_MAX_AGE_DAYS"):
            settings.script_max_age_days = int(
                os.getenv("SSYNC_CACHE_SCRIPT_MAX_AGE_DAYS")
            )
        if os.getenv("SSYNC_CACHE_RECYCLED_ID_MAX_AGE_DAYS"):
            settings.recycled_id_max_age_days = int(
                os.getenv("SSYNC_CACHE_RECYCLED_ID_MAX_AGE_DAYS")
            )
        if os.getenv("SSYNC_CACHE_CLEANUP_INTERVAL_HOURS"):
            settings.cleanup_interval_hours = int(
                os.getenv("SSYNC_CACHE_CLEANUP_INTERVAL_HOURS")
            )
        if os.getenv("SSYNC_CACHE_MAX_SIZE_MB"):
            settings.max_size_mb = int(os.getenv("SSYNC_CACHE_MAX_SIZE_MB"))
        if os.getenv("SSYNC_CACHE_AUTO_CLEANUP"):
            settings.auto_cleanup = _env_flag("SSYNC_CACHE_AUTO_CLEANUP")

        return settings

    def load_api_key(self) -> str:
        """Load API key from config file or environment variable."""
        api_key = ""

        # Try to load from config file
        if "api_key" in self.raw_config:
            api_key = _resolve_env_reference(self.raw_config["api_key"])

        # Environment variable override
        if os.getenv("SSYNC_API_KEY"):
            api_key = os.getenv("SSYNC_API_KEY")

        return api_key

    def load_api_settings(self) -> APISettings:
        """Load API server settings from config file with environment variable overrides."""
        # Default settings
        settings = APISettings()

        # Try to load from config file
        api_config = self.raw_config.get("api")
        if isinstance(api_config, dict):
            settings = APISettings(
                host=api_config.get("host", settings.host),
                port=api_config.get("port", settings.port),
                https=api_config.get("https", settings.https),
            )

        # Environment variable overrides
        if os.getenv("SSYNC_API_HOST"):
            settings.host = os.getenv("SSYNC_API_HOST")
        if os.getenv("SSYNC_API_PORT"):
            settings.port = int(os.getenv("SSYNC_API_PORT"))
        if os.getenv("SSYNC_API_HTTPS"):
            settings.https = _env_flag("SSYNC_API_HTTPS", "true")

        return settings

    def load_connection_settings(self) -> Dict[str, int]:
        """Load connection settings from config file or environment variables."""
        settings = {"connect_timeout": 5}

        conn_config = self.raw_config.get("connections")
        if isinstance(conn_config, dict):
            settings["connect_timeout"] = int(
                conn_config.get("connect_timeout", settings["connect_timeout"])
            )

        if os.getenv("SSYNC_CONNECT_TIMEOUT"):
            settings["connect_timeout"] = int(os.getenv("SSYNC_CONNECT_TIMEOUT"))

        return settings

    def load_path_restrictions(self) -> PathRestrictions:
        """Load path restrictions from config file with environment variable overrides."""
        # Default settings
        settings = PathRestrictions()

        # Try to load from config file
        restrictions_config = self.raw_config.get("path_restrictions")
        if isinstance(restrictions_config, dict):
            settings = PathRestrictions(
                enabled=restrictions_config.get("enabled", settings.enabled),
                allowed_paths=restrictions_config.get(
                    "allowed_paths", settings.allowed_paths
                ),
                forbidden_paths=restrictions_config.get(
                    "forbidden_paths", settings.forbidden_paths
                ),
                max_size_gb=restrictions_config.get(
                    "max_size_gb", settings.max_size_gb
                ),
                allow_home=restrictions_config.get("allow_home", settings.allow_home),
                allow_tmp=restrictions_config.get("allow_tmp", settings.allow_tmp),
                allow_absolute=restrictions_config.get(
                    "allow_absolute", settings.allow_absolute
                ),
            )

        # Environment variable overrides
        if os.getenv("SSYNC_PATH_RESTRICTIONS_ENABLED"):
            settings.enabled = _env_flag("SSYNC_PATH_RESTRICTIONS_ENABLED")
        if os.getenv("SSYNC_MAX_SYNC_SIZE_GB"):
            settings.max_size_gb = float(os.getenv("SSYNC_MAX_SYNC_SIZE_GB"))
        if os.getenv("SSYNC_ALLOW_ABSOLUTE_PATHS"):
            settings.allow_absolute = _env_flag("SSYNC_ALLOW_ABSOLUTE_PATHS")

        return settings

    def load_notification_settings(self) -> NotificationSettings:
        """Load notification settings from config file or environment variables."""
        settings = NotificationSettings()

        notifications = self.raw_config.get("notifications")
        if isinstance(notifications, dict):
            settings = NotificationSettings(
                enabled=notifications.get("enabled", settings.enabled),
                apns_key_id=_resolve_env_reference(
                    notifications.get("apns_key_id", settings.apns_key_id)
                ),
                apns_team_id=_resolve_env_reference(
                    notifications.get("apns_team_id", settings.apns_team_id)
                ),
                apns_bundle_id=notifications.get(
                    "apns_bundle_id", settings.apns_bundle_id
                ),
                apns_private_key=_resolve_env_reference(
                    notifications.get("apns_private_key", settings.apns_private_key)
                ),
                apns_use_sandbox=notifications.get(
                    "apns_use_sandbox", settings.apns_use_sandbox
                ),
                apns_timeout_seconds=notifications.get(
                    "apns_timeout_seconds", settings.apns_timeout_seconds
                ),
                webpush_enabled=notifications.get(
                    "webpush_enabled", settings.webpush_enabled
                ),
                webpush_vapid_public_key=_resolve_env_reference(
                    notifications.get(
                        "webpush_vapid_public_key",
                        settings.webpush_vapid_public_key,
                    )
                ),
                webpush_vapid_private_key=_resolve_env_reference(
                    notifications.get(
                        "webpush_vapid_private_key",
                        settings.webpush_vapid_private_key,
                    )
                ),
                webpush_vapid_subject=notifications.get(
                    "webpush_vapid_subject", settings.webpush_vapid_subject
                ),
            )

        if os.getenv("SSYNC_NOTIFICATIONS_ENABLED"):
            settings.enabled = _env_flag("SSYNC_NOTIFICATIONS_ENABLED")
        if os.getenv("SSYNC_APNS_KEY_ID"):
            settings.apns_key_id = os.getenv("SSYNC_APNS_KEY_ID")
        if os.getenv("SSYNC_APNS_TEAM_ID"):
            settings.apns_team_id = os.getenv("SSYNC_APNS_TEAM_ID")
        if os.getenv("SSYNC_APNS_BUNDLE_ID"):
            settings.apns_bundle_id = os.getenv("SSYNC_APNS_BUNDLE_ID")
        if os.getenv("SSYNC_APNS_PRIVATE_KEY"):
            settings.apns_private_key = os.getenv("SSYNC_APNS_PRIVATE_KEY")
        if os.getenv("SSYNC_APNS_USE_SANDBOX"):
            settings.apns_use_sandbox = _env_flag("SSYNC_APNS_USE_SANDBOX", "true")
        if os.getenv("SSYNC_APNS_TIMEOUT_SECONDS"):
            settings.apns_timeout_seconds = float(
                os.getenv("SSYNC_APNS_TIMEOUT_SECONDS")
            )
        if os.getenv("SSYNC_WEBPUSH_ENABLED"):
            settings.webpush_enabled = _env_flag("SSYNC_WEBPUSH_ENABLED")
        if os.getenv("SSYNC_WEBPUSH_VAPID_PUBLIC_KEY"):
            settings.webpush_vapid_public_key = os.getenv(
                "SSYNC_WEBPUSH_VAPID_PUBLIC_KEY"
            )
        if os.getenv("SSYNC_WEBPUSH_VAPID_PRIVATE_KEY"):
            settings.webpush_vapid_private_key = os.getenv(
                "SSYNC_WEBPUSH_VAPID_PRIVATE_KEY"
            )
        if os.getenv("SSYNC_WEBPUSH_VAPID_SUBJECT"):
            settings.webpush_vapid_subject = os.getenv("SSYNC_WEBPUSH_VAPID_SUBJECT")

        return settings


config = Config()
