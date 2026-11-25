"""Build and validate a local synthetic Parquet snapshot."""
import argparse
import json
from pathlib import Path

from data_engineering.transformations.synthetic_lakehouse import PRESETS, build_lakehouse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=PRESETS, default="small")
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("artifacts/lakehouse") / f"{args.preset}-seed-{args.seed}"
    try:
        result = build_lakehouse(args.preset, args.seed, output)
    except (ValueError, FileExistsError) as problem:
        parser.error(str(problem))
    print(json.dumps({"output": str(output), **result}, indent=2))


if __name__ == "__main__":
    main()
