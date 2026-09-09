# 017 vbridge IC251 实测轮次总结

> 测试项目：test_osc（TSMC 65nm 差分环形 VCO）
> 测试周期：2026-09-08 ~ 2026-09-09
> 测试环境：vbridge + IC25.1-64b + Spectre 25.1.0.417, 本地模式

---

## 一、测试轮次

| 轮次 | 内容 | 文档 |
|------|------|------|
| 1 | 原理图修复（VBN 连线 + bias_k4 参数） | 007 |
| 2 | 仿真验证（OCEAN + standalone） | 008, 009 |
| 3 | 上游能力审计 + 功能开发 | 010, 012 |
| 4 | CLI 命令规范化 + help 优化 | 011 |
| 5 | 场景覆盖度评估 + 补全 | 012, 013 |
| 6 | 仿真控制 + AC 测量 + 波形可视化 | 014, 015 |
| 7 | 原理图损坏事件 + 修复 + 安全防护 | 016 |

---

## 二、开发成果

### 新增 CLI 命令（14 个）

| 命令 | 功能 |
|------|------|
| `lib cells [--filter]` | PDK 器件列表 |
| `lib cell-info` | 器件 CDF 属性 |
| `lib views` | cell view 列表 |
| `lib list --detail` | 库路径显示 |
| `sch netlist --standalone` | 自动注入 PDK model + 默认分析 |
| `maestro run` | 运行 Maestro 仿真 |
| `maestro signals` | 列出仿真信号 |
| `maestro export` | 导出波形到文件 |
| `maestro var` | 查看/设置设计变量 |
| `sim plot` | 波形可视化（HTML/PNG，多信号叠加） |
| `sim measure gain` | AC 增益 (dB) |
| `sim measure bw` | -3dB 带宽 |
| `sim measure ugf/pm` | 0dB 频率 + 相位裕度 |
| `sim measure thd` | PSS 总谐波失真 |

### 新增 batch op（3 个）

| op | 功能 |
|----|------|
| `delete-inst` | 删除实例 |
| `move-inst` | 移动实例 |
| `copy-inst` | 复制实例（含参数） |

### 修复（9 个）

| 修复 | 方式 |
|------|------|
| `load` 本地模式 | patch: bridge.py ssh_runner guard |
| w↔wf 自动同步 | patch: params.py `_sync_w_wf()` |
| `sch read` 参数过载 | patch: cdf_param_filters.yaml + sch_cmd.py |
| `sim run` license 误报 | patch: runner.py 精确匹配 |
| `screenshot` 本地模式路径 | patch: bridge.py 本地路径 |
| `add-inst` view 默认值 | sch_cmd.py: "schematic" → "symbol" |
| `sch create`/`save` API 不匹配 | sch_cmd.py: 改用 SKILL |
| `symbol generate --overwrite` | symbol_cmd.py: `.action` 不加 `.value` |
| `skill-find` 路径检测 | cli.py: 自动从 daemon 检测 Cadence 安装路径 |

### 安全功能（2 个）

| 功能 | 说明 |
|------|------|
| `sch batch --dry-run` | 预览操作内容，不执行 |
| `sch create --force` | 已有 cell 默认拒绝覆盖 |

### 命名规范化

| 项 | 改动 |
|----|------|
| batch op | `connect`（替代 wire）、`orientation`/`direction`（统一） |
| CLI prog | 全层级递归替换为 `vbridge` |
| help text | 全部参数有描述 + 示例值 |
| sim measure | 参数名 `type`，epilog 按分析类型分组 |
| 子命令分组 | sch: read/edit/export, sim: run/results/other |

### 上游 patch（1 文件 5 个修复）

`patches/0002-ic251-field-fixes.patch`（161 行）：
- `runner.py`: license 误报精确匹配
- `bridge.py`: load 本地模式 + screenshot 本地路径
- `params.py`: w↔wf 自动同步
- `cdf_param_filters.yaml`: TSMC 65nm/40nm/GPDK 过滤规则

---

## 三、场景覆盖度

| 角色 | 初始 → 最终 |
|------|:-----------:|
| 原理图设计 | 60% → **95%** |
| 仿真工程 | 75% → **95%** |
| PDK/库管理 | 90% → **95%** |
| 项目审查 | 85% → **85%** |
| 自动化/CI | 80% → **85%** |

---

## 四、验证过的工作流

### 完整无 GUI 链路

```
vbridge sch read → sch batch/param → sch netlist --standalone → sim run → sim measure/plot
```

### 实际设计验证（test_osc）

| 分析 | 结果 |
|------|------|
| 5-corner 频率扫描 | 全部起振，f0 = 1.83~2.99 GHz |
| 温度扫描 (-40~125°C) | TC ≈ -4.7 MHz/°C |
| PSS + Pnoise | THD=9.95%, 6 频偏点噪声数据 |
| AC 测量验证 | RC 低通: gain=0dB, bw=1.59MHz（匹配理论值） |

### 发现并修复的设计问题

| 问题 | 发现方式 | 修复 |
|------|---------|------|
| VBN 偏置断开 | `sch read --json` 网络拓扑检查 | `label-mos` M3/M11 drain=VBN |
| M8 连接被破坏 | 逐器件网表对比 | `delete-inst` + `add-inst` 重建 |

---

## 五、已知限制

| 限制 | 说明 | workaround |
|------|------|-----------|
| screenshot Xvfb | 虚拟显示下 hiWindowSaveImage 不生成图片 | 使用 `sim plot` 代替 |
| Spectre notice 被收为 error | IC 精度提示在 errors 列表中 | 以 status 字段判断 |
| daemon 不自动退出 | 持续占用 license | `vbridge cleanup` 手动清理 |
| OA 缓存无法 API 清除 | 磁盘恢复对运行中 daemon 无效 | 在 daemon 内用 SKILL 修复 |

---

## 六、文档索引

| 文档 | 内容 | 状态 |
|------|------|------|
| 007 | IC251 首轮实测问题 | 历史 |
| 008 | 需求文档 | 大部分已解决 |
| 009 | 端到端评估 | 历史 |
| 010 | 开发计划 | 三批全部完成 |
| 011 | CLI help 审计 | 完成 |
| 012 | 场景覆盖度审计 | **核心参考** |
| 013 | 原理图操作补全 | 完成 |
| 014 | 仿真控制计划 | 完成 |
| 015 | 最终评估 | **核心参考** |
| 016 | 稳健性评估 | **核心参考** |
| **017** | **本轮总结** | **当前文档** |
| SKILL.md | Agent 使用指南 | **实时更新** |
