# Terraform Backend Configuration (S3)
# This file is committed to GitHub for infrastructure reproducibility
# Sensitive values can be overridden via GitHub Secrets or CLI flags

# IMPORTANT: Before running terraform init, ensure the S3 bucket and DynamoDB table
# are created using terraform-bootstrap (see terraform-bootstrap/ directory)

bucket = "cdc-pipeline-tfstate-dev"
key    = "terraform.tfstate"
region = "ap-south-1"

# For production, override with environment-specific values:
# terraform init -backend-config=backend.hcl -backend-config="bucket=your-prod-bucket" -backend-config="key=prod/terraform.tfstate" -backend-config="region=your-region"

