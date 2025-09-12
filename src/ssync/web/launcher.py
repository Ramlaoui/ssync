"""Simple launcher for ssync web interface (API + UI)."""

import os
import signal
import subprocess
import sys
import time
import warnings
import webbrowser
from pathlib import Path

import click
import requests
from urllib3.exceptions import InsecureRequestWarning

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


def is_api_running(port: int = 8042, use_https: bool = True) -> bool:
    """Check if API is already running."""
    protocol = "https" if use_https else "http"
    try:
        # Suppress SSL warnings for self-signed certs
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)
            response = requests.get(
                f"{protocol}://localhost:{port}/health",
                timeout=1,
                verify=False,  # Allow self-signed certs
            )
            return response.status_code == 200
    except Exception:
        return False


def get_pid_file() -> Path:
    """Get the PID file path."""
    return Path.home() / ".config" / "ssync" / "ssync-web.pid"


def save_pid(pid: int):
    """Save the process PID."""
    pid_file = get_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid))


def get_saved_pid() -> int | None:
    """Get the saved PID if it exists."""
    pid_file = get_pid_file()
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except Exception:
            return None
    return None


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop_server():
    """Stop the running server."""
    pid = get_saved_pid()
    if pid and is_process_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"✓ Stopped server (PID: {pid})")
            get_pid_file().unlink(missing_ok=True)
            return True
        except Exception:
            logger.error(f"❌ Could not stop server (PID: {pid})")
            return False
    else:
        get_pid_file().unlink(missing_ok=True)
    return False


def check_frontend_built() -> bool:
    """Check if frontend is built."""
    frontend_dist = Path(__file__).parent.parent.parent.parent / "web-frontend" / "dist"
    return frontend_dist.exists() and (frontend_dist / "index.html").exists()


def build_frontend() -> bool:
    """Build the frontend if needed."""
    frontend_dir = Path(__file__).parent.parent.parent.parent / "web-frontend"

    # Check if npm is installed
    try:
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("❌ npm is not installed. Please install Node.js and npm first.")
        return False

    logger.info("Building frontend...")

    # Install dependencies if needed
    if not (frontend_dir / "node_modules").exists():
        logger.info("Installing frontend dependencies...")
        result = subprocess.run(
            ["npm", "install"], cwd=frontend_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"Failed to install dependencies: {result.stderr}")
            return False

    # Build frontend
    result = subprocess.run(
        ["npm", "run", "build"], cwd=frontend_dir, capture_output=True, text=True
    )

    if result.returncode == 0:
        logger.info("✓ Frontend built successfully")
        return True
    else:
        logger.error(f"Failed to build frontend: {result.stderr}")
        return False


def start_server_background(port: int, host: str = "127.0.0.1", use_https: bool = True):
    """Start the server in the background using nohup or direct detachment."""
    # Set up environment with proper trusted hosts for 0.0.0.0 binding
    env = os.environ.copy()
    if host == "0.0.0.0":
        current_trusted = env.get("SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1")
        env["SSYNC_TRUSTED_HOSTS"] = f"{current_trusted},0.0.0.0"

    # Generate SSL certificates if using HTTPS
    ssl_args = ""
    if use_https:
        from .ssl_utils import generate_self_signed_cert

        cert_path, key_path = generate_self_signed_cert()
        ssl_args = f"--ssl-keyfile {key_path} --ssl-certfile {cert_path}"

    # Method 1: Try using nohup if available (most Unix systems)
    try:
        subprocess.run(["which", "nohup"], capture_output=True, check=True)
        # Use nohup to fully detach the process
        log_file = Path.home() / ".config" / "ssync" / "ssync-web.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = f"nohup {sys.executable} -m uvicorn ssync.web.app:app --host {host} --port {port} {ssl_args} > {log_file} 2>&1 &"
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        # Get the actual uvicorn PID (not the shell PID)
        time.sleep(1)
        # Try to find the uvicorn process
        result = subprocess.run(
            f"pgrep -f 'uvicorn.*ssync.web.app.*{port}'",
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            pid = int(result.stdout.strip().split("\n")[0])
            save_pid(pid)
            return True
    except Exception:
        pass

    # Method 2: Python subprocess with full detachment
    try:
        # Build command args
        cmd_args = [
            sys.executable,
            "-m",
            "uvicorn",
            "ssync.web.app:app",
            "--host",
            host,
            "--port",
            str(port),
        ]

        # Add SSL args if using HTTPS
        if use_https:
            from .ssl_utils import generate_self_signed_cert

            cert_path, key_path = generate_self_signed_cert()
            cmd_args.extend(["--ssl-keyfile", str(key_path)])
            cmd_args.extend(["--ssl-certfile", str(cert_path)])

        # Use Python to spawn the process
        if sys.platform == "win32":
            # Windows
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                env=env,
            )
        else:
            # Unix/Linux/Mac
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=os.setpgrp,  # Fully detach from parent process group
                env=env,
            )

        save_pid(process.pid)
        return True
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return False


