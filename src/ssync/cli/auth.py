"""Authentication management CLI commands."""

import os
import secrets
import sys
from pathlib import Path

import click
import yaml

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


@click.group()
def auth():
    """Manage API authentication."""
    pass


@auth.command()
@click.option("--force", is_flag=True, help="Overwrite existing API key")
def setup(force):
    """Set up API authentication (one-time setup for new users)."""

    click.echo("🔐 Setting up SLURM Manager authentication...\n")

    # Check if API key already exists
    config_dir = Path.home() / ".config" / "ssync"
    config_file = config_dir / "config.yaml"
    api_key_file = config_dir / ".api_key"

    existing_key = None

    # Check environment variable
    if os.getenv("SSYNC_API_KEY"):
        existing_key = "environment variable (SSYNC_API_KEY)"

    # Check config file
    elif config_file.exists():
        try:
            with open(config_file, "r") as f:
                config_data = yaml.safe_load(f) or {}
                if config_data.get("api_key"):
                    existing_key = "config file"
        except Exception:
            pass

    # Check API key file
    elif api_key_file.exists():
        existing_key = "API key file"

    if existing_key and not force:
        click.echo(f"✅ API key already configured in {existing_key}")
        click.echo("Use --force to generate a new key\n")

        # Show current key (partially masked)
        if api_key_file.exists():
            try:
                key = api_key_file.read_text().strip()
                masked_key = f"{key[:8]}...{key[-4:]}"
                click.echo(f"Current key: {masked_key}")
            except Exception:
                pass

        return

    # Generate new API key
    api_key = secrets.token_urlsafe(32)

    # Create config directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)

    # Save API key to file (preferred method)
    api_key_file.write_text(api_key)
    api_key_file.chmod(0o600)  # Restrict permissions

    click.echo(
        f"✅ Generated new API key: {click.style(api_key, fg='green', bold=True)}"
    )
    click.echo(f"✅ Saved to: {api_key_file}\n")

    # Update config file if it exists
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config_data = yaml.safe_load(f) or {}

            # Add API key to config
            config_data["api_key"] = api_key

            with open(config_file, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False)

            click.echo(f"✅ Updated config file: {config_file}")
        except Exception as e:
            click.echo(f"⚠️  Could not update config file: {e}")

    # Show usage instructions
    click.echo("\n" + "=" * 50)
    click.echo("🎉 Authentication setup complete!\n")
    click.echo("The API will now use this key automatically.")
    click.echo("\nTo use with the web UI, add to your environment:")
    click.echo(f"  export SSYNC_API_KEY={api_key}")
    click.echo("\nOr add to your frontend configuration.")
    click.echo("=" * 50)


@auth.command()
@click.option("--reveal", is_flag=True, help="Show the full API key (security risk!)")
def show(reveal):
    """Show current API key configuration."""

    # Check various sources
    sources = []

    # Environment variable
    if os.getenv("SSYNC_API_KEY"):
        key = os.getenv("SSYNC_API_KEY")
        display_key = key if reveal else f"{key[:8]}...{key[-4:]}"
        sources.append(("Environment variable", display_key, "SSYNC_API_KEY"))

    # Config file
    config_file = Path.home() / ".config" / "ssync" / "config.yaml"
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config_data = yaml.safe_load(f) or {}
                if config_data.get("api_key"):
                    key = config_data["api_key"]
                    display_key = key if reveal else f"{key[:8]}...{key[-4:]}"
                    sources.append(("Config file", display_key, str(config_file)))
        except Exception:
            pass

    # API key file
    api_key_file = Path.home() / ".config" / "ssync" / ".api_key"
    if api_key_file.exists():
        try:
            key = api_key_file.read_text().strip()
            display_key = key if reveal else f"{key[:8]}...{key[-4:]}"
            sources.append(("API key file", display_key, str(api_key_file)))
        except Exception:
            pass

    if not sources:
        click.echo("❌ No API key configured")
        click.echo("Run 'ssync auth setup' to generate one")
    else:
        if reveal:
            click.echo(
                click.style(
                    "⚠️  WARNING: Full API key will be displayed!", fg="red", bold=True
                )
            )
            click.echo("Make sure no one else can see your screen.\n")

        click.echo("🔐 API Key Configuration:\n")
        for source, key, location in sources:
            click.echo(f"  {source}:")
            click.echo(f"    Key: {click.style(key, fg='yellow')}")
            click.echo(f"    Location: {location}\n")

        if len(sources) > 1:
            click.echo("⚠️  Multiple API keys found. Priority order:")
            click.echo("  1. Environment variable (SSYNC_API_KEY)")
            click.echo("  2. Config file (config.yaml)")
            click.echo("  3. API key file (.api_key)")


@auth.command()
def test():
    """Test API authentication."""
    from ..web.client import AuthenticatedSlurmApiClient

    client = AuthenticatedSlurmApiClient()

    if not client.api_key:
        click.echo("❌ No API key configured")
        click.echo("Run 'ssync auth setup' to generate one")
        sys.exit(1)

    masked_key = f"{client.api_key[:8]}...{client.api_key[-4:]}"
    click.echo(f"🔑 Using API key: {masked_key}")

    # Check if server is running
    if not client.is_running():
        click.echo("⚠️  API server is not running")
        click.echo("Starting server...")
        if not client.start_server(Path.home() / ".config" / "ssync" / "config.yaml"):
            click.echo("❌ Failed to start API server")
            sys.exit(1)

    # Test authentication
    if client.test_auth():
        click.echo("✅ Authentication successful!")
    else:
        click.echo("❌ Authentication failed!")
        click.echo("Please check your API key configuration")
        sys.exit(1)


@auth.command()
@click.option("--secure/--insecure", default=True, help="Use secure or insecure API")
def migrate(secure):
    """Migrate from insecure to secure API."""

    if secure:
        click.echo("🔒 Migrating to secure API...\n")

        # Ensure API key exists
        api_key_file = Path.home() / ".config" / "ssync" / ".api_key"
        if not api_key_file.exists():
            click.echo("No API key found. Generating one...")
            ctx = click.get_current_context()
            ctx.invoke(setup)

        # Update any running services
        click.echo("\n✅ Migration complete!")
        click.echo("The secure API will be used for all future operations.")
        click.echo("\nTo start the secure API server:")
        click.echo("  ssync-web --secure")

    else:
        click.echo("⚠️  Reverting to insecure API...")
        click.echo("This is not recommended for production use.")
        click.echo("\nTo start the insecure API server:")
        click.echo("  ssync-web --insecure")


@auth.command()
def disable():
    """Disable authentication (not recommended)."""

    click.echo("⚠️  This will disable API authentication.")
    click.echo("This is NOT recommended for production use.\n")

    if not click.confirm("Are you sure you want to disable authentication?"):
        click.echo("Cancelled.")
        return

    # Set environment variable to disable auth
    click.echo("\nTo disable authentication, set this environment variable:")
    click.echo("  export SSYNC_REQUIRE_API_KEY=false")
    click.echo("\nOr start the server with:")
    click.echo("  SSYNC_REQUIRE_API_KEY=false ssync-web")
    click.echo("\n⚠️  Remember to re-enable authentication for production use!")


def add_auth_commands(cli):
    """Add auth commands to the main CLI."""
    cli.add_command(auth)
