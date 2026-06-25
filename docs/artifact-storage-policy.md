# Artifact Storage Policy

## Purpose

Artifacts are durable binary or large-text objects produced by runtime modules.
They are not the source of truth for owner module state. Owner modules keep their
own records and reference artifacts by id when payloads are too large or too
sensitive to inline.

## Default Rule

Runtime records should keep bounded previews, summaries, hashes, MIME metadata,
and artifact ids inline. Full payloads should move to Artifacts when they are:

- too large for model-visible replay or Operations projections
- binary, image, screenshot, OCR output, trace dump, or downloadable report data
- sensitive enough that every read must pass Authorization
- useful beyond the immediate worker process

Tool and browser outputs already follow this rule: model-visible replay receives
artifact refs and bounded previews instead of large inline payloads.

## LLM Raw Request And Response Payloads

LLM invocation rows may retain bounded request/response snapshots for debugging
and provider parity analysis. Full raw provider requests or responses must not be
stored inline by default.

If full raw LLM payload retention is enabled later, it must use Artifacts with all
of the following constraints:

- store the payload as an artifact owned by the LLM invocation or run
- keep only `artifact_id`, content hash, MIME type, byte size, and a bounded
  redacted preview in the LLM invocation record
- require Authorization for metadata, preview, original, and download reads
- apply the same redaction policy used by the LLM read model before exposing any
  preview in Operations or Workbench
- exclude full raw payload artifacts from future LLM request rendering unless a
  user-approved diagnostic tool explicitly reads them
- set retention and quota policies separately from user-facing generated files

Raw provider payload artifacts are diagnostic evidence, not session transcript
items and not prompt context.

## Retention

Artifact cleanup works on artifact ids and deletes complete artifact directories.
Production deployments should configure quotas by owner module and payload class:

- generated user files
- screenshots and browser traces
- tool large-output refs
- LLM diagnostic raw payloads, if enabled

LLM diagnostic raw payloads should have the shortest default retention window.

## Authorization

All artifact metadata, preview, original, and download reads must flow through the
Authorization owner. HTTP headers can supply a local development subject, but a
shared deployment must replace that with platform identity context rather than
bypassing artifact authorization.