@click.command()
@click.option("--port", default=8042, help="Port to run on")
@click.option("--host", default="127.0.0.1", help="Host to bind the server to")
@click.option("--stop", is_flag=True, help="Stop the running server")
@click.option("--status", is_flag=True, help="Check server status")
@click.option("--foreground", is_flag=True, help="Run in foreground (don't detach)")
@click.option("--no-browser", is_flag=True, help="Don't open browser")
@click.option("--skip-build", is_flag=True, help="Skip frontend build check")
@click.option("--no-https", is_flag=True, help="Disable HTTPS (use HTTP instead)")
def main(
    port: int,
    host: str,
    stop: bool,
    status: bool,
    foreground: bool,
    no_browser: bool,
    skip_build: bool,
    no_https: bool,
):
    """Launch ssync web interface (API + UI in one server)."""

    # Handle stop command
    if stop:
        if stop_server():
            logger.info("Server stopped.")
        else:
            logger.info("No server running.")
        return

    # Handle status command
    if status:
        if is_api_running(port):
            pid = get_saved_pid()
            logger.info(f"✓ ssync is running on port {port} (PID: {pid})")
        else:
            logger.info(f"✗ ssync is not running on port {port}")
        return

    use_https = not no_https
    protocol = "https" if use_https else "http"
    url = f"{protocol}://localhost:{port}"

    # Check if already running
    if is_api_running(port, use_https):
        logger.info(f"✓ ssync is already running at {url}")
        pid = get_saved_pid()
        if pid:
            logger.info(f"  PID: {pid}")
        logger.info("\nTo stop the server: ssync web --stop")
        if not no_browser:
            webbrowser.open(url)
        return

    # Check if frontend is built
    if not skip_build and not check_frontend_built():
        logger.info("Frontend not built. Building now...")
        if not build_frontend():
            logger.warning("\n⚠️  Could not build frontend. API will run without UI.")
            logger.warning(
                "To build manually: cd web-frontend && npm install && npm run build"
            )

    # Start API server
    logger.info(f"Starting ssync on port {port}...")

    if foreground:
        # Run in foreground (useful for debugging)
        logger.info("Running in foreground mode. Press Ctrl+C to stop.")

        # Set up environment with proper trusted hosts for 0.0.0.0 binding
        env = os.environ.copy()
        if host == "0.0.0.0":
            current_trusted = env.get("SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1")
            env["SSYNC_TRUSTED_HOSTS"] = f"{current_trusted},0.0.0.0"

        cmd_args = [
            sys.executable,
            "-m",
            "uvicorn",
            "ssync.web.app:app",
            "--host",
            host,
            "--port",
            str(port),
        ]

        if use_https:
            from .ssl_utils import generate_self_signed_cert

            cert_path, key_path = generate_self_signed_cert()
            cmd_args.extend(["--ssl-keyfile", str(key_path)])
            cmd_args.extend(["--ssl-certfile", str(cert_path)])

        try:
            subprocess.run(cmd_args, env=env)
        except KeyboardInterrupt:
            logger.info("\nServer stopped.")
    else:
        # Run in background (default)
        if start_server_background(port, host, use_https):
            # Wait for server to start
            started = False
            for _ in range(20):
                time.sleep(0.5)
                if is_api_running(port, use_https):
                    started = True
                    break

            if started:
                pid = get_saved_pid()
                logger.info(f"✓ ssync is running at {url}")
                if pid:
                    logger.info(f"  PID: {pid}")
                logger.info("\nThe server is running in the background.")
                logger.info("To stop it: ssync web --stop")
                logger.info("To check status: ssync web --status")

                # Open browser
                if not no_browser:
                    webbrowser.open(url)
            else:
                logger.error("❌ Failed to start server")
                stop_server()
        else:
            logger.error("❌ Failed to launch server process")


if __name__ == "__main__":
    main()
