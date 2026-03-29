terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
  
  backend "local" {
    path = "/tmp/terraform-rag.tfstate"
  }
}

provider "oci" {
  region              = var.region
  user_ocid           = var.user_ocid
  fingerprint         = var.fingerprint
  private_key         = var.private_key
  tenancy_ocid        = var.tenancy_ocid
  retry_duration_seconds = 60
}

# Get availability domain
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

# Get Ubuntu image
data "oci_core_images" "ubuntu_images" {
  compartment_id           = var.compartment_id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# Create VCN
resource "oci_core_vcn" "rag_vcn" {
  compartment_id = var.compartment_id
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "rag-vcn"
  dns_label      = "ragvcn"
  
  lifecycle {
    ignore_changes = [defined_tags]
  }
}

# Create Internet Gateway
resource "oci_core_internet_gateway" "rag_igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.rag_vcn.id
  display_name   = "rag-igw"
  enabled        = true
}

# Create Route Table
resource "oci_core_route_table" "rag_route_table" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.rag_vcn.id
  display_name   = "rag-route-table"

  route_rules {
    network_entity_id = oci_core_internet_gateway.rag_igw.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
}

# Create Security List
resource "oci_core_security_list" "rag_security_list" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.rag_vcn.id
  display_name   = "rag-security-list"

  # Ingress Rules
  ingress_security_rules {
    protocol    = "6"
    source      = var.allowed_ssh_cidr
    stateless   = false
    description = "SSH access"
    
    tcp_options {
      min = 22
      max = 22
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = var.allowed_web_cidr
    stateless   = false
    description = "HTTP access to RAG frontend"
    
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = var.allowed_web_cidr
    stateless   = false
    description = "API access to RAG backend"
    
    tcp_options {
      min = 8000
      max = 8000
    }
  }

  egress_security_rules {
    protocol    = "6"
    destination = "0.0.0.0/0"
    stateless   = false
    description = "HTTPS outbound"
    
    tcp_options {
      min = 443
      max = 443
    }
  }

  egress_security_rules {
    protocol    = "6"
    destination = "0.0.0.0/0"
    stateless   = false
    description = "HTTP outbound"
    
    tcp_options {
      min = 80
      max = 80
    }
  }

  egress_security_rules {
    protocol    = "17"
    destination = "0.0.0.0/0"
    stateless   = false
    description = "DNS outbound"
    
    udp_options {
      min = 53
      max = 53
    }
  }
}

# Create Subnet
resource "oci_core_subnet" "rag_subnet" {
  compartment_id      = var.compartment_id
  vcn_id              = oci_core_vcn.rag_vcn.id
  cidr_block          = "10.0.1.0/24"
  display_name        = "rag-subnet"
  dns_label           = "ragsubnet"
  route_table_id      = oci_core_route_table.rag_route_table.id
  security_list_ids   = [oci_core_security_list.rag_security_list.id]
  dhcp_options_id     = oci_core_vcn.rag_vcn.default_dhcp_options_id
}

# Create Compute Instance
resource "oci_core_instance" "rag_instance" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.compartment_id
  display_name        = "rag-application"
  shape               = var.instance_shape
  
  dynamic "shape_config" {
    for_each = var.instance_shape == "VM.Standard.E2.1.Micro" ? [1] : []
    content {
      memory_in_gbs = 1
      ocpus         = 1
    }
  }

  dynamic "shape_config" {
    for_each = var.instance_shape == "VM.Standard.A1.Flex" ? [1] : []
    content {
      memory_in_gbs = 6
      ocpus         = 1
    }
  }

  lifecycle {
    create_before_destroy = true
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.rag_subnet.id
    display_name     = "rag-vnic"
    assign_public_ip = true
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_images.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_size
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    deployment_trigger  = var.deployment_trigger
    user_data = base64encode(templatefile("${path.module}/../scripts/setup-docker.sh", {
      GITHUB_OWNER        = var.github_owner
      GITHUB_TOKEN        = var.github_token
      GITHUB_REPO         = var.github_repo
      GITHUB_REPOS        = var.github_repos
      ANTHROPIC_API_KEY   = var.anthropic_api_key
      OPENAI_API_KEY      = var.openai_api_key
      GROQ_API_KEY        = var.groq_api_key
      GEMINI_API_KEY      = var.gemini_api_key
      DEEPSEEK_API_KEY    = var.deepseek_api_key
      NOTION_TOKEN        = var.notion_token
      NOTION_DATABASE_IDS = var.notion_database_ids
      OCI_BUCKET_NAME     = var.oci_bucket_name
      OCI_NAMESPACE       = var.oci_namespace
      OCI_REGION          = var.region
    }))
  }

  timeouts {
    create = "20m"
  }
}
