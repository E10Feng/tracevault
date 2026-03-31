from __future__ import annotations
import argparse
import json
import os
import sys


def cmd_serve(args):
    import uvicorn
    from .server.app import app, get_storage, get_secret
    import tracevault.server.app as server_app

    server_app._default_db_path = args.db
    server_app._default_secret = os.environ.get("TRACEVAULT_SECRET", "test-secret")

    uvicorn.run(app, host="0.0.0.0", port=args.port)


def cmd_verify(args):
    from .storage import TraceStorage
    from .chain import verify_chain

    secret = os.environ.get("TRACEVAULT_SECRET", "test-secret")
    storage = TraceStorage(args.db)
    entries = storage.get_entries(args.session_id)

    if not entries:
        print(f"No entries found for session: {args.session_id}")
        sys.exit(1)

    valid, broken_at = verify_chain(entries, secret)
    if valid:
        print(f"Chain valid: True ({len(entries)} entries)")
    else:
        print(f"Chain valid: False (broken at step {broken_at})")
        sys.exit(1)


def cmd_export(args):
    import csv
    import io
    from .storage import TraceStorage

    storage = TraceStorage(args.db)
    session = storage.get_session(args.session_id)

    if session is None:
        print(f"Session not found: {args.session_id}")
        sys.exit(1)

    entries = storage.get_entries(args.session_id)

    if args.format == "json":
        data = {
            "session_id": session.session_id,
            "agent_name": session.agent_name,
            "created_at": session.created_at,
            "metadata": session.metadata,
            "entries": [e.model_dump() for e in entries],
        }
        print(json.dumps(data, indent=2))
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "session_id", "entry_id", "step_index", "entry_type",
            "summary", "hmac_hash", "prev_hash", "created_at", "payload"
        ])
        for entry in entries:
            writer.writerow([
                entry.session_id,
                entry.id,
                entry.step_index,
                entry.entry_type,
                entry.summary or "",
                entry.hmac_hash,
                entry.prev_hash,
                entry.created_at,
                json.dumps(entry.payload),
            ])
        output.seek(0)
        print(output.getvalue())


def main():
    parser = argparse.ArgumentParser(
        prog="tracevault",
        description="TraceVault - tamper-proof audit trails for LangChain agents",
    )
    parser.add_argument("--db", default="tracevault.db", help="SQLite database path")

    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the TraceVault server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_parser.add_argument("--db", default="tracevault.db", help="SQLite database path")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify a session chain")
    verify_parser.add_argument("session_id", help="Session ID to verify")
    verify_parser.add_argument("--db", default="tracevault.db", help="SQLite database path")

    # export
    export_parser = subparsers.add_parser("export", help="Export a session")
    export_parser.add_argument("session_id", help="Session ID to export")
    export_parser.add_argument(
        "--format", choices=["json", "csv"], default="json", help="Export format"
    )
    export_parser.add_argument("--db", default="tracevault.db", help="SQLite database path")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
