import argparse
import os
from pathlib import Path

from src.convert import (
    find_zevtc_files,
    find_local_repo_cli_executable,
    parse_with_elite_insights,
)
from src.data import summarize_log


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GW2 arcdps EVTC summary bot")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["logs"],
        help="Files or directories to scan. Defaults to the logs directory.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print boss name and kill time to the console and exit before connecting to Discord.",
    )
    parser.add_argument(
        "--token",
        help="Discord bot token. Only used if not running in --print-only mode.",
    )
    parser.add_argument(
        "--ei-cli",
        help="Path to GuildWars2EliteInsights-CLI.exe or GuildWars2EliteInsights.exe.",
    )
    parser.add_argument(
        "--out-dir",
        default="ei_output",
        help="Output directory for Elite Insights parser files.",
    )
    return parser


async def run_discord_bot(token: str, summaries: list[str]) -> None:
    try:
        import discord
    except ImportError:
        raise RuntimeError(
            "discord.py is not installed. Install it with: python -m pip install discord.py"
        )

    class BotClient(discord.Client):
        async def on_ready(self):
            print(f"Connected to Discord as {self.user}")
            for line in summaries:
                print(line)
            await self.close()

    intents = discord.Intents.default()
    client = BotClient(intents=intents)
    await client.start(token)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.token and not args.print_only:
        print(
            "Warning: No Discord token provided. The bot will only print summaries to the console."
        )
        args.print_only = True
    paths = find_zevtc_files(args.paths)
    if not paths:
        print("No log files found.")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cli_path = Path(args.ei_cli) if args.ei_cli else None
    if cli_path is None:
        cli_path = find_local_repo_cli_executable()

    if cli_path is None or not cli_path.exists():
        print(f"Specified EI CLI path does not exist: {cli_path}")
        return 1

    summaries = []
    for path in paths:
        abs_path = Path(__file__).parent / path
        try:
            parsed = parse_with_elite_insights(cli_path, abs_path, out_dir)
            summary = summarize_log(parsed)
            summaries.append(summary)
        except Exception as exc:
            summaries.append(f"{abs_path.name}: failed to parse EVTC: {exc}")

    for line in summaries:
        print(line)

    if args.print_only:
        return 0

    token = args.token or os.environ.get("DISCORD_TOKEN")
    if not token:
        print("No Discord token provided. Set --token or DISCORD_TOKEN to connect.")
        return 1

    try:
        import asyncio

        asyncio.run(run_discord_bot(token, summaries))
    except Exception as exc:
        print(f"Discord bot failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
