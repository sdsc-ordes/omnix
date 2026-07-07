"""Command-line entry point: fetch xenograft Content and print it readably.

Run it from inside the dev shell after copying `.example.env` to `.env`:

    uv run omnix

If a fetch dies with an ssl error, unset LD_LIBRARY_PATH first (the impure
devenv shell injects an old glibc that shadows the one `_ssl.so` needs), and
make sure you are on the EPFL VPN:

    env -u LD_LIBRARY_PATH uv run omnix

SLIMS columns have cryptic names (e.g. ``cntn_fk_status``). Each column also
carries a human-readable ``title`` ("Status"), a resolved ``displayValue``
("Available") and the raw ``value`` (10). This prints all three.
"""

import requests

from omnix.client import connect, load_config
from omnix.extract import CONTENT_TYPES, fetch_content


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


def main() -> None:
    config = load_config()
    slims = connect(config)

    try:
        for label, pk in CONTENT_TYPES.items():
            print(f"--- {label} (cntn_fk_contentType={pk}) ---\n")
            records = fetch_content(slims, pk)
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


if __name__ == "__main__":
    main()
