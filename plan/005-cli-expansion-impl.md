# 005 实施记录：Agent 工作流 CLI 命令扩展

日期: 2026-09-08

## 1. 实施范围

基于 plan/004 的分析，添加 11 个新 CLI 子命令，打通仿真和设计读写两个关键断层。

## 2. 新增命令清单

### 2.1 仿真组 `vbridge sim` (新增文件: sim_cmd.py)

| 命令 | 功能 | 上游 API |
|---|---|---|
| `sim run NETLIST [-o DIR] [--mode aps\|ax\|...]` | 运行 Spectre 仿真 | `SpectreSimulator.from_env().run_simulation()` |
| `sim result DIR [--signal NAME] [--json]` | 解析 PSF 结果 | `psf.read_psf_ascii()` |
| `sim license` | 检查 Spectre license | `SpectreSimulator.check_license()` |

### 2.2 库管理组 `vbridge lib` (新增文件: lib_cmd.py)

| 命令 | 功能 | 上游 API |
|---|---|---|
| `lib list [--json]` | 列出所有库 | `client.library.list()` |
| `lib create NAME --path PATH [--tech-lib]` | 创建库 | `client.library.create()` |

### 2.3 符号组 `vbridge symbol` (新增文件: symbol_cmd.py)

| 命令 | 功能 | 上游 API |
|---|---|---|
| `symbol generate LIB CELL [--overwrite]` | 从原理图生成 symbol | `client.symbol.generate_from_schematic()` |

### 2.4 扩展原理图组 `vbridge sch`

| 命令 | 功能 | 上游 API |
|---|---|---|
| `sch read LIB CELL [--json]` | 读取原理图结构 | `client.schematic.read()` |
| `sch param LIB CELL INST PARAM VALUE` | 设置实例参数 | `cdfSetInstParam` SKILL |

### 2.5 启动优化 `vbridge auto-start`

| 选项 | 功能 |
|---|---|
| `--wait` | 阻塞等待 daemon 完全就绪 |
| `--json` | 输出机器可读的 JSON 状态 |
| 内部缓存 | state 读取从 6-8 次减少到 2 次 |

## 3. 文件变更汇总

| 文件 | 操作 | 行数 |
|---|---|---|
| `vbridge/sim_cmd.py` | 新增 | 120 |
| `vbridge/lib_cmd.py` | 新增 | 40 |
| `vbridge/symbol_cmd.py` | 新增 | 24 |
| `vbridge/sch_cmd.py` | 扩展 (+read, +param) | +60 |
| `vbridge/auto_start.py` | 优化 (缓存+wait+json) | 重写 startup_sequence |
| `vbridge/cli.py` | 扩展 (注册+分发) | +90 |
| `docs/quickstart.md` | 重写 | 完整覆盖新命令 |

## 4. 覆盖率提升

| 域 | 之前 | 之后 |
|---|---|---|
| 通用 SKILL 执行 | 89% | 89% |
| 原理图 | 50% (4/8) | 75% (6/8) |
| 版图 | 0% | 0% (保持，通过 exec 可用) |
| 符号 | 0% | 20% (1/5) |
| Maestro | 3% | 3% (保持，通过 exec 可用) |
| Spectre 仿真 | **0%** | **30%** (3/10) |
| 库管理 | 0% | 14% (2/14) |

## 5. Agent 完整工作流现在可行

```
vbridge auto-start --wait --json     # 启动
vbridge lib create myLib --path ...  # 创建库
vbridge sch create myLib diffPair    # 创建原理图
vbridge sch batch myLib diffPair <<< '[...]'  # 放置器件
vbridge sch param myLib diffPair M0 w 2u      # 设置参数
vbridge sch save                     # 保存
vbridge symbol generate myLib diffPair        # 生成 symbol
vbridge sch read myLib diffPair --json        # 验证
vbridge sim run tb.scs -o /tmp/out --mode aps # 仿真
vbridge sim result /tmp/out/ --json           # 读取结果
```
