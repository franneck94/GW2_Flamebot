import re
from dataclasses import dataclass
from typing import Callable

from .convert import download_html_report
from .data import summarize_log


_DPS_REPORT_URL = re.compile(
    r"https?://(?:www\.)?dps\.report/[A-Za-z0-9][A-Za-z0-9_-]*",
    re.IGNORECASE,
)


@dataclass
class ReportSummary:
    url: str
    text: str
    error: str | None = None


def extract_dps_report_urls(lines: list[str]) -> list[str]:
    """Return unique dps.report links in message order."""
    urls = []
    seen = set()
    for line in lines:
        for match in _DPS_REPORT_URL.finditer(line):
            url = match.group(0)
            key = url.casefold()
            if key not in seen:
                seen.add(key)
                urls.append(url)
    return urls


def summarize_dps_report_urls(
    urls: list[str],
    loader: Callable[[str], dict] = download_html_report,
) -> list[ReportSummary]:
    """Download and summarize reports sequentially, preserving input order."""
    summaries = []
    for url in urls:
        print("[DEBUG] Downloading and summarizing report:", url)
        try:
            summaries.append(ReportSummary(url=url, text=summarize_log(loader(url))))
        except Exception as exc:
            summaries.append(ReportSummary(url=url, text="", error=str(exc)))
    return summaries


def summarize_discord_message(
    lines: list[str],
    loader: Callable[[str], dict] = download_html_report,
) -> list[ReportSummary]:
    urls = extract_dps_report_urls(lines)
    return summarize_dps_report_urls(urls, loader)
