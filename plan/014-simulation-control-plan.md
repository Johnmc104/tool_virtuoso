# 014 仿真控制开发计划

> 目标：将仿真覆盖度从 75% 提升到 90%+。

## 缺口分析

| 缺口 | 解决方案 | 需要新 CLI？ | 优先级 |
|------|---------|:---:|:---:|
| AC/PSS/Pnoise 配置 | Agent 编辑网表 + 文档指引 | 否 | P1 |
| Corner 仿真 | `--section ss_lib` 已有，多次运行 | 否 | P1 |
| 参数扫描 | Spectre `sweep` 语法写入网表 | 否（P2 加 CLI） | P1(doc) / P2(CLI) |
| AC 测量 (gain/ugf/pm) | 扩展 `sim measure` | 是 | P2 |
| THD 测量 | 需 PSS 谐波数据解析 | 是 | P3 |
| 波形可视化 | CSV 导出 + 外部工具 | 否 | P3 |

## P1 实施：文档 + 语法参考

在 SKILL.md 中添加完整的 Spectre 分析语法参考，使 agent 能自主编辑网表。

### Spectre 分析语法

```spectre
// 瞬态
tran1 tran stop=2u errpreset=moderate

// DC 工作点
dcOp dc

// DC 扫描
dcSweep sweep param=vgs start=0 stop=1.2 step=0.05 {
  dcOp dc
}

// AC 小信号
ac1 ac start=1k stop=10G dec=20

// PSS 周期稳态（振荡器）
ic ON=3.3 OP=0
pss1 (ON OP) pss fund=2G harms=7 tstab=300n errpreset=moderate

// Pnoise 相噪
pnoise1 (ON OP) pnoise start=1k stop=100M dec=5 relharmnum=1

// 参数扫描
paramSweep sweep param=vcon start=1.5 stop=2.7 step=0.3 {
  tran1 tran stop=2u
}

// 信号保存
saveOptions options save=selected
save ON OP V0:p
```

### Agent 工作流

```bash
# 1. 生成基础网表
vbridge sch netlist myLib myCell -o ./nl --standalone

# 2. Agent 按需编辑分析语句
# 例：替换默认 tran 为 AC
sed -i 's/tran tran stop=2u.*//' ./nl/input.scs
echo 'ac1 ac start=1k stop=10G dec=20' >> ./nl/input.scs

# 3. 运行
vbridge sim run ./nl/input.scs -o ./raw

# 4. 查看/测量
vbridge sim result ./raw/
vbridge sim measure ./raw/ freq ON --from 1e-6
vbridge sim result ./raw/ --csv --signal ON > wave.csv
```

### Corner 工作流

```bash
for corner in tt_lib ss_lib ff_lib; do
  vbridge sch netlist myLib myCell -o ./nl_${corner} --standalone --section $corner
  vbridge sim run ./nl_${corner}/input.scs -o ./raw_${corner}
  echo "$corner: $(vbridge sim measure ./raw_${corner}/ freq ON --from 1e-6)"
done
```
