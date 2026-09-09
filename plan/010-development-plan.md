# 010 vbridge 开发计划

> 基于 IC251 模拟设计全流程实测 + 上游代码库全面审计。
> 原则：上游已有的能力直接暴露为 CLI，不重复造轮子。上游改动通过 patch 管理。
> 日期：2026-09-08

---

## 一、上游已有但未暴露的能力（直接包装为 CLI）

### P1: PDK 器件查询

上游 `library/category.py` 提供分类 API（OA category 系统），
但 TSMC 65nm 不使用此系统。需要通用方案。

**已验证可行的 SKILL**：
```skill
; 列出 PDK 中全部 MOS 器件名
setof(cell ddGetObj("CRN65LP_v1.7a")~>cells rexMatchp("^nch_\\|^pch_" cell~>name))~>name

; 查器件 CDF 默认参数和描述
cdfGetCellCDF(ddGetObj("CRN65LP_v1.7a" "nch_33"))~>parameters

; 查器件可用 view（symbol/schematic/spectre/layout...）
ddGetObj("CRN65LP_v1.7a" "nch_33")~>views~>name
```

**计划实现**：
```bash
# 列出 PDK 库中的器件
vbridge lib cells CRN65LP_v1.7a
vbridge lib cells CRN65LP_v1.7a --filter "nch_*"
vbridge lib cells CRN65LP_v1.7a --filter "nch_*" --json

# 查看器件属性
vbridge lib cell-info CRN65LP_v1.7a nch_33
# → nch_33 (3.3V nominal VT NMOS transistor)
#   Views: symbol, schematic, spectre, layout, ...
#   Defaults: W=400n L=380n fingers=1 simM=1

# 查看器件 CDF 全部参数
vbridge lib cell-info CRN65LP_v1.7a nch_33 --json

# 列出 cell 的 view
vbridge lib views my_osc osc
```

**实现方式**：在 `vbridge/sch_cmd.py` 中加 `run_cells`/`run_cell_info`/`run_views`，
内部通过 `vbridge exec` 执行上述 SKILL。不需要改上游代码。

### P2: 库详细信息

上游 `library/management.py` 有 `get_library()→LibraryInfo(name,path,tech_lib)`。

**计划**：
```bash
vbridge lib list --detail
# → cdsDefTechLib       /opt/Cadence/IC231/.../cdsDefTechLib
#   my_osc              /home/zhhe/work_ana/test_osc/my_osc
#   CRN65LP_v1.7a       /opt/PDK/TSMC_65nm/.../tsmcN65
```

`--detail` 加路径列和 tech-lib 信息。`--json` 返回完整 LibraryInfo。

### P3: Maestro 配置和仿真

上游 `maestro/` 模块已完整：
- `lifecycle.py`: `open_session`, `close_session`
- `writer.py`: `create_test`, `set_analysis`, `add_output`, `set_spec`, `set_var`, `set_corner`
- `reader/`: `read_results`, `export_waveform`
- `waveform_viewer.py`: `open_waveform_viewer`, `close_waveform_viewer`

当前通过 `vbridge snapshot` 和 `vbridge screenshot` 部分暴露。

**计划**（较大工作量，分阶段）：

阶段 1：
```bash
vbridge maestro open myLib myCell                    # 打开会话
vbridge maestro results                              # 读取最近结果
vbridge maestro export-wave "V(\"/VOUT\")" -o out.csv  # 导出波形
```

阶段 2：
```bash
vbridge maestro configure myLib myCell << 'EOF'
[{"op": "create-test", "test": "dc_check", ...},
 {"op": "set-analysis", "analysis": "dc", ...},
 {"op": "set-corner", "name": "tt"}]
EOF
vbridge maestro run
```

### P4: `sch netlist` 自动注入 PDK model

**现状**：`sch netlist` 生成的网表引用 `ade_e.scs`，独立运行需手动替换。

**计划**：
```bash
vbridge sch netlist myLib myCell -o ./nl --standalone
# 自动：
# 1. 从器件实例推导 PDK 库名
# 2. 从 cds.lib 查路径
# 3. 拼出 model include 路径
# 4. 替换 ade_e.scs 为实际 model include
# 5. 默认 section=tt_lib（可 --section 覆盖）
```

**实现**：后处理步骤，不需要改上游 netlister。
在 `vbridge/sch_cmd.py:run_netlist` 结束后加替换逻辑。

---

## 二、当前 patch 维护（上游修复）

`patches/0002-ic251-field-fixes.patch` 包含 3 个修复：

| 文件 | 改动 | 说明 |
|------|------|------|
| `bridge.py` | `_prepare_il_path` 加 `ssh_runner is not None` | `load` 本地模式 |
| `params.py` | 加 `_sync_w_wf()` 和 `_scale_eng()` | w↔wf 自动双向同步 |
| `cdf_param_filters.yaml` | 加 TSMC 65nm/40nm/GPDK 过滤规则 | `sch read` 文本模式不再过载 |

