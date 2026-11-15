"""Parametric wall mount for the Raspberry Pi Monitor with a hidden Raspberry Pi 5.

Run:  python hardware/mount.py      (needs build123d; writes hardware/out/)

Parts (printed in PETG):
  tray        bolts to the monitor's VESA 100 holes; holds the Pi; skirt hides the cavity
  tray-cleat  French-cleat hook, screwed to the back of the tray (M3 heat-set inserts)
  wall-cleat  screwed to the wall (drywall anchors); the tray hangs on it
  spacer      bottom bar on the back of the tray, keeps it parallel to the wall
  fit-vesa    quick print to check the VESA hole pattern and M4 screws
  fit-pi      quick print to check the Pi 5 hole pattern and M2.5 inserts

Coordinates (mm), "monitor frame": looking at the BACK of the monitor (as in Raspberry
Pi's rear-view drawing), X to the right with 0 at the centre, Y up from the monitor's
bottom edge, Z from the monitor's VESA surface towards the wall.

Monitor numbers come from Raspberry Pi's product brief (RP-008219-DS) and are marked
approximate. Check every MONITOR value against the real monitor before printing the tray.
"""

from pathlib import Path

from build123d import (Box, Compound, Cone, Cylinder, Mesher, Plane, Polygon, Pos, Rot,
                       RectangleRounded, Text, export_step, export_stl, extrude)

OUT = Path(__file__).parent / "out"

# --- Monitor (datasheet, approximate: verify) ---------------------------------
MON_W, MON_H = 360, 237
MON_BUMP_H = 127          # height of the 20 mm-thick lower rear section
MON_STEP = 10             # the upper rear is this much thinner than the lower section
VESA = 100                # hole pattern, square
VESA_ROWS = (12.5, 112.5) # hole rows, mm above the bottom edge
CENTRE_CLEAR = 42         # keep |X| < this free: connectors under the stand, flipped stand
STAND_HALF_W = 37         # flipped-up stand: about ±37 mm wide (drawing)...
STAND_PROUD = 12          # ...and 12 mm off the upper back (measured), i.e. 2 mm past the bump

# --- Mount ---------------------------------------------------------------------
CAVITY = 28               # monitor VESA surface to tray plate. The monitor's plugs enter
                          # sideways and lie flat, so this only has to fit the Pi and its fan
PLATE_T = 4               # tray plate thickness
WALL_T = 2.4              # skirt wall thickness
TRAY_W = 300
TRAY_Y0, TRAY_Y1 = 2, 215 # tray extent in Y (monitor frame)
TRAY_R = 10               # corner radius
MON_GAP = 3               # skirt stops this short of the monitor
NOTCH_W = 50              # cable exit in the bottom skirt, centred
VENT_W, VENT_PITCH = 6, 12

VESA_POST_R = 7
M4_CLEAR, M4_HEAD_D, M4_HEAD_H = 4.5, 8.5, 4.0
# The monitor's VESA holes are metal inserts only 5 mm deep (measured), so the screw
# must stop short of the bottom. Pick the longest screw from the M4 kit that leaves
# M4_ENGAGE of thread in the hole while its head still sits fully inside the post,
# and recess the head as deep as needed to make that length come out right.
VESA_HOLE_DEPTH = 5
M4_ENGAGE = VESA_HOLE_DEPTH - 1
M4_KIT = (30, 35, 40, 45, 50)
_POST_H = PLATE_T + CAVITY
M4_SCREW_L = max(L for L in M4_KIT if _POST_H - (L - M4_ENGAGE) >= M4_HEAD_H + 0.5)
M4_RECESS = _POST_H - (M4_SCREW_L - M4_ENGAGE)   # head counterbore depth from the tray's back

# Pi 5: board 85 x 56, M2.5 holes 3.5 mm in from the edge opposite the USB/Ethernet end.
PI_W, PI_H = 85, 56
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
PI_X0, PI_Y0 = 65, 145    # monitor frame: X of the boss pattern's inner edge minus 3.5, and the
                          # board's HDMI edge. Puts the USB end clear of the flipped-up stand
