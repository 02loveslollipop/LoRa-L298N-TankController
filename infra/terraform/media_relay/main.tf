terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_vpc" "default" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

locals {
  vpc_id = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id
}

data "aws_subnet_ids" "selected" {
  vpc_id = local.vpc_id
}

data "aws_eip" "existing" {
  count = var.existing_eip_allocation_id != null ? 1 : 0
  id    = var.existing_eip_allocation_id
}

locals {
  subnet_id = var.subnet_id != null ? var.subnet_id : data.aws_subnet_ids.selected.ids[0]
  tcp_ports = [8554, 1935, 8888, 8889, 9998, 9999]
  udp_ports = [8200]
  port_rules = concat(
    [for p in local.tcp_ports : {
      port     = p
      protocol = "tcp"
    }],
    [for p in local.udp_ports : {
      port     = p
      protocol = "udp"
    }]
  )
  merged_tags = merge({
    Name = var.name
  }, var.tags)
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  mediamtx_config = templatefile("${path.module}/templates/mediamtx.yaml.tpl", {
    log_level   = var.log_level
    publish_user = var.publish_user
    publish_pass = var.publish_pass
    viewer_user  = var.viewer_user
    viewer_pass  = var.viewer_pass
  })

  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    mediamtx_config = local.mediamtx_config
    mediamtx_version = var.mediamtx_version
  })
}

resource "aws_security_group" "mediamtx" {
  name        = "${var.name}-sg"
  description = "Network rules for the Mediamtx relay"
  vpc_id      = local.vpc_id

  dynamic "ingress" {
    for_each = local.port_rules
    content {
      description = "Allow ${ingress.value.protocol} port ${ingress.value.port}"
      from_port   = ingress.value.port
      to_port     = ingress.value.port
      protocol    = ingress.value.protocol
      cidr_blocks = var.allowed_cidrs
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = local.merged_tags
}

resource "aws_instance" "mediamtx" {
  ami           = data.aws_ami.al2023.id
  instance_type = var.instance_type
  subnet_id     = local.subnet_id

  associate_public_ip_address = true
  key_name                   = var.key_name
  vpc_security_group_ids     = [aws_security_group.mediamtx.id]

  user_data = local.user_data

  tags = local.merged_tags
}

resource "aws_eip" "mediamtx" {
  count    = var.existing_eip_allocation_id == null ? 1 : 0
  domain   = "vpc"
  instance = aws_instance.mediamtx.id
  tags     = local.merged_tags
}

resource "aws_eip_association" "mediamtx" {
  count         = var.existing_eip_allocation_id != null ? 1 : 0
  allocation_id = var.existing_eip_allocation_id
  instance_id   = aws_instance.mediamtx.id
}

output "instance_id" {
  description = "ID of the EC2 instance running Mediamtx"
  value       = aws_instance.mediamtx.id
}

output "elastic_ip" {
  description = "Elastic IP address associated with the relay"
  value = var.existing_eip_allocation_id != null
    ? data.aws_eip.existing[0].public_ip
    : aws_eip.mediamtx[0].public_ip
}

output "public_dns" {
  description = "Public DNS name of the instance"
  value       = aws_instance.mediamtx.public_dns
}

output "security_group_id" {
  description = "Security group controlling relay ingress"
  value       = aws_security_group.mediamtx.id
}
