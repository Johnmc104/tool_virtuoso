# 013 原理图编辑操作补全计划

> 基于 012 场景审计中原理图设计 80% 覆盖度的缺口分析。

## 缺失操作及实现方案

| 操作 | 当前状态 | SKILL 验证 | 实现方式 |
|------|---------|-----------|---------|
| 删除实例 | △ exec 可用 | `dbDeleteObject(inst)` ✓ | 新 batch op: `delete-inst` |
| 移动实例 | ✗ | `inst~>xy = list(x y)` ✓ | 新 batch op: `move-inst` |
| 复制实例 | ✗ | `dbCopyFig` 调用失败 | 新 batch op: `copy-inst`，改用放置+参数复制 |
| 查询实例位置 | △ exec 可用 | `inst~>xy` ✓ | `sch list` 已有坐标 |
| 修改实例朝向 | ✗ | `inst~>orient = "MX"` 待验证 | 新 batch op: `move-inst` 含 orient |

### 新增 3 个 batch op

```json
{"op": "delete-inst", "inst": "M3"}

{"op": "move-inst", "inst": "M2", "x": 2.0, "y": 4.0}
{"op": "move-inst", "inst": "M2", "x": 2.0, "y": 4.0, "orient": "MX"}

{"op": "copy-inst", "inst": "M1", "name": "M3", "x": 4.0, "y": 0.0}
```

### SKILL 实现

```skill
; delete-inst
let((inst) inst = car(setof(i cv~>instances i~>name == "NAME"))
  when(inst dbDeleteObject(inst)))

; move-inst
let((inst) inst = car(setof(i cv~>instances i~>name == "NAME"))
  when(inst inst~>xy = list(X Y)
    when(ORIENT inst~>orient = ORIENT)))

; copy-inst (放置同类器件 + 复制参数)
let((src srcCdf dst dstCdf)
  src = car(setof(i cv~>instances i~>name == "SRC"))
  dst = dbCreateInst(cv dbOpenCellView(src~>libName src~>cellName "symbol") "NEW" list(X Y) "R0")
  srcCdf = cdfGetInstCDF(src) dstCdf = cdfGetInstCDF(dst)
  foreach(p srcCdf~>parameters
    let((dp) dp = cdfFindParamByName(dstCdf p~>name)
      when(dp dp~>value = p~>value))))
```
