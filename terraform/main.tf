# Vigil on Azure. See DEPLOYMENT.md for the architecture and resource list.
#
#   main.tf        resource group, names, generated secrets, container registry, identity, logs
#   database.tf    Azure Database for PostgreSQL Flexible Server      (data)
#   keyvault.tf    Azure Key Vault                                     (secrets)
#   api.tf         Azure Container Apps environment + API app          (FastAPI backend)
#   frontend.tf    Azure Static Web Apps                               (React dashboard)
#
# deploy.ps1 applies this in two passes:
#   1. base resources (resource group, registry, identity, AcrPull) so the image can be built and pushed,
#   2. everything else, with image_tag set to the image it just pushed.

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

resource "random_password" "admin" {
  length           = 20
  special          = true
  override_special = "!@#%^*-_=+"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

# Signs login tokens. Fixed per deployment so sessions survive restarts and new revisions.
resource "random_password" "auth_secret" {
  length  = 64
  special = false
}

locals {
  name           = "${var.prefix}-${random_string.suffix.result}"
  admin_password = coalesce(var.admin_password, random_password.admin.result)
  image          = "${azurerm_container_registry.main.login_server}/vigil:${var.image_tag}"
}

# ---------- Base (pass 1) ----------

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = var.tags
}

resource "azurerm_container_registry" "main" {
  name                = "acr${var.prefix}${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.tags
}

# The API's identity: pulls the image from the registry and reads its secrets from Key Vault.
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  principal_type       = "ServicePrincipal"
}

# ---------- Shared (pass 2) ----------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}
