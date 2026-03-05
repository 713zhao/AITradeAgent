#!/bin/bash

# PicoClaw Finance Agent - Docker Deployment Script
# Quick start script for deploying the complete system with Docker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC} $1"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Initialize
print_header "PicoClaw Finance Agent - Docker Deployment"

# Check Docker installation
print_info "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi
print_success "Docker $(docker --version | cut -d' ' -f3)"

# Check Docker Compose installation
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed."
    echo "Install: curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-Linux-x86_64 -o /usr/local/bin/docker-compose"
    exit 1
fi
print_success "Docker Compose $(docker-compose --version | cut -d' ' -f3)"

# Check Docker daemon
if ! docker ps &> /dev/null; then
    print_error "Docker daemon is not running or you don't have permission."
    echo "Fix: sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
fi
print_success "Docker daemon is running"

# Get current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

print_info "Working directory: $(pwd)"

# Parse arguments
MODE="${1:-up}"
SERVICES="${2:-all}"

case $MODE in
    up)
        print_header "Starting PicoClaw Services"
        
        # Check if images exist
        print_info "Checking Docker images..."
        
        # Build if needed
        if [ "$SERVICES" = "all" ] || [ "$SERVICES" = "build" ]; then
            print_info "Building Docker images..."
            docker-compose build --pull
            print_success "Images built successfully"
        fi
        
        # Start services
        print_info "Starting services..."
        if [ "$SERVICES" = "all" ]; then
            docker-compose up -d
            print_success "All services started"
        else
            docker-compose up -d $SERVICES
            print_success "Services started: $SERVICES"
        fi
        
        # Wait for services to be healthy
        print_info "Waiting for services to become healthy..."
        sleep 5
        
        # Check service status
        print_header "Service Status"
        docker-compose ps
        
        # Print access information
        print_header "Access Information"
        
        if docker-compose exec dashboard ls /dev/null 2>/dev/null; then
            print_success "Dashboard: http://localhost:8501"
        fi
        if docker-compose exec picotradeagent ls /dev/null 2>/dev/null; then
            print_success "API Backend: http://localhost:5000"
        fi
        if docker-compose exec redis ls /dev/null 2>/dev/null; then
            print_success "Redis: localhost:6379"
        fi
        if docker-compose exec nginx ls /dev/null 2>/dev/null; then
            print_success "Nginx Proxy: http://localhost:80"
        fi
        
        echo ""
        print_info "View logs: docker-compose logs -f"
        print_info "Stop all: docker-compose down"
        print_info "Stop specific: docker-compose stop <service>"
        ;;
        
    down|stop)
        print_header "Stopping PicoClaw Services"
        docker-compose down
        print_success "Services stopped"
        
        if [ "$1" = "down" ]; then
            print_warning "Note: Volumes are preserved. Use 'docker-compose down -v' to remove volumes."
        fi
        ;;
        
    restart)
        print_header "Restarting PicoClaw Services"
        docker-compose restart
        print_success "Services restarted"
        
        sleep 3
        docker-compose ps
        ;;
        
    logs)
        SERVICE="${2:-}"
        if [ -z "$SERVICE" ]; then
            docker-compose logs -f
        else
            docker-compose logs -f "$SERVICE"
        fi
        ;;
        
    status)
        print_header "Service Status"
        docker-compose ps
        
        print_header "Resource Usage"
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
        ;;
        
    test)
        print_header "Running Tests"
        
        SERVICE="${2:-dashboard}"
        
        case $SERVICE in
            dashboard)
                print_info "Running dashboard tests..."
                docker-compose exec dashboard python -m pytest tests/test_phase8_integration.py -v
                ;;
            api)
                print_info "Running API tests..."
                docker-compose exec picotradeagent python -m pytest tests/test_phase7_api.py -v
                ;;
            all)
                print_info "Running all tests..."
                docker-compose exec dashboard python -m pytest tests/test_phase8_integration.py -v
                docker-compose exec picotradeagent python -m pytest tests/test_phase7_api.py -v
                ;;
            *)
                print_error "Unknown test: $SERVICE"
                echo "Available: dashboard, api, all"
                exit 1
                ;;
        esac
        ;;
        
    shell)
        SERVICE="${2:-picotradeagent}"
        print_info "Connecting to $SERVICE shell..."
        docker-compose exec "$SERVICE" bash
        ;;
        
    health)
        print_header "Health Check"
        
        print_info "Checking Dashboard..."
        if curl -s http://localhost:8501/_stcore/health > /dev/null 2>&1; then
            print_success "Dashboard is healthy"
        else
            print_warning "Dashboard is not responding"
        fi
        
        print_info "Checking API Backend..."
        if curl -s http://localhost:5000/health > /dev/null 2>&1; then
            print_success "API Backend is healthy"
        else
            print_warning "API Backend is not responding"
        fi
        
        print_info "Checking Redis..."
        if docker-compose exec redis redis-cli ping 2>/dev/null | grep -q PONG; then
            print_success "Redis is healthy"
        else
            print_warning "Redis is not responding"
        fi
        ;;
        
    clean)
        print_header "Cleaning Up"
        print_warning "This will remove all containers and volumes!"
        read -p "Continue? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose down -v
            print_success "Cleanup complete"
        else
            print_info "Cleanup cancelled"
        fi
        ;;
        
    build)
        print_header "Building Docker Images"
        docker-compose build --pull
        print_success "Build complete"
        ;;
        
    version)
        echo "PicoClaw Finance Agent Docker Deployment"
        echo "Phase: 8 - Complete"
        echo "Docker: $(docker --version)"
        echo "Docker Compose: $(docker-compose --version)"
        ;;
        
    help|*)
        cat << EOF

PicoClaw Finance Agent - Docker Deployment Script

Usage: $(basename "$0") <command> [options]

Commands:
    up [service]        Start services (default: all)
                        Example: $(basename "$0") up dashboard
    
    down                Stop services (keep volumes)
    
    stop                Same as 'down'
    
    restart             Restart all services
    
    logs [service]      View logs (default: all)
                        Example: $(basename "$0") logs dashboard
    
    status              Show service status and resource usage
    
    test [type]         Run tests (dashboard, api, all)
                        Example: $(basename "$0") test dashboard
    
    shell [service]     Connect to shell (default: picotradeagent)
                        Example: $(basename "$0") shell dashboard
    
    health              Check service health
    
    build               Build Docker images
    
    clean               Remove containers and volumes (WARNING!)
    
    version             Show version information
    
    help                Show this help message

Services:
    - picotradeagent    Main trading engine & API
    - dashboard         Streamlit web dashboard
    - redis             Data cache
    - nginx             Reverse proxy
    - prometheus        Metrics collection
    - grafana           Monitoring dashboard (port 3000)
    - adminer           Database tool (port 8080)

Examples:
    Start all services:
        $(basename "$0") up
    
    Start just the dashboard and API:
        $(basename "$0") up "dashboard picotradeagent"
    
    View dashboard logs:
        $(basename "$0") logs dashboard
    
    Run tests:
        $(basename "$0") test all
    
    Get service status:
        $(basename "$0") status
    
    Check health:
        $(basename "$0") health

For more information, see PHASE8_DOCKER_DEPLOYMENT.md

EOF
        ;;
esac

exit 0