PI_BOSS_R, PI_BOSS_H = 3.5, 6
PCB_T = 1.6
# Screws from the Swpeet N8 kit: M2.5 x 8 for the Pi, M3 x 12 for the cleat and spacer.
# Hole depths and pads below are derived from these so the screws clamp before bottoming out.
PI_SCREW_L = 8
M25_INSERT_D = 3.6
M25_INSERT_DEPTH = PI_SCREW_L - PCB_T + 1      # screw tip clears the bottom of the hole by 1 mm

# Board orientation: component side faces the monitor, HDMI/USB-C edge down. Seen from
# the back that puts the SD-card end at the right and the USB/Ethernet end towards the
# centre. "Board-local" coordinates: x from the SD-card end, y up from the HDMI edge.
PI_SD_END_X = PI_X0 + 65                       # monitor-frame X of the SD-card end


def board_to_monitor(lx, ly):
    """Board-local (x, y) to monitor-frame (X, Y)."""
    return PI_SD_END_X - lx, PI_Y0 + ly


# Fan bracket: holds the official Pi 5 case fan (30 x 30 x 7 mm) over the SoC, blowing
# down onto its heatsink. SoC position measured from a photo of the board.
SOC_X, SOC_Y = 33.2, 20.8                      # board-local centre of the SoC
HEATSINK_H = 6.5                               # official case heatsink: 4 mm on the ~2 mm SoC package + pad
HEATSINK_W, HEATSINK_D = 17, 12                # its footprint (board-local x, y)
FAN_S, FAN_T, FAN_HOLE_PITCH = 30, 7, 24
BRACKET_T = 3
# The fan's screw heads (3 mm) hang under the bracket, over the board's connectors
# (CAM/DISP ribbon sockets ~5 mm, HDMI ~3.5 mm), so the bracket clears those as
# well as the heatsink.
FAN_SCREW_HEAD_H = 3
BOARD_PARTS_H = 6.5                            # tallest connector under the bracket, with margin
BRACKET_ABOVE_PCB = max(HEATSINK_H + 2, BOARD_PARTS_H + FAN_SCREW_HEAD_H + 0.5)
BRACKET_Z = PLATE_T + PI_BOSS_H + PCB_T + BRACKET_ABOVE_PCB   # tray print-frame Z of its underside
FAN_POSTS = [(-6, 6), (-6, 42)]                # board-local, past the SD-card end, clear of the slot
FAN_POST_R = 4

# French cleat, both halves share one 8 mm layer between tray and wall.
CLEAT_W, CLEAT_T = 240, 8
TRAY_CLEAT_TOP = TRAY_Y1 - 2
TRAY_CLEAT_H = 40         # at the wall side
WALL_CLEAT_H = 40         # at the wall side
CLEAT_FIT = 0.5           # clearance between the two 45° faces
CLEAT_SCREW_X = (-115, -40, 40, 115)
CLEAT_SCREW_Y = TRAY_Y1 - 10
M3_CLEAR, M3_INSERT_D = 3.4, 4.2
M3_SCREW_L = 12
M3_ENGAGE = 6                                  # thread into the cleat/spacer insert
M3_PAD_H = M3_SCREW_L - M3_ENGAGE - PLATE_T    # raised pad inside the tray under each screw head
M3_INSERT_DEPTH = M3_ENGAGE + 0.5
FAN_POST_INSERT_DEPTH = M3_SCREW_L - BRACKET_T + 1   # M3 x 12 through the bracket into the post
WALL_SCREW_X = (-100, -35, 35, 100)
WALL_SCREW_D, WALL_SCREW_HEAD_D = 4.5, 9  # #8 / 4 mm flat-head screws into anchors

SPACER_W, SPACER_H = 200, 20
SPACER_SCREW_X = (-80, 80)
SPACER_SLOT_W = M4_HEAD_D + 3   # hex-key access to the lower VESA screws through the spacer
assert all(abs(abs(x) - VESA / 2) > SPACER_SLOT_W / 2 + M3_INSERT_D for x in SPACER_SCREW_X), \
    "spacer slots run into its screw inserts"

BACK_Z = CAVITY + PLATE_T           # monitor-frame Z of the tray's back face
WALL_Z = BACK_Z + CLEAT_T           # monitor-frame Z of the wall

