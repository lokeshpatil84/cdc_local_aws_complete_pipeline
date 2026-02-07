bucket         = "cdc-pipeline-tfstate-dev"
key            = "terraform.tfstate"
region         = "ap-south-1"
encrypt        = true
dynamodb_table = "cdc-pipeline-terraform-lock-dev"

