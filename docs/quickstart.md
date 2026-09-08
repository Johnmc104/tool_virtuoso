# 快速入门

## 前提

- Linux x86_64（CentOS 7+）
- Cadence Virtuoso IC23.1（或 IC6.1.8+）
- X11 显示环境（VNC / X11 Forward）

## 1. 安装

```bash
tar xzf virtuoso-bridge-*-linux-x86_64.tar.gz
cp bin/virtuoso-bridge bin/vbridge ~/.local/bin/
```

确保 `~/.local/bin` 在 PATH 中。

## 2. 初始化

```bash
vbridge init localhost
```

生成配置文件 `~/.virtuoso-bridge/.env`。

## 3. 一键启动

```bash
vbridge auto-start
```

执行流程：
1. 检测 daemon 是否已运行（防重复）
2. 启动 bridge（生成 SKILL 脚本）
3. 启动 Virtuoso（带 `-replay` 加载脚本）
4. 等待 daemon 就绪

Agent 推荐用法（阻塞等待 + JSON 输出）：

```bash
vbridge auto-start --wait --json
```

## 4. 执行 SKILL

```bash
# 单行表达式（vbridge 扩展，纯文本输出）
vbridge exec "geGetEditCellView()~>cellName"

# 从 stdin 读取
echo 'println("hello")' | vbridge exec

# 上游原生命令（JSON 输出）
vbridge eval 'getCurrentTime()'

# 加载 IL 文件（JSON 输出）
vbridge load ~/scripts/my_setup.il
```

## 5. 库管理

```bash
# 列出所有库
vbridge lib list
vbridge lib list --json

# 创建库
vbridge lib create myLib --path /home/user/myLib --tech-lib tsmc65
```

## 6. 原理图操作

```bash
# 创建/打开 cellview
vbridge sch create myLib myCell

# 读取原理图结构
vbridge sch read myLib myCell --json

# 列出实例
vbridge sch list myLib myCell

# 设置实例参数
vbridge sch param myLib myCell M0 w 1u
vbridge sch param myLib myCell M0 l 60n

# 批量操作（JSON stdin）
echo '[{"op":"add-inst","lib":"analogLib","cell":"nmos4","name":"M1","x":0,"y":0}]' | \
  vbridge sch batch myLib myCell

# 保存并检查
vbridge sch save
```

## 7. 生成 Symbol

```bash
vbridge symbol generate myLib myCell
vbridge symbol generate myLib myCell --overwrite
```

## 8. Spectre 仿真

```bash
# 运行仿真（返回 JSON 结果）
vbridge sim run tb_inv.scs -o /tmp/sim_out --mode aps

# 查看仿真结果
vbridge sim result /tmp/sim_out/
vbridge sim result /tmp/sim_out/ --signal VOUT --json

# 检查 license
vbridge sim license
```

## 9. 查看状态

```bash
vbridge status
vbridge windows
vbridge screenshot
```

## 10. Agent 集成

vbridge 设计为 CLI 工具，可直接被 AI Agent 调用：

```python
import subprocess, json

# 启动并等待就绪
r = subprocess.run(["vbridge", "auto-start", "--wait", "--json"],
                   capture_output=True, text=True)
status = json.loads(r.stdout)

# 读取原理图
r = subprocess.run(["vbridge", "sch", "read", "myLib", "myCell", "--json"],
                   capture_output=True, text=True)
schematic = json.loads(r.stdout)

# 运行仿真
r = subprocess.run(["vbridge", "sim", "run", "tb.scs", "-o", "/tmp/out"],
                   capture_output=True, text=True)
result = json.loads(r.stdout)
```
