"""Security utilities and middleware for the SLURM Manager API."""

import hashlib
import os
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException, Request

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class RateLimiter:
    """Rate limiting middleware to prevent abuse."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_size = burst_size
        self._request_counts: Dict[str, List[float]] = defaultdict(list)
        self._burst_tokens: Dict[str, int] = defaultdict(lambda: burst_size)
        self._last_refill: Dict[str, float] = defaultdict(time.time)

    def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier from request."""
        # Use API key if present, otherwise use IP
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        # Get real IP considering proxy headers
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _cleanup_old_requests(self, client_id: str, current_time: float):
        """Remove request timestamps older than 1 hour."""
        cutoff = current_time - 3600
        self._request_counts[client_id] = [
            ts for ts in self._request_counts[client_id] if ts > cutoff
        ]

    def _refill_tokens(self, client_id: str, current_time: float):
        """Refill burst tokens over time."""
        time_passed = current_time - self._last_refill[client_id]
        tokens_to_add = int(time_passed * self.burst_size / 60)  # Refill over 1 minute

        if tokens_to_add > 0:
            self._burst_tokens[client_id] = min(
                self.burst_size, self._burst_tokens[client_id] + tokens_to_add
            )
            self._last_refill[client_id] = current_time

    async def check_rate_limit(self, request: Request) -> bool:
        """Check if request should be rate limited."""
        client_id = self._get_client_id(request)
        current_time = time.time()

        # Cleanup old requests
        self._cleanup_old_requests(client_id, current_time)

        # Refill burst tokens
        self._refill_tokens(client_id, current_time)

        # Get request counts
        requests = self._request_counts[client_id]

        # Check hourly limit
        hour_ago = current_time - 3600
        hour_requests = [ts for ts in requests if ts > hour_ago]
        if len(hour_requests) >= self.requests_per_hour:
            return False

        # Check minute limit
        minute_ago = current_time - 60
        minute_requests = [ts for ts in requests if ts > minute_ago]
        if len(minute_requests) >= self.requests_per_minute:
            # Check burst tokens
            if self._burst_tokens[client_id] <= 0:
                return False
            self._burst_tokens[client_id] -= 1

        # Record this request
        self._request_counts[client_id].append(current_time)
        return True


class PathValidator:
    """Validate and sanitize file paths to prevent traversal attacks."""

    # Blacklisted path components
    BLACKLISTED_COMPONENTS = {
        "..",
        "~",
        "${",
        "$(",
        "`",
        "|",
        ";",
        "&",
        ">",
        "<",
        "\n",
        "\r",
        "\0",
        "//",
        "\\",
    }

    # Sensitive file patterns that should never be accessed
    SENSITIVE_FILES = {
        r".*\.ssh/.*",
        r".*\.gnupg/.*",
        r".*\.aws/.*",
        r".*\.kube/.*",
        r".*\.docker/.*",
        r".*\.git/.*",
        r".*/passwd$",
        r".*/shadow$",
        r".*\.key$",
        r".*\.pem$",
        r".*\.crt$",
        r".*\.p12$",
        r".*\.pfx$",
        r".*_rsa$",
        r".*_dsa$",
        r".*_ecdsa$",
        r".*_ed25519$",
    }

    @classmethod
    def validate_path(
        cls, path: str, base_type: str = "local", user_home: Optional[Path] = None
    ) -> Path:
        """
        Validate and sanitize a file path.

        Args:
            path: Path to validate
            base_type: Type of base paths to check against ("local" or "remote")
            user_home: User's home directory for additional validation

        Returns:
            Sanitized Path object

        Raises:
            HTTPException: If path is invalid or potentially malicious
        """
        if not path:
            raise HTTPException(status_code=400, detail="Path cannot be empty")

        # Check for blacklisted components
        for component in cls.BLACKLISTED_COMPONENTS:
            if component in path:
                raise HTTPException(
                    status_code=400, detail="Invalid path component detected"
                )

        # Resolve and normalize path
        try:
            resolved_path = Path(path).expanduser().resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path format")

        path_str = str(resolved_path)

        # Check against sensitive file patterns
        for pattern in cls.SENSITIVE_FILES:
            if re.match(pattern, path_str):
                raise HTTPException(
                    status_code=403, detail="Access to sensitive files is forbidden"
                )

        # Note: Path restrictions are now handled by the backend configuration
        # in src/ssync/sync.py via PathRestrictions from config.
        # The API only does basic security validation (no traversal, no sensitive files)

        return resolved_path


