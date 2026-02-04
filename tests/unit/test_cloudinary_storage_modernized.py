from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest

from app.services.storage.cloudinary_storage import CloudinaryStorage


class TestCloudinaryStorageModernized:
    @pytest.fixture
    def storage(self) -> CloudinaryStorage:
        with patch("app.services.storage.cloudinary_storage.config"):
            return CloudinaryStorage()

    @pytest.mark.asyncio
    @patch("app.services.storage.cloudinary_storage.upload")
    @patch("app.services.storage.cloudinary_storage.get_event_loop")
    async def test_upload_profile_picture_transformations(
        self,
        mock_get_loop: MagicMock,
        mock_upload: MagicMock,
        storage: CloudinaryStorage,
    ) -> None:
        # Mock loop.run_in_executor to call the partial synchronously for testing
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        async def mock_run(executor: object, func: Callable[[], object]) -> object:
            return func()

        mock_loop.run_in_executor = mock_run

        mock_upload.return_value = {"secure_url": "https://secure.url"}

        user_id = "user123"
        file_data = b"fake data"
        content_type = "image/jpeg"

        await storage.upload_profile_picture(user_id, file_data, content_type)

        # Verify upload was called with split transformations
        args, kwargs = mock_upload.call_args
        transformations = kwargs.get("transformation")

        # Transformation should be a list with separate dictionaries for quality and fetch_format
        assert len(transformations) == 3
        assert transformations[1] == {"quality": "auto:good"}
        assert transformations[2] == {"fetch_format": "auto"}

    @pytest.mark.asyncio
    @patch("app.services.storage.cloudinary_storage.upload")
    @patch("app.services.storage.cloudinary_storage.get_event_loop")
    async def test_upload_media_transformations(
        self,
        mock_get_loop: MagicMock,
        mock_upload: MagicMock,
        storage: CloudinaryStorage,
    ) -> None:
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        async def mock_run(executor: object, func: Callable[[], object]) -> object:
            return func()

        mock_loop.run_in_executor = mock_run

        mock_upload.return_value = {"secure_url": "https://secure.url"}

        await storage.upload_media("folder", "entity", "media", b"data", "image/jpeg")

        args, kwargs = mock_upload.call_args
        transformations = kwargs.get("transformation")

        assert len(transformations) == 2
        assert transformations[0] == {"quality": "auto:good"}
        assert transformations[1] == {"fetch_format": "auto"}
