#!/usr/bin/env python3
"""
Post-edit hook: Tracks modified files and invalidates dependent verification layers.
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
    file_path = tool_input.get("file_path", "")

    if not file_path.endswith(".rs"):
        return

    state = load_state()

    # Track modified file
    if file_path not in state.get("files", []):
        if "files" not in state:
            state["files"] = []
        state["files"].append(file_path)

    # Invalidate downstream gates when code changes
    invalidated = []
    implementation_gates = ["implementation", "static-analysis", "formal-verification",
                           "dynamic-analysis", "review", "safety-case"]

    for gate in implementation_gates:
        if gate in state.get("gates_passed", []):
            state["gates_passed"].remove(gate)
            invalidated.append(gate)

    save_state(state)

    messages = []
    messages.append(f"Tracking {os.path.basename(file_path)} ({len(state['files'])} files modified)")

    if invalidated:
        messages.append(f"Invalidated gates: {', '.join(invalidated)}")

    result = {
        "message": "[Swiss Cheese] " + " | ".join(messages)
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
