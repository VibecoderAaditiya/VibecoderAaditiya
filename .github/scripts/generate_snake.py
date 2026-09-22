#!/usr/bin/env python3
"""
Generates a custom animated SVG: a snake that crawls across a user's real
GitHub contribution graph, eating each glowing green square as it passes,
growing longer with every square it eats.

Usage: python3 generate_snake.py <github_username> <output_svg_path>

No API token needed — reads the public contributions page directly.
"""
import sys
import os
import re
import datetime
import urllib.request

CELL = 13          # px between cell centers
RADIUS = 5          # bead radius
PAD_X = 30
PAD_Y = 30
TOTAL_DUR = 42      # seconds for one full loop
MAX_TAIL = 7        # max snake segments (including head)
BURST_FRAC = 0.012  # fraction of total duration a "pop" burst lasts
FADE_FRAC = 0.02    # fraction of total duration the eaten-fade lasts

# Real GitHub green palette
LEVEL_COLORS = {
    0: "#1b2430",
    1: "#0e4429",
    2: "#046b34",
    3: "#26a641",
    4: "#39d353",
}
EATEN_COLOR = "#161b22"
BG_COLOR = "#0d1117"
SNAKE_COLOR = "#f2f2f2"
SNAKE_HEAD_COLOR = "#ffffff"
SNAKE_EYE_COLOR = "#0d1117"


def fetch_grid(username):
    url = f"https://github.com/users/{username}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    weekday_rows = []
    for r in rows:
        cells = re.findall(r'data-date="([0-9-]+)"[^>]*data-level="([0-9])"', r)
        if cells:
            weekday_rows.append(cells)

    if not weekday_rows:
        raise RuntimeError("Could not parse contribution data")

    today = datetime.date.today()
    n_weeks = len(weekday_rows[0])
    grid = []  # list of (week, weekday, date, level)
    for weekday, row in enumerate(weekday_rows):
        for week, (date_str, level) in enumerate(row):
            d = datetime.date.fromisoformat(date_str)
            if d > today:
                continue
            grid.append({"week": week, "weekday": weekday, "date": date_str, "level": int(level)})
    return grid, n_weeks, len(weekday_rows)


def boustrophedon_order(grid, n_weeks, n_days):
    by_pos = {(c["week"], c["weekday"]): c for c in grid}
    order = []
    for week in range(n_weeks):
        days = range(n_days) if week % 2 == 0 else range(n_days - 1, -1, -1)
        for day in days:
            c = by_pos.get((week, day))
            if c:
                order.append(c)
    return order


