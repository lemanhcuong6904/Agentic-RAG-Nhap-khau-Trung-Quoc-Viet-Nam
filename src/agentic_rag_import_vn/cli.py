from __future__ import annotations

import argparse

from agentic_rag_import_vn.agents.orchestrator import answer_query
from agentic_rag_import_vn.console import make_console

console = make_console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the Agentic RAG MVP")
    parser.add_argument("query", help="User query")
    parser.add_argument("--trace", action="store_true", help="Show tool trace")
    args = parser.parse_args()
    response = answer_query(args.query)
    console.print(response.answer)
    if args.trace:
        console.print("\nTool trace")
        for item in response.tool_calls:
            console.print(item)
    if response.warnings:
        console.print("\n[yellow]Warnings[/yellow]")
        for warning in response.warnings:
            console.print(f"- {warning}")


if __name__ == "__main__":
    main()
