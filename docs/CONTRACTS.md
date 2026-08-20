---
id: ACTAKIT-CONTRACTS-001
kind: canonical-contracts
state: proposed-for-acceptance
created: 2026-08-19
authority: architecture-proposal
summary: Versioned record, review, citation, privacy, and projection contracts for actakit 1.0.
related:
  - ACTAKIT-ARCH-001
  - ACTAKIT-IMPLEMENTATION-001
  - ACTAKIT-RELEASE-001
---

# Canonical Contracts

## Contract Rules

Canonical records are persisted by the node service in a relational store. They
are serialized in versioned canonical JSON for hashing, audit, export, and
tests. Markdown, YAML frontmatter, JSONL, and database rows are formats; none
alone defines meaning.

Every mutable canonical record has:

```yaml
id: opaque stable identifier
schema_version: contract version
origin_node_id: issuing canton node
revision: monotonic record-local revision
created_at: ISO-8601 UTC timestamp
created_by: human, service, or process identity
record_hash: SHA-256 of canonical serialization
```

Every authoritative mutation carries an `operation_id`, `actor_role`, and a
reason when it approves, rejects, corrects, restricts, or releases. A mutation
of an existing record also carries `expected_revision`.

Reusing an operation ID with the same canonical request returns its prior
receipt. Reusing it with different meaning is rejected. A stale revision is
rejected or explicitly reconciled; it never silently overwrites.

## IDs and Namespaces

IDs are opaque UUIDv7-compatible values with type prefixes such as `src_`,
`run_`, `cap_`, `art_`, `rep_`, `doc_`, `clm_`, `evl_`, `ep_`, `hilo_`,
`review_`, `corr_`, and `snap_`.

Filenames, municipal acta numbers, URLs, titles, Hilo names, and list positions
are labels or external identifiers. They are never canonical identity. Every
federated/public identifier includes the originating node namespace.

## Source Admission

### Source policy

A source policy is a versioned, human-approved rule for one source family. It
records issuer/owner, authority level, allowed hosts/endpoints, permitted
document types, acquisition method, rate limits, terms/rights note,
retention/privacy policy, review date, and status:

```text
draft -> active -> suspended -> retired
```

A source run pins one active policy revision. Public reachability does not imply
collection, retention, redistribution, or automated processing permission.

### Source run and capture

A source run is one bounded attempt to inspect a declared scope. It records
trigger, adapter/configuration version, start/end, count, diagnostics, source
checkpoint, and outcome:

```text
queued -> running -> succeeded | partial | failed | cancelled
```

A source capture records each discovered/fetched/unchanged/unsupported/failed
resource. It retains requested/final URL, retrieval time, limited safe response
metadata, source-local identifier, and either an artifact ID or failure reason.
A partial run cannot delete prior source knowledge.

## Evidence Custody

### Artifact

An evidence artifact is immutable acquired bytes. It requires SHA-256, byte
length, detected media type, first capture, acquired time, archive locator, and
fixity/custody status:

```text
pending -> verified | quarantined | rejected | disposed
```

The archive writes, hashes, fsyncs, and atomically places bytes before the
database creates a custody receipt. The same bytes from two source captures may
share physical storage but retain separate provenance.

### Representation

A representation is a source original, extracted text, OCR output, normalized
text, page image, transcript, preview, or redacted public derivative. It names
its immutable parent artifact/representation and records its own digest, media
type, language/charset, generator version, configuration hash, quality metadata,
and process run:

```text
pending -> validated | failed -> deprecated
```

An OCR or redacted representation never replaces the original evidence.

### Process run

Extraction, OCR, import, classification, model use, and rendering are process
runs. Each records exact input IDs/hashes, executor/version, configuration,
model/provider/prompt identifiers where applicable, time, result IDs, and
diagnostics. A model result is a proposal, never factual source evidence.

## Civic Documents

All civic documents share a `CivicDocument` identity with source-supplied title,
issuer/body, controlled type, supplied/normalized identifiers, date object,
language, representations, identity confidence, and visibility tier.

Supported 1.0 types:

```text
acta, agenda, convocatoria, acuerdo, resolucion, oficio, informe,
dictamen, presupuesto, plan, contratacion, expediente,
reglamento_ordenanza, aviso_publico, correspondencia, comunicado_prensa,
audio_video, dataset, otro
```

