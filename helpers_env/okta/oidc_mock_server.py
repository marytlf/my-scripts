import time
import json
import base64
import ldap3
import os
import uuid
import hashlib
import re
import zlib
import xml.etree.ElementTree as ET
from xml.dom import minidom
from flask import Flask, request, jsonify, redirect, Response
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs, urlparse
from ldap3 import Server, Connection, ALL, SUBTREE

app = Flask(__name__)

# --- Configuration ---
RANCHER_URL = "PLACEHOLDER"
EXTERNAL_IP = "provider-mock.com.local"
PORT = 44065
BASE_URL = f"https://{EXTERNAL_IP}:{PORT}"

# OIDC Configuration
ISSUER_PATH = "/oidc"
ISSUER_URL = f"{BASE_URL}{ISSUER_PATH}"
CLIENT_ID = "RANCHER_MOCK_CLIENT"
CLIENT_SECRET = "super-secret-12345"

# Okta Mock Configuration
OKTA_ISSUER_PATH = "/okta-mock"
OKTA_ISSUER_URL = f"{BASE_URL}{OKTA_ISSUER_PATH}"
OKTA_CLIENT_ID = "rancher-okta-mock"
OKTA_CLIENT_SECRET = "okta-secret-12345"

# SAML Configuration
# SAML Configuration - Use full URLs
SAML_PATH = "/saml"
SAML_ENTITY_ID = f"{BASE_URL}{SAML_PATH}" # http://<EXTERNAL_IP>:44065/saml
SAML_METADATA_URL = f"{SAML_ENTITY_ID}/metadata"
SAML_SSO_URL = f"{BASE_URL}{SAML_PATH}/sso" # Full URL, not relative!
SAML_SLO_URL = f"{BASE_URL}{SAML_PATH}/slo" # Full URL, not relative!
SAML_ASSERTION_CONSUMER_SERVICE_URL = f"https://{RANCHER_URL}/v3-public/localProviders/local?action=login&providerName=okta"

SAML_CERT = None


# --- Auth Code & Token Stores (in-memory, keyed by token -> username) ---
AUTH_CODE_STORE: dict = {}  # auth_code -> username
ACCESS_TOKEN_STORE: dict = {} # access_token -> username
SAML_AUTHN_REQUEST_STORE: dict = {} # request_id -> username

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

# --- SAML Certificate Generation ---
def generate_self_signed_certificate():
  """Generate a self-signed X.509 certificate for SAML"""
  subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
    x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mock IdP"),
    x509.NameAttribute(NameOID.COMMON_NAME, "mock-idp.local"),
  ])

  cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(public_key)
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.utcnow())
    .not_valid_after(datetime.utcnow() + timedelta(days=365))
    .sign(private_key, hashes.SHA256())
  )
  return cert

def get_saml_certificate():
  """Get or generate the SAML certificate (singleton pattern)"""
  global SAML_CERT
  if SAML_CERT is None:
    SAML_CERT = generate_self_signed_certificate()
  return SAML_CERT


def get_certificate_pem():
  """Get the certificate in PEM format"""
  cert = get_saml_certificate()
  return cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')


def get_certificate_base64():
  """Get the certificate in base64 format (for SAML metadata)"""
  cert = get_saml_certificate()
  return base64.b64encode(
    cert.public_bytes(serialization.Encoding.PEM)
  ).decode('utf-8')


def get_certificate_der():
  """Get the certificate in DER format"""
  cert = get_saml_certificate()
  return cert.public_bytes(serialization.Encoding.DER)


def get_saml_cert():
  """Get the public certificate for SAML signing"""
  return get_certificate_pem()


def get_saml_cert_base64():
  """Get the public certificate in base64 for SAML metadata"""
  return get_certificate_base64()


# Update the get_saml_cert function
def get_saml_cert():
  """Get the public certificate for SAML signing"""
  return get_certificate_pem()


def get_saml_cert_base64():
  """Get the public certificate in base64 for SAML metadata"""
  return get_certificate_base64()

