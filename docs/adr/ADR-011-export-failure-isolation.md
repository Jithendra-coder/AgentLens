# ADR-011 - Export Failure Isolation

Status: Accepted

## Context

Telemetry export is operational support and must not unexpectedly change host
application behavior. M2 exporters are local and synchronous; M3 owns network
ingestion.

## Decision

Exporter failures are caught, recorded as the non-sensitive `export failure`
diagnostic category, and do not break application execution. Application
exceptions always remain the exception that propagates. M2 has no strict export
mode; a future strict mode would need an explicit contract.

## Consequences

The application can continue when telemetry collection fails, while callers can
inspect diagnostics. A trace result may exist even when its exporter did not
accept it.

## Alternatives rejected

Raising exporter exceptions by default was rejected because observability must
not become an accidental application dependency.
