# 010 本地模式全面评估与 sim result 增强

日期: 2026-09-08

## 1. 本地模式命令安全评估

**根因**: 上游 `VirtuosoClient.from_env()` 即使对 `VB_REMOTE_HOST=localhost`
也会创建 SSHClient 实例作为 tunnel。任何通过 `tunnel.upload_text()`/`download_file()` 的操作
都会触发 `_require_deployment_runner()` → 本地模式下为 None → 抛 RuntimeError。

**vbridge 自有命令全部安全**: `exec`, `sch *`, `lib *`, `symbol *` 使用 `get_client()`
创建无 tunnel 的 VirtuosoClient（本地模式直连 daemon 端口）。

**上游命令评估结果** (通过 `upstream_dispatch` 分发的 20 个命令):

| 命令 | 本地模式 | 原因 |
|------|----------|------|
| init/start/stop/restart/status/license/profile | SAFE | 不使用 VirtuosoClient |
| eval | SAFE | 纯 TCP execute_skill |
| load | **FIXED** | `_load_with_local_fallback` 检测本地模式后直接发 SKILL `load()` |
| windows | SAFE | 纯 SKILL |
| screenshot | SAFE | 内部有 `if tunnel and ssh_runner` 守卫 |
| dismiss-dialog / dismiss-window / bootstrap | SAFE | 纯 SKILL / X11 本地操作 |
| skill-find / skill-info | SAFE | 内部有 `runner is not None` 守卫 |
| doc-search | SAFE | 本地模式使用本地文档根 |
| export-visio | SAFE | 纯 SKILL |
| snapshot | **PARTIAL** | 无 `-o` 时纯 SKILL 安全；`-o ROOT` 调用 `download_file` 会失败 |

**结论**: 本地模式下 27 个命令中 26 个安全，1 个部分安全（snapshot -o）。

## 2. sim result 增强

### 之前的问题

- 瞬态数据只显示 `[75652 points]`（字符串），无法提取实际数值
- `--signal ON --json` 只返回 DC 值，跳过瞬态
- 无法导出为 CSV 供外部工具处理
- 文件匹配遗漏 `tran1.tran.tran` 格式

### 修复内容

1. **`_find_analysis_files`**: 改进文件发现，同时匹配 `.tran` 后缀和含 `.tran` 的文件名
2. **`_summarize_signal`**: 概览显示 min/max 而非仅 `[N points]`
3. **`--signal ON --json`**: 返回完整数据数组 `{"ON": [2.95, 3.01, ...]}`
4. **`--json`** (无 signal): 返回每个信号的 points/min/max 结构化统计
5. **`--csv`**: 导出完整数据为 CSV 格式到 stdout

### 用法示例

```bash
# 概览（含 min/max）
vbridge sim result ./output.raw/
# → tran1.tran.tran:
#     time: [75652 pts] min=0  max=2e-06
#     ON:   [75652 pts] min=2.37  max=3.28

# 查询单信号（返回完整数组）
vbridge sim result ./output.raw/ --signal ON --json
# → {"ON": [2.956, 3.012, ...]}

# 统计概览
vbridge sim result ./output.raw/ --json
# → {"tran1.tran.tran": {"ON": {"points": 75652, "min": 2.37, "max": 3.28}, ...}}

# 导出 CSV
vbridge sim result ./output.raw/ --csv --signal ON > on_waveform.csv
# → time,ON
#    0.0,2.956933...
#    1.32e-11,2.957...
```
