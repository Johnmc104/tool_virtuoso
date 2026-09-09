# 007 IC251 实际使用测试反馈

## 测试场景

在 `test_osc` 项目中使用 vbridge + IC251 修改差分环振原理图：
1. 用 `label-mos` 修复 net14→VBN 缺失连线
2. 用 SKILL 批量修改 16 个 MOS 的 W/L 及寄生参数（bias_k4 优化）
3. 通过 OCEAN 生成网表并用 Spectre 251 仿真验证

测试日期：2026-09-08

## 问题清单

### P1: `vbridge sch list` PyInstaller 打包缺数据文件

**现象**：
```
FileNotFoundError: [Errno 2] No such file or directory:
  '/tmp/_MEInPxMUv/virtuoso_bridge/virtuoso/schematic/cdf_param_filters.yaml'
```

**原因**：`reader.py` 用 `Path(__file__).parent / "cdf_param_filters.yaml"` 定位数据文件。
PyInstaller `--onefile` 模式下，`__file__` 指向临时解压目录，yaml 文件未被打包进去。

`packaging.yaml` 里有 `collect_all: [virtuoso_bridge]`，理论上应该收集所有数据文件，
但实际未生效。可能是 `collect_all` 无法识别 `.yaml` 文件，或路径嵌套过深。

**影响**：`vbridge sch list`、`vbridge sch read` 不可用。

**建议修复**：在 PyInstaller spec 中显式添加 `datas` 项：
```python
datas=[('virtuoso_bridge/virtuoso/schematic/cdf_param_filters.yaml',
        'virtuoso_bridge/virtuoso/schematic/')]
```
或在 `reader.py` 中加 PyInstaller 兼容路径检测（`sys._MEIPASS`）。

### P2: `vbridge sch param` 依赖不存在的 `cdfSetInstParam`

**现象**：
```
[sch] error:
  ("load" 0 t nil ("*Error* load: error while loading file ..."))
```

**原因**：`sch_cmd.py:run_param()` 生成的 SKILL 使用 `cdfSetInstParam()` 和
`dbFindInstByName()`，这两个函数在 IC251 (OA 22.62) 中不存在：

```python
# sch_cmd.py line 183-184
f'inst = dbFindInstByName(cv "{...}")\n'
f'cdfSetInstParam(inst "{...}" "{...}")\n'
```

在 IC251 CIW 里验证：
```
fboundp(quote(cdfSetInstParam))  => nil
fboundp(quote(dbFindInstByName)) => nil
```

**可用替代 API**：
```skill
; 查找实例
inst = car(setof(i cv~>instances i~>name == "M3"))

; 设置参数
cdf = cdfGetInstCDF(inst)
cdfFindParamByName(cdf "w")~>value = "1600n"
```

**影响**：`vbridge sch param` 完全不可用。

**建议修复**：
1. 添加 `dbFindInstByName` 的 fallback 实现（`setof` 方式）
2. 替换 `cdfSetInstParam` 为 `cdfFindParamByName(cdf "param")~>value = "val"` 模式
3. 建议在 SKILL 生成前做一次 `fboundp` 检查，根据 Virtuoso 版本选择 API

### P3: `vbridge load` 本地模式不可用

**现象**：
```
Failed to prepare IL path: Deployment SSH runner is unavailable in local mode
```

**原因**：`vbridge load` 尝试通过 SSH 部署 .il 文件到远程，在本地模式下无 SSH runner。

**解决方法**：用 `vbridge exec 'load("/absolute/path/to/file.il")'` 代替。
在 CIW 进程内直接 `load()` 可以加载任何本地路径。

**建议修复**：本地模式下直接构造 `load("...")` SKILL 表达式发送给 daemon。

### P4: CDF 参数 `w` 与 `wf` 不同步

**现象**：通过 `cdfFindParamByName(cdf "w")~>value = "1600n"` 设置 W 后，
CDF 读回显示 w=1.6u，但 Spectre 网表中仍输出 w=400n（原值）。

**原因**：TSMC CDF 系统有 `w`（总宽度）和 `wf`（finger width）两个参数。
直接赋值绕过了 CDF callback，`wf` 未被联动更新。
Spectre netlister 实际使用的是 `wf`（因为 `nf=1`，`wf` 就是器件宽度）。

设置 L 没有此问题（L 无对应的 "finger L" 参数），寄生参数（ad/as/pd/ps/nrd/nrs）也不受影响。