`otro` requires a label and review. Type profiles add only fields needing domain
semantics. Actas require session body, date, type, and supplied acta number
where available. Reports identify reporting body and covered period.
Budgets/plans identify their fiscal/planning period. An unknown date records
source text and precision (`day`, `month`, `year`, or `unknown`); the system
never invents a full date.

```text
candidate -> described -> verified | rejected
```

Withdrawal of an external document is an observable source condition, not
deletion of preserved evidence.

## Claims and Evidence Links

An episode is reader-oriented; a claim is the smallest approved proposition.
Every claim carries exact text, language, classification, temporal scope,
attribution, sensitivity flags, review state, and revision history.

```text
source_assertion
derived_inference
community_report
verification_question
```

```text
draft -> in_review -> accepted | rejected
accepted -> superseded | retracted | restricted
```

An evidence link binds a claim to an immutable representation through one typed
relation:

```text
supports, contradicts, contextualizes, quotes, mentions
```

It includes an exact locator. Minimum locators are artifact digest,
representation ID, and page/folio or article/item. Strong locators add exact
quote, prefix/suffix, and offsets in a named hashed text representation.

| Representation | Required locator |
|---|---|
| PDF | Page plus exact quote; article/item when supplied |
| Text/HTML | Exact quote, prefix, suffix, start/end offsets |
| Audio/video | Start/end time and transcript quote where available |
| Spreadsheet/table | Sheet/table, row, column/header, quoted value |
| Scan/image | Page/image and region coordinates; OCR quote when available |

Direct source assertions require an active supporting locator. Inferences name
their input claims and rationale. Community reports and questions are not
rendered as official factual findings by default.

## Review and Editorial Assessment

A review targets an immutable subject revision/hash. It records reviewer,
authority role, checklist, decision, rationale, timestamp, and follow-up:

```text
open -> approved | rejected | returned | deferred
```

The initial roles are extractor, reviewer, editor, publisher, privacy reviewer,
node administrator, canton custodian, and recovery custodian. One person may
temporarily hold several roles, but a publisher cannot be the sole reviewer of
their own public release without a recorded canton waiver.

An editorial assessment may be `BLOCKED`, `REVIEW`, or `READY`. It measures
process sufficiency, never truth, legality, or permission to publish.

Quotations require quote-context review. Sensitive claims require a
harm/minimization review. Quantitative claims require an identified data source
and either reproduction evidence or a stated reproducibility limitation.

## Episodes and Hilos

An episode groups accepted claims for a reader-facing event or development. It
has a title, date/date range, concise summary, linked documents, included claims,
and review state.

Hilos have stable IDs, slugs, titles, aliases, scope/exclusions, parent block,
and lifecycle:

```text
proposed -> active -> deprecated
```

Episode-Hilo membership is a reviewed edge (`primary`, `secondary`, or
`context`) with rationale. Multiple memberships do not duplicate a canonical
episode. Generated Markdown renders memberships and claims; curated legacy
context remains preserved until separately migrated.

## Corrections, Privacy, and Retention

A correction names the target revision, kind, reason, evidence, approver, and

```text
clarify, replace, retract, redact, unlink_evidence, merge
```

Corrections create new state and a supersession chain. A redacted public
representation is a derivative; it never silently overwrites a restricted
original.

Every retained record has an access tier and privacy/retention classification.
Public derivatives are default-deny until classified. Contact details, precise
home addresses, medical data, minors' identifying information, and individual
political-preference inferences are blocked from public output by default.
Legal holds stop automatic disposal. Retention actions preserve a minimal audit
receipt without retaining prohibited content.

## Publication and Federation

A publication snapshot is an immutable package of exact approved record
revisions and public-safe representations:

```text
draft -> validated -> released -> superseded | retracted
```

The snapshot manifest includes schema version, origin node, input checkpoint,
record/representation list, hashes, build process, approvals, publicability
policy, correction status, and output hashes.

A node exports only explicit public snapshots. A peer imports a valid snapshot
as external evidence in a separate read-only namespace. Imported material never
becomes locally authoritative, is never auto-republished, and cannot mutate the
originating node. Omission from a later package is not withdrawal; withdrawal
is a signed explicit record.

## Legacy Compatibility

Existing Markdown actas and Hilos remain authoritative legacy content until
their records are imported and reviewed. The importer creates proposals with
stated provenance limits. No mass regeneration, automatic normalization, or
revision rewriting is allowed.
