from __future__ import annotations

import json
import os
import sys
import termios
import time
import tty
from typing import Any

# ANSI colors — only used when output is a TTY.
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"

# Terrain grade buckets (gradient %) mapped to a color. Blue-ish for downhill,
# green/cyan around flat, orange and red for positive grades. Buckets are
# inclusive at the lower bound: g in [lo, hi).
_GRADE_COLORS: list[tuple[float, float, str]] = [
    (-99.0, -15.0, "\033[34m"),    # very steep downhill -> dark blue
    (-15.0, -10.0, "\033[38;5;33m"),  # steep downhill -> blue
    (-10.0, -5.0, "\033[38;5;81m"),   # downhill -> light blue
    (-5.0, 0.0, "\033[38;5;45m"),     # mild downhill / near flat -> cyan
    (0.0, 5.0, _GREEN),              # flat -> green
    (5.0, 10.0, _YELLOW),            # rolling uphill -> yellow
    (10.0, 15.0, "\033[38;5;214m"),  # steep uphill -> orange
    (15.0, 99.0, "\033[31m"),        # steepest uphill -> red
]


def _grade_color(gradient: float) -> str:
    """Return the ANSI color code for a gradient bucket (always non-empty)."""
    for lo, hi, code in _GRADE_COLORS:
        if lo <= gradient < hi:
            return code
    return _GREEN


