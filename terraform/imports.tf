# This file handles the import of existing resources to prevent "ResourceExistsException"
# Terraform 1.5+ allows import blocks directly in configuration.

import {
  to = aws_secretsmanager_secret.db_credentials
  id = "arn:aws:secretsmanager:ap-south-1:661722818226:secret:cdc-pipeline-prod-db-credentials-sXAK91"
}