class ScriptValidator:
    """Validate and sanitize SLURM scripts for security."""

    # Dangerous command patterns
    DANGEROUS_PATTERNS = [
        (r"rm\s+-rf\s+/(?:\s|$)", "Dangerous recursive deletion of root"),
        (r"chmod\s+777", "Overly permissive file permissions"),
        (r"sudo\s+", "Sudo commands not allowed"),
        (r">\s*/etc/", "Writing to system directories forbidden"),
        (r"curl\s+.*\|\s*sh", "Remote code execution attempt"),
        (r"wget\s+.*\|\s*sh", "Remote code execution attempt"),
        (r"nc\s+-l", "Network backdoor attempt"),
        (r"mkfifo\s+/tmp/", "Named pipe creation in tmp"),
        (r"/etc/passwd", "Access to system password file"),
        (r"/etc/shadow", "Access to system shadow file"),
        (r"base64\s+-d.*\|\s*sh", "Encoded command execution"),
        (r"eval\s+.*\$", "Dynamic code evaluation"),
        (r"exec\s+.*<", "Input redirection to exec"),
    ]

    # Resource limits
    MAX_SCRIPT_SIZE = 1024 * 1024  # 1MB
    MAX_LINE_LENGTH = 10000

    @classmethod
    def validate_script(cls, script_content: str) -> str:
        """
        Validate and sanitize a SLURM script.

        Args:
            script_content: Script content to validate

        Returns:
            Sanitized script content

        Raises:
            HTTPException: If script contains dangerous patterns
        """
        if not script_content:
            raise HTTPException(status_code=400, detail="Script cannot be empty")

        # Check size limits
        if len(script_content) > cls.MAX_SCRIPT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Script too large (max {cls.MAX_SCRIPT_SIZE} bytes)",
            )

        # Check line length
        lines = script_content.split("\n")
        for i, line in enumerate(lines):
            if len(line) > cls.MAX_LINE_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Line {i + 1} too long (max {cls.MAX_LINE_LENGTH} chars)",
                )

        # Check for dangerous patterns
        for pattern, description in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, script_content, re.IGNORECASE | re.MULTILINE):
                logger.warning(f"Blocked script with pattern: {description}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Script contains forbidden pattern: {description}",
                )

        # Additional validation for environment variables
        env_vars = re.findall(r"\$\{?([A-Z_][A-Z0-9_]*)\}?", script_content)
        sensitive_vars = {
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "GITHUB_TOKEN",
            "GITLAB_TOKEN",
            "SSH_PRIVATE_KEY",
        }

        for var in env_vars:
            if var in sensitive_vars:
                raise HTTPException(
                    status_code=400,
                    detail="Script references sensitive environment variables",
                )

        return script_content


