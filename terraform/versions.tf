terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.20"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.2"
    }
  }
}

# Same Azure CLI login and ARM_SUBSCRIPTION_ID as azurerm
provider "azapi" {}

# The subscription comes from ARM_SUBSCRIPTION_ID (deploy.ps1 sets it from `az account show`)
# and authentication from the Azure CLI login.
provider "azurerm" {
  features {
    resource_group {
      # destroy.ps1 must be able to remove the group even if something was added by hand.
      prevent_deletion_if_contains_resources = false
    }

    key_vault {
      # destroy.ps1 removes the vault completely, so a redeploy can reuse names
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}
