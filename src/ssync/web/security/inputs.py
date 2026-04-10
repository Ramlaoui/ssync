"""Validation, sanitization, and rate limiting helpers for the web API."""

import hashlib
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from ...models.job import JobState
from ...utils.logging import setup_logger

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
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _cleanup_old_requests(self, client_id: str, current_time: float):
        cutoff = current_time - 3600
        self._request_counts[client_id] = [
            ts for ts in self._request_counts[client_id] if ts > cutoff
        ]

    def _refill_tokens(self, client_id: str, current_time: float):
        time_passed = current_time - self._last_refill[client_id]
        tokens_to_add = int(time_passed * self.burst_size / 60)

        if tokens_to_add > 0:
            self._burst_tokens[client_id] = min(
                self.burst_size, self._burst_tokens[client_id] + tokens_to_add
            )
            self._last_refill[client_id] = current_time

    async def check_rate_limit(self, request: Request) -> bool:
        client_id = self._get_client_id(request)
        current_time = time.time()

        self._cleanup_old_requests(client_id, current_time)
        self._refill_tokens(client_id, current_time)

        requests = self._request_counts[client_id]
        hour_ago = current_time - 3600
        hour_requests = [ts for ts in requests if ts > hour_ago]
        if len(hour_requests) >= self.requests_per_hour:
            return False

        minute_ago = current_time - 60
        minute_requests = [ts for ts in requests if ts > minute_ago]
        if len(minute_requests) >= self.requests_per_minute:
            if self._burst_tokens[client_id] <= 0:
                return False
            self._burst_tokens[client_id] -= 1

        self._request_counts[client_id].append(current_time)
        return True


class PathValidator:
    """Validate and sanitize file paths to prevent traversal attacks."""

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
    def validate_path(cls, path: str, user_home: Optional[Path] = None) -> Path:
        if not path:
            raise HTTPException(status_code=400, detail="Path cannot be empty")

        for component in cls.BLACKLISTED_COMPONENTS:
            if component in path:
                raise HTTPException(
                    status_code=400, detail="Invalid path component detected"
                )

        try:
            resolved_path = Path(path).expanduser().resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path format")

        path_str = str(resolved_path)
        for pattern in cls.SENSITIVE_FILES:
            if re.match(pattern, path_str):
                raise HTTPException(
                    status_code=403, detail="Access to sensitive files is forbidden"
                )

        return resolved_path


class ScriptValidator:
    """Validate and sanitize Slurm scripts for security."""

    DANGEROUS_PATTERNS = [
        (r"rm\s+-rf\s+/", "Dangerous recursive deletion of root"),
        (r"chmod\s+777", "Overly permissive file permissions"),
        (r"sudo\s+", "Sudo commands not allowed"),
        (r">\s*/etc/", "Writing to system directories forbidden"),
        (r"curl\s+.*\|\s*(/bin/)?(sh|bash)", "Remote code execution attempt"),
        (r"wget\s+.*\|\s*(/bin/)?(sh|bash)", "Remote code execution attempt"),
        (r"nc\s+-l", "Network backdoor attempt"),
        (r"mkfifo\s+/tmp/", "Named pipe creation in tmp"),
        (r"/etc/passwd", "Access to system password file"),
        (r"/etc/shadow", "Access to system shadow file"),
        (r"base64\s+-d.*\|\s*(/bin/)?(sh|bash)", "Encoded command execution"),
        (r"eval\s+.*\$", "Dynamic code evaluation"),
        (r"exec\s+.*<", "Input redirection to exec"),
    ]
    MAX_SCRIPT_SIZE = 1024 * 1024
    MAX_LINE_LENGTH = 10000

    @classmethod
    def validate_script(cls, script_content: str) -> str:
        if not script_content:
            raise HTTPException(status_code=400, detail="Script cannot be empty")

        if len(script_content) > cls.MAX_SCRIPT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Script too large (max {cls.MAX_SCRIPT_SIZE} bytes)",
            )

        lines = script_content.split("\n")
        for i, line in enumerate(lines):
            if len(line) > cls.MAX_LINE_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Line {i + 1} too long (max {cls.MAX_LINE_LENGTH} chars)",
                )

        for pattern, description in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, script_content, re.IGNORECASE | re.MULTILINE):
                logger.warning(f"Blocked script with pattern: {description}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Script contains forbidden pattern: {description}",
                )

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
        if not hostname:
            raise HTTPException(status_code=400, detail="Hostname cannot be empty")

        if not re.match(
            r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$",
            hostname,
        ):
            raise HTTPException(status_code=400, detail="Invalid hostname format")

        return hostname.lower()

    @staticmethod
    def sanitize_job_id(job_id: str) -> str:
        if not job_id:
            raise HTTPException(status_code=400, detail="Job ID cannot be empty")

        if not re.match(r"^[0-9]+(_(\[[\d\-,%]+\]|\d+))?$", job_id):
            raise HTTPException(status_code=400, detail="Invalid job ID format")

        return job_id

    @staticmethod
    def sanitize_username(username: str) -> str:
        if not username:
            return username

        if not re.match(r"^[a-z_][a-z0-9_\-]{0,31}$", username):
            raise HTTPException(status_code=400, detail="Invalid username format")

        return username

    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        if not text:
            return text

        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
        if len(text) > max_length:
            text = text[:max_length]

        dangerous_patterns = [
            r";\s*(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|EXEC)",
            r"--\s*$",
            r"/\*.*?\*/",
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"\b(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|EXEC|UNION|SELECT)\b",
        ]
        for pattern in dangerous_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip()


def normalize_device_token(token: str) -> str:
    normalized = re.sub(r"[^0-9a-fA-F]", "", token or "")
    if len(normalized) < 32:
        raise HTTPException(status_code=400, detail="Invalid device token")
    return normalized.lower()


def normalize_environment(environment: Optional[str]) -> Optional[str]:
    if environment is None:
        return None

    normalized = environment.lower()
    if normalized not in {"sandbox", "production"}:
        raise HTTPException(status_code=400, detail="Invalid environment value")

    return normalized


def sanitize_notification_preferences(data: dict[str, Any]) -> dict[str, Any]:
    allowed_states = data.get("allowed_states")
    if allowed_states is not None:
        valid_states = {state.value for state in JobState}
        for state in allowed_states:
            if state not in valid_states:
                raise HTTPException(
                    status_code=400, detail=f"Invalid job state: {state}"
                )

    def _sanitize_list(values, sanitizer):
        if values is None:
            return None
        return [sanitizer(value) for value in values]

    data["muted_job_ids"] = _sanitize_list(
        data.get("muted_job_ids"), InputSanitizer.sanitize_job_id
    )
    data["muted_hosts"] = _sanitize_list(
        data.get("muted_hosts"), InputSanitizer.sanitize_hostname
    )
    data["allowed_users"] = _sanitize_list(
        data.get("allowed_users"), InputSanitizer.sanitize_username
    )

    patterns = data.get("muted_job_name_patterns")
    if patterns is not None:
        data["muted_job_name_patterns"] = [
            InputSanitizer.sanitize_text(pattern, max_length=200)
            for pattern in patterns
        ]

    return data


def sanitize_error_message(error: Exception) -> str:
    error_str = str(error)
    error_str = re.sub(r"/home/\w+", "/home/[USER]", error_str)
    error_str = re.sub(r"/Users/\w+", "/Users/[USER]", error_str)
    error_str = re.sub(r"/[/\w\-\.]+", "[PATH]", error_str)
    error_str = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[IP]", error_str)
    error_str = re.sub(r":\d{2,5}", ":[PORT]", error_str)
    return error_str
