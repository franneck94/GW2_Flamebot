import requests
from pathlib import Path
import json
import subprocess
from typing import Any

from .data import get_html_report_data


def find_zevtc_files(paths):
    result = []
    for path in paths:
        p = Path(path)
        if p.is_dir():
            result.extend(sorted(p.glob("*.zevtc")))
        elif p.exists():
            result.append(p)
    return result


def find_local_repo_cli_executable() -> Path | None:
    script_dir = Path(__file__).resolve().parent.parent
    return script_dir / "GW2EICLI" / "GuildWars2EliteInsights-CLI.exe"


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


def find_html_next_to(zevtc: Path) -> Path | None:
    parent = zevtc.parent
    if not parent.exists():
        return None
    candidates = [p for p in parent.glob("*.html") if zevtc.stem in p.name]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0].resolve()


def parse_with_elite_insights(cli_path: Path, zevtc_path: Path, out_dir: Path) -> dict:
    html_path = find_html_next_to(zevtc_path)

    if not html_path:
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
        html_paths = extract_generated_html_paths(output, out_dir)
        html_path = html_paths[0] if html_paths else None

    if html_path is None:
        raise RuntimeError(
            f"No HTML report found for {zevtc_path}. CLI output:\n{output}"
        )

    html_data = parse_html_report(html_path)
    return html_data


def parse_html_report(html_path: Path) -> dict:
    text = html_path.read_text(encoding="utf-8", errors="ignore")

    def extract_json(marker: str, end_marker: str) -> dict[str, Any] | None:
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
    return get_html_report_data(log_data, graph_data)


def download_html_report(url: str) -> dict:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    html_text = response.text
    temp_path = Path("logs") / f"{url.split('/')[-1]}.html"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(html_text, encoding="utf-8", errors="ignore")

    return parse_html_report(temp_path)
