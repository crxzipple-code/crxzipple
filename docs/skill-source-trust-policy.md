# Skill Source Trust Policy

## Purpose

Skills are executable operating instructions for agents. A skill package can
change model-visible behavior and may reference scripts, resources, tools, and
access requirements. External skill installation therefore needs provenance and
trust controls before it is broadened beyond local/operator-managed sources.

## Current Allowed Sources

The current runtime may load skills from:

- system or bundled readonly sources
- global/local sources configured by the operator
- workspace sources inside the authorized workspace boundary
- explicitly installed packages whose source directory passes filesystem
  containment and validation

Runtime visibility is governed by Skills enablement policy. The `trusted` flag on
an enablement policy means the operator has allowed runtime visibility for that
target; it is not a cryptographic signature.

## Required Provenance For Broader External Install

Before broad external marketplace/repository installation is enabled, each
external package source must provide:

- source URI and immutable revision, commit, or package digest
- package fingerprint computed from `SKILL.md`, manifest/frontmatter, and
  discovered resource files
- installer actor, reason, timestamp, target source, and target scope
- signature or trusted publisher proof when the source is not operator-local
- installation audit record linked to the package index entry

An external install without provenance is allowed only as an explicit local
operator action and must remain scoped to local/workspace sources.

## Verification Rules

External install must reject or quarantine a package when:

- source root escapes its allowed boundary
- package fingerprint changes between validation and apply
- signature/publisher proof is required but absent or invalid
- `SKILL.md` or resource files are symlinked outside the package root
- required tools or access references bypass Tool/Access owner module ids
- the target source is readonly/system

Quarantined packages may be indexed for diagnostics but must not become
model-visible and must not be expanded into Context Workspace runtime slices.

## Runtime Visibility

Only active packages from enabled sources can become model-visible. Context
Workspace may render selected skill summaries and instructions according to
runtime policy, but broader external-source trust must be decided by Skills
owner state before rendering.
