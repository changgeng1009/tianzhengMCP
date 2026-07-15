# Manifest 版本与迁移

## 兼容矩阵

| 输入版本 | 处理 |
|---|---|
| `1.0` | 规范化为 `1.0.0` 后迁移 |
| `1.0.0` | 迁移到 `1.1.0` |
| `1.1.0` | 已是 canonical，不迁移 |
| 低于 `1.0` | `MANIFEST_VERSION_TOO_OLD` |
| 高于 `1.1.0` | `MANIFEST_VERSION_TOO_NEW` |
| 无已验证路径 | `MANIFEST_VERSION_UNSUPPORTED` |

实现见 `config/versioning.py:29` 和 `config/migrator.py:89`。WP1 已对现有 5 个旧示例完成离线迁移自检；正式 `tests/config_driven` 尚待 test_agent。

## 迁移原则

1. 先用旧 Schema 验证输入。
2. 拒绝未知顶层字段，不静默丢弃。
3. 拒绝 `production_allowed=true` 或 `production_d1_allowed=true`。
4. 不继承旧 approval；存在审批对象时返回 `CONFIG_APPROVAL_INHERITANCE_FORBIDDEN`。
5. 将旧 checkpoint、identity、options 等放入显式 `extensions.legacy_*`，保留可追踪性。
6. 不生成时间、随机 UUID、approval 或真实身份验证结论。
7. 迁移结果重新用 1.1.0 Schema 验证。

## API

- `ManifestVersionPolicy.normalize(version)`
- `ManifestVersionPolicy.migration_path(version)`
- `ManifestMigrator.preview(manifest)`
- `ManifestMigrator.migrate(manifest)`
- `ManifestLoader.load_canonical(path)`

`preview()` 返回字段变化、deprecated、无法迁移字段和 warnings。写出 `.migrated.json` 的 CLI 尚未实现，不得原地覆盖旧 Manifest。

## 已知限制

- 当前迁移器只覆盖项目已有 1.0 字段集合。
- 带实际旧审批票据的 Manifest 必须人工移除票据后再迁移。
- 迁移保留身份声明，不验证磁盘文档。
- CLI migrate/diff 尚待实现和验证。

