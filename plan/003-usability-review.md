# 003 可用性审查：vbridge 适配层问题与优化建议

日期: 2026-09-08

## 1. 审查范围

对 vbridge/ 下全部 10 个文件（995 行）进行可用性、简洁性和工程场景便利性审查，
结合上游 v0.8.0 的能力变化评估每个组件的当前价值。

## 2. 发现清单

### 2.1 [HIGH] auto_start.py 状态文件路径过期

**问题**: `STATE_DIR` 硬编码 `~/.cache/virtuoso_bridge/state.json`，
但上游 v0.8.0 已迁移到 `~/.local/state/virtuoso_bridge/state.json` (XDG_STATE_HOME)。
上游 `read_state()` 会检查 primary + legacy 两个路径，但我们的 `_read_state()`
只检查 legacy 路径。

**影响**: 在全新安装环境下，upstream `start` 写入新路径，但 `auto-start`
读不到状态，导致：
- 误判为未启动，触发重复 `virtuoso-bridge start`
- `_get_port()` 回退到环境变量默认值，可能端口不匹配
- `_get_setup_path()` 返回 None，强制重新生成 setup.il

**修复**: 使用上游的 `SSHClient.read_state()` 替换自有 `_read_state()`，
或导入 `runtime_paths.state_dir` 构造正确路径。

### 2.2 [HIGH] sch_cmd.py 调用了不存在的方法

**问题**: `_dispatch_op` 中 7 个操作类型有 6 个调用了 `SchematicEditor`
上不存在的方法：

| 操作 | 调用的方法 | 实际是否存在 |
|---|---|---|
| `add-inst` | `sch.add_instance()` | **不存在** |
| `wire` | `sch.add_wire_between_instance_terms()` | **不存在** |
| `label-term` | `sch.add_net_label_to_instance_term()` | **不存在** |
| `label-mos` | `sch.add_net_label_to_transistor()` | 存在 |
| `add-pin` | `sch.add_pin()` | **不存在** |
| `add-wire` | `sch.add_wire()` | **不存在** |
| `add-label` | `sch.add_label()` | **不存在** |

`SchematicEditor` 仅有 `add(skill_cmd_str)` 和 `add_net_label_to_transistor()` 两个方法。

**影响**: 除 `label-mos` 外，所有批量原理图操作在运行时会抛出 `AttributeError`。
`vbridge sch batch` 命令实际不可用。

**修复选项**:
- A) 用 `sch.add(skill_cmd)` 重写，构造对应 SKILL 命令字符串
- B) 利用上游 `schematic/ops.py` 中的独立函数（如 `schematic_create_inst_by_master_name`）
- C) 暂时移除不可用的操作，只保留 `label-mos`，标注 TODO

### 2.3 [MEDIUM] `_ensure_setup_il` 缺少 RB_IDENTITY_PATH

**问题**: `auto_start.py:_ensure_setup_il()` 生成的 `virtuoso_setup.il` 不包含
上游 v0.8.0 新增的 `RB_IDENTITY_PATH` 环境变量设置。

**影响**: split-host 环境下 daemon identity 诊断不可用。功能缺失但不导致崩溃。

**修复**: 在生成的 setup.il 内容中加入 `setShellEnvVar("RB_IDENTITY_PATH" "...")` 行。

### 2.4 [MEDIUM] env_helpers.py 与上游 load_vb_env 功能重叠

**问题**: `load_env_robust()` 实现了简化版的 .env 查找逻辑（CWD → ~/.virtuoso-bridge/），
而上游 `load_vb_env()` 提供了更完善的版本：

| 能力 | `load_env_robust` | 上游 `load_vb_env` |
|---|---|---|
| CWD .env | 直接使用 | 检查含 VB_* 键才使用 |
| 向上遍历目录 | 不支持 | 支持 |
| 识别 VB 配置 | 不识别 | 按 VB_* 键过滤 |
| split-host 键 | 不识别 | 识别新的 VB_DAEMON_HOST 等 |
| 显式 --env | 不支持 | 支持 |

**影响**: 在项目子目录运行 vbridge exec/sch 时，可能加载到错误的 .env 文件。

**修复**: 将 `load_env_robust()` 替换为上游的 `load_vb_env()` 调用。
`get_client()` 保留（它处理 frozen binary 和 local mode 的客户端创建逻辑，
上游 `VirtuosoClient.from_env()` 现在也涵盖了这些场景，但 `wait_bridge_ready`
集成仍有价值）。

### 2.5 [MEDIUM] exec_cmd.py 表达式包装弱于上游

**问题**: `exec_cmd.py` 对表达式仅添加 `"\n" + expression` 前缀来触发多行路径。
上游 `eval` 使用 `progn(\n{skill}\n)` 包装。

**影响**:
- 多语句表达式（`printf(...) "ret"`）只返回最后一个形式的结果
- 尾部 `;` 注释可能吞掉闭括号

**修复**: 采用上游的 `progn()` 包装方式。

### 2.6 [MEDIUM] _run_bridge_start 使用子进程而非直接调用

**问题**: `auto_start.py:_run_bridge_start()` 通过 `subprocess.run([bridge, "start"])`
调用 `virtuoso-bridge start`。但 vbridge 进程已经导入了 `_patched_cli_start()`，
可以直接调用。

