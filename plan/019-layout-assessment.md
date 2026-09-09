# 019 Layout 能力评估

## 上游已有的 API

### Layout 编辑（25 个 SKILL 函数 + LayoutEditor 上下文管理）

| 类别 | 函数 | 功能 |
|------|------|------|
| 实例 | `layout_create_param_inst` | 放置参数化器件 |
| | `layout_create_simple_mosaic` | 阵列放置 |
| 几何 | `layout_create_rect` | 画矩形 |
| | `layout_create_path` | 画路径（走线） |
| | `layout_create_polygon` | 画多边形 |
| | `layout_create_label` | 加标签 |
| | `layout_create_via` / `via_by_name` | 加 via |
| 查询 | `layout_read_geometry` | 读取几何数据 |
| | `layout_read_summary` | 读取摘要（实例数、形状数） |
| | `layout_list_shapes` | 列出指定层的形状 |
| | `layout_highlight_net` | 高亮 net |
| 图层 | `layout_set_active_lpp` | 设置当前图层 |
| | `layout_show/hide/show_only_layers` | 图层可见性 |
| 清理 | `layout_delete_cell` | 删除 cell |
| | `layout_delete_selected` | 删除选中对象 |
| | `layout_delete_shapes_on_layer` | 删除指定层形状 |
| | `layout_clear_routing` | 清除布线 |
| 视图 | `layout_fit_view` | 适配视图 |
| | `layout_select_box` | 选择框 |

### GDS 导出

| 函数 | 功能 |
|------|------|
| `client.layout.export_gds()` | 完整 GDS-II Stream-out（支持远程） |
| `xstream_export_gds_skill()` | XStream GDS 导出 SKILL 生成 |

### Layout 编辑器

```python
with client.layout.modify("myLib", "myCell") as lay:
    lay.add(layout_create_rect("M1", 0, 0, 10, 0.5))
    lay.add(layout_create_path("M2", [(0,0),(10,0),(10,5)], width=0.1))
    lay.add(layout_create_via_by_name("M1_M2", 5, 0.25))
```

## 当前 CLI 状态

**零覆盖**——没有任何 layout CLI 命令。

## 评估：是否需要 layout CLI？

### 模拟设计 vs 数字设计的 layout 需求

| 维度 | 模拟 layout | 数字 layout |
|------|------------|------------|
| 自动化程度 | 低（手工为主） | 高（PnR 工具） |
| Agent 适用性 | △ 有限 | ✗ 不适用 |
| 核心操作 | 放器件、画连线、加 via | PnR 工具完成 |
| 查询需求 | DRC/LVS 结果、几何信息 | 时序报告 |

### 对 Agent 有价值的 layout 操作

| 操作 | 价值 | 理由 |
|------|------|------|
| 读取 layout 信息 | **高** | 检查器件放置、面积、层数 |
| GDS 导出 | **高** | 后端流程交接 |
| 简单器件放置 | 中 | 自动生成简单版图（电阻、电容阵列） |
| DRC/LVS 查询 | **高** | 验证结果自动化 |
| 手动画走线 | 低 | 模拟 layout 走线需要人工判断 |

## 建议的 CLI 实现

### P1（高价值、小工作量）

```bash
# 读取 layout 信息
vbridge layout read LIB CELL               # 摘要：实例数、形状数、面积
vbridge layout read LIB CELL --json        # 完整几何数据

# GDS 导出
vbridge layout export-gds LIB CELL -o output.gds
```

### P2（中等价值）

```bash
# 批量操作（类似 sch batch）
echo '[
  {"op":"add-rect","layer":"M1","x1":0,"y1":0,"x2":10,"y2":0.5},
  {"op":"add-via","via":"M1_M2","x":5,"y":0.25},
  {"op":"add-label","layer":"M1","text":"VDD","x":5,"y":0.25}
]' | vbridge layout batch LIB CELL

# 图层管理
vbridge layout layers LIB CELL              # 列出使用的图层
```

### 不做

| 操作 | 理由 |
|------|------|
| 交互式走线 | 需要人工路径规划 |
| 自动布局布线 | 需要约束和规则引擎 |
| DRC/LVS 运行 | 需要 Calibre/PVS 集成 |

## 工作量估算

| 命令 | 实现方式 | 工作量 |
|------|---------|--------|
| `layout read` | 包装 `layout_read_summary` + `read_geometry` | ~40 行 |
| `layout export-gds` | 包装 `client.layout.export_gds()` | ~30 行 |
| `layout batch` | 类似 `sch batch`，dispatch layout ops | ~80 行 |
| CLI 注册 | cli.py 加子命令 | ~40 行 |
| **合计** | | **~190 行** |
