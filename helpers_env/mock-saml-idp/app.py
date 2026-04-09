from flask import Flask, request
import json
import base64
from saml2 import BINDING_HTTP_REDIRECT
from saml2.config import IdPConfig
from saml2.server import Server
from saml2.metadata import entity_descriptor
from saml2.saml import NameID

app = Flask(__name__)

# Load users
with open("users.json") as f:
    USERS = {u["username"]: u for u in json.load(f)["users"]}

BASE = "https://PLACEHOLDER_URL:5000"

def build_config():
    return {
        "entityid": f"{BASE}/metadata",
        "xmlsec_binary": "/usr/bin/xmlsec1",

        "service": {
            "idp": {
                "name": "Mock Rancher IdP",
                "endpoints": {
                    "single_sign_on_service": [
                        (f"{BASE}/sso", BINDING_HTTP_REDIRECT),
                    ],
                },
                "name_id_format": [
                    "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
                ],
                # 🔴 REQUIRED for Rancher
                "sign_response": True,
                "sign_assertion": True,
            }
        },

        "key_file": "certs/idp.key",
        "cert_file": "certs/idp.crt",

        "metadata": {
            "local": ["/app/metadata/rancher_metadata.xml"]
        },

        "accepted_time_diff": 60,
    }

idp_config = IdPConfig().load(build_config())
idp_server = Server(config=idp_config)

@app.route("/metadata")
def metadata():
    ed = entity_descriptor(idp_server.config)
    return str(ed.to_string()), 200, {"Content-Type": "text/xml"}


@app.route("/sso", methods=["GET", "POST"])
def sso():
    saml_request = request.values.get("SAMLRequest")
    relay_state = request.values.get("RelayState")

    if request.method == "GET" and "user" not in request.args:
        options = "".join(f'<option value="{u}">{u}</option>' for u in USERS)
        return f"""
        <form method="post">
            <input type="hidden" name="SAMLRequest" value="{saml_request}" />
            <input type="hidden" name="RelayState" value="{relay_state}" />
            <select name="user">{options}</select>
            <button type="submit">Login</button>
        </form>
        """

    username = request.form.get("user")
    user = USERS.get(username)
    if not user:
        return "User not found", 404

    req_info = idp_server.parse_authn_request(
        saml_request,
        BINDING_HTTP_REDIRECT
    )

    req = req_info.message

    acs_url = req.assertion_consumer_service_url
    request_id = req.id
    sp_entity_id = req.issuer.text

    identity = {
        "username": user["username"],
        "email": user["email"],
        "displayName": user["username"],
        "groups": user["groups"],
    }

    name_id = NameID(
        text=user["username"],
        #format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
        format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    )

    response = idp_server.create_authn_response(
        identity=identity,
        in_response_to=request_id,
        destination=acs_url,
        sp_entity_id=sp_entity_id,
        name_id=name_id,
        authn={"class_ref": "urn:oasis:names:tc:SAML:2.0:ac:classes:Password"},
    )

    saml_response = base64.b64encode(
        str(response).encode("utf-8")
    ).decode("utf-8")

    return f"""
    <html>
    <body onload="document.forms[0].submit()">
        <form method="post" action="{acs_url}">
            <input type="hidden" name="SAMLResponse" value="{saml_response}" />
            <input type="hidden" name="RelayState" value="{relay_state}" />
        </form>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        ssl_context=("certs/idp.crt", "certs/idp.key"),
        debug=True
    )
