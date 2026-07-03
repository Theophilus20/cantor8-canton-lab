"""
Set up a TransferPreapproval on the INTERNAL party (the one the validator hosts,
which the operator token can actAs). Uses the correct *Proposal* template and a
plain submit-and-wait (no external signing needed for a hosted party).

Key differences from earlier failed attempts:
  - template is TransferPreapprovalProposal (NOT TransferPreapproval)
  - actAs the INTERNAL party (hosted by validator) -> operator token can act
  - plain /v2/commands/submit-and-wait (no interactive-submission/signing)
"""
import json
import uuid
import httpx
from auth import get_token, auth_header
from config import LEDGER_JSON_SYNC, ADMIN_BASE

INTERNAL_PARTY = "hackathon-party::12204e94c0e449c0efcd270dd1e68259c36471cebef132e5c7dfc2750fe8c9eed77f"

# Try both alias forms; some participants want the Proposal template.
TEMPLATE = "#splice-wallet:Splice.Wallet.TransferPreapproval:TransferPreapprovalProposal"


def _get(url, token):
    r = httpx.get(url, headers=auth_header(token), timeout=60)
    print(f"GET {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:600])
    r.raise_for_status()
    return r.json()


def _post(url, token, payload):
    r = httpx.post(url, headers={**auth_header(token), "Content-Type": "application/json"},
                   json=payload, timeout=60)
    print(f"POST {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:1500])
    r.raise_for_status()
    return r.json()


def main():
    tok = get_token()["access_token"]
    print("== auth ok ==")

    # DSO party (often needed as the 'dso' arg on the proposal)
    dso_party = None
    try:
        dso = _get(f"{ADMIN_BASE}/v0/scan-proxy/dso-party-id", tok)
        dso_party = dso.get("dso_party_id") or dso.get("dsoPartyId")
        print("DSO party:", dso_party)
    except Exception as e:
        print("  (no DSO party:", str(e)[:120], ")")

    # validator operator party (the provider on the preapproval)
    provider = None
    try:
        vu = _get(f"{ADMIN_BASE}/v0/validator-user", tok)
        provider = vu.get("party_id") or vu.get("partyId")
        print("validator operator party:", provider)
    except Exception as e:
        print("  (no validator-user:", str(e)[:120], ")")

    url = f"{LEDGER_JSON_SYNC}/v2/commands/submit-and-wait"
    # Try a few argument shapes; adjust from the error body which names fields.
    create_args = {
        "receiver": INTERNAL_PARTY,
        "provider": provider,   # validator operator party
    }
    payload = {
        "commands": [{
            "CreateCommand": {
                "templateId": TEMPLATE,
                "createArguments": create_args,
            }
        }],
        "commandId": f"preapproval-{uuid.uuid4()}",
        "userId": "hackathon",
        "actAs": [provider],          # act as the OPERATOR (token can do this)
        "readAs": [INTERNAL_PARTY, provider],
    }
    print("\nsubmitting with args:", json.dumps(create_args))
    out = _post(url, tok, payload)
    print("\nRESULT:", json.dumps(out, indent=2)[:800])
    print("\nIf 200: TransferPreapprovalProposal created on the internal party.")


if __name__ == "__main__":
    main()