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

## 4. Token identity vs. allocated party (root cause of the blocked steps)
Running the flow revealed that the hackathon client_credentials token
authenticates as the validator operator user **`validator-backend@clients`**,
not as the newly allocated party's user. Consequences observed:
- Wallet endpoint `GET /v0/wallet/transfer-offers` → 404
  "No wallet found for user 'validator-backend@clients' for operation
  'listTransferOffers'".
- The Ledger `submit-and-wait` create for TransferPreapproval acts as the
  allocated party but the template isn't vetted on the participant
  (TEMPLATES_OR_INTERFACES_NOT_FOUND), so the preapproval can't be created
  this way either.
This means: with the provided token you can allocate parties and read the
ledger/ACS, but you cannot perform wallet actions (accept offers, set up a
preapproval) *as* the allocated party. Suggest the workshop either (a) issue
per-party user tokens, or (b) document that coins must be sent via a path that
doesn't require the receiver to hold a preapproval/wallet, or (c) clarify the
correct package-qualified TransferPreapproval template id so the Ledger-API
create path works.

## 5. Coins arrive as a Token Standard AmuletTransferInstruction, and accept is blocked by token scope
When the team sent CC, it did NOT arrive as a Holding or a legacy
Splice.Wallet.TransferOffer. A wildcard ACS query showed it as:
  Splice.AmuletTransferInstruction:AmuletTransferInstruction
i.e. a Token Standard transfer instruction pending receiver acceptance.

To claim it, the receiver must exercise `TransferInstruction_Accept` on the
`#splice-api-token-transfer-instruction-v1:...:TransferInstruction` interface.
Attempting this via the Ledger API with the hackathon token returned:
  403 "A security-sensitive error has been received" (masked auth error).

Root cause: the token acts as `validator-backend@clients` (validator operator),
but TransferInstruction_Accept must be exercised by the *receiver party's* user,
and also requires disclosed registry context (amulet-rules) in extraArgs.context.
With the single operator-scoped client_credentials token provided, the receiver
cannot accept the transfer — so the "get CCs and use them" portion of the
workshop cannot be completed as written.

Suggestions:
- Document that sent CC arrives as an AmuletTransferInstruction needing
  TransferInstruction_Accept (not a wallet TransferOffer).
- Provide either per-party user tokens (so the receiver can actAs its party) or
  a preapproval set up on the receiver in advance so sends auto-settle.
- Document the required extraArgs.context disclosed contracts (amulet-rules etc.)
  and how to fetch them from the registry/scan-proxy.

## Summary of what completed successfully
- Auth (client_credentials -> JWT): OK
- Party allocation (/v0/admin/users): OK
- Ledger-end + ACS (Holding filter and wildcard): OK
- Located incoming CC as AmuletTransferInstruction, extracted its contractId: OK
- Attempted TransferInstruction_Accept (blocked by token scope, documented): OK

## 6. DEFINITIVE ROOT CAUSE: shared operator token cannot actAs allocated parties
Attempted the full external-party preapproval via interactive-submission,
following the sheet (NOT setup-proposal):
  1) Set up external party via /v0/admin/external-party/topology/{generate,submit}
     with client-side ed25519 signing  -> SUCCESS (party + key created)
  2) GET /v2/state/connected-synchronizers -> got synchronizerId  (OK)
  3) GET /v0/scan-proxy/dso-party-id       -> got DSO party        (OK)
  4) POST /v2/interactive-submission/prepare (actAs = external party)
     -> 403 "A security-sensitive error has been received"

Conclusion (confirmed from three independent angles — TransferInstruction_Accept,
wallet transfer-offers, and interactive-submission/prepare — all 403/404):
The hackathon's single client_credentials token authenticates as the validator
operator user `validator-backend@clients`. The Ledger API authorizes `prepare`
based on the TOKEN USER's rights (CanActAs), NOT on possession of the party's
signing key. That user has no CanActAs right for parties we allocate, so we
cannot actAs them to accept transfers or create preapprovals. Holding the
external party's ed25519 key lets us satisfy the signature at execute-time, but
we can never reach execute because prepare is rejected first.

What would unblock it (suggestions for Cantor8):
- Issue per-party Ledger API user tokens, OR grant the hackathon user
  CanActAs / CanReadAsAnyParty rights, OR
- Pre-create a TransferPreapproval for each participant's party server-side so
  sends auto-settle, OR
- Send CC via a path that doesn't require the receiver to actAs (e.g. to a
  party the operator token already controls).

Net: the documented "set up preapproval -> get CC -> use it" flow cannot be
completed end-to-end with the credentials handed out. Everything up to the
authZ boundary was implemented and verified.

## 7. RESOLVED — full flow completed. The two actual root causes:
Finding #6 above was WRONG in its conclusion — the flow IS completable with the
hackathon token. The real blockers, both now fixed and verified with a
successful accept (updateId 122050e2...):

(a) **userId mismatch**: the token's Ledger API user is
    `validator-backend@clients` (the Keycloak client). Submitting commands with
    any other `userId` (e.g. "hackathon") is rejected as a masked
    403 "security-sensitive error" — with NO hint that userId is the problem.
    Setting `userId: "validator-backend@clients"` (or omitting it) allows
    actAs on internally hosted parties.
    DOCS SUGGESTION: state the ledger-api user id for the shared token, and
    that the masked 403 commonly means userId/actAs mismatch.

(b) **Token Standard choice context**: `TransferInstruction_Accept` fails with
    `Missing context entry for: external-party-config-state` unless the choice
    context is fetched from the registry and passed in. The working recipe:
      POST /v0/scan-proxy/registry/transfer-instruction/v1/{cid}/choice-contexts/accept
    returns `choiceContextData` (goes into choiceArgument.extraArgs.context)
    and `disclosedContracts` (4 contracts; go into the command's
    disclosedContracts, mapping created_event_blob -> createdEventBlob etc.).
    DOCS SUGGESTION: the sheet links the transfer-instruction API but never
    says the accept requires this context fetch; one worked example would
    save hours.

With (a)+(b), TransferInstruction_Accept returned 200 and the CC settled.
Full journey: allocate -> receive as AmuletTransferInstruction -> fetch accept
choice-context via scan-proxy -> exercise accept -> Holding balance on ACS.
