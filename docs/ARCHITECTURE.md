---
id: ACTAKIT-ARCH-001
kind: target-architecture
state: proposed-for-acceptance
created: 2026-08-19
authority: architecture-proposal
summary: Federated civic-record architecture with sovereign canton nodes, immutable evidence custody, human-reviewed claims, and rebuildable public projections.
related:
  - ACTAKIT-ROADMAP-001
  - ACTAKIT-STATUS-001
---

# Target Architecture

## Purpose

actakit is a local civic-record system for municipal actas. It must let people
find, verify, cite, correct, and reuse public-interest information without
turning AI summaries, Markdown files, or publication targets into authorities.

The first durable deployment is a **local civic record**. Public outputs are
audited exports, not the default authority or a promise of a public archive.

The 1.0 distribution unit is an autonomous canton node. Nodes may exchange
explicitly public, signed evidence packages, but they do not share a database,
operator account store, or canonical writer.

## Product Boundary

actakit is a civic institutional-record system. Actas are its first specialized
workflow, not its ceiling. Its common record model must admit municipal reports,
budgets, agreements, official correspondence, public notices, plans, datasets,
and other approved civic source types without making every source look like a
meeting.

```text
common civic record core
  source -> artifact -> representation -> document -> claim -> review
  -> publication snapshot

acta profile
  meeting -> agenda article/item -> intervention/agreement -> episode -> Hilo

report profile
  reporting body -> period -> finding/metric -> recommendation/response
```

Digest is a compatible sibling, not an actakit dependency. Digest may later
discover or preserve an external source and submit an evidence package. Actakit
independently applies its own source policy, review, civic interpretation, and
publication rules. Actakit must operate fully when Digest is unavailable.

## Architectural Decisions

1. Each canton operates a sovereign actakit node. A local actakit service is the
   sole writer of canonical state for that node.
2. SQLite in WAL mode is the baseline node store for canonical metadata,
   revisions, approvals, and operation receipts. It is not a substitute for the
   source files themselves.
3. An immutable content-addressed archive stores acquired source bytes and
   derived representations. Raw evidence is restricted by default.
4. Markdown actas, Hilos, reports, search indexes, Nextcloud manifests, and MCP
   responses are projections. They never become a second canonical store.
5. AI, scrapers, OCR, importers, and future clients may propose work. Named humans
   approve consequential claims, corrections, and publication.
6. Historical vault content remains a legacy import/projection source. It is not
   mass-rewritten to fit the new model.
7. The system begins with the next Esparza acta after Acta 161. A successful
   first proof is required before historical migration or public publication.

## Non-Negotiable Laws

### Evidence before interpretation

An acquired file, its extracted text, an AI proposal, a human-approved claim,
and a published statement are distinct records. No later record overwrites the
prior record or silently inherits its authority.

### Proposal is not approval

```text
acquisition or extraction proposal
!= approved source observation
!= approved claim
!= publication decision
```

The same person may act as extractor, reviewer, editor, and publisher at first,
but every action records its authority role.

### Identity and occurrence are distinct

```text
Acta identity
!= downloaded file version
!= OCR/extraction run
!= AI processing run
!= review event
!= publication snapshot
```

The same PDF acquired twice is not necessarily two actas. A corrected source,
newly discovered page, or improved extraction is a new representation or
revision with explicit lineage.

### No implicit deletion

Absence from a page, source run, model response, Hilo, index, or publication
does not mean the underlying item ceased to exist. A source run may declare a
complete scope only when that scope is known and recorded.

### Corrections preserve history

Corrections, clarifications, retractions, and privacy redactions produce new
attributable state. The public view may show the latest approved state, but the
internal record preserves the reason, authority, and supersession chain.

### Projections are disposable

Generated Hilos, search indexes, exports, and publication plans declare their
input checkpoint and build version. They can be rebuilt without destroying
canonical history. Curated legacy Hilos are preserved until deliberately
migrated as reviewed projection content.

## Semantic Record Families

The first implementation needs these families. It does not need a universal
ontology or a graph database. The relational records explicitly model graph
relationships and may later generate a graph/RDF projection.

