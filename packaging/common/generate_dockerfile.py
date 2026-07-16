#!/usr/bin/env python3
"""从 packaging.yaml 生成项目专属 Dockerfile。

用法:
    python3 generate_dockerfile.py /path/to/project/packaging.yaml

输出 Dockerfile 到 stdout，或通过 --output 指定文件路径。
"""

import argparse
import sys
from pathlib import Path

import yaml


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    cfg.setdefault("project", {"name": "app"})
    cfg.setdefault("python", {"version": "3.11.9"})
    cfg.setdefault("components", {})
    cfg["components"].setdefault("openssl", True)
    cfg["components"].setdefault("sqlite", False)
    cfg.setdefault("binaries", [])
    cfg.setdefault("dependencies", {})
    cfg.setdefault("sources", [])
    cfg.setdefault("extra_copy", [])
    cfg.setdefault("output_dir", "release/bin")
    cfg.setdefault("frontend", None)
    cfg.setdefault("vendor", [])
    cfg.setdefault("patches", [])
    return cfg


def _parse_source(s):
    """Parse source entry — string or dict with path/dest/flatten."""
    if isinstance(s, str):
        if ":" in s and not s.startswith("/"):
            parts = s.split(":", 1)
            return {"path": parts[0], "dest": parts[1]}
        return {"path": s, "dest": s}
    return s


def _lines(*args):
    return "\n".join(args)


def gen_openssl_stage():
    return _lines(
        "# ════════════════════════════════════════════════════════════",
        "# Stage: 编译 OpenSSL 3.0",
        "# ════════════════════════════════════════════════════════════",
        "FROM quay.io/pypa/manylinux2014_x86_64 AS openssl-builder",
        "",
        'ARG HTTP_PROXY=""',
        'ARG HTTPS_PROXY=""',
        "",
        "COPY packaging/src/rpms/ /tmp/rpms/",
        "RUN if ls /tmp/rpms/*.rpm &>/dev/null 2>&1; then \\",
        "        yum -y --disablerepo='*' localinstall /tmp/rpms/*.rpm || yum -y install perl-IPC-Cmd; \\",
        "    else \\",
        "        yum -y install perl-IPC-Cmd; \\",
        "    fi && yum clean all && rm -rf /tmp/rpms",
        "",
        "ARG OPENSSL_VERSION=3.0.15",
        "COPY packaging/src/openssl-${OPENSSL_VERSION}.tar.gz /tmp/",
        "RUN tar xzf /tmp/openssl-${OPENSSL_VERSION}.tar.gz -C /tmp && \\",
        "    cd /tmp/openssl-${OPENSSL_VERSION} && \\",
        "    ./config --prefix=/opt/openssl --openssldir=/opt/openssl/ssl \\",
        "        shared no-tests && \\",
        '    make -j"$(nproc)" && \\',
        "    make install_sw && \\",
        "    rm -rf /tmp/openssl-${OPENSSL_VERSION}*",
    )


def gen_sqlite_stage():
    return _lines(
        "# ════════════════════════════════════════════════════════════",
        "# Stage: 编译 SQLite 3.45",
        "# ════════════════════════════════════════════════════════════",
        "FROM quay.io/pypa/manylinux2014_x86_64 AS sqlite-builder",
        "",
        "ARG SQLITE_VERSION=3450000",
        "COPY packaging/src/sqlite-autoconf-${SQLITE_VERSION}.tar.gz /tmp/",
        "RUN tar xzf /tmp/sqlite-autoconf-${SQLITE_VERSION}.tar.gz -C /tmp && \\",
        "    cd /tmp/sqlite-autoconf-${SQLITE_VERSION} && \\",
        '    ./configure --prefix=/opt/sqlite --disable-static \\',
        '        CFLAGS="-O2 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_JSON1" && \\',
        '    make -j"$(nproc)" && make install && \\',
        "    rm -rf /tmp/sqlite-autoconf-${SQLITE_VERSION}*",
    )


