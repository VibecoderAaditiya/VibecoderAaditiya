#!/usr/bin/env python3
"""
Generates a custom animated SVG: a square-bodied snake that hunts down the
brightest (most active) GitHub contribution squares first, working its way
down to the dimmer ones, eating each as it passes and growing longer with
every square it eats.

Usage: python3 generate_snake.py <github_username> <output_svg_path>
No API token needed — reads the public contributions page directly.
"""
import sys
import os
import re
import urllib.request

CELL = 13           # px between cell centers
SIZE = 9             # square body size
PAD_X = 30
PAD_Y = 30
TOTAL_DUR = 42       # seconds for one full loop
MAX_TAIL = 7         # max snake segments (including head)
BURST_FRAC = 0.012
FADE_FRAC = 0.02

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

    n_weeks = len(weekday_rows[0])
    grid = {}
    for weekday, row in enumerate(weekday_rows):
        for week, (date_str, level) in enumerate(row):
            grid[(week, weekday)] = int(level)
    return grid, n_weeks, len(weekday_rows)


def manhattan_path(a, b):
    """Grid-stepped path from a to b (exclusive of a), moving one axis then the other."""
    (aw, ad), (bw, bd) = a, b
    path = []
    step = 1 if bd > ad else -1
    for d in range(ad + step, bd + step, step) if ad != bd else []:
        path.append((aw, d))
    cur_d = bd
    step = 1 if bw > aw else -1
    for w in range(aw + step, bw + step, step) if aw != bw else []:
        path.append((w, cur_d))
    return path


def build_order(grid, n_weeks, n_days):
    """Nearest-neighbor path, visiting brightest squares first, dimmest active last."""
    all_cells = [(w, d) for w in range(n_weeks) for d in range(n_days) if (w, d) in grid]
    pos = (0, 0)
    order = []          # list of (week, weekday)
    eat_flags = []      # True if this step is an actual "eat" of a target square

    for level in (4, 3, 2, 1):
        remaining = {c for c in all_cells if grid[c] == level}
        while remaining:
            nxt = min(remaining, key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]))
            remaining.discard(nxt)
            for step_cell in manhattan_path(pos, nxt):
                is_target = step_cell == nxt
                order.append(step_cell)
                eat_flags.append(is_target)
            pos = nxt

    return order, eat_flags