# Screw-length sanity: holes must stop short of breaking through their part.
assert M25_INSERT_DEPTH <= PLATE_T + PI_BOSS_H - 1.5, "M2.5 screw too long for the Pi bosses"
assert M3_INSERT_DEPTH <= CLEAT_T - 1, "M3 screw too long for the cleat/spacer bars"
assert M3_PAD_H >= 0, "M3 screw too short to reach the inserts"
assert _POST_H - M4_RECESS >= 10, "too little post left under the M4 screw head"
assert BRACKET_Z - FAN_POST_INSERT_DEPTH >= PLATE_T + 1, "fan posts too short for their inserts"
FAN_INTAKE_GAP = (PLATE_T + CAVITY + MON_STEP) - (BRACKET_Z + BRACKET_T + FAN_T)
assert FAN_INTAKE_GAP >= 5, f"only {FAN_INTAKE_GAP:.1f} mm between the fan and the monitor"


def vesa_holes():
    return [(sx * VESA / 2, y) for y in VESA_ROWS for sx in (-1, 1)]


def pi_holes():
    return [(PI_X0 + hx, PI_Y0 + hy) for hx, hy in PI_HOLES]


# All parts are modelled in their print orientation (bed at Z=0). The tray's print
# frame looks at it from the monitor side, so X is mirrored relative to the monitor frame.

def tray():
    h, cy = TRAY_Y1 - TRAY_Y0, (TRAY_Y0 + TRAY_Y1) / 2
    skirt_h = CAVITY - MON_GAP
    outline = RectangleRounded(TRAY_W, h, TRAY_R)
    inner = RectangleRounded(TRAY_W - 2 * WALL_T, h - 2 * WALL_T, TRAY_R - WALL_T)
    body = Pos(0, cy, 0) * extrude(outline, PLATE_T)
    body += Pos(0, cy, PLATE_T) * extrude(outline - inner, skirt_h)

    # Vertical vent slots in the top and bottom skirts (short bridges print cleanly).
    vent_h = skirt_h - 10
    for i in range(-11, 12):
        x = i * VENT_PITCH
        for y in (TRAY_Y0 + WALL_T / 2, TRAY_Y1 - WALL_T / 2):
            if abs(x) > TRAY_W / 2 - TRAY_R - VENT_W or (y < cy and abs(x) < NOTCH_W / 2 + VENT_PITCH):
                continue
            body -= Pos(x, y, PLATE_T + 5 + vent_h / 2) * Box(VENT_W, WALL_T * 3, vent_h)
    # Cable exit, bottom centre.
    body -= Pos(0, TRAY_Y0 + WALL_T / 2, PLATE_T + 1 + skirt_h / 2) * Box(NOTCH_W, WALL_T * 3, skirt_h)

    # VESA posts: M4 through, socket head recessed into the back.
    post_h = PLATE_T + CAVITY
    for x, y in vesa_holes():
        body += Pos(-x, y, post_h / 2) * Cylinder(VESA_POST_R, post_h)
    for x, y in vesa_holes():
        body -= Pos(-x, y, post_h / 2) * Cylinder(M4_CLEAR / 2, post_h + 2)
        body -= Pos(-x, y, M4_RECESS / 2) * Cylinder(M4_HEAD_D / 2, M4_RECESS + 0.01)

    # Pi 5 bosses with M2.5 heat-set inserts.
    boss_top = PLATE_T + PI_BOSS_H
    for x, y in pi_holes():
        body += Pos(-x, y, boss_top / 2) * Cylinder(PI_BOSS_R, boss_top)
    for x, y in pi_holes():
        body -= Pos(-x, y, boss_top - M25_INSERT_DEPTH / 2) * Cylinder(M25_INSERT_D / 2, M25_INSERT_DEPTH + 0.01)

    # Posts for the fan bracket, past the Pi's SD-card end, with M3 inserts on top.
    for lx, ly in FAN_POSTS:
        x, y = board_to_monitor(lx, ly)
        body += Pos(-x, y, BRACKET_Z / 2) * Cylinder(FAN_POST_R, BRACKET_Z)
        body -= Pos(-x, y, BRACKET_Z - FAN_POST_INSERT_DEPTH / 2) * Cylinder(M3_INSERT_D / 2, FAN_POST_INSERT_DEPTH + 0.01)

    # Cleat and spacer bars are screwed on from inside the tray; a raised pad under each
    # screw head sets how far the screw reaches into the bar's insert.
    bar_screws = [(x, CLEAT_SCREW_Y) for x in CLEAT_SCREW_X] + [(x, TRAY_Y0 + 4 + SPACER_H / 2) for x in SPACER_SCREW_X]
    pad_top = PLATE_T + M3_PAD_H
    for x, y in bar_screws:
        body += Pos(-x, y, pad_top / 2) * Cylinder(4.5, pad_top)
    for x, y in bar_screws:
        body -= Pos(-x, y, pad_top / 2) * Cylinder(M3_CLEAR / 2, pad_top + 2)
    return body


