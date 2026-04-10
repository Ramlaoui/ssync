"""CLI-facing launcher for the ssync web interface."""

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import click

from ..utils.config import config
from ..utils.logging import setup_logger
from ..web.ssl_utils import generate_self_signed_cert
from .server import ServerManager

logger = setup_logger(__name__)


def _frontend_root() -> Path:
    return Path(__file__).parent.parent.parent.parent / "web-frontend"


def _frontend_dist() -> Path:
    return _frontend_root() / "dist"


def check_frontend_built() -> bool:
    """Return True when the compiled web frontend is available."""
    dist = _frontend_dist()
    return dist.exists() and (dist / "index.html").exists()


def build_frontend() -> bool:
    """Build the frontend assets if needed for the web UI."""
    frontend_dir = _frontend_root()

    try:
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("npm is not installed. Please install Node.js and npm first.")
        return False

    logger.info("Building frontend...")

    if not (frontend_dir / "node_modules").exists():
        logger.info("Installing frontend dependencies...")
        result = subprocess.run(
            ["npm", "install"], cwd=frontend_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"Failed to install dependencies: {result.stderr}")
            return False

    result = subprocess.run(
        ["npm", "run", "build"], cwd=frontend_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"Failed to build frontend: {result.stderr}")
        return False

    logger.info("Frontend built successfully")
    return True


def _build_server_manager(*, host: str, port: int, use_https: bool) -> ServerManager:
    protocol = "https" if use_https else "http"
    return ServerManager(url=f"{protocol}://{host}:{port}")


def _foreground_env(host: str) -> dict[str, str]:
    env = os.environ.copy()
    if host == "0.0.0.0":
        current_trusted = env.get("SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1")
        env["SSYNC_TRUSTED_HOSTS"] = f"{current_trusted},0.0.0.0"
    env["SSYNC_CONFIG_PATH"] = str(config.config_path)
    return env


def _foreground_cmd(*, host: str, port: int, use_https: bool) -> list[str]:
    cmd = [
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
        cert_path, key_path = generate_self_signed_cert()
        cmd.extend(["--ssl-keyfile", str(key_path), "--ssl-certfile", str(cert_path)])
    return cmd


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
    use_https = not no_https
    protocol = "https" if use_https else "http"
    url = f"{protocol}://localhost:{port}"
    server = _build_server_manager(host=host, port=port, use_https=use_https)

    if stop:
        if server.stop():
            logger.info("Server stopped.")
        else:
            logger.info("No server running.")
        return

    if status:
        if server.is_running():
            logger.info(f"ssync is running at {url}")
        else:
            logger.info(f"ssync is not running at {url}")
        return

    if server.is_running():
        logger.info(f"ssync is already running at {url}")
        logger.info("To stop the server: ssync web --stop")
        if not no_browser:
            webbrowser.open(url)
        return

    if not skip_build and not check_frontend_built():
        logger.info("Frontend not built. Building now...")
        if not build_frontend():
            logger.warning("Could not build frontend. API will run without UI.")
            logger.warning(
                "To build manually: cd web-frontend && npm install && npm run build"
            )

    logger.info(f"Starting ssync on port {port}...")

    if foreground:
        logger.info("Running in foreground mode. Press Ctrl+C to stop.")
        try:
            subprocess.run(
                _foreground_cmd(host=host, port=port, use_https=use_https),
                env=_foreground_env(host),
            )
        except KeyboardInterrupt:
            logger.info("Server stopped.")
        return

    if not server.start(config.config_path):
        logger.error("Failed to start server")
        return

    started = False
    for _ in range(20):
        time.sleep(0.5)
        if server.is_running():
            started = True
            break

    if not started:
        logger.error("Failed to start server")
        server.stop()
        return

    logger.info(f"ssync is running at {url}")
    logger.info("The server is running in the background.")
    logger.info("To stop it: ssync web --stop")
    logger.info("To check status: ssync web --status")
    if not no_browser:
        webbrowser.open(url)


__all__ = ["build_frontend", "check_frontend_built", "main"]
