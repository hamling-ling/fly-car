"""Poster figure: LPLC2 somas, lobula-plate postsynapses, and the camera plane.

The layout matches fig7. LPLC2 junctions sit on lobula-plate squares (a, b),
with the same orientation as LC4: larger a is more lateral, smaller b is up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import draw_fig7


def main() -> None:
    draw_fig7.render(draw_fig7.LPLC2)


if __name__ == "__main__":
    main()
