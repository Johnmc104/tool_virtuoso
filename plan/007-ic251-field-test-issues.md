# 007 IC251 实际使用测试反馈

## 测试场景

在 `test_osc` 项目中使用 vbridge + IC251 修改差分环振原理图：
1. 用 `label-mos` 修复 net14→VBN 缺失连线
2. 用 SKILL 批量修改 16 个 MOS 的 W/L 及寄生参数（bias_k4 优化）
3. 通过 OCEAN 生成网表并用 Spectre 251 仿真验证

测试日期：2026-09-08

## 问题清单

### P1: `vbridge sch list` PyInstaller 打包缺数据文件

**现象**：
```
FileNotFoundError: [Errno 2] No such file or directory:
  '/tmp/_MEInPxMUv/virtuoso_bridge/virtuoso/schematic/cdf_param_filters.yaml'
```

**原因**：`reader.py` 用 `Path(__file__).parent / "cdf_param_filters.yaml"` 定位数据文件。
PyInstaller `--onefile` 模式下，`__file__` 指向临时解压目录，yaml 文件未被打包进去。

`packaging.yaml` 里有 `collect_all: [virtuoso_bridge]`，理论上应该收集所有数据文件，
但实际未生效。可能是 `collect_all` 无法识别 `.yaml` 文件，或路径嵌套过深。

**影响**：`vbridge sch list`、`vbridge sch read` 不可用。

**建议修复**：在 PyInstaller spec 中显式添加 `datas` 项：
```python
datas=[('virtuoso_bridge/virtuoso/schematic/cdf_param_filters.yaml',
        'virtuoso_bridge/virtuoso/schematic/')]
```
或在 `reader.py` 中加 PyInstaller 兼容路径检测（`sys._MEIPASS`）。

### P2: `vbridge sch param` 依赖不存在的 `cdfSetInstParam`

**现象**：
```
[sch] error:
  ("load" 0 t nil ("*Error* load: error while loading file ..."))
```

**原因**：`sch_cmd.py:run_param()` 生成的 SKILL 使用 `cdfSetInstParam()` 和
`dbFindInstByName()`，这两个函数在 IC251 (OA 22.62) 中不存在：

```python
# sch_cmd.py line 183-184
f'inst = dbFindInstByName(cv "{...}")\n'
f'cdfSetInstParam(inst "{...}" "{...}")\n'
```

在 IC251 CIW 里验证：
```
fboundp(quote(cdfSetInstParam))  => nil
fboundp(quote(dbFindInstByName)) => nil
```

**可用替代 API**：
```skill
; 查找实例
inst = car(setof(i cv~>instances i~>name == "M3"))

; 设置参数
cdf = cdfGetInstCDF(inst)
cdfFindParamByName(cdf "w")~>value = "1600n"
```

**影响**：`vbridge sch param` 完全不可用。

**建议修复**：
1. 添加 `dbFindInstByName` 的 fallback 实现（`setof` 方式）
2. 替换 `cdfSetInstParam` 为 `cdfFindParamByName(cdf "param")~>value = "val"` 模式
3. 建议在 SKILL 生成前做一次 `fboundp` 检查，根据 Virtuoso 版本选择 API

### P3: `vbridge load` 本地模式不可用

**现象**：
```
Failed to prepare IL path: Deployment SSH runner is unavailable in local mode
```

**原因**：`vbridge load` 尝试通过 SSH 部署 .il 文件到远程，在本地模式下无 SSH runner。

**解决方法**：用 `vbridge exec 'load("/absolute/path/to/file.il")'` 代替。
在 CIW 进程内直接 `load()` 可以加载任何本地路径。

**建议修复**：本地模式下直接构造 `load("...")` SKILL 表达式发送给 daemon。

### P4: CDF 参数 `w` 与 `wf` 不同步

**现象**：通过 `cdfFindParamByName(cdf "w")~>value = "1600n"` 设置 W 后，
CDF 读回显示 w=1.6u，但 Spectre 网表中仍输出 w=400n（原值）。

**原因**：TSMC CDF 系统有 `w`（总宽度）和 `wf`（finger width）两个参数。
直接赋值绕过了 CDF callback，`wf` 未被联动更新。
Spectre netlister 实际使用的是 `wf`（因为 `nf=1`，`wf` 就是器件宽度）。

设置 L 没有此问题（L 无对应的 "finger L" 参数），寄生参数（ad/as/pd/ps/nrd/nrs）也不受影响。

**解决方法**：同时设置 `w` 和 `wf`：
```skill
cdfFindParamByName(cdf "w")~>value = "1600n"
cdfFindParamByName(cdf "wf")~>value = "1600n"
```

**建议改进**：`vbridge sch param` 和 `label-mos` 等修改参数的接口，
在设置 `w` 时应自动联动 `wf = w / nf`。
或者触发 CDF callback 来自动处理关联参数。

## 工作正常的部分

- `vbridge exec` 执行任意 SKILL 表达式 ✓
- `vbridge exec 'load("...")'` 加载 .il 脚本 ✓
- `vbridge sch batch` 的 `label-mos` 操作 ✓（成功修复了之前 `schCreateWireLabel` 无法合并网络的问题）
- `vbridge status` 状态检查 ✓
- Virtuoso daemon 连接稳定 ✓

## 有效使用模式总结

在 IC251 本地模式下，推荐工作流：

1. **修改网络连接**：`vbridge sch batch` + `label-mos` / `label-term`
2. **修改器件参数**：写 .il 脚本 + `vbridge exec 'load("...")'`
3. **批量参数查询**：`vbridge exec` + SKILL `setof`/`cdfGetInstCDF` 组合
4. **生成网表/仿真**：OCEAN `ocean -nograph -restore xxx.ocn`
