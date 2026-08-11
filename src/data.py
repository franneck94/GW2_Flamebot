from typing import Any


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

                times_downed = get_int(12, def_row)
                times_died = get_int(14, def_row)
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

    return "\n".join(parts)