**影响**:
- 增加了对二进制文件发现的依赖（`_find_vbridge_bin()` 可能找不到）
- 子进程开销（启动时间 + 环境继承）
- 出错信息被子进程吞掉

**修复**: 替换为直接调用 `_patched_cli_start()`，仅在需要环境隔离时保留子进程路径。

### 2.7 [LOW] load_cmd.py 已成为死代码

**问题**: 上游 v0.8.0 合入后，`cli.py` 中 `load` 命令已路由到上游 `cli_load`，
`load_cmd.py` 不再被任何代码导入或调用。

**影响**: 无功能影响，仅增加维护认知负担。

**修复**: 删除 `vbridge/load_cmd.py`。

### 2.8 [LOW] _resource_patch.py 从未被调用

**问题**: `patch_resource_finders()` 已定义但整个项目中无任何调用点。
Git 历史显示它从初始提交就存在但从未被接入。

**影响**: 52 行死代码。

**修复**: 删除 `vbridge/_resource_patch.py`，或在 `entry_vbridge.py` 中
调用以实际启用 frozen binary 资源路径修补。

### 2.9 [LOW] run_list_instances 使用内联 SKILL 而非上游 API

**问题**: `sch_cmd.py:run_list_instances()` 手写了 ~15 行 SKILL 查询实例列表。
上游 `schematic/reader.py` 提供 `read_schematic()` 返回结构化字典，
包含 instances、nets、pins 等完整信息。

**影响**: 内联 SKILL 脆弱，不处理边缘情况（无 xy 的实例、特殊字符名称），
且输出格式固定不可扩展。

**修复**: 用 `schematic.reader.read_schematic()` 替换，格式化输出结构化结果。

### 2.10 [LOW] quickstart.md 未覆盖新命令

**问题**: 文档仍基于 v0.7.0 功能集，未提及：
- `vbridge eval` / `vbridge load` (上游原生版本)
- `vbridge skill-find` / `vbridge skill-info`
- `vbridge profile` 管理
- `vbridge bootstrap` 引导
- split-host 配置

**影响**: 用户不知道新增能力的存在。

## 3. exec vs eval 共存分析

| 维度 | `vbridge exec` | 上游 `eval` |
|---|---|---|
| 输出格式 | 纯文本（shell 友好） | 完整 JSON（结构化） |
| stdin 触发 | 省略参数或 `-` | 需显式 `--stdin` |
| 桥接等待 | `wait_bridge_ready` 30s | 无（连接失败则报错） |
| 表达式包装 | `\n` + expr（弱） | `progn(\n...\n)`（强） |
| JSON 模式 | `--json`（4 字段） | 默认 JSON（完整模型） |
| 静默模式 | 无 | `--quiet` |
| 退出码 | 0/1 | 0/1/2 |

**结论**: `exec` 对 auto-start 工作流有不可替代的价值（wait_bridge_ready），
且纯文本输出更适合 shell 脚本集成。保留但修复表达式包装。

## 4. 优化优先级建议

### Phase 1: 修复阻塞性问题（必须）

| # | 问题 | 修改文件 | 工作量 |
|---|---|---|---|
| 1 | 状态文件路径过期 | auto_start.py | 小 |
| 2 | sch_cmd 方法不存在 | sch_cmd.py | 中 |

### Phase 2: 与上游对齐（推荐）

| # | 问题 | 修改文件 | 工作量 |
|---|---|---|---|
| 3 | setup.il 缺少 IDENTITY_PATH | auto_start.py | 小 |
| 4 | env_helpers 替换为上游 | env_helpers.py | 小 |
| 5 | exec 表达式包装 | exec_cmd.py | 小 |
| 6 | _run_bridge_start 直接调用 | auto_start.py | 小 |

### Phase 3: 清理（可选）

| # | 问题 | 修改文件 | 工作量 |
|---|---|---|---|
| 7 | 删除 load_cmd.py | load_cmd.py | 微 |
| 8 | 删除 _resource_patch.py | _resource_patch.py | 微 |
| 9 | list_instances 用上游 API | sch_cmd.py | 小 |
| 10 | 更新 quickstart.md | docs/quickstart.md | 中 |

## 5. 架构层面观察

vbridge 适配层当前 995 行代码，其中：
- **有效代码**: ~700 行（cli.py, auto_start.py, exec_cmd.py, sch_cmd.py, _frozen_patches.py, _display.py）
- **死代码**: ~87 行（load_cmd.py, _resource_patch.py）
- **可上游化**: ~57 行（env_helpers.py 的 load_env_robust 已被上游 load_vb_env 覆盖）

随着上游 v0.8.0 持续吸收 CLI 功能（eval/load/profile/bootstrap/skill-find 等），
vbridge 的独有价值集中在三个方面：

1. **auto-start 编排** — 一键启动 bridge + Virtuoso + daemon 等待
2. **PyInstaller 冻结适配** — setup.il 路径修补 + daemon 内嵌执行
3. **exec + wait_bridge_ready** — auto-start 友好的 SKILL 执行

`sch` 命令目前不可用（方法不存在），需要重写或移除。
