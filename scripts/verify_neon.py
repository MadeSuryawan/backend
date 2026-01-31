from asyncio import run as asyncio_run
from pathlib import Path
from sys import path as sys_path

from sqlalchemy import text

try:
    from app.db.database import engine
except ImportError:
    # Add project root to path so 'app' module can be found
    project_root = Path(__file__).resolve().parent.parent
    sys_path.append(str(project_root))
    from app.db.database import engine


async def main() -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            print("Database connection verified successfully!")

            # Check for tables
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
                ),
            )
            tables = result.scalars().all()
            print(f"Tables found: {tables}")

    except ConnectionError as e:
        print(f"Connection failed: {e}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio_run(main())
