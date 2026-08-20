---
id: ACTAKIT-IMPLEMENTATION-001
kind: implementation-plan
state: proposed-for-acceptance
created: 2026-08-19
authority: roadmap-proposal
summary: Ordered work packages, dependencies, and proof gates for reaching a distributable actakit 1.0.
related:
  - ACTAKIT-ARCH-001
  - ACTAKIT-CONTRACTS-001
  - ACTAKIT-RELEASE-001
---

# Implementation Plan Through 1.0

## Delivery Rule

Every work package ends with executable evidence, not a design claim. A later
package may not bypass an earlier gate. Work may be parallelized only when its
inputs and authority boundaries are explicit.

Current scripts are retained as adapters and legacy import tools. They are not
incrementally promoted into canonical writers. New authority flows through the
node service from the first persistent write onward.

## Work Package 0: Acceptance and Operating Policies

**Purpose:** turn proposed architecture into explicit human authority.

**Deliverables**

- Accepted/amended architecture and contracts.
- Node role charter: two canton custodians, administrator, reviewer/publisher,
  privacy contact, recovery custodian, and support escalation.
- Versioned source admission, privacy/minimization, correction, retention,
  federation, release, incident, and support policies.
- Supported deployment profile: one organization-owned Linux LTS host/node.
- Confirmed 1.0 release identity. If `1.0.0` was previously distributed, it is
  never reused; the first GA release receives a new valid version.
- A privacy-reviewed synthetic fixture corpus and named first Esparza proof.

**Gate:** named human authority accepts the policy set. No persistent service or
migration work starts before this gate.

## Work Package 1: Repository Foundation and Test Harness

**Purpose:** make correctness measurable before changing data authority.

**Deliverables**

- Responsibility-oriented package layout: `kernel`, `application`,
  `infrastructure`, `adapters`, `projections`, and `clients`.
- One declared test command that discovers all supported tests and excludes
  archived/non-product material explicitly.
- Linting, type checking, formatting, dependency lock, contract-schema checks,
  and import-boundary tests in CI.
- Fixture corpus with municipal CMS variants, PDFs, DOCX, image-only PDFs,
  malformed files, changed bytes at same URL, duplicate names, Spanish/OCR
  defects, hostile document text, and privacy-sensitive cases.
- Versioning matrix for application, database schema, record schema, config,
  projection/export schema, and federation package schema.

**Reuse:** preserve current parser/extractor tests; promote the current Hilo
tests into the full test command; keep `tools/MuniEsparzaAPI` isolated until it
is converted into a source adapter.

**Gate:** CI runs the complete test set from a clean checkout. No test command
may hide archived failures accidentally. Contracts and fixture expectations are
versioned outside production implementation.

## Work Package 2: Dependency-Free Semantic Kernel

**Purpose:** prove meaning and validation without database/network complexity.

**Deliverables**

- Typed IDs, UTC timestamps, SHA-256 values, revisions, operations, receipts,
  schema versions, and typed errors.
- Immutable in-memory contract objects from `CONTRACTS.md`.
- Canonical JSON serialization and hashing.
- Source, claim, evidence-link, locator, review, correction, and snapshot
  validation.
- Pure editorial-readiness assessment.
- Import readers for legacy Markdown v1 and current frontmatter v2. Readers do
  not mutate the vault.

**Required negative tests**

- AI proposal cannot support a factual claim.
- Quote without locator/context check is blocked.
- Claim with no required evidence is blocked.
- Citation cannot resolve to URL-only or page-only provenance.
- Same operation ID with different request is rejected.
- Stale mutation is rejected.
- Personal-data classifications prevent public rendering.

**Gate:** all core transitions, invalid states, and canonical serializations
pass unit and property tests. No database or UI hides an undefined semantic rule.

## Work Package 3: Node Service, SQLite, and Evidence Archive

**Purpose:** establish durable local authority for one canton node.

**Deliverables**

- One unprivileged local node service and client protocol over a Unix socket.
- SQLite WAL canonical database with explicit migrations and foreign keys.
- Content-addressed evidence archive with atomic write, fsync, hash verification,
  restrictive permissions, and custody receipts.
- Source policy, source run, source capture, artifact, representation, process
  run, operation receipt, audit, and health repositories.
- Backup/export candidate builder, restore verifier, and schema compatibility
  checks.

**Rules**

- Clients never open SQLite directly for canonical writes.
- Archive object write/verification precedes its database reference.
- SQLite files remain on local storage, never sync folders, network shares, or
  cloud-drive mounts.
- The service serializes writers and bounds read transactions.

**Gate**

- Same bytes from two sources retain distinct capture provenance.
- Missing archive object degrades custody without erasing history.
- Partial source run does not delete prior records.
- Restart preserves records; only ephemeral coordination state disappears.
- Backup/restore reproduces a verified inactive candidate node.
- Killed/interrupted writes leave no authoritative half-record.

## Work Package 4: Source Adapters and Representation Pipeline

**Purpose:** admit official documents safely before interpreting them.

**Deliverables**

- Adapter protocol with source-policy enforcement, bounded network access,
  redirect revalidation, host allowlists, rate limits, size/media-type limits,
  safe diagnostics, and source checkpoints.
- Esparza municipal CMS adapter based on the current generic scraper.
- Optional Junar adapter refactored from `MuniEsparzaAPI` after the generic path
  passes the proof.
- Sandboxed PDF/DOCX extraction with no network, non-root execution, bounded
  CPU/memory/time, and representation/process-run registration.
- File-type and hash verification adapted from current tools.

