"""Stage the plugin assemblies into the ApplicationPlugins bundle.

Copies ONLY this project's three assemblies. It refuses to stage any Autodesk managed DLL,
token or secret, and it writes nowhere outside the bundle directory. It does not install
the bundle — copying it into ApplicationPlugins is a deliberate manual step.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parent / "TianzhengCadPlugin.bundle"
CONTENTS = BUNDLE_DIR / "Contents"
BUILD_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "src" / "TianzhengCadPlugin" / "bin" / "Release" / "net8.0-windows"
)

PLUGIN_ASSEMBLIES = (
    "TianzhengCadPlugin.dll",
    "TianzhengCadPlugin.Protocol.dll",
    "TianzhengCadPlugin.Transport.dll",
)

#: Never redistribute AutoCAD's own assemblies.
FORBIDDEN = {"acmgd.dll", "acdbmgd.dll", "accoremgd.dll", "adwindows.dll", "acwindows.dll"}


def main() -> int:
    if not BUILD_OUTPUT.is_dir():
        print(f"build output not found: {BUILD_OUTPUT}\nrun: dotnet build -c Release", file=sys.stderr)
        return 2

    CONTENTS.mkdir(parents=True, exist_ok=True)

    staged: list[str] = []
    for name in PLUGIN_ASSEMBLIES:
        source = BUILD_OUTPUT / name
        if not source.is_file():
            print(f"missing assembly: {name}", file=sys.stderr)
            return 2
        shutil.copy2(source, CONTENTS / name)
        staged.append(name)

    # Fail loudly if anything forbidden ever ends up in the bundle.
    for item in CONTENTS.iterdir():
        if item.name.lower() in FORBIDDEN:
            print(f"refusing to ship Autodesk assembly: {item.name}", file=sys.stderr)
            return 3
        if item.suffix.lower() in {".token", ".dwg", ".dxf"}:
            print(f"refusing to ship {item.name}", file=sys.stderr)
            return 3

    print("staged into", CONTENTS)
    for name in staged:
        print("  ", name)
    print("\nInstall manually by copying TianzhengCadPlugin.bundle to")
    print(r"  %APPDATA%\Autodesk\ApplicationPlugins\")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
