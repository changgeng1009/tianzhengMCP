# CLI Reference

```powershell
python -m mcp.skill_cli backend-list
python -m mcp.skill_cli backend-capabilities --backend com
python -m mcp.skill_cli backend-doctor --backend mock
python -m mcp.skill_cli inspect --config skill/configs/default.yaml --reference ref.pdf --source source.dwg --dry-run
python -m mcp.skill_cli diff --config skill/configs/default.yaml --dry-run
python -m mcp.skill_cli plan --config skill/configs/default.yaml --backend com --dry-run
python -m mcp.skill_cli execute-sandbox --backend mock --working-copy safe-copy.dwg --dry-run
python -m mcp.skill_cli qa --config skill/configs/default.yaml --dry-run
python -m mcp.skill_cli run --config skill/configs/default.yaml --run-id example --dry-run
python -m mcp.skill_cli validate-fixture
```

通用参数：`--backend`、`--config`、`--dry-run`、`--reference`、`--source`、`--working-copy`、`--reports-dir`、`--run-id`。

`execute-sandbox` 强制要求 working copy。Stage 2 中 `--execute` 和 backend doctor `--connect` 都会安全拒绝。
