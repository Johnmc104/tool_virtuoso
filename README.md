# Virtuoso Bridge Tools

Cadence Virtuoso SKILL Bridge 二进制工具集。提供命令行直接操控 Virtuoso CIW，支持一键启动、SKILL 执行、原理图批处理等功能。

## 安装

解压分发包，将 `bin/` 加入 PATH：

```bash
tar xzf virtuoso-bridge-*-linux-x86_64.tar.gz -C /opt/vtool/
export PATH="/opt/vtool/bin:$PATH"
```

或使用 `make deploy-bin`（需设置 `VTOOL_HOME`）：

```bash
export VTOOL_HOME=/opt/vtool
make deploy-bin
```

## Python 源码使用

分发包中 `lib/` 目录包含完整 Python 源码，可供多用户共享引用：

```bash
export PYTHONPATH="/opt/vtool/lib:$PYTHONPATH"
```

之后可直接在 Python 中使用：

```python
from virtuoso_bridge.client import VirtuosoClient
from vbridge.auto_start import startup_sequence
```

## 快速开始

```bash
# 初始化配置（首次使用）
vbridge init localhost

# 一键启动 Bridge + Virtuoso
vbridge auto-start

# 执行 SKILL 表达式
vbridge exec "ddGetLibList()~>name"

# 加载 IL 文件
vbridge load setup.il

# 查看状态
vbridge status
```

## 构建

依赖 Docker（manylinux2014 基础镜像，确保 CentOS 7 兼容）：

```bash
make build        # Docker 构建（推荐）
make build-local  # 本地构建（仅当前系统 glibc）
make package      # 打包为 tar.gz 分发包
make pkg-info     # 查看打包配置
```

构建会自动 patch `ramic_bridge.il`（修复 IC23.1 兼容性），编译完成后恢复。

## 开发

```bash
git clone --recursive <repo-url>
cd tool_virtuoso
make dev          # pip install -e 上游库
```

`virtuoso-bridge-lite/` 为 git submodule，更新：

```bash
git submodule update --remote
```

## 架构

```
virtuoso-bridge   底层 Bridge 二进制（上游 CLI 直接打包）
vbridge           上层调度工具（扩展命令 + EDA 自启动）
```

`vbridge` 调用 `virtuoso-bridge` 作为子进程处理 init/start/stop，自身负责 auto-start 编排、exec/load 透传和 daemon 回调。

