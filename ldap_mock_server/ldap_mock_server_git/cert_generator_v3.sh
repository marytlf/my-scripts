#!/bin/bash

# --- CONFIGURATION VARIABLES ---
# The IP/Hostname your clients will use to connect to the LDAP server
IP_ADDR="$(hostname -i | awk -F\  '{print $1}')"
HOST_FQDN="$(hostname)"

# The base path where the certificates will be created (Your current directory)
BASE_DIR=$(pwd)
# -------------------------------



# Function to create the necessary Organizational Units (OUs)
create_ou_ldif() {
    echo "Creating organizational units setup file (ou-setup.ldif)..."
    # Create the LDIF file in the base directory where users.ldif is expected to be
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
    echo "ou-setup.ldif created in $BASE_DIR"
}

create_tls_fix_ldif() {
    echo "Creating TLS CA fix file (tls-ca-fix.ldif)..."
    cat > "$BASE_DIR/tls-ca-fix.ldif" <<EOF
dn: cn=config
changetype: modify
replace: olcTLSCACertFile
olcTLSCACertFile: /container/service/slapd/assets/certs/ca.crt
-
replace: olcTLSCACertPath
olcTLSCACertPath: /container/service/slapd/assets/certs
EOF
}


# Function to load the LDAP data files into the running container
load_ldap_data() {
    echo "--- Loading LDAP data into mock-ldap container ---"
    
    # Define file paths
    OU_FILE="ou-setup.ldif"
    USERS_FILE="users.ldif"
    TLS_FIX_FILE="tls-ca-fix.ldif"

    # 1. Copy and load the TLS CA Fix
    echo "Applying TLS CA configuration fix..."
    docker cp "$BASE_DIR/$TLS_FIX_FILE" mock-ldap:/tmp/$TLS_FIX_FILE

    # Use ldapmodify to apply the fix
    docker exec mock-ldap ldapmodify -Q -Y EXTERNAL -H ldapi:/// -f /tmp/$TLS_FIX_FILE

    # 1. Copy the OU setup file into the container
    echo "Copying $OU_FILE to container..."
    docker cp "$BASE_DIR/$OU_FILE" mock-ldap:/tmp/$OU_FILE
    
    # 2. Load the Organizational Units
    echo "Loading Organizational Units..."
    docker exec mock-ldap ldapadd -x -D "cn=admin,dc=mock,dc=com" -w "testpass" -f /tmp/$OU_FILE
    
    # 3. Copy the users.ldif file into the container
    # NOTE: Assuming users.ldif is in your BASE_DIR (~/ldap_mock_server)
    echo "Copying $USERS_FILE to container..."
    docker cp "$BASE_DIR/$USERS_FILE" mock-ldap:/tmp/$USERS_FILE
    
    # 4. Load the Users and Groups
    echo "Loading users and groups from $USERS_FILE..."
    docker exec mock-ldap ldapadd -x -D "cn=admin,dc=mock,dc=com" -w "testpass" -f /tmp/$USERS_FILE
    
    # Verify a user was added (e.g., alice)
    echo "Verifying 'alice' entry was added..."
    docker exec mock-ldap ldapsearch -x -H ldap://127.0.0.1:389 \
        -D "cn=admin,dc=mock,dc=com" -w "testpass" \
        -b "cn=alice,ou=users,dc=mock,dc=com"
}

create_openssl_config() {
    # Set variables for new directory and host details
    DATE_STR=$(date +%Y%m%d_%H%M%S)
    #CERT_DIR="certificates_$DATE_STR"
    CERT_DIR="certs"
    export CERT_DIR

    # Create a clean directory and enter it
    mkdir -p "$CERT_DIR"
    cd "$CERT_DIR"

    echo "Entering directory: $(pwd)"

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
# CA Root Common Name
CN = mock-ldap

[ v3_req ]
subjectAltName = @alt_names

[ v3_ca ]
# This section MUST exist and MUST contain CA:TRUE for the root cert
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = CA:TRUE
subjectAltName = @alt_names

[ v3_ext ]
# Server Certificate Extensions
subjectAltName = @alt_names
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[ alt_names ]
IP.1 = ${IP_ADDR}
IP.2 = 172.17.0.1
IP.3 = 127.0.0.1
DNS.1 = ${HOST_FQDN}
DNS.2 = mock-ldap
DNS.3 = localhost
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
        -extensions v3_ca
    
    echo "CA Root Certificate generated."
}

