# 001 项目分析：tool_virtuoso 与上游 virtuoso-bridge-lite 适配关系

日期: 2026-09-08

## 1. 项目概述

**tool_virtuoso** 是基于开源项目 [virtuoso-bridge-lite](https://github.com/Arcadia-1/virtuoso-bridge-lite)（MIT 协议）的企业内部二进制分发工具集，目标是将 Python 项目打包为独立可执行文件，在无 Python 环境的 EDA 服务器上直接使用。

### 上游项目

- **名称**: virtuoso-bridge-lite v0.7.0
- **作者**: Zhishuai Zhang 等（清华大学）
- **定位**: Cadence Virtuoso SKILL Bridge 的 Python 基础设施，支持远程 SSH 隧道模式和本地模式
- **核心能力**: VirtuosoClient (TCP SKILL 客户端)、SpectreSimulator (仿真)、SSHClient (隧道管理)
- **AI 原生设计**: CLI-first，内置 Agent skill 文件，面向 Claude Code/Cursor 等编码代理

### 本项目

- **名称**: tool_virtuoso (Virtuoso Bridge Tools)
- **定位**: 上游的二进制打包分发版本 + 扩展命令层 (vbridge)
- **输出**: 两个 PyInstaller 单文件二进制
  - `virtuoso-bridge` — 上游 CLI 的直接打包
  - `vbridge` — 扩展 CLI，包含 auto-start、exec、load、sch 等附加命令

## 2. 架构分析

```
┌────────────────────────────────────────────────────────────┐
│  vbridge CLI (entry_vbridge.py → vbridge/cli.py)           │
│   ├── auto-start  — 一键启动编排                           │
│   ├── exec        — SKILL 表达式执行                       │
│   ├── load        — IL 文件加载                            │
│   ├── sch         — 原理图批量操作                         │
│   ├── daemon      — RAMIC bridge daemon 内嵌运行            │
│   └── [上游命令]  — init/start/stop/status/... 透传        │
├────────────────────────────────────────────────────────────┤
│  virtuoso-bridge CLI (entry_virtuoso_bridge.py)             │
│   └── 上游 virtuoso_bridge.cli:main 直接调用               │
├────────────────────────────────────────────────────────────┤
│  virtuoso_bridge (上游 Python 库)                          │
│   ├── transport/  — SSH 隧道、远程路径                      │
│   ├── virtuoso/   — SKILL 客户端、布局/原理图/仿真          │
│   └── spectre/    — Spectre 仿真器                         │
└────────────────────────────────────────────────────────────┘
```

### 上下游关系

| 层 | 来源 | 打包方式 |
|---|---|---|
| `virtuoso_bridge/` | 上游 submodule `virtuoso-bridge-lite/src/` | PyInstaller collect_all + lib/ 源码分发 |
| `vbridge/` | 本项目自有代码 | PyInstaller collect_submodules + lib/ 源码分发 |
| `patches/` | 本项目 IC23.1 兼容性补丁 | 构建前 apply，构建后 revert |

## 3. 本项目扩展内容 (vbridge/)

### 3.1 文件清单

| 文件 | 功能 | 行数 |
|---|---|---|
| `cli.py` | 扩展 CLI 入口，合并上游命令 + 本地命令 | ~243 |
| `auto_start.py` | 一键启动编排（bridge start → Virtuoso 启动 → daemon 等待）| ~289 |
| `exec_cmd.py` | SKILL 表达式执行，支持 stdin/JSON 输出 | ~43 |
| `load_cmd.py` | IL 文件加载 | ~36 |
| `sch_cmd.py` | 原理图批量操作（add-inst/wire/label/pin 等）| ~126 |
| `env_helpers.py` | .env 加载 + VirtuosoClient 工厂 | ~58 |
| `_frozen_patches.py` | PyInstaller 冻结二进制 setup.il 路径修补 | ~38 |
| `_resource_patch.py` | PyInstaller _MEIPASS 资源路径修补 | ~53 |
| `_display.py` | X11 DISPLAY 自动检测（VNC/X11 socket）| ~56 |

### 3.2 关键适配点

1. **PyInstaller 冻结兼容**
   - `_frozen_patches.py`: 改写 `virtuoso_setup.il` 中的 `RB_PYTHON_PATH` 和 `RB_DAEMON_PATH`，使其指向打包后的 `vbridge` 二进制而非 Python 解释器
   - `_resource_patch.py`: Monkey-patch `_find_ramic_bridge_il` 和 `_find_ramic_bridge_daemon`，回退到 `sys._MEIPASS` 路径
   - `cli.py:_run_daemon()`: daemon 子命令内嵌执行 `ramic_bridge_daemon_3.py`，无需外部 Python

2. **auto-start 编排**
   - 状态检测 → bridge start → Virtuoso 启动 → daemon 就绪轮询
   - VNC DISPLAY 自动探测
   - 防重复启动机制
   - 非阻塞设计（Virtuoso 冷启动慢，不永久等待）

3. **上游命令透传**
   - `cli.py:build_parser()` 继承上游 `build_parser()`，追加本地子命令
   - `main()` 通过 `upstream_dispatch` 字典路由上游命令，本地命令走 if-elif

4. **IC23.1 兼容性补丁**
   - `patches/0001-fix-buttonLayout-ic231.patch`: 将 `ramic_bridge.il` 中 `?buttonLayout 'Empty` 改为 `'OKCancelApply`
   - 构建时 apply，构建后 revert（不污染 submodule）

## 4. 打包基础设施 (packaging/)

### 4.1 构建流程

```
make build
  → packaging/common/build.sh (Docker 模式)
    → generate_dockerfile.py (从 packaging.yaml 生成 Dockerfile)
    → manylinux2014 基础镜像
    → 源码编译 Python 3.11.9 + OpenSSL
    → pip install 依赖
    → PyInstaller --onefile 打包
    → 输出: release/bin/{virtuoso-bridge, vbridge}
```

### 4.2 packaging.yaml 配置

- 两个二进制入口: `entry_virtuoso_bridge.py`, `entry_vbridge.py`
- 依赖来源: `virtuoso-bridge-lite/pyproject.toml`
- 源码: `virtuoso-bridge-lite/src/` → Docker 内 `src/`, `vbridge/` → Docker 内
- 输出: `release/bin/`

### 4.3 分发包结构

```
virtuoso-bridge-<ver>-linux-x86_64.tar.gz
├── bin/
│   ├── virtuoso-bridge    # 上游 CLI 二进制
│   └── vbridge            # 扩展 CLI 二进制
├── lib/
│   ├── virtuoso_bridge/   # 上游 Python 源码（多用户共享引用）
│   ├── vbridge/           # 本项目 Python 源码
│   └── pyproject.toml     # 上游元数据
├── docs/
│   └── quickstart.md
└── README.md
```

### 4.4 当前未提交改动 (packaging/common/)

`build.sh` 和 `generate_dockerfile.py` 中有大量未提交改动，主要涉及：

1. **`--save-env` 模式**: 新增编译环境导出功能，用于内网离线构建
   - Docker 基础镜像保存为 tar
   - pip wheels 下载缓存
   - 前端包缓存（pnpm/npm 自动检测）
   - Node 镜像保存

2. **公共源码目录**: `common_packaging/src/` 支持多项目共享大文件（Docker 镜像、RPM 等）

3. **离线构建支持**: `generate_dockerfile.py --offline` 生成使用本地 wheels 的 Dockerfile

4. **`packaging.mk`**: 新增 `save-build-env` Make target

## 5. 上游版本与同步状态

| 项 | 值 |
|---|---|
| submodule 指向 | `virtuoso-bridge-lite` (Arcadia-1/virtuoso-bridge-lite.git) |
| 上游版本 | 0.7.0 |
| 最新 upstream commit | `febee2c` (feat: add library and category management APIs) |
| lib/ 与 src/ 一致性 | 一致（lib/ 在 `make pre-package` 时从 src/ 复制） |

### 上游近期活跃功能

- Library/Category 管理 API
- Symbol 绘图辅助
- XStream GDS 导出
- 原理图 wire-bound label
- Python 3.9 兼容修复

## 6. 风险与关注点

1. **上游 API 变更**: `vbridge/cli.py` 硬导入了上游 `cli` 模块的多个符号 (`_CLI_PROFILE`, `_SCREENSHOT_TARGET` 等内部变量)，上游重构时可能断裂
2. **冻结路径脆弱**: `_frozen_patches.py` 和 `_resource_patch.py` 依赖上游文件的精确路径结构，上游目录重组时需同步更新
3. **IC23.1 补丁维护**: 上游 `ramic_bridge.il` 更新时需验证补丁是否仍然适用
4. **packaging/common/ 是共享基础设施**: 改动影响所有使用此框架的项目，需谨慎

## 7. 总结

本项目是上游 virtuoso-bridge-lite 的「企业分发包装层」，核心价值在于：
- **零依赖部署**: PyInstaller 单文件，无需 Python 环境
- **一键启动**: `vbridge auto-start` 自动化整个启动链
- **扩展命令**: exec/load/sch 提供更友好的高层接口
- **内网离线构建**: packaging 基础设施支持无外网环境编译

适配层代码量约 900 行，保持了与上游的清晰边界。
