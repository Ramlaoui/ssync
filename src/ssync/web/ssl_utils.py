"""SSL certificate generation and management utilities."""

import ipaddress
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


def get_cert_dir() -> Path:
    """Get the directory for storing SSL certificates."""
    cert_dir = Path.home() / ".config" / "ssync" / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    return cert_dir


def generate_self_signed_cert(hostname: str = "localhost") -> tuple[Path, Path]:
    """
    Generate a self-signed certificate for local development.

    Returns:
        Tuple of (cert_path, key_path)
    """
    cert_dir = get_cert_dir()
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    # Check if valid certificates already exist
    if cert_path.exists() and key_path.exists():
        # Check if cert is still valid
        try:
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read(), default_backend())
                if cert.not_valid_after_utc > datetime.now(timezone.utc):
                    return cert_path, key_path
        except Exception:
            pass

    logger.info("Generating self-signed SSL certificate...")

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    # Generate certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "State"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "City"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ssync"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    # Write private key
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    key_path.chmod(0o600)

    # Write certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    logger.info(f"✓ SSL certificate generated at {cert_path}")
    logger.info(
        "  Note: You'll see a browser warning about the self-signed certificate."
    )
    logger.info(
        "  This is normal for local development. Accept the certificate to proceed."
    )

    return cert_path, key_path


def install_cert_to_system(cert_path: Path) -> bool:
    """
    Try to install certificate to system trust store (optional).
    This reduces browser warnings but requires admin privileges.
    """
    system = os.uname().sysname.lower()

    try:
        if system == "darwin":  # macOS
            subprocess.run(
                [
                    "security",
                    "add-trusted-cert",
                    "-d",
                    "-r",
                    "trustRoot",
                    "-k",
                    "/Library/Keychains/System.keychain",
                    str(cert_path),
                ],
                check=True,
                capture_output=True,
            )
            logger.info("✓ Certificate added to macOS keychain")
            return True
        elif system == "linux":
            # Different Linux distros have different methods
            # This is Ubuntu/Debian specific
            cert_dest = Path("/usr/local/share/ca-certificates/ssync.crt")
            subprocess.run(["sudo", "cp", str(cert_path), str(cert_dest)], check=True)
            subprocess.run(["sudo", "update-ca-certificates"], check=True)
            logger.info("✓ Certificate added to Linux trust store")
            return True
    except subprocess.CalledProcessError:
        logger.info(
            "ℹ Could not add certificate to system trust store (requires admin)"
        )
    except Exception:
        pass

    return False
