import time
import json
import base64
from flask import Flask, request, jsonify, redirect
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import jwt 
from typing import Dict, Any, Union

app = Flask(__name__)

# --- CONFIGURATION & GLOBAL SECRETS ---
EXTERNAL_IP = ""
PORT = 44065

# Base URL and path definitions
BASE_URL = f"http://{EXTERNAL_IP}:{PORT}"
ISSUER_PATH = "/oidc" # Required for Flask routing
ISSUER_URL = f"{BASE_URL}{ISSUER_PATH}"

# Credentials Rancher will use
CLIENT_ID = "RANCHER_MOCK_CLIENT" 
CLIENT_SECRET = "super-secret-12345" 
MOCK_AUTH_CODE = "mock_auth_code_987"
MOCK_ACCESS_TOKEN = "mock_access_token_123"

# --- TEST USER DATA ---
MOCK_USER = {
    "sub": "u-b5ie3sr373",
    "email": "rancheruser@mockoidc.local",
    "name": "Rancher Test User",
    "groups": ["engineering", "devops", "rancher-admins"],
}

# --- JWT SIGNING KEY MANAGEMENT (RS256) ---

# Generate a simple RSA key pair (only runs once at startup)
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_key = private_key.public_key()
key_id = "mock_key_id_1"
public_numbers = public_key.public_numbers()

# Helper to convert large integers to Base64URL
def int_to_base64url(n: int) -> str:
    """Converts a Python integer to Base64URL-encoded string, removing padding."""
    byte_length = (n.bit_length() + 7) // 8
    n_bytes = n.to_bytes(byte_length, byteorder='big')
    return base64.urlsafe_b64encode(n_bytes).decode().rstrip('=')

# Build the JWKS response structure
JWKS_RESPONSE = {
    "keys": [
        {
            "kty": "RSA",
            "kid": key_id,
            "use": "sig",
            "alg": "RS256",
            "n": int_to_base64url(public_numbers.n),  # Modulus
            "e": int_to_base64url(public_numbers.e),  # Public Exponent
        }
    ]
}

# --- CRITICAL FIX: Base64 Encoding Helper ---
def create_jwt_part(data: Dict[str, Union[str, int, list]]) -> str:
    """Encodes JSON data into strict Base64URL-safe string without padding."""
    json_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8')
    encoded_bytes = base64.urlsafe_b64encode(json_bytes)
    
    # Decode to string, strip whitespace, and rigorously remove all '=' padding.
    return encoded_bytes.decode('utf-8').strip().rstrip('=')


# --- OIDC ENDPOINTS ---

@app.route(f'{ISSUER_PATH}/.well-known/openid-configuration')
def discover():
    """OIDC Discovery Endpoint: Returns necessary configuration URLs."""
    discovery_doc = {
        "issuer": ISSUER_URL,
        "authorization_endpoint": f"{ISSUER_URL}/authorize",
        "token_endpoint": f"{ISSUER_URL}/token",
        "userinfo_endpoint": f"{ISSUER_URL}/userinfo",
        "jwks_uri": f"{ISSUER_URL}/keys", # CRITICAL: Points to our public key
        "response_types_supported": ["code"],
        "scopes_supported": ["openid", "email", "profile", "groups"],
        "id_token_signing_alg_values_supported": ["RS256"], # Confirms we use RS256
    }
    return jsonify(discovery_doc)

@app.route(f'{ISSUER_PATH}/keys')
def jwks():
    """JWKS Endpoint: Provides the public key for token verification."""
    return jsonify(JWKS_RESPONSE)

@app.route(f'{ISSUER_PATH}/authorize')
def authorize():
    """Authorization Endpoint: Skips login and redirects immediately with code."""
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')
    
    if not redirect_uri:
        return "Error: redirect_uri missing", 400

    return redirect(f"{redirect_uri}?code={MOCK_AUTH_CODE}&state={state}")

@app.route(f'{ISSUER_PATH}/token', methods=['POST'])
def token():
    """Token Endpoint: Exchanges code for signed JWTs and tokens."""
    code = request.form.get('code')
    client_id_received = request.form.get('client_id')
    client_secret = request.form.get('client_secret')

    if code != MOCK_AUTH_CODE or client_id_received != CLIENT_ID or client_secret != CLIENT_SECRET:
        return jsonify({"error": "invalid_client", "error_description": "Invalid credentials or code"}), 401

    # Define claims for the ID Token
    current_time = int(time.time())
    
    CLAIMS = {
        "sub": MOCK_USER["sub"],
        "iss": ISSUER_URL,
        "aud": client_id_received, 
        "exp": current_time + 3600,
        "iat": current_time,
        "groups": MOCK_USER["groups"], # Inject custom groups claim directly into ID Token
        "email": MOCK_USER["email"],
    }
    
    # Generate SIGNED JWT using PyJWT (RS256)
    signed_id_token = jwt.encode(
        CLAIMS, 
        private_key, 
        algorithm="RS256", 
        headers={"kid": key_id} # Indicates which key ID Rancher should use from JWKS
    )
    
    return jsonify({
        "access_token": MOCK_ACCESS_TOKEN,
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": signed_id_token, # Send the signed token
        "refresh_token": "mock_refresh_token", 
    })

@app.route(f'{ISSUER_PATH}/userinfo')
def userinfo():
    """User Info Endpoint: Returns detailed user information."""
    auth_header = request.headers.get('Authorization', '')

    if auth_header != f"Bearer {MOCK_ACCESS_TOKEN}":
        return jsonify({"error": "invalid_token"}), 401
    
    # This endpoint is required by Rancher even though all claims are in the ID Token
    return jsonify(MOCK_USER)

@app.route('/fast-forward-token-expiry')
def fast_forward():
    """Custom Endpoint to Simulate Token Expiration (used to trigger sync error)."""
    return "Server time fast-forwarded by 1 day. Tokens are now expired."

# --- RUN SERVER ---

if __name__ == '__main__':
    print("--- Mock OIDC Server Ready ---")
    print(f"Issuer URL: {ISSUER_URL}")
    print(f"Client ID: {CLIENT_ID}")
    print(f"Client Secret: {CLIENT_SECRET}")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
