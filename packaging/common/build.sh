#!/usr/bin/env bash
# packaging/common/build.sh — 通用 Python 二进制打包脚本
#
# 基于 packaging.yaml 配置文件驱动的 Docker 构建，
# 在 manylinux2014 (CentOS 7, glibc 2.17) 上编译 Python + 依赖并用 PyInstaller 打包。
#
# 用法:
#   packaging/common/build.sh                        # 在项目根目录执行
#   packaging/common/build.sh --config my.yaml       # 指定配置文件
#   packaging/common/build.sh --local                # 本地构建 (跳过 Docker)
#   packaging/common/build.sh --proxy http://proxy:port
#
# 源码包缓存策略:
#   源码包存放在 packaging/src/ (项目本地，不入 git)。
#   首次构建时自动下载，后续复用缓存。

set -euo pipefail

# ----------------------------------------------------------------
# 定位脚本自身和项目根目录
# ----------------------------------------------------------------
COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGING_DIR="$(cd "${COMMON_DIR}/.." && pwd)"
PROJECT_ROOT="$(pwd)"

# ----------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[1;32m[OK]\033[0m    %s\n' "$*"; }
err()   { printf '\033[1;31m[ERR]\033[0m   %s\n' "$*" >&2; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }

# ----------------------------------------------------------------
# 参数解析
# ----------------------------------------------------------------
MODE="docker"
CONFIG_FILE=""
PROXY_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --local|-l)
            MODE="local"
            shift
            ;;
        --save-env)
            MODE="save-env"
            shift
            ;;
        --proxy)
            PROXY_ARG="$2"
            export HTTP_PROXY="${2}"
            export HTTPS_PROXY="${2}"
            shift 2
            ;;
        --config|-c)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 [--local] [--save-env] [--proxy http://proxy:port] [--config packaging.yaml]"
            echo ""
            echo "  (无参数)           Docker 构建（推荐，CentOS 7 兼容）"
            echo "  --local            本地构建（仅当前系统 glibc 兼容）"
            echo "  --save-env         导出编译环境 (Docker 镜像 + pip 依赖)"
            echo "  --proxy URL        设置代理"
            echo "  --config FILE      指定配置文件（默认 packaging.yaml）"
            exit 0
            ;;
        *)
            err "未知参数: $1"
            echo "用法: $0 [--local] [--save-env] [--proxy http://proxy:port] [--config packaging.yaml]"
            exit 1
            ;;
    esac
done

# ----------------------------------------------------------------
# 查找配置文件
# ----------------------------------------------------------------
if [[ -z "${CONFIG_FILE}" ]]; then
    if [[ -f "${PROJECT_ROOT}/packaging.yaml" ]]; then
        CONFIG_FILE="${PROJECT_ROOT}/packaging.yaml"
    elif [[ -f "${PROJECT_ROOT}/packaging.yml" ]]; then
        CONFIG_FILE="${PROJECT_ROOT}/packaging.yml"
    else
        err "未找到 packaging.yaml。请在项目根目录创建或使用 --config 指定。"
        exit 1
    fi
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
    err "配置文件不存在: ${CONFIG_FILE}"
    exit 1
fi

info "配置文件: ${CONFIG_FILE}"

# ----------------------------------------------------------------
# 解析配置 (使用 Python + PyYAML)
# ----------------------------------------------------------------
parse_yaml() {
    local key="$1"
    python3 -c "
import yaml, sys
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
keys = '${key}'.split('.')
v = cfg
for k in keys:
    if isinstance(v, dict):
        v = v.get(k, '')
    else:
        v = ''
        break
if isinstance(v, list):
    print('\n'.join(str(i) for i in v))
elif isinstance(v, bool):
    print('true' if v else 'false')
else:
    print(v if v else '')
"
}

PROJECT_NAME=$(parse_yaml "project.name")
PYTHON_VERSION=$(parse_yaml "python.version")
NEED_SQLITE=$(parse_yaml "components.sqlite")
OUTPUT_DIR_REL=$(parse_yaml "output_dir")
OUTPUT_DIR="${PROJECT_ROOT}/${OUTPUT_DIR_REL:-release/bin}"
IMAGE_NAME="${PROJECT_NAME}-builder"
VERSION=$(cat "${PROJECT_ROOT}/VERSION" 2>/dev/null || echo "0.0.0-dev")

