# ============================================================
# common_packaging/packaging.mk — 公共打包目标
# ============================================================
#
# 提供 build / install / package / release 四个标准目标。
# 项目 Makefile 通过 include 引入，只需设置必要变量。
#
# ── 必须变量（项目在 include 之前设置）──
#   PROJECT_NAME    项目名 (如 ktm, tool_plan, vcm)
#
# ── 可选变量（有默认值）──
#   VERSION         版本号 (默认从 VERSION 文件读取)
#   COMMON_PKG_DIR  common_packaging 目录路径
#   RELEASE_DIR     构建产物目录 (默认 release)
#   BIN_DIR         二进制输出目录 (默认 release/bin)
#   DIST_DIR        压缩包输出目录 (默认 dist)
#   INSTALL_DIR     安装目标目录 (默认 $$VTOOL_HOME/bin)
#   BINARIES        二进制文件名列表 (默认 = PROJECT_NAME)
#   BUILD_SCRIPT    构建脚本路径 (默认 common build.sh)
#   PACKAGE_FILES   打包时额外包含的文件/目录 (相对 RELEASE_DIR)
#   ARCHIVE_EXTRA_DIRS  解压后额外包含的顶级目录 (如 dist/ deploy/)
#
# ── 用法示例 ──
#   PROJECT_NAME := ktm
#   include /path/to/common_packaging/packaging.mk
#
# ── 项目可覆盖的钩子目标 ──
#   pre-build       构建前执行 (如前端构建)
#   post-build      构建后执行 (如 strip)
#   pre-package     打包前执行 (如复制前端产物)
#   post-package    打包后执行
#   pre-release     发布前执行
# ============================================================

# ── 路径推断 ──
# 如果项目没有显式设置 COMMON_PKG_DIR，从本文件路径推断
COMMON_PKG_DIR ?= $(dir $(lastword $(MAKEFILE_LIST)))

# ── 默认值 ──
VERSION        ?= $(shell cat VERSION 2>/dev/null || echo "0.0.0-dev")
RELEASE_DIR    ?= release
BIN_DIR        ?= $(RELEASE_DIR)/bin
DIST_DIR       ?= dist
BINARIES       ?= $(PROJECT_NAME)
INSTALL_DIR    ?= $(if $(VTOOL_HOME),$(VTOOL_HOME)/bin,)

ARCH           ?= $(shell uname -m)
OS_NAME        ?= $(shell uname -s | tr '[:upper:]' '[:lower:]')
PLATFORM       := $(OS_NAME)-$(ARCH)

ARCHIVE_NAME   ?= $(PROJECT_NAME)-$(VERSION)-$(PLATFORM).tar.gz
ARCHIVE_PATH   := $(DIST_DIR)/$(ARCHIVE_NAME)

BUILD_SCRIPT   ?= $(COMMON_PKG_DIR)/build.sh

# 包内额外文件 (项目可追加)
PACKAGE_FILES  ?=

