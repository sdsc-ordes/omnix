"""SLIMS connection helpers: load credentials from `.env` and open a client."""

from os import getenv

from dotenv import load_dotenv
from slims.slims import Slims


def load_config() -> dict[str, str]:
    """Read SLIMS credentials from the environment (.env)."""
    load_dotenv()
    keys = ("SLIMS_NAME", "SLIMS_URL", "SLIMS_USER", "SLIMS_SECRET")
    config = {key: getenv(key) for key in keys}

    missing = [key for key, value in config.items() if not value]
    if missing:
        raise SystemExit(
            "Missing environment variables: "
            + ", ".join(missing)
            + "\nCopy .example.env to .env and fill in your credentials."
        )
    return config  # type: ignore[return-value]


def connect(config: dict[str, str]) -> Slims:
    """Open an authenticated connection to the SLIMS REST API."""
    return Slims(
        config["SLIMS_NAME"],
        config["SLIMS_URL"],
        config["SLIMS_USER"],
        config["SLIMS_SECRET"],
    )
