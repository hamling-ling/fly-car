"""Knobs for this car. The color ranges and the pulse scale live in flycar."""

# True when the picture's left is the car's right.
MIRROR = False

# Membrane window. Image counts stay put between these calls.
TICK_S = 0.02

# How often a new frame is read into the counts. Slower than the membrane.
COUNT_S = 0.10

# Idle heartbeat. While the sheet, the rates, or the wheels are active,
# main.py also prints every DETAIL_S and whenever the command changes.
LOG_S = 1.0
DETAIL_S = 0.10

# Frames to drop before the first command. Exposure is still climbing.
WARMUP_FRAMES = 20
