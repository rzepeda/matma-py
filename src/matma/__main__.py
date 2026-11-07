"""Enable `python -m matma` as an alternative to the console script."""

from matma.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
