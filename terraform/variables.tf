variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "SSH public key for server access"
  type        = string
}

variable "ssh_allowed_ip" {
  description = "IP address allowed for SSH access (CIDR notation)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "noyau.news"
}

variable "server_type" {
  description = "Hetzner server type (cx22 = 2 vCPU, 4GB RAM)"
  type        = string
  default     = "cx22"
}

variable "location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "nbg1" # Nuremberg, Germany
}

variable "server_name" {
  description = "Name for the server"
  type        = string
  default     = "noyau-prod"
}

# Application secrets
variable "neon_database_url" {
  description = "Neon PostgreSQL connection string (postgresql://...)"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Application secret key for JWT signing"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "resend_api_key" {
  description = "Resend API key for transactional emails"
  type        = string
  sensitive   = true
}

variable "github_username" {
  description = "GitHub username for GHCR authentication"
  type        = string
}

variable "github_token" {
  description = "GitHub personal access token (read:packages scope) for GHCR"
  type        = string
  sensitive   = true
}

variable "github_repo" {
  description = "GitHub repository in format owner/repo"
  type        = string
}

# Twitter/Nitter credentials for X/Twitter ingestion
variable "twitter_username" {
  description = "Twitter username for Nitter session tokens"
  type        = string
  default     = ""
}

variable "twitter_password" {
  description = "Twitter password for Nitter session tokens"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twitter_totp_secret" {
  description = "Twitter TOTP secret for 2FA (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

# =============================================================================
# Twitter API v2 (for posting)
# =============================================================================

variable "twitter_api_key" {
  description = "Twitter API v2 key for posting digest threads"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twitter_api_secret" {
  description = "Twitter API v2 secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twitter_access_token" {
  description = "Twitter OAuth 1.0a access token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twitter_access_token_secret" {
  description = "Twitter OAuth 1.0a access token secret"
  type        = string
  sensitive   = true
  default     = ""
}

# =============================================================================
# Analytics
# =============================================================================

variable "posthog_api_key" {
  description = "PostHog project API key for analytics"
  type        = string
  default     = ""
}

variable "posthog_host" {
  description = "PostHog host URL"
  type        = string
  default     = "https://eu.i.posthog.com"
}

# =============================================================================
# Email Validation (Verifalia)
# =============================================================================

variable "verifalia_username" {
  description = "Verifalia API username for email validation"
  type        = string
  default     = ""
}

variable "verifalia_password" {
  description = "Verifalia API password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "verifalia_quality" {
  description = "Verifalia validation quality level"
  type        = string
  default     = "Standard"
}

variable "verifalia_timeout" {
  description = "Verifalia request timeout in seconds"
  type        = number
  default     = 30
}

variable "verifalia_cache_ttl_hours" {
  description = "Cache TTL for validated emails in hours"
  type        = number
  default     = 24
}

# =============================================================================
# Discord
# =============================================================================

variable "discord_webhook_url" {
  description = "Discord webhook URL for notifications"
  type        = string
  default     = ""
}

variable "discord_error_webhook_url" {
  description = "Discord webhook URL for error notifications (private channel)"
  type        = string
  default     = ""
}

# =============================================================================
# LLM Configuration
# =============================================================================

variable "llm_model" {
  description = "OpenAI model to use (gpt-4o, gpt-4o-mini, gpt-4-turbo)"
  type        = string
  default     = "gpt-4o"
}

# =============================================================================
# Scheduler
# =============================================================================

variable "scheduler_enabled" {
  description = "Enable in-app APScheduler for hourly/daily jobs"
  type        = bool
  default     = true
}

# =============================================================================
# Video Generation
# =============================================================================

variable "video_enabled" {
  description = "Enable video generation feature"
  type        = bool
  default     = false
}

variable "video_output_dir" {
  description = "Directory for generated videos"
  type        = string
  default     = "/opt/noyau/output/videos"
}

variable "pexels_api_key" {
  description = "Pexels API key for stock footage"
  type        = string
  sensitive   = true
  default     = ""
}

variable "freesound_client_id" {
  description = "Freesound client ID for background music"
  type        = string
  default     = ""
}

variable "freesound_client_secret" {
  description = "Freesound client secret for background music"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tts_provider" {
  description = "TTS provider: edge (free), openai (default), elevenlabs (best)"
  type        = string
  default     = "openai"
}

variable "elevenlabs_api_key" {
  description = "ElevenLabs API key for TTS"
  type        = string
  sensitive   = true
  default     = ""
}

variable "youtube_client_id" {
  description = "Google OAuth 2.0 client ID for YouTube uploads"
  type        = string
  default     = ""
}

variable "youtube_client_secret" {
  description = "Google OAuth 2.0 client secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "youtube_refresh_token" {
  description = "YouTube API refresh token"
  type        = string
  sensitive   = true
  default     = ""
}

# =============================================================================
# S3 Storage
# =============================================================================

variable "s3_bucket_name" {
  description = "S3 bucket name for videos and logs"
  type        = string
  default     = ""
}

variable "s3_region" {
  description = "AWS S3 region"
  type        = string
  default     = "us-east-1"
}

variable "s3_access_key_id" {
  description = "AWS access key ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "s3_secret_access_key" {
  description = "AWS secret access key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "s3_endpoint_url" {
  description = "S3-compatible endpoint URL (for MinIO, R2, etc.)"
  type        = string
  default     = ""
}

variable "s3_public_url" {
  description = "Public URL for R2/S3 bucket (required for Instagram/TikTok)"
  type        = string
  default     = ""
}

# =============================================================================
# TikTok Content Posting API
# =============================================================================

variable "tiktok_client_key" {
  description = "TikTok app client key"
  type        = string
  default     = ""
}

variable "tiktok_client_secret" {
  description = "TikTok app client secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tiktok_access_token" {
  description = "TikTok OAuth access token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tiktok_refresh_token" {
  description = "TikTok OAuth refresh token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tiktok_redirect_uri" {
  description = "TikTok OAuth redirect URI"
  type        = string
  default     = ""
}

# =============================================================================
# Instagram Graph API
# =============================================================================

variable "instagram_app_id" {
  description = "Facebook/Instagram app ID"
  type        = string
  default     = ""
}

variable "instagram_app_secret" {
  description = "Facebook/Instagram app secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "instagram_business_account_id" {
  description = "Instagram Business Account ID"
  type        = string
  default     = ""
}

variable "instagram_access_token" {
  description = "Instagram Graph API access token"
  type        = string
  sensitive   = true
  default     = ""
}
