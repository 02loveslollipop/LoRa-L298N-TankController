variable "region" {
  description = "AWS region to deploy the relay into"
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name used for tagging the Mediamtx resources"
  type        = string
  default     = "mediamtx-relay"
}

variable "publish_user" {
  description = "Username that the SBC uses to publish the RTSP feed"
  type        = string
}

variable "publish_pass" {
  description = "Password paired with publish_user"
  type        = string
  sensitive   = true
}

variable "viewer_user" {
  description = "Username required for viewers (set to 'any' to allow anonymous access)"
  type        = string
  default     = "any"
}

variable "viewer_pass" {
  description = "Password for viewer access"
  type        = string
  default     = ""
  sensitive   = true
}

variable "allowed_cidrs" {
  description = "CIDR blocks allowed to reach the relay ports"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "instance_type" {
  description = "EC2 instance type used for Mediamtx"
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "Optional EC2 key pair name for SSH access"
  type        = string
  default     = "orion"
}

variable "vpc_id" {
  description = "Optional VPC ID. Defaults to the account's default VPC"
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Optional subnet ID. Defaults to the first subnet in the selected VPC"
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "existing_eip_allocation_id" {
  description = "Optional allocation ID of an existing Elastic IP to attach to the instance"
  type        = string
  default     = null
}

variable "mediamtx_version" {
  description = "Mediamtx container version to run"
  type        = string
  default     = "1.15.3"
}

variable "log_level" {
  description = "Mediamtx log level"
  type        = string
  default     = "info"
}
