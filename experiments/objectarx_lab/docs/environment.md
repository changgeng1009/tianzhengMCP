# ObjectARX Research Prototype — Environment Report

**Date:** 2026-07-16
**Status:** OBJECTARX_ENVIRONMENT_BLOCKED

## 1. AutoCAD

| Item | Value |
|------|-------|
| Version | AutoCAD 2026 |
| COM ProgID | `AutoCAD.Application.25` |
| CLSID | `{363E5B47-885D-44C3-89EB-A2AB2129B57E}` |
| Install Path | `E:\AutoCAD 2026\` |
| COM Automation | Confirmed (AutoCAD.Application.25 registered) |

AutoCAD 2026 is installed on E: drive and fully COM-accessible.
The current project's COM adapter can already reach this installation.

## 2. ObjectARX SDK

| Item | Status |
|------|--------|
| SDK installed | NOT FOUND |
| Search locations | `C:\ObjectARX*`, `C:\Autodesk\`, `D:\`, `E:\`, `C:\Program Files\Autodesk\` |
| SDK bundled with AutoCAD | NOT present in `E:\AutoCAD 2026\` |

The ObjectARX SDK is a separate download from Autodesk.
It is NOT bundled with the standard AutoCAD installation.
Download requires an Autodesk Developer Network account.

## 3. Visual Studio

| Item | Status |
|------|--------|
| Visual Studio | NOT INSTALLED |
| VS Installer | Present (shell only, `C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe`) |
| VS 2022 / 2019 | No editions found |
| C++ workload | NOT INSTALLED |
| MSBuild | NOT FOUND |
| cl.exe (MSVC) | NOT FOUND |
| CMake | NOT FOUND |
| .NET SDK | NOT FOUND |
| Windows SDK | 10.0.26100.0 (present but unusable without VS) |

vswhere.exe returns zero products — the Visual Studio Installer exists
but no Visual Studio edition has been installed.

## 4. ObjectARX SDK Version Requirements

For AutoCAD 2026, the required ObjectARX SDK corresponds to:
- **AutoCAD API version:** AcDb 25.0 / ObjectARX 2026
- **Required Visual Studio:** Visual Studio 2022 (17.x) with MSVC v143
- **Required Platform Toolset:** v143
- **Required Windows SDK:** 10.0

## 5. Summary of Gaps

| Requirement | Status |
|-------------|--------|
| ObjectARX SDK 2026 | MISSING |
| Visual Studio 2022 | MISSING |
| MSVC v143 C++ toolchain | MISSING |
| AutoCAD 2026 | PRESENT |

## 6. What Must Be Installed

To proceed past BLOCKED state:

1. **Visual Studio 2022** (Community, Professional, or Enterprise)
   - Workload: "Desktop development with C++"
   - This installs MSBuild, cl.exe, MSVC v143, Windows SDK

2. **ObjectARX SDK 2026**
   - Download from: https://www.autodesk.com/developer-network/platform-technologies/objectarx
   - Requires free Autodesk Developer Network registration
   - Install to a known path (e.g., `C:\ObjectARX 2026\`)

## 7. Decision

```
OBJECTARX_ENVIRONMENT_BLOCKED
```

No code can be written or compiled at this stage.
The environment lacks both the C++ toolchain and the SDK.
