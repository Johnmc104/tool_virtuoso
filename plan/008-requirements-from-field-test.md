# 008 vbridge 开发需求：基于 IC251 模拟设计实测

> 来源：在 `test_osc`（TSMC 65nm 差分环振）项目中完成"修原理图 → 改参数 → 跑仿真 → 提数据"全流程。
> 测试环境：vbridge v0.8.0, Virtuoso IC25.1-64b, Spectre 25.1.0.417, 本地模式。
> 日期：2026-09-08

---

## 一、当前能力现状

### 已通过验证、可正常使用

| 命令 | 用途 | 实测结论 |
|------|------|----------|
| `exec` | 执行 SKILL 表达式 | 稳定，支持多行、单引号包裹 |
| `exec 'load("...")'` | 加载 .il 脚本 | 可用，是 `load` 本地模式的替代方案 |
| `sch batch` + `label-mos` | 修改端子网名 | 成功修复 net14→VBN 连线缺陷 |
| `sch batch` + `set-param` | 批量改器件参数 | 成功修改 16 个 MOS 的 W/L/寄生参数 |
| `sch param` | 单实例改参数 | 正常工作，自动同步 `w`→`wf` |
| `sch read` / `sch read --json` | 读取原理图拓扑和参数 | 返回完整的实例、网络连接、CDF 参数 |
| `sch list` | 列出实例 | 可用，但 cell name 列显示 `?` |
| `lib list` | 列出库 | 正常 |
| `sim run` | 运行 Spectre 仿真 | 正常（需先 `module load spectre`） |
| `sim result` | 解析仿真结果 | DC 完整解析；`--csv` 导出全部瞬态数据 |
| `sim result --csv --signal X` | 导出指定信号 | 正常，只输出 time + 指定信号两列 |
| `status` | 检查连接状态 | 正常 |

### 已知缺陷

| 编号 | 命令 | 现象 | 状态 |
|------|------|------|------|
| BUG-1 | `load file.il` | 本地模式报 SSH runner 错误 | ✓ 已修复（bridge.py ssh_runner guard） |
| BUG-2 | `sch list` | cell name 列显示 `?` | ✓ 已修复 |
| BUG-3 | `sim result --signal X --json` | 瞬态只返回 DC 标量 | 中（`--csv` 可导出完整数据） |

---

## 二、新功能需求

### ~~REQ-1: `load` 本地模式支持~~ ✓ 已修复

修改 `bridge.py:_prepare_il_path` 加 `ssh_runner is not None` 检查。

---

### ~~REQ-2: 从原理图生成 Spectre 网表~~ ✓ 已存在

`vbridge sch netlist myLib myCell -o ./output` 命令已可用（之前未发现）。

**注意**: 生成的网表引用 `ade_e.scs`，独立仿真时需手动替换为 PDK model include。

**优先级**: ~~P1~~ 已解决（附加需求：支持 `--model` 参数自动注入 PDK include）

---

### ~~REQ-2 原文备份~~: 从原理图生成 Spectre 网表

**优先级**: ~~P1~~ 已解决

**场景**: 修改原理图后需验证，当前必须手写 OCEAN 脚本（7~10 行），
再 `ocean -nograph -restore xxx.ocn`。OCEAN 启动慢（~10 秒加载 cxt），
退出时经常 SIGSEGV (exit 139)，残留进程占 license。

**期望**:
```bash
vbridge netlist my_osc osc \
  --simulator spectre \
  --model "/opt/PDK/.../toplevel.scs" --section tt_lib \
  --output ./netlist/
```

或至少：
```bash
vbridge netlist my_osc osc --output ./netlist/
# 使用 ADE/Maestro 已配置的 simulator、model、corner
```

**输出**: 标准 Spectre `.scs` 网表文件，可直接 `spectre -64` 或 `vbridge sim run` 运行。

**补充**: 生成网表后可以绕过 OCEAN，直接用 `vbridge sim run` 跑仿真，
形成完整的 `sch batch → netlist → sim run → sim result` 无 GUI 链路。

---

### REQ-3: 瞬态数据的 JSON 返回

**优先级**: P2

**现象**: `sim result --signal ON --json` 只返回 DC 标量 `{"ON": 2.957}`，
瞬态数据被跳过。`--csv` 能完整导出，但 JSON 不行。

**期望**:
```bash
vbridge sim result ./raw/ --signal ON --json
# → {"dcOp.dc": {"ON": 2.957},
#    "tran1.tran.tran": {"time": [...], "ON": [...]}}
```

**注意**: 75652 点 × 9 信号的完整 JSON 会很大（~50 MB）。
建议支持裁剪参数：
```bash
vbridge sim result ./raw/ --signal ON --json --from 1u --to 1.5u
```

---

### REQ-4: 内建测量命令

**优先级**: P2

**场景**: 每次提取频率/电流都要写 20+ 行 Python（过零点检测、平均值计算）。
这些是模拟设计中最高频的操作。

**期望**:
```bash
# 频率（上升过零点周期平均）
vbridge sim measure freq ./raw/ --signal ON --from 1u
# → 1851.62 MHz

# 平均值
vbridge sim measure avg ./raw/ --signal V0:p --from 1u
# → -1.4126e-04 A

# 峰峰值
vbridge sim measure pp ./raw/ --signal ON --from 1u
# → 0.9166 V (2.3659 ~ 3.2825)

# RMS
vbridge sim measure rms ./raw/ --signal ON --from 1u

# 差分频率（更抗共模漂移）
vbridge sim measure freq ./raw/ --signal "ON-OP" --from 1u
```

