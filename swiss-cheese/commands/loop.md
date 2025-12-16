---
description: Start iterative refinement loop until all gates pass
---

You are starting the Swiss Cheese iterative refinement loop. This will continuously run gates and fix issues until all 9 layers pass.

## Loop Algorithm

```
while not all_gates_passed:
    for gate in [requirements, architecture, tdd, implementation,
                 static-analysis, formal-verification, dynamic-analysis,
                 review, safety-case]:

        if gate in skipped_gates:
            continue

        if gate not in passed_gates:
            result = run_gate(gate)

            if result == PASS:
                passed_gates.add(gate)
            else:
                fix_issues(result.issues)
                # Loop will retry this gate
                break  # Start over to catch regressions
```

## Execution Rules

1. **Sequential Gates**: Run gates in order (requirements → safety-case)
2. **Fix Before Proceed**: Don't skip to next gate if current fails
3. **Regression Detection**: If a file changes, re-run affected gates
4. **User Checkpoints**: Pause for user input at critical decisions
5. **Timeout**: Stop after 50 iterations to prevent infinite loops

## Gate Dependencies

```
requirements ──→ architecture ──→ tdd ──→ implementation ──┬──→ static-analysis
                                                           ├──→ formal-verification
                                                           └──→ dynamic-analysis
                                                                      ↓
                                                                   review
                                                                      ↓
                                                                 safety-case
```

## Starting the Loop

1. Read current state from `/tmp/swiss_cheese_state.json`
2. Identify first unpassed gate
3. Run that gate using the gate agent
4. If passes, continue to next
5. If fails, fix issues and retry
6. Continue until all gates pass or user cancels with `/swiss-cheese:cancel`

## Progress Tracking

After each gate attempt, update the state file and report:
- Current gate being processed
- Pass/fail status
- Issues found (if any)
- Estimated progress

Begin the loop now. Start with the first unpassed gate.
