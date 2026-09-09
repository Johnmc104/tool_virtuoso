# vbridge — Virtuoso Bridge CLI

无 GUI 操控 Cadence Virtuoso：原理图编辑、仿真运行、结果测量、版图操作、PDK 查询。

## 安装

```bash
tar xzf virtuoso-bridge-*-linux-x86_64.tar.gz -C /opt/vtool/
export PATH="/opt/vtool/bin:$PATH"
```

## 快速开始

```bash
vbridge init localhost                                    # 初始化
vbridge auto-start                                        # 启动
vbridge -V                                                # 查版本
vbridge -h                                                # 查所有命令
```

## 功能概览

### 原理图

```bash
vbridge sch read myLib myCell --json                      # 读拓扑（instances + nets + pins）
vbridge sch param myLib myCell M0 w 2u                    # 改参数（auto w/wf sync）
vbridge sch batch myLib myCell < ops.json                 # 批量操作（--dry-run 预览）
vbridge sch netlist myLib myCell -o ./nl --standalone      # 导出 Spectre 网表
vbridge sch create myLib myCell                           # 创建 cell（--force 覆盖）
vbridge symbol generate myLib myCell                      # 生成 symbol
```

batch op 类型：`add-inst`, `delete-inst`, `move-inst`, `copy-inst`, `connect`, `label-mos`, `label-term`, `set-param`, `add-pin`

### 仿真

```bash
vbridge sim run input.scs -o ./raw --mode aps             # 运行 Spectre
vbridge sim result ./raw/                                 # 结果概览（DC + tran min/max）
vbridge sim result ./raw/ --csv --signal ON               # 导出 CSV
vbridge sim measure ./raw/ freq ON --from 1e-6            # 频率（1.85e9）
vbridge sim measure ./raw/ gain out                       # AC 增益 (dB)
vbridge sim measure ./raw/ bw out                         # -3dB 带宽 (Hz)
vbridge sim measure ./raw/ thd ON                         # PSS THD (%)
vbridge sim plot ./raw/ ON,OP -o wave.html                # 波形图（HTML/PNG）
```

### Maestro

```bash
vbridge maestro run myLib myCell                          # 运行 Maestro 仿真
vbridge maestro signals myLib myCell                      # 列出信号
vbridge maestro export myLib myCell ON -o wave.txt        # 导出波形
vbridge maestro var myLib myCell                          # 查看设计变量
```

### 版图

```bash
vbridge layout read myLib myCell                          # 版图摘要
vbridge layout layers myLib myCell                        # 列出 layer/purpose
vbridge layout export-gds myLib myCell -o out.gds         # GDS 导出
vbridge layout batch myLib myCell < ops.json              # 批量操作（--dry-run）
```

### 库管理

```bash
vbridge lib list --detail                                 # 列出库 + 路径
vbridge lib create myLib --path /path --tech-lib PDK      # 创建库
vbridge lib cells CRN65LP_v1.7a --filter "nch_*"          # PDK 器件列表
vbridge lib cell-info CRN65LP_v1.7a nch_33                # 器件属性
```

### SKILL

```bash
vbridge exec "expression"                                 # 执行 SKILL
vbridge load script.il                                    # 加载 .il 文件
vbridge skill-find dbOpen                                 # 搜索 SKILL API 文档
```

### 工具

```bash
vbridge status                                            # 检查连接
vbridge cleanup --dry-run                                 # 清理残留进程 + 锁文件
vbridge screenshot ciw -o shot.png                        # 截图
```

## 构建

```bash
make build-local   # 本地构建
make build         # Docker 构建（CentOS 7 兼容）
make package       # 打包 tar.gz
```

## 架构

```
vbridge              CLI 入口（扩展命令 + 安全功能）
  ├── sch_cmd        原理图操作（read/batch/param/netlist/create）
  ├── sim_cmd        仿真控制（run/result/measure）
  ├── plot_cmd       波形可视化（HTML/PNG）
  ├── layout_cmd     版图操作（read/batch/layers/export-gds）
  ├── maestro_cmd    Maestro 集成（run/signals/export/var）
  ├── lib_cmd        库管理（list/create/cells/cell-info/views）
  └── cleanup_cmd    进程清理

virtuoso-bridge-lite  上游 Python 库（submodule）
patches/              上游修复（IC251 兼容 + 功能增强）
```
