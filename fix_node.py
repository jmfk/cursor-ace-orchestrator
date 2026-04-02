#!/usr/bin/env python3
"""
Utility script to manually fix stuck or problematic nodes in the hierarchical planner.

Usage:
    python fix_node.py <node_id> --actionable false --description "New description"
    python fix_node.py <node_id> --reset-retry
    python fix_node.py <node_id> --info
"""

import argparse
import sys
from pathlib import Path
from ruamel.yaml import YAML

NODES_DIR = Path(".rolf/plans/nodes")


def load_node(node_id: str):
    """Load a node from its YAML file."""
    node_file = NODES_DIR / f"{node_id}.yaml"
    if not node_file.exists():
        print(f"❌ Node file not found: {node_file}")
        sys.exit(1)

    yaml = YAML()
    with open(node_file, "r") as f:
        return yaml.load(f), node_file


def save_node(node_data, node_file):
    """Save a node to its YAML file."""
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(node_file, "w") as f:
        yaml.dump(node_data, f)
    print(f"✅ Node saved: {node_file}")


def show_node_info(node_id: str):
    """Display information about a node."""
    node_data, _ = load_node(node_id)
    print(f"\n📋 Node {node_id} Information:")
    print(f"  Title: {node_data.get('title', 'N/A')}")
    print(f"  Depth: {node_data.get('depth', 'N/A')}")
    print(f"  Status: {node_data.get('status', 'N/A')}")
    print(f"  Actionable: {node_data.get('actionable', 'N/A')}")
    print(f"  Retry Count: {node_data.get('retry_count', 0)}")
    print(f"  Description: {node_data.get('description', 'N/A')}")
    print(f"  Reasoning: {node_data.get('reasoning', 'N/A')}")
    print(f"  Children: {len(node_data.get('children', []))}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Fix or inspect hierarchical planner nodes"
    )
    parser.add_argument("node_id", help="Node ID (e.g., 0011)")
    parser.add_argument(
        "--actionable",
        choices=["true", "false"],
        help="Set actionable status",
    )
    parser.add_argument(
        "--description",
        type=str,
        help="Set node description",
    )
    parser.add_argument(
        "--reasoning",
        type=str,
        help="Set node reasoning",
    )
    parser.add_argument(
        "--reset-retry",
        action="store_true",
        help="Reset retry_count to 0",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Display node information",
    )

    args = parser.parse_args()

    if args.info:
        show_node_info(args.node_id)
        return

    node_data, node_file = load_node(args.node_id)
    modified = False

    if args.actionable is not None:
        actionable_val = args.actionable == "true"
        node_data["actionable"] = actionable_val
        print(f"  ✏️  Set actionable = {actionable_val}")
        modified = True

    if args.description is not None:
        node_data["description"] = args.description
        print(f"  ✏️  Set description = {args.description}")
        modified = True

    if args.reasoning is not None:
        node_data["reasoning"] = args.reasoning
        print(f"  ✏️  Set reasoning = {args.reasoning}")
        modified = True

    if args.reset_retry:
        node_data["retry_count"] = 0
        print(f"  ✏️  Reset retry_count = 0")
        modified = True

    if modified:
        save_node(node_data, node_file)
    else:
        print("⚠️  No changes specified. Use --help for usage.")
        show_node_info(args.node_id)


if __name__ == "__main__":
    main()
