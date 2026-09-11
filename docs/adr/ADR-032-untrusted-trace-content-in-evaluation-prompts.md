# ADR-032 — Untrusted Trace Content in Evaluation Prompts

Status: Accepted

## Context

Retrieved documents, tool outputs, questions, and model answers can contain
text that attempts to override evaluator instructions or exfiltrate secrets.

## Decision

The judge boundary treats all trace content as structured untrusted evidence.
It uses a fixed instruction prohibiting instruction-following, tools, URLs,
configuration disclosure, and criteria changes. Evidence is minimal and bounded;
truncation is explicit. No raw prompt or chain-of-thought is persisted.

## Consequences

Prompt-injection text remains inspectable as data in the bounded request but
cannot change core evaluator policy. Provider adapters must preserve this
boundary and may not turn tenant-provided endpoints into network calls.
