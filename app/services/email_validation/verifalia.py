"""Verifalia email validation provider."""

import asyncio

import aiohttp

from app.core.logging import get_logger

from .base import BaseEmailValidator
from .models import ValidationResult, ValidationStatus

logger = get_logger(__name__)


class VerifaliaValidator(BaseEmailValidator):
    """Email validation using Verifalia API."""

    provider_name = "verifalia"
    BASE_URL = "https://api.verifalia.com/v2.5"

    # Map Verifalia classification to our status
    _STATUS_MAP = {
        "Deliverable": ValidationStatus.VALID,
        "Undeliverable": ValidationStatus.INVALID,
        "Risky": ValidationStatus.RISKY,
        "Unknown": ValidationStatus.UNKNOWN,
    }

    def __init__(
        self,
        username: str,
        password: str,
        quality: str = "Standard",
        timeout_seconds: int = 30,
        max_polls: int = 10,
        poll_interval: float = 1.0,
    ) -> None:
        """
        Initialize Verifalia validator.

        Args:
            username: Verifalia account username
            password: Verifalia account password
            quality: Validation quality level (Standard, High, Extreme)
            timeout_seconds: HTTP request timeout
            max_polls: Maximum number of polling attempts
            poll_interval: Seconds between poll attempts
        """
        self.username = username
        self.password = password
        self.quality = quality
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_polls = max_polls
        self.poll_interval = poll_interval

    async def validate(self, email: str) -> ValidationResult:
        """Validate a single email address."""
        results = await self.validate_batch([email])
        return results[0]

    async def validate_batch(self, emails: list[str]) -> list[ValidationResult]:
        """Validate multiple email addresses."""
        try:
            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(self.username, self.password),
                timeout=self.timeout,
            ) as session:
                # Submit validation job
                job = await self._submit_job(session, emails)
                if not job:
                    return [self._unknown_result(email, "Failed to submit job") for email in emails]

                job_id = job.get("overview", {}).get("id")
                if not job_id:
                    return [self._unknown_result(email, "No job ID returned") for email in emails]

                # Check if already completed (synchronous response)
                if job.get("overview", {}).get("status") == "Completed":
                    return self._parse_results(emails, job)

                # Poll for completion
                result = await self._wait_for_result(session, job_id)
                if not result:
                    return [self._unknown_result(email, "Job timed out") for email in emails]

                return self._parse_results(emails, result)

        except TimeoutError:
            logger.bind(emails=emails).warning("verifalia_timeout")
            return [self._unknown_result(email, "Request timed out") for email in emails]
        except aiohttp.ClientError as e:
            logger.bind(error=str(e)).error("verifalia_client_error")
            return [self._unknown_result(email, f"Client error: {e}") for email in emails]
        except Exception as e:
            logger.bind(error=str(e)).error("verifalia_unexpected_error")
            return [self._unknown_result(email, f"Unexpected error: {e}") for email in emails]

    async def _submit_job(self, session: aiohttp.ClientSession, emails: list[str]) -> dict | None:
        """Submit validation job to Verifalia."""
        payload = {
            "entries": [{"inputData": email} for email in emails],
            "quality": self.quality,
        }

        try:
            async with session.post(
                f"{self.BASE_URL}/email-validations",
                json=payload,
            ) as response:
                if response.status in (200, 202):
                    return await response.json()
                elif response.status == 401:
                    logger.error("verifalia_auth_failure")
                    return None
                elif response.status == 402:
                    logger.error("verifalia_insufficient_credits")
                    return None
                else:
                    logger.bind(status=response.status).error("verifalia_submit_error")
                    return None
        except Exception as e:
            logger.bind(error=str(e)).error("verifalia_submit_exception")
            return None

    async def _wait_for_result(self, session: aiohttp.ClientSession, job_id: str) -> dict | None:
        """Poll for job completion."""
        for _ in range(self.max_polls):
            try:
                async with session.get(
                    f"{self.BASE_URL}/email-validations/{job_id}",
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("overview", {}).get("status") == "Completed":
                            return data
                    elif response.status == 410:
                        # Job expired/deleted
                        logger.bind(job_id=job_id).warning("verifalia_job_expired")
                        return None
            except Exception as e:
                logger.bind(error=str(e)).warning("verifalia_poll_error")

            await asyncio.sleep(self.poll_interval)

        logger.bind(job_id=job_id).warning("verifalia_poll_timeout")
        return None

    def _parse_results(self, emails: list[str], response: dict) -> list[ValidationResult]:
        """Parse Verifalia response to ValidationResults."""
        entries = response.get("entries", [])

        # Create a map of input email to entry (Verifalia returns in order, but be safe)
        entry_map = {entry.get("inputData", "").lower(): entry for entry in entries}

        results = []
        for email in emails:
            entry = entry_map.get(email.lower())
            if entry:
                results.append(self._parse_entry(email, entry))
            else:
                results.append(self._unknown_result(email, "Entry not found in response"))

        return results

    def _parse_entry(self, email: str, entry: dict) -> ValidationResult:
        """Parse a single Verifalia response entry to ValidationResult."""
        classification = entry.get("classification", "Unknown")
        status = self._STATUS_MAP.get(classification, ValidationStatus.UNKNOWN)

        return ValidationResult(
            email=email,
            status=status,
            provider=self.provider_name,
            is_deliverable=classification == "Deliverable",
            is_disposable=entry.get("isDisposableEmailAddress", False),
            is_role_based=entry.get("isRoleAccount", False),
            is_free_provider=entry.get("isFreeEmailAddress", False),
            reason=entry.get("status"),
            raw_response=entry,
        )

    def _unknown_result(self, email: str, reason: str) -> ValidationResult:
        """Create an UNKNOWN result for error cases (fail open)."""
        return ValidationResult(
            email=email,
            status=ValidationStatus.UNKNOWN,
            provider=self.provider_name,
            is_deliverable=True,  # Fail open
            reason=reason,
        )
