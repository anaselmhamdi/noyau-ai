output "server_ip" {
  description = "Public IPv4 address of the server"
  value       = hcloud_server.main.ipv4_address
}

output "server_ipv6" {
  description = "Public IPv6 address of the server"
  value       = hcloud_server.main.ipv6_address
}

output "server_id" {
  description = "Hetzner server ID"
  value       = hcloud_server.main.id
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh root@${hcloud_server.main.ipv4_address}"
}

output "dns_instructions" {
  description = "DNS configuration instructions"
  value       = <<-EOT
    Configure DNS records for ${var.domain_name}:

    A record:    ${var.domain_name} -> ${hcloud_server.main.ipv4_address}
    AAAA record: ${var.domain_name} -> ${hcloud_server.main.ipv6_address}

    Caddy will automatically provision TLS certificates via Let's Encrypt.
  EOT
}

output "deployment_instructions" {
  description = "Post-deployment instructions"
  value       = <<-EOT
    After terraform apply:

    1. Copy config files to server:
       scp config.yml Caddyfile root@${hcloud_server.main.ipv4_address}:/opt/noyau/

    2. SSH into the server and start services:
       ssh root@${hcloud_server.main.ipv4_address}
       cd /opt/noyau
       docker compose pull
       docker compose up -d

    3. Run initial migrations:
       docker compose exec api alembic upgrade head

    4. Start timers:
       systemctl start noyau-hourly.timer noyau-daily.timer noyau-backup.timer
  EOT
}

output "ghcr_image" {
  description = "GHCR image URL for the API"
  value       = "ghcr.io/${var.github_repo}-api:latest"
}

output "github_secrets_needed" {
  description = "GitHub Secrets to configure for CI/CD"
  value       = <<-EOT
    Add these secrets to GitHub (Settings > Secrets > Actions):

    HETZNER_HOST     = ${hcloud_server.main.ipv4_address}
    HETZNER_USER     = root
    HETZNER_SSH_KEY  = (contents of your private key file)
    FLY_API_TOKEN    = (from: flyctl tokens create deploy)
  EOT
}
