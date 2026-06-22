###############################################################################
# CloudPilot — Azure infrastructure (AKS + PostgreSQL + Redis)
# Read-only-by-design platform; this provisions the hosting infra only.
###############################################################################

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "cloudpilot" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

module "aks" {
  source              = "./modules/aks"
  prefix              = var.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.cloudpilot.name
  node_count          = var.aks_node_count
  node_vm_size        = var.aks_node_vm_size
  tags                = var.tags
}

resource "azurerm_postgresql_flexible_server" "db" {
  name                   = "${var.prefix}-pg"
  resource_group_name    = azurerm_resource_group.cloudpilot.name
  location               = var.location
  version                = "16"
  administrator_login    = var.pg_admin_user
  administrator_password = var.pg_admin_password
  sku_name               = var.pg_sku
  storage_mb             = 32768
  zone                   = "1"
  tags                   = var.tags
}

resource "azurerm_postgresql_flexible_server_database" "cloudpilot" {
  name      = "cloudpilot"
  server_id = azurerm_postgresql_flexible_server.db.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_redis_cache" "cache" {
  name                = "${var.prefix}-redis"
  resource_group_name = azurerm_resource_group.cloudpilot.name
  location            = var.location
  capacity            = 1
  family              = "C"
  sku_name            = "Standard"
  minimum_tls_version = "1.2"
  tags                = var.tags
}
