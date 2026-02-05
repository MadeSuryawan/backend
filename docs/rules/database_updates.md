# **Agent Knowledge: Database Refactoring & Migrations (Alembic)**

**Current State:**

* **Migration Tool:** Alembic (Async configuration).
* **Driver:** `asyncpg` (PostgreSQL).
* **Schema Authority:** Alembic is the single source of truth. `SQLModel.metadata.create_all()` is **DISABLED**.
* **Linting:** Generated migrations are automatically formatted by `ruff`.

**Refactoring Workflow Rules:**

1. **Modify Python First:** When changing schema, modify `app/models/*.py` first using SQLModel.
2. **Import Visibility:** If creating a NEW model file, you **MUST** import it in `app/models/__init__.py`. If you fail to do this, Alembic will not detect the new table.
3. **Generate Migration:**
    * Command: `./scripts/migrate.sh generate "descriptive_slug"`
    * *Do not* write raw SQL files manually unless complex data migration is required.
4. **Review Logic:**
    * Check for `op.drop_column` or `op.drop_table` in generated scripts to prevent accidental data loss.
    * Ensure new indexes (especially GIN for JSONB) are explicitly named in the migration script.

**Performance Optimization Context (Postgres):**

* **JSON/Tags:** When adding JSONB columns, always suggest adding a **GIN index** in the migration if the column will be searched.
* **Search:** For text search requirements, prefer `pg_trgm` indexes over external search services.
* **Keys:** Continue using `UUID` for all primary keys.

**Troubleshooting Knowledge:**

* If `alembic upgrade` fails with "relation already exists", use `./scripts/migrate.sh stamp <current_revision>` to sync the history.
* If "Target database is not up to date", run `./scripts/migrate.sh upgrade` before making new changes.
