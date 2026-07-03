"""
Set up a TransferPreapproval for the EXTERNAL party via the Ledger API's
interactive-submission (prepare -> sign -> execute), following the workshop
sheet (NOT setup-proposal).

Reads the external party's ed25519 private key (hex) from KEY.txt.
Uses the party id below (the hackathon-ext party you created).

Steps:
  1) GET  /v2/state/connected-synchronizers   -> synchronizerId
  2) fetch registry context (DSO admin id) from scan-proxy
  3) POST /v2/interactive-submission/prepare   -> preparedTransaction + hash
  4) sign hash with ed25519 key
  5) POST /v2/interactive-submission/execute   -> submit signed tx

Every response body is printed so any missing field / wrong shape is visible.
"""
import binascii
import json
import uuid
import httpx
from cryptography.hazmat.primitives.asymmetric import ed25519

from auth import get_token, auth_header
from config import LEDGER_JSON_SYNC, ADMIN_BASE

# The external party you set up (holds the key in KEY.txt):
EXT_PARTY = "hackathon-ext::1220b3f4d0e65ae8789026efcfad78a0736d37fe0e0a0e7d7060fb366012c2794f14"

PREAPPROVAL_PROPOSAL = "#splice-wallet:Splice.Wallet.TransferPreapproval:TransferPreapprovalProposal"


def load_key():
    with open("KEY.txt") as f:
        hexkey = f.read().strip()
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(binascii.unhexlify(hexkey))
    from cryptography.hazmat.primitives import serialization
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, binascii.hexlify(pub).decode()


def _get(url, token):
    r = httpx.get(url, headers=auth_header(token), timeout=60)
    print(f"GET {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:800])
    r.raise_for_status()
    return r.json()


def _post(url, token, payload):
    r = httpx.post(url, headers={**auth_header(token), "Content-Type": "application/json"},
                   json=payload, timeout=60)
    print(f"POST {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:1200])
    r.raise_for_status()
    return r.json()


def main():
    tok = get_token()["access_token"]
    print("== auth ok ==")
    priv, pub_hex = load_key()
    print("loaded key; public:", pub_hex)

    # 1) synchronizer id
    sync = _get(f"{LEDGER_JSON_SYNC}/v2/state/connected-synchronizers", tok)
    syncs = sync.get("connectedSynchronizers", [])
    synchronizer_id = syncs[0]["synchronizerId"] if syncs else None
    print("synchronizerId:", synchronizer_id)

    # 2) DSO / registry admin id (needed as provider/instrumentAdmin context)
    #    scan-proxy on the validator exposes the DSO party id:
    try:
        dso = _get(f"{ADMIN_BASE}/v0/scan-proxy/dso-party-id", tok)
        dso_party = dso.get("dso_party_id") or dso.get("dsoPartyId")
        print("DSO party:", dso_party)
    except Exception as e:
        dso_party = None
        print("  (could not fetch DSO party:", str(e)[:150], ")")

    # 3) prepare the create of TransferPreapprovalProposal
    #    ⚠️ createArguments fields per the DAML template; adjust from error body.
    prepare_payload = {
        "userId": "hackathon",
        "commandId": f"preapproval-{uuid.uuid4()}",
        "actAs": [EXT_PARTY],
        "readAs": [],
        "synchronizerId": synchronizer_id,
        "verboseHashing": False,
        "packageIdSelectionPreference": [],
        "commands": [{
            "CreateCommand": {
                "templateId": PREAPPROVAL_PROPOSAL,
                "createArguments": {
                    "receiver": EXT_PARTY,
                    "provider": dso_party,     # ⚠️ may need validator operator party instead
                    # possibly "expiresAt", "dso", etc. — see error body
                },
            }
        }],
    }
    prep = _post(f"{LEDGER_JSON_SYNC}/v2/interactive-submission/prepare", tok, prepare_payload)
    prepared_tx = prep.get("preparedTransaction")
    tx_hash_b64 = prep.get("preparedTransactionHash")
    print("got prepared tx; hash present:", bool(tx_hash_b64))

    # 4) sign the hash (base64-decoded) with ed25519
    import base64
    hash_bytes = base64.b64decode(tx_hash_b64)
    sig = priv.sign(hash_bytes)
    sig_b64 = base64.b64encode(sig).decode()

    # 5) execute
    execute_payload = {
        "preparedTransaction": prepared_tx,
        "hashingSchemeVersion": "HASHING_SCHEME_VERSION_V2",
        "userId": "hackathon",
        "submissionId": str(uuid.uuid4()),
        "deduplicationPeriod": {"Empty": {}},
        "partySignatures": {
            "signatures": [{
                "party": EXT_PARTY,
                "signatures": [{
                    "format": "SIGNATURE_FORMAT_CONCAT",
                    "signature": sig_b64,
                    "signedBy": pub_hex,
                    "signingAlgorithmSpec": "SIGNING_ALGORITHM_SPEC_ED25519",
                }],
            }],
        },
    }
    out = _post(f"{LEDGER_JSON_SYNC}/v2/interactive-submission/execute", tok, execute_payload)
    print("\nEXECUTE result:", json.dumps(out, indent=2)[:500])
    print("\nIf 200: TransferPreapprovalProposal created. It still needs the")
    print("provider (validator operator) to accept it before it becomes a")
    print("TransferPreapproval — but the hard signed-submission worked.")


if __name__ == "__main__":
    main()
