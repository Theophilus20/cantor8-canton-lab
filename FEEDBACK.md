# Docs Feedback Cantor8 "Touching the Ledger" Lab

Confirmed by running the full flow against the DevNet validator.

## What worked
- Auth via Keycloak client_credentials — worked exactly as the sheet's snippet showed.
- ACS query filtering over the Holding interface returned cleanly (0 balance, as expected pre-funding).
- Getting ledger-end offset then passing it as `activeAtOffset` to active-contracts works.

## Issues found (step → docs said → reality → fix)

### 1. Party allocation path was not given
- The sheet says "use the validator's Admin API" but gives no exact path.
- `/v0/admin/party` → **404 Not Found**.
- Working endpoint: **`POST /v0/admin/users`** with body `{"name": "<hint>"}`.
  This onboards a user AND allocates the DAML party.
- Suggestion: state the exact endpoint + body in the sheet.

### 2. submit-and-wait required fields not documented
- Initial body `{commands, actAs}` → **400: Missing required field at 'commandId'**.
- Required fields: `commandId`, `userId`, `actAs`, `readAs` (in addition to `commands`).
- Suggestion: give a minimal working JSON body in the sheet.

### 3. TransferPreapproval template not resolvable  ← biggest blocker
- Using the interface id from the sheet
  (`#splice-wallet:Splice.Wallet.TransferPreapproval:TransferPreapproval`) in a
  CreateCommand → **404 TEMPLATES_OR_INTERFACES_NOT_FOUND**:
  "Templates do not exist:
  f799a58f...:Splice.Wallet.TransferPreapproval:TransferPreapproval".
- The `#splice-wallet` alias resolved to a package-id that isn't vetted/known on
  this participant, OR TransferPreapproval must be created via a different flow
  (the Admin API setup-proposal, which the sheet explicitly forbids).
- Also: the create needs provider / instrumentAdmin (DSO) party refs and ~0.25
  USD of CC — but "get CCs from the team" is a *later* step in the sheet, so the
  ordering makes the preapproval step impossible to complete when first reached.
- Suggestion: clarify (a) the correct package-qualified template id, (b) the
  required createArguments, and (c) reorder so funding happens before preapproval.

## ACS / balance
- Once funded, re-running check_acs against the same Holding interface filter is
  the correct way to see balance composed of Holding contracts. Verified the
  query shape returns 200 with an empty set at 0 balance.

## Old vs new vs GRPC
- The sheet links both a new (~2wk) JSON Ledger API reference and a deprecated
  Digital Asset one. The v2 JSON endpoints (/v2/state/ledger-end,
  /v2/state/active-contracts, /v2/commands/submit-and-wait) are the current ones.

## Party ID allocated during this run
hackathon-party::12204e94c0e449c0efcd270dd1e68259c36471cebef132e5c7dfc2750fe8c9eed77f