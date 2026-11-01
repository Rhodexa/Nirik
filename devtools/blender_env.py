"""Locate Blender and build the environment for dev runs and tests.

Blender lookup order: $BLENDER, the newest official build unpacked in
~/.local/opt/blender-*/, then `blender` on PATH.

OCIO workaround: Fedora's Blender 5.1 ships a v2.5 OCIO config but links
OpenColorIO 2.4, so Blender silently falls back to "Standard" only (no AgX).
When the OpenColorIO library Blender loads is older than the config, we write
a copy of the config with its version lowered and absolute search paths, and
point OCIO at it. Official builds bundle a matching library and need nothing.
Only processes started through this module are affected.

Usage:
  python -m devtools.blender_env [blender args...]   launch Blender
  python -m devtools.blender_env --extensions-dir    print the user extensions dir
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"


def _official_builds() -> list[Path]:
    builds = Path.home().glob(".local/opt/blender-*/blender")

    def version_key(exe: Path):
        m = re.match(r"blender-(\d+)\.(\d+)\.(\d+)", exe.parent.name)
        return tuple(map(int, m.groups())) if m else (0, 0, 0)

    return sorted(builds, key=version_key, reverse=True)


def blender_path() -> str:
    path = os.environ.get("BLENDER")
    if not path:
        official = _official_builds()
        path = str(official[0]) if official else shutil.which("blender")
    if not path:
        sys.exit("Blender not found: install it or set BLENDER=/path/to/blender")
    return path


def _version(text: str) -> tuple[int, int]:
    major, minor = text.split(".")[:2]
    return int(major), int(minor)


def _system_ocio_config() -> Path | None:
    exe = Path(blender_path()).resolve()
    candidates = [*exe.parent.glob("*/datafiles/colormanagement/config.ocio"),
                  *Path("/usr/share/blender").glob("*/datafiles/colormanagement/config.ocio")]
    return candidates[0] if candidates else None


def _ocio_lib_version() -> tuple[int, int] | None:
    bundled = Path(blender_path()).resolve().parent / "lib"
    versions = [m.group(1) for p in bundled.glob("libOpenColorIO.so.*")
                if (m := re.fullmatch(r"libOpenColorIO\.so\.(\d+\.\d+)", p.name))]
    if versions:
        return max(map(_version, versions))
    try:
        out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True).stdout
    except OSError:
        return None
    m = re.search(r"libOpenColorIO\.so\.(\d+\.\d+)", out)
    return _version(m.group(1)) if m else None


def patched_ocio_config() -> Path | None:
    """Path to a compatible OCIO config, or None when no patch is needed."""
    config = _system_ocio_config()
    lib = _ocio_lib_version()
    if config is None or lib is None:
        return None
    text = config.read_text()
    m = re.search(r"^ocio_profile_version:\s*(\d+\.\d+)", text, re.M)
    if not m or _version(m.group(1)) <= lib:
        return None

    text = text.replace(m.group(0), f"ocio_profile_version: {lib[0]}.{lib[1]}")
    sp = re.search(r'^search_path:\s*"([^"]*)"', text, re.M)
    if sp:
        dirs = ":".join(str(config.parent / d) for d in sp.group(1).split(":"))
        text = text.replace(sp.group(0), f'search_path: "{dirs}"')

    out = CACHE / "ocio" / "config.ocio"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text() != text:
        out.write_text(text)
    return out


def blender_env() -> dict[str, str]:
    env = dict(os.environ)
    if "OCIO" not in env:
        patched = patched_ocio_config()
        if patched:
            env["OCIO"] = str(patched)
    return env


def blender_cmd(*args: str) -> list[str]:
    return [blender_path(), *args]


def user_extensions_dir() -> str:
    out = subprocess.run(
        blender_cmd("-b", "--factory-startup", "--python-expr",
                    "import bpy; print('EXT_DIR=' + bpy.utils.user_resource('EXTENSIONS'))"),
        env=blender_env(), capture_output=True, text=True).stdout
    return re.search(r"^EXT_DIR=(.*)$", out, re.M).group(1) + "/user_default"


if __name__ == "__main__":
    if sys.argv[1:] == ["--extensions-dir"]:
        print(user_extensions_dir())
        sys.exit()
    cmd = blender_cmd(*sys.argv[1:])
    os.execvpe(cmd[0], cmd, blender_env())
