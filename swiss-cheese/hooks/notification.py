#!/usr/bin/env python3
"""
Notification hook: Handles async notifications from verification processes.
"""
import json
import sys


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    # Pass through notifications from verification agents
    message = input_data.get("message", "")
    if message and "[Swiss Cheese]" in message:
        result = {"message": message}
        print(json.dumps(result))


if __name__ == "__main__":
    main()