构建时 `pre-build` 自动应用，`post-build` 自动恢复上游。

---

## 三、vbridge 自有代码改进（直接修改，不需 patch）

### 已完成

- [x] `sch_cmd.py:run_read` — 文本模式只显示关键参数 + 网络连接表
- [x] `sch_cmd.py:_format_params_brief` — 智能参数摘要

### 计划（第一批已完成 2026-09-09）

- [x] `lib_cmd.py:run_cells` — `vbridge lib cells <lib> [--filter] [--json]`
- [x] `lib_cmd.py:run_cell_info` — `vbridge lib cell-info <lib> <cell> [--json]`
- [x] `lib_cmd.py:run_views` — `vbridge lib views <lib> <cell>`
- [x] `sch_cmd.py:run_netlist` — `--standalone` 自动检测 PDK model + 加默认分析
- [x] `cli.py` — 注册新子命令

---

## 四、不重复造轮子清单

以下功能上游已有完整实现，无需开发：

| 需求 | 上游解决方案 | 访问方式 |
|------|-------------|---------|
| 频率/电流测量 | `vbridge sim measure` | CLI ✓ |
| 进程清理 | `vbridge cleanup` | CLI ✓ |
| 截图 | `vbridge screenshot` | CLI ✓ |
| Maestro 快照 | `vbridge snapshot` | CLI ✓ |
| 网表生成 | `vbridge sch netlist` | CLI ✓ |
| PSF 解析 | `vbridge sim result --csv` | CLI ✓ |
| Symbol 生成 | `vbridge symbol generate` | CLI ✓ |
| GDS 导出 | `layout/streamout.py:export_gds()` | Python API |
| 网表导入原理图 | `schematic/netlist.py:import_netlist_schematic()` | Python API |
| 自动布局 | `schematic/planner.py:SchematicPlanner` | Python API |
| 并行仿真 | `spectre/runner.py:SpectrePool` | Python API |
| 参数扫描解析 | `spectre/parsers.py:parse_sweep_psf_directory()` | Python API |
| Maestro 配置 | `maestro/writer.py` 全套 | Python API |
| 波形窗口 | `maestro/waveform_viewer.py` | Python API |
| SKILL 文档查询 | `vbridge skill-find/skill-info` | CLI ✓（需 SKILL Finder 数据） |
| Profile 管理 | `vbridge profile show/bind/clear` | CLI ✓ |
| Visio 导出 | `vbridge export-visio` | CLI ✓ |

---

## 五、优先级排序

| 优先级 | 任务 | 工作量 | 依赖 |
|--------|------|--------|------|
| **P1** | PDK 器件查询 CLI（lib cells/cell-info/views） | 小（~100 行） | 无 |
| **P1** | `sch netlist --standalone` | 小（~50 行后处理） | 无 |
| **P1** | `lib list --detail` 显示路径 | 小（~30 行） | 无 |
| **P2** | Maestro 结果读取 CLI | 中（包装现有 API） | 需要 Maestro 仿真 history |
| **P2** | 波形导出 CLI | 中（包装 export_waveform） | 同上 |
| **P3** | Maestro 完整配置 CLI | 大（JSON batch 协议） | 需要完整测试 |
| **P3** | GDS 导出 CLI | 小（包装 export_gds） | 需要 layout view |

---

## 六、实施顺序

**第一批（✓ 已完成 2026-09-09）**：
1. ✓ `vbridge lib cells` — PDK 器件列表（支持 --filter 和 --json）
2. ✓ `vbridge lib cell-info` — 器件 CDF 属性（描述 + views + 默认参数）
3. ✓ `vbridge lib views` — cell view 列表
4. ✓ `vbridge sch netlist --standalone` — 自动检测 PDK model + 注入 include + 追加分析语句
5. ✓ `vbridge lib list --detail` — 列出库路径

全部通过验证：8 大类命令全功能测试通过。

**第二批（✓ 已完成 2026-09-09）**：
5. ✓ `vbridge maestro run` — 运行 Maestro 仿真
6. ✓ `vbridge maestro signals` — 列出可用信号（27 个信号）
7. ✓ `vbridge maestro export` — 导出波形到文件（自动查找 PSF 目录）

全部通过验证。

**第三批（部分完成 2026-09-09）**：
8. ✓ `vbridge maestro var` — 查看/设置设计变量
9. 待做: `vbridge maestro configure` — JSON batch 配置 test/analysis/corner（上游 writer.py 已有 API）
10. 待做: `vbridge maestro corner` — 查看/设置 corner 配置
