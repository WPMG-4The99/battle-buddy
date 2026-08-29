"""Windowed Windows entry. Same as `python -m battlebuddy ui`. No account."""

from battlebuddy.ui.app import run_ui


def main() -> None:
    raise SystemExit(run_ui())


if __name__ == "__main__":
    main()
