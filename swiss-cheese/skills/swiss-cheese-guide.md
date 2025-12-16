---
description: Use this skill when the user asks about "Swiss Cheese Model", "safety-critical Rust", "verification layers", "how to use swiss-cheese plugin", "rust verification workflow", "9-layer verification", or needs guidance on using the Swiss Cheese verification plugin for Rust development.
---

# Swiss Cheese Model - Safety-Critical Rust Development Guide

The Swiss Cheese Model plugin implements a 9-layer verification approach for safety-critical Rust development, inspired by NASA's Swiss Cheese Model for accident prevention.

## Core Concept

Like layers of Swiss cheese, each verification layer catches defects that slip through previous layers. No single layer is perfect, but together they provide defense in depth.

## The 9 Verification Layers

### Layer 1: Requirements (`/swiss-cheese:gate requirements`)
- Formalize requirements with Rust-specific constraints
- Identify ownership, lifetime, and concurrency requirements
- Define testable acceptance criteria
- Agent: `requirements-agent`

### Layer 2: Architecture (`/swiss-cheese:gate architecture`)
- Design type-safe, ownership-correct architecture
- Define module structure and trait contracts
- Plan error handling strategy
- Agent: `architecture-agent`

### Layer 3: TDD (`/swiss-cheese:gate tdd`)
- Write comprehensive tests BEFORE implementation
- Unit tests, integration tests, property-based tests
- Tests should compile but fail (red phase)
- Agent: `tdd-agent`

### Layer 4: Implementation (`/swiss-cheese:gate implementation`)
- Implement safe Rust code to pass tests
- Minimize `unsafe` blocks
- Follow Rust idioms and API guidelines
- Agent: `implementation-agent`

### Layer 5: Static Analysis (`/swiss-cheese:gate static-analysis`)
- Run `cargo clippy -- -D warnings`
- Run `cargo audit` for vulnerabilities
- Run `cargo deny check` for licenses
- Audit all `unsafe` blocks
- Agent: `static-analysis-agent`

### Layer 6: Formal Verification (`/swiss-cheese:gate formal-verification`)
- Prove properties with Kani, Prusti, Creusot
- Model checking for critical functions
- Can be skipped if no unsafe code (use `/swiss-cheese:skip-layer`)
- Agent: `formal-verification-agent`

### Layer 7: Dynamic Analysis (`/swiss-cheese:gate dynamic-analysis`)
- Run Miri for undefined behavior detection
- Fuzzing with cargo-fuzz
- Coverage analysis (target >80%)
- Agent: `dynamic-analysis-agent`

### Layer 8: Review (`/swiss-cheese:gate review`)
- Independent fresh-eyes code review
- Security, correctness, reliability, maintainability
- Agent: `review-agent` (uses Opus model)

### Layer 9: Safety Case (`/swiss-cheese:gate safety-case`)
- Assemble all verification evidence
- Requirements traceability
- Make GO/NO-GO release decision
- Agent: `safety-agent` (uses Opus model)

## Quick Start Commands

```
/swiss-cheese              # Start a new verification session
/swiss-cheese:status       # Show current verification status
/swiss-cheese:gate <name>  # Run a specific gate
/swiss-cheese:loop         # Iterate until all gates pass
/swiss-cheese:skip-layer   # Skip a layer with justification
/swiss-cheese:cancel       # Cancel the current loop
```

## State Management

Session state is stored in `/tmp/swiss_cheese_state.json`:
```json
{
  "layer": "current-layer",
  "files": ["modified/files.rs"],
  "gates_passed": ["requirements", "architecture"],
  "ci_runs": [{"command": "cargo test", "layer": "tdd"}],
  "project_dir": "/path/to/project",
  "started_at": "2024-01-01T00:00:00"
}
```

## Hooks

The plugin includes hooks that:
- **Pre-edit**: Warn about unsafe patterns, enforce layer constraints
- **Post-edit**: Track modified files, invalidate dependent gates
- **Pre-bash**: Track verification commands
- **Stop**: Summarize session and suggest next steps

## Example Architecture Document

See `examples/example_project.toml` for a complete TOML architecture document defining:
- Project configuration
- Layer definitions
- Task dependencies
- Gate configurations
- Agent definitions

## Best Practices

1. **Don't skip layers** unless absolutely necessary
2. **Document skip decisions** with clear justification
3. **Re-run affected gates** when code changes
4. **Use the loop command** for iterative refinement
5. **Review all warnings** from hooks before proceeding
