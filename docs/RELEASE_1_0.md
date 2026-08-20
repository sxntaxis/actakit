---
id: ACTAKIT-RELEASE-001
kind: release-and-operations-plan
state: proposed-for-acceptance
created: 2026-08-19
authority: roadmap-proposal
summary: Deployment, security, federation, migration, support, and evidence gates for a distributable actakit 1.0.
related:
  - ACTAKIT-ARCH-001
  - ACTAKIT-CONTRACTS-001
  - ACTAKIT-IMPLEMENTATION-001
---

# Release and Operations Plan for 1.0

## Distribution Model

1.0 distributes a sovereign canton node, not a hosted national service. The
supported baseline is an organization-owned Linux LTS workstation or mini-server
with encrypted local storage, an unprivileged service account, one local node
service, SQLite WAL, and a content-addressed archive.

The node functions offline after installation. It has no mandatory telemetry,
cloud account, central identity provider, or remote administrator. macOS and
other platforms remain preview until they meet the same certification evidence.

```text
local operator clients
        |
  canton node service
        |
SQLite WAL + immutable archive + audit trail
        |
optional signed public snapshots
        |
explicitly trusted peer nodes or removable media
```

SQLite is safe only on local attached storage. Node database/WAL files must not
be put on NFS, SMB, Dropbox, Nextcloud sync folders, or shared cloud drives.

## Organization and Roles

Every distributed node requires at least two named canton custodians.

| Role | Authority |
|---|---|
| Canton custodian | Node policy, appointments, peer trust, recovery/activation decisions |
| Node administrator | Install, patch, monitor, back up, restore; no unilateral publication |
| Records editor | Create and correct local records within assigned scope |
| Reviewer/publisher | Review and release a public snapshot |
| Privacy reviewer | Review sensitive-data, minimization, redaction, and retention cases |
| Federation steward | Add/remove peer trust and import schedules; cannot make imports local authority |
| Recovery custodian | Holds independently stored recovery material; no routine node access |
| Support provider | No standing data, key, backup, or publication access |

The publisher cannot be the sole reviewer of their own release unless a recorded
waiver explains why a small organization cannot separate the roles.

## Node Identity and Federation

A node receives an immutable random `node_id` at installation. It has an offline
Ed25519 root key and an online snapshot-signing key. The root signs key
certificates, rotations, and recovery epochs. The online key signs public
snapshots, feeds, and withdrawal notices.

Private key material stays under canton custody. The root recovery key is
encrypted and held separately from ordinary backups by recovery custodians.
Support providers and peer nodes never receive it.

Peer trust is explicit: a federation steward verifies a peer root-key fingerprint
through an independent canton-controlled channel, then pins it locally. There is
no trust-on-first-use and no mandatory global registry.

Federation packages use canonical JSON, SHA-256 digests, Ed25519 signatures,
versioned schemas, fixed size/path limits, expiry, and explicit withdrawals.

```text
receive
-> verify path/type/size
-> verify manifest hashes
-> validate schema
-> verify signature and pinned root chain
-> quarantine and preview
-> import as external evidence
```

Imported material always shows producing node, snapshot, signer, import time,
and withdrawal status. No import auto-republishes, merges identity, or modifies

## Public Release and Withdrawal

The public release builder exports only approved public snapshots and public-safe
representations. It never exports a database dump, archive root, private source
policy, credentials, internal review notes, or restricted originals.

Every released package identifies exact input revisions, policy/build versions,
approvals, manifest hash, origin node, and correction status. A correction emits
a new snapshot. Omission in a later snapshot is not deletion; a signed
withdrawal names scope, effective time, and non-sensitive reason code.

Withdrawal removes material from ordinary local public views after verification,
but cannot prove that prior recipients deleted their copies. This limitation is
part of operator and public documentation.

## Security Baseline

| Threat | Required 1.0 control |
|---|---|
| Hostile municipal site/redirect | Policy allowlist, redirect revalidation, private-address denial, media/size limits, rate limits, source receipts |
| Malicious PDF/DOCX | Non-root, no-network extraction sandbox; read-only inputs; resource limits; maintained parsers |
| Local shared-directory attacker | Dedicated OS account, restricted permissions, atomic descriptor-safe writes, symlink/TOCTOU tests |
| Prompt injection | Documents are data, never instructions; AI has no shell/network/secrets/canonical-write authority |
| Accidental destructive operation | Node identity preflight, dry run, explicit confirmation, operation receipt, backup |
| Privacy/civic harm | Evidence/locator requirements, human review, minimization/redaction policy, no individual profiling or targeted persuasion |
| Supply-chain compromise | Hash-locked dependencies, signed releases, SBOM, license/vulnerability review, reproducible build evidence |
| Lost keys/backups | Independent recovery custody, encrypted 3-2-1 backups, tested restore/key-loss runbook |

