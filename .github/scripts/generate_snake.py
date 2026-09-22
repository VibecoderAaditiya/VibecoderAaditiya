#!/usr/bin/env python3

"""
GitHub Contribution Snake
=========================

Animated SVG of a Snake-game-style creature hunting GitHub
contribution squares.

Behavior:

    START
      ↓
    hunt brightest squares
      ↓
    eat → grow
      ↓
    finish all targets
      ↓
    return to START
      ↓
    restore all contribution squares
      ↓
    repeat forever

Usage:

    python3 generate_snake.py <github_username> <output.svg>

Example:

    python3 generate_snake.py aadi snake.svg
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

# Lower = faster.
STEP_TIME = 0.085

# Pause at the starting position before restarting.
RESET_PAUSE_STEPS = 12

# Pause after finishing all beads before returning.
FINISH_PAUSE_STEPS = 10

# Snake appearance.
SNAKE_COLOR = "#f2f2f2"
SNAKE_HEAD_COLOR = "#ffffff"
SNAKE_EYE_COLOR = "#0d1117"

# Contribution colors.
LEVEL_COLORS = {
    0: "#1b2430",
    1: "#0e4429",
    2: "#046b34",
    3: "#26a641",
    4: "#39d353",
}

# What an eaten square becomes.
EATEN_COLOR = "#161b22"

MAX_STEPS = 50000


# ============================================================
# GITHUB DATA
# ============================================================

def fetch_grid(username):
    url = f"https://github.com/users/{username}/contributions"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 GitHub-Snake"
        },
    )

    try:
        html = urllib.request.urlopen(
            req,
            timeout=20
        ).read().decode("utf-8")

    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch GitHub contributions: {exc}"
        )

    rows = re.findall(
        r"<tr[^>]*>(.*?)</tr>",
        html,
        re.S
    )

    weekday_rows = []

    for row in rows:

        cells = re.findall(
            r'data-date="([0-9-]+)"[^>]*data-level="([0-9])"',
            row
        )

        if cells:
            weekday_rows.append(cells)

    if not weekday_rows:
        raise RuntimeError(
            "Could not parse GitHub contribution data."
        )

    n_days = len(weekday_rows)
    n_weeks = max(
        len(row)
        for row in weekday_rows
    )

    grid = {}

    for day, row in enumerate(weekday_rows):

        for week, (_, level) in enumerate(row):

            grid[(week, day)] = int(level)

    return grid, n_weeks, n_days


# ============================================================
# GRID
# ============================================================

DIRECTIONS = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
)


def neighbors(cell, width, height):

    x, y = cell

    for dx, dy in DIRECTIONS:

        nx = x + dx
        ny = y + dy

        if (
            0 <= nx < width
            and 0 <= ny < height
        ):
            yield nx, ny


# ============================================================
# BFS
# ============================================================

def find_path(
    start,
    target,
    body,
    width,
    height,
):
    """
    Find a collision-free path.

    body[0] = head
    body[-1] = tail

    The tail is allowed as a destination because it moves
    away during a normal Snake movement.
    """

    if start == target:
        return []

    blocked = set(body[:-1])

    if target in blocked:
        return None

    queue = deque([start])
    parent = {
        start: None
    }

    while queue:

        current = queue.popleft()

        for nxt in neighbors(
            current,
            width,
            height,
        ):

            if nxt in parent:
                continue

            if nxt in blocked:
                continue

            parent[nxt] = current

            if nxt == target:

                path = []

                cursor = target

                while cursor != start:

                    path.append(cursor)

                    cursor = parent[cursor]

                path.reverse()

                return path

            queue.append(nxt)

    return None


# ============================================================
# TARGET SELECTION
# ============================================================

def choose_target(
    head,
    body,
    remaining,
    width,
    height,
):
    """
    Brightness is the primary priority.

    Within a brightness level, nearest reachable
    contribution square wins.
    """

    for level in (4, 3, 2, 1):

        targets = [
            cell
            for cell, target_level in remaining.items()
            if target_level == level
            and cell not in body
        ]

        best_target = None
        best_path = None

        for target in targets:

            path = find_path(
                head,
                target,
                body,
                width,
                height,
            )

            if path is None:
                continue

            if (
                best_path is None
                or len(path) < len(best_path)
            ):
                best_target = target
                best_path = path

        if best_target is not None:

            return (
                best_target,
                best_path,
            )

    return None, None


# ============================================================
# SIMULATION FRAME
# ============================================================

def frame(body, eaten=None):

    return {
        "body": tuple(body),
        "eaten": eaten,
    }


# ============================================================
# SIMULATE ONE COMPLETE RUN
# ============================================================

def simulate_run(
    grid,
    width,
    height,
):
    """
    Produces actual Snake states.

    Every frame contains the complete body.

    Example:

        frame 0
        H

        frame 1
        H
        B

        frame 2
        H
        B
        B

        eat:
        H
        B
        B
        B

    The tail remains on an eating frame,
    causing the snake to grow.
    """

    # --------------------------------------------------------
    # Start position.
    # --------------------------------------------------------

    start = (0, 0)

    if start not in grid:

        start = min(
            grid.keys(),
            key=lambda p: (
                p[0],
                p[1],
            )
        )

    body = [start]

    # --------------------------------------------------------
    # All active contribution squares.
    # --------------------------------------------------------

    remaining = {
        cell: level
        for cell, level in grid.items()
        if level > 0
        and cell != start
    }

    frames = [
        frame(body)
    ]

    eaten_cells = []

    steps = 0

    # ========================================================
    # HUNT
    # ========================================================

    while remaining:

        if steps >= MAX_STEPS:
            break

        target, path = choose_target(
            body[0],
            body,
            remaining,
            width,
            height,
        )

        # ----------------------------------------------------
        # If no target can currently be reached,
        # move toward the largest available space.
        # ----------------------------------------------------

        if target is None:

            candidates = []

            for nxt in neighbors(
                body[0],
                width,
                height,
            ):

                if nxt in body[:-1]:
                    continue

                # Normal movement.
                new_body = [nxt] + body[:-1]

                # Estimate available space.
                queue = deque([nxt])
                visited = {nxt}

                while queue:

                    current = queue.popleft()

                    for candidate in neighbors(
                        current,
                        width,
                        height,
                    ):

                        if candidate in visited:
                            continue

                        if candidate in new_body:
                            continue

                        visited.add(candidate)
                        queue.append(candidate)

                candidates.append(
                    (
                        len(visited),
                        nxt,
                    )
                )

            if not candidates:
                break

            candidates.sort(
                reverse=True
            )

            nxt = candidates[0][1]

            body = [
                nxt
            ] + body[:-1]

            frames.append(
                frame(body)
            )

            steps += 1

            continue

        # ----------------------------------------------------
        # Follow target path.
        # ----------------------------------------------------

        for nxt in path:

            if steps >= MAX_STEPS:
                break

            eating = (
                nxt == target
                and target in remaining
            )

            # Safety.
            if nxt in body[:-1]:
                break

            # ------------------------------------------------
            # NORMAL MOVE
            # ------------------------------------------------

            if not eating:

                body = [
                    nxt
                ] + body[:-1]

                frames.append(
                    frame(body)
                )

            # ------------------------------------------------
            # EAT
            # ------------------------------------------------

            else:

                # Add head.
                #
                # IMPORTANT:
                # Do NOT remove the tail.
                #
                # This is what makes the snake grow.
                body = [
                    nxt
                ] + body

                eaten_cells.append(
                    target
                )

                del remaining[target]

                frames.append(
                    frame(
                        body,
                        eaten=target,
                    )
                )

            steps += 1

            if eating:
                break

    # ========================================================
    # FINISH PAUSE
    # ========================================================

    for _ in range(
        FINISH_PAUSE_STEPS
    ):

        frames.append(
            frame(body)
        )

    # ========================================================
    # RETURN TO START
    # ========================================================

    """
    We do not simply teleport the snake.

    The snake head travels through the reverse of its
    previously visited head trajectory.

    To keep this safe and visually clean, the return phase
    is intentionally a RESET phase: the body contracts while
    the head travels toward the starting area.
    """

    # Create a safe route from current head to start.
    return_path = find_path(
        body[0],
        start,
        body,
        width,
        height,
    )

    if return_path is None:

        # If the fully grown body blocks a direct return,
        # use a clean reset path independent of the body.
        return_path = find_path(
            body[0],
            start,
            [],
            width,
            height,
        )

    if return_path:

        for nxt in return_path:

            if len(body) > 1:

                # Move normally while shrinking one segment
                # at a time during reset.
                body = [
                    nxt
                ] + body[:-1]

            else:

                body = [
                    nxt
                ]

            frames.append(
                frame(body)
            )

    # Ensure exact start.
    body = [start]

    frames.append(
        frame(body)
    )

    # ========================================================
    # RESET PAUSE
    # ========================================================

    for _ in range(
        RESET_PAUSE_STEPS
    ):

        frames.append(
            frame(body)
        )

    return (
        frames,
        eaten_cells,
    )


# ============================================================
# BUILD SVG
# ============================================================

def build_svg(
    grid,
    frames,
    n_weeks,
    n_days,
):
    """
    Generates transparent SVG.

    No black background rectangle is created.
    """

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

    total_frames = len(frames)

    duration = (
        max(
            total_frames - 1,
            1
        )
        * STEP_TIME
    )

    duration = round(
        duration,
        3
    )

    # --------------------------------------------------------
    # Time keys.
    # --------------------------------------------------------

    times = [
        round(
            i / (total_frames - 1),
            6
        )
        for i in range(total_frames)
    ]

    key_times = ";".join(
        str(t)
        for t in times
    )

    def xy(cell):

        return (
            PAD_X + cell[0] * CELL,
            PAD_Y + cell[1] * CELL,
        )

    # ========================================================
    # EAT EVENTS
    # ========================================================

    eat_times = {}

    for index, current_frame in enumerate(frames):

        eaten = current_frame["eaten"]

        if (
            eaten is not None
            and eaten not in eat_times
        ):

            eat_times[eaten] = times[index]

    # ========================================================
    # SVG START
    # ========================================================

    svg = []

    svg.append(
        f'<svg '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="{width}" '
        f'height="{height}">'
    )

    # ========================================================
    # FILTERS
    # ========================================================

    svg.append(
        """
        <defs>

            <filter
                id="glow"
                x="-100%"
                y="-100%"
                width="300%"
                height="300%"
            >
                <feGaussianBlur
                    stdDeviation="2.2"
                    result="blur"
                />

                <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                </feMerge>
            </filter>

            <filter
                id="strongGlow"
                x="-200%"
                y="-200%"
                width="400%"
                height="400%"
            >
                <feGaussianBlur
                    stdDeviation="3.5"
                    result="blur"
                />

                <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                </feMerge>
            </filter>

        </defs>
        """
    )

    # ========================================================
    # CONTRIBUTION CELLS
    # ========================================================

    svg.append(
        '<g id="contributions">'
    )

    for cell, level in grid.items():

        x, y = xy(cell)

        rx = x - SIZE / 2
        ry = y - SIZE / 2

        color = LEVEL_COLORS[level]

        # ----------------------------------------------------
        # NEVER EATEN
        # ----------------------------------------------------

        if cell not in eat_times:

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
        # EATEN CELL
        # ----------------------------------------------------

        eat_t = eat_times[cell]

        # The key trick:
        #
        # 0 → visible
        # eat time → visible
        # immediately after eat → invisible
        # until the loop ends
        # loop restart → visible again
        #
        # This guarantees the bead comes back every cycle.

        after_eat = min(
            eat_t + 0.0005,
            0.999999
        )

        svg.append(
            f'<rect '
            f'x="{rx}" '
            f'y="{ry}" '
            f'width="{SIZE}" '
            f'height="{SIZE}" '
            f'rx="2" '
            f'fill="{color}" '
            f'filter="url(#glow)">'

            f'<animate '
            f'attributeName="opacity" '
            f'keyTimes="0;{eat_t};{after_eat};1" '
            f'values="1;1;0;0" '
            f'calcMode="discrete" '
            f'dur="{duration}s" '
            f'repeatCount="indefinite"/>'

            '</rect>'
        )

        # ----------------------------------------------------
        # EAT BURST
        # ----------------------------------------------------

        burst_end = min(
            eat_t + 0.018,
            1.0
        )

        svg.append(
            f'<circle '
            f'cx="{x}" '
            f'cy="{y}" '
            f'r="0" '
            f'fill="none" '
            f'stroke="{color}" '
            f'stroke-width="1.5" '
            f'opacity="0" '
            f'filter="url(#strongGlow)">'

            f'<animate '
            f'attributeName="r" '
            f'keyTimes="0;{eat_t};{burst_end};1" '
            f'values="0;{SIZE / 2};{SIZE * 1.5};{SIZE * 1.5}" '
            f'dur="{duration}s" '
            f'repeatCount="indefinite"/>'

            f'<animate '
            f'attributeName="opacity" '
            f'keyTimes="0;{eat_t};{burst_end};1" '
            f'values="0;0.9;0;0" '
            f'dur="{duration}s" '
            f'repeatCount="indefinite"/>'

            '</circle>'
        )

    svg.append(
        '</g>'
    )

    # ========================================================
    # SNAKE
    # ========================================================

    max_length = max(
        len(f["body"])
        for f in frames
    )

    svg.append(
        '<g id="snake">'
    )

    # Draw tail first.
    # Draw head last.
    for segment_index in range(
        max_length - 1,
        -1,
        -1
    ):

        x_values = []
        y_values = []
        opacity_values = []

        for current_frame in frames:

            body = current_frame["body"]

            if (
                segment_index
                < len(body)
            ):

                cell = body[
                    segment_index
                ]

                x, y = xy(cell)

                x_values.append(
                    str(
                        x
                        - (
                            SIZE + 1
                        ) / 2
                    )
                )

                y_values.append(
                    str(
                        y
                        - (
                            SIZE + 1
                        ) / 2
                    )
                )

                opacity_values.append(
                    "1"
                )

            else:

                # Segment hasn't been created yet.
                #
                # Keep it at the tail position,
                # but hide it.

                body_tail = body[-1]

                x, y = xy(
                    body_tail
                )

                x_values.append(
                    str(
                        x
                        - (
                            SIZE + 1
                        ) / 2
                    )
                )

                y_values.append(
                    str(
                        y
                        - (
                            SIZE + 1
                        ) / 2
                    )
                )

                opacity_values.append(
                    "0"
                )

        # ----------------------------------------------------
        # HEAD
        # ----------------------------------------------------

        if segment_index == 0:

            segment_size = (
                SIZE + 2.5
            )

            radius = 2.8

            fill = (
                SNAKE_HEAD_COLOR
            )

        # ----------------------------------------------------
        # BODY
        # ----------------------------------------------------

        else:

            segment_size = (
                SIZE + 1
            )

            radius = 2.4

            fill = SNAKE_COLOR

        svg.append(
            f'<rect '
            f'width="{segment_size}" '
            f'height="{segment_size}" '
            f'rx="{radius}" '
            f'fill="{fill}" '
            f'filter="url(#glow)">'

            f'<animate '
            f'attributeName="x" '
            f'keyTimes="{key_times}" '
            f'values="{";".join(x_values)}" '
            f'calcMode="discrete" '
            f'dur="{duration}s" '
            f'repeatCount="indefinite"/>'

            f'<animate '
            f'attributeName="y" '
            f'keyTimes="{key_times}" '
            f'values="{";".join(y_values)}" '
            f'calcMode="discrete" '
            f'dur="{duration}s" '
            f'repeatCount="indefinite"/>'

            f'<animate '
            f'attributeName="opacity" '
            f'keyTimes="{key_times}" '
            f'values="{";".join(opacity_values)}" '
            f'calcMode="discrete" '
            f'dur="{duration}s" '
            f'repeatCount="indefinite"/>'

            '</rect>'
        )

        # ====================================================
        # EYES
        # ====================================================

        if segment_index == 0:

            eye_x = []
            eye_y = []
            eye_opacity = []

            for current_frame in frames:

                body = current_frame[
                    "body"
                ]

                if body:

                    x, y = xy(
                        body[0]
                    )

                    eye_x.append(
                        str(
                            x + 2.2
                        )
                    )

                    eye_y.append(
                        str(
                            y - 2.2
                        )
                    )

                    eye_opacity.append(
                        "1"
                    )

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
                f'dur="{duration}s" '
                f'repeatCount="indefinite"/>'

                f'<animate '
                f'attributeName="cy" '
                f'keyTimes="{key_times}" '
                f'values="{";".join(eye_y)}" '
                f'calcMode="discrete" '
                f'dur="{duration}s" '
                f'repeatCount="indefinite"/>'

                f'<animate '
                f'attributeName="opacity" '
                f'keyTimes="{key_times}" '
                f'values="{";".join(eye_opacity)}" '
                f'calcMode="discrete" '
                f'dur="{duration}s" '
                f'repeatCount="indefinite"/>'

                '</circle>'
            )

    svg.append(
        '</g>'
    )

    # ========================================================
    # CLOSE SVG
    # ========================================================

    svg.append(
        '</svg>'
    )

    return "".join(svg)


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) < 3:

        print(
            "Usage: "
            "python3 generate_snake.py "
            "<github_username> "
            "<output.svg>"
        )

        sys.exit(1)

    username = sys.argv[1]
    output_path = sys.argv[2]

    print(
        f"Fetching GitHub contributions "
        f"for @{username}..."
    )

    grid, n_weeks, n_days = fetch_grid(
        username
    )

    active = sum(
        1
        for level in grid.values()
        if level > 0
    )

    print(
        f"Grid: "
        f"{n_weeks} × {n_days}"
    )

    print(
        f"Active contribution squares: "
        f"{active}"
    )

    print(
        "Simulating Snake..."
    )

    frames, eaten = simulate_run(
        grid,
        n_weeks,
        n_days,
    )

    print(
        f"Animation frames: "
        f"{len(frames)}"
    )

    print(
        f"Squares eaten: "
        f"{len(eaten)}"
    )

    print(
        "Building SVG..."
    )

    svg = build_svg(
        grid,
        frames,
        eaten,
        n_weeks,
        n_days,
    )

    output_dir = os.path.dirname(
        os.path.abspath(
            output_path
        )
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(svg)

    print(
        f"✓ Wrote {output_path}"
    )

    print(
        f"✓ SVG size: "
        f"{len(svg):,} bytes"
    )


if __name__ == "__main__":
    main()
