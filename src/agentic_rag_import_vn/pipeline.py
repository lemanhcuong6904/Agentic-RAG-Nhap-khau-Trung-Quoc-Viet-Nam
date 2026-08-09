from __future__ import annotations

import argparse

from agentic_rag_import_vn.console import make_console
from agentic_rag_import_vn.ingestion.inventory import run_inventory
from agentic_rag_import_vn.ingestion.text_extract import run_text_extraction
from agentic_rag_import_vn.processing.chunking import run_chunking
from agentic_rag_import_vn.processing.curation import run_curate_legal
from agentic_rag_import_vn.processing.vnaccs import run_vnaccs_build
from agentic_rag_import_vn.retrieval.bm25 import run_build_bm25

console = make_console()


def cmd_inventory(_: argparse.Namespace) -> None:
    outputs = run_inventory()
    console.print("[green]Inventory complete[/green]")
    console.print(f"documents: {outputs.documents_path}")
    console.print(f"registry: {outputs.registry_path}")
    console.print(f"inventory report: {outputs.inventory_report_path}")
    console.print(f"quality report: {outputs.quality_report_path}")


def cmd_extract_text(args: argparse.Namespace) -> None:
    output = run_text_extraction(limit=args.limit)
    console.print("[green]Canonical parsing complete[/green]")
    console.print(f"parsed json: {output}")


def cmd_curate_legal(_: argparse.Namespace) -> None:
    output = run_curate_legal()
    console.print("[green]Legal curation complete[/green]")
    console.print(f"curated legal pages: {output}")


def cmd_build_chunks(_: argparse.Namespace) -> None:
    output = run_chunking()
    console.print("[green]Chunking complete[/green]")
    console.print(f"chunks: {output}")


def cmd_build_bm25(_: argparse.Namespace) -> None:
    output = run_build_bm25()
    console.print("[green]BM25 index complete[/green]")
    console.print(f"index: {output}")


def cmd_build_vnaccs(_: argparse.Namespace) -> None:
    output = run_vnaccs_build()
    console.print("[green]VNACCS lookup build complete[/green]")
    console.print(f"vnaccs: {output}")


def cmd_all(args: argparse.Namespace) -> None:
    cmd_inventory(args)
    cmd_extract_text(args)
    cmd_curate_legal(args)
    cmd_build_chunks(args)
    cmd_build_bm25(args)
    cmd_build_vnaccs(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agentic RAG data pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="Scan raw data and create manifests")
    inventory.set_defaults(func=cmd_inventory)

    extract = subparsers.add_parser("extract-text", help="Extract page/sheet text from source documents")
    extract.add_argument("--limit", type=int, default=None, help="Optional document limit for smoke runs")
    extract.set_defaults(func=cmd_extract_text)

    chunks = subparsers.add_parser("build-chunks", help="Build legal text chunks with provenance")
    chunks.set_defaults(func=cmd_build_chunks)

    curate = subparsers.add_parser("curate-legal", help="Promote validated legal pages into curated zone")
    curate.set_defaults(func=cmd_curate_legal)

    bm25 = subparsers.add_parser("build-bm25", help="Build lexical retrieval index")
    bm25.set_defaults(func=cmd_build_bm25)

    vnaccs = subparsers.add_parser("build-vnaccs", help="Build structured VNACCS lookup table")
    vnaccs.set_defaults(func=cmd_build_vnaccs)

    all_cmd = subparsers.add_parser("all", help="Run all available MVP pipeline steps")
    all_cmd.add_argument("--limit", type=int, default=None, help="Optional document limit for smoke runs")
    all_cmd.set_defaults(func=cmd_all)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