No public endpoint is enabled by default. Any future endpoint serves only
approved snapshots and is separately reviewed for authentication, rate limiting,
logging, abuse handling, and data minimization.

## Backup and Restore

Backups use a consistent SQLite backup method, never a copy of a live database
file that ignores its WAL. Each backup contains database snapshot, referenced
archive objects, schema/app/configuration versions, policy/taxonomy,
audit/publication receipts, key certificates, and an encrypted checksum manifest.
Live secrets and the sole recovery key are not stored beside the backup.

Use encrypted 3-2-1 custody:

```text
one local encrypted recovery copy
one separate-device copy
one organization-controlled off-site or disconnected copy
```

Before each release, and at least daily during operation, create and verify a
backup. Restore rehearsals occur at least quarterly on clean isolated hardware.
A restored node is inactive until database, archive hashes, schema, audit,
projection, and publication ledgers are verified and a custodian activates it.

## Packaging, Updates, and Compatibility

1.0 ships a signed source distribution, wheel, and rootless OCI image. The
release includes SHA-256 checksums, SBOM, third-party license report,
vulnerability report, build provenance, installation instructions, and recovery
instructions. Dependencies are locked transitively with hashes; build and
development dependencies are locked separately.

Release channels are `dev`, `beta`, `rc`, and `stable`. No channel performs an
and a documented compatibility/rollback path. Software update transport never
receives civic-record data.

Version independently:

```text
application
database schema
canonical record schema
config schema
projection/export schema
federation package schema
```

Within `1.x`, additive changes preserve supported compatibility. Breaking
canonical/config/export changes require a major release, staged migration, and
coexistence plan. The stable channel supports security fixes for 18 months and
the current plus previous minor release for routine fixes.

## Migration From Existing Esparza Work

1. Inventory the legacy vault without mutation: source/derived hashes,
   duplicates, references, unparseable dates, missing citations, symlinks, and
   source-lineage gaps.
2. Create an immutable pre-migration backup and fingerprint.
3. Build an isolated inactive candidate node, never in place.
4. Import selected records as review proposals with explicit source/locator
   limitations; preserve legacy Markdown separately.
5. Reconcile source hashes, document identity, citations, Hilos, privacy status,
   and projection output. Record accepted, quarantined, rejected, and unresolved
   items.
6. Activate only by explicit administrator receipt and fence the old writer.

The first operational proof uses a new acta after Acta 161. Historical material
is migrated only after the new workflow succeeds in real work.

## Test and Evidence Program

| Layer | Required proof |
|---|---|
| Unit/contract | IDs, revisions, schemas, locators, privacy gates, operation replay, citation rendering |
| Parser/extraction | PDF/DOCX/OCR variants, malformed files, Spanish dates, Unicode, hostile text, changed sources |
| Integration | Source run through archive, representation, proposal, review, claim, episode, Hilo, and snapshot |
| Failure/recovery | Kill, disk full, permission denial, lock contention, timeout, corrupt object/database, restart, stale writer |
| Security | Path/symlink, SSRF/redirect, parser sandbox, prompt injection, secret redaction, publication authorization |
| Migration | Legacy candidate, interrupted migration, rollback, split-authority quarantine |
| Federation | Valid package/import plus invalid hash/signature/key/path/size/withdrawal cases |
| Operator journey | Named human source review, correction, backup, restore, and public release workflow |

Fixtures are synthetic or explicitly privacy/rights-approved. Expected results
remain independent from production implementation. CI runs every supported test
layer; release tests repeat enough times to expose flakes.

## 1.0 General Availability Gates

| Gate | Required evidence |
|---|---|
| Release identity | Confirm whether `1.0.0` was externally distributed; never reuse a published version |
| Policies/governance | Accepted role, source, privacy, correction, retention, federation, incident, and release policies |
| Contracts | Versioned/validated canonical, CLI, configuration, projection, and package contracts |
| Integrity | Reference corpus has complete source-hash/citation lineage and no unresolved critical misattribution/data loss |
| Migration | Fresh migration, interruption, stale-writer, rollback, and split-authority drills pass |
| Recovery | Clean-machine restore verifies database/archive and meets the documented recovery objective |
| Security | Threat controls, sandbox, path, prompt-injection, secret, privacy, and authorization tests pass |
| Supply chain | Locked dependencies, SBOM, licenses, vulnerability review, signed artifacts/tag, and provenance are published |
| Federation | Two isolated pilot nodes exchange valid snapshots and reject invalid/trust-violating packages |
| Pilot | Two independent FA local organizations complete a documented civic cycle, correction, export, and restore drill |
| Operations | Spanish-first runbooks, training, support contacts, incident templates, and containment drill complete |
| Approval | Release, security, privacy/data, and pilot civic authorities sign the GA decision |

Validation evidence is not release authority. A candidate becomes 1.0 only after
all gates are recorded, reviewed, and explicitly approved.
