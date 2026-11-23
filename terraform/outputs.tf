output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "acr_name" {
  value = azurerm_container_registry.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "app_url" {
  description = "The dashboard (Azure Static Web Apps)."
  value       = "https://${azurerm_static_web_app.dashboard.default_host_name}"
}

output "api_url" {
  description = "The API (Azure Container Apps)."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "static_web_app_name" {
  value = azurerm_static_web_app.dashboard.name
}

output "static_web_app_deployment_token" {
  value     = azurerm_static_web_app.dashboard.api_key
  sensitive = true
}

output "postgres_server" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "container_app_name" {
  value = azurerm_container_app.api.name
}

output "admin_username" {
  value = var.admin_username
}

output "admin_password" {
  value     = local.admin_password
  sensitive = true
}
