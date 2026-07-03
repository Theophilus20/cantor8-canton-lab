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


# --- Step 2b: list & accept incoming transfer offers -----------------------
# Because no TransferPreapproval is set up, coins sent to us arrive as a
# legacy Splice.Wallet.TransferOffer that must be explicitly accepted.
# These wallet endpoints are DEPRECATED and require the JWT subject to be our
# own user; with a client_credentials token they may return 401/403 — if so,
# that's a documented limitation (see FEEDBACK.md), not a code bug.
WALLET_BASE = ADMIN_BASE  # same validator base: /api/validator

def accept_offers(token):
    list_url = f"{WALLET_BASE}/v0/wallet/transfer-offers"
    offers = _get(list_url, token)
    items = offers.get("offers", offers) if isinstance(offers, dict) else offers
    print("transfer offers found:", len(items) if hasattr(items, "__len__") else items)
    accepted = 0
    for o in (items or []):
        cid = o.get("contract_id") or o.get("contractId") or o.get("cid")
        if not cid:
            continue
        acc_url = f"{WALLET_BASE}/v0/wallet/transfer-offers/{cid}/accept"
        _post(acc_url, token, {})
        accepted += 1
    print("offers accepted:", accepted)
    return accepted


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
    n = len(out) if isinstance(out, list) else "see body"
    print("Holding-filtered ACS entries:", n)

    # --- Second pass: show ALL active contracts for this party (wildcard) ---
    # If coins arrived as a pending TransferOffer (not a Holding), the filtered
    # query above misses it. This wildcard pass reveals whatever actually landed.
    wildcard = {
        "verbose": True,
        "activeAtOffset": offset,
        "filter": {"filtersByParty": {pid: {"cumulative": [
            {"identifierFilter": {"WildcardFilter": {"value": {
                "includeCreatedEventBlob": False
            }}}}
        ]}}},
    }
    all_out = _post(url, token, wildcard)
    if isinstance(all_out, list):
        print("TOTAL active contracts for party:", len(all_out))
        import re
        from collections import Counter
        blob = json.dumps(all_out)
        tids = re.findall(r'"templateId"\s*:\s*"([^"]+)"', blob)
        for t, c in Counter(tids).items():
            print(f"  {c} x {t}")
        # capture the AmuletTransferInstruction contractId so we can accept it
        for row in all_out:
            rj = json.dumps(row)
            if "AmuletTransferInstruction" in rj:
                m = re.search(r'"contractId"\s*:\s*"([^"]+)"', rj)
                if m:
                    STATE["transfer_instruction_cid"] = m.group(1)
                    print("  -> transfer instruction cid:", m.group(1))
    else:
        print("wildcard ACS: see body")
    return out


# --- Step 5: accept the incoming Token Standard transfer instruction --------
def accept_instruction(token):
    cid = STATE.get("transfer_instruction_cid")
    pid = STATE.get("party_id")
    if not cid:
        print("no transfer instruction to accept.")
        return
    import uuid
    url = f"{LEDGER_JSON_SYNC}/v2/commands/submit-and-wait"
    iface = "#splice-api-token-transfer-instruction-v1:Splice.Api.Token.TransferInstructionV1:TransferInstruction"
    payload = {
        "commands": [{
            "ExerciseCommand": {
                "templateId": iface,          # exercise via the interface
                "contractId": cid,
                "choice": "TransferInstruction_Accept",
                "choiceArgument": {
                    "extraArgs": {
                        "context": {"values": {}},   # may need disclosed contracts
                        "meta": {"values": {}},
                    }
                },
            }
        }],
        "commandId": f"accept-{uuid.uuid4()}",
        "userId": "hackathon",
        "actAs": [pid],
        "readAs": [pid],
    }
    return _post(url, token, payload)


if __name__ == "__main__":
    tok = get_token()["access_token"]
    print("== auth ok ==")
    allocate_party(tok)
    try:
        setup_preapproval(tok)
    except Exception as e:
        print("\n[preapproval skipped — expected until CCs/params available]")
        print("  reason:", str(e)[:200], "\n")
    try:
        accept_offers(tok)   # accept any incoming coin offers (no preapproval set)
    except Exception as e:
        print("\n[accept_offers skipped — wallet endpoint may be deprecated/forbidden]")
        print("  reason:", str(e)[:200], "\n")
    check_acs(tok)
    # Now try to accept the incoming Token Standard transfer instruction:
    try:
        accept_instruction(tok)
    except Exception as e:
        print("\n[accept_instruction failed — may need disclosed registry context]")
        print("  reason:", str(e)[:300], "\n")
    # Re-check ACS to see if a Holding (balance) now exists:
    print("\n=== ACS after accept ===")
    check_acs(tok)
    print("\nSTATE:", json.dumps(STATE, indent=2, default=str))