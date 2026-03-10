import time
import json
import base64
import os
from flask import Flask, request, jsonify, redirect
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

app = Flask(__name__)

# --- Configuration ---
EXTERNAL_IP = ""

if (EXTERNAL_IP == ""):
    EXTERNAL_IP = input("Enter external IP/DNS (without https://): ")

PORT = 44065
BASE_URL = f"http://{EXTERNAL_IP}:{PORT}"

ISSUER_PATH = "/oidc"
ISSUER_URL = f"{BASE_URL}{ISSUER_PATH}"
CLIENT_ID = "RANCHER_MOCK_CLIENT"
CLIENT_SECRET = "super-secret-12345"

# --- Auth Code & Token Stores (in-memory, keyed by token -> username) ---
AUTH_CODE_STORE: dict = {}    # auth_code  -> username
ACCESS_TOKEN_STORE: dict = {} # access_token -> username

# --- RSA Key Generation ---
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_key = private_key.public_key()
key_id = "mock_key_id_1"
public_numbers = public_key.public_numbers()

e_b64 = base64.urlsafe_b64encode(public_numbers.e.to_bytes(3, byteorder='big')).decode().rstrip('=')
n_b64 = base64.urlsafe_b64encode(public_numbers.n.to_bytes(256, byteorder='big')).decode().rstrip('=')

JWKS_RESPONSE = {
    "keys": [
        {
            "kty": "RSA",
            "kid": key_id,
            "use": "sig",
            "alg": "RS256",
            "n": n_b64,
            "e": e_b64,
        }
    ]
}

# -------------------------------------------------------------------
# Multi-User Store
# -------------------------------------------------------------------
USERS_FILE = os.path.join(os.path.dirname(__file__), "oidc_users.json")

DEFAULT_USERS = [
    {
        "sub": "u-b5ie3sr373",
        "email": "rancheruser@mockoidc.local",
        "name": "Rancher Test User",
        "username": "rancheruser",
        "password": "password123",
        "groups": ["engineering", "devops", "rancher-admins"],
    }
]


def load_users() -> dict:
    """Load users from JSON file keyed by username. Seeds defaults on first run."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users_list = json.load(f)
        return {u["username"]: u for u in users_list}
    # First run — persist defaults
    save_users({u["username"]: u for u in DEFAULT_USERS})
    return {u["username"]: u for u in DEFAULT_USERS}


def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users.values()), f, indent=2)


def get_user_by_sub(sub: str) -> dict | None:
    """Look up a user by their 'sub' claim."""
    users = load_users()
    return next((u for u in users.values() if u["sub"] == sub), None)


def get_user_by_username(username: str) -> dict | None:
    users = load_users()
    return users.get(username)


# -------------------------------------------------------------------
# User Management Helpers (callable at runtime via /admin endpoints)
# -------------------------------------------------------------------

def add_user_to_store(data: dict) -> tuple[bool, str]:
    """Add a single user. Returns (success, message)."""
    users = load_users()
    username = data.get("username")
    if not username:
        return False, "Missing 'username' field."
    if username in users:
        return False, f"User '{username}' already exists."

    data.setdefault("sub",      f"u-{username[:6]}001")
    data.setdefault("email",    f"{username}@mockoidc.local")
    data.setdefault("name",     username)
    data.setdefault("password", "password123")
    data.setdefault("groups",   ["engineering"])

    users[username] = data
    save_users(users)
    return True, f"User '{username}' created."


def delete_user_from_store(username: str) -> tuple[bool, str]:
    users = load_users()
    if username not in users:
        return False, f"User '{username}' not found."
    del users[username]
    save_users(users)
    return True, f"User '{username}' deleted."


# -------------------------------------------------------------------
# OIDC Endpoints
# -------------------------------------------------------------------

@app.route(f'{ISSUER_PATH}/keys')
def jwks():
    return jsonify(JWKS_RESPONSE)


@app.route(f'{ISSUER_PATH}/.well-known/openid-configuration')
def discover():
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


@app.route(f'{ISSUER_PATH}/authorize', methods=['GET'])
def authorize():
    """Step 1: Show a login form so the user can choose who to authenticate as."""
    redirect_uri = request.args.get('redirect_uri', '')
    state        = request.args.get('state', '')

    if not redirect_uri:
        return "Error: redirect_uri missing", 400

    users = load_users()
    user_options = "".join(
        f'<option value="{u}">{u} — {data.get("name", "")} ({", ".join(data.get("groups", []))})</option>'
        for u, data in users.items()
    )

    login_form = f"""
