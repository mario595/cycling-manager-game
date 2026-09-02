from __future__ import annotations

import json
import os
import sys
import termios
import time
import tty
from typing import Any


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

    # Course profile bar
    bar_width = 60
    profile_chars = []
    for seg in segments:
        seg_chars = max(1, int(seg["length"] / course_length * bar_width))
        grad = seg["gradient"]
        if grad > 0:
            profile_chars.extend(["\u2207"] * seg_chars)
        elif grad < 0:
            profile_chars.extend(["\u2202"] * seg_chars)
        else:
            profile_chars.extend(["="] * seg_chars)
    profile = "".join(profile_chars[:bar_width])

    print(f"  Course  [{profile}]")

    # Distance scale
    scale_positions = [0, 0.25, 0.5, 0.75, 1.0]
    scale_display = ""
    for i, frac in enumerate(scale_positions):
        label = f"{course_length * frac / 1000:.1f}km"
        if i == 0:
            scale_display = label
        else:
            char_pos = int(frac * bar_width)
            scale_display += " " * (char_pos - len(scale_display)) + label
    print(f"  {scale_display}")
    print()

    # Rider progress
    for r in riders:
        name = r["name"]
        pos = r["pos"]
        energy = r["energy"]
        stamina = r["stamina"]
        finished = r["finished"]

        progress = pos / course_length if course_length > 0 else 0
        bar_filled = min(bar_width, int(progress * bar_width))
        bar = "\u2588" * bar_filled + "\u2591" * (bar_width - bar_filled)

        status = "FIN" if finished else f"{progress * 100:.0f}%"
        e_bar = "\u2588" * int(energy / 10) + "\u2591" * (10 - int(energy / 10))
        s_bar = "\u2588" * int(stamina / 10) + "\u2591" * (10 - int(stamina / 10))

        print(
            f"  {name:10s} {bar} {status:>4s}  "
            f"E:{e_bar} {energy:5.1f}  S:{s_bar} {stamina:5.1f}"
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
