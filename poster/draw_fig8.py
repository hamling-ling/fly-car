"""LPLC2 now shares poster/fig7_lobula with LC4.

Both rear views are drawn by draw_fig7.render_pair. This entry point writes
that same sheet, so an older fig8 command still refreshes the combined figure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import draw_fig7


def main() -> None:
    draw_fig7.render_pair()


if __name__ == "__main__":
    main()
