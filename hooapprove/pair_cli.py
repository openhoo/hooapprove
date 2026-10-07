"""Private owner-side QR pairing. Never expose this command as an agent tool."""

import argparse
import getpass
import os
import warnings
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
    try:
        parsed = urlparse(args.url)
        _ = parsed.port  # Access validates port syntax and range.
    except ValueError:
        parser.error("Use a valid service origin")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        parser.error("Use only the service origin, without credentials, path, query or fragment")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        parser.error("Use HTTPS or a local loopback demo")
    try:
        import segno
    except ImportError:
        parser.error("Install pairing support first: uv sync --extra pairing")
    # Reserve privately before creating the credential; no clobber or symlink following.
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        parser.error("Cannot create private QR file; choose a new file in an existing directory")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Executor token (hidden): ")
        if not token:
            raise RuntimeError("Executor token is required")
        with httpx.Client(
            base_url=args.url.rstrip("/"), timeout=15, follow_redirects=False
        ) as client:
            response = client.post(
                "/v1/pairings",
                headers={"Authorization": "Bearer " + token},
                json={"subject": args.subject, "label": args.label},
            )
        if response.status_code != 201:
            parser.exit(
                1,
                f"Pairing failed (HTTP {response.status_code}); recipient may already be paired.\n",
            )
        value = response.json()
        with os.fdopen(fd, "wb") as output:
            fd = -1
            segno.make_qr(value["uri"]).save(output, kind="png", scale=8)
        print(
            f"Private QR saved to {args.output}. Scan in HooApprove within 5 minutes, then delete the image."
        )
    except BaseException as error:
        if fd >= 0:
            os.close(fd)
        args.output.unlink(missing_ok=True)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        # Network and QR errors may include credential-bearing response data.
        parser.exit(
            1, "Pairing failed; private QR file removed. Check the service and try again.\n"
        )


if __name__ == "__main__":
    main()
