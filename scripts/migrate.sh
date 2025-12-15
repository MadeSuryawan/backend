#!/bin/bash
# Alembic migration helper script for BaliBlissed Backend
# Usage: ./scripts/migrate.sh <command> [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

COMMAND=${1:-help}
REVISION=${2:-head}

case "$COMMAND" in
    upgrade)
        print_info "Upgrading database to: $REVISION"
        uv run alembic upgrade "$REVISION"
        print_success "Database upgraded successfully!"
        ;;

    downgrade)
        print_warning "Downgrading database to: $REVISION"
        read -p "Are you sure? This may result in data loss. (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            uv run alembic downgrade "$REVISION"
            print_success "Database downgraded successfully!"
        else
            print_info "Downgrade cancelled."
        fi
        ;;

    current)
        print_info "Current revision:"
        uv run alembic current
        ;;

    history)
        print_info "Migration history:"
        uv run alembic history --verbose
        ;;

    heads)
        print_info "Migration heads:"
        uv run alembic heads
        ;;

    generate)
        if [ -z "$2" ]; then
            print_error "Migration message required"
            echo "Usage: ./scripts/migrate.sh generate 'add_column_xyz'"
            exit 1
        fi
        print_info "Generating migration: $2"
        uv run alembic revision --autogenerate -m "$2"
        print_success "Migration generated! Review the file before applying."
        ;;

    stamp)
        if [ -z "$2" ]; then
            print_error "Revision required"
            echo "Usage: ./scripts/migrate.sh stamp head"
            exit 1
        fi
        print_warning "Stamping database with revision: $2"
        uv run alembic stamp "$2"
        print_success "Database stamped with revision: $2"
        ;;

    check)
        print_info "Checking for pending migrations..."
        uv run alembic check && print_success "No pending migrations!" || print_warning "Pending migrations detected!"
        ;;

    sql)
        if [ -z "$2" ]; then
            REVISION="head"
        fi
        print_info "Generating SQL for upgrade to: $REVISION"
        uv run alembic upgrade "$REVISION" --sql
        ;;

    reset)
        print_warning "This will downgrade to base and upgrade to head!"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Resetting database..."
            uv run alembic downgrade base
            uv run alembic upgrade head
            print_success "Database reset complete!"
        else
            print_info "Reset cancelled."
        fi
        ;;

    help|*)
        echo ""
        echo "🗄️  BaliBlissed Database Migration Tool"
        echo ""
        echo "Usage: ./scripts/migrate.sh <command> [options]"
        echo ""
        echo "Commands:"
        echo "  upgrade [rev]     Upgrade database to revision (default: head)"
        echo "  downgrade [rev]   Downgrade database to revision (default: -1)"
        echo "  current           Show current revision"
        echo "  history           Show migration history"
        echo "  heads             Show current heads"
        echo "  generate <msg>    Generate new migration with autogenerate"
        echo "  stamp <rev>       Stamp database with revision (for existing DBs)"
        echo "  check             Check for pending migrations"
        echo "  sql [rev]         Generate SQL without executing"
        echo "  reset             Downgrade to base and upgrade to head"
        echo "  help              Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./scripts/migrate.sh upgrade              # Upgrade to latest"
        echo "  ./scripts/migrate.sh upgrade 0001         # Upgrade to specific revision"
        echo "  ./scripts/migrate.sh downgrade -1         # Downgrade one step"
        echo "  ./scripts/migrate.sh generate 'add_foo'   # Generate new migration"
        echo "  ./scripts/migrate.sh stamp head           # Mark existing DB as current"
        echo ""
        ;;
esac

