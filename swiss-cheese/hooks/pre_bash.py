#!/usr/bin/env python3
"""
Pre-bash hook: Monitors CI/build commands and tracks verification state.
"""
import json
import sys
import os

STATE_FILE = "/tmp/swiss_cheese_state.json"


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"layer": None, "files": [], "gates_passed": [], "ci_runs": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    state = load_state()

    # Track verification commands
    verification_commands = {
        "cargo test": "tdd",
        "cargo clippy": "static-analysis",
        "cargo audit": "static-analysis",
        "cargo deny": "static-analysis",
        "cargo miri": "dynamic-analysis",
        "cargo fuzz": "dynamic-analysis",
        "cargo kani": "formal-verification",
    }

    for cmd, layer in verification_commands.items():
        if cmd in command:
            if "ci_runs" not in state:
                state["ci_runs"] = []
            state["ci_runs"].append({"command": cmd, "layer": layer})
            save_state(state)

            result = {
                "message": f"[Swiss Cheese] Running {layer} verification: {cmd}"
            }
            print(json.dumps(result))
            return

    # Warn about direct cargo build without verification
    if "cargo build --release" in command:
        gates_passed = state.get("gates_passed", [])
        missing = []
        required = ["requirements", "architecture", "tdd", "implementation", "static-analysis"]
        for gate in required:
            if gate not in gates_passed:
                missing.append(gate)

        if missing:
            result = {
                "message": f"[Swiss Cheese] Warning: Release build without verification.\n"
                          f"  Missing gates: {', '.join(missing)}\n"
                          f"  Run /swiss-cheese:status to see verification state"
            }
            print(json.dumps(result))


if __name__ == "__main__":
    main()
