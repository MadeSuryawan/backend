#!/bin/bash
# Generate self-signed certificates for Redis SSL/TLS

set -e

CERT_DIR="${1:-secrets/redis-certs}"
DAYS=365
KEY_SIZE=4096

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Redis SSL Certificate Generator ===${NC}"
echo ""

# Resolve directory path (handle both absolute and relative)
if [[ "$CERT_DIR" = /* ]]; then
    FULL_CERT_DIR="$CERT_DIR"
else
    # Get the directory where the script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    FULL_CERT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/$CERT_DIR"
fi

# Create directory with parents if needed
echo -e "${YELLOW}Creating certificate directory: $FULL_CERT_DIR${NC}"
if ! mkdir -p "$FULL_CERT_DIR"; then
    echo -e "${RED}Error: Failed to create directory $FULL_CERT_DIR${NC}"
    exit 1
fi

# Check if directory is writable
if [[ ! -w "$FULL_CERT_DIR" ]]; then
    echo -e "${RED}Error: Directory $FULL_CERT_DIR is not writable${NC}"
    exit 1
fi

cd "$FULL_CERT_DIR"
echo -e "${GREEN}✓${NC} Working directory: $(pwd)"
echo ""

# Generate CA
echo -e "${GREEN}1. Generating CA certificate...${NC}"
openssl genrsa -out ca-key.pem $KEY_SIZE 2>/dev/null
openssl req -new -x509 -sha256 -days $DAYS \
  -key ca-key.pem \
  -out ca-cert.pem \
  -subj "/C=US/ST=State/L=City/O=BaliBlissed/CN=Redis CA"
echo -e "   ${GREEN}✓${NC} CA certificate: ca-cert.pem"

# Generate Server Certificate
echo -e "${GREEN}2. Generating Redis server certificate...${NC}"
openssl genrsa -out redis-server-key.pem $KEY_SIZE 2>/dev/null
openssl req -new -sha256 \
  -key redis-server-key.pem \
  -out redis-server.csr \
  -subj "/C=US/ST=State/L=City/O=BaliBlissed/CN=localhost"

cat > redis-server-ext.cnf << EOF
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = redis
DNS.3 = *.redis.cache.windows.net
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

openssl x509 -req -sha256 -days $DAYS \
  -in redis-server.csr \
  -CA ca-cert.pem \
  -CAkey ca-key.pem \
  -CAcreateserial \
  -out redis-server-cert.pem \
  -extfile redis-server-ext.cnf 2>/dev/null

echo -e "   ${GREEN}✓${NC} Server certificate: redis-server-cert.pem"
echo -e "   ${GREEN}✓${NC} Server private key: redis-server-key.pem"

# Generate Client Certificate
echo -e "${GREEN}3. Generating Redis client certificate (for mTLS)...${NC}"
openssl genrsa -out redis-client-key.pem $KEY_SIZE 2>/dev/null
openssl req -new -sha256 \
  -key redis-client-key.pem \
  -out redis-client.csr \
  -subj "/C=US/ST=State/L=City/O=BaliBlissed/CN=redis-client"

cat > redis-client-ext.cnf << EOF
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
EOF

openssl x509 -req -sha256 -days $DAYS \
  -in redis-client.csr \
  -CA ca-cert.pem \
  -CAkey ca-key.pem \
  -CAcreateserial \
  -out redis-client-cert.pem \
  -extfile redis-client-ext.cnf 2>/dev/null

echo -e "   ${GREEN}✓${NC} Client certificate: redis-client-cert.pem"
echo -e "   ${GREEN}✓${NC} Client private key: redis-client-key.pem"

# Clean up CSR, config files, and serial files
rm -f *.csr *.cnf *.srl

# Set restrictive permissions
echo ""
echo -e "${GREEN}4. Setting secure file permissions...${NC}"
chmod 600 *-key.pem
chmod 644 *.pem
echo -e "   ${GREEN}✓${NC} Private keys: 600 (owner read/write only)"
echo -e "   ${GREEN}✓${NC} Certificates: 644 (world readable)"

# Create combined CA bundle
cat ca-cert.pem > ca-bundle.crt
echo -e "   ${GREEN}✓${NC} CA bundle: ca-bundle.crt"

echo ""
echo -e "${GREEN}=== Certificate Generation Complete ===${NC}"
echo ""
echo "Files in $FULL_CERT_DIR:"
ls -la *.pem *.crt 2>/dev/null || ls -la
echo ""
echo -e "${YELLOW}Configuration for .env:${NC}"
echo "----------------------------------------"
echo "# For Redis server using these certificates:"
echo "REDIS_SSL=true"
echo "REDIS_SSL_CA_CERTS=$CERT_DIR/ca-cert.pem"
echo ""
echo "# For mTLS (mutual TLS):"
echo "REDIS_SSL_CERTFILE=$CERT_DIR/redis-client-cert.pem"
echo "REDIS_SSL_KEYFILE=$CERT_DIR/redis-client-key.pem"
echo ""
echo -e "${YELLOW}Verify certificates:${NC}"
echo "  openssl x509 -in $CERT_DIR/ca-cert.pem -text -noout"
echo "  openssl x509 -in $CERT_DIR/redis-server-cert.pem -text -noout"
echo "  openssl verify -CAfile $CERT_DIR/ca-cert.pem $CERT_DIR/redis-server-cert.pem"
