# AgentLens Datasets

M9 datasets are project-scoped collections of provider-neutral JSON cases. A
case stores an opaque case ID, explicit position, name, input, metadata, tags,
optional ground truth, and source provenance. Ground truth is input evidence for
future evaluation; it is not an evaluation result.

## Versions

Creating a version creates a `draft`. Draft cases may be added, edited, or
removed. Finalization computes a SHA-256 checksum over canonical JSON for the
ordered cases and changes the version to `finalized`. Finalized content,
positions, checksum, and provenance are immutable; a new version is required
for changes. Explicit positions define order, so database row order is never
used. The checksum covers ordered case content, not generated case identity, so
portable imports can receive fresh opaque IDs. Distinct case IDs permit
duplicate content intentionally.

## Trace-derived cases

The trace-to-case operation requires `trace_id`, `span_id`, `input_field`
(`input` or `output`), and a case name. It records the source trace ID,
canonical trace fingerprint, trace start timestamp, span ID, and extraction
configuration. The operation never guesses which span or field to use.

## Portable format

Finalized versions export as `agentlens-dataset-v1` JSON containing dataset and
version metadata plus ordered cases, tags, ground truth, and checksum. Imports
are validated as JSON-safe content, reject unsupported schemas, duplicate IDs,
invalid positions, and checksum mismatches, and create a reviewed draft with
fresh opaque case IDs. No imported value is executed.

Retention enforcement, branching, merging, and large-scale annotation tooling
remain deferred.