def gen_python_stage(cfg: dict):
    py_ver = cfg["python"]["version"]
    need_sqlite = cfg["components"]["sqlite"]

    lines = [
        "# ════════════════════════════════════════════════════════════",
        f"# Stage: 编译 Python {py_ver}",
        "# ════════════════════════════════════════════════════════════",
        "FROM quay.io/pypa/manylinux2014_x86_64 AS python-builder",
        "",
        "COPY packaging/src/rpms/ /tmp/rpms/",
        "RUN if ls /tmp/rpms/*.rpm &>/dev/null 2>&1; then \\",
        "        yum -y --disablerepo='*' localinstall /tmp/rpms/*.rpm || yum -y install libffi-devel; \\",
        "    else \\",
        "        yum -y install libffi-devel; \\",
        "    fi && yum clean all && rm -rf /tmp/rpms",
        "",
        "COPY --from=openssl-builder /opt/openssl /opt/openssl",
    ]

    sqlite_env = ""
    sqlite_ldflags = ""
    sqlite_cppflags = ""
    sqlite_pkgconfig = ""
    if need_sqlite:
        lines.append("COPY --from=sqlite-builder /opt/sqlite /opt/sqlite")
        sqlite_env = ":/opt/sqlite/lib"
        sqlite_ldflags = " -L/opt/sqlite/lib"
        sqlite_cppflags = " -I/opt/sqlite/include"
        sqlite_pkgconfig = ":/opt/sqlite/lib/pkgconfig"

    lines += [
        "",
        f"ENV LD_LIBRARY_PATH=/opt/openssl/lib64:/opt/openssl/lib{sqlite_env}",
        f"ENV PKG_CONFIG_PATH=/opt/openssl/lib64/pkgconfig:/opt/openssl/lib/pkgconfig{sqlite_pkgconfig}",
        "",
        f"ARG PYTHON_VERSION={py_ver}",
        "COPY packaging/src/Python-${PYTHON_VERSION}.tgz /tmp/",
        "RUN tar xzf /tmp/Python-${PYTHON_VERSION}.tgz -C /tmp && \\",
        "    cd /tmp/Python-${PYTHON_VERSION} && \\",
        f"    LD_LIBRARY_PATH=/opt/openssl/lib64:/opt/openssl/lib{sqlite_env} \\",
        "    ./configure --enable-shared --prefix=/opt/cpython \\",
        "        --with-openssl=/opt/openssl \\",
        "        --with-openssl-rpath=auto \\",
        f'        LDFLAGS="-Wl,-rpath,/opt/cpython/lib -L/opt/openssl/lib64 -L/opt/openssl/lib{sqlite_ldflags}" \\',
        f'        CPPFLAGS="-I/opt/openssl/include{sqlite_cppflags}" && \\',
        f"    LD_LIBRARY_PATH=/opt/openssl/lib64:/opt/openssl/lib{sqlite_env} \\",
        '    make -j"$(nproc)" && \\',
        "    make install && \\",
        "    rm -rf /tmp/Python-${PYTHON_VERSION}*",
    ]

    return "\n".join(lines)


def gen_frontend_stage(cfg: dict):
    fe = cfg.get("frontend")
    if not fe or not fe.get("enabled"):
        return ""

    node_image = fe.get("node_image", "node:20-slim")
    npm_registry = fe.get("npm_registry", "https://registry.npmmirror.com")
    build_cmd = fe.get("build_cmd", "npx vite build --outDir /build/dist")
    source_dir = fe.get("source_dir", "web-ui/")

    lines = [
        "# ════════════════════════════════════════════════════════════",
        "# Stage: 前端构建",
        "# ════════════════════════════════════════════════════════════",
        f"FROM {node_image} AS frontend-builder",
        "WORKDIR /build",
    ]
    for f in fe.get("workdir_files", []):
        lines.append(f"COPY {f} ./")
    lines += [
        f"RUN npm config set registry {npm_registry} && npm ci",
        f"COPY {source_dir} ./",
        f"RUN {build_cmd}",
    ]
    return "\n".join(lines)


