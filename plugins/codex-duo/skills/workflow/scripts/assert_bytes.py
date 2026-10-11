"""Offline byte assertion: avoid nested shell / Python source escaping."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("expected_hex", help="Expected bytes as hexadecimal, e.g. 61667465720a")
    args = parser.parse_args()
    try:
        expected = bytes.fromhex(args.expected_hex)
    except ValueError:
        parser.error("expected_hex must contain hexadecimal bytes")
    try:
        actual = args.path.read_bytes()
    except OSError as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    if actual != expected:
        parser.exit(1, f"FAIL: expected {expected.hex()}, got {actual.hex()}\n")
    print(f"PASS: {args.path} == {expected.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
