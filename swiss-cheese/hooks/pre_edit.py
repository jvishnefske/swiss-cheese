#!/usr/bin/env python3
"""
Pre-edit hook: Validates Rust code changes against safety requirements.
Warns about unsafe patterns and enforces layer constraints.
"""
import json
import sys
import os

STATE_FILE = "/tmp/swiss_cheese_state.json"

UNSAFE_PATTERNS = [
    ("unsafe", "Contains `unsafe` block - requires Layer 5 (static analysis) review"),
    ("*const", "Contains raw pointer (*const) - verify memory safety"),
    ("*mut", "Contains mutable raw pointer (*mut) - high risk pattern"),
    ("transmute", "Contains transmute - Layer 6 (formal verification) required"),
    ('extern "C"', "Contains FFI - verify ABI compatibility"),
    (".unwrap()", "Contains unwrap() - consider ? operator or proper error handling"),
    ("panic!", "Contains panic! - verify this is intentional for safety-critical code"),
    ("todo!", "Contains todo! - incomplete implementation"),
    ("unimplemented!", "Contains unimplemented! - incomplete implementation"),
]


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"layer": None, "files": [], "gates_passed": []}


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Only check Rust files
    if not file_path.endswith(".rs"):
        return

    state = load_state()
    new_content = tool_input.get("content", "") or tool_input.get("new_string", "")

    warnings = []
    blockers = []

    # Check for unsafe patterns
    for pattern, message in UNSAFE_PATTERNS:
        if pattern in new_content:
            warnings.append(message)

    # Layer-specific enforcement
    current_layer = state.get("layer")
    if current_layer:
        if current_layer == "requirements" and new_content:
            blockers.append("Layer 1 (Requirements): Should not be writing code yet")
        elif current_layer == "architecture" and "impl " in new_content:
            blockers.append("Layer 2 (Architecture): Should not implement yet, only define types/traits")
        elif current_layer == "tdd" and "impl " in new_content and "#[test]" not in new_content:
            warnings.append("Layer 3 (TDD): Write tests before implementation")

    # Output result
    if blockers:
        result = {
            "decision": "block",
            "reason": f"[Swiss Cheese] Blocked:\n" + "\n".join(f"  - {b}" for b in blockers)
        }
        print(json.dumps(result))
        sys.exit(1)
    elif warnings:
        result = {
            "message": f"[Swiss Cheese] Safety warnings for {os.path.basename(file_path)}:\n" +
                      "\n".join(f"  - {w}" for w in warnings)
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
