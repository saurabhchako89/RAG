variable "user_ocid" {
  description = "OCI user OCID"
  type        = string
}

variable "fingerprint" {
  description = "OCI API key fingerprint"
  type        = string
}

variable "tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
}

variable "region" {
  description = "OCI region"
  type        = string
}

variable "private_key" {
  description = "Private key contents for OCI API"
  type        = string
  sensitive   = true
}

variable "compartment_id" {
  description = "Compartment OCID for infrastructure"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
}

variable "github_owner" {
  description = "GitHub organization or username"
  type        = string
}

variable "github_repo" {
  description = "Repository name containing the RAG app"
  type        = string
}

variable "github_token" {
  description = "GitHub token used to clone repo and pull GHCR images"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "Optional OpenAI API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Optional Anthropic (Claude) API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "groq_api_key" {
  description = "Optional Groq API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "gemini_api_key" {
  description = "Optional Google Gemini API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "deepseek_api_key" {
  description = "Optional DeepSeek API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_repos" {
  description = "Comma-separated list of owner/repo to sync (GitHub connector)"
  type        = string
  default     = ""
}

variable "notion_token" {
  description = "Optional Notion integration token"
  type        = string
  default     = ""
  sensitive   = true
}

variable "notion_database_ids" {
  description = "Comma-separated Notion database IDs to sync"
  type        = string
  default     = ""
}

variable "allowed_ssh_cidr" {
  description = "CIDR range allowed to SSH"
  type        = string
  default     = "0.0.0.0/0"
}

variable "allowed_web_cidr" {
  description = "CIDR range allowed to reach HTTP/Backend"
  type        = string
  default     = "0.0.0.0/0"
}

variable "instance_shape" {
  description = "Compute shape"
  type        = string
  default     = "VM.Standard.E2.1.Micro"
}

variable "boot_volume_size" {
  description = "Boot volume size in GB"
  type        = number
  default     = 50
}

variable "deployment_trigger" {
  description = "Increment to force reprovision"
  type        = number
  default     = 1
}

variable "oci_bucket_name" {
  description = "OCI Object Storage bucket name for document uploads"
  type        = string
  default     = ""
}

variable "oci_namespace" {
  description = "OCI Object Storage namespace (tenancy namespace)"
  type        = string
  default     = ""
}
