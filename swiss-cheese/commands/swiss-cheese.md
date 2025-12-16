---
description: Start safety-critical Rust development with design review
arguments:
  - name: design_doc
    description: Path to design document (TOML or markdown)
    required: false
---

You are starting a safety-critical Rust development session using the Swiss Cheese Model.

## Swiss Cheese Model Overview

Like the NASA Swiss Cheese Model for accident prevention, this workflow uses 9 independent verification layers. Each layer catches defects that slip through previous layers - no single point of failure.

```
Layer 1: Requirements    → Formalize requirements with Rust-specific constraints
Layer 2: Architecture    → Design type-safe, ownership-correct architecture
Layer 3: TDD             → Write comprehensive tests BEFORE implementation
Layer 4: Implementation  → Implement safe Rust code to pass tests
Layer 5: Static Analysis → Run Clippy, cargo-audit, cargo-deny, unsafe audit
Layer 6: Formal Verify   → Prove properties with Kani, Prusti, Creusot
Layer 7: Dynamic Analysis→ Run Miri, fuzzing, coverage, timing analysis
Layer 8: Review          → Independent fresh-eyes review
Layer 9: Safety Case     → Assemble safety case and make release decision
```

## Your Task

{{#if design_doc}}
1. Read and analyze the design document at: {{design_doc}}
2. Validate requirements are complete and testable
3. Identify safety-critical components
4. Create a verification plan
{{else}}
1. Ask the user about their project and requirements
2. Help them create or identify a design document
3. Guide them through requirements validation
{{/if}}

## Session State

Initialize the Swiss Cheese session state by creating/updating `/tmp/swiss_cheese_state.json`:
```json
{
  "layer": "requirements",
  "files": [],
  "gates_passed": [],
  "ci_runs": [],
  "project_dir": "<current working directory>",
  "started_at": "<timestamp>"
}
```

## Next Steps

After design review, guide the user through:
1. `/swiss-cheese:gate requirements` - Validate requirements
2. `/swiss-cheese:gate architecture` - Design architecture
3. Continue through each layer...

Or use `/swiss-cheese:loop` to iterate until all gates pass.

Remember: The goal is defense in depth. Each layer should be independent and thorough.
