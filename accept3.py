"""
FINAL accept: the userId fix got us past authZ. The remaining piece is the
choice context ('external-party-config-state' etc.) which the registry serves
via the Token Standard transfer-instruction API:
  POST .../registry/transfer-instruction/v1/{cid}/choice-contexts/accept
The response provides context data + disclosed contracts to include.
"""
import json
import re
import uuid
import httpx
from auth import get_token, auth_header
from config import LEDGER_JSON_SYNC, ADMIN_BASE

INTERNAL_PARTY = "hackathon-party::12204e94c0e449c0efcd270dd1e68259c36471cebef132e5c7dfc2750fe8c9eed77f"
TI_IFACE = "#splice-api-token-transfer-instruction-v1:Splice.Api.Token.TransferInstructionV1:TransferInstruction"
USER_ID = "validator-backend@clients"


def _get(url, token):
    r = httpx.get(url, headers=auth_header(token), timeout=60)
    if r.status_code >= 400:
        print(f"GET {url} -> {r.status_code}")
    r.raise_for_status()
    return r.json()


def _post_raw(url, token, payload, label=""):
    r = httpx.post(url, headers={**auth_header(token), "Content-Type": "application/json"},
                   json=payload, timeout=60)
    print(f"POST {label or url} -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:1200])
    return r


def find_instruction_cid(token):
    end = _get(f"{LEDGER_JSON_SYNC}/v2/state/ledger-end", token)
    payload = {
        "verbose": True,
        "activeAtOffset": end.get("offset"),
        "filter": {"filtersByParty": {INTERNAL_PARTY: {"cumulative": [
            {"identifierFilter": {"WildcardFilter": {"value": {"includeCreatedEventBlob": False}}}}
        ]}}},
    }
    r = _post_raw(f"{LEDGER_JSON_SYNC}/v2/state/active-contracts", token, payload, "ACS")
    r.raise_for_status()
    for row in r.json():
        rj = json.dumps(row)
        if "AmuletTransferInstruction" in rj:
            m = re.search(r'"contractId"\s*:\s*"([^"]+)"', rj)
            if m:
                return m.group(1)
    return None


def fetch_accept_context(token, cid):
    """Try candidate registry endpoints for the accept choice context."""
    candidates = [
        f"{ADMIN_BASE}/v0/scan-proxy/registry/transfer-instruction/v1/{cid}/choice-contexts/accept",
        f"{ADMIN_BASE}/v0/scan-proxy/transfer-instruction/v1/{cid}/choice-contexts/accept",
        f"https://scan.dev.digik.cantor8.tech/registry/transfer-instruction/v1/{cid}/choice-contexts/accept",
        f"https://scan.dev.digik.cantor8.tech/api/scan/registry/transfer-instruction/v1/{cid}/choice-contexts/accept",
    ]
    for url in candidates:
        try:
            r = _post_raw(url, token, {}, f"context: {url.split('cantor8.tech')[-1][:60]}")
            if r.status_code < 400:
                return r.json()
        except Exception as e:
            print("  (unreachable:", str(e)[:80], ")")
    return None


def norm_disclosed(dc):
    """Map registry disclosed-contract fields to Ledger API v2 names."""
    return {
        "templateId": dc.get("templateId") or dc.get("template_id"),
        "contractId": dc.get("contractId") or dc.get("contract_id"),
        "createdEventBlob": dc.get("createdEventBlob") or dc.get("created_event_blob"),
        "synchronizerId": dc.get("synchronizerId") or dc.get("synchronizer_id")
                          or dc.get("domainId") or dc.get("domain_id") or "",
    }


def main():
    tok = get_token()["access_token"]
    print("== auth ok ==")
    cid = find_instruction_cid(tok)
    if not cid:
        print("No pending instruction found.")
        return
    print("instruction cid:", cid[:40], "...")

    ctx = fetch_accept_context(tok, cid)
    if not ctx:
        print("\nCould not fetch choice context from any candidate URL.")
        print("Paste this output back — we may need the correct scan/registry URL.")
        return
    print("\ncontext response keys:", list(ctx.keys()))
    cc = ctx.get("choiceContext") or ctx.get("choice_context") or ctx
    context_data = cc.get("choiceContextData") or cc.get("choice_context_data") or {}
    disclosed = cc.get("disclosedContracts") or cc.get("disclosed_contracts") or []
    print("context data keys:", list(context_data.keys()) if isinstance(context_data, dict) else type(context_data))
    print("disclosed contracts:", len(disclosed))

    payload = {
        "commands": [{
            "ExerciseCommand": {
                "templateId": TI_IFACE,
                "contractId": cid,
                "choice": "TransferInstruction_Accept",
                "choiceArgument": {
                    "extraArgs": {
                        "context": context_data,
                        "meta": {"values": {}},
                    }
                },
            }
        }],
        "commandId": f"accept-{uuid.uuid4()}",
        "userId": USER_ID,
        "actAs": [INTERNAL_PARTY],
        "readAs": [INTERNAL_PARTY],
        "disclosedContracts": [norm_disclosed(d) for d in disclosed],
    }
    r = _post_raw(f"{LEDGER_JSON_SYNC}/v2/commands/submit-and-wait", tok, payload, "ACCEPT with context")
    if r.status_code < 400:
        print("\n\n*** COINS ACCEPTED! ***")
        print(json.dumps(r.json(), indent=2)[:800])
        print("\nRun `python flow.py` to see your Holding balance.")
    else:
        print("\nAccept failed — paste this output back; the error names the next fix.")


if __name__ == "__main__":
    main()
