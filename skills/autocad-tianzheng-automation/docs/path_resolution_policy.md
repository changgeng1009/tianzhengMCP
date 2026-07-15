# 路径解析策略

## 核心规则

`ManifestPathResolver` 只做 Windows 词法解析，见 `config/path_resolver.py:66`。它使用字符串和 `ntpath`，不调用 `open`、`read`、`stat`、`exists`、文件哈希或 strict resolve。

- 相对路径相对于 Manifest 所在目录，而不是当前 PowerShell cwd。
- 默认策略为 `project_relative`。
- `..` 直接阻断为 `PATH_TRAVERSAL_BLOCKED`。
- UNC 默认阻断为 `PATH_UNC_NOT_ALLOWED`。
- 外部绝对路径默认阻断为 `PATH_EXTERNAL_NOT_ALLOWED`。
- source/output 同路径阻断为 `PATH_SOURCE_OUTPUT_COLLISION`。
- 输出不得位于统一 Skill 安装目录或原始 GitHub Skill 根。
- 大小写和斜杠只做词法规范化，不接触磁盘。

## 支持策略

| 策略 | 行为 |
|---|---|
| `project_relative` | 相对 Manifest 目录并必须位于 project root |
| `workspace_relative` | 相对显式 workspace root |
| `absolute_explicit` | 仅显式允许外部路径时接受绝对路径 |
| `external_readonly` | 只允许显式、只读输入；禁止输出 |

默认配置把 `allow_external=false`、`allow_unc=false` 作为安全权限，普通 override 不能提升。

## Symlink 与 Junction

本层不探测文件系统，所以输出 `runtime_boundary_verification_required=true`。未来安全后端必须独立观察边界，并调用 `validate_runtime_boundary_observation()`；观察到越界时返回 `PATH_SYMLINK_BOUNDARY_VIOLATION`。在该验证发生前，不得声明路径已通过真实边界验证。

## CAD 文件边界

路径字符串可以声明 `.dwg/.dxf`，但解析器不得打开、读取、扫描或哈希目标。Manifest 中的 expected hash 只是未来验证要求，不是本阶段的验证证据。

