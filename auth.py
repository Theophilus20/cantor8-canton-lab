"""
Step 0: Auth. Grab a JWT via client_credentials.
Directly follows the proto snippet on the sheet.
"""
import httpx
from config import IDP_BASE_URL, REALM, CLIENT_ID, CLIENT_SECRET


def get_token() -> dict:
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    url = f"{IDP_BASE_URL}/realms/{REALM}/protocol/openid-connect/token"
    resp = httpx.post(url, data=data, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    return {
        "access_token": body["access_token"],
        "expires_in": int(body.get("expires_in", 600)),
    }


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    tok = get_token()
    print("Got token, expires_in:", tok["expires_in"])
    print("token[:40]:", tok["access_token"][:40], "...")
