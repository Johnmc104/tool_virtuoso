# 004 Agent 工作流分析：启动、设计软件调用、仿真

日期: 2026-09-08

## 1. 分析视角

从 AI Agent（Claude Code / Cursor）驱动 EDA 设计的完整工作流出发，
评估 vbridge 在以下四个环节的能力覆盖和缺口：

```
启动 → 设计读写 → 仿真执行 → 结果分析
```

## 2. 能力矩阵：上游 API vs vbridge CLI 暴露

### 2.1 上游 Python API 能力全景

| 域 | 类 | 关键方法 | 需要 Virtuoso | vbridge CLI 暴露 |
|---|---|---|---|---|
| **原理图** | `SchematicOps` | `create`, `edit`, `read`, `plan`, `create_from_plan`, `modify`, `export_netlist`, `import_netlist` | 是 | `sch batch/create/save/list` |
| **版图** | `LayoutOps` | `create`, `edit`, `modify`, `export_gds` | 是 | 无 |
| **符号** | `SymbolOps` | `create`, `edit`, `generate_from_schematic`, `read_ports`, `modify` | 是 | 无 |
| **Maestro** | `MaestroOps` | `open_session`, `set_design`, `set_analysis`, `run_simulation`, `run_and_wait`, `read_results`, `snapshot`, `set_var`, `get_var`, +20 more | 是 | `snapshot` (只读) |
| **库管理** | `LibraryOps` | `list`, `create`, `delete`, `rename`, `list_categories`, etc. | 是 | 无 |
| **Spectre** | `SpectreSimulator` | `from_env`, `run_simulation`, `run_parallel`, `submit`, `wait_all`, `check_license` | **否** (独立) | 无 |
| **Spectre 池** | `SpectrePool` | `submit`, `wait_all`, `shutdown` | **否** | 无 |
| **PSF 解析** | `spectre.psf` | `read_psf_ascii`, `result_file`, `scalar`, `vector`, `frequency_hz` | **否** | 无 |
| **原理图规划** | `SchematicPlanner` | 约束求解器，自动布局元件位置 | 否 (计算) | 无 |
| **通用** | `VirtuosoClient` | `execute_skill`, `load_il`, `screenshot`, `dismiss_dialog`, `find_skill`, `get_skill_more_info`, `search_docs`, `upload_file`, `download_file` | 是 | `exec`, `eval`, `load`, `screenshot`, `dismiss-dialog`, `skill-find`, `skill-info`, `doc-search` |

### 2.2 覆盖率评估

| 维度 | 可用 API | CLI 暴露 | 覆盖率 |
|---|---|---|---|
| 通用 SKILL 执行 | 9 个方法 | 8 个命令 | **89%** |
| 原理图编辑 | 8 个方法 | 4 个命令 | **50%** |
| 版图编辑 | 4 个方法 | 0 个命令 | **0%** |
| 符号编辑 | 5 个方法 | 0 个命令 | **0%** |
| Maestro 仿真 | 37 个方法 | 1 个命令 (snapshot) | **3%** |
| Spectre 仿真 | 10 个方法 | 0 个命令 | **0%** |
| 库管理 | 14 个方法 | 0 个命令 | **0%** |

**结论**: vbridge CLI 仅对「通用 SKILL 执行」有较好覆盖，
对具体设计域的结构化操作几乎不暴露。Agent 被迫降级到 `exec` 手写 SKILL。

## 3. 启动流程分析

### 3.1 冷启动时序（无 bridge，无 Virtuoso）

