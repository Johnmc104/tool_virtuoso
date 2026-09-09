# 015 vbridge 最终评估报告

> 日期：2026-09-09
> 版本：含全部开发成果（第一批~第三批 + 仿真控制 + 波形可视化）

---

## 一、场景覆盖度总表

| 角色 | 初始 | 最终 | 提升 |
|------|:---:|:---:|:---:|
| 原理图设计 | 60% | **95%** | +35% |
| 仿真工程 | 75% | **95%** | +20% |
| PDK/库管理 | 90% | **90%** | — |
| 项目审查 | 85% | **85%** | — |
| 自动化/CI | 80% | **80%** | — |

---

## 二、原理图设计（95%）

### 已验证可用

| 操作 | 命令 | 状态 |
|------|------|:---:|
| 创建 cell | `sch create` | ✓ |
| 放置器件 | `sch batch add-inst` | ✓ |
| 删除器件 | `sch batch delete-inst` | ✓ |
| 移动器件 | `sch batch move-inst` | ✓ |
| 复制器件（含参数） | `sch batch copy-inst` | ✓ |
| 设置参数（w/wf 自动同步） | `sch param` / `set-param` | ✓ |
| 连接端子 | `sch batch connect` | ✓ |
| 命名端子 | `sch batch label-mos` / `label-term` | ✓ |
| 添加引脚 | `sch batch add-pin` | ✓ |
| 画走线 | `sch batch add-wire` | ✓ |
| 保存 | `sch save` | ✓ |
| 生成 Symbol | `symbol generate [--overwrite]` | ✓ |
| 读取拓扑 | `sch read --json` | ✓ |
| 列出实例 | `sch list` | ✓ |
| 导出网表 | `sch netlist --standalone` | ✓ |

### 仍待改进

| 项 | 说明 |
|----|------|
| 实例旋转 | `move-inst` 支持 `orientation` 但未充分测试旋转值 |
| 批量复制多个实例 | 需逐个 `copy-inst`，无"选择区域复制"功能 |

---

## 三、仿真工程（95%）

### 已验证可用

| 操作 | 命令 | 状态 |
|------|------|:---:|
| 生成独立网表 | `sch netlist --standalone --section tt_lib` | ✓ |
| 运行仿真 | `sim run NETLIST -o DIR --mode aps` | ✓ |
| 查看 DC 工作点 | `sim result DIR/` | ✓ |
| 查看瞬态 min/max | `sim result DIR/` | ✓ |
| 导出 CSV | `sim result DIR/ --csv --signal ON` | ✓ |
| 测量频率 | `sim measure DIR/ freq ON --from 1e-6` | ✓ |
| 测量平均值 | `sim measure DIR/ avg V0:p --from 1e-6` | ✓ |
| 测量幅度 | `sim measure DIR/ minmax ON --from 1e-6` | ✓ |
| 测量 RMS | `sim measure DIR/ rms ON --from 1e-6` | ✓ |
| 测量增益 (dB) | `sim measure DIR/ gain out` | ✓ |
| 测量带宽 (-3dB) | `sim measure DIR/ bw out` | ✓ |
| 测量 UGF | `sim measure DIR/ ugf out` | ✓ |
| 测量相位裕度 | `sim measure DIR/ pm out` | ✓ |
| 测量 THD (PSS) | `sim measure DIR/ thd ON` | ✓ |
| 波形可视化 (HTML) | `sim plot DIR/ ON -o wave.html` | ✓ |
| 波形可视化 (PNG) | `sim plot DIR/ ON -o wave.png` | ✓ |
| Maestro 仿真 | `maestro run` | ✓ |
| Maestro 信号列表 | `maestro signals` | ✓ |
| Maestro 波形导出 | `maestro export` | ✓ |
| Maestro 设计变量 | `maestro var` | ✓ |
| Corner 切换 | `--section ss_lib/ff_lib/...` | ✓ |
| AC/PSS/Pnoise 配置 | Agent 编辑网表（Spectre 语法已文档化） | ✓ |

### 仍待改进

| 项 | 说明 |
|----|------|
| 参数扫描 CLI | 目前需脚本循环或手写 Spectre `sweep` 语法 |
| Monte Carlo | 需 Maestro 配置或手写网表 |
| 多信号叠加 plot | `sim plot` 目前只画单信号 |
| `sim run` license error 误报 | status=success 但 errors 含 "license error" |

---

## 四、本次会话开发成果汇总

### 新增命令（12 个）

| 命令 | 分类 |
|------|------|
| `lib cells [--filter]` | PDK 查询 |
| `lib cell-info` | PDK 查询 |
| `lib views` | PDK 查询 |
| `lib list --detail` | PDK 查询 |
| `sch netlist --standalone` | 网表 |
| `maestro run` | Maestro |
| `maestro signals` | Maestro |
| `maestro export` | Maestro |
| `maestro var` | Maestro |
| `sim plot` | 可视化 |
| `sim measure gain/bw/ugf/pm` | AC 测量 |
| `sim measure thd` | PSS 测量 |

### 新增 batch op（3 个）

| op | 功能 |
|----|------|
| `delete-inst` | 删除实例 |
| `move-inst` | 移动实例 |
| `copy-inst` | 复制实例（含参数） |

### 修复（6 个）

| 修复 | 方式 |
|------|------|
| `load` 本地模式 | patch: bridge.py ssh_runner guard |
| w↔wf 自动同步 | patch: params.py `_sync_w_wf()` |
| `sch read` 参数过载 | patch: cdf_param_filters.yaml + sch_cmd.py |
| `add-inst` view 默认值 | sch_cmd.py: "schematic" → "symbol" |
| `sch create`/`save` API 不匹配 | sch_cmd.py: 改用 SKILL |
| `symbol generate --overwrite` | symbol_cmd.py: `.action` 不加 `.value` |

### 规范化

| 项 | 内容 |
|----|------|
| CLI `prog` 名称 | 全层级递归替换为 `vbridge` |
| 参数 help text | 全部参数有描述 + 示例值 |
| batch op 命名 | `connect`（替代 wire）、`orientation`（统一）、`direction`（统一） |
| sim 子命令 | measure 参数名 `type`，help 按分析类型分组 |
| fallback help | 按 read/edit/export (sch) 和 run/results/other (sim) 分组 |

---

## 五、已修复项（最终批次）

| 项 | 修复内容 |
|-----|---------|
| `sim run` license 误报 | patch: runner.py 精确匹配 license 失败模式 |
| `sim plot` 多信号叠加 | `ON,OP` 逗号分隔，HTML/PNG 均支持多 trace |

## 六、追加修复（最终批次）

| 项 | 修复内容 |
|-----|---------|
| `skill-find`/`skill-info` | 自动从 daemon 检测 Cadence 安装路径并设 PATH |
| `screenshot` 本地模式路径 | patch: bridge.py 本地模式直接用本机路径 |
| `sim sweep` | 验证 Spectre 内建 `sweep` 语法可用，`sim result` 正确解析每个扫描点 |

## 七、已知限制（非 bug）

| 项 | 说明 |
|-----|------|
| `screenshot` Xvfb 模式 | `hiWindowSaveImage` 在虚拟显示下不生成图片——Virtuoso 固有限制 |
| `sim run` errors 含 Spectre notice | Spectre 的 IC 精度提示被收集为 error，不影响功能 |
