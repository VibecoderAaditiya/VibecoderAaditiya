#!/usr/bin/env python3
"""
GitHub Contribution Snake
-------------------------

A Snake-game-style animated SVG that hunts GitHub contribution squares.

Behavior:
- Level 4 targets are eaten first
- Then level 3
- Then level 2
- Then level 1
- The snake moves one grid cell at a time
- The snake cannot move through its own body
- Eating a contribution square grows the snake by one segment
- Eaten contribution squares disappear
- The animation loops automatically

Usage:
    python3 generate_snake.py <github_username> <output_svg_path>

Example:
    python3 generate_snake.py aadi output/snake.svg
"""

import sys
import os
import re
import urllib.request
from collections import deque


# ============================================================
# CONFIG
# ============================================================

CELL = 13
SIZE = 9

PAD_X = 30
PAD_Y = 30

STEP_TIME = 0.085

BG_COLOR = "#0d1117"
EATEN_COLOR = "#161b22"

SNAKE_COLOR = "#f2f2f2"
SNAKE_HEAD_COLOR = "#ffffff"
SNAKE_EYE_COLOR = "#0d1117"

LEVEL_COLORS = {
    0: "#1b2430",
    1: "#0e4429",
    2: "#046b34",
    3: "#26a641",
    4: "#39d353",
}

# Number of extra frames after the final target before looping.
LOOP_PAUSE_STEPS = 30

# Prevent pathological SVGs if GitHub changes its grid.
MAX_SIMULATION_STEPS = 30000


# ============================================================
# FETCH GITHUB CONTRIBUTION GRID
# ============================================================

def fetch_grid(username):
    url = f"https://github.com/users/{username}/contributions"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 GitHub-Contribution-Snake"
        },
    )

    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch GitHub contributions for '{username}': {exc}"
        )

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)

    weekday_rows = []

    for row in rows:
        cells = re.findall(
            r'data-date="([0-9-]+)"[^>]*data-level="([0-9])"',
            row,
        )

        if cells:
            weekday_rows.append(cells)

    if not weekday_rows:
        raise RuntimeError(
            "Could not parse GitHub contribution data."
        )

    # GitHub contribution HTML normally has 7 weekday rows.
    # We transpose the data into:
    #
    #     (week, weekday) -> level
    #
    # rather than assuming every row has exactly the same size.

    n_days = len(weekday_rows)
    n_weeks = max(len(row) for row in weekday_rows)

    grid = {}

    for weekday, row in enumerate(weekday_rows):
        for week, (_, level) in enumerate(row):
            grid[(week, weekday)] = int(level)

    return grid, n_weeks, n_days


# ============================================================
# GRID HELPERS
# ============================================================

DIRECTIONS = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
)


def neighbors(cell, n_weeks, n_days):
    w, d = cell

    for dw, dd in DIRECTIONS:
        nw = w + dw
        nd = d + dd

        if 0 <= nw < n_weeks and 0 <= nd < n_days:
            yield (nw, nd)


def is_inside(cell, n_weeks, n_days):
    w, d = cell
    return 0 <= w < n_weeks and 0 <= d < n_days


# ============================================================
# BFS PATHFINDING
# ============================================================

def bfs_path(
    start,
    target,
    body,
    n_weeks,
    n_days,
    allow_tail=True,
):
    """
    Find a shortest collision-free path from start to target.

    The snake body is represented as:

        [head, neck, ..., tail]

    The tail can normally be entered because it moves away on
    the same turn.

    However, if we are specifically targeting an eating move,
    the target itself must not be part of the body.
    """

    if start == target:
        return []

    blocked = set(body)

    # The tail normally disappears when the snake moves.
    if allow_tail and len(body) > 1:
        blocked.discard(body[-1])

    # Never allow the target if it is occupied by the body.
    if target in blocked:
        return None

    queue = deque([start])
    parent = {start: None}

    while queue:
        current = queue.popleft()

        for nxt in neighbors(current, n_weeks, n_days):

            if nxt in parent:
                continue

            if nxt in blocked and nxt != target:
                continue

            parent[nxt] = current

            if nxt == target:
                path = []
                cur = target

                while cur != start:
                    path.append(cur)
                    cur = parent[cur]

                path.reverse()
                return path

            queue.append(nxt)

    return None