**输出格式**: 默认纯文本一行，`--json` 返回结构化数据。

---

### REQ-5: 波形可视化

**优先级**: P2

**场景**: 整个调试过程中从未看到波形图。只通过数值判断"在振荡"。
模拟设计师的核心工作界面是波形。

**期望**（按复杂度递增）:

**5a. 终端 ASCII 预览**（最小实现）:
```bash
vbridge sim plot ./raw/ --signal ON --from 1.5u --to 1.6u --ascii
# ON  ▁▂▅█▇▅▂▁▂▅█▇▅▂▁  (1.85 GHz, 2.37~3.28 V)
```

**5b. 生成 PNG 图像**:
```bash
vbridge sim plot ./raw/ --signals "ON,OP" --from 1.5u --to 1.6u -o waveform.png
```

**5c. 生成交互式 HTML**:
```bash
vbridge sim plot ./raw/ --signals "ON,OP,V0:p" -o waveform.html
# 可缩放、悬停显示数值
```

**注意**: `--csv` 已经能导出全部数据，所以 plot 功能可以基于 CSV 管道实现，
不需要再写 PSF 解析器。

---

### REQ-6: 进程与 License 清理

**优先级**: P3

**场景**: OCEAN `run()` 完成后经常 SIGSEGV 退出，残留 `virtuoso`/`cdsServIpc`/`spectre`
进程占着 `Virtuoso_Spectre` license。OA lock 文件也需手动清理。

**当前操作**:
```bash
ps -u $USER | grep -E 'virtuoso|cdsServIpc|spectre'
kill <pid>
find my_osc -name '*.cdslck*' -delete
```

**期望**:
```bash
vbridge cleanup
# [cleanup] Killed 2 orphan processes (cdsServIpc:12345, spectre:12346)
# [cleanup] Removed 3 lock files
# [cleanup] Released Virtuoso_Spectre license
```

---

### REQ-7: `sch list` 显示 cell name

**优先级**: P3

**现象**:
```
  M8        ?                (9.88, -1.75)
  M15       ?                (10.38, 1.00)
```

`sch read` 正常显示 `nch_33`/`pch_33`/`delay`。
`sch list` 的 `run_list_instances` 可能取的字段和 `run_read` 不同。

**期望**:
```
  M8        nch_33           (9.88, -1.75)
  M15       pch_33           (10.38, 1.00)
  I10       delay            (8.06, 4.88)
```

---

## 三、文档/Skill 补充建议

### DOC-1: `schCreateWireLabel` 不合并网络

skill 文档当前已有警告（"必须用 `label-mos`，不要用 `schCreateWireLabel`"），
建议补充原因说明：

> 裸 `schCreateWireLabel` 在已有 wire 上贴 label 时，如果该 wire 未物理连接到
> 已命名的 net，Virtuoso netlister 不会合并网络。网表中仍输出自动生成的 net 名。
> `label-mos` / `label-term` 先从端子延伸新 wire stub，再在 stub 上放 label，
> 物理连接保证了网络合并。

### DOC-2: `sim run` 需要 `spectre` 在 PATH

`vbridge sim run` 不会自动设置 Cadence 环境。用户需先：
```bash
module load cadence/spectre/251   # 或设 VB_CADENCE_CSHRC
```

否则报 `Spectre executable not found: spectre`。

### DOC-3: `sim result` 的 Spectre log "Maximum value" 说明

Spectre 日志中 `Maximum value achieved for any signal: I(V0:p) = 277.2 uA`
是整个仿真时间内的**瞬时峰值**（通常出现在 t=0 的 IC 切换点），
不是稳态平均值。稳态平均电流通常需要从瞬态数据中截取 t > tstab 段计算。

### DOC-4: TSMC CDF 的 `w` vs `wf`

`vbridge sch param` 已自动同步 `wf`，但在 `vbridge exec` 中手写 SKILL 时需注意：
直接赋值 `cdfFindParamByName(cdf "w")~>value` 绕过 CDF callback，
`wf`（finger width）不会联动更新。Spectre netlister 使用 `wf` 而非 `w`。
必须同时设置两者，或使用 `vbridge sch param`。

---

## 四、总结（2026-09-08 最终状态）

vbridge 已实现完整的无 GUI 工作流：

```
sch read (查看) → sch batch/param (编辑) → sch netlist (网表) → sim run (仿真) → sim result --csv (数据)
```

原标为"最大缺口"的网表生成（REQ-2）和 load 本地模式（REQ-1）均已解决。
w/wf 同步通过 Python 层 `_sync_w_wf()` 修复，不依赖 CDF callback。

**已解决（本次发现已存在的命令）**：
- ~~REQ-4: 内建测量~~ → `vbridge sim measure` 已可用（freq/avg/rms/minmax）
- ~~REQ-6: 进程清理~~ → `vbridge cleanup` 已可用（--dry-run 预览）
- 波形查看器 API 存在于上游（`waveform_viewer.py`），但仅支持 Maestro history，无独立 CLI

**剩余需求优先级**：
- P1: `sch netlist` 生成可独立运行的网表（自动注入 PDK model include，或 `--model` 参数）
- P2: 波形可视化 — CLI 级别（生成 PNG/HTML，不依赖 Maestro/X11）
- P2: `sim result --signal --json` 返回瞬态数据
- P3: `screenshot` 本地模式路径修复
