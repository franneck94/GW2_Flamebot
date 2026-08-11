from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any


class DefensiveStatsColumn(IntEnum):
    TIMES_DOWNED = 12
    TIMES_DIED = 14


class OffensiveStatsColumn(IntEnum):
    POWER_HITS = 20
    POWER_HITS_ABOVE_90 = 21
    CONDITION_HITS = 22
    CONDITION_HITS_ABOVE_90 = 23


class DpsStatsColumn(IntEnum):
    TOTAL_DAMAGE = 0
    POWER_DAMAGE = 1
    CONDITION_DAMAGE = 2
    BREAKBAR_DAMAGE = 3


QUICKNESS_ID = 1187
ALACRITY_ID = 30328


def get_int(index: int, def_row: list) -> int:
    if index >= len(def_row):
        return 0
    value = def_row[index]
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _power_above_90(stats: list) -> float | None:
    total_index = OffensiveStatsColumn.POWER_HITS
    above_90_index = OffensiveStatsColumn.POWER_HITS_ABOVE_90
    if len(stats) <= above_90_index or not stats[total_index]:
        return None
    return stats[above_90_index] / stats[total_index] * 100


def _generation(gen_stats: list, idx: int, boon_index: int) -> float | None:
    if boon_index < 0 or idx >= len(gen_stats):
        return None
    data = gen_stats[idx].get("data", [])
    return data[boon_index][0] if boon_index < len(data) else None


@dataclass
class PlayerStats:
    name: str
    group: Any
    dps: float
    breakbar: int
    quickness: float | None
    alacrity: float | None
    above_90_target: float | None
    above_90_all: float | None
    is_heal: bool

    @property
    def above_90(self) -> float | None:
        if self.above_90_target is not None:
            return self.above_90_target
        return self.above_90_all


def build_player_stats(log_data: dict[str, Any]) -> list[PlayerStats]:
    """Per-player values as the Elite Insights tables render them."""
    phase = (log_data.get("phases") or [{}])[0]
    players = log_data.get("players") or []
    duration_s = (phase.get("duration") or 0) / 1000
    boon_ids = log_data.get("boons") or []
    gen_self = phase.get("buffsStatContainer", {}).get("boonGenActiveSelfStats", [])
    dps_stats = phase.get("dpsStats") or []
    target_stats = phase.get("offensiveStatsTargets") or []
    all_stats = phase.get("offensiveStats") or []

    quick_index = boon_ids.index(QUICKNESS_ID) if QUICKNESS_ID in boon_ids else -1
    alac_index = boon_ids.index(ALACRITY_ID) if ALACRITY_ID in boon_ids else -1

    rows: list[PlayerStats] = []
    for idx, player in enumerate(players):
        name = player.get("name")
        if not name:
            continue
        dps_row = dps_stats[idx] if idx < len(dps_stats) else []
        total_damage = get_int(DpsStatsColumn.TOTAL_DAMAGE, dps_row)
        target_row = (
            target_stats[idx][0]
            if idx < len(target_stats) and target_stats[idx]
            else None
        )
        rows.append(
            PlayerStats(
                name=name,
                group=player.get("group"),
                dps=total_damage / duration_s if duration_s else 0.0,
                breakbar=get_int(DpsStatsColumn.BREAKBAR_DAMAGE, dps_row),
                quickness=_generation(gen_self, idx, quick_index),
                alacrity=_generation(gen_self, idx, alac_index),
                above_90_target=_power_above_90(target_row) if target_row else None,
                above_90_all=(
                    _power_above_90(all_stats[idx]) if idx < len(all_stats) else None
                ),
                is_heal=bool(player.get("heal")),
            )
        )
    return rows


