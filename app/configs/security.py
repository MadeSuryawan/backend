"""
Password security configuration module.

This module provides password hashing configuration with Argon2 and security
level management for different environments.
"""

from passlib.context import CryptContext
from pydantic import BaseModel


class SecurityInfo(BaseModel):
    """Security configuration information for a specific security level."""

    description: str
    memory_cost: int
    time_cost: int
    parallelism: int
    hash_time: str


CONFIG_MAP: dict[str, SecurityInfo] = {
    "development": SecurityInfo(
        description="Fast hashing for development/testing",
        memory_cost=65536,  # 64 MB
        time_cost=1,  # 1 iteration
        parallelism=1,  # 1 thread
        hash_time="~20ms",
    ),
    "standard": SecurityInfo(
        description="Balanced security and performance (default)",
        memory_cost=524288,  # 512 MB
        time_cost=2,  # 2 iterations
        parallelism=2,  # 2 threads
        hash_time="~100-150ms",
    ),
    "high": SecurityInfo(
        description="High security, slower hashing",
        memory_cost=1048576,  # 1 GB
        time_cost=3,  # 3 iterations
        parallelism=4,  # 4 threads
        hash_time="~500ms",
    ),
    "paranoid": SecurityInfo(
        description="Maximum security, very slow",
        memory_cost=2097152,  # 2 GB
        time_cost=4,  # 4 iterations
        parallelism=8,  # 8 threads
        hash_time="~2-5s",
    ),
}


def get_context(level: str) -> CryptContext:
    """
    Get CryptContext configured for specified security level.

    Args:
        level: Security level to use

    Returns:
        CryptContext: Configured context

    Example:
        >>> ctx = get_context("high")
        >>> hashed = ctx.hash("password")

    """
    config = CONFIG_MAP[level]

    return CryptContext(
        schemes=["argon2", "pbkdf2_sha256"],
        deprecated="pbkdf2_sha256",
        argon2__memory_cost=config.memory_cost,
        argon2__time_cost=config.time_cost,
        argon2__parallelism=config.parallelism,
    )


def print_config_info() -> None:
    """Print detailed information about all security levels."""
    from rich import print as rprint  # noqa: PLC0415

    yellow = "[yellow]=[yellow]" * 80
    rprint("\n" + yellow)
    rprint("[b i blue]Password Hashing Configuration Guide[b i blue]")
    rprint(yellow)

    for level, config in CONFIG_MAP.items():
        mem_cost: int = config.memory_cost
        rprint(f"\n[b green]{level.upper()}:[b green]")
        rprint(yellow)
        rprint(
            f"\t[i blue]Description:[i blue]        [green]{config.description}[green]",
        )
        rprint(
            f"\t[i blue]Memory Cost:[i blue]        [green]{mem_cost:,} bytes ({mem_cost // (1024 * 1024)}MB)[green]",
        )
        rprint(
            f"\t[i blue]Time Cost:[i blue]          [green]{config.time_cost} iterations[green]",
        )
        rprint(
            f"\t[i blue]Parallelism:[i blue]        [green]{config.parallelism} threads[green]",
        )
        rprint(
            f"\t[i blue]Estimated Time:[i blue]     [green]{config.hash_time}[green]",
        )

    rprint("\n" + yellow)
    rprint("[b i blue]Recommendations:[b i blue]")
    rprint(yellow)
    rprint("""
  DEVELOPMENT:
    Use for local testing and development
    Fastest option for rapid iteration

  STANDARD (default):
    Use for most production applications
    Good balance of security and performance
    Suitable for web applications with normal load

  HIGH:
    Use for sensitive applications (banking, health)
    Higher security with acceptable performance
    Monitor system load when under heavy authentication

  PARANOID:
    Use only for extremely sensitive systems
    Maximum brute-force resistance
    May impact user experience during login
    Consider using only for initial password setup

Parameters Explanation:
  - Memory Cost: Higher = harder for GPU/ASIC attacks
  - Time Cost: More iterations = harder to brute-force
  - Parallelism: More threads = better performance on multi-core systems
    """)


if __name__ == "__main__":
    print_config_info()
