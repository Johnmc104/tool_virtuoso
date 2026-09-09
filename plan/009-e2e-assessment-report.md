# 009 vbridge 端到端使用评估报告

> 基于 `test_osc` 差分环振完整工作流：原理图读取 → 编辑 → 网表生成 → 仿真 → 结果查看。
> 版本：vbridge v0.1.0（含 `load` 本地模式修复），IC251，Spectre 251。
> 日期：2026-09-08

---

## 一、各环节评估

### 1. 原理图信息获取

#### 1.1 库和 Cell 发现

| 操作 | 命令 | 体验评分 | 说明 |
|------|------|----------|------|
| 列出库 | `vbridge lib list` | ★★★★★ | 一条命令，14 个库清晰列出 |
| 列出 cell | `vbridge exec 'ddGetObj("my_osc")~>cells~>name'` | ★★★☆☆ | 需要写 SKILL，无直接命令 |
| 列出 view | `vbridge exec 'ddGetObj("my_osc" "osc")~>views~>name'` | ★★★☆☆ | 同上 |

**建议**：增加 `vbridge lib cells my_osc` 和 `vbridge lib views my_osc osc`。

#### 1.2 实例列表

| 命令 | 内容 | 体验评分 | 说明 |
|------|------|----------|------|
| `sch list` | 名称 + cell + 坐标 | ★★★★☆ | 简洁，适合快速浏览，cell name 已修复 |
| `sch read` (文本) | 名称 + cell + 全部 CDF 参数 | ★★☆☆☆ | 信息过多，每个 MOS 输出 100+ 参数，淹没关键信息 |
| `sch read --json` + python | 按需提取 | ★★★★★ | JSON 结构化，可精确过滤 W/L/nf 等关键参数 |

**建议**：`sch read` 文本模式增加 `--brief` 选项，只显示关键参数（w/l/nf/m + dc voltage）。
或参照 `sch list` 的表格格式，加一列显示关键参数摘要。

#### 1.3 网络连接关系

| 命令 | 体验评分 | 说明 |
|------|----------|------|
| `sch read --json` → `nets` | ★★★★★ | 完整的网络拓扑：每个 net 的所有连接（inst.term 格式） |

实测输出：
```json
"VBN": {"connections": ["M11.D", "M3.D", "M8.G", "M16.G", "I10.VBN", ...]}
```

这是**最有价值的功能之一**——能直接验证连线正确性，无需打开 GUI。
发现 VBN 缺陷、验证修复都可以用这个命令一步完成。

**无改进建议**，当前已很好用。

#### 1.4 子电路读取

| 命令 | 体验评分 | 说明 |
|------|----------|------|
| `sch read my_osc delay --json` | ★★★★★ | 完整：引脚列表 + 内部实例 + 内部网络 |

实测：delay 子电路的 8 个引脚、7 个 MOS、9 个内部 net 全部正确列出。

#### 1.5 引脚（Pins）

`sch read --json` 的 `pins` 字段对顶层 `osc` 返回空 `{}`。
这是因为 `osc` 作为顶层仿真单元没有 schematic pin（只有 vdc 源连外部）。
子电路 `delay` 正确返回 8 个引脚。属于正常行为。

---

### 2. 原理图编辑

#### 2.1 修改端子网名

| 方法 | 体验评分 | 说明 |
|------|----------|------|
| `sch batch label-mos` | ★★★★★ | 两行 JSON 即完成 M3/M11 drain → VBN |
| `sch batch label-term` | 未测试 | 应同理可用 |

**关键发现**（已文档化）：裸 `schCreateWireLabel` 不合并网络，必须用 `label-mos`/`label-term`。

#### 2.2 修改器件参数

| 方法 | 体验评分 | 说明 |
|------|----------|------|
| `sch param` | ★★★★★ | 自动触发 CDF callback，w/wf 同步 |
| `sch batch set-param` | ★★★☆☆ | 可一次改多个参数，**但不同步 wf** |

**新发现**：`sch batch set-param` 设 `w=2400n` 后 `wf` 仍为 `1.6u`。
只有 `sch param` 输出了 `(with CDF callbacks)` 并正确同步。

**这是本次测试最重要的 bug**——`set-param` 是批量改参数的主力操作，
wf 不同步会导致网表中器件宽度错误，且很难发现（需要对比 w 和 wf 才能看出）。

**建议**：`set-param` 应与 `sch param` 使用相同的 CDF callback 机制。
至少在设置 `w` 时自动同步 `wf = w / nf`。

#### 2.3 批量编辑工作流

16 个 MOS 全部改尺寸的场景：
- `sch param`：逐个调用（16 × 8 = 128 次），自动同步但慢
- `sch batch set-param`：一次 JSON（16 条 op），快但 wf 不同步
- `.il 脚本` + `load`：最灵活，现在 `load` 已修复可直接用

**建议**：修复 `set-param` 的 wf 同步后，`sch batch` 就是最佳批量编辑方案。

---

### 3. 网表生成

