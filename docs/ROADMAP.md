---
id: ACTAKIT-ROADMAP-001
kind: implementation-roadmap
state: proposed-for-acceptance
created: 2026-08-19
authority: roadmap-proposal
summary: Architecture-first, proof-gated plan for evolving actakit from a file pipeline into a local civic-record service without discarding the existing vault.
related:
  - ACTAKIT-ARCH-001
  - ACTAKIT-STATUS-001
---

# Implementation Roadmap

This is the conceptual phase map. The ordered engineering work packages,
dependencies, and acceptance evidence through 1.0 are in
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). The 1.0 distribution and
operations requirements are in [`RELEASE_1_0.md`](RELEASE_1_0.md).

## How Much Architecture Now

Do enough architecture now to freeze expensive boundaries, and no more.

**Freeze before implementation:** semantic ownership, evidence identity,
revision/correction rules, review authority, privacy/publication policy,
database/archive boundary, projection boundary, operation replay, source-run
semantics, and MCP read/write boundary.

**Defer until evidence demands it:** web UI, public hosting, national corpus
scale, domain-pack plugins, graph database, vector search, IIIF service,
semantic-web endpoint, scheduler cluster, and national orchestration.

The outcome is not a speculative platform. It is a durable local core that can
grow without reassigning authority later.

## Phase 0: Architecture Acceptance

**Deliverables**

- Accept or amend `docs/ARCHITECTURE.md`.
- Name the initial human roles and escalation path.
- Adopt source-admission, privacy/minimization, correction, and publication
  policies as versioned documents.
- Define a small schema vocabulary and stable ID rules.
- Define the first acceptance fixture and the required evidence for Acta 162.

**Gate**

No database, daemon, MCP, or migration code begins until the human authority
accepts the architecture and policy set.

## Phase 1: Dependency-Free Semantic Kernel

**Goal:** validate the civic record model before storage/network complexity.

**Build**

- Typed IDs, revisions, digests, timestamps, operation envelopes, and errors.
- Immutable record contracts for artifacts, representations, claims, evidence
  links, review decisions, and publication snapshots.
- Pure editorial-readiness assessment.
- Input/output schema validation and stable serialization.

**Proof**

- AI proposals cannot be factual support.
- Quotes require exact locators and context review.
- Quantitative claims require a documented source/reproduction limit.
- Conflicting evidence remains visible.
- Same operation ID is replay-safe; changed semantics are rejected.

## Phase 2: Local Canonical Service and Evidence Custody

**Goal:** establish one durable local writer without changing public outputs.

**Build**

- Profile-scoped SQLite WAL store with versioned migrations.
- Content-addressed archive with SHA-256 fixity verification and custody
  receipts.
- Source policy, source-run, acquisition-attempt, and source-health records.
- Atomic writes, restricted file permissions, backup/restore verification, and
  fail-closed unsupported-schema behavior.

**Proof**

- Same bytes from distinct sources preserve distinct provenance.
- Missing archive bytes degrade custody but do not erase history.
- Partial/failing source runs do not imply deletion.
- Stale writers cannot advance a newer revision.
- Restart preserves canonical data and invalidates only ephemeral state.

## Phase 3: One New Acta Vertical Slice

**Goal:** prove the system with the first official Esparza acta after Acta 161.

**Flow**

```text
source admission
-> acquire and archive original bytes
-> verify fixity and source policy
-> extract representation
-> record extraction/AI proposal occurrence
-> human review
-> approve claims and episode
-> render local acta dossier and Hilo update
-> generate citation packet
```

**Constraints**

- No historical regeneration.
- No live Nextcloud publishing.
- No claim reaches an approved Hilo without evidence links and locators.
- The human reviewer can reject, correct, return, or defer the proposal.

**Proof**

- A reader can move from one Hilo assertion to a fixed source artifact and
  article/item/page locator.
- Replaying extraction creates a new proposal, not a silent correction.
- Re-running integration does not duplicate a claim or rewrite curated Hilos.
- One interrupted operation recovers without duplicate canonical state.

## Phase 4: Projection and Citation Layer

**Goal:** preserve today’s accessible output while making it generated and
auditable for new records.

**Build**

- Approved acta dossier renderer.
- Incremental Hilo renderer that preserves explicitly curated context.
- Citation styles for meeting notes, podcasts, research, and machine clients.
- Projection manifests with input checkpoint, schema version, build time, and
  output hashes.
- Search over approved claims and evidence metadata.

**Proof**

- Markdown, search, and citation output agree on claim/version/locator.
- A projection can be deleted and rebuilt identically from its checkpoint.
- A correction produces a new projection/snapshot rather than editing a prior
  publication record in place.

## Phase 5: Operator Interfaces and Federation Contract

**Goal:** make approved civic evidence safely reusable by people and prepare
sovereign canton nodes to exchange reviewed public snapshots.

**Build**

- Versioned local service protocol and CLI client.
- Versioned, opt-in public snapshot/export manifest and citation bundle.
- Node namespace, publicability, correction, and import/adoption rules.
- Strict input/output schemas, bounded queries, authorization scopes, audit
  records, and fail-closed validation binding every response to a
  snapshot/checkpoint.

**Proof**

- A second node can import a public snapshot only as external evidence and
  cannot mutate the originating node.
- A correction or withdrawal remains traceable across exported snapshots.
- Citation retrieval is deterministic and returns source limitations.
- Prompt-injection text in a source document cannot alter tool behavior.

## Phase 6: Controlled Publication and Nextcloud Adapter

**Goal:** publish only reviewed immutable snapshots.

**Build**

- Publication policy and named publisher approval.
- Signed or hash-bound publication manifest.
- Nextcloud adapter that uploads a reviewed snapshot idempotently.
- Publication receipt and optional external verification.
- Correction/withdrawal workflow that preserves prior publication history.

**Proof**

- A plan cannot publish an unapproved claim.
- A retry does not duplicate or overwrite a newer snapshot.
- An uncertain remote response remains uncertain until verified.
- No remote deletion is part of normal publication.

## Phase 7: Deliberate Historical Migration

**Goal:** improve selected high-value history without inventing provenance.

**Approach**

- Migrate by bounded thematic or acta batches.
- Preserve legacy source quality and locator limitations explicitly.
- Record imports as human-reviewed migration proposals.
- Keep legacy Markdown as an accessible projection and source reference.

**Gate**

Historical migration proceeds only after the new-acta vertical slice has been
used and reviewed in real work.

## Future Decisions, Not Commitments

- Public hosting and open-data catalog
- Read-only MCP, REST, or other client adapters
- IIIF page-image service
- JSON-LD/RDF, PROV-O, DCAT, and Web Annotation exports
- National orchestrator or cross-canton discovery service
- Multi-reviewer governance
- Public correction/takedown portal
- Additional source types: press, social media, interviews, budgets, and
  procurement records

Each requires a separate architecture-impact decision. None is implied by the
local civic-record core.
