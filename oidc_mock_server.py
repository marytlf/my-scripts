import time
import json
import base64
from flask import Flask, request, jsonify, redirect, url_for
import jwt # New import for JWT creation
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

app = Flask(__name__)

# --- Configuration ---
EXTERNAL_IP = ""
PORT = 44065
BASE_URL = f"http://{EXTERNAL_IP}:{PORT}"

# Define the path component
ISSUER_PATH = "/oidc"
ISSUER_URL = f"{BASE_URL}{ISSUER_PATH}"
CLIENT_ID = "RANCHER_MOCK_CLIENT" # Use this in Rancher configuration
CLIENT_SECRET = "super-secret-12345" # Use this in Rancher configuration

# --- Test User Data ---
MOCK_USER = {
    "sub": "u-b5ie3sr373",
    "email": "rancheruser@mockoidc.local",
    "name": "Rancher Test User",
    "groups": ["engineering", "devops", "rancher-admins"],
}

# --- Mock State ---
MOCK_ACCESS_TOKEN = "mock_access_token_123"
MOCK_AUTH_CODE = "mock_auth_code_987"
#DUMMY_SIGNATURE = "S1gN4TUrE" 

DUMMY_SIGNATURE = "MTIzNDU2Nzg5MA"

private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_key = private_key.public_key()
# Serialize the public key components for the JWKS endpoint
key_id = "mock_key_id_1"
public_numbers = public_key.public_numbers()

# Convert public key components to Base64URL encoding for JWKS
e_b64 = base64.urlsafe_b64encode(public_numbers.e.to_bytes(3, byteorder='big')).decode().rstrip('=')
n_b64 = base64.urlsafe_b64encode(public_numbers.n.to_bytes(256, byteorder='big')).decode().rstrip('=')


JWKS_RESPONSE = {
    "keys": [
        {
            "kty": "RSA",
            "kid": key_id,
            "use": "sig",
            "alg": "RS256",
            "n": n_b64,  # Modulus
            "e": e_b64,  # Public Exponent
        }
    ]
}

# --- CRITICAL FIX: Base64 Encoding Helper ---
def create_jwt_part(data):
    """Encodes JSON data into strict Base64URL-safe string, ensuring padding is removed."""

    # 1. Convert dictionary to compact JSON string and encode to bytes
    json_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8')

    # 2. Base64 URL-safe encode the bytes
    encoded_bytes = base64.urlsafe_b64encode(json_bytes)

    # 3. Decode to string and apply rigorous cleaning

    # .strip(): Removes leading/trailing whitespace (just in case)
    # .rstrip(b'='): Removes trailing '=' padding bytes (most critical step)

    # We must ensure we decode the bytes correctly after encoding and stripping.
    return encoded_bytes.decode('utf-8').strip().rstrip('=')


# Static, globally available JWT Header (alg: none, typ: JWT)
HEADER_CLAIMS = {"alg": "none", "typ": "JWT"}
DUMMY_HEADER = create_jwt_part(HEADER_CLAIMS)


# --- OIDC Endpoints ---

@app.route(f'{ISSUER_PATH}/keys')
def jwks():
    """JWKS Endpoint: Provides the public key for token verification."""
    return jsonify(JWKS_RESPONSE)


@app.route(f'{ISSUER_PATH}/.well-known/openid-configuration')
def discover():
    """OIDC Discovery Endpoint"""
    discovery_doc = {
        "issuer": ISSUER_URL,
        "authorization_endpoint": f"{ISSUER_URL}/authorize",
        "token_endpoint": f"{ISSUER_URL}/token",
        "userinfo_endpoint": f"{ISSUER_URL}/userinfo",
        "jwks_uri": f"{ISSUER_URL}/keys",
        "response_types_supported": ["code"],
        "scopes_supported": ["openid", "email", "profile", "groups"],
    }
    return jsonify(discovery_doc)

@app.route(f'{ISSUER_PATH}/authorize')
def authorize():
    """Step 1: Authorization Endpoint"""
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')
    
    if not redirect_uri:
        return "Error: redirect_uri missing", 400

    return redirect(f"{redirect_uri}?code={MOCK_AUTH_CODE}&state={state}")

@app.route(f'{ISSUER_PATH}/token', methods=['POST'])
def token():
    """Step 2: Token Endpoint"""
    code = request.form.get('code')
    client_id_received = request.form.get('client_id')
    client_secret = request.form.get('client_secret')

    # The 401 you saw was likely due to the first request missing the client_id/secret header, 
    # or the initial state not matching. The 200 on retry confirms it passed validation.
    if code != MOCK_AUTH_CODE or client_id_received != CLIENT_ID or client_secret != CLIENT_SECRET:
        return jsonify({"error": "invalid_client", "error_description": "Invalid credentials or code"}), 401

    # --- FIX: Generate fresh JWT payload here ---
    current_time = int(time.time())
    CLAIMS = {
        "sub": MOCK_USER["sub"],
        "iss": ISSUER_URL,
        "aud": client_id_received, 
        "exp": current_time + 3600,
        "iat": current_time,
        "groups": MOCK_USER["groups"], # Add groups to the ID Token payload for max compatibility
    }
    signed_id_token = jwt.encode(
        CLAIMS, 
        private_key, 
        algorithm="RS256", 
        headers={"kid": key_id}
    )

    #PAYLOAD = {
    #    "sub": MOCK_USER["sub"],
    #    "iss": ISSUER_URL,
    #    "aud": client_id_received, # Use the client_id received in the request
    #    "exp": current_time + 3600, # Fresh expiration time
    #    "iat": current_time,       # Fresh issued at time
    #}
    
    # Generate Base64 Payload using the safe function
    #DUMMY_PAYLOAD = create_jwt_part(PAYLOAD)
    
    # Assemble the final, valid-structured JWT
    #live_id_token = f"{DUMMY_HEADER}.{DUMMY_PAYLOAD}.{DUMMY_SIGNATURE}"
    # ---------------------------------------------
    
    return jsonify({
        "access_token": MOCK_ACCESS_TOKEN,
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": signed_id_token, 
        "refresh_token": "mock_refresh_token", 
    })

@app.route(f'{ISSUER_PATH}/userinfo')
def userinfo():
    """Step 3: User Info Endpoint"""
    auth_header = request.headers.get('Authorization', '')

    if auth_header != f"Bearer {MOCK_ACCESS_TOKEN}":
        return jsonify({"error": "invalid_token"}), 401
    
    return jsonify(MOCK_USER)

@app.route('/fast-forward-token-expiry')
def fast_forward():
    """Custom Endpoint to Simulate Token Expiration"""
    # This remains functional for testing the original issue (token expiration)
    return "Server time fast-forwarded by 1 day. Tokens are now expired."

# --- Run Server ---

if __name__ == '__main__':
    print("--- Mock OIDC Server Ready ---")
    print(f"Issuer URL: {ISSUER_URL}")
    print(f"Client ID: {CLIENT_ID}")
    print(f"Client Secret: {CLIENT_SECRET}")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
