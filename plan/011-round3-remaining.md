# 011 第三轮实施：剩余功能项

日期: 2026-09-08

## 状态回顾

已完成: P1-P5 修复, A1 set-param, C1 PSF 解析增强 (CSV/min-max), P3 load 本地模式, 上游 CDF callback 集成。

## 本轮实施

### 1. `vbridge sch netlist` — 网表生成 (B1)

上游 `SchematicOps.export_netlist(lib, cell, output_dir)` 通过 Virtuoso netlister
生成 Spectre 网表，自动下载到本地。封装为 CLI 命令。

### 2. `vbridge sim measure` — 内建测量

从 PSF 数据中直接计算常用指标，避免用户每次写 Python。

子命令: `freq`, `avg`, `rms`, `minmax`, `cross`

### 3. 修正 skill 文档

`set-param` 现在使用上游 `_run_batched_param_update`，触发 CDF callbacks。
skill 文档中的"不触发 callback"警告已过时。

### 4. `vbridge cleanup` — 进程清理 (E1)

清理残留 Cadence 进程 + OA lock 文件。
