# TianzhengCadPlugin.bundle — manual installation

An ApplicationPlugins bundle for AutoCAD 2026 (R25.1, 64-bit Windows).

Installation is **manual and explicit**. Nothing here installs itself, modifies Trusted
Paths, changes `SECURELOAD`, or writes to the registry.

## Contents

```
TianzhengCadPlugin.bundle/
├── PackageContents.xml          (version + platform constraints, load metadata)
└── Contents/
    ├── TianzhengCadPlugin.dll
    ├── TianzhengCadPlugin.Protocol.dll
    └── TianzhengCadPlugin.Transport.dll
```

AutoCAD's own managed assemblies (`acmgd.dll`, `acdbmgd.dll`, `accoremgd.dll`) are **not**
included and must never be copied here — the AutoCAD process supplies them at runtime.

## 1. Build

```bash
dotnet build plugin/TianzhengCadPlugin.sln -c Release
```

## 2. Stage the bundle

```bash
python plugin/bundle/stage_bundle.py
```

This copies the three plugin assemblies into `Contents/`. It writes nowhere else.

## 3. Install (manual, per-user)

Copy the whole `TianzhengCadPlugin.bundle` directory to:

```
%APPDATA%\Autodesk\ApplicationPlugins\
```

Per-machine installation (`%PROGRAMDATA%\Autodesk\ApplicationPlugins\`) is possible but is
**not** performed by any script here, since it affects every user on the host.

## 4. Configure the session

The plugin refuses to open its listener without an injected token. Set these in the
environment of the AutoCAD process **before** starting it:

| Variable | Purpose |
|---|---|
| `TIANZHENG_PLUGIN_TOKEN` | Shared secret, minimum 32 characters (or `TIANZHENG_PLUGIN_TOKEN_FILE`) |
| `TIANZHENG_PLUGIN_PORT` | Loopback port (default 5987) |
| `TIANZHENG_PLUGIN_SANDBOX_ROOT` | Directory the plugin may save synthetic documents into |

Without `TIANZHENG_PLUGIN_SANDBOX_ROOT`, save is refused with `SANDBOX_NOT_CONFIGURED`.

## 5. Verify

Start AutoCAD 2026 and run `TZPLUGINSTATUS`. Expect:

```
state=READY listening=127.0.0.1:<port> protocol=2.0.0 readiness_state=AVAILABLE_SANDBOX_ENTITY_MVP
```

## Uninstall

Delete the `TianzhengCadPlugin.bundle` directory from `ApplicationPlugins`. Nothing else is
left behind: the plugin creates no registry keys and modifies no AutoCAD settings.

## Development loading

For development, prefer `NETLOAD` against the Release output instead of installing a bundle
— see `docs/S7_AUTOCAD_PLUGIN_BACKEND.md` §17. At the SECURELOAD prompt choose **Load once**,
never "Always load".
