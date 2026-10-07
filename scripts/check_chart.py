"""Verify the production chart accepts only digest-pinned images and HTTPS origins."""

import subprocess
from pathlib import Path

CHART = Path(__file__).resolve().parents[1] / "deploy"
IMAGE = "ghcr.io/openhoo/hooapprove@sha256:" + "a" * 64


def render(image, public_url="https://approve.example"):
    return subprocess.run(
        [
            "helm",
            "template",
            "review",
            str(CHART),
            "--set-string",
            f"image={image}",
            "--set-string",
            f"publicUrl={public_url}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def main():
    accepted = render(IMAGE)
    assert accepted.returncode == 0, accepted.stderr
    assert IMAGE in accepted.stdout
    assert "replicas: 1" in accepted.stdout
    assert "type: Recreate" in accepted.stdout
    for image in ("", "ghcr.io/openhoo/hooapprove:latest", IMAGE[:-1], IMAGE + "suffix"):
        assert render(image).returncode != 0, "Chart accepted an unpinned image"
    for url in (
        "http://approve.example",
        "https://operator:private@approve.example",
        "https://approve.example/api",
        "https://approve.example?token=private",
    ):
        assert render(IMAGE, url).returncode != 0, "Chart accepted an unsafe origin"
    print("Chart: digest pinning, HTTPS origins and single-replica Recreate verified")


if __name__ == "__main__":
    main()
