"""
Discord bot for managing digest subscriptions via DMs.

Users add the bot to their server and run /subscribe to receive daily digest DMs.
Uses discord.py with slash commands.
"""

import discord
from discord import app_commands
from sqlalchemy import select

from app.config import get_config
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import generate_ref_code
from app.models.messaging import MessagingConnection
from app.models.user import User

logger = get_logger(__name__)


class NoyauBot(discord.Client):
    """Discord bot client for Noyau daily digest subscriptions."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._setup_commands()

    def _setup_commands(self) -> None:
        """Register slash commands."""

        @self.tree.command(
            name="subscribe",
            description="Subscribe to receive the daily tech digest via DM",
        )
        @app_commands.describe(email="Your email address (for account linking)")
        async def subscribe(interaction: discord.Interaction, email: str) -> None:
            """Subscribe to daily digest DMs."""
            await self._handle_subscribe(interaction, email)

        @self.tree.command(
            name="unsubscribe",
            description="Stop receiving daily digest DMs",
        )
        async def unsubscribe(interaction: discord.Interaction) -> None:
            """Unsubscribe from daily digest DMs."""
            await self._handle_unsubscribe(interaction)

        @self.tree.command(
            name="status",
            description="Check your subscription status",
        )
        async def status(interaction: discord.Interaction) -> None:
            """Check subscription status."""
            await self._handle_status(interaction)

    async def setup_hook(self) -> None:
        """Called when the bot is ready to sync commands."""
        await self.tree.sync()
        logger.info("discord_bot_commands_synced")

    async def on_ready(self) -> None:
        """Called when the bot has connected to Discord."""
        logger.bind(
            user=self.user.name if self.user else "unknown",
            guilds=len(self.guilds),
        ).info("discord_bot_ready")

    async def _handle_subscribe(
        self,
        interaction: discord.Interaction,
        email: str,
    ) -> None:
        """Handle /subscribe command."""
        await interaction.response.defer(ephemeral=True)

        discord_user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        guild_name = interaction.guild.name if interaction.guild else None

        # Validate email format (basic check)
        if "@" not in email or "." not in email.split("@")[-1]:
            await interaction.followup.send(
                "Please provide a valid email address.",
                ephemeral=True,
            )
            return

        email = email.lower().strip()

        async with AsyncSessionLocal() as db:
            try:
                # Check if user already has a connection
                result = await db.execute(
                    select(MessagingConnection).where(
                        MessagingConnection.platform == "discord",
                        MessagingConnection.platform_user_id == discord_user_id,
                    )
                )
                existing_connection = result.scalar_one_or_none()

                if existing_connection and existing_connection.is_active:
                    await interaction.followup.send(
                        "You're already subscribed! Use `/unsubscribe` to stop receiving digests.",
                        ephemeral=True,
                    )
                    return

                # Find or create user by email
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()

                if not user:
                    # Create new user
                    user = User(
                        email=email,
                        ref_code=generate_ref_code(),
                    )
                    db.add(user)
                    await db.flush()
                    logger.bind(email=email, source="discord").info("user_created")

                if existing_connection:
                    # Reactivate existing connection
                    existing_connection.is_active = True
                    existing_connection.user_id = user.id
                    existing_connection.platform_team_id = guild_id
                    existing_connection.platform_team_name = guild_name
                    logger.bind(discord_user_id=discord_user_id).info(
                        "discord_subscription_reactivated"
                    )
                else:
                    # Create new connection
                    connection = MessagingConnection(
                        user_id=user.id,
                        platform="discord",
                        platform_user_id=discord_user_id,
                        platform_team_id=guild_id,
                        platform_team_name=guild_name,
                    )
                    db.add(connection)
                    logger.bind(discord_user_id=discord_user_id).info(
                        "discord_subscription_created"
                    )

                await db.commit()

                await interaction.followup.send(
                    f"Subscribed! You'll receive the daily tech digest via DM every day.\n"
                    f"Your account is linked to: {email}\n\n"
                    f"Use `/unsubscribe` anytime to stop.",
                    ephemeral=True,
                )

            except Exception as e:
                await db.rollback()
                logger.bind(error=str(e)).error("discord_subscribe_error")
                await interaction.followup.send(
                    "Something went wrong. Please try again later.",
                    ephemeral=True,
                )

    async def _handle_unsubscribe(self, interaction: discord.Interaction) -> None:
        """Handle /unsubscribe command."""
        await interaction.response.defer(ephemeral=True)

        discord_user_id = str(interaction.user.id)

        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(MessagingConnection).where(
                        MessagingConnection.platform == "discord",
                        MessagingConnection.platform_user_id == discord_user_id,
                        MessagingConnection.is_active.is_(True),
                    )
                )
                connection = result.scalar_one_or_none()

                if not connection:
                    await interaction.followup.send(
                        "You're not currently subscribed. Use `/subscribe` to start receiving digests.",
                        ephemeral=True,
                    )
                    return

                connection.is_active = False
                await db.commit()

                logger.bind(discord_user_id=discord_user_id).info(
                    "discord_subscription_deactivated"
                )

                await interaction.followup.send(
                    "Unsubscribed. You won't receive any more daily digest DMs.\n"
                    "Use `/subscribe` anytime to start again.",
                    ephemeral=True,
                )

            except Exception as e:
                await db.rollback()
                logger.bind(error=str(e)).error("discord_unsubscribe_error")
                await interaction.followup.send(
                    "Something went wrong. Please try again later.",
                    ephemeral=True,
                )

    async def _handle_status(self, interaction: discord.Interaction) -> None:
        """Handle /status command."""
        await interaction.response.defer(ephemeral=True)

        discord_user_id = str(interaction.user.id)

        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(MessagingConnection, User)
                    .join(User, MessagingConnection.user_id == User.id)
                    .where(
                        MessagingConnection.platform == "discord",
                        MessagingConnection.platform_user_id == discord_user_id,
                    )
                )
                row = result.first()

                if not row:
                    await interaction.followup.send(
                        "You're not subscribed. Use `/subscribe` to start receiving the daily tech digest.",
                        ephemeral=True,
                    )
                    return

                connection, user = row

                status_emoji = ":white_check_mark:" if connection.is_active else ":x:"
                status_text = "Active" if connection.is_active else "Paused"

                last_sent = "Never"
                if connection.last_sent_at:
                    last_sent = connection.last_sent_at.strftime("%Y-%m-%d %H:%M UTC")

                await interaction.followup.send(
                    f"**Noyau Digest Subscription**\n\n"
                    f"{status_emoji} Status: **{status_text}**\n"
                    f":envelope: Email: {user.email}\n"
                    f":clock1: Last sent: {last_sent}\n\n"
                    f"{'Use `/unsubscribe` to stop.' if connection.is_active else 'Use `/subscribe` to reactivate.'}",
                    ephemeral=True,
                )

            except Exception as e:
                logger.bind(error=str(e)).error("discord_status_error")
                await interaction.followup.send(
                    "Something went wrong. Please try again later.",
                    ephemeral=True,
                )


async def run_bot() -> None:
    """Run the Discord bot."""
    config = get_config()

    if not config.discord_bot.enabled:
        logger.warning("discord_bot_disabled")
        return

    if not config.discord_bot.bot_token:
        logger.error("discord_bot_token_not_set")
        return

    bot = NoyauBot()

    try:
        await bot.start(config.discord_bot.bot_token)
    except discord.LoginFailure:
        logger.error("discord_bot_login_failed")
    except Exception as e:
        logger.bind(error=str(e)).error("discord_bot_error")
    finally:
        if not bot.is_closed():
            await bot.close()