**Gate:** the system correctly handles a changed document at the same URL,
duplicate filenames, malformed documents, scan/OCR failure, redirects, source
outage, and interrupted extraction. Every retained output names its parent.

## Work Package 5: Reviewable Civic Interpretation

**Purpose:** turn evidence into controlled civic knowledge.

**Deliverables**

- Proposal creation for extraction, document description, claims, routing,
  entity suggestions, announcements, and report findings.
- Named reviewer/editor workflows that approve, reject, return, defer, correct,
  or restrict a concrete record revision.
- Acta profile: session details, articles/items, agreements, announcements,
  episodes, and Hilo memberships.
- Generic report/officio/budget profiles with document-specific fields but the
  same claim/evidence/review core.
- Exception queue for weak locators, date ambiguity, duplicate identity,
  unknown topics, contradictory evidence, and sensitive content.

**Gate:** no approved claim, episode, or Hilo membership can be created without
evidence, locators, and review decision. The operator can see unresolved
conflicts and source limitations without reading database rows.

## Work Package 6: First End-to-End Esparza Proof

**Purpose:** prove the full model against the first available official acta after
Acta 161.

```text
source policy
-> source run and capture
-> immutable original artifact
-> extraction representation
-> AI/human proposals
-> named review
-> accepted claims and episode
-> local acta dossier/Hilo projection
-> citation packet
```

**Constraints**

- No legacy acta/Hilo is regenerated or modified automatically.
- No live Nextcloud publication occurs.
- The same processing run may be replayed without duplicate claims/episodes.
- A human reviewer can reject or correct each material proposal.

**Gate:** a meeting participant, podcast researcher, and scholarly reader can
each trace one rendered Hilo statement to a fixed artifact, representation,
page/article/item, quote, review decision, and source limitation. The node can
rebuild that projection after deletion without changing canonical history.

## Work Package 7: Projections, Search, and Local Operator Experience

**Purpose:** make the durable model useful without exposing internal complexity.

**Deliverables**

- Acta dossier, Hilo, citation, review queue, and source-health renderers.
- Projection manifests with input checkpoint, build version, output hashes, and
  publicability tier.
- Search over approved local claims and metadata only.
- Spanish-first CLI/operator workflows for intake, review, correction, export,
  backup verification, and health.
- Legacy Hilo preservation/import strategy that adds new projected content while
  maintaining curated historical context.

**Gate:** deleting a projection and rebuilding it from the same checkpoint yields
an equivalent result. Search, Markdown, and citation views agree on claim
revision and evidence locator. Corrections create a new view/snapshot rather
than a silent prose edit.

## Work Package 8: Controlled Publication and Inter-Canton Exchange

**Purpose:** distribute public civic material without centralizing authority.

**Deliverables**

- Public snapshot builder that permits only approved public-safe records and
  representations.
- Signed, hash-bound snapshot manifest, correction, retraction, and withdrawal
  records.
- Node identity root and online snapshot signing-key lifecycle.
- Opt-in peer allowlist, node card, package validation, quarantine/preview, and
  imported external-evidence namespace.
- Generic publication adapter contract; Nextcloud is one optional adapter after
  the generic release workflow passes.

**Explicit exclusions**

- No shared national database.
- No automatic peer trust, identity merge, republishing, or conflict resolution.
- No cross-canton writes.
- No writable MCP in 1.0.

**Gate:** two isolated test nodes exchange a valid public snapshot. Tampered
hashes, invalid signatures, expired/rotated keys, unsafe paths, oversized
packages, untrusted peers, and withdrawals fail or quarantine correctly.
Imported records retain origin and cannot be edited as local authority.

## Work Package 9: Legacy Migration and Operational Hardening

**Purpose:** bring value from existing work without laundering uncertain history
into new canonical records.

**Deliverables**

- Read-only inventory of the Plaza vault: hashes, duplicates, citations, broken
  references, source lineage, and ambiguity report.
- Immutable pre-migration backup and verified migration candidate node.
- Bounded importer that turns selected legacy records into review proposals with
  stated provenance/locator limits.
- Reconciliation report for accepted, quarantined, rejected, and unresolved
  imports.
- Recovery, backup, restore, key rotation, update, incident, and downgrade
  runbooks.

**Gate:** migration activates only by explicit administrator receipt after source
hash, lineage, citation, privacy, and projection reconciliation. Rollback is a
new authority activation; it never pretends to retract external publication.

## Work Package 10: Beta, Release Candidate, and 1.0

**Purpose:** prove distribution in real civic organizations before general use.

```text
dev: synthetic fixtures only
-> beta: opt-in pilot nodes with isolated data
-> rc: frozen schema, migrations, and release candidate
-> stable: signed 1.0 release
```

**Beta requirements**

- At least two independent Frente Amplio local organizations.
- Thirty days of routine use or equivalent documented civic work cycle.
- One real document workflow, correction, export, and restore drill per pilot.
- No unresolved P0/P1 data-integrity, security, privacy, or publication defect.

**Gate:** all release gates in `RELEASE_1_0.md` are evidenced and signed by
release, security, privacy/data, and pilot civic authorities.

## Work Explicitly Later

- Public web application and national hosting.
- National orchestrator or deputy/presidential dashboard.
- Graph database, triplestore, SPARQL endpoint, vector database, or semantic
  search beyond approved local search.
- IIIF server, DCAT catalog, JSON-LD/RDF public graph, and advanced standards
  adapters.
- General press/social/interview intelligence beyond approved civic sources.
- Writable MCP or autonomous publication.

These may be valuable. They are not prerequisites for a durable, distributable
1.0 canton node.
