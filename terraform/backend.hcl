# ============================================================
# Terraform Backend Configuration (HCL format)
# ============================================================
# This file is used for local development with:
#   terraform init -backend-config=backend.hcl
#
# For CI/CD, values are passed via -backend-config flags
# (see .github/workflows/cd-main.yml)
#
# ============================================================

bucket         = "cdc-pipeline-tfstate-dev"
key            = "terraform.tfstate"
region         = "ap-south-1"
encrypt        = true
dynamodb_table = "cdc-pipeline-terraform-lock-dev"

