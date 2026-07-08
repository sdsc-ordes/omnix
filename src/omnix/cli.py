"""Command-line entry point for omnix.

Subcommands:

    omnix snapshot     Pull SLIMS -> reshape -> write the local SQLite snapshot.
    omnix serve        Launch the web app over an existing snapshot.
    omnix dump         Print raw Content records (debugging).

`snapshot` and `dump` reach your SLIMS instance over the network (connect to its
VPN first if it requires one). `serve` only reads the local snapshot file.

SLIMS columns have cryptic names (e.g. ``cntn_fk_status``). Each column also
carries a human-readable ``title`` ("Status"), a resolved ``displayValue``
("Available") and the raw ``value`` (10). `dump` prints all three.
"""

import argparse

from . import store

# `serve` reads only the local snapshot, so the SLIMS/HTTP stack (`requests`,
# `slims`, and the client/extract/snapshot modules) is imported lazily inside the
# commands that need it, rather than at module load.


def describe_record(record) -> None:
    """Print one record's non-empty columns as: Title [name] = value."""
    print(f"== {record.table_name()} (pk={record.pk()}) ==")
    for column in record.json_entity["columns"]:
        value = column.get("value")
        if value is None:
            continue

        name = column.get("name")
        title = column.get("title") or name
        display = column.get("displayValue")

        # For foreign keys, displayValue resolves the raw pk to a label.
        if display not in (None, "") and display != value:
            print(f"  {title} [{name}] = {display}  (raw: {value})")
        else:
            print(f"  {title} [{name}] = {value}")
    print()


def cmd_dump(_args) -> None:
    import requests  # noqa: PLC0415 (lazy: pulls in the ssl-dependent slims stack)

    from .client import connect, load_config  # noqa: PLC0415
    from .extract import CONTENT_TYPES, fetch_all  # noqa: PLC0415

    config = load_config()
    slims = connect(config)
    try:
        for label, pk in CONTENT_TYPES.items():
            print(f"--- {label} (cntn_fk_contentType={pk}) ---\n")
            records = fetch_all(slims, pk, limit=5)
            if not records:
                print("  (no records)\n")
                continue
            for record in records:
                describe_record(record)
    except requests.exceptions.RequestException as error:
        raise SystemExit(
            f"Could not reach SLIMS at {config['SLIMS_URL']!r}: {error}\n"
            "Check the VPN, SLIMS_URL, and SLIMS_USER / SLIMS_SECRET."
        ) from error


def cmd_snapshot(args) -> None:
    import requests  # noqa: PLC0415 (lazy: pulls in the ssl-dependent slims stack)

    from . import snapshot as snapshot_mod  # noqa: PLC0415
    from .client import load_config  # noqa: PLC0415

    config = load_config()
    try:
        counts = snapshot_mod.run(args.db, limit=args.limit)
    except requests.exceptions.RequestException as error:
        raise SystemExit(
            f"Could not reach SLIMS at {config['SLIMS_URL']!r}: {error}\n"
            "Check the VPN, SLIMS_URL, and SLIMS_USER / SLIMS_SECRET."
        ) from error
    summary = ", ".join(f"{n} {k}" for k, n in counts.items())
    print(f"Wrote snapshot to {args.db}: {summary}")


def cmd_serve(args) -> None:
    from .web.app import create_app  # noqa: PLC0415 (lazy: avoid importing Flask unless serving)

    app = create_app(args.db)
    print(f"Serving omnix on http://{args.host}:{args.port}  (snapshot: {args.db})")
    app.run(host=args.host, port=args.port, debug=args.debug)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omnix", description="SLIMS xenograft browser.")
    sub = parser.add_subparsers(dest="command")

    p_snap = sub.add_parser("snapshot", help="Pull SLIMS into the local SQLite snapshot.")
    p_snap.add_argument("--db", default=str(store.DEFAULT_DB), help="SQLite path.")
    p_snap.add_argument("--limit", type=int, default=None, help="Cap rows per content type (dev).")
    p_snap.set_defaults(func=cmd_snapshot)

    p_serve = sub.add_parser("serve", help="Run the web app over an existing snapshot.")
    p_serve.add_argument("--db", default=str(store.DEFAULT_DB), help="SQLite path.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--debug", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_dump = sub.add_parser("dump", help="Print raw Content records (debugging).")
    p_dump.set_defaults(func=cmd_dump)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
