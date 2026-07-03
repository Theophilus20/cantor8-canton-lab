"""
Attempt to set up an EXTERNAL party via the validator Admin API topology flow:
  1) POST /v0/admin/external-party/topology/generate  -> party_id + topology_txs
  2) sign each tx hash locally with an ed25519 key
  3) POST /v0/admin/external-party/topology/submit     -> party_id

This is the path the workshop sheet points to
(/v0/admin/external-party/topology/{generate,submit}) and explicitly says NOT
to use setup-proposal. Requires external signing, done here with `cryptography`.

Honest caveats:
- The exact generate request body isn't fully documented; we send a party hint.
  If it 400s, read the body — it names the missing field.
- 'signed_hash' encoding (hex vs base64) is a guess; if submit rejects the
  signature, that's the thing to flip. Either way it's documented feedback.
"""
import binascii
import httpx
from cryptography.hazmat.primitives.asymmetric import ed25519

from auth import get_token, auth_header
from config import ADMIN_BASE

GEN = f"{ADMIN_BASE}/v0/admin/external-party/topology/generate"
SUB = f"{ADMIN_BASE}/v0/admin/external-party/topology/submit"


def _post(url, token, payload):
    r = httpx.post(url, headers={**auth_header(token), "Content-Type": "application/json"},
                   json=payload, timeout=60)
    print(f"POST {url}\n  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:1000])
    r.raise_for_status()
    return r.json()


def main():
    tok = get_token()["access_token"]
    print("== auth ok ==")

    # 1) generate a keypair
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    from cryptography.hazmat.primitives import serialization
    pub_raw = pub.public_bytes(serialization.Encoding.Raw,
                               serialization.PublicFormat.Raw)
    pub_hex = binascii.hexlify(pub_raw).decode()
    print("ed25519 public key (hex):", pub_hex)

    # 2) generate topology txs
    #    ⚠️ VERIFY body: try a party hint + the public key. If it 400s, the
    #    response body will name the correct fields.
    gen_payload = {
        "party_hint": "hackathon-ext",     # ⚠️ VERIFY field name
        "public_key": pub_hex,             # ⚠️ some versions want the key here
    }
    gen = _post(GEN, tok, gen_payload)
    party_id = gen.get("party_id")
    txs = gen.get("topology_txs", [])
    print("generated party_id:", party_id)
    print("num topology txs:", len(txs))

    # 3) sign each tx's hash (hex-encoded) and build signed_topology_txs
    signed = []
    for t in txs:
        tx_b64 = t.get("topology_tx")
        hash_hex = t.get("hash")
        hash_bytes = binascii.unhexlify(hash_hex)
        sig = priv.sign(hash_bytes)                 # ed25519 over the raw hash
        signed.append({
            "topology_tx": tx_b64,                  # echo back unchanged
            "signed_hash": binascii.hexlify(sig).decode(),  # ⚠️ hex vs base64?
        })

    sub_payload = {
        "public_key": pub_hex,
        "signed_topology_txs": signed,
    }
    out = _post(SUB, tok, sub_payload)
    print("SUBMIT result party_id:", out.get("party_id"))
    print("\nSUCCESS: external party set up. Save the key if you want to reuse it.")
    print("private key (hex):",
          binascii.hexlify(priv.private_bytes(
              serialization.Encoding.Raw,
              serialization.PrivateFormat.Raw,
              serialization.NoEncryption())).decode())


if __name__ == "__main__":
    main()