| 方法 | 体验评分 | 说明 |
|------|----------|------|
| OCEAN 脚本 + `ocean -nograph` | ★★☆☆☆ | 需手写 7 行 .ocn，启动慢 ~10s，经常 SIGSEGV |
| 无 vbridge 命令 | — | 仍然是最大缺口 |

OCEAN 的痛点：
1. 需要指定 `simulator`/`design`/`modelFile`/`analysis`/`temp`/`ic` 共 7 个参数
2. 启动加载 ~30 个 .cxt 文件花 10 秒
3. 退出时 exit 139 (SIGSEGV)
4. 与 vbridge daemon 并发时报 lock 警告

**建议不变**：实现 `vbridge netlist my_osc osc`。

---

### 4. 仿真控制

| 操作 | 命令 | 体验评分 | 说明 |
|------|------|----------|------|
| 运行仿真 | `vbridge sim run input.scs -o ./raw` | ★★★★☆ | JSON 返回信号列表和路径；需先 `module load spectre` |
| 仿真模式 | `--mode aps/ax/cx/mx/lx` | 未测试 | 有选项 |
| License 检查 | `vbridge sim license` | 未测试 | 有命令 |

**问题**：
1. `status: "success"` 时 `errors` 里有 `"license error"` 误报（实际仿真成功）
2. 无法在命令行覆盖 Vcon 等设计变量（需手动改网表）
3. 无法指定 initial conditions（需写在网表里）

**建议**：
- 修复 license error 误报（检查 Spectre 退出码而非 log 中的 license 字符串）
- 未来增加 `--param Vcon=2.1` 和 `--ic "ON=3.3,OP=0"` 参数覆盖

---

### 5. 结果查看

#### 5.1 概览模式

| 命令 | 体验评分 | 说明 |
|------|----------|------|
| `sim result dir/` | ★★★★★ | DC 直接显示数值；瞬态显示点数 + min/max |

实测输出非常实用：
```
dcOp.dc:
  VBN: 1.051000774318816
  V0:p: -0.0001411909474908613

tran.tran.tran:
  ON: [75652 pts] min=2.097  max=3.3
  V0:p: [75652 pts] min=-0.0002772  max=-0.0001389
```

一眼判断：VBN=1.05V 正常，ON 在 2.1~3.3V 振荡，V0:p 峰值 277uA。

#### 5.2 信号查询

| 命令 | 体验评分 | 说明 |
|------|----------|------|
| `sim result --signal X --json` | ★★★☆☆ | 只返回 DC 标量，瞬态被跳过 |
| `sim result --csv --signal X` | ★★★★★ | 完整导出 time + 信号两列 |
| `sim result --csv` (全部) | ★★★★☆ | 75652 × 9 列 CSV，数据量大但完整 |

**建议**：`--signal X --json` 也应返回瞬态数据（数组），可加 `--from/--to` 裁剪。

#### 5.3 数据分析

当前从 CSV 提取频率/电流需要写 ~20 行 Python。

| 分析 | 方法 | 体验评分 |
|------|------|----------|
| 频率 | Python 过零点检测 | ★★☆☆☆ |
| 平均电流 | Python 截取 + 求均值 | ★★☆☆☆ |
| DC 工作点 | `sim result` 直接显示 | ★★★★★ |

**建议不变**：内建 `vbridge sim measure freq/avg/pp/rms`。

#### 5.4 波形可视化

无任何波形查看能力。

---

### 6. SKILL 执行

| 命令 | 体验评分 | 说明 |
|------|----------|------|
| `exec` (单行) | ★★★★★ | 稳定，响应快 |
| `exec` (多行) | ★★★★☆ | 单引号包裹即可，但需注意转义 |
| `load file.il` | ★★★★★ | 本地模式已修复 |

`exec` + `load` 组合覆盖了所有 SKILL 需求，是 vbridge 的坚实底座。

---

## 二、命令易用性评分总表

| 命令 | 评分 | 备注 |
|------|------|------|
| `lib list` | ★★★★★ | |
| `sch list` | ★★★★☆ | cell name 已修复 |
| `sch read --json` | ★★★★★ | 结构化输出极好，网络拓扑最有价值 |
| `sch read` (文本) | ★★☆☆☆ | 100+ 参数信息过载 |
| `sch batch label-mos` | ★★★★★ | |
| `sch batch set-param` | ★★★☆☆ | **wf 不同步（BUG）** |
| `sch param` | ★★★★★ | CDF callback 正常 |
| `sch save` | ★★★★★ | |
| `sim run` | ★★★★☆ | license error 误报 |
| `sim result` (概览) | ★★★★★ | min/max 很实用 |
| `sim result --csv` | ★★★★★ | 完整数据，可管道处理 |
| `sim result --signal --json` | ★★★☆☆ | 只返回 DC |
| `exec` | ★★★★★ | |
| `load` | ★★★★★ | 本地模式已修复 |
| `status` | ★★★★★ | |

**平均：4.1 / 5**

---

## 三、新发现的问题