**解决方法**：同时设置 `w` 和 `wf`：
```skill
cdfFindParamByName(cdf "w")~>value = "1600n"
cdfFindParamByName(cdf "wf")~>value = "1600n"
```

**建议改进**：`vbridge sch param` 和 `label-mos` 等修改参数的接口，
在设置 `w` 时应自动联动 `wf = w / nf`。
或者触发 CDF callback 来自动处理关联参数。

## 修复后复测 (2026-09-08)

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| P1: `sch list` yaml | FileNotFoundError | ✓ 正常列出 26 instances（cell name 列显示 `?`，`sch read` 正常） |
| P2: `sch param` | cdfSetInstParam 不存在 | ✓ 正常设参且自动 sync wf：`[sch] Set M3.w = 1600n (wf synced)` |
| P3: `load` 本地模式 | SSH runner 不可用 | ✗ 仍报 `Deployment SSH runner is unavailable in local mode` |
| P4: w/wf 不同步 | 需手动设 wf | ✓ 由 P2 修复自动处理 |

### 新发现的小问题

**P5: `sch list` cell name 显示 `?`**

```
  M8        ?                (9.88, -1.75)
  M15       ?                (10.38, 1.00)
```

`sch read` 正常显示 cell name（`nch_33`, `pch_33`, `delay`），
`sch list` 对应列为 `?`。可能是 `run_list_instances` 取的字段和 `run_read` 不同。

## 端到端工作流缺口分析

以下基于完整的"原理图修改 → 网表生成 → 仿真 → 结果提取"流程，
按设计阶段梳理 vbridge 尚未覆盖或体验不佳的环节。

### A. 原理图编辑

**A1: `sch batch` 缺少 `set-param` 操作**

当前需修改多个实例参数时，只能写 .il 脚本 + `vbridge exec 'load("...")'`。

实际操作：写 25 行 SKILL 遍历 16 个实例名，逐个 `cdfFindParamByName`。
理想方式：
```bash
echo '[
  {"op": "set-param", "inst": "M3", "params": {"w": "1600n", "l": "1520n", "ad": "3.68e-13"}},
  {"op": "set-param", "inst": "M11", "params": {"w": "1600n", "l": "1520n"}}
]' | vbridge sch batch my_osc osc
```

或在 `sch param` 支持多实例：
```bash
vbridge sch param my_osc osc "M0,M1,M2,M3,M4,M6,M7,M8" w 1600n
```

**A2: `schCreateWireLabel` vs `label-mos` 行为差异需文档化**

实际经历：直接调 `schCreateWireLabel` 在 net14 的 wire 上贴 VBN 标签，
CDF 显示网名正确但 netlister 不认，网表仍输出 net14。
换用 `label-mos`（先画 wire stub 再贴 label）后一次成功。

原因：裸 `schCreateWireLabel` 贴在已有 wire 上时，
如果没有物理连接到 named net 的 wire，netlister 不合并网络。
`label-mos` 从端子向外延伸一段新 wire，label 挂在新 wire 上，
物理连接保证了网络合并。

建议：在 skill 文档中明确说明：修改端子网名必须用 `label-mos` / `label-term`，
不要直接用 `schCreateWireLabel`。

### B. 仿真控制

**B1: 无从原理图生成网表的命令**

实际操作：写 OCEAN `.ocn` 脚本，`ocean -nograph -restore run_osc.ocn`。
需要手动指定 `simulator`、`design`、`resultsDir`、`modelFile`、`analysis`、`temp`、`ic`。

理想方式：
```bash
vbridge netlist my_osc osc --simulator spectre --output ./netlist/
```
或封装 OCEAN 的参数模板让用户只填差异项。

**B2: 无直接运行仿真的命令**

skill 文档提到 `spectre_run` 内建工具，但实际会话中不可用（非 MCP 工具）。
实际操作：手写 standalone `.scs` 网表 + `spectre -64 -format psfascii`。

理想方式：
```bash
vbridge sim run input.scs --format psfascii --raw ./output.raw
# 或从原理图直接
vbridge sim run my_osc osc --analysis tran --stop 2u --params "Vcon=2.1"
```

**B3: OCEAN 脚本的 ic / 设计变量需手工硬编码**

差分环振必须加 `ic("/ON" 3.3 "/OP" 0)` 才能起振，
Vcon 值通过修改 V1.dc 指定，没有参数化传入机制。

理想方式：支持从命令行覆盖设计变量和初始条件：
```bash
vbridge sim run my_osc osc --ic "ON=3.3,OP=0" --var "Vcon=2.1"
```