def _cleat_bar(profile_yz):
    """Extrude a (Y, Z) profile, given in the monitor frame, across CLEAT_W."""
    pts = [(y, z) for y, z in profile_yz]
    return extrude(Plane.YZ * Polygon(*pts, align=None), CLEAT_W / 2, both=True)


def tray_cleat_monitor_frame():
    top, bot_wall = TRAY_CLEAT_TOP, TRAY_CLEAT_TOP - TRAY_CLEAT_H
    bar = _cleat_bar([(top, BACK_Z), (top, WALL_Z), (bot_wall, WALL_Z), (bot_wall + CLEAT_T, BACK_Z)])
    for x in CLEAT_SCREW_X:
        bar -= Pos(x, CLEAT_SCREW_Y, BACK_Z + M3_INSERT_DEPTH / 2) * Cylinder(M3_INSERT_D / 2, M3_INSERT_DEPTH + 0.01)
    return bar


def wall_cleat_monitor_frame():
    # Its 45° top face sits under the tray cleat's, CLEAT_FIT lower.
    top_wall = TRAY_CLEAT_TOP - TRAY_CLEAT_H - CLEAT_FIT
    bot = top_wall - WALL_CLEAT_H
    bar = _cleat_bar([(top_wall, WALL_Z), (top_wall + CLEAT_T, BACK_Z), (bot, BACK_Z), (bot, WALL_Z)])
    y = bot + (WALL_CLEAT_H - CLEAT_T) / 2
    for x in WALL_SCREW_X:
        bar -= Pos(x, y, (BACK_Z + WALL_Z) / 2) * Cylinder(WALL_SCREW_D / 2, CLEAT_T + 2)
        # Countersink on the room-facing side so flat-head screws sit flush.
        cs = (WALL_SCREW_HEAD_D - WALL_SCREW_D) / 2
        bar -= Pos(x, y, BACK_Z + cs / 2) * Rot(180, 0, 0) * Cone(WALL_SCREW_D / 2, WALL_SCREW_HEAD_D / 2, cs + 0.01)
    return bar


def spacer_monitor_frame():
    y0 = TRAY_Y0 + 4
    bar = Pos(0, y0 + SPACER_H / 2, (BACK_Z + WALL_Z) / 2) * Box(SPACER_W, SPACER_H, CLEAT_T)
    # The spacer lies over the lower VESA screw heads and its own screws go in from inside
    # the tray, so it goes on first: U-slots open at the bottom let a hex key reach the heads.
    vy = VESA_ROWS[0]
    for x, _ in vesa_holes()[:2]:
        bar -= Pos(x, vy, (BACK_Z + WALL_Z) / 2) * Cylinder(SPACER_SLOT_W / 2, CLEAT_T + 2)
        bar -= Pos(x, (y0 - 1 + vy) / 2, (BACK_Z + WALL_Z) / 2) * Box(SPACER_SLOT_W, vy - y0 + 1, CLEAT_T + 2)
    for x in SPACER_SCREW_X:
        bar -= Pos(x, y0 + SPACER_H / 2, BACK_Z + M3_INSERT_DEPTH / 2) * Cylinder(M3_INSERT_D / 2, M3_INSERT_DEPTH + 0.01)
    return bar


def to_print(part, flip):
    """Lay a monitor-frame cleat/spacer bar flat: the tray-side face (flip=False)
    or the wall-side face (flip=True) on the bed."""
    bb = part.bounding_box()
    if flip:
        part = Rot(0, 180, 0) * part
        bb = part.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * part


