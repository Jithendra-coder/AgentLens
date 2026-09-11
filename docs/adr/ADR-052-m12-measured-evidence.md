# ADR-052: M12 uses measured, bounded evidence

M12 performance and reliability artifacts record raw successful samples,
failures, environment, configuration, and methodology. Missing workload
coverage is labelled unavailable instead of being estimated. This keeps local
measurements reproducible without turning them into production capacity claims.
