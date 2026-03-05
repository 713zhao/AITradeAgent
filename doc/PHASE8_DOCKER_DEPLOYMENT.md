# Phase 8 Docker Deployment Guide

## Overview

This guide covers containerizing and deploying the PicoClaw Finance Agent system with full Streamlit dashboard support using Docker and Docker Compose.

**System Architecture**:
```
Client Browser
    ↓
Nginx (Port 80/443)
    ├→ http://localhost/api/*  → Flask API (5000)
    ├→ http://localhost/dashboard/ → Streamlit Dashboard (8501)
    └→ http://localhost:3000 → Grafana (3000)
    ├→ Redis Cache (6379)
    ├→ Prometheus (9090)
    └→ Adminer DB Admin (8080)
```

## Prerequisites

- Docker 20.10+
- Docker Compose 1.29+
- 4GB+ RAM for containers
- 10GB+ disk space

### Install Docker on Linux

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker $USER
newgrp docker

# CentOS/RHEL
sudo yum install -y docker docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

# Verify installation
docker --version
docker-compose --version
```

## Quick Start

### 1. Clone/Navigate to Project

```bash
cd /home/eric/.picoclaw/workspace/picotradeagent
```

### 2. Build Images

```bash
# Build all services
docker-compose build

# Build only specific services
docker-compose build picotradeagent dashboard
```

### 3. Start Services

```bash
# Start in background
docker-compose up -d

# Start with logs visible
docker-compose up

# Start specific services
docker-compose up -d picotradeagent redis dashboard
```

### 4. Access Services

Once started, services are available at:

- **Dashboard UI**: http://localhost:8501 (or http://localhost/dashboard/)
- **API Backend**: http://localhost:5000
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Adminer**: http://localhost:8080

### 5. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f dashboard
docker-compose logs -f picotradeagent
docker-compose logs -f redis

# Last 100 lines
docker-compose logs --tail=100 -f picotradeagent
```

### 6. Stop Services

```bash
# Stop all services (keep volumes)
docker-compose stop

# Stop all services (remove containers)
docker-compose down

# Stop all services (remove containers and volumes)
docker-compose down -v

# Stop specific services
docker-compose stop dashboard redis
```

## Service Details

### Main Backend Service (picotradeagent)

**Port**: 5000  
**Dockerfile**: `Dockerfile`  
**Base Image**: python:3.11-slim

**Health Check**: Every 30s, timeout 10s

**Key Features**:
- Flask REST API
- Redis integration
- Trading decision system
- Position management
- Risk analysis

**View Logs**:
```bash
docker-compose logs -f picotradeagent
```

**Execute Commands in Container**:
```bash
docker-compose exec picotradeagent python -m pytest tests/
docker-compose exec picotradeagent bash
```

### Streamlit Dashboard Service

**Port**: 8501  
**Dockerfile**: `Dockerfile.ui`  
**Base Image**: python:3.11-slim

**Health Check**: Every 30s, timeout 10s, starts after 10s

**Key Features**:
- Interactive portfolio dashboard
- Real-time risk monitoring
- Performance analytics
- Trade history viewer
- Backtest comparison
- System controls

**Configuration**: `/home/appuser/.streamlit/config.toml`

**View Logs**:
```bash
docker-compose logs -f dashboard
```

**Execute Commands**:
```bash
docker-compose exec dashboard streamlit --version
docker-compose exec dashboard python -m pytest tests/test_phase8_integration.py
```

### Redis Cache Service

**Port**: 6379  
**Image**: redis:7-alpine

**Purpose**:
- Session caching
- Rate limiting
- Real-time data storage
- Trade queue

**View Data**:
```bash
docker-compose exec redis redis-cli
# In Redis CLI:
> KEYS *
> GET key_name
> FLUSHALL  # Clear all
```

### Nginx Reverse Proxy

**Ports**: 80 (HTTP), 443 (HTTPS)  
**Image**: nginx:latest

**Purpose**:
- SSL/TLS termination
- Route requests to services
- Load balancing
- Security headers

**Configuration**: `picotradeagent-nginx.conf`

**Reload Configuration**:
```bash
docker-compose exec nginx nginx -s reload
```

### Prometheus Monitoring

**Port**: 9090  
**Image**: prom/prometheus:latest

**Purpose**:
- Metrics collection
- Time-series database
- 30-day retention

**Configuration**: `prometheus.yml`

### Grafana Dashboard

**Port**: 3000  
**Image**: grafana/grafana:latest

**Default Credentials**:
- Username: `admin`
- Password: `admin`

**Purpose**:
- Visualization of metrics
- Alerting rules
- Dashboard creation

### Adminer Database Admin

**Port**: 8080  
**Image**: adminer:latest