def _color(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _terrain_cells(
    segments: list[dict[str, Any]], course_length: float, width: int
) -> list[float]:
    """Map the course onto `width` cells; each cell holds the gradient (%) of
    the course segment covering that cell's position."""
    if course_length <= 0:
        return [0.0] * width
    cells = []
    for seg in segments:
        seg_chars = max(1, int(seg["length"] / course_length * width))
        cells.extend([seg["gradient"]] * seg_chars)
    cells = cells[:width]
    # Pad with flat (0.0) if the course doesn't fully cover `width` cells so the
    # caller can always index terrain[0..width).
    while len(cells) < width:
        cells.append(0.0)
    return cells


def _load_log(path: str) -> list[dict[str, Any]]:
    frames = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                frames.append(json.loads(line))
    return frames


def _get_key() -> str:
    if not sys.stdin.isatty():
        # Non-interactive: read a single char from the pipe.
        ch = sys.stdin.read(1)
        if not ch:
            return "quit"  # EOF
        return ch

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "C":
                    return "right"
                elif ch3 == "D":
                    return "left"
            return "escape"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _render_frame(
    frame: dict[str, Any],
    speed_label: str,
    auto_play: bool,
    max_time: int,
    clear_screen: bool = True,
) -> None:
    if clear_screen:
        os.system("clear")

    course_length = frame["course_length"]
    segments = frame["segments"]
    riders = frame["riders"]
    t = frame["time"]

    pct = int((t / max_time) * 100) if max_time > 0 else 0
    print(f"Race Viewer — t={t}s / ~{max_time}s ({pct}%)")
    print()

    # Shared layout: every bar (course profile, rider progress, scale) starts at
    # the same column so a rider can be read against the terrain directly.
    bar_width = 60
    name_w = 10
    bar_indent = "  " + " " * (name_w + 1)  # 13 columns before the bar glyphs

    # Course profile bar — colored by terrain grade. The "[" occupies column 12
    # so the profile glyphs align exactly with rider progress bars.
    terrain = _terrain_cells(segments, course_length, bar_width)
    profile_chars = []
    for grad in terrain:
        glyph = "\u2207" if grad > 0 else ("\u2202" if grad < 0 else "=")
        if _is_tty():
            profile_chars.append(f"{_grade_color(grad)}{glyph}")
        else:
            profile_chars.append(glyph)
    profile = "".join(profile_chars) + (_RESET if _is_tty() else "")
    course_label = "  " + "Course".ljust(name_w)  # "[" lands on column 12
    print(f"{course_label}[{profile}]")

    # Distance scale — aligned under the bar band.
    scale_positions = [0, 0.25, 0.5, 0.75, 1.0]
    scale_display = ""
    for i, frac in enumerate(scale_positions):
        label = f"{course_length * frac / 1000:.1f}km"
        if i == 0:
            scale_display = label
        else:
            char_pos = int(frac * bar_width)
            scale_display += " " * max(0, char_pos - len(scale_display)) + label
    print(f"{bar_indent}{scale_display}")
    print()

    # Rider progress — sorted by position (front first) so the gap column
    # always refers to the row directly above.
    sorted_riders = sorted(riders, key=lambda r: r["pos"], reverse=True)

    for k, r in enumerate(sorted_riders):
        name = r["name"]
        pos = r["pos"]
        speed = r.get("speed", 0.0)
        energy = r["energy"]
        stamina = r["stamina"]
        finished = r["finished"]
        drafting = r.get("drafting", False)
        pulling = r.get("pulling", False)

        # Truncate long names so columns stay aligned.
        if len(name) > name_w:
            name = name[:5] + ".." + name[-1]

        progress = pos / course_length if course_length > 0 else 0
        bar_filled = min(bar_width, int(progress * bar_width))

        # Filled portion colored by the terrain each cell lies on; the rest is
        # the neutral "unridden" filler.
        bar = ""
        tty = _is_tty()
        current_code: str | None = None
        for cell_i in range(bar_width):
            if cell_i < bar_filled:
                if tty:
                    code = _grade_color(terrain[cell_i])
                    if code != current_code:
                        bar += code
                        current_code = code
                bar += "\u2588"
            else:
                if tty and current_code is not None:
                    bar += _RESET
                    current_code = None
                bar += "\u2591"
        if tty and current_code is not None:
            bar += _RESET

        # Status at a fixed visible width (3 chars) + a fixed marker slot (2 chars)
        # so appearing P/* markers don't shift the layout.
        if finished:
            status = "FIN"
            marker = ""
        else:
            status = f"{progress * 100:.0f}%"
            if pulling:
                marker = _color("P ", _GREEN)
            elif drafting:
                marker = _color("* ", _YELLOW)
            else:
                marker = "  "

        # Gap to the rider directly ahead (front rider has no one ahead).
        if k == 0:
            gap_disp = "+----   --"
        else:
            prev = sorted_riders[k - 1]
            gap_m = prev["pos"] - pos
            gap_t = gap_m / speed if speed > 0 else 0.0
            gap_disp = f"+{gap_m:6.1f}m {int(gap_t):3d}s"

        e_bar = "\u2588" * int(energy / 10) + "\u2591" * (10 - int(energy / 10))
        s_bar = "\u2588" * int(stamina / 10) + "\u2591" * (10 - int(stamina / 10))

        print(
            f"  {name:<{name_w}s} {bar} {status:>3s}{marker} "
            f"{gap_disp:>13s}  E:{e_bar} {energy:5.1f}  S:{s_bar} {stamina:5.1f}"
        )

    print()
    mode = "Auto-play: ON " if auto_play else "Auto-play: OFF"
    print(f"  [{mode} | Speed: {speed_label}]")
    print("  \u2190 \u2192 step | Space toggle auto-play | 1-5 speed | q quit")


def _read_key_timeout(timeout: float) -> str | None:
    """Return a key pressed within the timeout, or None. Works for TTY and pipe."""
    if not sys.stdin.isatty():
        import select

        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        if not ch:
            return None
        return ch

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        import select

        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def play(path: str, start_speed: int = 1) -> None:
    frames = _load_log(path)
    if not frames:
        print("Empty log file.")
        return

    speed_options = [1, 5, 10, 30, 60]
    speed_index = 0
    for i, s in enumerate(speed_options):
        if s == start_speed:
            speed_index = i
            break

    current = 0
    auto_play = False
    running = True
    max_time = frames[-1]["time"]

    while running:
        frame = frames[current]
        speed_label = f"x{speed_options[speed_index]}"
        _render_frame(frame, speed_label, auto_play, max_time)

        if auto_play:
            # Read key with timeout, advance by speed ticks per frame
            delay = 0.05  # 50ms real time per frame
            steps = speed_options[speed_index]

            ch = _read_key_timeout(delay)
            if ch is None:
                pass
            elif ch == "q":
                running = False
                continue
            elif ch == " ":
                auto_play = False
                continue
            elif ch in "12345":
                speed_index = int(ch) - 1
                continue

            current = min(current + steps, len(frames) - 1)
            if current >= len(frames) - 1:
                auto_play = False
        else:
            key = _get_key()
            if key in ("q", "quit"):
                running = False
            elif key == "right":
                current = min(current + 1, len(frames) - 1)
            elif key == "left":
                current = max(current - 1, 0)
            elif key == " ":
                auto_play = True
            elif key in "12345":
                speed_index = int(key) - 1

    # Restore terminal
    os.system("clear")
    print("Race finished.")


def dump(path: str, frame_index: int | None = None) -> None:
    frames = _load_log(path)
    if not frames:
        print("Empty log file.")
        return

    if frame_index is None:
        frame_index = len(frames) - 1
    frame_index = max(0, min(frame_index, len(frames) - 1))
    _render_frame(
        frames[frame_index], "x1", False, frames[-1]["time"], clear_screen=False
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m race_engine.player <log_file> [--speed N] [--dump [frame]]")
        sys.exit(1)

    path = sys.argv[1]
    speed = 1
    if "--speed" in sys.argv:
        idx = sys.argv.index("--speed")
        if idx + 1 < len(sys.argv):
            speed = int(sys.argv[idx + 1])

    if "--dump" in sys.argv:
        idx = sys.argv.index("--dump")
        frame_index = None
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            frame_index = int(sys.argv[idx + 1])
        dump(path, frame_index)
        return

    play(path, start_speed=speed)


if __name__ == "__main__":
    main()