### C. 结果提取与数据分析

**C1: 无 PSF 解析工具**

skill 文档提到 `spectre_parse` 工具，实际不可用。
psfxl（二进制）格式完全无法读取，只能重跑 psfascii。

实际操作：写 40 行 Python 解析 psfascii 的 `"signal" value` 行格式，
手工实现过零点检测、频率计算、电流平均。

理想方式：
```bash
# 解析 DC 工作点
vbridge psf read ./output.raw/dcOp.dc
# → VBN=1.051V  net1=2.1027V  V0:p=-141.2uA

# 提取瞬态波形为 CSV
vbridge psf export ./output.raw/tran1.tran.tran --signals ON OP V0:p --csv

# 内建测量
vbridge measure freq ./output.raw --signal ON --from 1u
# → 1851.62 MHz
vbridge measure avg ./output.raw --signal V0:p --from 1u
# → -141.26 uA
```

**C2: Spectre log 的 "Maximum value" 容易误读**

`I(V0:p) = 277.2 uA` 是 t=0（IC 切换瞬间）的峰值，不是稳态平均。
之前 plan 文档中将此值直接用于功耗计算（P = 277 × 3.3 = 0.915 mW），
实际稳态平均电流只有 141 uA。

建议：在 skill 文档或 PSF 解析工具的输出中明确区分 peak / average / rms。

### D. 波形可视化

**D1: 完全没有波形查看能力 — 模拟设计最大缺口**

整个流程中从未看到 ON/OP 的振荡波形。只通过数值确认"在振荡"。
模拟设计师的核心工作界面是波形查看器。

理想方式（按优先级）：

1. **最小可用**：ASCII 预览
```bash
vbridge wave preview ./output.raw --signal ON --from 1.5u --to 1.6u
# ON ▁▂▅█▇▅▂▁▂▅█▇▅▂▁  (1.85 GHz, 2.37~3.28V)
```

2. **实用级**：生成 PNG/HTML
```bash
vbridge wave plot ./output.raw --signals "ON,OP" --from 1.5u --to 1.6u -o waveform.png
```

3. **完整级**：启动交互查看器
```bash
vbridge wave open ./output.raw   # 启动 Verdi/wvfm 或 web viewer
```

**D2: 无法对比多次仿真结果的波形**

优化实验有 9 个变体，每个有独立的 PSF 目录。
无法快速叠加对比不同变体的波形或指标。

理想方式：
```bash
vbridge wave compare \
  --label base    ./run_251/opt/base_tran/ \
  --label bias_k4 ./run_251/opt/bias_k4_tran/ \
  --signal ON --from 1.5u --to 1.6u
```

### E. 进程与环境管理

**E1: OCEAN 退出后进程残留 / 崩溃**

`ocean -nograph` 跑完 `run()` 后以 exit code 139 (SIGSEGV) 崩溃，
`virtuoso`/`cdsServIpc` 进程有时不退出，占着 `Virtuoso_Spectre` license。
OA lock 文件残留需手动清理。

实际操作：
```bash
ps -u $USER | grep -E 'virtuoso|cdsServIpc|spectre'
find my_osc -name '*.cdslck*' -delete
```

理想方式：
```bash
vbridge cleanup   # 一键清理：kill 残留进程 + 删 lock 文件 + 释放 license
```

**E2: vbridge daemon 与 OCEAN 共存时的 lock 冲突**

OCEAN 打开原理图时报 `Unable to lock database file`（因 vbridge daemon 已持有）。
不影响网表生成和仿真，但产生 warning 和一个 `strcat: nil` 错误。

建议：文档说明 daemon 与 OCEAN 并发时的 lock 行为，
或提供 `vbridge sch unlock` / `vbridge pause` 临时释放。

## 工作正常的部分

- `vbridge exec` 执行任意 SKILL 表达式 ✓
- `vbridge exec 'load("...")'` 加载 .il 脚本 ✓
- `vbridge sch batch` 的 `label-mos` 操作 ✓
- `vbridge sch read` 读取完整 CDF 参数 ✓
- `vbridge sch param` 设置参数并自动 sync wf ✓
- `vbridge status` 状态检查 ✓
- Virtuoso daemon 连接稳定 ✓

## 第二轮更新后复测 (2026-09-08)

新版 skill 文档增加了 `set-param`、`sim run`、`sim result`、`lib list`、`symbol generate` 等命令。

### 已解决

