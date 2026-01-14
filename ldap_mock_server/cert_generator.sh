create_openssl_config() {
    # Set variables for new directory and host details
    DATE_STR=$(date +%Y%m%d_%H%M%S)
    CERT_DIR="certificates_$DATE_STR"
    # The hostname/IP used in your previous attempts
    IP_ADDR="172.31.12.105"
    HOST_FQDN="ip-172-31-12-105"

    # Create a clean directory and enter it
    mkdir -p "$CERT_DIR"
    cd "$CERT_DIR"

    # 1. Create a dynamic OpenSSL configuration file (openssl.cnf)
    cat > openssl.cnf <<EOF
[ req ]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[ dn ]
C = BR
ST = Brazil
L = Sao Paulo
O = Mock-LDAP-CA
CN = Mock-LDAP-CA-Root

[ v3_req ]
subjectAltName = @alt_names

[ v3_ca ]
# This section MUST exist and MUST contain CA:TRUE for the root cert
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = CA:FALSE
subjectAltName = @alt_names

[ v3_ext ]
subjectAltName = @alt_names
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment

[ alt_names ]
IP.1 = ${IP_ADDR}
IP.2 = 172.17.0.1
DNS.1 = ${HOST_FQDN}
DNS.2 = "mock.com"
EOF
    echo "Created OpenSSL config file in $CERT_DIR/openssl.cnf"
}


generate_certificates() {
    echo "Generating CA Root Key and Certificate..."
    # 2. Generate CA Private Key (ca-root.key) and Self-Signed Certificate (ca-root.crt)
    openssl req -x509 -nodes -new -sha256 \
        -days 3650 \
        -keyout ca-root.key \
        -out ca-root.crt \
        -config openssl.cnf \
        -extensions v3_ext
    
    echo "CA Root Certificate generated."
}
generate_server_key() {
    echo "Generating Server Key and CSR..."
    # 3. Generate Server Private Key (ldap-server.key)
    openssl genrsa -out ldap-server.key 4096

    # 4. Generate Server Certificate Signing Request (ldap-server.csr)
    # CN must match the primary hostname/IP used for connection
    openssl req -new -sha256 \
	-nodes \
        -key ldap-server.key \
        -out ldap-server.csr \
        -config openssl.cnf
}

sign_server_cert() {
    echo "Signing Server Certificate..."
    # 5. Sign the Server Certificate with the CA Root
    openssl x509 -req -sha256 \
        -days 365 \
        -in ldap-server.csr \
        -CA ca-root.crt \
        -CAkey ca-root.key \
        -CAcreateserial \
        -out ldap-server.crt \
        -extfile openssl.cnf \
        -extensions v3_ext
}

verify_certs() {
    echo "Verifying key pair match..."
    # 6. Verify that the server key and server certificate match
    if openssl x509 -noout -modulus -in ldap-server.crt | openssl md5 && \
        openssl rsa -noout -modulus -in ldap-server.key | openssl md5 ; then
        echo "SUCCESS: Certificate and Key Moduli MATCH."
    else
        echo "ERROR: Certificate and Key Moduli DO NOT MATCH."
    fi

    # Clean up temporary files
    rm ldap-server.csr ca-root.srl
    cd ..
    echo "New certificates are ready."
}


run_full_generation() {
    # Ensure you are not inside a previous certificate directory
    cd ~/ldap_mock_server

    create_openssl_config
    generate_certificates
    generate_server_key
    sign_server_cert
    verify_certs
}

run_full_generation
