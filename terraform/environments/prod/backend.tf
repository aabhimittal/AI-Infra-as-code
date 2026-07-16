# =============================================================================
# Terraform settings + remote state backend for the prod environment.
#
# The S3 backend below is commented out on purpose - it references
# account-specific resources (bucket, DynamoDB lock table) that must be
# created out-of-band (or via a small bootstrap stack) before `terraform
# init` can use them. Uncomment and adjust before running init in a real
# account. For prod specifically, also enable S3 bucket versioning + a
# restrictive bucket policy on the state bucket.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # backend "s3" {
  #   bucket         = "myapp-terraform-state-prod"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "myapp-terraform-locks"
  #   encrypt        = true
  # }
}