### BUG-NEW-1: CDF callback 不触发 w↔wf 联动（`sch param` 和 `set-param` 均受影响）

**初始错误结论**：以为只有 `set-param` 有问题，`sch param` 正常。
**纠正后结论**：`sch param` 和 `set-param` 使用相同的 `_run_batched_param_update` 函数，
两者都不能触发 w→wf 或 wf→w 的联动。之前 `sch param` "能工作" 是因为 wf 已经是正确值。

**验证实验**：
```bash
# 手动把 wf 改成 800n
vbridge exec '...cdfFindParamByName(cdf "wf")~>value = "800n"...'

# 用 sch param 改 w
vbridge sch param my_osc osc M3 w 1600n
# → W=1.6u wf=800n  ← wf 没跟着变！

# 反方向也不行
vbridge exec '...cdfFindParamByName(cdf "w")~>value = "999n"...'
vbridge sch param my_osc osc M3 wf 1600n
# → W=999n wf=1.6u  ← w 没跟着变！
```

**根因**：`params.py` 中 `_RUN_CALLBACKS_ON_CV` 的 SKILL 模板在 cell CDF 上下文中
执行 callback（`errset(evalstring(cb) t)`），但 TSMC PDK 的 w/wf callback
依赖 `cdfgForm` 上下文和 GUI form 状态，在纯 SKILL 执行环境中不生效。

**影响**：严重——设 `w` 后 `wf` 不变，网表使用 `wf` 值，导致器件宽度错误。
**workaround**：修改 w 时必须同时手动修改 wf（和反过来）。
**优先级**：P0

**建议修复**：不依赖 CDF callback 来同步 w/wf，改为在 Python 层硬编码同步逻辑：
```python
# 在 _run_batched_param_update 或 set_instance_params 中：
if "w" in params and "wf" not in params:
    nf = int(current_nf or "1")
    params["wf"] = params["w"]  # when nf=1
    # or: wf = float(parse_eng(params["w"])) / nf
if "wf" in params and "w" not in params:
    nf = int(current_nf or "1")
    params["w"] = params["wf"]  # when nf=1
```

### BUG-NEW-2: `sim run` license error 误报

`status: "success"` 但 `errors: ["license error"]`。
Spectre 日志中有 license checkout 成功的记录，仿真正常完成。
可能是解析 log 时错误匹配了 "license" 关键字。

**影响**：低——不影响功能，但 exit code 非零会误导自动化脚本。
**优先级**：P2

---

## 四、Skill 文档更新建议

当前 `tool-virtuoso-bridge` skill 文档侧重命令参考，缺少实际使用场景指引。建议重构为：

### 结构建议

```
1. 快速入门（5 分钟）
   - 连接检查: vbridge status
   - 读原理图: vbridge sch read lib cell --json
   - 改参数: vbridge sch param lib cell inst param value
   - 跑仿真: vbridge sim run netlist.scs -o ./raw
   - 看结果: vbridge sim result ./raw/

2. 原理图操作详解
   - 信息获取: lib list → sch list → sch read --json
   - 编辑: sch param (单个) / sch batch (批量)
   - 连线修改: label-mos / label-term（附 schCreateWireLabel 陷阱说明）
   - 保存: sch save
   - SKILL 直接执行: exec / load

3. 仿真流程
   - 网表准备（当前需 OCEAN）
   - 运行: sim run
   - 结果概览: sim result
   - 数据导出: sim result --csv --signal X
   - 频率/电流提取 Python 示例

4. 命令参考（当前文档内容）

5. 常见问题
   - set-param 的 w/wf 问题
   - license error 误报
   - OCEAN lock 冲突
   - spectre 不在 PATH
```

### 关键补充内容

1. **`sch read --json` 的数据结构说明**——当前文档只有示例没有字段说明
2. **`sim result --csv` 管道用法**——与 Python/awk 配合提取频率/电流的实例
3. **`set-param` vs `sch param` 区别**——callback 行为不同，W 时必须注意
4. **模拟设计完整工作流示例**——从零开始的差分对/环振设计流程

---

## 五、总结

vbridge 在"读原理图 + 改参数 + 跑仿真 + 导数据"这条链路上已基本可用，
`sch read --json` 和 `sim result --csv` 是两个亮点功能。

### 会话期间修复的问题

| 问题 | 修复 |
|------|------|
| w/wf 不同步 | Python 层 `_sync_w_wf()` 自动双向同步 |
| `load` 本地模式 | `bridge.py` 加 `ssh_runner is not None` 检查 |
| 网表生成缺口 | `vbridge sch netlist` 已存在（本次才发现） |

### 最终状态

完整无 GUI 链路已打通：
`sch read → sch batch/param → sch netlist → sim run → sim result --csv`

**仍需改进的 1 个功能**：`sch netlist` 的网表需手动加 PDK model include
**最需要增加的 1 个功能**：波形可视化
**最需要改善的 1 个体验**：`sch read` 文本模式的参数过载（`--brief`）
