"""Private owner-side QR pairing. Never expose this command as an agent tool."""

import argparse
import getpass
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main():
    parser = argparse.ArgumentParser(description="Pair a phone without an account or login")
    parser.add_argument("--url", default="https://approve.openhoo.dev")
    parser.add_argument(
        "--subject", required=True, help="Fixed recipient configured in your executor"
    )
    parser.add_argument(
        "--label", required=True, help="Recognizable connection name shown on the phone"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Private PNG file; must not already exist"
    )
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        parser.error("Use HTTPS or a local loopback demo")
    try:
        import segno
    except ImportError:
        parser.error("Install pairing support first: uv sync --extra pairing")
    # Reserve privately before creating the credential; no clobber or symlink following.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        token = getpass.getpass("Executor token (hidden): ")
        with httpx.Client(
            base_url=args.url.rstrip("/"), timeout=15, follow_redirects=False
        ) as client:
            response = client.post(
                "/v1/pairings",
                headers={"Authorization": "Bearer " + token},
                json={"subject": args.subject, "label": args.label},
            )
        if response.status_code != 201:
            raise RuntimeError(
                f"Pairing failed (HTTP {response.status_code}); recipient may already be paired"
            )
        value = response.json()
        with os.fdopen(fd, "wb") as output:
            fd = -1
            segno.make_qr(value["uri"]).save(output, kind="png", scale=8)
        print(
            f"Private QR saved to {args.output}. Scan in HooApprove within 5 minutes, then delete the image."
        )
    except BaseException:
        if fd >= 0:
            os.close(fd)
        args.output.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
