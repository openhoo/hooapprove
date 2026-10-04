"""Start an isolated real HTTP approval server and test Shooping's actual adapter against it."""

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from hooapprove.app import create_app
from hooapprove.config import Settings


def main():
    worktree = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="hooapprove-wire-") as directory:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        settings = Settings(
            database=str(Path(directory) / "test.db"),
            public_url=url,
            demo=True,
            services={
                "rewe": {"token": "wire-proof-service-" + "a" * 40, "subjects": ["demo-human"]}
            },
        )
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings),
                host="127.0.0.1",
                port=port,
                access_log=False,
                log_level="error",
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.02)
            if not server.started:
                raise RuntimeError("Isolated approval server did not start")
            result = subprocess.run(
                ["node", str(Path(__file__).with_name("rewe-wire-proof.mjs")), url, str(worktree)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            proof = json.loads(result.stdout.strip())
            print(json.dumps(proof, indent=2))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
