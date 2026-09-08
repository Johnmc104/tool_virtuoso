# 009 IC251 复测反馈修复 (Round 2)

日期: 2026-09-08

## 已修复

### P5: `sch list` cell name 显示 `?`

**根因**: `run_list_instances` 取 `inst.get("cellName")`，但 `read_schematic` 返回的 key 是 `"cell"`。

**修复**: 改为 `inst.get("cell", "?")`。

### A1: `sch batch` 新增 `set-param` 操作

支持在批量编辑中直接设置实例 CDF 参数，无需写 .il 脚本：

```json
{"op": "set-param", "inst": "M3", "params": {"w": "1600n", "l": "1520n", "ad": "3.68e-13"}}
```

- 使用 IC251 兼容 API (`cdfGetInstCDF` + `cdfFindParamByName`)
- 设置 `w` 时自动同步 `wf`
- 支持任意 CDF 参数（W/L/nf/寄生参数等）

### A2: Skill 文档更新

在 `tool-virtuoso-bridge` skill 中添加：
- `set-param` op 文档
- `schCreateWireLabel` vs `label-mos` 行为差异警告

## 未处理（留待后续）

| 项目 | 优先级 | 说明 |
|---|---|---|
| D1 波形可视化 | P0 | 需要 PSF 解析 + matplotlib/plotly 或 ASCII art |
| C1 PSF 解析 CLI | P0 | `sim result` 已有基础框架，需增强 |
| B1 网表生成 | P1 | 封装 OCEAN 或上游 SchematicOps.export_netlist |
| B2/B3 仿真参数化 | P2 | 设计变量 / IC 传入机制 |
| E1 进程清理 | P2 | `vbridge cleanup` 命令 |