generate_server_key() {
    echo "Generating Server Key and CSR..."
    
    # 3. Generate Server Private Key (ldap-server.key)
    openssl genrsa -out ldap-server.key 4096
    
    # Set restrictive permissions for the key immediately
    chmod 600 ldap-server.key

    # 4. Generate Server Certificate Signing Request (ldap-server.csr)
    # FIX: Use -subj to explicitly set the server's DN (CN)
    DN_STRING="/C=BR/ST=Brazil/L=Sao Paulo/O=Mock-LDAP-Server/CN=${HOST_FQDN}"
    openssl req -new -sha256 \
        -key ldap-server.key \
        -out ldap-server.csr \
        -config openssl.cnf \
        -subj "${DN_STRING}"
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

change_names(){
    echo "Changing names..."
    mv ldap-server.key ldap.key 
    mv ca-root.crt ca.crt 
    mv ldap-server.crt ldap.crt 
}

verify_certs() {
    echo "Verifying key pair match..."
    # 6. Verify that the server key and server certificate match
    if openssl x509 -noout -modulus -in ldap-server.crt | openssl md5 && \
        openssl rsa -noout -modulus -in ldap-server.key | openssl md5 ; then
        echo "SUCCESS: Certificate and Key Moduli MATCH."
        
        # 🌟 FIX: Create the chained certificate for OpenLDAP
        echo "Creating chained server certificate (ldap-chained.crt)..."
        cat ldap-server.crt ca-root.crt > ldap-chained.crt
        chmod 600 ldap-server.key ca-root.key 
        change_names
        echo "Changing file ownership to UID:911 for container access..."
        sudo chown -R 911:911 ./*
        
        # Clean up temporary files
        rm ldap-server.csr ca-root.srl
    else
        echo "ERROR: Certificate and Key Moduli DO NOT MATCH. Aborting."
        return 1
    fi

    cd "$BASE_DIR" # Return to the starting directory
    echo "New certificates are ready in directory: ${CERT_DIR}"
}



run_docker_old() {
    echo "--- Running Docker container with new certificates ---"
    
    # Stop/Remove any existing mock-ldap container
    echo "Stopping and removing existing 'mock-ldap' container..."
    docker stop mock-ldap &> /dev/null
    docker rm mock-ldap &> /dev/null

    # Full path to the certificates
    CERT_PATH="${BASE_DIR}/${CERT_DIR}"
    
    echo "Mounting certificates from: ${CERT_PATH}"

    # 1. Start the Docker container
    # Verify that there are NO spaces after the \ character on any of these lines
    docker run -d \
        --name mock-ldap \
        -p 389:389 -p 636:636 \
        -e LDAP_ADMIN_PASSWORD=testpass \
        -e LDAP_DOMAIN="mock.com" \
        -e LOG_LEVEL=debug \
        -e SLAPD_DEBUG=256 \
        -e LDAP_LOGLEVEL=65535 \
        -v "${CERT_PATH}/ldap-chained.crt:/container/service/slapd/assets/certs/ldap.crt" \
        -v "${CERT_PATH}/ldap-server.key:/container/service/slapd/assets/certs/ldap.key" \
        -v "${CERT_PATH}/ca-root.crt:/container/service/slapd/assets/certs/ca.crt" \
        --env LDAP_TLS=true \
        --env LDAP_TLS_CRT_FILE=ldap.crt \
        --env LDAP_TLS_KEY_FILE=ldap.key \
        --env LDAP_TLS_CA_CRT_FILE=ca.crt \
        osixia/openldap:latest 
    
    # Check if the container started successfully before proceeding
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to start Docker container."
        return 1
    fi
    
    echo "Container started. Waiting 15 seconds for LDAP service initialization..."
    # 2. Wait for the LDAP service to be ready
    sleep 15 
    
    # 3. Load the data
    load_ldap_data
    
    echo "SUCCESS: Docker container 'mock-ldap' is running and data is loaded."
    echo "To check logs: docker logs -f mock-ldap"
}

run_docker() {
    echo "--- Running Docker container with new certificates ---"

    # Stop/Remove any existing mock-ldap container
    echo "Stopping and removing existing 'mock-ldap' container..."
    # Stop/Remove existing container
    docker stop mock-ldap &> /dev/null
    docker rm mock-ldap &> /dev/null

    # Full path to the certificates
    CERT_PATH="${BASE_DIR}/${CERT_DIR}"

    # Run Bitnami OpenLDAP
    docker run -d \
        --name mock-ldap \
        -p 389:389 -p 636:636 \
        -e LDAP_ADMIN_USERNAME=admin \
        -e LDAP_ADMIN_PASSWORD=testpass \
        -e LDAP_BASE=dc=mock,dc=com \
        -e LDAP_TLS_VERIFY_CLIENT=allow \
        -e LDAP_TLS_PORT=636 \
        -e LDAP_TLS_KEY_FILE=/certs/ldap.key \
        -e LDAP_TLS_CERT_FILE=/certs/ldap.crt \
        -e LDAP_TLS_CA_FILE=/certs/ca.crt \
        -v "${CERT_PATH}/ldap-server.key:/certs/ldap.key:ro" \
        -v "${CERT_PATH}/ldap-chained.crt:/certs/ldap.crt:ro" \
        -v "${CERT_PATH}/ca-root.crt:/certs/ca.crt:ro" \
        bitnami/openldap:latest
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to start Docker container."
        return 1
    fi

    echo "Container started. Waiting 15 seconds for LDAP service initialization..."
    sleep 15

    # Check the 636 port listener status
    echo "Checking 636 port listener health..."
    docker logs mock-ldap | grep "slapd starting"

    echo "SUCCESS: Docker container 'mock-ldap' is running."
    echo "If you still see 'No certificate was found', the issue is an internal bug in the osixia image."
}

# --- Main Execution ---
run_full_generation() {
    create_openssl_config || return 1
    generate_certificates || return 1
    generate_server_key || return 1
    sign_server_cert || return 1
    verify_certs || return 1
    
    #create_ou_ldif
    #create_tls_fix_ldif
    #run_docker
}

run_full_generation
