# 018 后续开发意见

> 基于 IC251 实测两天的完整经验，面向下一阶段开发。

---

## 一、当前位置

vbridge 已完成从"能连上"到"能做事"的跨越。原理图编辑和仿真工程的覆盖度均达 95%。
核心链路 `read → edit → netlist → simulate → measure → plot` 全流程无 GUI 可用。

**不需要继续加功能了。** 下一阶段应聚焦三件事：稳定性、可维护性、实际项目推广。

---

## 二、优先级排序

### P0: 必须做（阻塞推广）

#### 2.1 daemon 生命周期管理

**问题**：Virtuoso 进程启动后不退出，持续占 license + 内存。多人共用 EDA 服务器时
会耗尽 license 配额。

**方案**：
```
选项 A（推荐）: Python daemon 加空闲超时
  - ramic_bridge_daemon_3.py 主循环加 idle_timeout 计数
  - 无连接 30 分钟后发 SIGINT 给 Virtuoso
  - 用户可配置: VB_IDLE_TIMEOUT=1800 (秒)
  工作量: ~30 行改动, 上游 patch

选项 B: 外部看门狗
  - cron 每 30 分钟检查 vbridge status + 连接时间戳
  - 超时则 vbridge cleanup
  工作量: ~20 行 shell 脚本
```

#### 2.2 原理图修改的事务完整性

**问题**：`sch batch` 执行多个 op 时，如果第 3 个 op 失败，前 2 个已生效且无法回滚。
本轮测试的 M8 损坏事件就是此类问题。

**方案**：
```
方案 A（推荐）: batch 前后网表 diff
  - 执行前生成基准网表（md5 或逐器件连接快照）
  - 执行后生成新网表并 diff
  - 打印改动摘要供用户确认
  - 不是事务回滚，但能立即发现意外改动
  工作量: ~50 行

方案 B: 在 SKILL 层做 undo
  - 利用 OA 的 undo 机制（dbUndoMark / dbUndo）
  - 复杂度高，OA undo 在 IC251 的可靠性未验证
  工作量: ~100 行, 风险高
```

---

### P1: 应该做（提升日常体验）

#### 2.3 `sch netlist --ic` 参数

**问题**：振荡器需要 `ic ON=3.3 OP=0` 才能起振，当前需手动编辑网表。

**方案**：
```bash
vbridge sch netlist my_osc osc -o ./nl --standalone --ic "ON=3.3,OP=0"
# 在网表中自动生成: ic ON=3.3 OP=0
```
工作量: ~10 行

#### 2.4 `sim sweep` 内建参数扫描

**问题**：多参数点仿真需写 shell 循环或手动改网表。

**方案**：
```bash
vbridge sim sweep input.scs -o ./raw --param vcon --start 1.5 --stop 2.7 --step 0.3
# 内部：生成 Spectre sweep 语法包裹 → sim run → 解析多点结果
```
工作量: ~80 行（需处理 sweep PSF 结果解析）

#### 2.5 `sch diff` 网表对比

**问题**：修改原理图后需要确认改了什么，当前只能手动 diff 网表文件。

**方案**：
```bash
vbridge sch diff my_osc osc --baseline ./baseline.scs
# 输出:
#   M8: gate VBN→GND (CHANGED)
#   M3: params w 400n→1.6u (CHANGED)
#   M_TEST: (ADDED)
```
工作量: ~60 行

---

### P2: 可以做（锦上添花）

#### 2.6 多 cell 操作

```bash
vbridge sch copy my_osc osc my_osc osc_v2        # 复制 cell
vbridge sch rename my_osc osc_old my_osc osc_v1   # 重命名
```

#### 2.7 `sim plot` 增强

```bash
vbridge sim plot DIR ON,OP -o wave.html --log-x     # X 轴对数（AC 响应）
vbridge sim plot DIR ON -o wave.html --overlay DIR2  # 叠加多次仿真结果
```

#### 2.8 Maestro corner 配置

```bash
vbridge maestro corner my_osc osc --add tt ss ff    # 配置 corner
vbridge maestro run my_osc osc --corner all          # 跑全 corner
```

#### 2.9 报告生成

```bash
vbridge report my_osc osc -o report.html \
  --corner tt,ss,ff \
  --measure "freq:ON, avg:V0:p, thd:ON" \
  --plot "ON,OP"
# 生成包含表格 + 波形图的 HTML 报告
```

---

### 不做

| 项 | 理由 |
|----|------|
| 波形交互查看器（zoom/pan） | HTML Canvas 已有基础，但完整交互器件需要前端框架，ROI 低 |
| Layout 操作 CLI | 上游有 Python API，但 layout 流程与 agent 工作方式不匹配 |
| Monte Carlo CLI | 需要 Maestro 配置 + 大量仿真管理，复杂度高 |
| 替换 argparse 为 click | 改善 --help 体验但需重写整个 CLI 层 |

---

## 三、架构建议

### 3.1 patch 管理

当前 `patches/0002-ic251-field-fixes.patch` 包含 5 个文件的修改。随着改动增多，
单个 patch 会变大且难以维护。

**建议**：按功能拆分 patch：
```
patches/
  0001-fix-buttonLayout-ic231.patch      # 已有
  0002-bridge-local-mode.patch           # load + screenshot 本地模式
  0003-params-wf-sync.patch              # w↔wf 自动同步
  0004-cdf-filters-tsmc.patch            # TSMC 65nm/40nm CDF 过滤
  0005-runner-license-check.patch        # license 误报精确匹配
```

### 3.2 测试

当前无自动化测试。建议添加：
```
tests/
  test_sch_batch.py    # batch op 功能测试（需 daemon 连接）
  test_sim_measure.py  # 测量功能测试（用固定 PSF 数据）
  test_cli_help.py     # CLI help 完整性检查（无需 daemon）
```

最简起步：`test_cli_help.py` 不需要 daemon 连接，只检查所有命令的 `--help` 能正常输出。

### 3.3 版本管理

当前 `VERSION` 文件是 `0.8.0`（上游版本），vbridge 构建后显示 `v0.1.0`（不一致）。

**建议**：vbridge 有独立版本号，格式 `vbridge-YYYYMMDD`（日期版本，简单直接）。

---

## 四、推广路径

| 阶段 | 内容 | 前提 |
|------|------|------|
| 1. 自用验证 | 在 test_osc 上完成全部验证项（corner/temp/PSS 已做） | 已完成 |
| 2. 文档定稿 | SKILL.md + 017 总结 + 使用示例 | 已完成 |
| 3. 团队试用 | 选 1-2 个项目组试用，收集反馈 | 需 daemon 生命周期管理 |
| 4. 正式部署 | 加入项目工具链，CI 集成 | 需自动化测试 |

**阶段 3 的最低要求**：
- daemon 空闲超时退出（防止 license 泄漏）
- `--dry-run`（已实现）
- `--force` 保护（已实现）
- SKILL.md 使用指南（已完成）

---

## 五、本轮经验教训

| 教训 | 改进 |
|------|------|
| 在生产 cell 上测试新功能 | 必须用独立测试 cell |
| OA daemon 缓存无法外部清除 | 修复必须在 daemon 内通过 SKILL |
| 错误归因（ade_e.scs 误判） | 先对比网表器件连接，再怀疑环境差异 |
| 频繁重新构建 PyInstaller | 开发期用 `PYTHONPATH=lib:. python3.11` 直接跑，最终再打包 |
| CDF callback 在 IC251 不工作 | Python 层硬编码同步（_sync_w_wf），不依赖 SKILL callback |
