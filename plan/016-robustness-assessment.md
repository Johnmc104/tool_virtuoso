# 016 vbridge 稳健性评估

> 从资源释放、文件安全、性能、可用性四个维度评估，输出改进方案。

---

## 一、资源释放

### 1.1 License 占用

| 问题 | 当前状态 | 风险 |
|------|---------|------|
| Virtuoso daemon 不自动退出 | 启动后持续占用 Virtuoso_Spectre license | **高**——license 数量有限 |
| OCEAN 退出后残留进程 | `cdsServIpc`/`virtuoso` 不退出 | **高**——额外占 license |
| Spectre 仿真进程 | `sim run` 结束后进程退出 | 低——正常 |

**改进**：
- P1: Python daemon 加空闲超时退出（`--idle-timeout 1800` 参数）
- P1: `sim run` 结束后自动调 `cleanup` 检查残留
- P2: SKILL daemon `RBStart()` 加定期心跳检查，无连接时关闭

### 1.2 内存

| 问题 | 当前状态 | 风险 |
|------|---------|------|
| Virtuoso 进程 ~250 MB | 启动后常驻 | 中 |
| `sim result --csv` 大文件 | 75652 点全加载到内存 | 低——<20 MB |
| `sim plot` HTML 生成 | 降采样到 2000 点 | 低 |

**无需改进**——当前内存使用合理。

### 1.3 磁盘

| 问题 | 当前状态 | 风险 |
|------|---------|------|
| OA lock 文件残留 | `*.cdslck*` 累积 | 中——阻止其他用户编辑 |
| Spectre 临时文件 | `/tmp` 下仿真产物 | 中——累积占磁盘 |
| `sim run` 输出目录 | 用户指定 `-o` | 低——用户管理 |

**改进**：
- P2: `cleanup` 增加 `--tmp` 选项清理 `/tmp` 下的 Spectre 临时文件
- P2: `sim run` 结束后自动清理 Spectre 的 `.ahdlSimDB`/`.pcf` 临时目录

---

## 二、文件安全

### 2.1 原理图保护

| 问题 | 当前状态 | 风险 |
|------|---------|------|
| 测试操作直接修改生产 cell | 无保护 | **高**——已发生 M8 损坏事件 |
| `sch create` 覆盖已有 cell | 无确认 | **高**——数据丢失 |
| `delete-inst` 无确认 | 立即执行 | 中 |
| daemon 缓存与磁盘不一致 | 无检测机制 | **高**——恢复无效 |

**改进**：
- P1: `sch batch` 增加 `--dry-run` 模式（显示将要做的修改，不执行）
- P1: `sch create` 增加 `--force` 要求（默认不覆盖已有 cell）
- P1: `sch batch` 前后自动生成网表 diff（检测意外改动）
- P2: 增加 `sch backup LIB CELL` 命令（在 daemon 内备份，不依赖文件系统 cp）
- P2: 增加 `sch diff LIB CELL --baseline FILE` 命令（对比当前原理图与基准网表）

### 2.2 网表完整性

| 问题 | 当前状态 | 风险 |
|------|---------|------|
| `--standalone` 替换 ade_e.scs | 可能丢失 ADE 配置 | 低——实测无影响 |
| 网表 `ic` 需手动添加 | 振荡器不起振 | 中——用户需了解 |

**改进**：
- P2: `sch netlist --standalone` 增加 `--ic "ON=3.3,OP=0"` 参数
- P3: 自动检测环路结构并建议 ic 节点

---

## 三、性能

### 3.1 SKILL 执行延迟

| 操作 | 延迟 | 评估 |
|------|------|------|
| `exec` 简单表达式 | ~15 ms | 优秀 |
| `sch read --json` | ~200 ms | 良好 |
| `sch batch` (9 ops) | ~500 ms | 良好 |
| `set-param` (CDF callback) | ~300 ms | 良好 |
| `sch netlist` | ~1 s | 良好 |
| `lib cells` (1141 cells) | ~500 ms | 良好 |

**无需改进**——所有操作在 1 秒内完成。

### 3.2 仿真性能

| 操作 | 时间 | 评估 |
|------|------|------|
| `sim run` (tran 2us) | ~15 s | 取决于 Spectre |
| `sim result` 概览 | ~1 s | 良好 |
| `sim result --csv` (75652 pts) | ~2 s | 良好 |
| `sim measure freq` | ~2 s | 良好 |
| `sim plot` HTML | <1 s | 优秀 |

**无需改进**。

### 3.3 PyInstaller 启动

| 操作 | 冷启动 | 热启动 |
|------|--------|--------|
| `vbridge exec` | ~1.5 s | ~0.5 s |
| `vbridge status` | ~1 s | ~0.3 s |

**P3**: 考虑 `--nopreamble` 跳过 matplotlib 等大模块的导入。

---

## 四、可用性

### 4.1 错误处理

| 场景 | 当前行为 | 改进 |
|------|---------|------|
| daemon 未连接 | `exec` 超时 | P1: 快速检测并提示 `vbridge auto-start` |
| spectre 不在 PATH | `sim run` 报 "not found" | 已处理 ✓ |
| 网表语法错误 | spectre 报错但 `sim run` 返回 partial | P2: 解析 spectre 错误并显示关键行 |
| `sch batch` op 名称拼写错误 | "unknown op" 报错 | 已处理 ✓ |
| `sim measure` 信号不存在 | "not found" 报错 | 已处理 ✓ |
| `sim measure` 数据不足 | "not enough crossings" | 已处理 ✓ |

### 4.2 用户引导

| 场景 | 当前行为 | 改进 |
|------|---------|------|
| 首次使用 | 需手动 `init` + `start` | P2: `vbridge doctor` 诊断环境 |
| 忘记命令参数 | `--help` 可用 | 已处理 ✓ |
| 不知道有哪些信号 | 需先 `sim result` 看 | 已处理 ✓ |
| 不知道 PDK 器件 | `lib cells` + `cell-info` | 已处理 ✓ |

---

## 五、优先级排序

### P1（影响安全和资源）

| 改进 | 工作量 | 实现方式 |
|------|--------|---------|
| `sch batch --dry-run` | 小 | vbridge sch_cmd.py |
| `sch create --force` | 小 | vbridge sch_cmd.py |
| Python daemon 空闲超时 | 中 | 上游 ramic_bridge_daemon_3.py |
| `sch batch` 前后网表 diff | 中 | vbridge sch_cmd.py |

### P2（提升体验）

| 改进 | 工作量 | 实现方式 |
|------|--------|---------|
| `sch backup LIB CELL` | 小 | vbridge SKILL |
| `sch diff LIB CELL --baseline` | 中 | vbridge |
| `cleanup --tmp` 清理临时文件 | 小 | vbridge cleanup_cmd.py |
| `sch netlist --ic "ON=3.3,OP=0"` | 小 | vbridge sch_cmd.py |
| `vbridge doctor` 环境诊断 | 中 | vbridge |

### P3（锦上添花）

| 改进 | 工作量 |
|------|--------|
| PyInstaller 启动优化 | 大 |
| 自动检测环路建议 ic | 大 |
