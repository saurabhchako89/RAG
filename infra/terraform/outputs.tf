output "instance_public_ip" {
  description = "Public IP address of the OCI instance"
  value       = oci_core_instance.rag_instance.public_ip
}

output "instance_ocid" {
  description = "OCID of the OCI instance"
  value       = oci_core_instance.rag_instance.id
}
