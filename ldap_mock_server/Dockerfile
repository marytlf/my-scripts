# Use a robust OpenLDAP base image which is designed for containers
# This image handles much of the complexity of OpenLDAP configuration.
FROM osixia/openldap:1.5.0

# --- Certificate Setup ---

# 1. Create a directory for the custom certificates inside the container.
# The osixia/openldap image expects certificates in /container/service/slapd/assets/certs/
# or similar, but we'll use a more standard location /container/run/slapd/slapd.d/certs/
# which the image automatically handles when custom certificates are provided.

# 2. Copy the custom certificates from your local directory into the container.
# The image expects the CA root cert, the server cert, and the server key.
# We map the specific names used by the osixia image for custom certs:
#   LDAP_TLS_CACERT_FILE: ca-root.crt
#   LDAP_TLS_CERT_FILE: ldap-server.crt (or ldap-chained.crt if the mock server supports it)
#   LDAP_TLS_KEY_FILE: ldap-server.key
# Note: I'm using ldap-server.crt for the server cert as per standard OpenLDAP setup.
# The ldap-chained.crt is usually used by clients or intermediate CAs.

COPY certificates_20251216_181447/ca-root.crt /container/service/slapd/assets/certs/custom/ca.crt
COPY certificates_20251216_181447/ldap-server.crt /container/service/slapd/assets/certs/custom/server.crt
COPY certificates_20251216_181447/ldap-server.key /container/service/slapd/assets/certs/custom/server.key

# --- Environment Configuration for TLS ---

# Set environment variables to tell the OpenLDAP container to use the custom certificates.
# This forces the use of the copied certs for both LDAPS (636) and STARTTLS (389).
ENV LDAP_TLS_VERIFY_CLIENT=never \
    LDAP_TLS_CACERT_FILE=/container/service/slapd/assets/certs/custom/ca.crt \
    LDAP_TLS_CERT_FILE=/container/service/slapd/assets/certs/custom/server.crt \
    LDAP_TLS_KEY_FILE=/container/service/slapd/assets/certs/custom/server.key

# --- Mock Data Setup (Example Placeholder) ---

# Define the domain for the mock server. Replace with your desired domain.
ENV LDAP_DOMAIN="mock-server.com"
ENV LDAP_ORGANISATION="LDAP Mock"

# Set a password for the admin user (cn=admin,dc=mock-server,dc=com)
# !!! IMPORTANT: CHANGE THIS IN PRODUCTION/REAL USE SCENARIOS !!!
ENV LDAP_ADMIN_PASSWORD="admin_password"

# Optional: Add custom LDIF files for your mock data.
# COPY your_mock_data.ldif /etc/ldap/slapd.d/mock_data/

# --- Expose Ports ---

# Expose the standard LDAP (389) and LDAPS (636) ports
# The base image typically handles starting the service automatically
EXPOSE 389 636

# The CMD is inherited from the base image and starts the slapd service.
