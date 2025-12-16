# Project IDX Workflow Guide

This guide documents the workflow for developing the BaliBlissed Backend within the Project IDX environment.

## 1. Environment Setup

When you open or restart the Project IDX workspace, the configuration in `.idx/dev.nix` automatically handles the environment setup.

### Automated Actions

The workspace automatically performs the following:

* **Installs Python 3.13**: Sets up the required Python version.
* **Installs `uv`**: Fetches the latest version of the `uv` package manager.
* **Syncs Dependencies**: Runs `uv sync` to install all project dependencies from `uv.lock`.
* **Installs Dev Tools**: Installs `ruff`, `pyrefly`, and `pytest` globally via `uv tool`.
* **Starts Services**:
  * **PostgreSQL**: Starts the Postgres server using the local data directory `.idx/postgres_data`.
  * **Redis**: Enables the Redis service.

### First-Time Setup (If needed)

If the database fails to connect on the very first run, you may need to initialize it manually:

```bash
initdb -D .idx/postgres_data
pg_ctl -D .idx/postgres_data start -l .idx/postgres.log
createuser -s user
createdb -O user baliblissed
```

*Note: The `onCreate` hook in `dev.nix` attempts to do this automatically when the workspace is first created.*

## 2. Running the Application

To start the backend server, use the dedicated IDX run script. This script replaces the Docker-based workflow used on local machines.

```bash
./scripts/run_idx.sh start
```

*(Note: Running `./scripts/run_idx.sh` without arguments also defaults to starting the app)*

### What the Script Does

1. **Loads Environment**: Reads from `./secrets/.env` if it exists, otherwise falls back to IDX environment variables.
2. **Checks Database**: Verifies connectivity to the local Postgres service.
3. **Database Management**:
    * Prompts to recreate the database (optional).
    * Runs `python -m app.db.init_db` to initialize tables.
4. **Starts Server**: Launches `uvicorn` with hot-reload enabled on port 8000.

## 3. Development Workflow

### Dependency Management

* **Add a package**: `uv add <package>`
* **Add a dev package**: `uv add --dev <package>`
* **Sync environment**: `uv sync` (Run this if you pull changes that modify `uv.lock`)

### Testing

Run tests using `pytest`. The tool is installed globally in the environment.

```bash
pytest
```

### Code Quality

* **Linting**: `ruff check .`
* **Formatting**: `ruff format .`
* **Refactoring**: `pyrefly`

### Database Operations

* **Connect to DB**: `psql -U user -d baliblissed`
* **Reset DB**: The `./scripts/run_idx.sh` script includes an interactive option to drop and recreate the database.

## 4. Troubleshooting

* **Services not running**:
    If `psql` cannot connect, try manually starting the Postgres service:

    ```bash
    pg_ctl -D .idx/postgres_data start -l .idx/postgres.log
    ```

* **Tools not found**:
    If `ruff` or `pytest` are missing, ensure `~/.local/bin` is in your PATH or run:

    ```bash
    export PATH="$HOME/.local/bin:$PATH"
    ```
