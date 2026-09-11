# ADR-055: Recovery and observability remain bounded

Recovery scans, runtime lists, analytics windows, and benchmark workloads use
explicit finite limits. PostgreSQL remains authoritative; a Redis outage does
not trigger an unbounded scan or an unbounded in-memory queue.
