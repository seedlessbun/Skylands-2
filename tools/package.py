"""Build the release zip: the Skylands mod plus the Willow2 Mod Manager it runs on.

The mod manager (bl-sdk, LGPL-3.0) is downloaded from its official GitHub release, checked
against a pinned SHA-256, and bundled with credit so Play works in one click. No game files
from Borderlands 2 or Skyrim are ever included.

Usage: python tools/package.py   -> dist/Skylands-<version>.zip and dist/entries.json
"""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "mod" / "skylands"
DIST = ROOT / "dist"
CACHE = ROOT / ".cache"

SDK_URL = "https://github.com/bl-sdk/willow2-mod-manager/releases/download/v3.8/willow2-sdk.zip"
SDK_SHA256 = "e1862ddb282cf845369c9ca1ca70ac180d6104cce25d8a133557fc74e157b4c7"
SDK_LICENSE_URL = "https://raw.githubusercontent.com/bl-sdk/willow2-mod-manager/v3.8/LICENSE"

MOD_FILES = ["__init__.py", "game.py", "progression.py", "sheet_data.py", "pyproject.toml",
             "skyrim/__init__.py", "skyrim/bsa.py", "skyrim/data.py", "skyrim/esm.py", "skyrim/lz4.py",
             "skyrim/strings.py"]


def fetch(url: str, dest: Path, sha256: str | None = None) -> bytes:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url) as r:  # noqa: S310 - fixed official URLs
            dest.write_bytes(r.read())
    data = dest.read_bytes()
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        dest.unlink()
        raise SystemExit(f"{url}: checksum mismatch")
    return data


def main() -> int:
    version = tomllib.loads((MOD / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    sdk_zip = CACHE / "willow2-sdk-v3.8.zip"
    fetch(SDK_URL, sdk_zip, SDK_SHA256)
    sdk_license = fetch(SDK_LICENSE_URL, CACHE / "willow2-LICENSE.txt").decode("utf-8")

    DIST.mkdir(exist_ok=True)
    out = DIST / f"Skylands-{version}.zip"
    entries: list[dict] = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def add(arc: str, data: bytes) -> None:
            info = zipfile.ZipInfo(arc, date_time=(2026, 10, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
            entries.append({"path": arc, "size": len(data)})

        with zipfile.ZipFile(sdk_zip) as sdk:
            for name in sorted(sdk.namelist()):
                if name.endswith("/") or "/.stubs/" in name:
                    continue
                add(name, sdk.read(name))
        for rel in MOD_FILES:
            add(f"sdk_mods/skylands/{rel}", (MOD / rel).read_bytes())
        add("sdk_mods/skylands/CREDITS.txt", (ROOT / "CREDITS.md").read_bytes())
        add("sdk_mods/skylands/README.txt", (MOD / "README.txt").read_bytes())
        add("sdk_mods/skylands/LICENSE-willow2-mod-manager.txt", sdk_license.encode("utf-8"))

    (DIST / "entries.json").write_text(json.dumps(entries, indent=1), encoding="utf-8")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size} bytes  sha256 {digest}  {len(entries)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
