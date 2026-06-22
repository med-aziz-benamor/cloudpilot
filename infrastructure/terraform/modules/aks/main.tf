###############################################################################
# AKS module — managed Kubernetes cluster for CloudPilot
###############################################################################

variable "prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "node_count" {
  type    = number
  default = 2
}
variable "node_vm_size" {
  type    = string
  default = "Standard_D2s_v3"
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "${var.prefix}-aks"
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = "${var.prefix}-aks"

  default_node_pool {
    name                = "system"
    node_count          = var.node_count
    vm_size             = var.node_vm_size
    enable_auto_scaling = true
    min_count           = var.node_count
    max_count           = var.node_count + 2
    os_disk_size_gb     = 64
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    network_policy = "calico" # enforce the NetworkPolicies defined for the namespace
  }

  tags = var.tags
}

output "cluster_name" {
  value = azurerm_kubernetes_cluster.aks.name
}

output "kube_config" {
  value     = azurerm_kubernetes_cluster.aks.kube_config_raw
  sensitive = true
}
