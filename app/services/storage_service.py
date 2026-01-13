"""AWS S3 storage service for videos and logs."""

import gzip
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class S3StorageService:
    """
    S3 storage service for videos, logs, and other files.

    Supports:
    - Video uploads with public URLs
    - Log archival with compression
    - Generic file uploads
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ):
        """
        Initialize S3 storage service.

        Args:
            bucket_name: S3 bucket name (defaults to settings)
            region: AWS region (defaults to settings)
            access_key_id: AWS access key (defaults to settings/env)
            secret_access_key: AWS secret key (defaults to settings/env)
            endpoint_url: Custom endpoint for S3-compatible storage (e.g., MinIO, R2)
        """
        settings = get_settings()
        self.bucket_name = bucket_name or settings.s3_bucket_name
        self.endpoint_url = endpoint_url or settings.s3_endpoint_url or None
        # R2 and other S3-compatible services use 'auto' region
        self.region = region or ("auto" if self.endpoint_url else settings.s3_region)

        # Create S3 client
        client_kwargs = {
            "service_name": "s3",
            "region_name": self.region,
        }

        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key
        elif settings.s3_access_key_id and settings.s3_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key

        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url

        self._client = boto3.client(**client_kwargs)
        self._configured = bool(self.bucket_name)

    def _build_public_url(self, key: str) -> str:
        """Build a public URL for an S3 object."""
        settings = get_settings()
        # Use configured public URL if available (required for social media platforms)
        if settings.s3_public_url:
            return f"{settings.s3_public_url.rstrip('/')}/{key}"
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket_name}/{key}"
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"

    def _build_upload_args(
        self,
        content_type: str,
        public: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, str | dict[str, str]]:
        """Build ExtraArgs dict for S3 upload operations."""
        extra_args: dict[str, str | dict[str, str]] = {"ContentType": content_type}
        if public:
            extra_args["ACL"] = "public-read"
        if metadata:
            extra_args["Metadata"] = metadata
        return extra_args

    def is_configured(self) -> bool:
        """Check if S3 is properly configured."""
        return self._configured

    async def upload_file(
        self,
        file_path: Path,
        key: str,
        content_type: str | None = None,
        public: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        """
        Upload a file to S3.

        Args:
            file_path: Local path to the file
            key: S3 object key (path in bucket)
            content_type: MIME type (auto-detected if not provided)
            public: Whether to make the file publicly accessible
            metadata: Optional metadata to attach to the object

        Returns:
            Public URL if successful, None otherwise
        """
        if not self._configured:
            logger.warning("s3_not_configured_skipping_upload")
            return None

        if not file_path.exists():
            logger.bind(path=str(file_path)).error("file_not_found_for_upload")
            return None

        # Auto-detect content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or "application/octet-stream"

        extra_args = self._build_upload_args(content_type, public, metadata)

        try:
            self._client.upload_file(
                str(file_path),
                self.bucket_name,
                key,
                ExtraArgs=extra_args,
            )

            url = self._build_public_url(key)
            logger.bind(key=key, url=url).info("file_uploaded_to_s3")
            return url

        except ClientError as e:
            logger.bind(key=key, error=str(e)).error("s3_upload_failed")
            return None

    async def upload_fileobj(
        self,
        fileobj: BinaryIO,
        key: str,
        content_type: str = "application/octet-stream",
        public: bool = False,
    ) -> str | None:
        """
        Upload a file-like object to S3.

        Args:
            fileobj: File-like object to upload
            key: S3 object key
            content_type: MIME type
            public: Whether to make publicly accessible

        Returns:
            Public URL if successful, None otherwise
        """
        if not self._configured:
            logger.warning("s3_not_configured_skipping_upload")
            return None

        extra_args = self._build_upload_args(content_type, public)

        try:
            self._client.upload_fileobj(
                fileobj,
                self.bucket_name,
                key,
                ExtraArgs=extra_args,
            )

            url = self._build_public_url(key)
            logger.bind(key=key).info("fileobj_uploaded_to_s3")
            return url

        except ClientError as e:
            logger.bind(key=key, error=str(e)).error("s3_upload_fileobj_failed")
            return None

    async def upload_video(
        self,
        video_path: Path,
        issue_date: str,
        rank: int,
        filename: str | None = None,
    ) -> str | None:
        """
        Upload a video file to S3.

        Args:
            video_path: Path to the video file
            issue_date: Date string for organizing (YYYY-MM-DD)
            rank: Video rank in the digest
            filename: Optional custom filename

        Returns:
            Public URL of the uploaded video
        """
        filename = filename or video_path.name
        key = f"videos/{issue_date}/rank_{rank}/{filename}"

        return await self.upload_file(
            file_path=video_path,
            key=key,
            content_type="video/mp4",
            public=True,
            metadata={
                "issue_date": issue_date,
                "rank": str(rank),
            },
        )

    async def archive_log_file(
        self,
        log_path: Path,
        compress: bool = True,
    ) -> str | None:
        """
        Archive a log file to S3.

        Args:
            log_path: Path to the log file
            compress: Whether to gzip compress before uploading

        Returns:
            S3 URL of the archived log
        """
        if not log_path.exists():
            logger.bind(path=str(log_path)).warning("log_file_not_found")
            return None

        # Generate key with date prefix for organization
        date_prefix = datetime.now().strftime("%Y/%m/%d")
        filename = log_path.name

        if compress:
            # Compress the log file
            compressed_path = log_path.with_suffix(log_path.suffix + ".gz")
            with open(log_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)

            key = f"logs/{date_prefix}/{filename}.gz"
            result = await self.upload_file(
                file_path=compressed_path,
                key=key,
                content_type="application/gzip",
                public=False,
            )

            # Clean up compressed file
            compressed_path.unlink()
            return result
        else:
            key = f"logs/{date_prefix}/{filename}"
            return await self.upload_file(
                file_path=log_path,
                key=key,
                content_type="text/plain",
                public=False,
            )

    async def download_file(self, key: str, destination: Path) -> bool:
        """
        Download a file from S3.

        Args:
            key: S3 object key to download
            destination: Local path to save the file

        Returns:
            True if successful, False otherwise
        """
        if not self._configured:
            logger.warning("s3_not_configured_skipping_download")
            return False

        try:
            # Ensure parent directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)

            self._client.download_file(
                self.bucket_name,
                key,
                str(destination),
            )

            logger.bind(key=key, destination=str(destination)).info("file_downloaded_from_s3")
            return True

        except ClientError as e:
            logger.bind(key=key, error=str(e)).error("s3_download_failed")
            return False

    async def delete_file(self, key: str) -> bool:
        """
        Delete a file from S3.

        Args:
            key: S3 object key to delete

        Returns:
            True if successful, False otherwise
        """
        if not self._configured:
            return False

        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.bind(key=key).info("file_deleted_from_s3")
            return True
        except ClientError as e:
            logger.bind(key=key, error=str(e)).error("s3_delete_failed")
            return False

    async def list_files(self, prefix: str, max_keys: int = 1000) -> list[dict]:
        """
        List files in S3 with a given prefix.

        Args:
            prefix: Key prefix to filter by
            max_keys: Maximum number of keys to return

        Returns:
            List of objects with key, size, and last_modified
        """
        if not self._configured:
            return []

        try:
            response = self._client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys,
            )

            return [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
                for obj in response.get("Contents", [])
            ]

        except ClientError as e:
            logger.bind(prefix=prefix, error=str(e)).error("s3_list_failed")
            return []

    def get_presigned_url(self, key: str, expiration: int = 3600) -> str | None:
        """
        Generate a presigned URL for temporary access.

        Args:
            key: S3 object key
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL or None
        """
        if not self._configured:
            return None

        try:
            url: str = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            logger.bind(key=key, error=str(e)).error("presigned_url_generation_failed")
            return None


# Singleton instance
_storage_service: S3StorageService | None = None


def get_storage_service() -> S3StorageService:
    """Get the singleton storage service instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = S3StorageService()
    return _storage_service