| 建议项 | 状态 | 结果 |
|--------|------|------|
| A1: `set-param` 批量操作 | ✓ 已实现 | `[sch] OK: 2 ops applied`，多实例多参数均正常 |
| B2: 仿真运行命令 | ✓ 已实现 | `vbridge sim run` 返回信号列表和输出路径（需先 `module load spectre`） |
| C1: PSF 解析 CLI | ✓ 部分实现 | DC 工作点可完整解析；瞬态数据仅显示点数 |
| A2: `schCreateWireLabel` 文档 | ✓ 已文档化 | skill 文档明确注明必须用 `label-mos` |

### 新增命令测试结果

**`set-param`** — 完全可用：
```bash
echo '[{"op": "set-param", "inst": "M3", "params": {"w": "1600n", "l": "1520n"}}]' \
  | vbridge sch batch my_osc osc
# → [sch] OK: 1 ops applied to my_osc/osc/schematic
```

**`sim run`** — 可用，需 spectre 在 PATH：
```bash
module load cadence/spectre/251
vbridge sim run standalone.scs -o ./sim_test
# → {"status": "success", "signals": ["ON", "OP", "V0:p", ...], "output_dir": "..."}
```

**`sim result`** — DC 可用，瞬态数据不完整：
```bash
vbridge sim result ./sim_test/standalone.raw/
# DC 工作点正确显示：VBN=1.051V, net1=2.1027V, V0:p=-141.2uA
# 瞬态显示 "[75652 points]"（字符串），无法提取实际数据
```

**`sim result --signal ON --json`** — 只返回 DC 值，瞬态被跳过：
```json
{"ON": 2.956933283931938}
```

**`sch read --json`** — 非常好用，结构化输出：
```json
{"instances": [{"name": "M3", "cell": "nch_33", "params": {"w": "1.6u", ...}}],
 "nets": {"VBN": {"connections": ["M11.D", "M3.D", "M8.G", ...]}}}
```

**`lib list`** — 正常列出 14 个库。

### 仍待解决

| 建议项 | 状态 | 说明 |
|--------|------|------|
| P3: `load` 本地模式 | ✗ 未修复 | 仍报 `SSH runner unavailable`，用 `exec 'load("...")'` 绕过 |
| P5: `sch list` cell name | ✗ 未修复 | 显示 `?`，`sch read` 正常 |
| D1: 波形可视化 | ✗ 未实现 | 有 CSV 数据但无图形输出 |
| B1: 网表生成命令 | ✗ 未实现 | 仍需手写 OCEAN 脚本 |
| E1: 进程清理 | ✗ 未实现 | 仍需手动 `ps` + `kill` + `find -delete` |

### 瞬态数据提取：`--csv` 已完全解决

第二轮更新后 `sim result --csv` 可完整导出瞬态波形数据：

```bash
# 全部信号，75652 行 CSV
vbridge sim result ./standalone.raw/ --csv

# 只导出 ON 信号（time + ON 两列）
vbridge sim result ./standalone.raw/ --csv --signal ON
```

输出格式清晰：
```csv
# dcOp.dc (scalar)
signal,value
ON,2.956933283931938
V0:p,-0.0001411909474908613
# tran1.tran.tran (sweep, 75652 points)
time,ON
0.0,3.299855751086825
1.953125e-12,3.158654213206797
```

验证：通过 CSV 数据提取的频率 1851.62 MHz 与手工解析 psfascii 结果完全一致。

### 进一步改进建议

现有功能已覆盖"改原理图 → 跑仿真 → 导数据"的完整链路，
剩余优化方向：

1. **内建测量**：`vbridge sim measure freq --signal ON --from 1u`，
   避免用户每次都要写 Python 做过零点检测
2. **波形预览**：CSV 数据在手，可生成 PNG/HTML（`vbridge sim plot ...`）
3. **网表生成**：`vbridge netlist my_osc osc` 封装 OCEAN 调用
4. **`load` 本地模式**：直接构造 `load("...")` 发给 daemon

## 优先级建议（更新后）

| 优先级 | 项目 | 理由 |
|--------|------|------|
| **P1** | D1: 波形可视化 | CSV 数据已有，差一个 plot 命令 |
| **P1** | B1: 网表生成命令 | 仍需手写 OCEAN |
| **P1** | P3: `load` 本地模式 | 基础功能，修复简单 |
| **P2** | 内建测量 (freq/avg/rms) | 减少手工 Python |
| **P2** | E1: 进程清理 | 防止 license 泄漏 |
| **P3** | P5: `sch list` cell name | 小 bug |
