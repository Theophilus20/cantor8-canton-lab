"""
Canton low-level flow. Run steps in order.

⚠️  IMPORTANT: request bodies marked `# ⚠️ VERIFY` are best-guesses from
the sheet + Canton docs. The Ledger API docs are ~2 weeks old, so shapes
may differ. When one 400s/422s, inspect resp.text, fix, and LOG THE FIX in
FEEDBACK.md — that log is literally what Cantor8 asked for.
"""
import json
import httpx
from auth import get_token, auth_header
from config import ADMIN_BASE, LEDGER_JSON_SYNC, PREAPPROVAL_INTERFACE

STATE = {}  # holds party_id etc across steps


def _post(url, token, payload):
    r = httpx.post(url, headers={**auth_header(token), "Content-Type": "application/json"},
                   json=payload, timeout=60)
    print(f"POST {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:800])   # <-- read this to fix the shape
    r.raise_for_status()
    return r.json()


def _get(url, token, params=None):
    r = httpx.get(url, headers=auth_header(token), params=params, timeout=60)
    print(f"GET {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:800])
    r.raise_for_status()
    return r.json()


# --- Step 1: allocate an internal party ------------------------------------
def allocate_party(token, hint="hackathon-party"):
    # ⚠️ VERIFY: Admin API path + body. Sheet says use the Admin API to create
    # an INTERNAL party. Common Splice validator path is /v0/admin/users or a
    # party-allocation endpoint. The sheet's external-party topology endpoints
    # (/v0/admin/external-party/topology/{generate,submit}) are for EXTERNAL
    # parties — and it explicitly says DO NOT use setup-proposal.
    url = f"{ADMIN_BASE}/v0/admin/users"   # correct endpoint (allocates user + party)
    payload = {"name": hint}                # onboards a user, creating a DAML party
    out = _post(url, token, payload)
    STATE["party_id"] = out.get("partyId") or out.get("party_id") or out
    print("PARTY_ID:", STATE["party_id"])
    return out


# --- Step 2: set up PreApproval contract -----------------------------------
def setup_preapproval(token):
    # ⚠️ VERIFY: this is a Ledger API command submission (create/exercise).
    # JSON Ledger API create typically looks like below. The template/interface
    # is the TransferPreapproval from the sheet.
    import uuid
    pid = STATE.get("party_id")
    url = f"{LEDGER_JSON_SYNC}/v2/commands/submit-and-wait"
    # NOTE: TransferPreapproval needs provider/receiver/instrumentAdmin (DSO)
    # party refs + ~0.25 USD of CC. Until CCs arrive from the team and those
    # refs are known, this create may fail with a missing-field/insufficient
    # -funds error — that's expected. See FEEDBACK.md.
    payload = {
        "commands": [{
            "CreateCommand": {
                "templateId": PREAPPROVAL_INTERFACE,
                "createArguments": {
                    # ⚠️ fill from token metadata / registry info once you have CCs:
                    "receiver": pid,
                    # "provider": <validator operator party>,
                    # "instrumentAdmin": <DSO/registry admin party>,
                }
            }
        }],
        "commandId": f"preapproval-{uuid.uuid4()}",
        "userId": "hackathon",          # matches your Ledger API user
        "actAs": [pid],
        "readAs": [pid],
    }
    return _post(url, token, payload)


# --- Step 3/4: check ACS, filter over Holding interface --------------------
def check_acs(token):
    # ⚠️ VERIFY: ACS query on JSON Ledger API. Often an active-contracts
    # endpoint that takes a filter by interface/template id.
    pid = STATE.get("party_id")
    # ACS query needs an activeAtOffset — get current ledger end first.
    end = _get(f"{LEDGER_JSON_SYNC}/v2/state/ledger-end", token)
    offset = end.get("offset") if isinstance(end, dict) else end
    print("ledger-end offset:", offset)

    url = f"{LEDGER_JSON_SYNC}/v2/state/active-contracts"
    holding_iface = "#splice-api-token-holding-v1:Splice.Api.Token.HoldingV1:Holding"
    payload = {
        "verbose": True,
        "activeAtOffset": offset,
        "filter": {"filtersByParty": {pid: {"cumulative": [
            {"identifierFilter": {"InterfaceFilter": {"value": {
                "includeInterfaceView": True,
                "includeCreatedEventBlob": False,
                "interfaceId": holding_iface,
            }}}}
        ]}}},
    }
    out = _post(url, token, payload)
    print("ACS entries:", len(out) if isinstance(out, list) else "see body")
    return out


if __name__ == "__main__":
    tok = get_token()["access_token"]
    print("== auth ok ==")
    allocate_party(tok)
    try:
        setup_preapproval(tok)
    except Exception as e:
        print("\n[preapproval skipped — expected until CCs/params available]")
        print("  reason:", str(e)[:200], "\n")
    check_acs(tok)
    print("\nSTATE:", json.dumps(STATE, indent=2, default=str))