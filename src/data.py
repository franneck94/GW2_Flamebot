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


def get_int(index: int, def_row: list) -> int:
    if index >= len(def_row):
        return 0
    value = def_row[index]
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def final_value(value: list | float | int) -> list | float | int:
    if isinstance(value, list) and value:
        return value[-1]
    return value or 0.0


def _above_90_percentage(
    stats: list,
    total_column: OffensiveStatsColumn,
    above_90_column: OffensiveStatsColumn,
) -> float | None:
    total_index = total_column.value
    above_90_index = above_90_column.value
    if (
        total_index >= len(stats)
        or above_90_index >= len(stats)
        or not stats[total_index]
    ):
        return None
    return round(stats[above_90_index] / stats[total_index] * 100, 2)


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
    boon_providers: dict[str, dict[str, Any]] = {"quickness": {}, "alacrity": {}}
    boon_dps: list[str] = []
    boon_heal: list[str] = []
    lowest_writ_uptime = None
    if graph_data and log_data.get("players"):
        phase_players = (
            graph_data.get("phases", [])[0].get("players", [])
            if graph_data.get("phases")
            else []
        )

        best_dmg = -1
        best_cc = -1
        worst_dmg = None
        worst_cc = None
        for idx, phase_player in enumerate(phase_players):
            name = None
            if idx < len(log_data["players"]):
                name = log_data["players"][idx].get("name")
            damage_total = final_value(phase_player.get("damage", {}).get("total"))
            breakbar = phase_player.get("breakbarDamage", {}).get("targets", [])
            cc_total = 0
            for target_vals in breakbar:
                cc_total += final_value(target_vals)  # type: ignore

            if damage_total > best_dmg:  # type: ignore
                best_dmg = damage_total  # type: ignore
                top_dmg = name
            if cc_total > best_cc:
                best_cc = cc_total
                top_cc = name
            # bottom (minimum) values - include zeros as valid
            if worst_dmg is None or damage_total < worst_dmg:  # type: ignore
                worst_dmg = damage_total
                bottom_dmg = name
            if worst_cc is None or cc_total < worst_cc:
                worst_cc = cc_total
                bottom_cc = name

        phase = log_data.get("phases", [{}])[0]
        duration_ms = phase.get("duration") or 0
        players = log_data["players"]
        self_generation = phase.get("buffsStatContainer", {}).get(
            "boonGenActiveSelfStats", []
        )
        boon_ids = log_data.get("boons", [])
        for boon_name, boon_id in (("quickness", 1187), ("alacrity", 30328)):
            for group in sorted({player.get("group") for player in players}):
                candidates = []
                for idx, player in enumerate(players):
                    if player.get("group") != group or idx >= len(self_generation):
                        continue
                    data = self_generation[idx].get("data", [])
                    if boon_id not in boon_ids or boon_ids.index(boon_id) >= len(data):
                        continue
                    candidates.append(
                        (data[boon_ids.index(boon_id)][0], player["name"], idx)
                    )
                if candidates:
                    value, name, idx = max(candidates)
                    boon_providers[boon_name][str(group)] = {
                        "name": name,
                        "percentage": value,
                        "isHeal": bool(players[idx].get("heal")),
                    }
                    (boon_heal if players[idx].get("heal") else boon_dps).append(name)

        writ_candidates = []
        for idx, player in enumerate(players):
            if idx >= len(phase.get("offensiveStats", [])) or not player.get("name"):
                continue
            stats = phase["offensiveStats"][idx]
            percentages = [
                value
                for value in (
                    _above_90_percentage(
                        stats,
                        OffensiveStatsColumn.POWER_HITS,
                        OffensiveStatsColumn.POWER_HITS_ABOVE_90,
                    ),
                    _above_90_percentage(
                        stats,
                        OffensiveStatsColumn.CONDITION_HITS,
                        OffensiveStatsColumn.CONDITION_HITS_ABOVE_90,
                    ),
                )
                if value is not None
            ]
            if percentages:
                writ_candidates.append((player["name"], min(percentages)))
        if writ_candidates:
            lowest_writ_uptime = min(writ_candidates, key=lambda item: item[1])

        healer_names = set(boon_heal)
        eligible_damage = [
            (
                players[idx].get("name"),
                final_value(phase_player.get("damage", {}).get("total")),
            )
            for idx, phase_player in enumerate(phase_players)
            if idx < len(players) and players[idx].get("name") not in healer_names
        ]
        if eligible_damage:
            bottom_dmg = min(eligible_damage, key=lambda item: item[1])[0]

    result = {
        "bossName": boss,
        "fightDuration": fight_duration,
        "topDmg": top_dmg,
        "topCc": top_cc,
        "bottomDmg": bottom_dmg,
        "bottomCc": bottom_cc,
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


def _get_and_add_value(parsed: dict[str, Any], key: str, parts: list[str]):
    value = parsed.get(key)
    if value is not None:
        parts.append(f"{key}={value}")


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

    _get_and_add_value(parsed, "topDmg", parts)
    _get_and_add_value(parsed, "topCc", parts)
    _get_and_add_value(parsed, "bottomDmg", parts)
    _get_and_add_value(parsed, "bottomCc", parts)
    _get_and_add_value(parsed, "totalTimesDowned", parts)
    _get_and_add_value(parsed, "totalTimesDied", parts)

    providers = parsed.get("boonProviders", {})
    for boon_name in ("quickness", "alacrity"):
        for group, provider in providers.get(boon_name, {}).items():
            parts.append(
                f"{boon_name.title()} G{group}={provider['name']} ({provider['percentage']:.3f}%)"
            )
    _get_and_add_value(parsed, "boonDps", parts)
    _get_and_add_value(parsed, "boonHeal", parts)
    writ = parsed.get("lowestWritUptime")
    if writ:
        parts.append(f"LowestWritUptime={writ[0]} ({writ[1]:.3f}%)")

    return "\n".join(parts)
