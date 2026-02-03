from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.storage.cloudinary_storage import CloudinaryStorage
from app.services.storage.local import LocalStorage


class TestLocalStorageCleanup:
    @pytest.mark.asyncio
    async def test_delete_all_media_local(self, tmp_path: Path) -> None:
        # Setup LocalStorage with tmp_path
        storage = LocalStorage()
        storage.uploads_dir = tmp_path

        folder = "test_folder"
        entity_id = "test_entity"
        entity_dir = tmp_path / folder / entity_id
        entity_dir.mkdir(parents=True)

        # Create some files
        (entity_dir / "file1.jpg").write_text("fake")
        (entity_dir / "file2.mp4").write_text("fake")

        assert entity_dir.exists()

        result = await storage.delete_all_media(folder, entity_id)

        assert result is True
        assert not entity_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_all_media_local_nonexistent(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.uploads_dir = tmp_path

        result = await storage.delete_all_media("nonexistent", "id")
        assert result is False


class TestCloudinaryStorageCleanup:
    @pytest.mark.asyncio
    @patch("cloudinary.api.delete_resources_by_prefix")
    async def test_delete_all_media_cloudinary(self, mock_delete: MagicMock) -> None:
        # Mock results
        mock_delete.return_value = {"deleted": {"res1": "deleted"}}

        storage = CloudinaryStorage()
        folder = "test_folder"
        entity_id = "test_entity"

        result = await storage.delete_all_media(folder, entity_id)

        assert result is True
        assert mock_delete.call_count == 2  # Once for image, once for video

        prefix = f"baliblissed/{folder}/{entity_id}/"
        mock_delete.assert_any_call(prefix, resource_type="image")
        mock_delete.assert_any_call(prefix, resource_type="video")

    @pytest.mark.asyncio
    @patch("cloudinary.api.delete_resources_by_prefix")
    async def test_delete_all_media_cloudinary_error(self, mock_delete: MagicMock) -> None:
        mock_delete.side_effect = Exception("Cloudinary error")

        storage = CloudinaryStorage()
        result = await storage.delete_all_media("folder", "id")

        assert result is False
