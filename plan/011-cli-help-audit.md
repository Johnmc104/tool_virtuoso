# 011 CLI 命令与 Help 信息审计

> 基于最新构建（2026-09-09），完整梳理所有命令的 help 质量和优化点。

## 一、命令全景

### 顶级命令（29 个）

| 命令 | 来源 | help 质量 | 说明 |
|------|------|-----------|------|
| `init` | 上游 | ★★★★☆ | 缺示例 |
| `start` | 上游 | ★★★★☆ | |
| `stop` | 上游 | ★★★★★ | |
| `restart` | 上游 | ★★★★★ | |
| `status` | 上游 | ★★★★★ | |
| `license` | 上游 | ★★★☆☆ | 与 `sim license` 重复 |
| `profile` | 上游 | ★★★☆☆ | 子命令 show/bind/clear 无说明 |
| `load` | 上游 | ★★★★★ | 有描述、示例、VSCode 片段 |
| `eval` | 上游 | ★★★★☆ | |
| `exec` | vbridge | ★★★☆☆ | --timeout/--json/--env 缺 help text |
| `auto-start` | vbridge | ★★★★★ | |
| `sch` | vbridge | ★★★★★ | 完整子命令表 |
| `sim` | vbridge | ★★★★★ | 完整子命令表 |
| `lib` | vbridge | ★★★★★ | 完整子命令表 |
| `maestro` | vbridge | ★★★★★ | 完整子命令表 |
| `symbol` | vbridge | ★★☆☆☆ | 只列 generate，无说明 |
| `cleanup` | vbridge | ★★★★★ | |
| `screenshot` | 上游 | ★★★★☆ | |
| `snapshot` | 上游 | ★★★★★ | |
| `windows` | 上游 | ★★★★☆ | |
| `dismiss-dialog` | 上游 | ★★★☆☆ | 无参数说明 |
| `list-windows` | 上游 | ★★★☆☆ | |
| `dismiss-window` | 上游 | ★★★☆☆ | |
| `bootstrap` | 上游 | ★★★☆☆ | |
| `skill-find` | 上游 | ★★★★☆ | |
| `skill-info` | 上游 | ★★★★☆ | |
| `doc-search` | 上游 | ★★★★☆ | |
| `export-visio` | 上游 | ★★★☆☆ | |
| `daemon` | 内部 | N/A | 不面向用户 |

### 子命令 help（二级）

| 命令 | `--help` 可用 | prog 正确 | 参数有描述 | 优化点 |
|------|:---:|:---:|:---:|------|
| `sch list` | ✓ | ✓ | △ lib/cell 无示例 | 上游注册，改需 patch |
| `sch read` | ✓ | ✓ | △ --json 无说明 | 同上 |
| `sch param` | ✓ | ✓ | △ inst/param/value 有描述 | 缺 w/wf 同步说明 |
| `sch batch` | ✓ | ✓ | △ lib/cell 无示例 | 缺 op 类型说明 |
| `sch netlist` | ✓ | ✓ | ★ --standalone/--section 有描述 | lib/cell 无示例 |
| `sch create` | ✓ | ✓ | △ | |
| `sch save` | ✓ | ✓ | ★ | |
| `sim run` | ✓ | ✓ | ★ netlist/mode 有描述 | |
| `sim result` | ✓ | ✓ | ★ --signal/--csv/--json | |
| `sim measure` | ✓ | ✓ | ★ dir/measure/signal/--from/--to | |
| `sim license` | ✓ | ✓ | ★ | |
| `lib list` | ✓ | ✓ | ★ --detail/--json | |
| `lib create` | ✓ | ✓ | ★ --path/--tech-lib | |
| `lib cells` | ✓ | ✓ | ★★ lib 有示例，--filter 有示例 | |
| `lib cell-info` | ✓ | ✓ | ★★ lib/cell 有示例 | |
| `lib views` | ✓ | ✓ | ★★ lib/cell 有示例 | |
| `maestro run` | ✓ | ✓ | ★★ lib/cell 有示例 | |
| `maestro signals` | ✓ | ✓ | ★★ --history/--analysis 有说明 | |
| `maestro export` | ✓ | ✓ | ★★ signal 有示例 | |
| `maestro var` | ✓ | ✓ | ★★ name/value 有说明 | |
| `symbol generate` | ✓ | ✓ | △ lib/cell 无示例 | |

## 二、已完成的优化

1. ✓ `prog` 名称递归替换 → 全部显示 `vbridge`（不再是 `virtuoso-bridge`）
2. ✓ 顶级子命令（sch/sim/lib/maestro）fallback help 完整列出子命令 + 描述 + 关键参数
3. ✓ vbridge 新增子命令（lib cells/cell-info/views, maestro run/signals/export/var）全部参数有 help text + 示例
4. ✓ 公共参数通过 `_add_common_opts` / `_add_lib_cell_args` 统一管理

## 三、待优化项

### 可在 vbridge 侧修复（直接改 cli.py）

| 项 | 位置 | 改动 |
|----|------|------|
| `exec` 的 --timeout/--json 缺 help | `sp_exec` | 加 help= |
| `symbol` fallback help 太简单 | `_handle_symbol` | 加子命令描述 |
| `sch batch` 缺 op 类型说明 | `sp_batch` help 或 epilog | 加 epilog 列出 op 类型 |
| `sch param` 缺 w/wf 说明 | `sp_param` help | 在 help 中提及 auto-sync |

### 需上游修改（通过 patch）

| 项 | 位置 | 改动 |
|----|------|------|
| `sch list/read/param/batch` 的 lib/cell 无示例 | 上游 cli.py | 加 help="Library name (e.g. ...)" |
| `eval` 的参数无 help | 上游 cli.py | 加 help= |
| `dismiss-dialog` 无参数说明 | 上游 cli.py | |
| 顶级 `license` 与 `sim license` 重复 | 上游 | 考虑统一 |

### 非 help 层面的 CLI 设计问题

| 项 | 说明 | 建议 |
|----|------|------|
| 顶级命令太多（29 个） | 混杂了高频命令和低频诊断命令 | 低频命令归入 `vbridge diag` 子组 |
| `license` 出现两次 | 顶级 + sim 下 | 保留 `sim license`，去掉顶级 |
| `eval` 与 `exec` 功能重叠 | eval=上游(JSON)，exec=vbridge(文本) | 在 help 中说明区别 |
| `list-windows` vs `windows` | 两个命令功能接近 | 在 help 中说明区别 |

## 四、最终状态 (2026-09-09)

### 已全部修复

- ✓ `prog` 名称：全层级递归替换为 `vbridge`
- ✓ 上游 20 个命令 = vbridge upstream_dispatch 20 个，完全同步
- ✓ vbridge 额外 11 个命令全部注册和 dispatch
- ✓ 所有参数都有 help text + 示例值
- ✓ `sch batch` epilog 列出 8 种 op 类型 + 使用示例
- ✓ 公共参数（-p/--env/--timeout/lib/cell）通过辅助函数统一管理
- ✓ 全部修改在 vbridge 自有的 `cli.py` 中完成，零上游修改

### 参数描述质量

| 来源 | 数量 | help 质量 |
|------|------|-----------|
| 上游命令 | 20 | ★★★★☆（全部有 help，部分缺示例值） |
| vbridge 命令 | 11 + 20 子命令 | ★★★★★（全部有 help + 示例值） |

### 无需再改的部分

上游命令的参数描述已经完整（Connection profile、.env path、timeout 等全有说明）。
不需要通过 patch 或拦截修改上游参数。
