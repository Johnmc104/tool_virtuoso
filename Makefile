PROJECT_NAME  := virtuoso-bridge
BINARIES      := virtuoso-bridge vbridge
PACKAGE_FILES := README.md docs/ lib/

include packaging/common/packaging.mk

.PHONY: help dev

help: ## 显示所有目标
	@echo "Usage: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## 开发模式安装
	pip install -e virtuoso-bridge-lite/

pre-build::
	@for p in patches/*.patch; do \
		[ -f "$$p" ] && git -C virtuoso-bridge-lite apply ../$$p 2>/dev/null || true; \
	done

post-build::
	@git -C virtuoso-bridge-lite checkout -- . 2>/dev/null || true

pre-package::
	@rm -rf lib && mkdir -p lib
	@cp -r virtuoso-bridge-lite/src/virtuoso_bridge lib/
	@cp -r vbridge lib/
	@find lib -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@cp virtuoso-bridge-lite/pyproject.toml lib/
