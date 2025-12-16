---
description: Show current verification status across all layers
---

Read the Swiss Cheese session state from `/tmp/swiss_cheese_state.json` and display a comprehensive status report.

## Status Report Format

```
Swiss Cheese Verification Status
================================

Project: <project_dir or "Not initialized">
Started: <started_at or "N/A">

Verification Layers:
[x] Layer 1: Requirements     - PASSED
[x] Layer 2: Architecture     - PASSED
[x] Layer 3: TDD              - PASSED
[ ] Layer 4: Implementation   - PENDING  <-- Current
[ ] Layer 5: Static Analysis  - PENDING
[ ] Layer 6: Formal Verify    - SKIPPED (no unsafe code)
[ ] Layer 7: Dynamic Analysis - PENDING
[ ] Layer 8: Review           - PENDING
[ ] Layer 9: Safety Case      - PENDING

Progress: 3/9 gates passed (33%)

Modified Files (X total):
  - src/lib.rs
  - src/module.rs
  ...

CI Runs This Session:
  - cargo test (tdd)
  - cargo clippy (static-analysis)

Next Steps:
  1. Run: /swiss-cheese:gate implementation
  2. Or continue with: /swiss-cheese:loop
```

## Instructions

1. Read `/tmp/swiss_cheese_state.json`
2. If file doesn't exist, show "No active Swiss Cheese session. Start with /swiss-cheese"
3. Format and display the status report
4. Identify the next gate to run
5. Provide actionable next steps
