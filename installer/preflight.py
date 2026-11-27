"""Check installation prerequisites without changing the host."""

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def command_ok(command):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    root = Path(__file__).resolve().parents[1]

    checks = {
        "Linux": platform.system() == "Linux",
        "Python >= 3.10": sys.version_info >= (3, 10),
        "Non-root user": os.getuid() != 0,
        "PyYAML": importlib.util.find_spec("yaml") is not None,
        "WebSocket client": importlib.util.find_spec("websocket") is not None,
        "Docker CLI": shutil.which("docker") is not None,
        "Docker Compose": command_ok(["docker", "compose", "version"]),
        "Docker access": (
            command_ok(["docker", "info"])
            or command_ok(["sudo", "-n", "docker", "info"])
        ),
        "Free disk >= 3 GiB": shutil.disk_usage(root).free >= 3 * 1024**3,
        "Writable installation": os.access(root, os.W_OK)
    }

    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
