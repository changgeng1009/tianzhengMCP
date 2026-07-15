# 配置 CLI 参考（草稿）

## 当前实际 CLI

`scripts/skill_cli.py` 当前只注册：

- `inspect-manifest`
- `validate-manifest`
- `select-runtime`
- `build-plan --dry-run`
- `capabilities --mode ...`

注册代码位于 `scripts/skill_cli.py:38`–`:44`。该文件尚未接入 WP1 的 1.0→1.1.0 loader/migrator，也未接入 WP3 Registry/Plan APIs。由于主 Schema 已升级为 canonical 1.1.0，旧 CLI 对旧 examples 的兼容性必须由后续实现和测试恢复；当前不得声明 CLI 已验证通过。

## 待实现命令

以下均为需求，不是当前可用命令：

```text
manifest validate / normalize / explain / migrate / diff
config resolve
runtime select
product select
backend select
workflow select
plan build / verify / hash
simulate --backend offline|nextgen_mock
templates list / create
```

## 预定输出合同

- 成功输出 UTF-8、确定性排序 JSON。
- 失败输出 `{ok:false,error:{code,message,field,source,details,suggested_action}}`。
- 预定 exit codes：0 success、2 validation、3 conflict、4 backend、5 approval、6 path、7 version、8 baseline、9 internal。
- 默认 offline，不读取 CAD 文件，不连接 CAD/COM/天正。
- 保留旧命令别名，不静默删除。

这些输出和 exit code 必须在 CLI 实现与 test_agent 验证后回填为“已验证”。

