# docker-compose up -d

# uvicorn app:app --host 127.0.0.1 --port 8000 --reload --workers 4 --loop uvloop --http httptools
#!/bin/bash
# scripts/docker-dev.sh
# Development Docker management script for BaliBlissed

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
PROJECT_NAME="baliblissed"

PID_FILE="uvicorn.pid"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    else
        log_success "Docker is running"
    fi
}

# Create required directories
create_directories() {
    log_info "Creating required directories..."
    mkdir -p ./data/redis ./logs
    log_success "Directories created successfully"
}

# Start development environment
start() {
    log_info "Starting BaliBlissed development environment..."
    check_docker
    # check_env
    create_directories
    
    # docker-compose --profile development up --build -d
    docker-compose up -d
    uvicorn app:app --host 127.0.0.1 --port 8000 --reload --workers 4 --loop uvloop --http httptools
    # log_success "Development environment started successfully!"
}

# Stop development environment
stop() {
    log_info "Stopping BaliBlissed development environment..."
    # docker-compose --profile development down
    docker-compose down -v
    log_success "Development environment stopped successfully!"
}

case "${1:-help}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs "$2"
        ;;
    status)
        status
        ;;
    clean)
        clean
        ;;
    reset)
        reset
        ;;
    test)
        test
        ;;
    shell)
        shell
        ;;
    redis)
        redis
        ;;
    help|--help|-h)
        help
        ;;
    *)
        log_error "Unknown command: $1"
        help
        exit 1
        ;;
esac