**Purpose**:
- Database browser
- SQL queries
- Data management

## Volume Management

### Docker Volumes

Volumes persist data across container restarts:

```bash
# List all volumes
docker volume ls

# Inspect volume
docker volume inspect picotradeagent_redis-data

# Remove unused volumes
docker volume prune
```

### Named Volumes in Compose

```yaml
volumes:
  redis-data:        # Redis data persistence
  prometheus-data:   # Prometheus metrics
  grafana-data:      # Grafana config & dashboards
```

### Bind Mounts

Application code is mounted directly:

```yaml
volumes:
  - ./finance_service/storage:/app/finance_service/storage  # Persistent storage
  - ./logs:/app/logs                                         # Application logs
```

## Network Configuration

### Docker Network

All services communicate on `picotradeagent-net` bridge network:

```bash
# List networks
docker network ls

# Inspect network
docker network inspect picotradeagent_picotradeagent-net

# View service IPs
docker-compose exec picotradeagent nslookup dashboard
docker-compose exec picotradeagent nslookup redis
```

### Service Discovery

From inside containers, services are resolved by name:

```bash
# From picotradeagent container
http://dashboard:8501    # Access Streamlit
http://redis:6379        # Access Redis
http://nginx:80          # Access Nginx
```

## Production Deployment

### 1. SSL/TLS Certificates

```bash
# Generate self-signed certificate (dev only)
mkdir -p ssl/certs ssl/private
openssl req -x509 -newkey rsa:4096 \
  -keyout ssl/private/finance-agent.key \
  -out ssl/certs/finance-agent.crt \
  -days 365 -nodes \
  -subj "/CN=finance-agent.local"

# Or use Let's Encrypt
sudo certbot certonly --standalone -d your-domain.com
# Copy certs to ./ssl/
```

### 2. Environment Configuration

Create `.env.production`:

```bash
FLASK_ENV=production
PICOTRADEAGENT_ENV=production
STREAMLIT_SERVER_HEADLESS=true
REDIS_URL=redis://redis:6379
LOG_LEVEL=info
```

Pass to docker-compose:

```bash
docker-compose --env-file .env.production up -d
```

### 3. Scaling Services

For high availability, use multiple replicas:

```bash
docker-compose up -d --scale picotradeagent=3
```

Nginx will load-balance across replicas.

### 4. Resource Limits

Edit docker-compose.yml to add:

```yaml
services:
  picotradeagent:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs picotradeagent

# Common fixes
docker-compose down -v    # Clean start
docker-compose build --no-cache  # Rebuild
```

### Port Already in Use

```bash
# Find process using port
lsof -i :8501
sudo kill -9 <PID>

# Or change port in docker-compose.yml
ports:
  - "8502:8501"
```

### Dashboard Not Connecting to API

```bash
# Test connectivity inside dashboard container
docker-compose exec dashboard curl http://picotradeagent:5000/health

# Check network
docker network inspect picotradeagent_picotradeagent-net
```

### Out of Memory

```bash
# Check resource usage
docker stats

# Increase Docker memory limit
# Edit Docker Desktop settings or /etc/docker/daemon.json
```

### Permission Denied Errors

```bash
# Fix file permissions
sudo chown -R $USER:$USER ./finance_service/storage ./logs

# Or run as root (not recommended)
sudo docker-compose up -d
```

### Logs Growing Large

Docker logs are limited by compress settings in docker-compose.yml:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"    # Rotate at 10MB
    max-file: "3"      # Keep 3 files max
```

## Monitoring & Maintenance

### Health Checks

```bash
# Dashboard health
curl http://localhost:8501/_stcore/health

# API health
curl http://localhost:5000/health

# Redis health
docker-compose exec redis redis-cli ping
```

### Container Inspection

```bash
# List running containers
docker-compose ps

# Inspect container
docker-compose exec dashboard bash

# View resource usage
docker stats --no-stream
```

### Log Rotation

```bash
# View log files
docker-compose logs --tail=50 picotradeagent

# Export logs to file
docker-compose logs > logs/docker-compose.log

# Clear logs
docker-compose logs -f --tail=0 > /dev/null
```

### Update Services

```bash
# Pull latest images
docker-compose pull

# Rebuild local images
docker-compose build --pull

# Restart services
docker-compose up -d
```

## Advanced Configuration

### Custom Environment Variables

Create `.env`:

```bash
FLASK_ENV=production
REDIS_URL=redis://redis:6379
API_TIMEOUT=30
LOG_LEVEL=debug
```

Reference in docker-compose.yml:

```yaml
services:
  picotradeagent:
    env_file: .env
```

### Override Compose File

Create `docker-compose.override.yml`:

```yaml
version: '3.8'
services:
  picotradeagent:
    ports:
      - "5001:5000"  # Override port
    environment:
      FLASK_DEBUG: "true"
