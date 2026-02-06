# This file handles the import of existing resources to prevent "ResourceExistsException"
# Terraform 1.5+ allows import blocks directly in configuration.

# Replace 'YOUR_ACCOUNT_ID' with your actual AWS Account ID
# This tells Terraform to adopt the existing secret into the state

import {
  to = aws_secretsmanager_secret.db_credentials
  id = "arn:aws:secretsmanager:ap-south-1:6617-2281-8226:secret:cdc-pipeline-prod-db-credentials"
}