def gen_project_stage(cfg: dict):
    need_sqlite = cfg["components"]["sqlite"]
    project_name = cfg["project"]["name"]
    binaries = cfg["binaries"]
    deps = cfg.get("dependencies", {})
    sources = cfg.get("sources", [])
    extra_copy = cfg.get("extra_copy", [])
    fe = cfg.get("frontend")

    sqlite_ld = ":/opt/sqlite/lib" if need_sqlite else ""

    lines = [
        "# ════════════════════════════════════════════════════════════",
        f"# Stage: 项目构建 ({project_name})",
        "# ════════════════════════════════════════════════════════════",
        "FROM quay.io/pypa/manylinux2014_x86_64",
        "",
        'ARG HTTP_PROXY=""',
        'ARG HTTPS_PROXY=""',
        "",
        "COPY --from=openssl-builder /opt/openssl /opt/openssl",
    ]
    if need_sqlite:
        lines.append("COPY --from=sqlite-builder /opt/sqlite /opt/sqlite")
    lines += [
        "COPY --from=python-builder /opt/cpython /opt/cpython",
        "",
        "ENV PYTHON=/opt/cpython/bin/python3",
        f"ENV LD_LIBRARY_PATH=/opt/cpython/lib:/opt/openssl/lib64:/opt/openssl/lib{sqlite_ld}",
        "ENV PATH=/opt/cpython/bin:${PATH}",
        "",
    ]

    # 验证
    verify = '${PYTHON} -c "import ssl; print(\'SSL OK:\', ssl.OPENSSL_VERSION)"'
    if need_sqlite:
        verify += ' && \\\n    ${PYTHON} -c "import sqlite3; print(\'SQLite OK:\', sqlite3.sqlite_version)"'
    lines.append(f"RUN {verify}")

    lines += [
        "",
        "ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/",
        "ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn",
        "ENV PIP_INDEX_URL=${PIP_INDEX_URL}",
        "ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}",
        "ENV NO_PROXY=pypi.tuna.tsinghua.edu.cn,*.tuna.tsinghua.edu.cn",
        "ENV no_proxy=pypi.tuna.tsinghua.edu.cn,*.tuna.tsinghua.edu.cn",
        "",
        "RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \\",
        "    ${PYTHON} -m pip install --no-cache-dir --upgrade pip setuptools wheel && \\",
        "    ${PYTHON} -m pip install --no-cache-dir pyinstaller==6.13.0",
        "",
        "WORKDIR /build",
    ]

    # 依赖安装
    if deps.get("pyproject_toml"):
        pyproject_path = deps["pyproject_toml"]
        extra_files = deps.get("pyproject_extra_files", [])
        copy_items = [pyproject_path] + extra_files
        lines += ["", f"COPY {' '.join(copy_items)} ./"]
        for pre in deps.get("pre_install", []):
            lines += [
                "RUN --mount=type=cache,target=/root/.cache/pip \\",
                f"    ${{PYTHON}} -m pip install {pre}",
            ]
        py_cmd = (
            "import tomllib; print(' '.join("
            "tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))"
        )
        lines += [
            "RUN --mount=type=cache,target=/root/.cache/pip \\",
            f'    ${{PYTHON}} -m pip install \\',
            f'    $(${{PYTHON}} -c "{py_cmd}")',
        ]
    elif deps.get("requirements_files"):
        lines.append("")
        for rf in deps["requirements_files"]:
            alias = rf.replace("/", "-") if "/" in rf else rf
            lines.append(f"COPY {rf} {alias}")
        extra = deps.get("pip_extra_args", "")
        install_parts = []
        for rf in deps["requirements_files"]:
            alias = rf.replace("/", "-") if "/" in rf else rf
            install_parts.append(f"    ${{PYTHON}} -m pip install --no-cache-dir {extra} -r {alias}".rstrip())
        lines.append("RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \\")
        lines.append(" && \\\n".join(install_parts))
    elif deps.get("pip_install"):
        pkgs = " ".join(f'"{p}"' for p in deps["pip_install"])
        lines += [
            "",
            "RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \\",
            f"    ${{PYTHON}} -m pip install --no-cache-dir {pkgs}",
        ]

    # 源码复制
    lines.append("")
    for s in sources:
        entry = _parse_source(s)
        path = entry["path"]
        dest = entry.get("dest", path)
        if entry.get("flatten") or dest in (".", "./"):
            lines.append(f"COPY {path} ./")
        else:
            lines.append(f"COPY {path} {dest}")

    for s in extra_copy:
        entry = _parse_source(s)
        path = entry["path"]
        dest = entry.get("dest", path)
        lines.append(f"COPY {path} {dest}")

    # 前端产物复制
    if fe and fe.get("enabled"):
        dest = fe.get("output_dest", "static/dist/")
        lines.append(f"COPY --from=frontend-builder /build/dist {dest}")

    # Vendor 目录复制
    vendors = cfg.get("vendor", [])
    for v in vendors:
        vpath = v["path"]
        lines.append(f"COPY {vpath} {vpath}")

    # 安装项目自身 (pyproject_toml 模式: 源码已复制，安装 package metadata)
    if deps.get("pyproject_toml"):
        lines += [
            "",
            "RUN ${PYTHON} -m pip install --no-deps .",
        ]

    # Vendor 包安装
    for v in vendors:
        if v.get("install"):
            lines += [
                "RUN --mount=type=cache,target=/root/.cache/pip \\",
                f"    ${{PYTHON}} -m pip install {v['install']}",
            ]

    # 补丁应用
    patches = cfg.get("patches", [])
    if patches:
        lines.append("")
        for p in patches:
            lines.append(f"COPY {p['source']} {p['source']}")
        for p in patches:
            source = p["source"]
            target_dir = p["target_find_dir"]
            lines += [
                f'RUN for f in {source}*.py; do \\',
                '        [ -f "$f" ] || continue; \\',
                '        fname=$(basename "$f"); \\',
                f'        target=$(find {target_dir} -name "$fname" -type f 2>/dev/null | head -1); \\',
                '        [ -n "$target" ] && cp "$f" "$target" && echo "patched: $target"; \\',
                "    done",
            ]

    # PyInstaller spec 复制 (如果 spec 不在已复制的 sources 内)
    for b in binaries:
        if b.get("spec"):
            spec_path = b["spec"]
            already_covered = False
            for s in sources:
                entry = _parse_source(s)
                if spec_path.startswith(entry["path"]):
                    already_covered = True
                    break
            if not already_covered:
                lines.append(f"COPY {spec_path} {spec_path}")

    # PyInstaller 打包
    lines.append("")
    pyinstaller_parts = []
    binary_names = []
    for b in binaries:
        name = b["name"]
        binary_names.append(name)
        if b.get("spec"):
            spec_in_docker = b["spec"]
            # 如果 sources 使用 flatten, spec 路径需要调整
            for s in sources:
                entry = _parse_source(s)
                src_path = entry["path"]
                dest = entry.get("dest", src_path)
                if (entry.get("flatten") or dest in (".", "./")) and spec_in_docker.startswith(src_path):
                    spec_in_docker = spec_in_docker[len(src_path):]
                    if spec_in_docker.startswith("/"):
                        spec_in_docker = spec_in_docker[1:]
                    break
            pyinstaller_parts.append(
                f"    ${{PYTHON}} -m PyInstaller --noconfirm --log-level WARN {spec_in_docker}"
            )
        else:
            args = ["--name", name]
            if b.get("onefile", True):
                args.append("--onefile")
            args += ["--distpath", "/build/dist", "--workpath", "/build/build/pyinstaller"]
            args += ["--specpath", "/build/build", "--clean"]
            for hi in b.get("hidden_imports", []):
                args += ["--hidden-import", hi]
            for cs in b.get("collect_submodules", []):
                args += ["--collect-submodules", cs]
            for ca in b.get("collect_all", []):
                args += ["--collect-all", ca]
            for ad in b.get("add_data", []):
                args += ["--add-data", f'"/build/{ad}"']
            args.append(b["entry"])
            pyinstaller_parts.append(f'    ${{PYTHON}} -m PyInstaller {" ".join(args)}')

    lines.append("RUN --mount=type=cache,target=/build/build \\")
    lines.append(" && \\\n".join(pyinstaller_parts))

    # glibc 检查
    lines.append("")
    lines.append('RUN echo "=== glibc requirements ===" && \\')
    for i, name in enumerate(binary_names):
        end = "" if i == len(binary_names) - 1 else " && \\"
        lines.append(
            f"    echo \"{name}: $(objdump -T dist/{name} 2>/dev/null "
            f"| grep -oP 'GLIBC_[0-9.]+' | sort -V | uniq | tail -1)\"{end}"
        )

    # CMD
    lines.append("")
    cp_cmds = " && ".join(f"cp /build/dist/{n} /out/{n}" for n in binary_names)
    lines.append(f'CMD ["sh", "-c", "{cp_cmds}"]')

    return "\n".join(lines)


def generate(cfg: dict) -> str:
    sections = [
        "# syntax=docker/dockerfile:1",
        f"# Auto-generated Dockerfile for {cfg['project']['name']}",
        f"# Python {cfg['python']['version']} on manylinux2014 (CentOS 7, glibc 2.17)",
        "",
    ]

    sections.append(gen_openssl_stage())
    sections.append("")

    if cfg["components"]["sqlite"]:
        sections.append(gen_sqlite_stage())
        sections.append("")

    sections.append(gen_python_stage(cfg))
    sections.append("")

    fe_stage = gen_frontend_stage(cfg)
    if fe_stage:
        sections.append(fe_stage)
        sections.append("")

    sections.append(gen_project_stage(cfg))
    sections.append("")

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(description="从 packaging.yaml 生成 Dockerfile")
    parser.add_argument("config", help="packaging.yaml 路径")
    parser.add_argument("-o", "--output", help="输出 Dockerfile 路径 (默认 stdout)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dockerfile = generate(cfg)

    if args.output:
        Path(args.output).write_text(dockerfile)
        print(f"Dockerfile 已生成: {args.output}", file=sys.stderr)
    else:
        print(dockerfile)


if __name__ == "__main__":
    main()
