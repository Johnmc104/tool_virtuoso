# 002 上游更新：virtuoso-bridge-lite v0.7.0 → v0.8.0

日期: 2026-09-08

## 1. 更新范围

| 项 | 旧 | 新 |
|---|---|---|
| submodule commit | `febee2c` | `ae8e267` (origin/main) |
| 上游版本 | v0.7.0 | v0.8.0 |
| 新增提交数 | — | 37 |
| 文件变更 | — | 117 files, +12281/-1360 lines |

## 2. 上游重要新功能

### 2.1 Split Remote Host Roles (远程主机角色分离)
- 新增 `VB_DAEMON_HOST`, `VB_DEPLOY_HOST`, `VB_GUI_HOST`, `VB_SPECTRE_HOST`
- `VB_REMOTE_HOST` 保留为 legacy 兼容
- 新模块: `transport/remote_roles.py`

### 2.2 Paramiko SSH Backend
- 可选替代 OpenSSH 的 SSH 后端，支持 SOCKS5 代理
- 新模块: `transport/paramiko_backend.py` (~1400 行)
- 新依赖: `paramiko>=3.5`, `PySocks>=1.7.1` (可选，`[ssh]` extra)
- 二进制分发不包含 paramiko（我们使用 openssh 后端）

### 2.3 Deterministic Schematic Planner
- 新模块: `virtuoso/schematic/planner.py` (~990 行)
- 约束求解器，自动规划原理图元件布局
- ADR 文档: `docs/adr/0002-deterministic-schematic-planner.md`

### 2.4 其他重要变更
- `spectre/psf.py`: 严格 PSF 访问器
- `virtuoso/maestro/ops.py`: Maestro 操作 API
- `transport/transfer.py`: 文件传输计划
- `daemon_guard.py`: 跨用户 daemon 安全检查
- `cli.py` restart 现在通过 `RBStop()/RBStart()` 刷新 Virtuoso 端 daemon
- `ramic_bridge.il` 新增 `RBIdentityPath` 身份文件写入（split-host 诊断）
- 新增 `eval-type-backport` 依赖（Python <3.10 兼容）

### 2.5 CLI 新增命令
| 命令 | 功能 |
|---|---|
| `eval` | SKILL 表达式执行（上游原生，JSON 输出） |
| `load` | IL 文件加载（上游原生，JSON 输出） |
| `profile` | Profile 绑定管理 |
| `bootstrap` | 首次 CIW setup.il 加载引导 |
| `list-windows` | X11 窗口枚举（含 JSON 输出） |
| `dismiss-window` | 指定窗口 ID 操作 |
| `skill-find` | SKILL 函数搜索 |
| `skill-info` | SKILL 函数详细文档 |
| `doc-search` | Cadence 文档搜索 |

## 3. 适配层修改

### 3.1 vbridge/cli.py 变更

**移除**: 自定义 `load` 子命令（上游已内置更完善的版本）

**新增导入**:
- `_SCREENSHOT_OUTPUT`, `cli_load`, `cli_eval`
- `cli_dismiss_window`, `cli_list_windows`, `cli_bootstrap`
- `cli_profile`, `cli_find`, `cli_skill_info`, `cli_doc_search`

**更新分发表**: 从 11 个上游命令增加到 20 个

**Profile 解析**: 同步上游的 `resolve_profile()` + `bind_venv_profile()` 逻辑

**保留**: `exec` 命令作为 vbridge 兼容别名（与上游 `eval` 并存）

### 3.2 版本同步
- `VERSION`: 0.7.0 → 0.8.0
- `vbridge/__init__.py`: 0.7.0 → 0.8.0

### 3.3 packaging.yaml
- `hidden_imports` 新增 `eval_type_backport`

## 4. 兼容性验证

| 检查项 | 结果 |
|---|---|
| IC23.1 补丁适用性 | 通过（`?buttonLayout 'Empty` 行未变） |
| vbridge 全量导入 | 通过 (Python 3.11) |
| CLI parser 构建 | 通过（24 个子命令，无冲突） |
| `_resource_patch.py` 签名兼容 | 通过（`_find_ramic_bridge_il/daemon` 签名未变） |
| `_frozen_patches.py` 兼容 | 通过（setup.il 格式未变） |
| `env_helpers.py` 兼容 | 通过（`SSHClient.from_env`, `_is_localhost` 存在） |

## 5. 不包含在本次更新中

- `packaging/common/` 的离线构建改动（独立功能，待单独提交）
- `vbridge/load_cmd.py` 文件保留但不再使用（可在后续清理中移除）
- paramiko 相关的打包配置（可选依赖，二进制分发不需要）

## 6. 后续关注

1. `vbridge/load_cmd.py` 可以安全删除（上游 `load` 已完全替代）
2. 上游 `eval` 输出为完整 JSON（与我们 `exec` 的纯文本输出不同），用户可能需要适应
3. 上游 split-host 功能带来新的 `.env` 配置项，`docs/quickstart.md` 可能需要更新
4. `eval-type-backport` 仅在 Python <3.10 时需要，打包目标为 3.11 可能不需要，但加入 hidden_imports 无害
