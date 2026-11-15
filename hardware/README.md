# Wall mount

A 3D-printed mount that hangs the Raspberry Pi Monitor on the wall and hides the Pi 5 behind it.

```
 wall │ cleats │ tray │◄─ 28 mm cavity: Pi + cables ─►│ monitor │ front     (screen face 60 mm off the wall)
```

- **Wall cleat:** screwed to the wall (drywall anchors). French cleat: the monitor lifts straight off.
- **Tray:** bolts to the monitor's VESA 100 holes and hangs on the cleat. It holds the Pi in the upper right (seen from behind), where the monitor's back is 10 mm thinner and the fan has room. The skirt stays inside the monitor's outline, with vents top and bottom and a cable exit at the bottom centre.
- **Fan bracket:** screws onto two posts beside the Pi's SD-card end and holds the official Pi 5 case fan (30 × 30 × 7 mm) over the SoC heatsink, blowing down onto it. Set `HEATSINK_H` to your heatsink's height; the model checks the fan keeps at least 5 mm of air in front of it.
- **Tray cleat and spacer:** screwed to the back of the tray. They're separate parts so the tray prints flat.

The model is parametric: [`mount.py`](mount.py) (build123d). Every monitor dimension comes from Raspberry Pi's product brief, which marks them approximate. **Measure before printing the tray** (see the checklist below).

## Build the files

```bash
pip install build123d matplotlib
python hardware/mount.py     # STEP + STL per part, mount.3mf, assembly STLs → hardware/out/
python hardware/preview.py   # optional PNG renders
```

To look at it in 3D, serve `hardware/out/` with a copy of `viewer.html` as `index.html` (for example `python -m http.server -d hardware/out`) and open it in a browser.

## Measure first

On the real monitor, check these values at the top of `mount.py`:

| Value | Datasheet | Check |
|---|---|---|
| `VESA` | 100 × 100 | Hole spacing, centre to centre |
| `VESA_ROWS` | 12.5 / 112.5 mm above the bottom edge | Height of each hole row |
| VESA thread | **M4, 5 mm deep (measured)** | Metal inserts. `VESA_HOLE_DEPTH`; the model picks the screw length and head recess from it |
| `MON_BUMP_H` | 127 mm | Height of the thick lower section |
| `CENTRE_CLEAR` | ±42 mm | Width of the stand and connector area |
| `CAVITY` | **28 mm (chosen)** | The monitor's plugs enter sideways and lie flat in the recess under the stand, so the depth only has to fit the Pi: about 12 mm of air stays over its fan |

Then print **fit-vesa** (about 20 min) and hold it against the monitor with M4 screws, and **fit-pi** to check the Pi's M2.5 inserts. Only then print the tray.

## Printing (Bambu H2S, PETG)

| Part | Orientation | Notes |
|---|---|---|
| tray | Back face down, as exported | No supports. 3 walls, 15–20% gyroid. About 300 × 213 mm |
| tray-cleat, spacer | Tray-side face down, as exported | 4 walls; these carry the load |
| wall-cleat | Wall-side face down, as exported | 4 walls, 40% infill |
| fit-vesa, fit-pi | As exported | Test pieces |

`fit-check.3mf` (both test pieces) and `mount.3mf` (all four mount parts) open in Bambu Studio already arranged for the 340 × 320 mm H2S plate. Pick the PETG profile, set the walls/infill above, and slice.

## Hardware

- 4 × **M4 × 30** socket-head screws into the monitor. The VESA holes are only 5 mm deep, so the heads sit 6 mm down in the tray's posts and the screws reach 4 mm into the holes; `python hardware/mount.py` prints the length if you change `CAVITY`. **Don't use longer screws.**
- 4 × M2.5 heat-set inserts + 4 × **M2.5 × 8** screws for the Pi
- 8 × M3 heat-set inserts + 12 × **M3 × 12** screws: tray cleat (4), spacer (2), fan bracket (2), and 2–4 through the fan's corner holes into **M3 nuts** (the holes are clearance-sized, so screws won't bite)
- Both come in one box: [Swpeet 385-piece kit, variation N8](https://www.amazon.ca/dp/B0DRNPW9ZY). The hole depths and the 2 mm pads under the M3 screw heads are sized for these lengths (`PI_SCREW_L`, `M3_SCREW_L` in `mount.py`); change those if you use other screws.
- 4 × #8 (4 mm) flat-head screws + drywall anchors for the wall cleat
- Right-angle micro-HDMI to HDMI cable, ~30 cm (Pi to monitor)
- Short USB-C cable for the monitor's power, and the existing power supplies
- Cord cover from the bottom of the monitor to the outlet

## Assembly

1. Press the heat-set inserts into the tray (Pi bosses), the tray cleat and the spacer.
2. Screw the tray cleat and spacer to the back of the tray from inside. This has to happen before the tray goes on the monitor: their screws are only reachable from inside. The spacer's two U-slots sit over the lower VESA screw heads so a hex key reaches them.
3. Mount the Pi on its bosses, ports facing down, and the fan bracket on its posts (fan held with M3 nuts).
4. Flip the monitor's stand up to expose its connectors, and plug in HDMI and power.
5. Bolt the tray to the monitor's VESA holes (the lower two through the spacer's slots); route both power cords out of the bottom notch.
6. Level the wall cleat at the right height and screw it into the anchors. The tray cleat's hook sits 40 mm above the wall cleat's lower edge, near the top of the monitor.
7. Hang the monitor: lower the tray cleat onto the wall cleat and let it slide into place.
