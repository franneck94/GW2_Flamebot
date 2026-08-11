import argparse

from src.discord_integration import summarize_discord_message


DEFULT_MESSAGE = """
@flamebot

10.08.2026

https://dps.report/QdXn-20260810-193601_sabir
https://dps.report/nZJZ-20260810-221922_vg
https://dps.report/XUaC-20260810-221417_xera
https://dps.report/b4aN-20260810-220803_sab
https://dps.report/qB2G-20260810-220301_gors
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate a Discord message containing dps.report links."
    )
    parser.add_argument(
        "message",
        nargs="*",
        default=DEFULT_MESSAGE,
        help="Message text. Reads one message from stdin when omitted.",
    )
    args = parser.parse_args()
    message = args.message.split("\n") if args.message else [""]
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
