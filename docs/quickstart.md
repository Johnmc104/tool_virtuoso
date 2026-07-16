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

## 4. 执行 SKILL

```bash
# 单行表达式
vbridge exec "geGetEditCellView()~>cellName"

# 从 stdin 读取
echo 'println("hello")' | vbridge exec

# 查询库列表
vbridge exec 'ddGetLibList()~>name'
```

## 5. 加载 IL 文件

```bash
vbridge load ~/scripts/my_setup.il
```

## 6. 查看状态

```bash
vbridge status
```

## 7. 原理图操作

```bash
# 创建/打开 cellview
vbridge sch create myLib myCell

# 保存并检查
vbridge sch save

# 列出实例
vbridge sch list myLib myCell
```

## Agent 集成

vbridge 设计为 CLI 工具，可直接被 AI Agent 调用：

```python
import subprocess
result = subprocess.run(
    ["vbridge", "exec", "ddGetLibList()~>name"],
    capture_output=True, text=True
)
print(result.stdout)
```
