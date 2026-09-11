# Terminology

These terms are frozen for AgentLens. New competing terms require an ADR.

| Term | Definition |
| --- | --- |
| Trace | One complete logical execution/request observed by AgentLens. |
| Span | A timed operation belonging to a trace. |
| Event | A point-in-time occurrence associated with execution. |
| Evaluation | A process that analyzes observed execution data. |
| Evaluator | A versioned component that performs an evaluation. |
| Score | A numeric or categorical evaluator output. |
| Finding | A human-readable diagnostic result. |
| Dataset | A versioned collection of evaluation or replay cases. |
| Replay | Running preserved or historical cases against an execution configuration. |
| Baseline | The reference version or configuration. |
| Candidate | The version or configuration being tested. |
| Regression | A policy-significant or statistically meaningful degradation relative to the baseline. |
| Experiment | A controlled comparison involving system configurations and a dataset. |
| Quality Gate | A policy determining whether a candidate satisfies release requirements. |

Trace, Span, and Event are implemented as the M1 observed domain model. Usage
and ErrorInfo are supporting observed metadata types; Evaluation and Finding
remain derived concepts for later milestones.
