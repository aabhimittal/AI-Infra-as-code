# AI-Infra-as-Code — convenience targets.
# Usage: `make help`

ENV      ?= dev
STACK    ?= dev
WORKLOAD ?= ai-optimizer/examples/workload-$(ENV).yaml
TF_DIR   := terraform/environments/$(ENV)

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---- AI optimizer ------------------------------------------------------- #
.PHONY: optimizer-install optimizer-test optimize
optimizer-install: ## Install the ai-optimizer package (editable)
	cd ai-optimizer && pip install -e ".[dev]"

optimizer-test: ## Run the ai-optimizer test suite
	cd ai-optimizer && python -m unittest discover -s tests -v

optimize: ## Optimize infra for WORKLOAD and emit tfvars/pulumi (ENV=dev|staging|prod)
	cd ai-optimizer && python -m aiopt.cli optimize \
		-w examples/workload-$(ENV).yaml --emit-dir ../out/$(ENV) --stack $(STACK)

# ---- Terraform ---------------------------------------------------------- #
.PHONY: tf-init tf-plan tf-apply tf-destroy tf-fmt tf-validate
tf-init: ## terraform init for ENV
	cd $(TF_DIR) && terraform init

tf-plan: ## terraform plan for ENV
	cd $(TF_DIR) && terraform plan

tf-apply: ## terraform apply for ENV
	cd $(TF_DIR) && terraform apply

tf-destroy: ## terraform destroy for ENV
	cd $(TF_DIR) && terraform destroy

tf-fmt: ## terraform fmt (recursive)
	terraform fmt -recursive terraform

tf-validate: ## terraform validate for ENV
	cd $(TF_DIR) && terraform init -backend=false && terraform validate

# ---- Pulumi ------------------------------------------------------------- #
.PHONY: pulumi-install pulumi-preview pulumi-up pulumi-destroy
pulumi-install: ## Install Pulumi Python deps
	cd pulumi && pip install -r requirements.txt

pulumi-preview: ## pulumi preview for STACK
	cd pulumi && pulumi preview --stack $(STACK)

pulumi-up: ## pulumi up for STACK
	cd pulumi && pulumi up --stack $(STACK)

pulumi-destroy: ## pulumi destroy for STACK
	cd pulumi && pulumi destroy --stack $(STACK)
