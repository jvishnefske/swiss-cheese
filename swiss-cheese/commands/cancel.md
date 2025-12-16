---
description: Cancel the current verification loop
---

You are canceling the current Swiss Cheese verification loop.

## Actions

1. Read current state from `/tmp/swiss_cheese_state.json`
2. Display final status summary
3. Preserve the state file (don't delete - user may want to resume)
4. Confirm cancellation

## Output Format

```
Swiss Cheese Loop Cancelled
===========================

Final Status:
  Passed Gates: X/9
  - requirements: PASS
  - architecture: PASS
  - tdd: PASS
  - implementation: PENDING (was in progress)
  ...

Modified Files: X files tracked
State preserved in: /tmp/swiss_cheese_state.json

To resume: /swiss-cheese:loop
To start fresh: Delete state file and run /swiss-cheese
```

## Cleanup

- Do NOT delete the state file
- Stop any running gate processes
- Clear any "in progress" markers
- Report final state to user
