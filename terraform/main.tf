# SSH Key
resource "hcloud_ssh_key" "main" {
  name       = "noyau-deploy"
  public_key = var.ssh_public_key
}

# Firewall
resource "hcloud_firewall" "main" {
  name = "noyau-firewall"

  # SSH - restricted to specific IP
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = [var.ssh_allowed_ip]
  }

  # HTTP
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Allow all outbound
  rule {
    direction       = "out"
    protocol        = "tcp"
    port            = "1-65535"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction       = "out"
    protocol        = "udp"
    port            = "1-65535"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction       = "out"
    protocol        = "icmp"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }
}

# Server
resource "hcloud_server" "main" {
  name         = var.server_name
  image        = "ubuntu-24.04"
  server_type  = var.server_type
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.main.id]
  firewall_ids = [hcloud_firewall.main.id]

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    # Core
    domain            = var.domain_name
    neon_database_url = var.neon_database_url
    secret_key        = var.secret_key
    openai_api_key    = var.openai_api_key
    resend_api_key    = var.resend_api_key

    # GitHub
    github_username = var.github_username
    github_token    = var.github_token
    github_repo     = var.github_repo

    # Twitter/Nitter
    twitter_username    = var.twitter_username
    twitter_password    = var.twitter_password
    twitter_totp_secret = var.twitter_totp_secret

    # Twitter API v2 (posting)
    twitter_api_key             = var.twitter_api_key
    twitter_api_secret          = var.twitter_api_secret
    twitter_access_token        = var.twitter_access_token
    twitter_access_token_secret = var.twitter_access_token_secret

    # LLM
    llm_model = var.llm_model

    # Scheduler
    scheduler_enabled = var.scheduler_enabled

    # Analytics
    posthog_api_key = var.posthog_api_key
    posthog_host    = var.posthog_host

    # Verifalia
    verifalia_username        = var.verifalia_username
    verifalia_password        = var.verifalia_password
    verifalia_quality         = var.verifalia_quality
    verifalia_timeout         = var.verifalia_timeout
    verifalia_cache_ttl_hours = var.verifalia_cache_ttl_hours

    # Discord
    discord_webhook_url       = var.discord_webhook_url
    discord_error_webhook_url = var.discord_error_webhook_url

    # Video
    video_enabled           = var.video_enabled
    pexels_api_key          = var.pexels_api_key
    freesound_client_id     = var.freesound_client_id
    freesound_client_secret = var.freesound_client_secret
    tts_provider            = var.tts_provider
    elevenlabs_api_key      = var.elevenlabs_api_key
    youtube_client_id       = var.youtube_client_id
    youtube_client_secret   = var.youtube_client_secret
    youtube_refresh_token   = var.youtube_refresh_token

    # S3
    s3_bucket_name       = var.s3_bucket_name
    s3_region            = var.s3_region
    s3_access_key_id     = var.s3_access_key_id
    s3_secret_access_key = var.s3_secret_access_key
    s3_endpoint_url      = var.s3_endpoint_url
    s3_public_url        = var.s3_public_url

    # TikTok
    tiktok_client_key    = var.tiktok_client_key
    tiktok_client_secret = var.tiktok_client_secret
    tiktok_access_token  = var.tiktok_access_token
    tiktok_refresh_token = var.tiktok_refresh_token
    tiktok_redirect_uri  = var.tiktok_redirect_uri

    # Instagram
    instagram_app_id              = var.instagram_app_id
    instagram_app_secret          = var.instagram_app_secret
    instagram_business_account_id = var.instagram_business_account_id
    instagram_access_token        = var.instagram_access_token
  })

  labels = {
    app = "noyau"
    env = "production"
  }

  lifecycle {
    ignore_changes = [
      user_data,
    ]
  }
}
