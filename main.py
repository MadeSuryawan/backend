# main.py

# from uvicorn import run
from pathlib import Path
from subprocess import run

from app import app


def start(cmmd: list[str]) -> None:
    run(cmmd, check=True)


def main() -> None:
    file_path = Path(__file__).resolve()
    bin_path = file_path.parent / ".venv" / "bin"
    uvicorn_path = bin_path / "uvicorn"
    cmmd = [
        f"{uvicorn_path}",
        "app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
        "--log-level",
        "info",
        "--workers",
        "4",
        "--loop",
        "uvloop",
        "--http",
        "httptools",
    ]
    start(cmmd)


if __name__ == "__main__":
    __all__ = ["app"]
    # run(app, host="127.0.0.1", port=8000, log_level="info", reload=True)
    main()
