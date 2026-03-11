"""Security-focused settings validation tests."""

from warnings import catch_warnings, simplefilter

import pytest
from pydantic import ValidationError

from app.configs.settings import Settings


def test_rejects_dev_secret_key_sentinel_in_production() -> None:
    with catch_warnings():
        simplefilter("ignore")
        with pytest.raises(ValidationError):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="dev-only-insecure-key-replace-in-prod",
            )


def test_accepts_non_default_secret_key_in_production() -> None:
    with catch_warnings():
        simplefilter("ignore")
        settings = Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-secure-production-secret-key-value",
        )

    assert settings.SECRET_KEY == "a-secure-production-secret-key-value"