def fit_vesa():
    size, t = VESA + 30, 3
    plate = extrude(RectangleRounded(size, size, 6), t)
    plate -= extrude(RectangleRounded(VESA - 2 * VESA_POST_R - 6, VESA - 2 * VESA_POST_R - 6, 4), t)
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate -= Pos(sx * VESA / 2, sy * VESA / 2, t / 2) * Cylinder(M4_CLEAR / 2, t + 2)
    label = Pos(0, -VESA / 2 - 9, t) * extrude(Text("VESA 100 · M4", 6), 0.6)
    return plate + label


def fit_pi():
    # Same plate thickness and bosses as the tray, so this tests the real screw depth.
    plate = Pos(PI_W / 2 - 13, PI_H / 2, 0) * extrude(RectangleRounded(PI_W - 20, PI_H + 4, 4), PLATE_T)
    boss_top = PLATE_T + PI_BOSS_H
    for hx, hy in PI_HOLES:
        plate += Pos(hx, hy, boss_top / 2) * Cylinder(PI_BOSS_R, boss_top)
    for hx, hy in PI_HOLES:
        plate -= Pos(hx, hy, boss_top - M25_INSERT_DEPTH / 2) * Cylinder(M25_INSERT_D / 2, M25_INSERT_DEPTH + 0.01)
    return plate


def fan_bracket():
    """Flat plate in board-local coordinates: screws to the two fan posts and carries the
    fan over the SoC. The fan sits on top (towards the monitor); 4 x M3 x 12 go up through
    the bracket and the fan's corner holes, which are clearance-sized, into M3 nuts
    (two diagonal corners are enough)."""
    x0, x1 = FAN_POSTS[0][0] - FAN_POST_R - 1, SOC_X + FAN_S / 2 + 3
    y0, y1 = FAN_POSTS[0][1] - FAN_POST_R - 1, FAN_POSTS[1][1] + FAN_POST_R + 1
    plate = Pos((x0 + x1) / 2, (y0 + y1) / 2, 0) * extrude(RectangleRounded(x1 - x0, y1 - y0, 4), BRACKET_T)
    plate -= Pos(SOC_X, SOC_Y, BRACKET_T / 2) * Cylinder(FAN_S / 2 - 1.5, BRACKET_T + 2)   # airflow opening
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate -= Pos(SOC_X + sx * FAN_HOLE_PITCH / 2, SOC_Y + sy * FAN_HOLE_PITCH / 2, BRACKET_T / 2) * Cylinder(M3_CLEAR / 2, BRACKET_T + 2)
    for lx, ly in FAN_POSTS:
        plate -= Pos(lx, ly, BRACKET_T / 2) * Cylinder(M3_CLEAR / 2, BRACKET_T + 2)
    return plate


def parts():
    return {
        "tray": tray(),
        "tray-cleat": to_print(tray_cleat_monitor_frame(), flip=False),
        "wall-cleat": to_print(wall_cleat_monitor_frame(), flip=True),
        "spacer": to_print(spacer_monitor_frame(), flip=False),
        "fan-bracket": fan_bracket(),
        "fit-vesa": fit_vesa(),
        "fit-pi": fit_pi(),
    }


