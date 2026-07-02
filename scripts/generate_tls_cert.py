"""
Generates a self-signed TLS cert/key pair for the Wi-Fi upload portal
(project_objectives.txt requires TLS on the Uvicorn instance users connect
to over the kiosk's local AP — there's no CA-issued cert available since
the portal is only ever reached at a LAN IP, never a public domain).

Usage:
    python scripts/generate_tls_cert.py [output_dir]

Then point WebAppThreadManager at the output:
    WebAppThreadManager(ssl_certfile="certs/cert.pem", ssl_keyfile="certs/key.pem")
"""
import datetime
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "aio-spark-kiosk.local"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("aio-spark-kiosk.local"),
                x509.IPAddress(ipaddress.IPv4Address("192.168.4.1")),  # typical RaspAP gateway IP
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path = output_dir / "key.pem"
    cert_path = output_dir / "cert.pem"

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Wrote {cert_path} and {key_path} (valid 825 days)")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("certs")
    generate(out)