<!DOCTYPE html>
<html>
<head>
  <title>Mock OIDC Login</title>
  <style>
    body {{ font-family: sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .card {{ background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); width: 360px; }}
    h2 {{ margin-top: 0; color: #333; }}
    label {{ display: block; margin-bottom: 0.3rem; font-weight: bold; color: #555; font-size: 0.9rem; }}
    input, select {{ width: 100%; padding: 0.5rem; margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 1rem; }}
    button {{ width: 100%; padding: 0.7rem; background: #0070f3; color: white; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #005bb5; }}
    .badge {{ background: #eef; color: #336; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; margin-top: -0.5rem; margin-bottom: 1rem; display: block; }}
    .error {{ color: red; font-size: 0.85rem; margin-bottom: 1rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>🔐 Mock OIDC Login</h2>
    <p style="color:#888;font-size:0.85rem;">Development IdP — select a user to authenticate as</p>
    {"<p class='error'>❌ Invalid username or password.</p>" if request.args.get('error') else ""}
    <form method="POST" action="{ISSUER_PATH}/login">
      <input type="hidden" name="redirect_uri" value="{redirect_uri}">
      <input type="hidden" name="state" value="{state}">

      <label>Username</label>
      <select name="username">{user_options}</select>

      <label>Password</label>
      <input type="password" name="password" placeholder="Enter password">
      <span class="badge">Default password: password123</span>

      <button type="submit">Sign In</button>
    </form>
  </div>
</body>
</html>
"""
    return login_form, 200


@app.route(f'{ISSUER_PATH}/login', methods=['POST'])
def login():
    """Validates credentials and redirects back to Rancher with auth code."""
    redirect_uri = request.form.get('redirect_uri', '')
    state        = request.form.get('state', '')
    username     = request.form.get('username', '')
    password     = request.form.get('password', '')

    user = get_user_by_username(username)

    if not user or user.get('password') != password:
        # Bounce back to login form with error flag
        from urllib.parse import urlencode
        params = urlencode({'redirect_uri': redirect_uri, 'state': state, 'error': '1'})
        return redirect(f"{ISSUER_PATH}/authorize?{params}")

    import secrets
    auth_code = secrets.token_urlsafe(32)
    AUTH_CODE_STORE[auth_code] = username
    print(f"[login] Issued auth code for user: {username}")
    return redirect(f"{redirect_uri}?code={auth_code}&state={state}")


@app.route(f'{ISSUER_PATH}/token', methods=['POST'])
def token():
    """Step 2: Token Endpoint"""
    import secrets

    code               = request.form.get('code', '')
    client_id_received = request.form.get('client_id')
    client_secret      = request.form.get('client_secret')

    print(f"[token] Received code: {code}")
    print(f"[token] Auth code store: {AUTH_CODE_STORE}")

    if client_id_received != CLIENT_ID or client_secret != CLIENT_SECRET:
        return jsonify({"error": "invalid_client", "error_description": "Invalid client credentials"}), 401

    # Look up which user this code belongs to
    username = AUTH_CODE_STORE.pop(code, None)  # one-time use
    if not username:
        return jsonify({"error": "invalid_grant", "error_description": "Auth code not found or already used"}), 401

    user = get_user_by_username(username)
    if not user:
        return jsonify({"error": "server_error", "error_description": f"User '{username}' no longer exists"}), 500

    print(f"[token] Issuing token for user: {username}")

    # Issue a unique access token tied to this user
    access_token = secrets.token_urlsafe(32)
    ACCESS_TOKEN_STORE[access_token] = username

    current_time = int(time.time())
    claims = {
        "sub":    user["sub"],
        "iss":    ISSUER_URL,
        "aud":    client_id_received,
        "exp":    current_time + 3600,
        "iat":    current_time,
        "email":  user.get("email"),
        "name":   user.get("name"),
        "groups": user.get("groups", []),
    }

    signed_id_token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": key_id}
    )

    return jsonify({
        "access_token":  access_token,
        "token_type":    "Bearer",
        "expires_in":    3600,
        "id_token":      signed_id_token,
        "refresh_token": secrets.token_urlsafe(32),
    })


@app.route(f'{ISSUER_PATH}/userinfo')
def userinfo():
    """Step 3: UserInfo Endpoint — looks up user by access token."""
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "invalid_token"}), 401

    token_str = auth_header.split(" ", 1)[1]

    # Look up username from access token store
    username = ACCESS_TOKEN_STORE.get(token_str)
    if username:
        user = get_user_by_username(username)
        if not user:
            return jsonify({"error": "user_not_found"}), 404
        print(f"[userinfo] Returning info for user: {username}")
        return jsonify({k: v for k, v in user.items() if k != "password"})

    # Fallback: try to decode as a JWT (e.g. if access token is a JWT)
    try:
        decoded = jwt.decode(token_str, public_key, algorithms=["RS256"], audience=CLIENT_ID)
        sub  = decoded.get("sub")
        user = get_user_by_sub(sub)
        if not user:
            return jsonify({"error": "user_not_found"}), 404
        return jsonify({k: v for k, v in user.items() if k != "password"})
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "token_expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "invalid_token"}), 401


# -------------------------------------------------------------------
# Admin Endpoints (no auth — dev/test only, do not expose in prod)
# -------------------------------------------------------------------

@app.route('/admin/users', methods=['GET'])
def admin_list_users():
    """List all users (passwords excluded)."""
    users = load_users()
    sanitized = [{k: v for k, v in u.items() if k != "password"} for u in users.values()]
    return jsonify(sanitized)


@app.route('/admin/users', methods=['POST'])
def admin_add_user():
    """
    Add a single user.
    Body (JSON): { "username": "alice", "email": "...", "groups": [...], ... }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    ok, msg = add_user_to_store(data)
    return jsonify({"message": msg}), (201 if ok else 409)


@app.route('/admin/users/bulk', methods=['POST'])
def admin_bulk_add_users():
    """
    Add multiple users at once.
    Body (JSON): [ { "username": "alice", ... }, { "username": "bob", ... } ]
    """
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, list):
        return jsonify({"error": "Expected a JSON array of user objects"}), 400

    results = []
    for entry in data:
        ok, msg = add_user_to_store(entry)
        results.append({"username": entry.get("username"), "ok": ok, "message": msg})

    return jsonify(results), 207  # 207 Multi-Status


@app.route('/admin/users/<username>', methods=['DELETE'])
def admin_delete_user(username):
    """Delete a user by username."""
    ok, msg = delete_user_from_store(username)
    return jsonify({"message": msg}), (200 if ok else 404)


@app.route('/fast-forward-token-expiry')
def fast_forward():
    return "Server time fast-forwarded by 1 day. Tokens are now expired."


# -------------------------------------------------------------------
# Run
# -------------------------------------------------------------------

if __name__ == '__main__':
    users = load_users()
    print("--- Mock OIDC Server Ready ---")
    print(f"Issuer URL:    {ISSUER_URL}")
    print(f"Client ID:     {CLIENT_ID}")
    print(f"Client Secret: {CLIENT_SECRET}")
    print(f"Loaded users:  {list(users.keys())}")
    print()
    print("Admin endpoints (no auth):")
    print(f"  GET    /admin/users")
    print(f"  POST   /admin/users        {{...user...}}")
    print(f"  POST   /admin/users/bulk   [{{...}}, {{...}}]")
    print(f"  DELETE /admin/users/<username>")
    app.run(host='0.0.0.0', port=PORT, debug=False)