# Update all functions to use this
def get_certificate_pem():
  cert = get_saml_certificate()
  return cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')

def get_certificate_base64():
  cert = get_saml_certificate()
  return base64.b64encode(
    cert.public_bytes(serialization.Encoding.PEM)
  ).decode('utf-8')

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


def search_ldap_users(search_filter="(|(uid={})(cn={})(mail={})") -> list:
  """Search LDAP for users"""
  try:
    server = Server(f"ldap://localhost",389, get_info=ALL)
    conn = Connection(
      server,
      user="cn=admin,dc=mock,dc=com",
      password="testpass",
      auto_bind=True
    )
   
    if conn.bind():
      # Search for all users
      conn.search(
        'dc=mock,dc=com',
        search_filter,
        attributes=['uid', 'cn', 'mail', 'sn', 'givenName', 'memberOf']
      )
     
      users = []
      for entry in conn.entries:
        user = {
          'username': str(entry.uid),
          'name': str(entry.cn),
          'email': str(entry.mail),
          'groups': [str(g) for g in entry.memberOf] if hasattr(entry, 'memberOf') else []
        }
        users.append(user)
     
      conn.unbind()
      return users
    else:
      print(f"[LDAP] Failed to bind: {conn.result}")
      return []
  except Exception as e:
    print(f"[LDAP] Error searching users: {e}")
    return []



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

  data.setdefault("sub",   f"u-{username[:6]}001")
  data.setdefault("email",  f"{username}@mockoidc.local")
  data.setdefault("name",  username)
  data.setdefault("password", "password123")
  data.setdefault("groups", ["engineering"])

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
  state    = request.args.get('state', '')

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
  state    = request.form.get('state', '')
  username  = request.form.get('username', '')
  password  = request.form.get('password', '')

  user = get_user_by_username(username)

  if not user or user.get('password') != password:
    # Bounce back to login form with error flag
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

  code       = request.form.get('code', '')
  client_id_received = request.form.get('client_id')
  client_secret   = request.form.get('client_secret')

  print(f"[token] Received code: {code}")
  print(f"[token] Auth code store: {AUTH_CODE_STORE}")

  if client_id_received != CLIENT_ID or client_secret != CLIENT_SECRET:
    return jsonify({"error": "invalid_client", "error_description": "Invalid client credentials"}), 401

  # Look up which user this code belongs to
  username = AUTH_CODE_STORE.pop(code, None) # one-time use
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
    "sub":  user["sub"],
    "iss":  ISSUER_URL,
    "aud":  client_id_received,
    "exp":  current_time + 3600,
    "iat":  current_time,
    "email": user.get("email"),
    "name": user.get("name"),
    "groups": user.get("groups", []),
  }

  signed_id_token = jwt.encode(
    claims,
    private_key,
    algorithm="RS256",
    headers={"kid": key_id}
  )

  return jsonify({
    "access_token": access_token,
    "token_type":  "Bearer",
    "expires_in":  3600,
    "id_token":   signed_id_token,
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
    sub = decoded.get("sub")
    user = get_user_by_sub(sub)
    if not user:
      return jsonify({"error": "user_not_found"}), 404
    return jsonify({k: v for k, v in user.items() if k != "password"})
  except jwt.ExpiredSignatureError:
    return jsonify({"error": "token_expired"}), 401
  except jwt.InvalidTokenError:
    return jsonify({"error": "invalid_token"}), 401


# -------------------------------------------------------------------
# Okta Mock Endpoints
# -------------------------------------------------------------------

@app.route(f'{OKTA_ISSUER_PATH}/.well-known/openid-configuration')
def okta_discover():
  """Okta-style OIDC discovery endpoint"""
  discovery_doc = {
    "issuer": OKTA_ISSUER_URL,
    "authorization_endpoint": f"{OKTA_ISSUER_URL}/authorize",
    "token_endpoint": f"{OKTA_ISSUER_URL}/token",
    "userinfo_endpoint": f"{OKTA_ISSUER_URL}/userinfo",
    "jwks_uri": f"{OKTA_ISSUER_URL}/keys",
    "response_types_supported": ["code"],
    "scopes_supported": ["openid", "email", "profile", "groups"],
    "acr_values_supported": ["urn:okta:loa:1"],
    "subject_types_supported": ["public"],
    "id_token_signing_alg_values_supported": ["RS256"],
    "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  }
  return jsonify(discovery_doc)

# -------------------------------------------------------------------
# Okta Mock Endpoints
# -------------------------------------------------------------------

@app.route(f'{OKTA_ISSUER_PATH}/keys')
def okta_keys():
  """Okta-style JWKS endpoint"""
  return jsonify(JWKS_RESPONSE)


@app.route(f'{OKTA_ISSUER_PATH}/authorize', methods=['GET'])
def okta_authorize():
  """Okta-style authorization endpoint"""
  redirect_uri = request.args.get('redirect_uri', '')
  state    = request.args.get('state', '')
  client_id  = request.args.get('client_id', '')

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
 <title>Okta Mock Login</title>
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
  <h2>🔐 Okta Mock Login</h2>
  <p style="color:#888;font-size:0.85rem;">Development IdP — select a user to authenticate as</p>
  {"<p class='error'>❌ Invalid username or password.</p>" if request.args.get('error') else ""}
  <form method="POST" action="{OKTA_ISSUER_PATH}/login">
   <input type="hidden" name="redirect_uri" value="{redirect_uri}">
   <input type="hidden" name="state" value="{state}">
   <input type="hidden" name="client_id" value="{client_id}">

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


@app.route(f'{OKTA_ISSUER_PATH}/login', methods=['POST'])
def okta_login():
  """Okta-style login endpoint"""
  redirect_uri = request.form.get('redirect_uri', '')
  state    = request.form.get('state', '')
  client_id  = request.form.get('client_id', '')
  username  = request.form.get('username', '')
  password  = request.form.get('password', '')

  user = get_user_by_username(username)

  if not user or user.get('password') != password:
    params = urlencode({'redirect_uri': redirect_uri, 'state': state, 'error': '1'})
    return redirect(f"{OKTA_ISSUER_PATH}/authorize?{params}")

  import secrets
  auth_code = secrets.token_urlsafe(32)
  AUTH_CODE_STORE[auth_code] = username
  print(f"[okta-login] Issued auth code for user: {username}")
  return redirect(f"{redirect_uri}?code={auth_code}&state={state}")


@app.route(f'{OKTA_ISSUER_PATH}/token', methods=['POST'])
def okta_token():
  """Okta-style token endpoint"""
  import secrets

  code       = request.form.get('code', '')
  client_id_received = request.form.get('client_id')
  client_secret   = request.form.get('client_secret')

  print(f"[okta-token] Received code: {code}")

  if client_id_received != OKTA_CLIENT_ID or client_secret != OKTA_CLIENT_SECRET:
    return jsonify({"error": "invalid_client", "error_description": "Invalid client credentials"}), 401

  username = AUTH_CODE_STORE.pop(code, None)
  if not username:
    return jsonify({"error": "invalid_grant", "error_description": "Auth code not found or already used"}), 401

  user = get_user_by_username(username)
  if not user:
    return jsonify({"error": "server_error", "error_description": f"User '{username}' no longer exists"}), 500

  print(f"[okta-token] Issuing token for user: {username}")

  access_token = secrets.token_urlsafe(32)
  ACCESS_TOKEN_STORE[access_token] = username

  current_time = int(time.time())
  claims = {
    "sub":  user["sub"],
    "iss":  OKTA_ISSUER_URL,
    "aud":  client_id_received,
    "exp":  current_time + 3600,
    "iat":  current_time,
    "email": user.get("email"),
    "name": user.get("name"),
    "groups": user.get("groups", []),
  }

  signed_id_token = jwt.encode(
    claims,
    private_key,
    algorithm="RS256",
    headers={"kid": key_id}
  )

  return jsonify({
    "access_token": access_token,
    "token_type":  "Bearer",
    "expires_in":  3600,
    "id_token":   signed_id_token,
    "refresh_token": secrets.token_urlsafe(32),
  })


@app.route(f'{OKTA_ISSUER_PATH}/userinfo')
def okta_userinfo():
  """Okta-style userinfo endpoint"""
  auth_header = request.headers.get('Authorization', '')

  if not auth_header.startswith("Bearer "):
    return jsonify({"error": "invalid_token"}), 401

  token_str = auth_header.split(" ", 1)[1]

  username = ACCESS_TOKEN_STORE.get(token_str)
  if username:
    user = get_user_by_username(username)
    if not user:
      return jsonify({"error": "user_not_found"}), 404
    print(f"[okta-userinfo] Returning info for user: {username}")
    return jsonify({k: v for k, v in user.items() if k != "password"})

  try:
    decoded = jwt.decode(token_str, public_key, algorithms=["RS256"], audience=OKTA_CLIENT_ID)
    sub = decoded.get("sub")
    user = get_user_by_sub(sub)
    if not user:
      return jsonify({"error": "user_not_found"}), 404
    return jsonify({k: v for k, v in user.items() if k != "password"})
  except jwt.ExpiredSignatureError:
    return jsonify({"error": "token_expired"}), 401
  except jwt.InvalidTokenError:
    return jsonify({"error": "invalid_token"}), 401


# -------------------------------------------------------------------
# SAML Endpoints
# -------------------------------------------------------------------
def generate_saml_response(username, request_id):
    """Generate a SAML Response with correct Recipient and Audience"""
    user = get_user_by_username(username)
    if not user: return ""

    current_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    expiry_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    
    # Ensure Audience matches your Okta Client ID configured in Rancher
    audience = OKTA_CLIENT_ID 

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" 
                ID="_{uuid.uuid4()}" Version="2.0" IssueInstant="{current_time}" 
                Destination="{SAML_ASSERTION_CONSUMER_SERVICE_URL}" InResponseTo="{request_id}">
  <saml:Issuer>{SAML_ENTITY_ID}</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  <saml:Assertion ID="_{uuid.uuid4()}" Version="2.0" IssueInstant="{current_time}">
    <saml:Issuer>{SAML_ENTITY_ID}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{user['email']}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData InResponseTo="{request_id}" NotOnOrAfter="{expiry_time}" Recipient="{SAML_ASSERTION_CONSUMER_SERVICE_URL}"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="{current_time}" NotOnOrAfter="{expiry_time}">
      <saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="{current_time}" SessionIndex="_{uuid.uuid4()}">
      <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef></saml:AuthnContext>
    </saml:AuthnStatement>
    <saml:AttributeStatement>
      <saml:Attribute Name="email"><saml:AttributeValue>{user['email']}</saml:AttributeValue></saml:Attribute>
      <saml:Attribute Name="name"><saml:AttributeValue>{user['name']}</saml:AttributeValue></saml:Attribute>
      <saml:Attribute Name="username"><saml:AttributeValue>{user['username']}</saml:AttributeValue></saml:Attribute>
      <saml:Attribute Name="groups">
        {''.join([f'<saml:AttributeValue>{g}</saml:AttributeValue>' for g in user.get("groups", [])])}
      </saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>"""

def sign_saml_response(response_xml: str) -> str:
  """Sign the SAML Response with RSA"""
  # This is a simplified signing - in production use a proper SAML library
  # For testing, we'll return unsigned XML (Rancher may need to skip cert verification)
  return response_xml

@app.route(f'{SAML_PATH}/metadata')
def saml_metadata():
  """SAML Metadata endpoint"""
  cert_pem = get_certificate_pem()
  cert_base64 = get_certificate_base64()
 
  metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata"
         entityID="{SAML_ENTITY_ID}">
 <IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <KeyDescriptor use="signing">
   <KeyInfo xmlns="http://www.w3.org/2000/09/xmldsig#">
    <X509Data>
     <X509Certificate>{cert_base64}</X509Certificate>
    </X509Data>
   </KeyInfo>
  </KeyDescriptor>
  <SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="{SAML_SSO_URL}"/>
  <SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="{SAML_SLO_URL}"/>
 </IDPSSODescriptor>
</EntityDescriptor>"""
  return Response(metadata, mimetype='application/xml')

# Add this to your Flask script imports
@app.route(f'{SAML_PATH}/sso', methods=['GET', 'POST'])
def saml_sso():
    if request.method == 'GET':
        saml_request = request.args.get('SAMLRequest', '')
        relay_state = request.args.get('RelayState', '')
        
        # FIX: Capture the CSRF cookie Rancher sent to the browser
        csrf_token = request.cookies.get('CSRF', '')
        
        users = load_users()
        user_options = "".join([f'<option value="{u}">{u}</option>' for u in users])

        return f"""
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif; background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh;">
  <div style="background:white; padding:2rem; border-radius:8px; box-shadow:0 2px 12px rgba(0,0,0,0.1); width:350px;">
    <h2>🔐 Mock SAML Login</h2>
    <form method="POST" action="{SAML_SSO_URL}">
      <input type="hidden" name="SAMLRequest" value="{saml_request}">
      <input type="hidden" name="RelayState" value="{relay_state}">
      <input type="hidden" name="csrf_token" value="{csrf_token}">
      <label>Select User:</label>
      <select name="username" style="width:100%; padding:0.5rem; margin:1rem 0;">{user_options}</select>
      <label>Password:</label>
      <input type="password" name="password" value="password123" style="width:100%; padding:0.5rem; margin-bottom:1rem;">
      <button type="submit" style="width:100%; padding:0.7rem; background:#0070f3; color:white; border:none; border-radius:4px; cursor:pointer;">Sign In</button>
    </form>
  </div>
</body>
</html>
"""

    elif request.method == 'POST':
        saml_request = request.form.get('SAMLRequest', '')
        relay_state = request.form.get('RelayState', '')
        csrf_token = request.form.get('csrf_token', '') # This is the echoed cookie
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        user = load_users().get(username)
        if user and user.get('password') == password:
            # Extract RequestID from the original SAMLRequest to satisfy 'InResponseTo'
            request_id = "MOCK_ID"
            if saml_request:
                try:
                    decoded = base64.b64decode(saml_request)
                    try: xml_str = zlib.decompress(decoded, -zlib.MAX_WBITS).decode('utf-8')
                    except: xml_str = decoded.decode('utf-8', errors='ignore')
                    match = re.search(r'ID="([^"]+)"', xml_str)
                    if match: request_id = match.group(1)
                except: pass

            saml_xml = generate_saml_response(username, request_id)
            saml_response_b64 = base64.b64encode(saml_xml.encode('utf-8')).decode('utf-8')

            # FINAL SUBMISSION: Must include 'csrf' field for Rancher
        return f"""
<!DOCTYPE html>
<html>
<head><title>Finalizing Login</title></head>
<body style="font-family:sans-serif; text-align:center; padding-top:50px;">
    <div style="display:inline-block; padding:2rem; border:1px solid #ccc; border-radius:8px;">
        <h3>Final Step: Connect to Rancher</h3>
        <p>Browsers block automatic security tokens across different ports (44065 -> 443).</p>
        
        <form id="saml_form" method="post" action="{SAML_ASSERTION_CONSUMER_SERVICE_URL}">
            <input type="hidden" name="SAMLResponse" value="{saml_response_b64}">
            <input type="hidden" name="RelayState" value="{relay_state}">
            <input type="hidden" name="csrf" value="{csrf_token}">
            
            <button type="submit" style="padding:1rem 2rem; background:#0070f3; color:white; border:none; border-radius:4px; cursor:pointer; font-size:1.1rem;">
                Click here to finish Login
            </button>
        </form>
    </div>
</body>
</html>
"""
        return "Unauthorized", 401

@app.route(f'{SAML_PATH}/slo', methods=['GET', 'POST'])
def saml_slo():
  """SAML Single Logout endpoint"""
  return Response("SAML SLO endpoint - Not implemented in mock", mimetype='text/plain')


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

  return jsonify(results), 207 # 207 Multi-Status


@app.route('/admin/users/<username>', methods=['DELETE'])
def admin_delete_user(username):
  """Delete a user by username."""
  ok, msg = delete_user_from_store(username)
  return jsonify({"message": msg}), (200 if ok else 404)

@app.route('/admin/saml-keys', methods=['GET'])
def admin_get_saml_keys():
  """
  Get the private key and public certificate used for SAML signing.
  WARNING: This is for development/testing only. Do not expose in production!
  """
  cert = get_saml_certificate() # Use singleton
 
  # Get private key in PEM format
  private_key_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
  ).decode('utf-8')

  # Get public certificate in PEM format
  public_cert_pem = cert.public_bytes(
    serialization.Encoding.PEM
  ).decode('utf-8')

  # Get public certificate in base64 (for SAML metadata)
  public_cert_base64 = base64.b64encode(
    cert.public_bytes(serialization.Encoding.PEM)
  ).decode('utf-8')

  # Get certificate serial number
  cert_serial = cert.serial_number

  return jsonify({
    "private_key_pem": private_key_pem,
    "public_cert_pem": public_cert_pem,
    "public_cert_base64": public_cert_base64,
    "certificate_serial": str(cert_serial),
    "certificate_valid_from": cert.not_valid_before.isoformat(),
    "certificate_valid_until": cert.not_valid_after.isoformat(),
    "key_id": key_id,
    "algorithm": "RS256",
    "warning": "⚠️ WARNING: This is a development server. Do not expose this endpoint in production!"
  })
@app.route('/fast-forward-token-expiry')
def fast_forward():
  return "Server time fast-forwarded by 1 day. Tokens are now expired."


# -------------------------------------------------------------------
# Run
# -------------------------------------------------------------------

if __name__ == '__main__':
  users = load_users()
  print("--- Mock OIDC/Okta/SAML Server Ready ---")
  print(f"Base URL:  {BASE_URL}")
  print()
  print("OIDC Endpoints:")
  print(f" GET  {ISSUER_URL}/.well-known/openid-configuration")
  print(f" GET  {ISSUER_URL}/keys")
  print(f" GET  {ISSUER_URL}/authorize")
  print(f" POST {ISSUER_URL}/login")
  print(f" POST {ISSUER_URL}/token")
  print(f" GET  {ISSUER_URL}/userinfo")
  print()
  print("Okta Mock Endpoints:")
  print(f" GET  {OKTA_ISSUER_URL}/.well-known/openid-configuration")
  print(f" GET  {OKTA_ISSUER_URL}/keys")
  print(f" GET  {OKTA_ISSUER_URL}/authorize")
  print(f" POST {OKTA_ISSUER_URL}/login")
  print(f" POST {OKTA_ISSUER_URL}/token")
  print(f" GET  {OKTA_ISSUER_URL}/userinfo")
  print()
  print("SAML Endpoints:")
  print(f" GET  {SAML_PATH}/metadata")
  print(f" GET/POST {SAML_PATH}/sso")
  print(f" GET/POST {SAML_PATH}/slo")
  print()
  print("Admin Endpoints (no auth):")
  print(f" GET  /admin/users")
  print(f" POST /admin/users    {{...user...}}")
  print(f" POST /admin/users/bulk [{{...}}, {{...}}]")
  print(f" DELETE /admin/users/<username>")
  print()
  print(f"Loaded users: {list(users.keys())}")
  print(f"Client ID:  {CLIENT_ID}")
  print(f"Client Secret: {CLIENT_SECRET}")
  print()
  print("⚠️ WARNING: This is a development server. Do not expose to production!")
  print()
  app.run(host='0.0.0.0', port=PORT, debug=True, ssl_context='adhoc')

