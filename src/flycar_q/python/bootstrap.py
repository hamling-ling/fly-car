"""Put the flycar package on sys.path for this app.

A checkout is found by walking up to ``src/flycar``. On the board, copy that
package to ``~/ArduinoApps/flycar_q/python/flycar`` and the import succeeds
without this search.
"""

from __future__ import annotations

import sys
from pathlib import Path


def install() -> None:
    try:
        import flycar.behavior  # noqa: F401
    except ImportError:
        pass
    else:
        return
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "flycar" / "behavior.py").exists():
            candidate = parent
        elif (parent / "src" / "flycar" / "behavior.py").exists():
            candidate = parent / "src"
        else:
            continue
        entry = str(candidate)
        if entry not in sys.path:
            sys.path.insert(0, entry)
        return
    raise ImportError(
        "flycar が見つからない。src/flycar を "
        "~/ArduinoApps/flycar_q/python/flycar に置くか、リポジトリごと置いてから起動する。"
    )
