# Mediamtx Relay Terraform Stack

This module provisions everything required to host the relay on a single EC2 instance with an attached Elastic IP. The instance boots Amazon Linux 2023, installs Docker, writes the Mediamtx configuration, and launches the upstream `bluenviron/mediamtx` container with all required TCP and UDP ports published.

## What gets created

- Security group exposing TCP `8554`, `1935`, `8888`, `8889`, `9998`, `9999` and UDP `8200` to the CIDR list you supply.
- When `domain_name` is set, TCP `80` and `443` are also opened for the TLS proxy.
- EC2 instance (default `t3.small`) running in the chosen subnet/VPC.
- User data script that installs Docker and runs Mediamtx with the configuration rendered from Terraform inputs.
- Optional Caddy reverse proxy that fetches Let's Encrypt certificates for the supplied domain and fronts the Mediamtx HTTP/WebRTC endpoints.
- Elastic IP associated with the instance for a stable ingress point.
	- If you supply `existing_eip_allocation_id`, the module reuses that Elastic IP instead of allocating a new one.

You can optionally set `vpc_id`, `subnet_id`, or `key_name` to place the instance in a specific network or enable SSH access.

Key variables:

| Name | Description | Default |
| --- | --- | --- |
| `region` | AWS region to deploy into | `us-east-1` |
| `instance_type` | EC2 instance type | `t3.small` |
| `publish_user` / `publish_pass` | Credentials the SBC uses to publish | **required** |
| `viewer_user` / `viewer_pass` | Playback credentials (`viewer_user=any` allows anonymous access) | `any` / empty |
| `allowed_cidrs` | List of CIDR blocks allowed to reach the relay | `["0.0.0.0/0"]` |
| `key_name` | EC2 key pair used for SSH access | `orion` |
| `existing_eip_allocation_id` | Allocation ID of an existing Elastic IP to reuse | `null` |
| `mediamtx_version` | Container tag pulled from Docker Hub | `1.15.3` |
| `domain_name` | FQDN used to request a Let's Encrypt certificate (enables the Caddy TLS proxy) | `null` |
| `tags` | Extra tags applied to every resource | `{}` |

## Scaling & updates

- **Scale vertically:** change `instance_type` and re-apply.
- **Rotate credentials or config:** update the related variables and run `terraform apply`; the user data script re-renders the config and restarts the container on the next reboot. To force an immediate restart, use `terraform taint aws_instance.mediamtx` followed by `terraform apply`.
- **Tear down:** run `terraform destroy` to remove the EC2 instance, security group, and Elastic IP.

## GitHub Actions automation

The `Deploy Infrastructure and Services` workflow expects a base64-encoded `terraform.tfvars` stored in the repository secret `MEDIA_RELAY_TFVARS_B64`. To generate it locally:

```bash
cd infra/terraform/media_relay
terraform fmt
cat terraform.tfvars | base64 -w0   # on macOS: cat terraform.tfvars | base64 | tr -d '\n'
```

Copy the output into the GitHub secret. The workflow decodes the file into `terraform.tfvars` before running `terraform init` and `terraform apply`.

## terraform.tfvars example

Create a `terraform.tfvars` (or copy `terraform.tfvars.example` if you create one) to store sensitive values locally:

```hcl
region        = "us-east-1"
publish_user  = "robot"
publish_pass  = "change-me"
viewer_user   = "any"
viewer_pass   = ""
allowed_cidrs = ["203.0.113.0/24", "198.51.100.10/32"]
#domain_name   = "stream.example.com"
#existing_eip_allocation_id = "eipalloc-0123456789abcdef0"
```

Never commit files that contain secrets.