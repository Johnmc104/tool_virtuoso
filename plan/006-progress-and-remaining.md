# 006 进度跟踪与剩余问题

日期: 2026-09-08

## 1. 已完成工作总结

### 阶段 1: 项目分析 (001)
- [x] 项目架构、上下游关系、适配层分析

### 阶段 2: 上游更新 (002)
- [x] submodule 从 v0.7.0 更新到 v0.8.0 (febee2c → ae8e267, 37 commits)
- [x] 适配层同步：导入新符号、移除冲突 load 子命令、同步 profile 解析
- [x] 版本号同步到 0.8.0

### 阶段 3: 可用性修复 (003 → 30eca24)

| # | 问题 | 状态 |
|---|---|---|
| 2.1 | [HIGH] auto_start 状态路径过期 | **已修复** — 改用 `SSHClient.read_state()` |
| 2.2 | [HIGH] sch_cmd 调用不存在的方法 | **已修复** — 重写为使用 `schematic/ops` 函数 |
| 2.3 | [MED] setup.il 缺少 IDENTITY_PATH | **已修复** — 使用上游 `_generate_virtuoso_setup_il()` |
| 2.4 | [MED] env_helpers 与上游重叠 | **已修复** — 替换为 `load_vb_env()` |
| 2.5 | [MED] exec 表达式包装弱 | **已修复** — 采用 `progn()` 包装 |
| 2.6 | [MED] _run_bridge_start 子进程 | **已修复** — 改为直接调用 `_patched_cli_start()` |
| 2.7 | [LOW] load_cmd.py 死代码 | **已修复** — 已删除 |
| 2.8 | [LOW] _resource_patch.py 死代码 | **已修复** — 已删除 |
| 2.9 | [LOW] list_instances 内联 SKILL | **已修复** — 改用 `read_schematic()` |
| 2.10 | [LOW] quickstart.md 过期 | **已修复** — 完整重写 |

### 阶段 4: Agent 工作流分析 (004)
- [x] 能力矩阵：上游 API vs CLI 暴露
- [x] 启动流程时序分析
- [x] 仿真/设计断层识别

### 阶段 5: CLI 扩展实施 (005 → 44bc565)
- [x] `sim run/result/license` — Spectre 仿真 CLI
- [x] `lib list/create` — 库管理 CLI
- [x] `symbol generate` — 符号生成 CLI
- [x] `sch read/param` — 原理图读取和参数设置
- [x] `auto-start --wait --json` — Agent 友好启动
- [x] 启动流程状态读取缓存优化

### 阶段 6: 收尾修复 (本次)
- [x] 清理 cli.py 未使用的 `os` 和 `upstream_main` 导入
- [x] 为所有 `sch` 子命令添加 `--env` 参数（一致性）
- [x] 清理 sim_cmd.py 未使用的 `result_file` 导入

## 2. 当前代码状态

```
vbridge/
├── __init__.py          3 行   版本声明
├── cli.py             452 行   CLI 入口 + 27 个命令分发
├── auto_start.py      295 行   一键启动编排
├── exec_cmd.py         40 行   SKILL 执行 (wait_bridge_ready)
├── sch_cmd.py         197 行   原理图操作 (batch/create/save/list/read/param)
├── sim_cmd.py         137 行   Spectre 仿真 (run/result/license)
├── lib_cmd.py          39 行   库管理 (list/create)
├── symbol_cmd.py       22 行   符号生成 (generate)
├── env_helpers.py      33 行   VirtuosoClient 工厂
├── _frozen_patches.py  37 行   PyInstaller 冻结修补
└── _display.py         55 行   X11 DISPLAY 检测
合计                  1310 行
```

## 3. 剩余已知问题

### 3.1 [LOW] packaging/common/ 未提交改动

`build.sh`、`generate_dockerfile.py`、`packaging.mk` 有大量离线构建功能（`--save-env` 模式、
公共源码目录、Docker 镜像缓存）未提交。这是跨项目共享基础设施的独立功能，不影响 vbridge 本身。

**建议**: 在完成 vbridge 功能开发后单独提交。

### 3.2 [LOW] lib/ 目录源码副本过期

`lib/` 目录中的 Python 源码是 v0.7.0 版本（`make pre-package` 复制），
submodule 已更新到 v0.8.0。下次构建时 `make pre-package` 会自动同步。

**建议**: 仅在构建时同步，无需手动处理。

### 3.3 [LOW] upstream 命令透传的脆弱性

`cli.py` 从上游 `cli` 模块硬导入了 20+ 个符号（函数 + 内部变量），
这些不在上游的公开 API 承诺中。上游重构内部变量名时可能断裂。

涉及的内部符号：
- `_CLI_PROFILE`, `_SCREENSHOT_TARGET`, `_SCREENSHOT_OUTPUT`
- `_SNAPSHOT_OPTS`, `_EXPORT_VISIO_OPTS`
- `_make_stdio_safe`

**建议**: 可接受的风险。上游 CLI 是单文件、内部一致性强，这些变量近期稳定。
在每次 submodule 更新时做导入验证即可（已有测试）。

### 3.4 [INFO] 上游命令中未暴露给 vbridge 的少量命令

上游 v0.8.0 的部分参数式命令已在 `upstream_dispatch` 中正确绑定。
当前 27 个顶层命令 + 17 个子命令覆盖了全部上游 CLI 功能和 vbridge 扩展。

无遗漏命令。

## 4. 是否需要审查上游命令？

**不需要**。原因：

1. 上游的 20 个 CLI 命令全部在 `upstream_dispatch` 中正确绑定
2. 参数传递使用 `getattr(args, ...)` 安全兜底
3. 上次更新时已做过完整导入验证（所有符号存在、签名兼容）
4. 新增的 vbridge 命令组 (sim/lib/symbol/sch read|param) 不与上游冲突

唯一需要注意的时机是 **下次 submodule 更新时**，需要：
- 运行导入验证测试
- 检查上游是否新增了 CLI 命令（需要加入 dispatch）
- 检查上游是否修改了已绑定命令的签名

## 5. 阶段 7 更新 (2026-09-08)

### 已完成
- [x] 提交 packaging/common/ 离线构建功能 (c48d60c)
- [x] 添加 tests/test_imports.py 上游兼容性验证 (ea86817, 10 tests all pass)
- [x] lib/ 确认为构建产物（.gitignore），make pre-package 自动同步
- [x] cli.py 清理未使用导入、sch 子命令 --env 一致性修复

### 剩余可选

| 优先级 | 任务 | 说明 |
|---|---|---|
| 可选 | 添加 Maestro CLI | `maestro run/read` — 上游 API 已就绪 |
| 可选 | 添加 Layout CLI | `layout export-gds` — 上游 API 已就绪 |
