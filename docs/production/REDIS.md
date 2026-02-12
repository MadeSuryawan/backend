# Redis Production Setup Guide

Complete guide for configuring Redis with SSL/TLS and authentication in production environments for the BaliBlissed backend.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration Options](#configuration-options)
- [SSL/TLS Certificate Setup](#ssltls-certificate-setup)
- [Cloud Redis Providers](#cloud-redis-providers)
- [Docker Compose Setup](#docker-compose-setup)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

This application supports multiple Redis configurations:

| Mode               | Use Case                 | Security Level |
| ------------------ | ------------------------ | -------------- |
| Local (no auth)    | Development only         | Low            |
| Password only      | Simple production        | Medium         |
| TLS + Password     | Standard production      | High           |
| mTLS (mutual TLS)  | High-security production | Very High      |

## Quick Start

### 1. Generate Development Certificates

```bash
./scripts/generate-redis-certs.sh secrets/redis-certs
```

This creates:

- CA certificate (`ca-cert.pem`)
- Server certificate & key
- Client certificate & key (for mTLS)

### 2. Configure Environment

```bash
# secrets/.env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your-strong-password
REDIS_USERNAME=default              # Redis 6+ ACL
REDIS_SSL=true
REDIS_SSL_CA_CERTS=secrets/redis-certs/ca-cert.pem
```

### 3. Run with Docker Compose

```bash
docker-compose -f docker-compose.redis-ssl.yaml up -d
```

## Configuration Options

### Environment Variables

| Variable                   | Required   | Default     | Description                                |
| -------------------------- | ---------- | ----------- | ------------------------------------------ |
| `REDIS_HOST`               | No         | `localhost` | Redis server hostname                      |
| `REDIS_PORT`               | No         | `6379`      | Redis server port                          |
| `REDIS_DB`                 | No         | `0`         | Database number                            |
| `REDIS_USERNAME`           | No         |  -          | Redis ACL username (Redis 6+)              |
| `REDIS_PASSWORD`           | Yes (prod) |  -          | Authentication password                    |
| `REDIS_URL`                | No         |  -          | Full Redis URL (overrides other settings)  |
| `REDIS_SSL`                | No         | `false`     | Enable TLS/SSL connection                  |
| `REDIS_SSL_CA_CERTS`       | No         |  -          | Path to CA certificates file               |
| `REDIS_SSL_CERT_REQS`      | No         | `required`  | Certificate verification mode              |
| `REDIS_SSL_CERTFILE`       | No         |  -          | Client certificate (mTLS)                  |
| `REDIS_SSL_KEYFILE`        | No         |  -          | Client private key (mTLS)                  |
| `REDIS_SSL_CHECK_HOSTNAME` | No         | `true`      | Verify hostname matches certificate        |

### Certificate Verification Modes

- **`required`** (default) - Full certificate verification
- **`optional`** - Certificate requested but not required
- **`none`** - No verification (insecure, development only)

## SSL/TLS Certificate Setup

### Option 1: Self-Signed Certificates (Development/Testing)

```bash
# Generate all certificates
./scripts/generate-redis-certs.sh secrets/redis-certs

# Files created:
# - ca-cert.pem          # CA certificate (trust anchor)
# - redis-server-cert.pem # Server certificate
# - redis-server-key.pem  # Server private key
# - redis-client-cert.pem # Client certificate (mTLS)
# - redis-client-key.pem  # Client private key
```

### Option 2: Manual Certificate Generation

```bash
# 1. Create directory
mkdir -p secrets/redis-certs && cd secrets/redis-certs

# 2. Generate CA
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -sha256 -days 3650 \
  -key ca-key.pem -out ca-cert.pem \
  -subj "/C=US/ST=State/L=City/O=BaliBlissed/CN=Redis CA"

# 3. Generate Server Certificate
openssl genrsa -out redis-server-key.pem 4096
openssl req -new -sha256 \
  -key redis-server-key.pem -out redis-server.csr \
  -subj "/C=US/ST=State/L=City/O=BaliBlissed/CN=redis.yourdomain.com"

# Create server extensions
cat > redis-server-ext.cnf << 'EOF'
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = redis.yourdomain.com
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

# Sign server certificate
openssl x509 -req -sha256 -days 365 \
  -in redis-server.csr \
  -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -out redis-server-cert.pem \
  -extfile redis-server-ext.cnf

# 4. Set permissions
chmod 600 *-key.pem
chmod 644 *.pem
```

### Option 3: Let's Encrypt (Production with Public Domain)

```bash
# Install certbot
sudo apt install certbot

# Obtain certificate
sudo certbot certonly --standalone -d redis.yourdomain.com

# Certificates location:
# /etc/letsencrypt/live/redis.yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/redis.yourdomain.com/privkey.pem
```

Update `.env`:

```bash
REDIS_SSL_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
REDIS_SSL_CERTFILE=/etc/letsencrypt/live/redis.yourdomain.com/fullchain.pem
REDIS_SSL_KEYFILE=/etc/letsencrypt/live/redis.yourdomain.com/privkey.pem
```

## Cloud Redis Providers

### AWS ElastiCache for Redis

```bash
# Configuration
REDIS_HOST=master.xxxxxx.cache.amazonaws.com
REDIS_PORT=6379
REDIS_PASSWORD=your-auth-token
REDIS_SSL=true
REDIS_SSL_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# Note: AWS uses TLS encryption in transit by default for Redis 6+
# Download CA bundle if needed:
# wget https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

### Redis Cloud (Redis Labs)

```bash
REDIS_HOST=redis-xxxxx.cloud.redislabs.com
REDIS_PORT=16789
REDIS_USERNAME=default
REDIS_PASSWORD=your-password
REDIS_SSL=true
REDIS_SSL_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
```

### Upstash Redis

```bash
# Upstash uses TLS by default
REDIS_URL=rediss://default:password@xxx.upstash.io:6379
```

### Azure Cache for Redis

```bash
REDIS_HOST=xxxxxx.redis.cache.windows.net
REDIS_PORT=6380  # SSL port
REDIS_PASSWORD=your-access-key
REDIS_SSL=true
REDIS_SSL_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
```

### Google Cloud Memorystore

```bash
REDIS_HOST=10.0.0.3  # Private IP via VPC
REDIS_PORT=6378       # TLS port
REDIS_PASSWORD=your-auth-string
REDIS_SSL=true
```

## Docker Compose Setup

### Basic Redis with SSL

Create `docker-compose.redis-ssl.yaml`:

```yaml
services:
  redis-ssl:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6380:6380"
    volumes:
      - redis_ssl_data:/data
      - ./secrets/redis-certs:/certs:ro
    command: >
      redis-server
      --port 0
      --tls-port 6380
      --tls-cert-file /certs/redis-server-cert.pem
      --tls-key-file /certs/redis-server-key.pem
      --tls-ca-cert-file /certs/ca-cert.pem
      --tls-protocols "TLSv1.2 TLSv1.3"
      --requirepass dev-password
      --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "--tls", "--cacert", "/certs/ca-cert.pem", 
             "-a", "dev-password", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  backend:
    build: .
    environment:
      - REDIS_HOST=redis-ssl
      - REDIS_PORT=6380
      - REDIS_PASSWORD=dev-password
      - REDIS_SSL=true
      - REDIS_SSL_CA_CERTS=/app/secrets/redis-certs/ca-cert.pem
    volumes:
      - ./secrets/redis-certs:/app/secrets/redis-certs:ro
    depends_on:
      redis-ssl:
        condition: service_healthy

volumes:
  redis_ssl_data:
```

Run:

```bash
docker-compose -f docker-compose.redis-ssl.yaml up -d
```

### Redis with ACL (User Authentication)

Create `redis-acl.conf`:

```conf
# Redis ACL configuration
user default on >admin-password ~* &* +@all
user app on >app-password ~* &* +@read +@write -@dangerous
user readonly on >readonly-password ~* &* +@read
```

Update Docker Compose:

```yaml
services:
  redis-acl:
    image: redis:7-alpine
    volumes:
      - ./redis-acl.conf:/usr/local/etc/redis/redis.conf:ro
      - ./secrets/redis-certs:/certs:ro
    command: >
      redis-server
      /usr/local/etc/redis/redis.conf
      --tls-port 6380
      --tls-cert-file /certs/redis-server-cert.pem
      --tls-key-file /certs/redis-server-key.pem
      --port 0
```

Configure application:

```bash
REDIS_USERNAME=app
REDIS_PASSWORD=app-password
```

## Security Best Practices

### 1. Password Security

```bash
# Generate strong password (32+ characters)
openssl rand -base64 32

# Or use pwgen
pwgen -s 32 1
```

### 2. File Permissions

```bash
# Private keys should be readable only by owner
chmod 600 secrets/redis-certs/*-key.pem

# Certificates can be world-readable
chmod 644 secrets/redis-certs/*.pem

# Never commit certificates to git
echo "secrets/redis-certs/" >> .gitignore
```

### 3. Network Security

- **Bind to localhost only** for single-server setups:

  ```bash
  --bind 127.0.0.1 ::1
  ```

- **Use VPC/Private subnets** for cloud deployments
- **Enable TLS in transit** always in production
- **Use mTLS** for sensitive data

### 4. Production Checklist

- [ ] Strong password set (32+ characters)
- [ ] TLS/SSL enabled
- [ ] Certificate verification enabled (`REDIS_SSL_CERT_REQS=required`)
- [ ] Valid CA certificates configured
- [ ] Redis not exposed to public internet
- [ ] Authentication enabled (requirepass or ACL)
- [ ] Persistence configured (AOF or RDB)
- [ ] Regular backups scheduled
- [ ] Monitoring and alerting set up
- [ ] Certificate expiration monitoring

## Troubleshooting

### Connection Issues

```bash
# Test basic connectivity
telnet redis-host 6379

# Test TLS connection
openssl s_client -connect redis-host:6380 \
  -CAfile secrets/redis-certs/ca-cert.pem

# Test with redis-cli
redis-cli --tls \
  --cacert secrets/redis-certs/ca-cert.pem \
  --cert secrets/redis-certs/redis-client-cert.pem \
  --key secrets/redis-certs/redis-client-key.pem \
  -h redis-host -p 6380 -a password ping
```

### Certificate Verification

```bash
# Verify certificate chain
openssl verify -CAfile ca-cert.pem redis-server-cert.pem

# Check certificate details
openssl x509 -in redis-server-cert.pem -text -noout

# Check expiration date
openssl x509 -in redis-server-cert.pem -noout -dates
```

### Common Errors

| Error                      | Cause                                    | Solution                                               |
| -------------------------- | ---------------------------------------- | ------------------------------------------------------ |
| `Connection refused`       | Redis not running / wrong port           | Check Redis status and port                            |
| `Authentication failed`    | Wrong password                           | Verify `REDIS_PASSWORD`                                |
| `Certificate verify failed`| Invalid CA cert                          | Check `REDIS_SSL_CA_CERTS` path                        |
| `Hostname mismatch`        | Wrong CN in certificate                  | Set `REDIS_SSL_CHECK_HOSTNAME=false` or regenerate cert|
| `No such file or directory`| Missing cert files                       | Verify paths in configuration                          |

### Enable Debug Logging

```python
# In your application or test script
import logging
logging.basicConfig(level=logging.DEBUG)

# Test connection
from app.clients.redis_client import RedisClient
client = RedisClient()
await client.connect()
```

## Migration from Non-SSL to SSL

### Step-by-Step Migration

1. **Prepare certificates** using the generation script
2. **Configure Redis** to accept both SSL and non-SSL temporarily:

   ```bash
   redis-server \
     --port 6379 \
     --tls-port 6380 \
     --tls-cert-file /certs/server.pem \
     --tls-key-file /certs/server.key
   ```

3. **Update application** to use SSL port
4. **Test thoroughly**
5. **Remove non-SSL port**:

   ```bash
   --port 0  # Disable non-SSL
   ```

### Zero-Downtime Migration (Using Redis Sentinel)

1. Set up Redis Sentinel with SSL
2. Add new SSL-enabled Redis instance
3. Promote to master
4. Update application configuration
5. Decommission old instance

## Additional Resources

- [Redis TLS Documentation](https://redis.io/docs/management/security/encryption/)
- [Redis ACL Documentation](https://redis.io/docs/management/security/acl/)
- [OpenSSL Documentation](https://www.openssl.org/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