info "项目: ${PROJECT_NAME}"
info "Python: ${PYTHON_VERSION}"
info "SQLite: ${NEED_SQLITE}"
info "版本: ${VERSION}"

# ----------------------------------------------------------------
# 源码包版本 & 缓存目录
# 源码包存放在 packaging/src/ (项目本地目录，不入 git)
# ----------------------------------------------------------------
OPENSSL_VERSION="3.0.15"
SQLITE_VERSION="3450000"
SQLITE_YEAR="2024"
SRC_DIR="${PACKAGING_DIR}/src"

# 公共源码目录: 优先使用 common_packaging/src/ (Docker 镜像等大文件共享)
# 如果找不到, 回退到项目本地 SRC_DIR
COMMON_SRC_DIR="${SRC_DIR}"
for _candidate in \
    "${PROJECT_ROOT}/../common_packaging/src" \
    "${PROJECT_ROOT}/../../common_packaging/src"; do
    if [[ -d "${_candidate}" ]]; then
        COMMON_SRC_DIR="$(cd "${_candidate}" && pwd)"
        break
    fi
done
unset _candidate

# ----------------------------------------------------------------
# 下载/检查源码包
# ----------------------------------------------------------------
_find_or_link() {
    local filename="$1"
    local local_path="${SRC_DIR}/${filename}"
    local common_path="${COMMON_SRC_DIR}/${filename}"
    if [[ -f "${local_path}" ]]; then
        return 0
    fi
    if [[ "${COMMON_SRC_DIR}" != "${SRC_DIR}" && -f "${common_path}" ]]; then
        ln -sf "${common_path}" "${local_path}"
        return 0
    fi
    return 1
}

ensure_sources() {
    mkdir -p "${SRC_DIR}"

    local openssl_tar="openssl-${OPENSSL_VERSION}.tar.gz"
    if _find_or_link "${openssl_tar}"; then
        info "OpenSSL 源码包已缓存"
    else
        info "下载 OpenSSL ${OPENSSL_VERSION}..."
        curl -sSL -o "${SRC_DIR}/${openssl_tar}" \
            "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz"
    fi

    local python_tar="Python-${PYTHON_VERSION}.tgz"
    if _find_or_link "${python_tar}"; then
        info "Python ${PYTHON_VERSION} 源码包已缓存"
    else
        info "下载 Python ${PYTHON_VERSION}..."
        curl -sSL -o "${SRC_DIR}/${python_tar}" \
            "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
    fi

    if [[ "${NEED_SQLITE}" == "true" ]]; then
        local sqlite_tar="sqlite-autoconf-${SQLITE_VERSION}.tar.gz"
        if _find_or_link "${sqlite_tar}"; then
            info "SQLite 源码包已缓存"
        else
            info "下载 SQLite ${SQLITE_VERSION}..."
            curl -sSL -o "${SRC_DIR}/${sqlite_tar}" \
                "https://www.sqlite.org/${SQLITE_YEAR}/sqlite-autoconf-${SQLITE_VERSION}.tar.gz"
        fi
    fi
}

