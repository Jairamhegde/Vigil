# ---------- Azure Database for PostgreSQL Flexible Server ----------
# Holds identities, accounts, entitlements, audit events, risk metrics, the revocation log and the
# dashboard users. The API creates the tables and loads data/ on its first start.

resource "random_password" "db" {
  length  = 32
  special = false # used inside the connection URL, so keep it URL-safe
}

locals {
  postgres_location = coalesce(var.postgres_location, azurerm_resource_group.main.location)
}

resource "azurerm_postgresql_flexible_server" "main" {
  # The region is part of the name: a server name stays reserved in its old region for a while,
  # so moving the database to another region must not reuse it.
  name                          = "psql-${local.name}-${local.postgres_location}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = local.postgres_location
  version                       = var.postgres_version
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true # locked down by the firewall rule below
  administrator_login           = "vigiladmin"
  administrator_password        = random_password.db.result
  tags                          = var.tags

  authentication {
    password_auth_enabled         = true
    active_directory_auth_enabled = false
  }

  lifecycle {
    # Azure picks an availability zone on create; do not fight it on later applies
    ignore_changes = [zone, high_availability]
  }
}

resource "azurerm_postgresql_flexible_server_database" "vigil" {
  name      = "vigil"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# 0.0.0.0 - 0.0.0.0 is Azure's "allow access from Azure services": the Container App can connect,
# the public internet cannot. Connections must use TLS (require_secure_transport is on by default).
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

locals {
  database_url = format(
    "postgresql://%s:%s@%s:5432/%s?sslmode=require",
    azurerm_postgresql_flexible_server.main.administrator_login,
    random_password.db.result,
    azurerm_postgresql_flexible_server.main.fqdn,
    azurerm_postgresql_flexible_server_database.vigil.name,
  )
}