class InputSanitizer:
    """Sanitize user inputs to prevent injection attacks."""

    @staticmethod
    def sanitize_hostname(hostname: str) -> str:
        """Sanitize hostname input."""
        if not hostname:
            raise HTTPException(status_code=400, detail="Hostname cannot be empty")

        # Allow only valid hostname characters
        if not re.match(
            r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$",
            hostname,
        ):
            raise HTTPException(status_code=400, detail="Invalid hostname format")

        return hostname.lower()

    @staticmethod
    def sanitize_job_id(job_id: str) -> str:
        """Sanitize job ID input."""
        if not job_id:
            raise HTTPException(status_code=400, detail="Job ID cannot be empty")

        # SLURM job IDs are typically numeric or numeric with array indices
        if not re.match(r"^[0-9]+(_[0-9]+)?(\[[0-9\-,]+\])?$", job_id):
            raise HTTPException(status_code=400, detail="Invalid job ID format")

        return job_id

    @staticmethod
    def sanitize_username(username: str) -> str:
        """Sanitize username input."""
        if not username:
            return username

        # Unix usernames: lowercase letters, digits, underscore, hyphen
        if not re.match(r"^[a-z_][a-z0-9_\-]{0,31}$", username):
            raise HTTPException(status_code=400, detail="Invalid username format")

        return username

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage."""
        if not filename:
            raise HTTPException(status_code=400, detail="Filename cannot be empty")

        # Remove path components
        filename = os.path.basename(filename)

        # Remove dangerous characters
        filename = re.sub(r"[^\w\s\-\.]", "", filename)

        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:250] + ext

        return filename

    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        """Sanitize general text input."""
        if not text:
            return text

        # Remove control characters except newline and tab
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        # Limit length
        if len(text) > max_length:
            text = text[:max_length]

        # Remove potential SQL/command injection patterns
        dangerous_patterns = [
            r";\s*(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|EXEC)",
            r"--\s*$",
            r"/\*.*?\*/",
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
        ]

        for pattern in dangerous_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip()


class APIKeyManager:
    """Manage API keys with secure storage and rotation."""

    def __init__(self, key_file: Optional[Path] = None):
        # Use the same location as CLI for consistency
        self.key_file = key_file or Path.home() / ".config" / "ssync" / ".api_key"
        self.keys: Dict[str, Dict] = {}
        self.simple_key: Optional[str] = None
        self._load_keys()

    def _load_keys(self):
        """Load API keys from secure storage."""
        if self.key_file.exists():
            # Set restrictive permissions
            try:
                self.key_file.chmod(0o600)
            except Exception:
                pass

            try:
                # First try to read as simple text (single key)
                with open(self.key_file, "r") as f:
                    content = f.read().strip()

                # If it looks like JSON, parse it
                if content.startswith("{"):
                    import json

                    self.keys = json.loads(content)
                else:
                    # Simple key file - just the key itself
                    self.simple_key = content
                    # Also add to keys dict for compatibility
                    self.keys[content] = {
                        "name": "default",
                        "created_at": datetime.now().isoformat(),
                        "expires_at": (
                            datetime.now() + timedelta(days=365)
                        ).isoformat(),
                        "last_used": None,
                        "usage_count": 0,
                    }
            except Exception as e:
                logger.error(f"Failed to load API keys: {e}")
                self.keys = {}

    def generate_key(self, name: str, expires_days: int = 90) -> str:
        """Generate a new API key."""
        key = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(days=expires_days)

        self.keys[key] = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_used": None,
            "usage_count": 0,
        }

        self._save_keys()
        return key

    def validate_key(self, key: str) -> bool:
        """Validate an API key."""
        if key not in self.keys:
            return False

        key_data = self.keys[key]

        # Check expiration
        expires_at = datetime.fromisoformat(key_data["expires_at"])
        if datetime.now() > expires_at:
            return False

        # Update usage stats
        key_data["last_used"] = datetime.now().isoformat()
        key_data["usage_count"] += 1
        self._save_keys()

        return True

    def revoke_key(self, key: str):
        """Revoke an API key."""
        if key in self.keys:
            del self.keys[key]
            self._save_keys()

    def _save_keys(self):
        """Save API keys to secure storage."""
        import json

        self.key_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.key_file, "w") as f:
            json.dump(self.keys, f, indent=2)

        # Set restrictive permissions
        self.key_file.chmod(0o600)


def sanitize_error_message(error: Exception) -> str:
    """Sanitize error messages to prevent information disclosure."""
    error_str = str(error)

    # Remove file paths
    error_str = re.sub(r"/[/\w\-\.]+", "[PATH]", error_str)

    # Remove IP addresses
    error_str = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[IP]", error_str)

    # Remove port numbers
    error_str = re.sub(r":\d{2,5}", ":[PORT]", error_str)

    # Remove usernames that might appear in paths
    error_str = re.sub(r"/home/\w+", "/home/[USER]", error_str)
    error_str = re.sub(r"/Users/\w+", "/Users/[USER]", error_str)

    return error_str
