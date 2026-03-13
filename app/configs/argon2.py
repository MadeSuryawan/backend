"""
Argon2 security configuration module.

This module provides Argon2id configuration parameters matching
the current security levels to maintain existing security standards.
"""

from os import getenv

from argon2.low_level import Type
from pydantic import BaseModel


class Argon2Config(BaseModel):
    """Argon2 configuration parameters matching current security levels."""

    memory_cost: int = 65536  # KB (64 MB for development)
    time_cost: int = 1  # Iterations
    parallelism: int = 1  # Parallel threads
    hash_len: int = 32  # Output length in bytes
    salt_len: int = 16  # Salt length in bytes
    type: Type = Type.ID  # Argon2id variant


# Pre-defined configurations matching current CONFIG_MAP
ARGON2_PROFILES: dict[str, Argon2Config] = {
    "development": Argon2Config(
        memory_cost=65536,  # 64 MB
        time_cost=1,
        parallelism=1,
    ),
    "standard": Argon2Config(
        memory_cost=524288,  # 512 MB
        time_cost=2,
        parallelism=2,
    ),
    "high": Argon2Config(
        memory_cost=1048576,  # 1 GB
        time_cost=3,
        parallelism=4,
    ),
    "paranoid": Argon2Config(
        memory_cost=2097152,  # 2 GB
        time_cost=4,
        parallelism=8,
    ),
}

# Minimum recommended parameters for production
MIN_PRODUCTION_PARAMS = {
    "memory_cost": 131072,  # 128 MB minimum for production
    "time_cost": 2,
    "parallelism": 1,
}


def get_argon2_config(level: str, environment: str | None = None) -> Argon2Config:
    """
    Get Argon2 configuration for the specified security level.

    Args:
        level: Security level (development, standard, high, paranoid)
        environment: Optional environment override (development, production)

    Returns:
        Argon2Config: Configuration parameters

    Raises:
        ValueError: If weak parameters would be used in production
    """
    # Determine environment
    env = environment or getenv("ENVIRONMENT", "").lower()
    is_production = env in ("production", "prod")

    config = ARGON2_PROFILES.get(level, ARGON2_PROFILES["standard"])

    # Warn or error if using weak parameters in production
    if is_production and level == "development":
        detail = (
            "SECURITY: Cannot use 'development' security level in production environment. "
            "Use 'standard', 'high', or 'paranoid' instead."
        )
        raise ValueError(detail)

    if is_production:
        # Ensure minimum production parameters are met
        if config.memory_cost < MIN_PRODUCTION_PARAMS["memory_cost"]:
            detail = (
                f"SECURITY: memory_cost ({config.memory_cost} KB) is below minimum "
                f"recommended for production ({MIN_PRODUCTION_PARAMS['memory_cost']} KB)"
            )
            raise ValueError(detail)
        if config.time_cost < MIN_PRODUCTION_PARAMS["time_cost"]:
            detail = (
                f"SECURITY: time_cost ({config.time_cost}) is below minimum "
                f"recommended for production ({MIN_PRODUCTION_PARAMS['time_cost']})"
            )
            raise ValueError(detail)

    return config
