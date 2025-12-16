---
description: Request to skip a layer with justification (requires proof of inapplicability)
arguments:
  - name: layer
    description: Layer to skip (e.g., formal-verification)
    required: true
  - name: reason
    description: Justification for skipping
    required: true
---

You are processing a request to skip layer **{{layer}}** in the Swiss Cheese verification.

## Skip Request

**Layer**: {{layer}}
**Justification**: {{reason}}

## Validation Rules

Layers can only be skipped with valid justification:

### Formal Verification (Layer 6)
**Can skip if**:
- No `unsafe` blocks in codebase
- No safety-critical invariants
- Project is not safety-critical (e.g., internal tooling)
- Tools not available for target platform

**Cannot skip if**:
- Contains `unsafe` code
- Handles user input directly
- Security-critical functionality

### Dynamic Analysis (Layer 7)
**Can skip if**:
- Pure library with no I/O
- Comprehensive unit test coverage (>95%)
- No async or concurrent code

**Cannot skip if**:
- Network or file I/O
- Concurrent/parallel code
- User-facing application

### Other Layers
Layers 1-5 and 8-9 generally **cannot be skipped** as they form the core verification chain.

## Decision Process

1. Verify the layer is one that can potentially be skipped
2. Evaluate the justification against the criteria above
3. Check the codebase to validate claims (e.g., search for `unsafe`)
4. Make a decision:

**If APPROVED**:
- Add layer to `skipped_gates` in state file
- Document the justification
- Proceed to next layer

**If DENIED**:
- Explain why the skip cannot be approved
- Provide guidance on what's needed to pass the gate
- Suggest alternatives if applicable

## Evaluate Now

Analyze the codebase and the provided justification to make a decision on this skip request.
