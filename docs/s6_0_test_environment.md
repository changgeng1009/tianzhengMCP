# S6.0 统一开发测试环境

## 目的与边界

`D:\PythonEnvs\tianzheng-dev` 是项目默认 pytest、Mock/Fake、安全回归和静态检查的唯一开发环境。它与仅用于显式 S5 synthetic AutoCAD 集成的 `D:\PythonEnvs\tianzheng-s5` 分离；默认测试绝不启动 AutoCAD、不连接 COM 或天正，也不读取 DWG/DXF。

## 创建与安装

在英文工作目录 `T:\` 中执行：

```powershell
$dev = 'D:\PythonEnvs\tianzheng-dev\Scripts\python.exe'
& 'C:\Users\REDACTED_USER\AppData\Local\Programs\Python\Python313\python.exe' -m venv 'D:\PythonEnvs\tianzheng-dev'
& $dev -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` 是默认开发/测试安装入口，并复用根 `requirements.txt`。不得复制全局 site-packages、S5 环境或把本机路径写入依赖文件。

## 默认命令

```powershell
$dev = 'D:\PythonEnvs\tianzheng-dev\Scripts\python.exe'
& $dev -m pytest --collect-only -q
& $dev -m pytest -q
```

`pytest.ini` 自动加载文件访问守卫，并默认排除 `real_dwg`、`external_integration`、`autocad_required`、`tianzheng_required`、`com_required` 和 `production_only`。默认测试即使收集真实集成测试模块，也不会执行真实 CAD 路径。

## S5 Mock 定向验证

```powershell
& $dev -m pytest tests/safety/test_real_cad_access_guard.py tests/backends/test_autocad_launcher.py tests/backends/test_autocad_com_activation.py tests/backends/test_autocad_com_gateway.py tests/backends/test_real_autocad_com_backend.py tests/backends/test_s5_synthetic_runner.py -q
```

## 真实 AutoCAD 集成（不得用于默认回归）

真实集成必须单独获得授权，并仅限 S5 current-job synthetic sandbox：

```powershell
$env:CAD_S5_AUTOCAD_INTEGRATION = '1'
& $dev -m pytest -o addopts="-p tests.safety.pytest_plugin" -m "real_autocad and integration and requires_autocad" tests/autocad_integration
```

该命令不授予用户 DWG/DXF、天正、生产写入或 L4 权限；S6.0 未执行它。

## 已知限制

S6.0 清除了默认收集的依赖错误。当前默认回归仍有两个既有、artifact PDF 路径依赖的断言失败；它们不是依赖、CAD、COM 或本轮代码引入的问题，详见本阶段 evidence report。
