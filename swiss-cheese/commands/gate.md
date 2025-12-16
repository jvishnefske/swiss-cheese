---
description: Run a specific gate validation (exit 0=pass, exit 1=fail)
arguments:
  - name: gate_name
    description: "Gate to run: requirements, architecture, tdd, implementation, static-analysis, formal-verification, dynamic-analysis, review, safety-case"
    required: true
---

You are running the **{{gate_name}}** verification gate for the Swiss Cheese Model.

## Gate Definitions

{{#if (eq gate_name "requirements")}}
### Layer 1: Requirements Validation

**Objective**: Ensure requirements are complete, unambiguous, and testable.

**Checks**:
1. Each requirement has a unique identifier (REQ-XXX)
2. Requirements are testable (have clear acceptance criteria)
3. Rust-specific constraints are identified:
   - Memory safety requirements
   - Concurrency requirements
   - Error handling strategy
   - Performance constraints
4. Dependencies between requirements are documented
5. Safety-critical requirements are marked

**Pass Criteria**: All requirements validated, no ambiguities remain.

{{else if (eq gate_name "architecture")}}
### Layer 2: Architecture Design

**Objective**: Design type-safe, ownership-correct architecture.

**Checks**:
1. Module structure follows Rust idioms
2. Ownership model is clear (who owns what data)
3. Lifetimes are explicit where needed
4. Error types are defined
5. Public API surface is minimal
6. Traits define behavior contracts
7. No unnecessary `Arc<Mutex<>>` (design away shared state)

**Pass Criteria**: Architecture document complete, ownership model verified.

{{else if (eq gate_name "tdd")}}
### Layer 3: Test-Driven Development

**Objective**: Write comprehensive tests BEFORE implementation.

**Checks**:
1. Unit tests exist for all public functions
2. Integration tests cover module interactions
3. Property-based tests for invariants
4. Edge cases are covered
5. Error paths are tested
6. Tests are deterministic and fast

**Commands to run**:
```bash
cargo test --no-run  # Verify tests compile
```

**Pass Criteria**: All tests written and compiling (failing is expected - TDD red phase).

{{else if (eq gate_name "implementation")}}
### Layer 4: Implementation

**Objective**: Implement safe Rust code that passes all tests.

**Checks**:
1. All tests pass: `cargo test`
2. No compiler warnings: `cargo build 2>&1 | grep -c warning` = 0
3. Code follows Rust idioms
4. `unsafe` blocks are minimized and documented
5. Error handling uses `Result<T, E>` properly

**Commands to run**:
```bash
cargo test
cargo build --release
```

**Pass Criteria**: All tests pass, no warnings, clean build.

{{else if (eq gate_name "static-analysis")}}
### Layer 5: Static Analysis

**Objective**: Catch issues through static analysis tools.

**Tools to run**:
```bash
cargo clippy -- -D warnings
cargo audit
cargo deny check
cargo +nightly udeps  # Find unused dependencies
```

**Checks**:
1. Clippy passes with no warnings
2. No known vulnerabilities (cargo audit)
3. License compliance (cargo deny)
4. All `unsafe` blocks are audited and documented

**Pass Criteria**: All static analysis tools pass.

{{else if (eq gate_name "formal-verification")}}
### Layer 6: Formal Verification

**Objective**: Prove safety properties mathematically.

**Tools**:
```bash
cargo kani          # Model checking
cargo prusti        # Verification conditions
cargo creusot       # Deductive verification
```

**Checks**:
1. Critical functions have proof annotations
2. Invariants are specified and proven
3. No undefined behavior possible
4. Memory safety proven for unsafe blocks

**Note**: This layer may be skipped with `/swiss-cheese:skip-layer formal-verification` if:
- No unsafe code exists
- No safety-critical invariants
- Project is not safety-critical

**Pass Criteria**: Proofs complete or layer justifiably skipped.

{{else if (eq gate_name "dynamic-analysis")}}
### Layer 7: Dynamic Analysis

**Objective**: Find runtime issues through dynamic analysis.

**Tools to run**:
```bash
cargo +nightly miri test           # Undefined behavior detection
cargo fuzz run <target>            # Fuzzing
cargo tarpaulin --out Html         # Code coverage
```

**Checks**:
1. Miri finds no undefined behavior
2. Fuzzing runs without crashes (minimum 1 hour)
3. Code coverage > 80%
4. No memory leaks detected

**Pass Criteria**: All dynamic analysis passes, coverage targets met.

{{else if (eq gate_name "review")}}
### Layer 8: Code Review

**Objective**: Fresh-eyes independent review.

**Review Checklist**:
1. Code is readable and well-documented
2. Error messages are helpful
3. Public API is intuitive
4. No obvious logic errors
5. Security considerations addressed
6. Performance is acceptable
7. Edge cases handled

**Process**:
- Review each modified file
- Check diff against requirements
- Verify test coverage
- Document any concerns

**Pass Criteria**: Review complete, all concerns addressed.

{{else if (eq gate_name "safety-case")}}
### Layer 9: Safety Case

**Objective**: Assemble evidence and make release decision.

**Safety Case Contents**:
1. Requirements traceability matrix
2. Test coverage report
3. Static analysis results
4. Formal verification proofs (if applicable)
5. Dynamic analysis results
6. Review sign-off
7. Known limitations and mitigations
8. Release recommendation

**Decision Criteria**:
- All previous gates passed
- No unmitigated risks
- Documentation complete

**Pass Criteria**: Safety case assembled, release decision made.

{{else}}
### Unknown Gate: {{gate_name}}

Valid gates are:
- requirements
- architecture
- tdd
- implementation
- static-analysis
- formal-verification
- dynamic-analysis
- review
- safety-case

Please run with a valid gate name.
{{/if}}

## Execution

1. Run the gate checks as specified above
2. Document results
3. Update `/tmp/swiss_cheese_state.json`:
   - If PASS: Add "{{gate_name}}" to `gates_passed` array
   - If FAIL: Document what needs to be fixed

4. Report result:
   - PASS: Proceed to next gate
   - FAIL: Fix issues and re-run gate
