import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def find_local_repo_cli_executable() -> Path | None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir / "GW2-Elite-Insights-Parser"
    project_output_candidates = [
        script_dir / "GW2EICLI" / "GuildWars2EliteInsights-CLI.exe",
        repo_root / "GW2EI.bin" / "Debug" / "CLI" / "GuildWars2EliteInsights-CLI.exe",
        repo_root / "GW2EI.bin" / "Release" / "CLI" / "GuildWars2EliteInsights-CLI.exe",
        repo_root / "GW2EI.bin" / "NoRewards" / "CLI" / "GuildWars2EliteInsights-CLI.exe",
        repo_root / "GW2EIParserCLI" / "bin" / "Debug" / "net8.0" / "GuildWars2EliteInsights-CLI.exe",
        repo_root / "GW2EIParserCLI" / "bin" / "Release" / "net8.0" / "GuildWars2EliteInsights-CLI.exe",
        repo_root / "GW2EIParser" / "bin" / "Debug" / "net8.0" / "GuildWars2EliteInsights.exe",
        repo_root / "GW2EIParser" / "bin" / "Release" / "net8.0" / "GuildWars2EliteInsights.exe",
    ]
    for candidate in project_output_candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def find_cli_executable() -> Path:
    env_path = os.environ.get("ELITE_INSIGHTS_CLI_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate.resolve()

    local_repo_candidate = find_local_repo_cli_executable()
    if local_repo_candidate is not None:
        return local_repo_candidate

    candidates = [
        Path("GuildWars2EliteInsights-CLI.exe"),
        Path("GuildWars2EliteInsights.exe"),
        Path("./GuildWars2EliteInsights-CLI.exe"),
        Path("./GuildWars2EliteInsights.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    for part in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(part) / "GuildWars2EliteInsights-CLI.exe"
        if candidate.exists():
            return candidate.resolve()
        candidate = Path(part) / "GuildWars2EliteInsights.exe"
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find GuildWars2EliteInsights-CLI.exe or GuildWars2EliteInsights.exe. "
        "Build or place the CLI executable in GW2-Elite-Insights-Parser/GW2EI.bin/<Configuration>/CLI/ or pass --ei-cli. "
        "You can also set ELITE_INSIGHTS_CLI_PATH to the executable path."
    )


def write_temp_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_text = """
SaveAtOut=true
OutLocation=.
SaveOutJSON=true
IndentJSON=true
SaveOutXML=false
CompressRaw=false
ParseMultipleLogs=false
SkipFailedTries=true
"""
    config_path.write_text(config_text.strip() + "\n", encoding="utf-8")


def extract_generated_html_paths(output: str, out_dir: Path) -> list[Path]:
    html_paths = []
    for line in output.splitlines():
        if line.strip().startswith("Generated:"):
            path_str = line.split("Generated:", 1)[1].strip()
            if path_str.lower().endswith(".html"):
                candidate = Path(path_str)
                if not candidate.exists():
                    candidate = out_dir / path_str
                if candidate.exists():
                    html_paths.append(candidate.resolve())
    return html_paths


def parse_html_report(html_path: Path) -> dict:
    text = html_path.read_text(encoding="utf-8", errors="ignore")

    def extract_json(marker: str, end_marker: str) -> dict | None:
        start = text.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = text.find(end_marker, start)
        if end == -1:
            return None
        json_text = text[start:end].strip()
        if json_text.endswith(";"):
            json_text = json_text[:-1]
        return json.loads(json_text)

    log_data = extract_json("const _logData = ", "const _crData =")
    if log_data is None:
        raise ValueError("Could not find embedded _logData in HTML report")

    graph_data = extract_json("const _graphData = ", "const _healingStatsExtension =")

    boss = log_data.get("logName")
    if boss is None and log_data.get("targets"):
        boss = log_data["targets"][0].get("name")

    fight_duration = None
    total_times_downed = 0
    total_times_died = 0
    defensive_stats = {}
    if log_data.get("phases"):
        first_phase = log_data["phases"][0]
        fight_duration = first_phase.get("duration")
        def_stats = first_phase.get("defStats", [])
        if def_stats and log_data.get("players"):
            for idx, def_row in enumerate(def_stats):
                if idx >= len(log_data["players"]):
                    break
                player_name = log_data["players"][idx].get("name")
                if not player_name or not isinstance(def_row, list):
                    continue
                def get_int(index: int) -> int:
                    if index >= len(def_row):
                        return 0
                    value = def_row[index]
                    if isinstance(value, (int, float)):
                        return int(value)
                    if isinstance(value, str) and value.isdigit():
                        return int(value)
                    return 0

                times_downed = get_int(12)
                times_died = get_int(14)
                defensive_stats[player_name] = {
                    "timesDowned": times_downed,
                    "timesDied": times_died,
                }
                total_times_downed += times_downed
                total_times_died += times_died

    top_dmg = None
    top_cc = None
    if graph_data and log_data.get("players"):
        phase_players = graph_data.get("phases", [])[0].get("players", []) if graph_data.get("phases") else []

        def final_value(value):
            if isinstance(value, list) and value:
                return value[-1]
            return value or 0

        best_dmg = -1
        best_cc = -1
        for idx, phase_player in enumerate(phase_players):
            name = None
            if idx < len(log_data["players"]):
                name = log_data["players"][idx].get("name")
            damage_total = final_value(phase_player.get("damage", {}).get("total"))
            breakbar = phase_player.get("breakbarDamage", {}).get("targets", [])
            cc_total = 0
            for target_vals in breakbar:
                cc_total += final_value(target_vals)

            if damage_total > best_dmg:
                best_dmg = damage_total
                top_dmg = name
            if cc_total > best_cc:
                best_cc = cc_total
                top_cc = name

    result = {
        "bossName": boss,
        "fightDuration": fight_duration,
        "topDmgPlayerName": top_dmg,
        "topCcPlayerName": top_cc,
        "defensiveStats": defensive_stats,
        "totalTimesDowned": total_times_downed,
        "totalTimesDied": total_times_died,
    }
    return result


def parse_with_elite_insights(cli_path: Path, zevtc_path: Path, out_dir: Path) -> dict:
    # If an HTML report already exists next to the .zevtc, use it and skip running the CLI.
    def find_html_next_to(zevtc: Path) -> Path | None:
        parent = zevtc.parent
        if not parent.exists():
            return None
        candidates = [p for p in parent.glob("*.html") if zevtc.stem in p.name]
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0].resolve()

    existing_html = find_html_next_to(zevtc_path)
    if existing_html:
        try:
            return parse_html_report(existing_html)
        except Exception:
            # Fall back to running the CLI if parsing the existing HTML fails
            pass

    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = out_dir / "ei.conf"
    write_temp_config(cfg_path)

    args = [
        str(cli_path),
        "-c",
        str(cfg_path),
        str(zevtc_path),
    ]
    result = subprocess.run(
        args,
        cwd=out_dir,
        capture_output=True,
        text=True,
        shell=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Elite Insights CLI failed: {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )

    output = result.stdout + result.stderr
    json_objects = []
    for line in output.splitlines():
        if line.strip().startswith("Processed -"):
            _, json_text = line.split("Processed -", 1)
            try:
                payload = json.loads(json_text.strip())
                json_objects.append(payload)
            except json.JSONDecodeError:
                continue

    html_paths = extract_generated_html_paths(output, out_dir)
    html_data = None
    for html_path in html_paths:
        try:
            html_data = parse_html_report(html_path)
            break
        except Exception:
            continue

    if not json_objects:
        if html_data is None:
            raise RuntimeError(f"No parsed JSON output found in CLI output:\n{output}")
        return html_data

    parsed = json_objects[-1]
    if html_data:
        for key, value in html_data.items():
            if parsed.get(key) is None:
                parsed[key] = value

    return parsed


def format_duration(ms: int) -> str:
    if ms is None:
        return "<unknown>"
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    millis = ms % 1000
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def summarize_log(zevtc_path: Path, cli_path: Path, out_dir: Path) -> str:
    parsed = parse_with_elite_insights(cli_path, zevtc_path, out_dir)
    boss = parsed.get("bossName") or parsed.get("boss") or parsed.get("fileName") or "<unknown>"
    kill_time_ms = parsed.get("fightDuration") or parsed.get("duration") or parsed.get("killTime")
    top_dmg = parsed.get("topDmgPlayerName")
    top_cc = parsed.get("topCcPlayerName")
    total_downed = parsed.get("totalTimesDowned")
    total_died = parsed.get("totalTimesDied")

    parts = [f"{zevtc_path.name}: Boss={boss}"]
    if kill_time_ms is not None:
        parts.append(f"KillTime={format_duration(int(kill_time_ms))}")
    else:
        parts.append("KillTime=<unknown>")
    if top_dmg:
        parts.append(f"TopDmg={top_dmg}")
    if top_cc:
        parts.append(f"TopCC={top_cc}")
    if total_downed is not None:
        parts.append(f"TotalDowned={total_downed}")
    if total_died is not None:
        parts.append(f"TotalDied={total_died}")
    return ", ".join(parts)


def find_zevtc_files(paths):
    result = []
    for path in paths:
        p = Path(path)
        if p.is_dir():
            result.extend(sorted(p.glob("*.zevtc")))
        elif p.exists():
            result.append(p)
    return result


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
        print("Warning: No Discord token provided. The bot will only print summaries to the console.")
        args.print_only = True
    paths = find_zevtc_files(args.paths)
    if not paths:
        print("No log files found.")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cli_path = Path(args.ei_cli) if args.ei_cli else None
    if cli_path is None:
        try:
            cli_path = find_cli_executable()
        except FileNotFoundError as exc:
            print(exc)
            return 1
    elif not cli_path.exists():
        print(f"Specified EI CLI path does not exist: {cli_path}")
        return 1

    summaries = []
    for path in paths:
        abs_path = Path(__file__).parent / path
        try:
            summary = summarize_log(abs_path, cli_path, out_dir)
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
