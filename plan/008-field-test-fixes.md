# 008 IC251 实测问题修复计划

日期: 2026-09-08

## 修复清单

### P1: cdf_param_filters.yaml 未打包

**根因**: 上游 `pyproject.toml` 的 `[tool.setuptools.package-data]` 声明了
`maestro/*.yaml` 但遗漏了 `schematic/*.yaml`。PyInstaller `--collect-all` 依赖
setuptools 的 package-data 发现数据文件，遗漏的文件不会被收集。

**修复**: 在 `packaging.yaml` 中添加 `add_data` 显式包含：
```yaml
add_data:
  - "src/virtuoso_bridge/virtuoso/schematic/cdf_param_filters.yaml:virtuoso_bridge/virtuoso/schematic/"
```

### P2: sch param 使用不存在的 SKILL 函数

**根因**: `dbFindInstByName` 和 `cdfSetInstParam` 在 IC251 (OA 22.62) 中不存在。

**修复**: 重写 `run_param()` 使用兼容 API：
- 查找实例: `setof(i cv~>instances i~>name == "...")` 替代 `dbFindInstByName`
- 设置参数: `cdfFindParamByName(cdfGetInstCDF(inst) "p")~>value = "v"` 替代 `cdfSetInstParam`
- W 特殊处理: 设置 `w` 时自动联动 `wf`（`wf = w / nf`，或 `nf=1` 时 `wf = w`）

### P3: vbridge load 本地模式不可用

**根因**: 上游 `cli_load` 调用 `client.load_il()` 尝试通过 SSH 上传文件，
本地模式无 SSH runner 导致失败。

**修复**: 不修改上游代码。在 `cli.py` 中对 `load` 命令添加本地模式检测：
本地模式下改用 `exec 'load("...")'` 路径。

### P4: CDF w/wf 不同步

**修复**: 已合并到 P2 的 `run_param` 重写中。

## 文件变更

| 文件 | 变更 |
|---|---|
| `packaging.yaml` | 两个 binary 添加 `add_data` |
| `vbridge/sch_cmd.py` | 重写 `run_param()` |
| `vbridge/cli.py` | `load` 命令本地模式 fallback |
