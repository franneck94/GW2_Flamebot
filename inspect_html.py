from pathlib import Path
import json

text = Path("logs/20260810-221923_vg_kill.html").read_text(
    encoding="utf-8", errors="ignore"
)
marker = "const _logData = "
start = text.index(marker) + len(marker)
end = text.index("const _crData =", start)
js = text[start:end].strip()
if js.endswith(";"):
    js = js[:-1]

data = json.loads(js)
print("players", len(data["players"]))
player = data["players"][0]
print("player keys", list(player.keys()))
print("detail keys", sorted(player["details"].keys()))
for k in [
    "damage",
    "dps",
    "mechanicStats",
    "damageStats",
    "activeTimes",
    "cc",
    "combat",
    "enemyMechanicStats",
    "dmgDistributions",
]:
    if k in player["details"]:
        v = player["details"][k]
        print(
            k,
            type(v).__name__,
            v
            if isinstance(v, (int, float, str))
            else (len(v) if hasattr(v, "__len__") else type(v)),
        )
print(
    "sample mechanicStats keys",
    list(player["details"].get("mechanicStats", {}).keys())[:20],
)