# ── 颜色 ──
_C_GREEN  := \033[0;32m
_C_YELLOW := \033[1;33m
_C_BLUE   := \033[1;34m
_C_RED    := \033[1;31m
_C_RESET  := \033[0m

# ── 防止与项目目标冲突: 仅声明公共目标 ──
.PHONY: build build-local build-centos7 \
        deploy-bin \
        package tar \
        release tag version \
        save-build-env \
        pkg-clean pkg-info \
        pre-build post-build pre-package post-package pre-release

# ============================================================
# 1. build — Docker 构建 (CentOS 7 兼容)
# ============================================================
build: pre-build _do-build post-build ## Docker 构建二进制 (CentOS 7 兼容)

_do-build:
	@printf '%b\n' "$(_C_BLUE)[BUILD]$(_C_RESET) $(PROJECT_NAME) v$(VERSION) — Docker (manylinux2014 / glibc 2.17)"
	$(BUILD_SCRIPT)
	@for bin in $(BINARIES); do \
		if [ -f "$(BIN_DIR)/$$bin" ]; then \
			printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    $(BIN_DIR)/$$bin ($$(du -h $(BIN_DIR)/$$bin | cut -f1))"; \
		fi; \
	done

build-local: pre-build _do-build-local post-build ## 本地构建 (仅当前 glibc)

_do-build-local:
	@printf '%b\n' "$(_C_BLUE)[BUILD]$(_C_RESET) $(PROJECT_NAME) v$(VERSION) — 本地构建"
	$(BUILD_SCRIPT) --local

build-centos7: build ## 别名: build-centos7 → build

# ============================================================
# 1b. save-build-env — 导出编译环境供内网离线构建
# ============================================================
save-build-env: ## 导出编译环境 (Docker 镜像 + pip 依赖 + 源码包)
	@printf '%b\n' "$(_C_BLUE)[ENV]$(_C_RESET)  导出 $(PROJECT_NAME) 编译环境..."
	$(BUILD_SCRIPT) --save-env

# ============================================================
# 2. deploy-bin — 部署二进制到目标目录
# ============================================================
deploy-bin: ## 部署二进制到 $$VTOOL_HOME/bin/
	@if [ -z "$(INSTALL_DIR)" ]; then \
		printf '%b\n' "$(_C_RED)[ERR]$(_C_RESET)  VTOOL_HOME 未设置"; \
		echo "请设置环境变量: export VTOOL_HOME=/path/to/vtool"; \
		exit 1; \
	fi
	@_need_build=0; \
	for bin in $(BINARIES); do \
		if [ ! -f "$(BIN_DIR)/$$bin" ]; then \
			_need_build=1; \
			break; \
		fi; \
	done; \
	if [ "$$_need_build" = "1" ]; then \
		printf '%b\n' "$(_C_YELLOW)[WARN]$(_C_RESET) 二进制不存在，先执行构建..."; \
		$(MAKE) build; \
	fi
	@mkdir -p $(INSTALL_DIR)
	@for bin in $(BINARIES); do \
		cp "$(BIN_DIR)/$$bin" "$(INSTALL_DIR)/$$bin"; \
		chmod +x "$(INSTALL_DIR)/$$bin"; \
		printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    已安装: $(INSTALL_DIR)/$$bin"; \
	done

# ============================================================
# 3. package — 打包为 tar.gz
# ============================================================
package: pre-package _do-package post-package ## 打包为发布压缩包

_do-package:
	@printf '%b\n' "$(_C_BLUE)[PACK]$(_C_RESET) $(PROJECT_NAME) v$(VERSION)"
	@# 检查二进制存在
	@for bin in $(BINARIES); do \
		if [ ! -f "$(BIN_DIR)/$$bin" ]; then \
			printf '%b\n' "$(_C_RED)[ERR]$(_C_RESET)  $(BIN_DIR)/$$bin 不存在，请先 make build"; \
			exit 1; \
		fi; \
	done
	@# 创建临时打包目录
	@rm -rf /tmp/_pkg_$(PROJECT_NAME)
	@mkdir -p /tmp/_pkg_$(PROJECT_NAME)/bin
	@# 复制二进制
	@for bin in $(BINARIES); do \
		cp "$(BIN_DIR)/$$bin" "/tmp/_pkg_$(PROJECT_NAME)/bin/"; \
		chmod +x "/tmp/_pkg_$(PROJECT_NAME)/bin/$$bin"; \
	done
	@# 复制 VERSION
	@if [ -f VERSION ]; then cp VERSION /tmp/_pkg_$(PROJECT_NAME)/; fi
	@# 复制项目定义的额外文件
	@for f in $(PACKAGE_FILES); do \
		if [ -e "$$f" ]; then \
			cp -r "$$f" /tmp/_pkg_$(PROJECT_NAME)/; \
		fi; \
	done
	@# 生成压缩包
	@mkdir -p $(DIST_DIR)
	@tar -czf $(ARCHIVE_PATH) -C /tmp/_pkg_$(PROJECT_NAME) .
	@rm -rf /tmp/_pkg_$(PROJECT_NAME)
	@# 生成校验和
	@cd $(DIST_DIR) && sha256sum $(ARCHIVE_NAME) > $(ARCHIVE_NAME).sha256
	@printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    $(ARCHIVE_PATH) ($$(du -h $(ARCHIVE_PATH) | cut -f1))"
	@printf '%b\n' "        sha256: $$(cat $(DIST_DIR)/$(ARCHIVE_NAME).sha256 | cut -d' ' -f1)"

tar: package ## 别名: tar → package

# ============================================================
# 4. release — 创建 tag 并发布
# ============================================================
release: pre-release _do-release ## 创建 git tag 并发布到 GitHub

_do-release:
	@printf '%b\n' "$(_C_BLUE)[REL]$(_C_RESET)  $(PROJECT_NAME) v$(VERSION)"
	@# 创建 tag
	@if git rev-parse "v$(VERSION)" >/dev/null 2>&1; then \
		printf '%b\n' "$(_C_YELLOW)[WARN]$(_C_RESET) 标签 v$(VERSION) 已存在，跳过创建"; \
	else \
		git tag -a "v$(VERSION)" -m "Release $(PROJECT_NAME) v$(VERSION)"; \
		printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    已创建标签: v$(VERSION)"; \
	fi
	@# 推送 tag
	@git push origin "v$(VERSION)" 2>/dev/null && \
		printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    已推送标签到远程" || \
		printf '%b\n' "$(_C_YELLOW)[WARN]$(_C_RESET) 推送失败 (无远程或已存在)"
	@# GitHub Release (如果 gh 可用且有包文件)
	@if command -v gh >/dev/null 2>&1; then \
		if [ -f "$(ARCHIVE_PATH)" ]; then \
			if gh release view "v$(VERSION)" >/dev/null 2>&1; then \
				printf '%b\n' "$(_C_YELLOW)[WARN]$(_C_RESET) Release v$(VERSION) 已存在，上传附件..."; \
				gh release upload "v$(VERSION)" "$(ARCHIVE_PATH)" "$(ARCHIVE_PATH).sha256" --clobber; \
			else \
				gh release create "v$(VERSION)" \
					"$(ARCHIVE_PATH)" \
					"$(ARCHIVE_PATH).sha256" \
					--title "$(PROJECT_NAME) v$(VERSION)" \
					--notes "Release $(PROJECT_NAME) v$(VERSION) for $(PLATFORM)"; \
			fi; \
			printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    GitHub Release 完成"; \
		else \
			printf '%b\n' "$(_C_YELLOW)[WARN]$(_C_RESET) 包文件不存在，请先 make package"; \
		fi; \
	else \
		printf '%b\n' "$(_C_YELLOW)[INFO]$(_C_RESET) 安装 gh CLI 可自动创建 GitHub Release"; \
	fi

tag: ## 创建 git tag v$(VERSION)
	@if git rev-parse "v$(VERSION)" >/dev/null 2>&1; then \
		printf '%b\n' "$(_C_RED)[ERR]$(_C_RESET)  标签 v$(VERSION) 已存在"; \
		exit 1; \
	fi
	@git tag -a "v$(VERSION)" -m "Release $(PROJECT_NAME) v$(VERSION)"
	@printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    已创建标签: v$(VERSION)"

version: ## 显示版本号
	@echo "$(VERSION)"

# ============================================================
# 辅助目标
# ============================================================
pkg-clean: ## 清理构建产物
	@printf '%b\n' "$(_C_YELLOW)[CLEAN]$(_C_RESET) 清理构建产物..."
	rm -rf $(RELEASE_DIR) $(DIST_DIR) build/
	@printf '%b\n' "$(_C_GREEN)[OK]$(_C_RESET)    清理完成"

pkg-info: ## 显示打包配置
	@echo "========================================"
	@echo " $(PROJECT_NAME) v$(VERSION) — 打包配置"
	@echo "========================================"
	@echo "  PLATFORM     : $(PLATFORM)"
	@echo "  BINARIES     : $(BINARIES)"
	@echo "  BIN_DIR      : $(BIN_DIR)"
	@echo "  DIST_DIR     : $(DIST_DIR)"
	@echo "  ARCHIVE      : $(ARCHIVE_NAME)"
	@echo "  BUILD_SCRIPT : $(BUILD_SCRIPT)"
	@echo "  INSTALL_DIR  : $(or $(INSTALL_DIR),(未设置 VTOOL_HOME))"
	@echo "  PACKAGE_FILES: $(PACKAGE_FILES)"
	@echo "========================================"
	@for bin in $(BINARIES); do \
		if [ -f "$(BIN_DIR)/$$bin" ]; then \
			echo "  [存在] $(BIN_DIR)/$$bin ($$(du -h $(BIN_DIR)/$$bin | cut -f1))"; \
		else \
			echo "  [缺失] $(BIN_DIR)/$$bin"; \
		fi; \
	done

# ── 默认钩子 (空实现，项目可覆盖) ──
pre-build::
post-build::
pre-package::
post-package::
pre-release::
