variable "location" {
  description = "Azure region for every resource."
  type        = string
  default     = "koreacentral"
}

variable "prefix" {
  description = "Short lowercase name used in every resource name."
  type        = string
  default     = "vigil"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,11}$", var.prefix))
    error_message = "prefix must be 2-12 lowercase letters or digits, starting with a letter."
  }
}

variable "static_web_app_location" {
  description = "Region for Azure Static Web Apps (only centralus, eastus2, westus2, westeurope, eastasia offer it)."
  type        = string
  default     = "eastasia"
}

variable "postgres_location" {
  description = "Region for PostgreSQL. Empty = same as location. Student subscriptions cannot create B1ms in every region (SkuNotAvailable)."
  type        = string
  default     = ""
}

variable "postgres_sku" {
  description = "PostgreSQL Flexible Server size. B_Standard_B1ms is the smallest (1 vCore, 2 GB)."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "16"
}

variable "image_tag" {
  description = "Tag of the vigil image in the registry. Empty only during the first, base-only apply."
  type        = string
  default     = ""
}

variable "admin_username" {
  description = "Super admin created when the container starts."
  type        = string
  default     = "superadmin"
}

variable "admin_password" {
  description = "Super admin password. Leave null to have Terraform generate one."
  type        = string
  default     = null
  sensitive   = true
}

variable "min_replicas" {
  description = "0 scales to zero when idle (cheapest). 1 keeps one replica always warm."
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1], var.min_replicas)
    error_message = "min_replicas must be 0 or 1 (the API runs a single replica)."
  }
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project    = "vigil"
    managed_by = "terraform"
  }
}
