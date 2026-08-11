import argparse
import sys

from src.discord_integration import summarize_discord_message


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate a Discord message containing dps.report links."
    )
    parser.add_argument(
        "message",
        nargs="*",
        help="Message text. Reads one message from stdin when omitted.",
    )
    args = parser.parse_args()
    message = " ".join(args.message) if args.message else sys.stdin.read()
    reports = summarize_discord_message(message)

    if not reports:
        print("No dps.report links found.")
        return 1

    for index, report in enumerate(reports, start=1):
        print(f"--- Report {index}: {report.url} ---")
        if report.error:
            print(f"Failed to process report: {report.error}")
        else:
            print(report.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
