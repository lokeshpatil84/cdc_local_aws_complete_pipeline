# ============================================================
# Terraform Backend Configuration
# ============================================================
# This file configures the S3 backend for state storage
# 
# IMPORTANT: Before running terraform init, ensure the S3 bucket
# and DynamoDB table are created using terraform-bootstrap
# (see terraform-bootstrap/ directory)
#
# The bucket and table names are overridden via:
# 1. -backend-config flags (recommended for CI/CD)
# 2. backend.hcl file (for local development)
# 3. Environment variables (TF_VAR_*)
#
# ============================================================

terraform {
  backend "s3" {
    # These values are OVERRIDDEN by -backend-config flags
    # Default values are only used when no override is provided

    bucket         = "cdc-pipeline-tfstate-dev"        # Override via -backend-config="bucket=your-bucket"
    key            = "terraform.tfstate"               # State file path
    region         = "ap-south-1"                      # Override via -backend-config="region=your-region"
    encrypt        = true                              # Server-side encryption
    dynamodb_table = "cdc-pipeline-terraform-lock-dev" # Override via -backend-config="dynamodb_table=your-table"
  }
}

