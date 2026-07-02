"""
Canton hackathon config — all coordinates from the Cantor8 sheet.
Fill in CLIENT_ID / CLIENT_SECRET from what the team gives you.
"""

# --- IdP (Keycloak) ---
IDP_BASE_URL = "https://auth.dev.digik.cantor8.tech"
REALM = "master"  # token path uses /realms/master/... per the sheet
CLIENT_ID = "hackathon"                                   # sheet lists realm/client label "hackathon"
CLIENT_SECRET = "0JElLeAZK7fcRF4ngghM2s7XWxPgDYSD"        # from the sheet

# --- Validator Admin API (create internal parties) ---
ADMIN_BASE = "https://api.validator.dev.digik.cantor8.tech/api/validator"

# --- Validator Ledger API ---
LEDGER_JSON_SYNC = "https://api.validator.dev.digik.cantor8.tech/api/ledger"
LEDGER_JSON_WS   = "wss://api.validator.dev.digik.cantor8.tech/api/ledger"
LEDGER_GRPC      = "api.validator.dev.digik.cantor8.tech/api/rpc_ledger"

# Token Standard interface id from the sheet (AutoAccept preapproval proposal)
PREAPPROVAL_INTERFACE = "#splice-wallet:Splice.Wallet.TransferPreapproval:TransferPreapproval"