ensure_rpms() {
    local rpms_dir="${SRC_DIR}/rpms"
    if [[ -d "${rpms_dir}" ]] && ls "${rpms_dir}"/*.rpm &>/dev/null 2>&1; then
        info "RPM 包已缓存 ($(ls ${rpms_dir}/*.rpm | wc -l) 个)"
        return 0
    fi

    # 检查公共目录
    if [[ "${COMMON_SRC_DIR}" != "${SRC_DIR}" ]] && \
       [[ -d "${COMMON_SRC_DIR}/rpms" ]] && \
       ls "${COMMON_SRC_DIR}/rpms"/*.rpm &>/dev/null 2>&1; then
        info "从公共目录链接 RPM 包..."
        ln -sfn "${COMMON_SRC_DIR}/rpms" "${rpms_dir}"
        info "RPM 包已缓存 ($(ls ${rpms_dir}/*.rpm | wc -l) 个)"
        return 0
    fi

    info "首次下载 RPM 依赖包..."
    mkdir -p "${rpms_dir}"
    docker run --rm \
        -v "${rpms_dir}:/rpms" \
        quay.io/pypa/manylinux2014_x86_64 \
        bash -c 'yum install -y yum-utils && yumdownloader --resolve --destdir=/rpms perl-IPC-Cmd libffi-devel sqlite-devel 2>/dev/null && echo "RPM download OK"'

    if ls "${rpms_dir}"/*.rpm &>/dev/null 2>&1; then
        ok "RPM 包已下载: $(ls ${rpms_dir}/*.rpm | wc -l) 个"
    else
        err "RPM 下载失败，将在 Docker 构建时通过网络安装"
        rm -rf "${rpms_dir}"
        mkdir -p "${rpms_dir}"
    fi
}

# ----------------------------------------------------------------
# Docker 基础镜像管理
# ----------------------------------------------------------------
BASE_IMAGE="quay.io/pypa/manylinux2014_x86_64"
IMAGE_TAR="${COMMON_SRC_DIR}/manylinux2014_x86_64.tar"

ensure_docker_image() {
    if docker image inspect "${BASE_IMAGE}" &>/dev/null 2>&1; then
        return 0
    fi

    # 优先检查公共目录，再检查项目目录
    local tar=""
    if [[ -f "${COMMON_SRC_DIR}/manylinux2014_x86_64.tar" ]]; then
        tar="${COMMON_SRC_DIR}/manylinux2014_x86_64.tar"
    elif [[ -f "${SRC_DIR}/manylinux2014_x86_64.tar" ]]; then
        tar="${SRC_DIR}/manylinux2014_x86_64.tar"
    fi

    if [[ -n "${tar}" ]]; then
        info "从本地加载 Docker 基础镜像: ${tar}"
        docker load < "${tar}"
        ok "Docker 基础镜像已加载"
        return 0
    fi

    info "Docker 基础镜像将在构建时自动拉取 (需要网络)"
}

# ----------------------------------------------------------------
# 保存编译环境 (供内网离线构建)
# ----------------------------------------------------------------
save_env() {
    info "保存编译环境 (用于内网离线构建)"
    if [[ "${COMMON_SRC_DIR}" != "${SRC_DIR}" ]]; then
        info "公共目录: ${COMMON_SRC_DIR}"
        info "项目目录: ${SRC_DIR}"
    fi

    ensure_sources
    ensure_rpms

    # 1. 保存 Docker 基础镜像 → 公共目录 (所有项目共享)
    mkdir -p "${COMMON_SRC_DIR}"
    if [[ -f "${IMAGE_TAR}" ]]; then
        info "Docker 基础镜像已缓存: ${IMAGE_TAR} ($(du -h "${IMAGE_TAR}" | cut -f1))"
    else
        info "拉取并保存 Docker 基础镜像 → 公共目录..."
        docker pull "${BASE_IMAGE}"
        docker save "${BASE_IMAGE}" -o "${IMAGE_TAR}"
        ok "已保存: ${IMAGE_TAR} ($(du -h "${IMAGE_TAR}" | cut -f1))"
    fi

    # 2. 保存 Node 镜像 → 公共目录 (如果 Dockerfile 含前端构建)
    local fe_enabled
    fe_enabled=$(parse_yaml "frontend.enabled")
    if [[ "${fe_enabled}" == "true" ]]; then
        local node_image
        node_image=$(parse_yaml "frontend.node_image")
        node_image="${node_image:-node:20-slim}"
        local node_tar="${COMMON_SRC_DIR}/$(echo "${node_image}" | tr ':/' '__').tar"
        if [[ -f "${node_tar}" ]]; then
            info "Node 镜像已缓存: ${node_tar}"
        else
            info "拉取并保存 Node 镜像: ${node_image} → 公共目录..."
            docker pull "${node_image}"
            docker save "${node_image}" -o "${node_tar}"
            ok "已保存: ${node_tar} ($(du -h "${node_tar}" | cut -f1))"
        fi
    fi

    # 3. 下载 pip 依赖包 → 项目目录
    local wheels_dir="${SRC_DIR}/wheels"
    if [[ -d "${wheels_dir}" ]] && ls "${wheels_dir}"/*.whl &>/dev/null 2>&1; then
        local wheel_count
        wheel_count=$(ls "${wheels_dir}"/*.whl | wc -l)
        info "pip 依赖包已缓存 (${wheel_count} 个 .whl), 跳过下载"
        info "如需更新, 请先删除: rm -rf ${wheels_dir}"
    else
    mkdir -p "${wheels_dir}"

    local py_mm
    py_mm=$(echo "${PYTHON_VERSION}" | grep -oP '^\d+\.\d+')
    local py_tag="cp${py_mm//./}-cp${py_mm//./}"
    local py_bin="/opt/python/${py_tag}/bin/python"

    local reqs_file="${SRC_DIR}/_build_requirements.txt"

    # 基础依赖 (始终需要)
    cat > "${reqs_file}" << 'REQS'
pip
setuptools
wheel
pyinstaller==6.13.0
REQS

    # 从 packaging.yaml 提取项目依赖
    local pre_install
    pre_install=$(parse_yaml "dependencies.pre_install")
    if [[ -n "${pre_install}" ]]; then
        echo "${pre_install}" >> "${reqs_file}"
    fi

    local pip_install
    pip_install=$(parse_yaml "dependencies.pip_install")
    if [[ -n "${pip_install}" ]]; then
        echo "${pip_install}" >> "${reqs_file}"
    fi

    local deps_req
    deps_req=$(parse_yaml "dependencies.requirements_files")
    if [[ -n "${deps_req}" ]]; then
        while IFS= read -r rf; do
            [[ -z "${rf}" ]] && continue
            local rf_path="${PROJECT_ROOT}/${rf}"
            if [[ -f "${rf_path}" ]]; then
                grep -v '^\s*#' "${rf_path}" | grep -v '^\s*$' | grep -v '^\s*-' >> "${reqs_file}"
            fi
        done <<< "${deps_req}"
    fi

    local deps_pyproject
    deps_pyproject=$(parse_yaml "dependencies.pyproject_toml")
    if [[ -n "${deps_pyproject}" ]]; then
        python3 -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import os
with open(os.path.join('${PROJECT_ROOT}', '${deps_pyproject}'), 'rb') as f:
    proj = tomllib.load(f)
for dep in proj.get('project', {}).get('dependencies', []):
    print(dep)
" >> "${reqs_file}"
    fi

    info "下载 pip 依赖包 (Python ${py_mm}, manylinux2014)..."
    info "依赖列表: $(wc -l < "${reqs_file}") 条"

    local proxy_args=""
    if [[ -n "${PROXY_ARG}" ]]; then
        proxy_args="--env HTTP_PROXY=${PROXY_ARG} --env HTTPS_PROXY=${PROXY_ARG}"
    fi

    docker run --rm --network host \
        -v "${wheels_dir}:/wheels" \
        -v "${reqs_file}:/tmp/requirements.txt:ro" \
        ${proxy_args} \
        "${BASE_IMAGE}" \
        bash -c "${py_bin} -m pip download -d /wheels -r /tmp/requirements.txt && chown -R $(id -u):$(id -g) /wheels"

    rm -f "${reqs_file}"

    local wheel_count
    wheel_count=$(ls "${wheels_dir}" 2>/dev/null | wc -l)
    ok "pip 依赖包已缓存: ${wheel_count} 个文件"
    fi  # pip 缓存检查结束

    # 4. 前端包缓存 (自动检测 pnpm/npm)
    local fe_workdir="" fe_pkg_mgr="" fe_pkg_count=0

    # 从 packaging.yaml 读取配置 (优先)
    local fe_host_workdir fe_host_mgr
    fe_host_workdir=$(parse_yaml "frontend_host.workdir")
    fe_host_mgr=$(parse_yaml "frontend_host.package_manager")

    if [[ -n "${fe_host_workdir}" ]]; then
        fe_workdir="${PROJECT_ROOT}/${fe_host_workdir}"
        fe_pkg_mgr="${fe_host_mgr:-pnpm}"
    else
        # 自动检测: 扫描项目根目录和常见前端子目录
        for dir in "" "frontend/" "web-ui/" "web/"; do
            local check_dir="${PROJECT_ROOT}/${dir}"
            if [[ -f "${check_dir}pnpm-lock.yaml" ]]; then
                fe_workdir="${check_dir%/}"
                fe_pkg_mgr="pnpm"
                break
            elif [[ -f "${check_dir}package-lock.json" ]]; then
                fe_workdir="${check_dir%/}"
                fe_pkg_mgr="npm"
                break
            fi
        done
    fi

    if [[ -n "${fe_workdir}" && -n "${fe_pkg_mgr}" ]]; then
        local fe_store="${SRC_DIR}/${fe_pkg_mgr}-store"
        local fe_rel_dir="${fe_workdir#${PROJECT_ROOT}/}"
        [[ "${fe_rel_dir}" == "${PROJECT_ROOT}" ]] && fe_rel_dir="."
        info "检测到前端项目 (${fe_pkg_mgr}): ${fe_rel_dir}/"

        if [[ -d "${fe_store}" ]] && [[ $(find "${fe_store}" -type f 2>/dev/null | wc -l) -gt 0 ]]; then
            fe_pkg_count=$(find "${fe_store}" -type f 2>/dev/null | wc -l)
            info "${fe_pkg_mgr} 依赖已缓存 (${fe_pkg_count} 个文件), 跳过下载"
            info "如需更新, 请先删除: rm -rf ${fe_store}"
        elif [[ "${fe_pkg_mgr}" == "pnpm" ]]; then
            if ! command -v pnpm &>/dev/null; then
                warn "pnpm 未安装，跳过前端包缓存"
            else
                info "下载 pnpm 依赖到离线缓存..."
                (cd "${fe_workdir}" && CI=true pnpm fetch --store-dir "${fe_store}")
                fe_pkg_count=$(find "${fe_store}" -type f 2>/dev/null | wc -l)
                ok "pnpm 依赖已缓存: ${fe_store} ($(du -sh "${fe_store}" | cut -f1))"
            fi
        elif [[ "${fe_pkg_mgr}" == "npm" ]]; then
            if ! command -v npm &>/dev/null; then
                warn "npm 未安装，跳过前端包缓存"
            else
                info "下载 npm 依赖到离线缓存..."
                (cd "${fe_workdir}" && npm ci --cache "${fe_store}")
                fe_pkg_count=$(find "${fe_store}" -type f 2>/dev/null | wc -l)
                ok "npm 依赖已缓存: ${fe_store} ($(du -sh "${fe_store}" | cut -f1))"
            fi
        fi
    fi

    # 汇总
    echo ""
    echo "========================================="
    ok "编译环境保存完成"
    echo "========================================="
    if [[ "${COMMON_SRC_DIR}" != "${SRC_DIR}" ]]; then
        echo ""
        echo "  [公共] ${COMMON_SRC_DIR}/"
        echo "    Docker 镜像  : $(du -h "${IMAGE_TAR}" | cut -f1)"
        echo "    源码包       : $(ls "${COMMON_SRC_DIR}"/*.tar.gz "${COMMON_SRC_DIR}"/*.tgz 2>/dev/null | wc -l) 个"
        echo "    RPM 包       : $(ls "${COMMON_SRC_DIR}"/rpms/*.rpm 2>/dev/null | wc -l) 个"
        echo ""
        echo "  [项目] ${SRC_DIR}/"
        echo "    pip 包       : ${wheel_count} 个"
        if [[ ${fe_pkg_count} -gt 0 ]]; then
            echo "    前端包       : ${fe_pkg_mgr} ($(du -sh "${SRC_DIR}/${fe_pkg_mgr}-store" | cut -f1))"
        fi
    else
        local total_size
        total_size=$(du -sh "${SRC_DIR}" | cut -f1)
        echo "  总大小       : ${total_size}"
        echo "  Docker 镜像  : $(du -h "${IMAGE_TAR}" | cut -f1)"
        echo "  源码包       : $(ls "${SRC_DIR}"/*.tar.gz "${SRC_DIR}"/*.tgz 2>/dev/null | wc -l) 个"
        echo "  RPM 包       : $(ls "${SRC_DIR}"/rpms/*.rpm 2>/dev/null | wc -l) 个"
        echo "  pip 包       : ${wheel_count} 个"
        if [[ ${fe_pkg_count} -gt 0 ]]; then
            echo "  前端包       : ${fe_pkg_mgr} ($(du -sh "${SRC_DIR}/${fe_pkg_mgr}-store" | cut -f1))"
        fi
    fi
    echo ""
    echo "  内网使用方法:"
    if [[ "${COMMON_SRC_DIR}" != "${SRC_DIR}" ]]; then
        echo "    1. 复制公共目录: common_packaging/src/ (所有项目共享，仅需一份)"
        echo "    2. 复制项目目录: packaging/src/ (各项目独有)"
        echo "    3. 执行 make build 即可离线编译"
    else
        echo "    1. 将 packaging/src/ 整个目录复制到内网服务器的项目中"
        echo "    2. 执行 make build 即可离线编译"
    fi
    echo "========================================="
}

# ----------------------------------------------------------------
# Docker 构建
# ----------------------------------------------------------------
build_docker() {
    info "构建模式: Docker (manylinux2014 / CentOS 7 / glibc 2.17)"

    if ! command -v docker &>/dev/null; then
        err "Docker 未安装。请安装 Docker 或使用 --local 模式。"
        exit 1
    fi

    ensure_sources
    ensure_rpms
    ensure_docker_image

    # 检测离线模式: wheels 目录存在且非空
    local offline_flag=""
    local wheels_dir="${SRC_DIR}/wheels"
    if [[ -d "${wheels_dir}" ]] && ls "${wheels_dir}"/*.whl &>/dev/null 2>&1; then
        info "检测到离线 pip 缓存 (${wheels_dir})，启用离线模式"
        offline_flag="--offline"
    fi

    # 生成 Dockerfile
    local dockerfile="${PROJECT_ROOT}/.packaging.Dockerfile"
    info "生成 Dockerfile..."
    python3 "${COMMON_DIR}/generate_dockerfile.py" "${CONFIG_FILE}" -o "${dockerfile}" ${offline_flag}

    local build_args=(
        --build-arg "HTTP_PROXY=${HTTP_PROXY:-}"
        --build-arg "HTTPS_PROXY=${HTTPS_PROXY:-}"
    )
    if [[ -n "${PIP_INDEX_URL:-}" ]]; then
        build_args+=(--build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}")
    fi

    info "构建 Docker 镜像..."
    DOCKER_BUILDKIT=1 docker build \
        -t "${IMAGE_NAME}" \
        -f "${dockerfile}" \
        "${build_args[@]}" \
        .

    # 清理生成的 Dockerfile
    rm -f "${dockerfile}"

    # 提取二进制
    mkdir -p "${OUTPUT_DIR}"

    local bin_names
    bin_names=$(python3 -c "
import yaml
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
for b in cfg.get('binaries', []):
    print(b['name'])
")

    while IFS= read -r bin_name; do
        rm -f "${OUTPUT_DIR}/${bin_name}" 2>/dev/null || true
    done <<< "${bin_names}"

    info "提取二进制..."
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -v "${OUTPUT_DIR}:/out" \
        "${IMAGE_NAME}"

    _verify_binaries "${bin_names}"
}

# ----------------------------------------------------------------
# 本地构建
# ----------------------------------------------------------------
build_local() {
    info "构建模式: 本地 (仅兼容当前系统 glibc 及以上)"
    info "版本: ${VERSION}"

    local glibc_ver
    glibc_ver=$(ldd --version 2>&1 | head -1 | grep -oP '[0-9]+\.[0-9]+$' || echo "unknown")
    info "当前系统 glibc: ${glibc_ver}"

    local py=""
    if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
        py="${PROJECT_ROOT}/.venv/bin/python"
    else
        local py_major_minor
        py_major_minor=$(echo "${PYTHON_VERSION}" | grep -oP '^\d+\.\d+')
        for candidate in "python${py_major_minor}" python3 python; do
            if command -v "${candidate}" &>/dev/null; then
                py="${candidate}"
                break
            fi
        done
    fi
    if [[ -z "${py}" ]]; then
        err "未找到 Python。请安装 Python ${PYTHON_VERSION} 或激活 venv。"
        exit 1
    fi
    info "Python: $(${py} --version 2>&1)"

    local pip_args=()
    if [[ -n "${PIP_INDEX_URL:-}" ]]; then
        pip_args+=(-i "${PIP_INDEX_URL}")
    else
        pip_args+=(-i "https://pypi.tuna.tsinghua.edu.cn/simple/")
    fi

    if ! ${py} -m PyInstaller --version &>/dev/null 2>&1; then
        info "安装 PyInstaller..."
        ${py} -m pip install "${pip_args[@]}" pyinstaller==6.13.0
    fi

    # 预安装 (在主依赖之前)
    local pre_install
    pre_install=$(parse_yaml "dependencies.pre_install")
    if [[ -n "${pre_install}" ]]; then
        while IFS= read -r pkg; do
            [[ -z "${pkg}" ]] && continue
            info "预安装: pip install ${pkg}"
            ${py} -m pip install "${pip_args[@]}" ${pkg}
        done <<< "${pre_install}"
    fi

    # 依赖安装 — pyproject_toml / requirements_files / pip_install
    local deps_pyproject
    deps_pyproject=$(parse_yaml "dependencies.pyproject_toml")
    if [[ -n "${deps_pyproject}" ]]; then
        info "安装项目依赖 (${deps_pyproject})..."
        ${py} -m pip install "${pip_args[@]}" .
    fi

    local deps_pip
    deps_pip=$(parse_yaml "dependencies.pip_install")
    if [[ -n "${deps_pip}" ]]; then
        info "安装项目依赖..."
        while IFS= read -r pkg; do
            [[ -z "${pkg}" ]] && continue
            ${py} -m pip install "${pip_args[@]}" "${pkg}" 2>/dev/null || true
        done <<< "${deps_pip}"
    fi

    local deps_req
    deps_req=$(parse_yaml "dependencies.requirements_files")
    if [[ -n "${deps_req}" ]]; then
        while IFS= read -r rf; do
            [[ -z "${rf}" ]] && continue
            info "安装依赖: ${rf}"
            ${py} -m pip install "${pip_args[@]}" -r "${rf}"
        done <<< "${deps_req}"
    fi

    # Vendor 安装
    local vendor_installs
    vendor_installs=$(python3 -c "
import yaml
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
for v in cfg.get('vendor', []):
    if v.get('install'):
        print(v['install'])
" 2>/dev/null)
    if [[ -n "${vendor_installs}" ]]; then
        while IFS= read -r vargs; do
            [[ -z "${vargs}" ]] && continue
            info "安装 vendor: pip install ${vargs}"
            ${py} -m pip install ${vargs}
        done <<< "${vendor_installs}"
    fi

    # 补丁应用
    local patched_repos=()
    local patch_info
    patch_info=$(python3 -c "
import yaml
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
for p in cfg.get('patches', []):
    print(p['source'] + '|' + p['target_find_dir'])
" 2>/dev/null)
    if [[ -n "${patch_info}" ]]; then
        while IFS='|' read -r source target_dir; do
            [[ -z "${source}" ]] && continue
            info "应用补丁: ${source} → ${target_dir}"
            for f in ${source}*.py; do
                [[ -f "$f" ]] || continue
                local fname target
                fname=$(basename "$f")
                target=$(find "${target_dir}" -name "${fname}" -type f 2>/dev/null | head -1)
                if [[ -n "${target}" ]]; then
                    cp "$f" "${target}"
                    info "  patched: ${target}"
                    local repo_root="${target_dir}"
                    while [[ -n "${repo_root}" ]] && [[ ! -d "${repo_root}/.git" ]]; do
                        repo_root=$(dirname "${repo_root}")
                    done
                    [[ -d "${repo_root}/.git" ]] && patched_repos+=("${repo_root}")
                fi
            done
        done <<< "${patch_info}"
    fi

    mkdir -p "${OUTPUT_DIR}"

    local all_bin_names
    all_bin_names=$(python3 -c "
import yaml
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
for b in cfg.get('binaries', []):
    print(b['name'])
")

    echo "${all_bin_names}" | while IFS= read -r bin_name; do
        [[ -z "${bin_name}" ]] && continue
        local spec_file
        spec_file=$(python3 -c "
import yaml
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
for b in cfg.get('binaries', []):
    if b['name'] == '${bin_name}':
        print(b.get('spec', ''))
        break
")
        if [[ -n "${spec_file}" ]]; then
            info "打包 ${bin_name} (spec: ${spec_file})..."
            ${py} -m PyInstaller --noconfirm --log-level WARN "${spec_file}"
            [[ -f "dist/${bin_name}" ]] && mv "dist/${bin_name}" "${OUTPUT_DIR}/"
        else
            info "打包 ${bin_name} (inline)..."
            python3 -c "
import yaml, subprocess, sys
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
for b in cfg.get('binaries', []):
    if b['name'] != '${bin_name}':
        continue
    args = ['${py}', '-m', 'PyInstaller', '--noconfirm', '--log-level', 'WARN']
    args += ['--name', b['name']]
    if b.get('onefile', True):
        args += ['--onefile']
    args += ['--distpath', '${OUTPUT_DIR}']
    args += ['--clean']
    for hi in b.get('hidden_imports', []):
        args += ['--hidden-import', hi]
    for cs in b.get('collect_submodules', []):
        args += ['--collect-submodules', cs]
    for ca in b.get('collect_all', []):
        args += ['--collect-all', ca]
    for ad in b.get('add_data', []):
        args += ['--add-data', ad]
    args.append(b['entry'])
    sys.exit(subprocess.call(args))
"
        fi
    done

    # 恢复补丁修改 (还原 vendor submodule)
    if [[ ${#patched_repos[@]} -gt 0 ]]; then
        local unique_repos=($(printf '%s\n' "${patched_repos[@]}" | sort -u))
        for repo in "${unique_repos[@]}"; do
            info "恢复 ${repo} ..."
            git -C "${repo}" checkout . 2>/dev/null && \
                ok "  ${repo} 已恢复" || \
                warn "  ${repo} 恢复失败，请手动: git -C ${repo} checkout ."
        done
    fi

    _verify_binaries "${all_bin_names}"
}

# ----------------------------------------------------------------
# 验证产物
# ----------------------------------------------------------------
_verify_binaries() {
    local bin_names="$1"
    local all_ok=true

    while IFS= read -r bin_name; do
        [[ -z "${bin_name}" ]] && continue
        local bin="${OUTPUT_DIR}/${bin_name}"

        if [[ ! -f "${bin}" ]]; then
            err "构建失败: ${bin} 未生成"
            all_ok=false
            continue
        fi

        chmod +x "${bin}"
        local size
        size=$(du -h "${bin}" | cut -f1)
        ok "构建成功: ${OUTPUT_DIR_REL:-release/bin}/${bin_name} (${size})"

        if command -v objdump &>/dev/null; then
            local max_glibc
            max_glibc=$(objdump -T "${bin}" 2>/dev/null \
                | grep -oP 'GLIBC_[0-9.]+' | sort -V | tail -1 || true)
            if [[ -n "${max_glibc}" ]]; then
                local required
                required=$(echo "${max_glibc}" | grep -oP '[0-9.]+')
                info "  glibc 需求: ${max_glibc}"
                if [[ "$(printf '%s\n' "2.17" "${required}" | sort -V | head -1)" == "${required}" ]] || \
                   [[ "${required}" == "2.17" ]]; then
                    ok "  兼容 CentOS 7 (glibc 2.17)"
                else
                    err "  不兼容 CentOS 7! 需要 glibc ${required} > 2.17"
                    if [[ "${MODE}" == "local" ]]; then
                        err "  请使用 Docker 模式构建: $0 (不带 --local)"
                    fi
                fi
            fi
        fi
    done <<< "${bin_names}"

    if [[ "${all_ok}" != "true" ]]; then
        exit 1
    fi
}

# ----------------------------------------------------------------
# 入口
# ----------------------------------------------------------------
case "${MODE}" in
    docker)   build_docker ;;
    local)    build_local ;;
    save-env) save_env ;;
esac