# ============================================================
# SAFETY CHECK
# ============================================================

def flood_fill_size(start, body, n_weeks, n_days):
    """
    Estimate how much free space remains reachable from start.

    This prevents the snake from making obviously stupid moves
    that trap its head in a tiny pocket.
    """

    blocked = set(body)

    # Tail will normally move away.
    if len(body) > 1:
        blocked.discard(body[-1])

    if start in blocked:
        return 0

    queue = deque([start])
    visited = {start}

    while queue:
        current = queue.popleft()

        for nxt in neighbors(current, n_weeks, n_days):
            if nxt in visited:
                continue

            if nxt in blocked:
                continue

            visited.add(nxt)
            queue.append(nxt)

    return len(visited)


# ============================================================
# TARGET SELECTION
# ============================================================

def choose_target(
    head,
    body,
    remaining_targets,
    n_weeks,
    n_days,
):
    """
    Choose the highest-priority reachable target.

    Priority:
        level 4
        level 3
        level 2
        level 1

    Within the same level:
        shortest reachable path wins.
    """

    for level in (4, 3, 2, 1):

        candidates = [
            cell
            for cell in remaining_targets
            if remaining_targets[cell] == level
            and cell not in body
        ]

        if not candidates:
            continue

        best_target = None
        best_path = None

        for target in candidates:

            path = bfs_path(
                head,
                target,
                body,
                n_weeks,
                n_days,
            )

            if path is None:
                continue

            if best_path is None or len(path) < len(best_path):
                best_target = target
                best_path = path

        if best_target is not None:
            return best_target, best_path

    return None, None


# ============================================================
# SIMULATE SNAKE
# ============================================================

def simulate_snake(
    grid,
    n_weeks,
    n_days,
):
    """
    Generate the actual frame-by-frame Snake state.

    Every frame contains the entire body:

        frame[0] = head
        frame[1] = neck
        ...
        frame[-1] = tail

    This is the important architectural difference from the
    original implementation.
    """

    # Start near the upper-left corner.

    start = (0, 0)

    # Make sure the starting cell exists.
    if start not in grid:
        start = min(grid.keys())

    body = [start]

    # Only non-zero contribution squares are targets.
    remaining = {
        cell: level
        for cell, level in grid.items()
        if level > 0
    }

    # Don't eat the starting square accidentally.
    remaining.pop(start, None)

    frames = []

    # Initial frame.
    frames.append({
        "body": list(body),
        "eaten": None,
        "grow": False,
    })

    eaten_order = []

    steps = 0

    while remaining and steps < MAX_SIMULATION_STEPS:

        target, path = choose_target(
            body[0],
            body,
            remaining,
            n_weeks,
            n_days,
        )

        # ----------------------------------------------------
        # No target currently reachable.
        # Try moving toward open space instead of freezing.
        # ----------------------------------------------------

        if target is None:

            possible_moves = []

            for nxt in neighbors(
                body[0],
                n_weeks,
                n_days,
            ):
                if nxt in body[:-1]:
                    continue

                test_body = [nxt] + body

                # Normal movement removes tail.
                if len(test_body) > 1:
                    test_body.pop()

                space = flood_fill_size(
                    nxt,
                    test_body,
                    n_weeks,
                    n_days,
                )

                possible_moves.append(
                    (space, nxt)
                )

            if not possible_moves:
                break

            possible_moves.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            nxt = possible_moves[0][1]

            body = [nxt] + body

            if len(body) > 1:
                body.pop()

            frames.append({
                "body": list(body),
                "eaten": None,
                "grow": False,
            })

            steps += 1
            continue

        # ----------------------------------------------------
        # Follow path one cell at a time.
        # ----------------------------------------------------

        for nxt in path:

            if steps >= MAX_SIMULATION_STEPS:
                break

            eating = nxt == target and target in remaining

            # Collision check.
            occupied_without_tail = set(body[:-1])

            if nxt in occupied_without_tail:
                # This should never happen because BFS avoids it.
                # If it somehow does, abandon this path.
                break

            new_body = [nxt] + body

            if not eating:
                # Normal Snake movement:
                # add head, remove tail.
                new_body.pop()

            else:
                # Eating:
                # add head, KEEP tail.
                level = remaining.pop(target)
                eaten_order.append(
                    (target, level)
                )

            body = new_body

            frames.append({
                "body": list(body),
                "eaten": target if eating else None,
                "grow": eating,
            })

            steps += 1

            if eating:
                break

        else:
            continue

    # --------------------------------------------------------
    # Small pause at end.
    # --------------------------------------------------------

    for _ in range(LOOP_PAUSE_STEPS):
        frames.append({
            "body": list(body),
            "eaten": None,
            "grow": False,
        })

    return frames, eaten_order