def get_html_report_data(
    log_data: dict[str, Any],
    graph_data: dict[str, Any] | None,
) -> dict[str, Any]:
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

                times_downed = get_int(DefensiveStatsColumn.TIMES_DOWNED, def_row)
                times_died = get_int(DefensiveStatsColumn.TIMES_DIED, def_row)
                defensive_stats[player_name] = {
                    "timesDowned": times_downed,
                    "timesDied": times_died,
                }
                total_times_downed += times_downed
                total_times_died += times_died

    top_dmg = None
    top_cc = None
    bottom_dmg = None
    bottom_cc = None
    top_dps_value = None
    top_cc_value = None
    bottom_dps_value = None
    bottom_cc_value = None
    boon_providers: dict[str, dict[str, Any]] = {"quickness": {}, "alacrity": {}}
    boon_dps: list[str] = []
    boon_heal: list[str] = []
    lowest_writ_uptime = None

    player_stats = build_player_stats(log_data)
    if player_stats:
        groups = sorted({row.group for row in player_stats if row.group is not None})
        for boon_name in ("quickness", "alacrity"):
            for group in groups:
                candidates = [
                    row
                    for row in player_stats
                    if row.group == group and getattr(row, boon_name) is not None
                ]
                if not candidates:
                    continue
                best = max(candidates, key=lambda row: getattr(row, boon_name))
                boon_providers[boon_name][str(group)] = {
                    "name": best.name,
                    "percentage": getattr(best, boon_name),
                    "isHeal": best.is_heal,
                }
                (boon_heal if best.is_heal else boon_dps).append(best.name)

        healer_names = set(boon_heal)

        top = max(player_stats, key=lambda row: row.dps)
        top_dmg, top_dps_value = top.name, top.dps

        top_breakbar = max(player_stats, key=lambda row: row.breakbar)
        top_cc, top_cc_value = top_breakbar.name, top_breakbar.breakbar

        bottom_breakbar = min(player_stats, key=lambda row: row.breakbar)
        bottom_cc, bottom_cc_value = bottom_breakbar.name, bottom_breakbar.breakbar

        eligible_damage = [row for row in player_stats if row.name not in healer_names]
        if eligible_damage:
            bottom = min(eligible_damage, key=lambda row: row.dps)
            bottom_dmg, bottom_dps_value = bottom.name, bottom.dps

        writ_candidates = [
            (row.name, row.above_90) for row in player_stats if row.above_90 is not None
        ]
        if writ_candidates:
            lowest_writ_uptime = min(writ_candidates, key=lambda item: item[1])

    result = {
        "bossName": boss,
        "fightDuration": fight_duration,
        "topDmg": top_dmg,
        "topDps": top_dps_value,
        "topCc": top_cc,
        "topCcValue": top_cc_value,
        "bottomDmg": bottom_dmg,
        "bottomDps": bottom_dps_value,
        "bottomCc": bottom_cc,
        "bottomCcValue": bottom_cc_value,
        "playerStats": [
            {**asdict(row), "above90": row.above_90} for row in player_stats
        ],
        "defensiveStats": defensive_stats,
        "totalTimesDowned": total_times_downed,
        "totalTimesDied": total_times_died,
        "boonProviders": boon_providers,
        "boonDps": sorted(set(boon_dps)),
        "boonHeal": sorted(set(boon_heal)),
        "lowestWritUptime": lowest_writ_uptime,
    }
    return result


def format_duration(ms: int) -> str:
    if ms is None:
        return "<unknown>"
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    millis = ms % 1000
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _percent(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "-"


def format_player_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    header = (
        f"{'Sub':>3}  {'Name':<22} {'DPS':>8} {'Breakbar':>9} "
        f"{'Quick%':>8} {'Alac%':>8} {'>90%':>8}  heal"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.get('group', ''):>3}  {row.get('name', ''):<22} "
            f"{row.get('dps') or 0:>8,.0f} {row.get('breakbar') or 0:>9,.0f} "
            f"{_percent(row.get('quickness')):>8} {_percent(row.get('alacrity')):>8} "
            f"{_percent(row.get('above90')):>8}  "
            f"{'yes' if row.get('is_heal') else ''}"
        )
    return "\n".join(lines)


def _get_and_add_value(parsed: dict[str, Any], key: str, parts: list[str]):
    value = parsed.get(key)
    if value is not None:
        parts.append(f"{key}={value}")


def _get_and_add_stat(
    parsed: dict[str, Any], name_key: str, value_key: str, parts: list[str]
) -> None:
    name = parsed.get(name_key)
    value = parsed.get(value_key)
    if name is not None and value is not None:
        parts.append(f"{name_key}={name} ({value:,.0f})")
    elif name is not None:
        parts.append(f"{name_key}={name}")


def _get_and_add_damage_stat(
    parsed: dict[str, Any], name_key: str, dps_key: str, parts: list[str]
) -> None:
    name = parsed.get(name_key)
    dps = parsed.get(dps_key)
    if name is not None and dps is not None:
        parts.append(f"{name_key}={name} ({dps:,.0f} DPS)")
    elif name is not None:
        parts.append(f"{name_key}={name}")


def summarize_log(parsed: dict[str, Any]) -> str:
    boss = (
        parsed.get("bossName")
        or parsed.get("boss")
        or parsed.get("fileName")
        or "<unknown>"
    )
    kill_time_ms = (
        parsed.get("fightDuration") or parsed.get("duration") or parsed.get("killTime")
    )

    parts = [f"Boss={boss}"]
    if kill_time_ms is not None:
        parts.append(f"KillTime={format_duration(int(kill_time_ms))}")
    else:
        parts.append("KillTime=<unknown>")

    _get_and_add_value(parsed, "totalTimesDowned", parts)
    _get_and_add_value(parsed, "totalTimesDied", parts)
    _get_and_add_value(parsed, "boonDps", parts)
    _get_and_add_value(parsed, "boonHeal", parts)

    table = format_player_table(parsed.get("playerStats") or [])
    if table:
        parts.append("")
        parts.append(table)

    return "\n".join(parts)
