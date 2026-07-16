# =============================================================================
# Terraform / provider version constraints for the shared stack module.
#
# This file only declares *requirements*; the actual provider configuration
# (region, credentials, etc.) is supplied by the caller. Since this module is
# always invoked from environments/<env>/main.tf (the true Terraform root),
# provider configuration lives there, not here.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