def assembly():
    """Everything in the monitor frame, plus simple reference bodies (not printed)."""
    to_monitor = Pos(0, 0, BACK_Z) * Rot(0, 180, 0)        # tray print frame -> monitor frame
    board_to_tray = Pos(-PI_SD_END_X, PI_Y0, 0)             # board-local -> tray print frame
    monitor = (Pos(0, MON_BUMP_H / 2, -10) * Box(MON_W, MON_BUMP_H, 20)
               + Pos(0, (MON_BUMP_H + MON_H) / 2, -15) * Box(MON_W, MON_H - MON_BUMP_H, 10))
    pcb_top = PLATE_T + PI_BOSS_H + PCB_T
    pi = Pos(PI_W / 2, PI_H / 2, pcb_top - PCB_T / 2) * Box(PI_W, PI_H, PCB_T)
    pi += Pos(PI_W - 8, PI_H / 2, pcb_top + 8) * Box(22, 53, 16)                  # USB/Ethernet, 2 mm overhang
    pi += Pos(SOC_X, SOC_Y, pcb_top + HEATSINK_H / 2) * Box(HEATSINK_W, HEATSINK_D, HEATSINK_H)
    fan = Pos(SOC_X, SOC_Y, BRACKET_Z + BRACKET_T + FAN_T / 2) * Box(FAN_S, FAN_S, FAN_T)
    # Flipped-up stand, lying on the upper back from the bump up to the top edge.
    stand_z0, stand_z1 = -MON_STEP, -MON_STEP + STAND_PROUD
    stand = Pos(0, (MON_BUMP_H + MON_H) / 2, (stand_z0 + stand_z1) / 2) * Box(2 * STAND_HALF_W, MON_H - MON_BUMP_H, STAND_PROUD)
    return {
        "tray": to_monitor * tray(),
        "tray-cleat": tray_cleat_monitor_frame(),
        "wall-cleat": wall_cleat_monitor_frame(),
        "spacer": spacer_monitor_frame(),
        "fan-bracket": to_monitor * board_to_tray * Pos(0, 0, BRACKET_Z) * fan_bracket(),
        "monitor (ref)": monitor,
        "pi (ref)": to_monitor * board_to_tray * pi,
        "fan (ref)": to_monitor * board_to_tray * fan,
        "stand (ref)": stand,
    }


def write_plate(path, built, layout):
    """Write a 3MF with each part rotated about Z and its bounding box's lower-left corner
    placed at (x, y), so the plate opens in the slicer already arranged."""
    mesher = Mesher()
    for name, rot, x, y in layout:
        part = Rot(0, 0, rot) * built[name]
        bb = part.bounding_box()
        mesher.add_shape(Pos(x - bb.min.X, y - bb.min.Y, -bb.min.Z) * part,
                         linear_deflection=0.02, angular_deflection=0.2)
    mesher.write(str(path))


def main():
    OUT.mkdir(exist_ok=True)
    built = parts()
    for name, part in built.items():
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"), tolerance=0.02, angular_tolerance=0.2)
        bb = part.bounding_box()
        print(f"{name:11} {bb.size.X:6.1f} x {bb.size.Y:6.1f} x {bb.size.Z:5.1f} mm  {part.volume / 1000:6.1f} cm³")
    # Ready-to-slice plates for a 340 x 320 mm bed (Bambu H2S), parts laid out side by side.
    write_plate(OUT / "mount.3mf", built, [
        ("wall-cleat", 0, 5, 5),
        ("tray-cleat", 0, 5, 58),
        ("tray", 0, 5, 103),
        ("spacer", 90, 313, 105),
    ])
    write_plate(OUT / "fit-check.3mf", built, [("fit-vesa", 0, 100, 95), ("fit-pi", 0, 240, 130)])
    write_plate(OUT / "fan-bracket.3mf", built, [("fan-bracket", 0, 140, 135)])
    write_plate(OUT / "spacer.3mf", built, [("spacer", 0, 70, 150)])
    asm = assembly()
    export_step(Compound(children=list(asm.values())), str(OUT / "assembly.step"))
    # Assembled parts as STLs for hardware/viewer.html.
    for name, part in asm.items():
        slug = name.replace(" (ref)", "")
        export_stl(part, str(OUT / f"asm-{slug}.stl"), tolerance=0.05, angular_tolerance=0.3)
    print("wrote", OUT)
    print(f"Screws: 4 x M4 x {M4_SCREW_L} into the monitor (head recessed {M4_RECESS:.1f} mm, "
          f"{M4_ENGAGE} mm into the {VESA_HOLE_DEPTH} mm holes), 4 x M2.5 x {PI_SCREW_L}, "
          f"12 x M3 x {M3_SCREW_L} (cleat, spacer, fan bracket, fan)")
    print(f"Fan: bracket {BRACKET_Z - PLATE_T - PI_BOSS_H - PCB_T:.1f} mm above the PCB, "
          f"{FAN_INTAKE_GAP:.1f} mm of air between the fan and the monitor")


if __name__ == "__main__":
    main()
