# ---------- Azure Static Web Apps: the React dashboard ----------
# Terraform creates the site; deploy.ps1 builds frontend/ with the API URL and uploads it with the
# site's deployment token. Free tier: global CDN and HTTPS included.

resource "azurerm_static_web_app" "dashboard" {
  name                = "swa-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.static_web_app_location
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = var.tags
}
