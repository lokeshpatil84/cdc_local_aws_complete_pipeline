# Terraform Backend Configuration
# This file configures the S3 backend for state storage
# IMPORTANT: Before running terraform init, ensure the S3 bucket and DynamoDB table
# are created using terraform-bootstrap (see terraform-bootstrap/ directory)

terraform {
  backend "s3" {
    # Bucket and table names are overridden via backend-config or environment variables
    # Default values for local testing:
    bucket         = "cdc-pipeline-tfstate-dev"
    key            = "terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    dynamodb_table = "cdc-pipeline-terraform-lock-dev"
  }
}

