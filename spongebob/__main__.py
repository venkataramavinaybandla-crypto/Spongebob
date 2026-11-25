from __future__ import annotations

import argparse
from collections.abc import Sequence

from spongebob import __version__


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point for Spongebob (Network Impairment Simulator)."""
    parser = argparse.ArgumentParser(
        prog="spongebob",
        description="Spongebob — Network Impairment Simulator for delay, jitter, and packet loss.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"spongebob {__version__}",
    )
    parser.parse_args(argv)

    from spongebob.ui.app import SimulatorApp

    SimulatorApp().run()


if __name__ == "__main__":
    main()