def build_svg(order, n_weeks, n_days):
    width = PAD_X * 2 + (n_weeks - 1) * CELL + CELL
    height = PAD_Y * 2 + (n_days - 1) * CELL + CELL

    def xy(cell):
        x = PAD_X + cell["week"] * CELL
        y = PAD_Y + cell["weekday"] * CELL
        return x, y

    n = len(order)
    times = [round(i / (n - 1), 5) for i in range(n)]

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Segoe UI, sans-serif">'
    )
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="{BG_COLOR}"/>')

    svg.append(
        '<defs>'
        '<filter id="glow" x="-100%" y="-100%" width="300%" height="300%">'
        '<feGaussianBlur stdDeviation="2.4" result="blur"/>'
        '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter>'
        '<filter id="glowStrong" x="-150%" y="-150%" width="400%" height="400%">'
        '<feGaussianBlur stdDeviation="4" result="blur"/>'
        '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter>'
        '</defs>'
    )

    # ---- beads (contribution squares as glowing dots) ----
    svg.append('<g>')
    for i, cell in enumerate(order):
        x, y = xy(cell)
        level = cell["level"]
        base_color = LEVEL_COLORS[level]
        t_eat = times[i]
        t_fade_end = min(1.0, t_eat + FADE_FRAC)
        has_glow = level > 0

        filt = ' filter="url(#glow)"' if has_glow else ""
        svg.append(f'<circle cx="{x}" cy="{y}" r="{RADIUS}" fill="{base_color}"{filt}>')

        kt = [0, max(0, t_eat - 0.001), t_eat, t_fade_end, 1]
        kt_str = ";".join(str(round(v, 5)) for v in kt)
        svg.append(
            f'<animate attributeName="fill" calcMode="discrete" '
            f'keyTimes="0;{round(t_eat,5)};1" '
            f'values="{base_color};{base_color};{EATEN_COLOR}" '
            f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
        )
        if has_glow:
            svg.append(
                f'<animate attributeName="opacity" '
                f'keyTimes="{kt_str}" '
                f'values="1;1;1;0.35;0.35" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            # gentle idle pulse before being eaten
            svg.append(
                f'<animate attributeName="r" '
                f'keyTimes="0;{max(0.0001, t_eat*0.3)};{max(0.0002,t_eat*0.6)};{round(t_eat,5)};1" '
                f'values="{RADIUS};{RADIUS+0.8};{RADIUS};{RADIUS};{RADIUS}" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
        svg.append('</circle>')

        # pop/burst flourish exactly at the moment it's eaten
        if has_glow:
            t_burst_end = min(1.0, t_eat + BURST_FRAC)
            svg.append(
                f'<circle cx="{x}" cy="{y}" r="0" fill="none" stroke="{base_color}" '
                f'stroke-width="1.6" opacity="0" filter="url(#glowStrong)">'
                f'<animate attributeName="r" '
                f'keyTimes="0;{max(0,t_eat-0.001)};{round(t_eat,5)};{round(t_burst_end,5)};1" '
                f'values="0;0;{RADIUS};{RADIUS*2.6};{RADIUS*2.6}" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" '
                f'keyTimes="0;{max(0,t_eat-0.001)};{round(t_eat,5)};{round(t_burst_end,5)};1" '
                f'values="0;0;0.9;0;0" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                f'</circle>'
            )
    svg.append('</g>')

    # ---- snake segments ----
    coords = [xy(c) for c in order]

    def seg_values(attr_idx, k):
        vals = []
        for i in range(n):
            j = max(0, i - k)
            vals.append(str(coords[j][attr_idx]))
        return ";".join(vals)

    kt_all = ";".join(str(t) for t in times)

    svg.append('<g>')
    for k in range(MAX_TAIL - 1, -1, -1):
        reveal_t = round(min(times[min(k, n - 1)], 0.98), 5)
        is_head = k == 0
        r = RADIUS + (2.2 if is_head else 1.2)
        fill = SNAKE_HEAD_COLOR if is_head else SNAKE_COLOR
        op_base = 1 if is_head else 0.92 - (k * 0.03)

        cx_vals = seg_values(0, k)
        cy_vals = seg_values(1, k)

        svg.append(
            f'<circle r="{r}" fill="{fill}" filter="url(#glow)" opacity="0">'
            f'<animate attributeName="cx" keyTimes="{kt_all}" values="{cx_vals}" '
            f'calcMode="linear" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="cy" keyTimes="{kt_all}" values="{cy_vals}" '
            f'calcMode="linear" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" '
            f'keyTimes="0;{reveal_t};{min(1,reveal_t+0.01)};1" '
            f'values="0;0;{op_base};{op_base}" '
            f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            f'</circle>'
        )
        if is_head:
            eye_dx, eye_dy = 2.1, -2.1
            svg.append(
                f'<circle r="1" fill="{SNAKE_EYE_COLOR}" opacity="0">'
                f'<animate attributeName="cx" keyTimes="{kt_all}" '
                f'values="{";".join(str(coords[i][0]+eye_dx) for i in range(n))}" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                f'<animate attributeName="cy" keyTimes="{kt_all}" '
                f'values="{";".join(str(coords[i][1]+eye_dy) for i in range(n))}" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" '
                f'keyTimes="0;{reveal_t};{min(1,reveal_t+0.01)};1" '
                f'values="0;0;1;1" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                f'</circle>'
            )
    svg.append('</g>')

    svg.append('</svg>')
    return "".join(svg)


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_snake.py <username> <output.svg>")
        sys.exit(1)
    username, out_path = sys.argv[1], sys.argv[2]
    grid, n_weeks, n_days = fetch_grid(username)
    order = boustrophedon_order(grid, n_weeks, n_days)
    svg = build_svg(order, n_weeks, n_days)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"Wrote {out_path} ({len(order)} cells, {len(svg)} bytes)")


if __name__ == "__main__":
    main()