```

### Custom Networking

For external access to Docker services:

```yaml
networks:
  picotradeagent-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.25.0.0/16
```

## Testing in Docker

### Run Dashboard Tests

```bash
# Integration tests
docker-compose exec dashboard python -m pytest tests/test_phase8_integration.py -v

# Specific test
docker-compose exec dashboard python -m pytest tests/test_phase8_integration.py::TestAPIClientMocking -v

# With coverage
docker-compose exec dashboard python -m pytest tests/ --cov=finance_service
```

### Run API Tests

```bash
docker-compose exec picotradeagent python -m pytest tests/test_phase7_api.py -v
```

## Backup & Recovery

### Backup Data

```bash
# Export database
docker-compose exec picotradeagent \
  sqlite3 /app/finance_service/storage/finance.db \
  ".backup /backup/finance.db.backup"

# Backup volumes
docker run --rm \
  -v picotradeagent_redis-data:/data \
  -v $(pwd)/backups:/backup \
  redis:7-alpine \
  cp -r /data /backup/redis-$(date +%Y%m%d)

# Backup application data
tar -czf backups/app-$(date +%Y%m%d).tar.gz ./finance_service/storage ./logs
```

### Restore Data

```bash
# Restore database
docker-compose exec picotradeagent \
  sqlite3 /app/finance_service/storage/finance.db \
  ".restore /backup/finance.db.backup"

# Restore application data
tar -xzf backups/app-20260304.tar.gz
docker-compose restart
```

## Performance Tuning

### Redis Configuration

Edit docker-compose.yml:

```yaml
redis:
  command: >
    redis-server
    --appendonly yes
    --maxmemory 2gb
    --maxmemory-policy allkeys-lru
```

### Streamlit Performance

Create `.streamlit/config.toml`:

```toml
[client]
showErrorDetails = true

[logger]
level = "info"

[server]
port = 8501
headless = true
maxUploadSize = 200
enableCORS = false
enableXsrfProtection = true

[theme]
primaryColor = "#1f77b4"
```

### Nginx Optimization

Add to nginx config:

```nginx
# Compression
gzip on;
gzip_types text/plain text/css application/json;
gzip_min_length 1000;

# Keepalive
keepalive_timeout 65;
keepalive_requests 100;

# Caching
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m;
```

## Security Best Practices

### 1. Use Secrets Management

```bash
# Generate secure passwords
openssl rand -base64 32

# Use Docker secrets or .env file (keep private)
echo "MONGO_PASSWORD=secure_password" > .env.production
chmod 600 .env.production
```

### 2. Non-Root User

All containers run as `appuser` (non-root):

```dockerfile
USER appuser
```

### 3. Network Isolation

Services only communicate via bridge network:

```yaml
networks:
  picotradeagent-net:
    driver: bridge
```

### 4. SSL/TLS

Always use HTTPS in production. Nginx handles SSL termination.

### 5. Regular Updates

```bash
# Update base images
docker pull python:3.11-slim
docker pull nginx:latest
docker-compose build --pull
```

## Useful Docker Commands

```bash
# View all containers (including stopped)
docker ps -a

# Remove unused images/containers/volumes
docker system prune -a --volumes

# View image layers
docker history picotradeagent:latest

# Build specific image
docker build -f Dockerfile.ui -t picotradeagent-dashboard:latest .

# Push to registry
docker tag picotradeagent:latest myregistry/picotradeagent:1.0
docker push myregistry/picotradeagent:1.0

# Run one-off command
docker-compose run --rm picotradeagent python -c "print('test')"

# Copy files from container
docker cp picotradeagent:/app/logs ./local-logs

# Inspect network traffic
docker-compose exec picotradeagent tcpdump -i eth0
```

## Next Steps

1. **Configure SSL Certificates**: Generate or obtain valid SSL certs for HTTPS
2. **Set Environment Variables**: Create `.env.production` with secure values
3. **Deploy to Cloud**: Use Docker Swarm, Kubernetes, or cloud services
4. **Monitor in Production**: Configure alerts in Prometheus/Grafana
5. **Backup Strategy**: Set up automated backups of Redis and application data
6. **CI/CD Pipeline**: Automate builds and deployments with GitHub Actions

## Support

For issues or questions:

1. Check logs: `docker-compose logs -f`
2. Test connectivity: `docker-compose exec dashboard curl http://picotradeagent:5000/health`
3. Verify volumes: `docker volume ls`
4. Inspect images: `docker images`
5. Check resource usage: `docker stats`

---

**Last Updated**: March 4, 2026  
**Phase**: 8 - Complete  
**Status**: ✅ Production Ready