# ============================================================
# SVG GENERATION
# ============================================================

def build_svg(
    grid,
    frames,
    eaten_order,
    n_weeks,
    n_days,
):
    width = (
        PAD_X * 2
        + (n_weeks - 1) * CELL
        + CELL
    )

    height = (
        PAD_Y * 2
        + (n_days - 1) * CELL
        + CELL
    )

    frame_count = len(frames)

    if frame_count < 2:
        frame_count = 2

    total_duration = (
        max(frame_count - 1, 1)
        * STEP_TIME
    )

    total_duration = round(
        total_duration,
        3,
    )

    def xy(cell):
        return (
            PAD_X + cell[0] * CELL,
            PAD_Y + cell[1] * CELL,
        )

    # --------------------------------------------------------
    # Frame timing.
    # --------------------------------------------------------

    times = [
        round(
            i / (frame_count - 1),
            6,
        )
        for i in range(frame_count)
    ]

    key_times = ";".join(
        str(t)
        for t in times
    )

    # --------------------------------------------------------
    # Determine when each contribution square is eaten.
    # --------------------------------------------------------

    eat_time = {}

    for i, frame in enumerate(frames):
        cell = frame["eaten"]

        if cell is not None and cell not in eat_time:
            eat_time[cell] = times[i]

    # --------------------------------------------------------
    # SVG header.
    # --------------------------------------------------------

    svg = []

    svg.append(
        f'<svg '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="{width}" '
        f'height="{height}">'
    )

    svg.append(
        f'<rect '
        f'x="0" y="0" '
        f'width="{width}" '
        f'height="{height}" '
        f'rx="16" '
        f'fill="{BG_COLOR}"/>'
    )

    # --------------------------------------------------------
    # Filters.
    # --------------------------------------------------------

    svg.append(
        '<defs>'

        '<filter id="glow" '
        'x="-100%" y="-100%" '
        'width="300%" height="300%">'
        '<feGaussianBlur '
        'stdDeviation="2.4" '
        'result="blur"/>'
        '<feMerge>'
        '<feMergeNode in="blur"/>'
        '<feMergeNode in="SourceGraphic"/>'
        '</feMerge>'
        '</filter>'

        '<filter id="glowStrong" '
        'x="-150%" y="-150%" '
        'width="400%" height="400%">'
        '<feGaussianBlur '
        'stdDeviation="4" '
        'result="blur"/>'
        '<feMerge>'
        '<feMergeNode in="blur"/>'
        '<feMergeNode in="SourceGraphic"/>'
        '</feMerge>'
        '</filter>'

        '</defs>'
    )

    # ========================================================
    # CONTRIBUTION GRID
    # ========================================================

    svg.append("<g>")

    for cell, level in grid.items():

        x, y = xy(cell)

        rx = x - SIZE / 2
        ry = y - SIZE / 2

        color = LEVEL_COLORS[level]

        if cell not in eat_time:

            svg.append(
                f'<rect '
                f'x="{rx}" '
                f'y="{ry}" '
                f'width="{SIZE}" '
                f'height="{SIZE}" '
                f'rx="2" '
                f'fill="{color}"/>'
            )

            continue

        # ----------------------------------------------------
        # EATEN CONTRIBUTION
        # ----------------------------------------------------

        t = eat_time[cell]

        svg.append(
            f'<rect '
            f'x="{rx}" '
            f'y="{ry}" '
            f'width="{SIZE}" '
            f'height="{SIZE}" '
            f'rx="2" '
            f'fill="{color}" '
            f'filter="url(#glow)">'

            # Disappear exactly when eaten.
            f'<animate '
            f'attributeName="opacity" '
            f'calcMode="discrete" '
            f'keyTimes="0;{t};1" '
            f'values="1;1;0" '
            f'dur="{total_duration}s" '
            f'repeatCount="indefinite"/>'

            '</rect>'
        )

        # ----------------------------------------------------
        # EAT BURST
        # ----------------------------------------------------

        burst_end = min(
            1.0,
            t + 0.018,
        )

        svg.append(
            f'<circle '
            f'cx="{x}" '
            f'cy="{y}" '
            f'r="0" '
            f'fill="none" '
            f'stroke="{color}" '
            f'stroke-width="1.6" '
            f'opacity="0" '
            f'filter="url(#glowStrong)">'

            f'<animate '
            f'attributeName="r" '
            f'keyTimes="0;{t};{burst_end};1" '
            f'values="0;{SIZE / 2};{SIZE * 1.5};{SIZE * 1.5}" '
            f'dur="{total_duration}s" '
            f'repeatCount="indefinite"/>'

            f'<animate '
            f'attributeName="opacity" '
            f'keyTimes="0;{t};{burst_end};1" '
            f'values="0;0.9;0;0" '
            f'dur="{total_duration}s" '
            f'repeatCount="indefinite"/>'

            '</circle>'
        )

    svg.append("</g>")

    # ========================================================
    # SNAKE
    # ========================================================

    # Find maximum snake length.
    max_body_length = max(
        len(frame["body"])
        for frame in frames
    )

    svg.append("<g>")

    # Draw tail first, then head last.
    for segment_index in range(
        max_body_length - 1,
        -1,
        -1,
    ):

        x_values = []
        y_values = []
        opacity_values = []

        for frame in frames:

            body = frame["body"]

            if segment_index < len(body):

                cell = body[segment_index]
                x, y = xy(cell)

                x_values.append(
                    str(x - SIZE / 2)
                )

                y_values.append(
                    str(y - SIZE / 2)
                )

                opacity_values.append("1")

            else:
                # Segment doesn't exist yet.
                #
                # Put it at the tail position and hide it.
                #
                tail = body[-1]
                x, y = xy(tail)

                x_values.append(
                    str(x - SIZE / 2)
                )

                y_values.append(
                    str(y - SIZE / 2)
                )

                opacity_values.append("0")

        is_head = segment_index == 0

        if is_head:
            seg_size = SIZE + 2.5
            fill = SNAKE_HEAD_COLOR
            radius = 2.5
        else:
            seg_size = SIZE + 1.0
            fill = SNAKE_COLOR
            radius = 2.2

        # Slightly fade older tail segments.
        if is_head:
            base_opacity = 1
        else:
            base_opacity = max(
                0.45,
                0.92 - segment_index * 0.025,
            )

        svg.append(
            f'<rect '
            f'width="{seg_size}" '
            f'height="{seg_size}" '
            f'rx="{radius}" '
            f'fill="{fill}" '
            f'opacity="0">'

            f'<animate '
            f'attributeName="x" '
            f'keyTimes="{key_times}" '
            f'values="{";".join(x_values)}" '
            f'calcMode="discrete" '
            f'dur="{total_duration}s" '
            f'repeatCount="indefinite"/>'

            f'<animate '
            f'attributeName="y" '
            f'keyTimes="{key_times}" '
            f'values="{";".join(y_values)}" '
            f'calcMode="discrete" '
            f'dur="{total_duration}s" '
            f'repeatCount="indefinite"/>'

            f'<animate '
            f'attributeName="opacity" '
            f'keyTimes="{key_times}" '
            f'values="{";".join(opacity_values)}" '
            f'calcMode="discrete" '
            f'dur="{total_duration}s" '
            f'repeatCount="indefinite"/>'

            '</rect>'
        )

        # ----------------------------------------------------
        # HEAD EYE
        # ----------------------------------------------------

        if is_head:

            eye_x = []
            eye_y = []
            eye_opacity = []

            for frame in frames:

                body = frame["body"]

                if body:

                    x, y = xy(body[0])

                    eye_x.append(
                        str(x + 2.3)
                    )

                    eye_y.append(
                        str(y - 2.3)
                    )

                    eye_opacity.append("1")

                else:

                    eye_x.append("0")
                    eye_y.append("0")
                    eye_opacity.append("0")

            svg.append(
                f'<circle '
                f'r="1" '
                f'fill="{SNAKE_EYE_COLOR}">'

                f'<animate '
                f'attributeName="cx" '
                f'keyTimes="{key_times}" '
                f'values="{";".join(eye_x)}" '
                f'calcMode="discrete" '
                f'dur="{total_duration}s" '
                f'repeatCount="indefinite"/>'

                f'<animate '
                f'attributeName="cy" '
                f'keyTimes="{key_times}" '
                f'values="{";".join(eye_y)}" '
                f'calcMode="discrete" '
                f'dur="{total_duration}s" '
                f'repeatCount="indefinite"/>'

                f'<animate '
                f'attributeName="opacity" '
                f'keyTimes="{key_times}" '
                f'values="{";".join(eye_opacity)}" '
                f'calcMode="discrete" '
                f'dur="{total_duration}s" '
                f'repeatCount="indefinite"/>'

                '</circle>'
            )

    svg.append("</g>")

    svg.append("</svg>")

    return "".join(svg)


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) < 3:
        print(
            "Usage: python3 generate_snake.py "
            "<github_username> <output.svg>"
        )
        sys.exit(1)

    username = sys.argv[1]
    output_path = sys.argv[2]

    print(
        f"Fetching contribution data for @{username}..."
    )

    grid, n_weeks, n_days = fetch_grid(username)

    print(
        f"Grid: {n_weeks} weeks × {n_days} days"
    )

    target_count = sum(
        1
        for level in grid.values()
        if level > 0
    )

    print(
        f"Contribution targets: {target_count}"
    )

    print(
        "Simulating Snake..."
    )

    frames, eaten_order = simulate_snake(
        grid,
        n_weeks,
        n_days,
    )

    print(
        f"Generated {len(frames)} animation frames"
    )

    print(
        f"Snake ate {len(eaten_order)} contribution squares"
    )

    if eaten_order:

        counts = {
            1: 0,
            2: 0,
            3: 0,
            4: 0,
        }

        for _, level in eaten_order:
            counts[level] += 1

        print(
            "Eaten:",
            f"Level 4={counts[4]},",
            f"Level 3={counts[3]},",
            f"Level 2={counts[2]},",
            f"Level 1={counts[1]}",
        )

    print(
        "Building SVG..."
    )

    svg = build_svg(
        grid,
        frames,
        eaten_order,
        n_weeks,
        n_days,
    )

    output_dir = os.path.dirname(
        os.path.abspath(output_path)
    )

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(svg)

    print(
        f"✓ Wrote {output_path}"
    )

    print(
        f"✓ SVG size: {len(svg):,} bytes"
    )


if __name__ == "__main__":
    main()