```
Agent                     vbridge                    System
  |                         |                          |
  |-- auto-start ---------->|                          |
  |                         |-- _read_state() -------->| (文件 I/O #1)
  |                         |-- _get_port() ---------->| (文件 I/O #2: 再次 read_state)
  |                         |-- is_daemon_responding ->| (TCP connect, 失败)
  |                         |-- _get_setup_path() ---->| (文件 I/O #3: 再次 read_state)
  |                         |-- _run_bridge_start() -->|
  |                         |   |-- load_vb_env() ---->| (读 .env)
  |                         |   |-- _read_state() ---->| (文件 I/O #4)
  |                         |   |-- cli_start() ------>|
  |                         |   |   |-- SSH warm() --->| (SSH 连接 ~2-5s)
  |                         |   |   |-- deploy files ->| (SCP 上传 ~1-2s)
  |                         |   |   |-- save_state --->| (写状态文件)
  |                         |   |   |<- return 0 ------|
  |                         |-- _get_setup_path() ---->| (文件 I/O #5: 再次 read_state)
  |                         |-- _get_port() ---------->| (文件 I/O #6: 再次 read_state)
  |                         |-- is_daemon_responding ->| (TCP, 可能仍失败)
  |                         |-- _launch_virtuoso() --->|
  |                         |   |                      |-- virtuoso -replay (启动 ~30-120s)
  |                         |-- sleep(2) ------------->|
  |                         |-- _wait_for_daemon() --->| (轮询 TCP, 最多 15s)
  |                         |<- return 0 --------------|
  |                         |                          |
  |-- exec "1+1" --------->|                          |
  |                         |-- wait_bridge_ready() -->|
  |                         |   |-- is_daemon_responding (文件 I/O #7: _get_port → read_state)
  |                         |   |-- _wait_for_daemon() | (轮询至成功)
  |                         |-- get_client() --------->|
  |                         |   |-- load_vb_env() ---->| (再次读 .env)
  |                         |   |-- SSHClient.read_state() (文件 I/O #8)
  |                         |-- execute_skill() ------>| (TCP → SKILL → 返回)
  |<- "2" ------------------|                          |
```

### 3.2 启动瓶颈

| # | 瓶颈 | 耗时 | 可优化 |
|---|---|---|---|
| 1 | **重复状态读取**: `_read_state()` 在单次 auto-start 中被调用 6-8 次 | ~几 ms，但设计不干净 | 是：缓存到局部变量 |
| 2 | **SSH 握手 + 文件部署**: `ssh.warm()` + SCP 上传 | 2-7 秒 | 否：网络固有延迟 |
| 3 | **Virtuoso 冷启动**: `virtuoso -replay` 到 GUI 就绪 | 30-120 秒 | 否：EDA 软件固有行为 |
| 4 | **daemon 就绪等待**: CIW 加载 setup.il 后 daemon 才应答 | 取决于 Virtuoso 启动 | 部分：可提示进度 |
| 5 | **exec 重复初始化**: 每次 `exec` 都执行 `load_vb_env` + `read_state` | ~几 ms | 是：对连续调用可复用连接 |

### 3.3 热启动（bridge 已运行，Virtuoso 已就绪）

```
Agent                     vbridge
  |-- exec "expr" -------->|
  |                         |-- is_daemon_responding()  (TCP ~1ms, 成功)
  |                         |-- get_client()            (read_state + TCP 连接)
  |                         |-- execute_skill()         (TCP → SKILL ~10-100ms)
  |<- result ---------------|
```

热路径约 50-200ms，性能良好。

## 4. Agent 典型工作流缺口分析

### 4.1 场景：Agent 设计一个差分对放大器

```
Step 1: 创建库和 cellview
  需要: vbridge exec 'dbCreateLib("myLib" "/path")'  ← 降级到手写 SKILL
  期望: vbridge lib create myLib --path /path

Step 2: 创建原理图，放置 NMOS/PMOS
  当前: vbridge sch batch myLib diffPair <<< '[{"op":"add-inst",...}]'  ← 可用
  缺少: 设置实例参数（W/L/nf）← 无 CLI 操作类型

Step 3: 连线、加标签
  当前: vbridge sch batch ... <<< '[{"op":"wire",...}]'  ← 可用

Step 4: 保存并创建 symbol
  当前: vbridge sch save  ← 可用
  缺少: vbridge symbol generate myLib diffPair  ← 无 CLI 命令

Step 5: 创建 testbench（实例化 DUT + stimulus）
  当前: vbridge sch batch ...  ← 可用但繁琐

Step 6: 设置 Maestro 仿真
  完全缺失: 无 CLI 命令配置 Maestro
  降级: vbridge exec 'maeOpenSession(...)' + 一系列手写 SKILL

Step 7: 运行仿真
  完全缺失: 无 CLI 命令
  降级: vbridge exec 'maeRunSimulation()'

Step 8: 读取结果
  部分: vbridge snapshot -o output  ← 只能导出原始文件
  缺少: 结构化结果查询

Step 9: 调整参数并重新仿真
  降级: 回到 Step 6-8 的 SKILL 循环
```

