# ---------- Azure Container Apps: the FastAPI backend ----------

# Created with azapi because azurerm cannot set environmentMode. Without it Azure now creates an
# "Express" environment, which has fewer features. WorkloadProfiles mode with only the Consumption
# profile is still pay-per-use and scales to zero.
resource "azapi_resource" "environment" {
  type                      = "Microsoft.App/managedEnvironments@2026-07-01"
  name                      = "cae-${local.name}-wp"
  parent_id                 = azurerm_resource_group.main.id
  location                  = azurerm_resource_group.main.location
  tags                      = var.tags
  schema_validation_enabled = false # API version is newer than the provider's bundled schema

  body = {
    properties = {
      environmentMode = "WorkloadProfiles"
      workloadProfiles = [
        { name = "Consumption", workloadProfileType = "Consumption" }
      ]
    }
  }

  # The Log Analytics key is kept out of plan output
  sensitive_body = {
    properties = {
      appLogsConfiguration = {
        destination = "log-analytics"
        logAnalyticsConfiguration = {
          customerId = azurerm_log_analytics_workspace.main.workspace_id
          sharedKey  = azurerm_log_analytics_workspace.main.primary_shared_key
        }
      }
    }
  }
}

resource "azurerm_container_app" "api" {
  name                         = "${var.prefix}-api"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azapi_resource.environment.id
  workload_profile_name        = "Consumption"
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  # Key Vault references: the values stay in Key Vault and are read with the managed identity
  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "admin-password"
    key_vault_secret_id = azurerm_key_vault_secret.admin_password.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "auth-secret"
    key_vault_secret_id = azurerm_key_vault_secret.auth_secret.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    # Data is in PostgreSQL, but the two-step revoke keeps its short-lived confirmations in memory,
    # so both steps must reach the same replica.
    max_replicas = 1

    container {
      name   = "api"
      image  = local.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "VIGIL_DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name  = "VIGIL_ADMIN_USER"
        value = var.admin_username
      }

      env {
        name        = "VIGIL_ADMIN_PASSWORD"
        secret_name = "admin-password"
      }

      env {
        name        = "VIGIL_AUTH_SECRET"
        secret_name = "auth-secret"
      }

      # The dashboard on Static Web Apps calls this API from its own origin
      env {
        name  = "VIGIL_CORS_ORIGINS"
        value = "https://${azurerm_static_web_app.dashboard.default_host_name}"
      }

      # The first start loads data/ into the empty database, so allow up to 5 minutes
      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/api/health"
        interval_seconds        = 10
        failure_count_threshold = 30
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }
    }

    http_scale_rule {
      name                = "http"
      concurrent_requests = "50"
    }
  }

  lifecycle {
    precondition {
      condition     = var.image_tag != ""
      error_message = "image_tag is empty. Run deploy.ps1, which builds the image before creating the app."
    }
  }

  depends_on = [
    azurerm_role_assignment.acr_pull,
    azurerm_postgresql_flexible_server_firewall_rule.azure_services,
  ]
}
