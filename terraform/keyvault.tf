# ---------- Azure Key Vault ----------
# The database connection string, the super admin password and the token-signing key live here.
# The Container App reads them at runtime with its managed identity; they never sit in the app config.

resource "azurerm_key_vault" "main" {
  name                       = "kv-${local.name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false # so destroy.ps1 can remove it completely
  tags                       = var.tags

  # Whoever runs deploy.ps1 writes the secrets (and can purge them on destroy)
  access_policy {
    tenant_id          = data.azurerm_client_config.current.tenant_id
    object_id          = data.azurerm_client_config.current.object_id
    secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
  }

  # The API only reads
  access_policy {
    tenant_id          = data.azurerm_client_config.current.tenant_id
    object_id          = azurerm_user_assigned_identity.app.principal_id
    secret_permissions = ["Get", "List"]
  }
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = local.database_url
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "admin_password" {
  name         = "admin-password"
  value        = local.admin_password
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "auth_secret" {
  name         = "auth-secret"
  value        = random_password.auth_secret.result
  key_vault_id = azurerm_key_vault.main.id
}
