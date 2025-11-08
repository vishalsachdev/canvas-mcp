# Architecture Decision Records (ADR)

This directory contains Architecture Decision Records (ADRs) for Canvas MCP. ADRs document significant architectural decisions made during the project's development.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences.

## Format

Each ADR follows this structure:

- **Title**: Short noun phrase
- **Status**: Proposed, Accepted, Deprecated, Superseded
- **Context**: What is the issue we're trying to solve?
- **Decision**: What decision did we make?
- **Consequences**: What are the results of this decision?

## Index

- [ADR-001: Modular Architecture](001-modular-architecture.md) - Refactor to modular structure
- [ADR-002: Data Anonymization](002-data-anonymization.md) - FERPA-compliant anonymization
- [ADR-003: Code Execution API](003-code-execution-api.md) - TypeScript code execution for bulk operations
- [ADR-004: FastMCP Framework](004-fastmcp-framework.md) - Using FastMCP for MCP server implementation

## Creating New ADRs

When making significant architectural decisions:

1. **Create a new file**: `docs/adr/NNN-decision-title.md`
2. **Use the template**: Copy from `template.md`
3. **Fill in details**: Context, decision, consequences
4. **Update index**: Add to this README
5. **Submit PR**: Include ADR with implementation

## Numbering

ADRs are numbered sequentially (001, 002, 003, etc.). The number is not changed even if the ADR is superseded.

## Status Workflow

- **Proposed**: Under consideration
- **Accepted**: Decision is approved and active
- **Deprecated**: No longer recommended but not superseded
- **Superseded**: Replaced by another ADR (link to new one)

## References

- [ADR GitHub Organization](https://adr.github.io/)
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
