#!/bin/bash

# --- CONFIGURATION ---
IP_ADDR="172.31.12.105"
HOST_FQDN="ip-172-31-12-105"
BASE_DIR=$(pwd)
CERT_DIR="$BASE_DIR/certs"
mkdir -p "$CERT_DIR"

echo "--- Step 1: Generating SSL Certificates ---"

# Create OpenSSL Config
cat > "$CERT_DIR/openssl.cnf" <<EOF
[ req ]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_ca

[ dn ]
C = BR
ST = Brazil
L = Sao Paulo
O = Mock-LDAP-CA
CN = mock-ldap

[ v3_ca ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ v3_ext ]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[ alt_names ]
IP.1 = ${IP_ADDR}
IP.2 = 127.0.0.1
DNS.1 = ${HOST_FQDN}
DNS.2 = localhost
EOF

# Generate CA
openssl req -x509 -nodes -new -sha256 -days 3650 \
    -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" \
    -config "$CERT_DIR/openssl.cnf" -extensions v3_ca

# Generate Server Key and CSR
openssl genrsa -out "$CERT_DIR/ldap.key" 4096
openssl req -new -sha256 -key "$CERT_DIR/ldap.key" -out "$CERT_DIR/ldap.csr" \
    -subj "/C=BR/ST=Brazil/L=Sao Paulo/O=Mock-LDAP-Server/CN=${HOST_FQDN}"

# Sign Server Cert
openssl x509 -req -sha256 -days 365 \
    -in "$CERT_DIR/ldap.csr" -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial -out "$CERT_DIR/ldap.crt" \
    -extfile "$CERT_DIR/openssl.cnf" -extensions v3_ext

# Fix permissions for the container (OpenLDAP user is 1001 or 911 depending on version)
chmod 644 "$CERT_DIR/ldap.crt" "$CERT_DIR/ca.crt"
chmod 600 "$CERT_DIR/ldap.key"
sudo chown -R 911:911 "$CERT_DIR"

echo "--- Step 2: Creating LDIF Setup Files ---"

# Create OU Setup
cat > "$BASE_DIR/ou-setup.ldif" <<EOF
dn: ou=users,dc=mock,dc=com
objectClass: organizationalUnit
ou: users

dn: ou=admin,dc=mock,dc=com
objectClass: organizationalUnit
ou: admin

dn: ou=groups,dc=mock,dc=com
objectClass: organizationalUnit
ou: groups
EOF

echo "Setup complete. Now run: docker-compose up -d"
