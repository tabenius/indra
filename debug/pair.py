"""Provision a per-pair key over adb into the bridge's private app storage."""

import argparse
import os
from pathlib import Path
import secrets
import subprocess

from .auth import DEFAULT_KEY, load_key


def pair(serial, key_path):
    path = Path(key_path)
    if path.exists():
        key = load_key(path)
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(key.hex() + "\n")
    # Key bytes travel on stdin, never argv, logs, Git or shared Android storage.
    subprocess.run(
        ["adb", "-s", serial, "shell", "run-as", "com.ragbaz.bridge", "sh", "-c",
         "'umask 077; mkdir -p files; cat > files/indra-debug.key.tmp && mv files/indra-debug.key.tmp files/indra-debug.key'"],
        input=(key.hex() + "\n").encode(), check=True, timeout=15,
    )
    print(f"Pairing key provisioned to bridge private storage; host key: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY)
    args = parser.parse_args()
    try:
        pair(args.serial, args.key_file)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"pairing failed: {exc}\n")