def build_svg(grid, order, eat_flags, n_weeks, n_days):
    width = PAD_X * 2 + (n_weeks - 1) * CELL + CELL
    height = PAD_Y * 2 + (n_days - 1) * CELL + CELL

    def xy(cell):
        return PAD_X + cell[0] * CELL, PAD_Y + cell[1] * CELL

    n = len(order)
    times = [round(i / (n - 1), 5) for i in range(n)]

    # first eat-time per target cell (a cell is only "eaten" once, even if path crosses it again)
    eat_time = {}
    for i, (cell, is_eat) in enumerate(zip(order, eat_flags)):
        if is_eat and cell not in eat_time:
            eat_time[cell] = times[i]

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
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

    # ---- background squares (every cell in the calendar) ----
    all_cells = [(w, d) for w in range(n_weeks) for d in range(n_days) if (w, d) in grid]
    svg.append('<g>')
    for cell in all_cells:
        x, y = xy(cell)
        level = grid[cell]
        base_color = LEVEL_COLORS[level]
        rx = x - SIZE / 2
        ry = y - SIZE / 2
        has_glow = level > 0

        if cell in eat_time:
            t_eat = eat_time[cell]
            t_fade_end = min(1.0, t_eat + FADE_FRAC)
            filt = ' filter="url(#glow)"' if has_glow else ""
            svg.append(f'<rect x="{rx}" y="{ry}" width="{SIZE}" height="{SIZE}" rx="2" fill="{base_color}"{filt}>')
            svg.append(
                f'<animate attributeName="fill" calcMode="discrete" '
                f'keyTimes="0;{round(t_eat,5)};1" values="{base_color};{base_color};{EATEN_COLOR}" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            svg.append(
                f'<animate attributeName="opacity" '
                f'keyTimes="0;{max(0,round(t_eat-0.001,5))};{round(t_eat,5)};{round(t_fade_end,5)};1" '
                f'values="1;1;1;0.35;0.35" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            svg.append(
                f'<animate attributeName="width" '
                f'keyTimes="0;{max(0.0001, round(t_eat*0.5,5))};{round(t_eat,5)};1" '
                f'values="{SIZE};{SIZE+1.4};{SIZE};{SIZE}" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            svg.append(
                f'<animate attributeName="height" '
                f'keyTimes="0;{max(0.0001, round(t_eat*0.5,5))};{round(t_eat,5)};1" '
                f'values="{SIZE};{SIZE+1.4};{SIZE};{SIZE}" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            svg.append(
                f'<animate attributeName="x" '
                f'keyTimes="0;{max(0.0001, round(t_eat*0.5,5))};{round(t_eat,5)};1" '
                f'values="{rx};{rx-0.7};{rx};{rx}" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            svg.append(
                f'<animate attributeName="y" '
                f'keyTimes="0;{max(0.0001, round(t_eat*0.5,5))};{round(t_eat,5)};1" '
                f'values="{ry};{ry-0.7};{ry};{ry}" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            )
            svg.append('</rect>')

            if has_glow:
                t_burst_end = min(1.0, t_eat + BURST_FRAC)
                svg.append(
                    f'<circle cx="{x}" cy="{y}" r="0" fill="none" stroke="{base_color}" '
                    f'stroke-width="1.6" opacity="0" filter="url(#glowStrong)">'
                    f'<animate attributeName="r" '
                    f'keyTimes="0;{max(0,round(t_eat-0.001,5))};{round(t_eat,5)};{round(t_burst_end,5)};1" '
                    f'values="0;0;{SIZE/2};{SIZE*1.4};{SIZE*1.4}" '
                    f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                    f'<animate attributeName="opacity" '
                    f'keyTimes="0;{max(0,round(t_eat-0.001,5))};{round(t_eat,5)};{round(t_burst_end,5)};1" '
                    f'values="0;0;0.9;0;0" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                    f'</circle>'
                )
        else:
            # never visited by the snake — static background square
            svg.append(f'<rect x="{rx}" y="{ry}" width="{SIZE}" height="{SIZE}" rx="2" fill="{base_color}"/>')
    svg.append('</g>')

    # ---- snake segments (square-bodied) ----
    coords = [xy(c) for c in order]

    def seg_values(attr_idx, k, offset=0):
        vals = []
        for i in range(n):
            j = max(0, i - k)
            vals.append(str(coords[j][attr_idx] + offset))
        return ";".join(vals)

    kt_all = ";".join(str(t) for t in times)

    svg.append('<g>')
    for k in range(MAX_TAIL - 1, -1, -1):
        reveal_t = round(min(times[min(k, n - 1)], 0.98), 5)
        is_head = k == 0
        seg_size = SIZE + (2.5 if is_head else 1.0)
        fill = SNAKE_HEAD_COLOR if is_head else SNAKE_COLOR
        op_base = 1 if is_head else 0.92 - (k * 0.03)

        x_vals = seg_values(0, k, offset=-seg_size / 2)
        y_vals = seg_values(1, k, offset=-seg_size / 2)

        svg.append(
            f'<rect width="{seg_size}" height="{seg_size}" rx="2.5" fill="{fill}" '
            f'filter="url(#glow)" opacity="0">'
            f'<animate attributeName="x" keyTimes="{kt_all}" values="{x_vals}" '
            f'calcMode="linear" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="y" keyTimes="{kt_all}" values="{y_vals}" '
            f'calcMode="linear" dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" '
            f'keyTimes="0;{reveal_t};{min(1,reveal_t+0.01)};1" '
            f'values="0;0;{op_base};{op_base}" '
            f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
            f'</rect>'
        )
        if is_head:
            eye_dx, eye_dy = 2.3, -2.3
            cx_vals = seg_values(0, k, offset=eye_dx)
            cy_vals = seg_values(1, k, offset=eye_dy)
            svg.append(
                f'<circle r="1" fill="{SNAKE_EYE_COLOR}" opacity="0">'
                f'<animate attributeName="cx" keyTimes="{kt_all}" values="{cx_vals}" '
                f'dur="{TOTAL_DUR}s" repeatCount="indefinite"/>'
                f'<animate attributeName="cy" keyTimes="{kt_all}" values="{cy_vals}" '
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
    order, eat_flags = build_order(grid, n_weeks, n_days)
    svg = build_svg(grid, order, eat_flags, n_weeks, n_days)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"Wrote {out_path} ({len(order)} steps, {len(svg)} bytes)")


if __name__ == "__main__":
    main()
