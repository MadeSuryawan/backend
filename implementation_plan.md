# Resolve Circular Dependency - Implementation Plan

## Goal

Resolve the circular import between `app.clients` and `app.managers` to allow [app/main.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/main.py) to import [get_email_client](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/dependencies/dependencies.py#204-206) from [app/dependencies/dependencies.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/dependencies/dependencies.py).

## Problem

The dependency chain is:
`main` -> `dependencies` -> `clients` -> `decorators` -> `decorators.metrics` -> `managers.metrics` -> `managers (init)` -> [cache_manager](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/dependencies/dependencies.py#196-199) -> `clients`.
This causes a crash when `clients` is imported before `managers` is fully initialized.

## Proposed Changes

### Break the Cycle

1. **Refactor [app/managers/**init**.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/managers/__init__.py)**
    * Remove `from app.managers.cache_manager import cache_manager`
    * Remove `from app.managers.circuit_breaker import ...` and others if they cause similar issues or just to be consistent (lazy loading).
    * Goal: [app/managers/**init**.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/managers/__init__.py) should be empty or only contain imports that don't trigger heavy dependencies.
    * **Decision**: Remove ALL eager imports from [app/managers/**init**.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/managers/__init__.py) to prevent future cycles, or at least [cache_manager](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/dependencies/dependencies.py#196-199).

### Update Consumers

1. **Update imports in [app/main.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/main.py)**
    * Change `from app.managers import cache_manager` to `from app.managers.cache_manager import cache_manager`
    * Update other manager imports similarly.

2. **Update imports in [app/dependencies/dependencies.py](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/app/dependencies/dependencies.py)**
    * Change `from app.managers.cache_manager import CacheManager` (if it uses `from app.managers import ...`).
    * (It currently uses `from app.managers.cache_manager import CacheManager`, which is good).

3. **Scan and Update other files**
    * Use `grep` to find `from app.managers import` and update them.

## Verification Plan

### Automated Tests

1. **Run Tests**: `uv run pytest` to ensure no regressions.
2. **Run App**: `uv run python -m app.main` to ensure the app starts.

### Manual Verification

1. Verify the import cycle is broken by tracing the code.
