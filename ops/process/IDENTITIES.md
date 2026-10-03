# Role isolation and future authority

Design only: no identity, credential, repository protection, registration or
runner is created or changed by this PR.

| Role | Repository access | Local access |
|---|---|---|
| Author | Source, own branch and PR; workflow write only for reviewed CI changes | Isolated checkout; no provider key or writable paid runtime |
| Independent reviewer | Read source/artifacts and review under a distinct authenticated identity | Synthetic fixtures or approved read-only copies; no provider key |
| Hub/executor | Merge/adopt consequential work; issue/revoke exact authority | Provider key and sole shared lock/ledger writer |
| Owner/admin | Provision isolated identities and effective repository rules | Credential provisioning and access separation |

Shared-account role comments remain auditable, but do not authenticate independent
identities. Separate identities require genuinely isolated credentials, not labels
sharing the same token. The owner provisions separate accounts/app installations
or role credentials. Workers must not retrieve the executor key or impersonate the
spending issuer. Record allowed immutable issuer IDs; names alone are insufficient.

Preparation found no effective branch protection/rules on main. Admin follow-up:
configure required CI and independent review for consequential changes, stale
approval handling and restricted merge authority; verify actual effective settings.
A blanket native review rule may also require review on explanatory docs. Do not
promise an exemption until the chosen rules/merger enforce effect-based tiers.
No author bypass, self-downgrade or shared-token native approval. This setup is not
a blocker for the prospective text/CI cleanup and is not claimed to exist yet.

## Future structured purchase authority

[`authority-format.json`](authority-format.json) defines future record shape only;
today's runner does not accept it. Shape-valid JSON is not authorization. An
adopting reviewed adapter must fetch the original trusted authority event,
authenticate its immutable actor ID against the hub allowlist, compare the entire
record/body, bind exact executing commit/list/content/caps, then check live
revocation, withdrawal, expiry and consumption under the shared lock before each
send. Body hashes do not authenticate the issuer. Save provenance/check evidence
durably; unavailable or inconsistent checks fail closed.

Revocation is a later authenticated event bound to authorization ID. A copied
approved status, issuer string, worker boolean or cached comment is not live
approval. Exhaust one-time authority; restart only within its reviewed states and
only for untouched/unreserved IDs. Pending/uncertain requests retain reservation
and are never resent. Current runner authority, exact comments and stricter
semantics remain unchanged. Credential/protection setup requires owner/admin action.
This migration retains both independent and hub current-head AGREE under old rules.
