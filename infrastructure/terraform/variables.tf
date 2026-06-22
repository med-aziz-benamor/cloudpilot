variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "cloudpilot"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "westeurope"
}

variable "aks_node_count" {
  description = "Number of AKS nodes"
  type        = number
  default     = 2
}

variable "aks_node_vm_size" {
  description = "AKS node VM size"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "pg_admin_user" {
  description = "PostgreSQL admin username"
  type        = string
  default     = "cpadmin"
}

variable "pg_admin_password" {
  description = "PostgreSQL admin password"
  type        = string
  sensitive   = true
}

variable "pg_sku" {
  description = "PostgreSQL flexible server SKU"
  type        = string
  default     = "GP_Standard_D2s_v3"
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default = {
    project = "cloudpilot"
    owner   = "aziz-benamor"
    env     = "production"
  }
}