| Family | Canonical meaning | Required distinction |
|---|---|---|
| Source policy | Whether and how a source may be acquired, retained, processed, and disclosed | Public availability is not permission for every downstream use. |
| Source run | One bounded acquisition attempt and its checkpoint/freshness outcome | Failure is not a document or a deletion. |
| Evidence artifact | Immutable acquired bytes with hash, media type, source URI, capture time, and custody receipt | Source URI, hash, and local storage path are separate identifiers. |
| Representation | PDF, DOCX, page image, OCR text, normalized text, or redacted derivative | A derivative never replaces its parent evidence. |
| Process run | Extraction, OCR, model, normalization, or import occurrence | Inputs, implementation/configuration/model versions, outputs, and diagnostics remain attributable. |
| Proposal | Machine or human candidate observation, claim, routing, or relation | A proposal has no public/canonical effect until review. |
| Claim | One attributable proposition with kind, epistemic status, revision, and sensitivity flags | An episode can contain several claims. |
| Evidence link | Relation between a claim and an exact artifact representation/locator | Support, contradiction, quotation, and context are distinct. |
| Review decision | Named human approval, rejection, return for research, correction, or publication decision | Readiness is process sufficiency, never automatic truth. |
| Episode | Reader-oriented grouping of approved claims from an acta | Episode prose is a projection over claims, not the evidence model. |
| Hilo membership | Approved relation between an episode/claim and a topic | A topic view cannot rewrite the acta dossier. |
| Publication snapshot | Immutable, citable output package for one intended audience | A later correction does not rewrite a prior snapshot. |
| Operation receipt | Idempotent record of a consequential mutation | Same operation ID with different meaning is a conflict. |

Detailed field requirements and lifecycle rules are defined in
[`CONTRACTS.md`](CONTRACTS.md).

## Canonical Storage and Custody

```text
CLI / review UI / worker / future adapter
                 |
                 v
        local actakit service
          |                 |
          v                 v
 SQLite canonical store   content-addressed archive
          |                 |
          +--------+--------+
                   v
            read-only projections
```

### SQLite canonical store

Stores IDs, relationships, revisions, policies, decisions, operation receipts,
and projection checkpoints for one canton node. Every authoritative mutation includes an
`operation_id` and, where a record already exists, an `expected_revision`.
Stale writes are rejected or explicitly reconciled; silent last-write-wins is
prohibited.

SQLite is chosen for the baseline because canton nodes are autonomous,
local-first services, not tenants of one national database. Federation does not
require a shared database engine. A node may later adopt PostgreSQL when its own
concurrent operators, deployment, access-control, or availability requirements
justify it; that is a node-local deployment decision, not a federation contract.

### Content-addressed archive

Stores source and derivative bytes under a declared digest such as SHA-256.
Ingest verifies byte count and digest before a custody receipt is recorded.
The archive records raw source, extracted text, OCR, page images, and redacted
derivatives as separate representations. Restricted raw material must not enter
Git or a public projection by default.

### Filesystem roles

```text
vault/3 Fuentes/      legacy and operator-visible source organization
vault/actas/          human-readable acta dossier projection
vault/Hilos/          reader-facing thematic projection
archive/              immutable service-owned evidence archive
SQLite database       canonical control-plane state
```

The exact physical locations may change. Their semantic roles may not.

## Claim and Citation Model

Every consequential public assertion is a claim, not merely a paragraph. A
claim records at least:

```yaml
claim_id: stable opaque ID
kind: fact | attributed_assertion | quote | analysis | opinion | forecast
epistemic_status: unverified | supported | corroborated | contested | refuted | indeterminate | retracted
text: normalized proposition
flags:
  sensitive: false
  quantitative: false
  ai_material: true
```

Each evidence link records an immutable artifact/representation and an exact
locator. The minimum citation locator is:

```text
artifact digest + representation version + page/folio + article/item
```

When available, add a text quote with prefix/suffix and offsets relative to a
named, hashed text representation. Page-image coordinates are preserved when
the source supports them. This enables both a short meeting citation and a
scholarly verification path.

AI output may contextualize or propose a claim. It cannot be the evidentiary
support for a factual claim.

