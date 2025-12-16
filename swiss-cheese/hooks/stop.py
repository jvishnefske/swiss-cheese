#!/usr/bin/env python3
"""
Stop hook: Summarizes verification state and recommends next steps.
"""
import json
import sys
import os

STATE_FILE = "/tmp/swiss_cheese_state.json"

LAYERS = [
    ("requirements", "Layer 1: Requirements"),
    ("architecture", "Layer 2: Architecture"),
    ("tdd", "Layer 3: TDD"),
    ("implementation", "Layer 4: Implementation"),
    ("static-analysis", "Layer 5: Static Analysis"),
    ("formal-verification", "Layer 6: Formal Verification"),
    ("dynamic-analysis", "Layer 7: Dynamic Analysis"),
    ("review", "Layer 8: Review"),
    ("safety-case", "Layer 9: Safety Case"),
]


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"layer": None, "files": [], "gates_passed": [], "ci_runs": []}


def main():
    state = load_state()
    files = state.get("files", [])
    gates_passed = state.get("gates_passed", [])

    if not files and not gates_passed:
        return  # No activity to report

    # Build status summary
    lines = ["[Swiss Cheese] Session Summary", ""]

    if files:
        lines.append(f"Modified Files ({len(files)}):")
        for f in files[:10]:
            lines.append(f"  - {os.path.basename(f)}")
        if len(files) > 10:
            lines.append(f"  ... and {len(files) - 10} more")
        lines.append("")

    lines.append("Verification Status:")
    next_layer = None
    for layer_id, layer_name in LAYERS:
        status = "PASS" if layer_id in gates_passed else "pending"
        marker = "[x]" if status == "PASS" else "[ ]"
        lines.append(f"  {marker} {layer_name}")
        if status == "pending" and next_layer is None:
            next_layer = layer_id

    if next_layer:
        lines.append("")
        lines.append(f"Next: /swiss-cheese:gate {next_layer}")
        lines.append("Or run all: /swiss-cheese:loop")

    result = {"message": "\n".join(lines)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