### 4.2 场景：Agent 运行 Spectre 参数扫描（无 GUI）

```
Step 1: 准备网表 (.scs 文件)
  Agent 可直接生成文件  ← 无需 vbridge

Step 2: 运行仿真
  完全缺失: 无 CLI 命令
  上游 Python: sim = SpectreSimulator.from_env(); result = sim.run_simulation("tb.scs")
  Agent 降级: 写一个 .py 脚本 → python3 run_sim.py  ← 需要 Python 环境

Step 3: 并行扫描
  完全缺失: SpectrePool 无 CLI
  Agent 降级: 写 Python 脚本使用 SpectrePool API

Step 4: 解析结果
  完全缺失: PSF 解析器无 CLI
  Agent 降级: 写 Python 脚本使用 spectre.psf API
```

**核心问题**: Spectre 仿真是纯 Python API，没有任何 CLI 入口。
Agent 使用 vbridge 二进制时完全无法调用仿真功能。

## 5. 优化建议

### 5.1 启动优化（短期）

| # | 改进 | 工作量 | 收益 |
|---|---|---|---|
| S1 | `startup_sequence` 中缓存 state，避免重复 `_read_state()` | 小 | 代码清洁度 |
| S2 | 添加 `--wait` 标志到 `auto-start`，可选阻塞等待 daemon 就绪 | 小 | Agent 可确定性等待 |
| S3 | `auto-start` 成功时输出 JSON 状态供 Agent 解析 | 小 | Agent 可直接获取端口/路径 |

### 5.2 设计软件调用（中期）

| # | 新增 CLI 命令 | 覆盖场景 | 工作量 |
|---|---|---|---|
| D1 | `vbridge sch read LIB CELL [--json]` | 读取原理图结构 | 小 |
| D2 | `vbridge sch param INST PARAM VALUE` | 设置实例参数 | 小 |
| D3 | `vbridge symbol generate LIB CELL` | 从原理图生成 symbol | 小 |
| D4 | `vbridge lib list [--json]` | 列出库 | 小 |
| D5 | `vbridge lib create LIB` | 创建库 | 小 |

### 5.3 仿真（中期 — 高优先）

| # | 新增 CLI 命令 | 覆盖场景 | 工作量 |
|---|---|---|---|
| M1 | `vbridge sim run NETLIST [-o DIR] [--mode aps\|ax]` | Spectre 独立仿真 | 中 |
| M2 | `vbridge sim status` | 查看运行中仿真 | 小 |
| M3 | `vbridge sim result DIR [--signal NAME]` | PSF 结果查询 | 中 |
| M4 | `vbridge maestro run LIB CELL [--wait]` | Maestro GUI 仿真 | 中 |
| M5 | `vbridge maestro read LIB CELL [--json]` | 读取 Maestro 结果 | 小 |

### 5.4 优先级排序

```
P0 (解决核心断层):
  M1 sim run    — Agent 最常需要的操作，上游 API 已完善，仅缺 CLI 壳
  D1 sch read   — Agent 理解当前设计的基础

P1 (完善设计循环):
  D3 symbol generate  — 原理图完成后的必要步骤
  D2 sch param        — 设置 W/L 是设计的核心操作
  M3 sim result       — 查看仿真结果完成反馈环

P2 (便利性):
  M4 maestro run      — GUI 仿真入口
  D4/D5 lib list/create — 库管理
  S1-S3 启动优化      — 代码质量
```

## 6. 总结

vbridge 在「启动」和「通用 SKILL 执行」两个环节做得很好（auto-start 一键启动、exec/eval 双路径）。
但在 Agent 实际设计流程中，存在两个关键断层：

1. **设计读写断层**: 版图/符号/库管理零 CLI 覆盖，Agent 被迫降级到手写 SKILL
2. **仿真断层**: Spectre 仿真是纯 Python API，vbridge 二进制完全无法调用

这使得 Agent 的实际工作流退化为：`auto-start → exec SKILL → exec SKILL → ...`，
结构化 API 的优势被 CLI 层的缺失抵消。

最高优先级建议：添加 `sim run` 和 `sch read` 两个命令，
最小代价打通仿真和设计读取两个最关键的 Agent 工作流。