## Review, Editorial, and Privacy Policy

### Human roles

- **Extractor** admits or transforms evidence under a source policy.
- **Reviewer** checks source fidelity, locator quality, and uncertainty.
- **Editor** approves claim and episode wording for a stated purpose.
- **Publisher** approves one immutable output snapshot.
- **Privacy reviewer** handles sensitive-data, minimization, or redaction cases.

The early system may assign all roles to one named operator. The records remain
separate so multi-person review can be introduced without changing the model.

### Editorial readiness

The system may calculate `BLOCKED`, `REVIEW`, or `READY` based on recorded
requirements. These states mean only that the configured process is complete or
incomplete; they never declare a claim true or legally safe to publish.

Public derivatives are minimal by default. Raw official material is retained
only under source policy and restricted access. actakit does not create
individual political-preference profiles or targeted-persuasion records.

## Source Authority and Public Claims

Source authority is explicit and field-specific. An official municipal acta,
an OCR derivative, a secondary report, a community statement, and an AI
proposal cannot satisfy the same evidentiary requirement.

The system distinguishes at least:

```text
official source document
official publication or repository
operational consolidation/copy
human testimony or community perception
secondary reporting
AI proposal
```

Public wording must disclose relevant limitations rather than claiming that a
copy, extraction, or model output is the original official authority.

## Interfaces and Exports

### Federation

Actakit nodes cooperate through explicit, versioned, opt-in exports. They do
not directly write one another's canonical records or replicate unreviewed
private material.

```text
Canton node A approved public snapshot
-> versioned export manifest and citation bundle
-> canton node B or future national orchestrator imports as external evidence
-> local human review and local adoption decision
```

Federation requires stable node namespaces, immutable snapshot IDs, source and
policy metadata, output hashes, publicability status, and correction lineage.
Raw evidence remains at its originating node unless a source policy explicitly
allows distribution. A future national orchestrator is a read/import client of
sovereign nodes; it does not become their canonical writer.

### CLI and service protocol

The CLI is a client of the local service, not an alternate writer. Requests and
responses have versioned schemas, bounded inputs, typed errors, and operation
IDs. The first service may use a local Unix socket; no cloud deployment is
required.

### Optional MCP adapter

MCP is one possible future access adapter, not an actakit goal or required
roadmap phase. If adopted, it is read-only at first and serves only approved
published snapshots. Its initial operations are limited to:

```text
search_published_claims
get_claim_evidence
get_acta_metadata
generate_citation
verify_artifact_fixity
```

It has no arbitrary URL fetch, filesystem access, SQL/SPARQL execution,
publication, deletion, or unrestricted export. Every input/output uses a
versioned schema and fixed result limits. Any future mutation requires a
separate authorization, review, and audit design.

### Interoperability

The internal model must be able to export PROV-O-like provenance, Web
Annotation-style locators, JSON-LD/RDF, and DCAT catalog metadata without loss.
These are export profiles, not the initial operational database. IIIF and
ClaimReview are later adapters, only when their specific publication use cases
are genuinely met.

## Verification

Architecture claims are insufficient. Each phase must prove:

1. contract/unit invariants;
2. repository and migration integrity;
3. a realistic civic fixture journey;
4. idempotent replay and interrupted-write recovery;
5. a named human review journey;
6. a citation resolved from public prose to a fixed artifact/locator;
7. prohibited MCP and publication paths fail closed.

## Explicit Non-Goals

- Public hosting or a national archive before the local proof succeeds.
- A general-purpose political profiling system.
- Automated truth, legal advice, or autonomous publication.
- A graph database, triplestore, vector database, or distributed queue in the
  first durable vertical slice.
- Historical mass migration or regeneration of the curated Esparza vault.
- A web UI before the service, evidence, review, and citation contracts work.

## Acceptance Required

This document is proposed architecture, not an implementation authorization.
Named human authority must accept it, amend it, or reject it before canonical
database/service work starts.

The full implementation sequence and the 1.0 distribution gates are defined in
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) and
[`RELEASE_1_0.md`](RELEASE_1_0.md).
