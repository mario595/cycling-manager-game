"""deploy/tick.sh survives the SIGTERM a machine stop sends it (#136).

The entrypoint gives a running tick STOP_GRACE (90 s) to finish, but on Fly the
stop's SIGTERM reached the tick directly and killed it at once. tick.sh ignores
it; this runs the script's own preamble around a stand-in for the tick and
signals it mid-run.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

TICK_SH = Path(__file__).resolve().parents[1] / "tick.sh"


def test_the_tick_ignores_sigterm(tmp_path):
    script = TICK_SH.read_text()
    assert "trap '' TERM" in script
    assert script.index("trap '' TERM") < script.index("python manage.py tick")
    stand_in = tmp_path / "tick.sh"
    stand_in.write_text(
        script.replace("cd /app", f"cd {tmp_path}").replace(
            "python manage.py tick",
            f"{sys.executable} -c 'import time; time.sleep(1.5); open(\"done\", \"w\")'",
        )
    )
    proc = subprocess.Popen(["sh", str(stand_in)], start_new_session=True,
                            env={"PATH": "/usr/bin:/bin"})
    time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGTERM)  # the script and its child, as on Fly
    assert proc.wait(timeout=10) == 0
    assert (tmp_path / "done").exists()
