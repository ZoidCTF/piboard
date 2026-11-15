"""Render PNG previews of the mount: python hardware/preview.py (needs matplotlib)."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import mount  # noqa: E402

COLOURS = {
    "tray": (0.93, 0.93, 0.95, 1.0),
    "tray-cleat": (0.95, 0.62, 0.25, 1.0),
    "wall-cleat": (0.95, 0.45, 0.2, 1.0),
    "spacer": (0.95, 0.62, 0.25, 1.0),
    "monitor (ref)": (0.25, 0.27, 0.3, 0.35),
    "pi (ref)": (0.2, 0.6, 0.3, 1.0),
    "fan-bracket": (0.95, 0.62, 0.25, 1.0),
    "fan (ref)": (0.15, 0.15, 0.17, 1.0),
}
LIGHT = np.array([0.4, 0.5, 1.0]) / np.linalg.norm([0.4, 0.5, 1.0])


def mesh(part, tol=0.4):
    verts, tris = part.tessellate(tol, 0.5)
    v = np.array([[p.X, p.Y, p.Z] for p in verts])
    return v[np.array(tris)]


def shaded(tris, rgba, light=LIGHT):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    k = 0.45 + 0.55 * np.abs(n @ light)
    cols = np.tile(rgba, (len(tris), 1))
    cols[:, :3] *= k[:, None]
    return cols


def draw(ax, parts, elev, azim, light=LIGHT, vertical="y"):
    # One collection for everything, so matplotlib depth-sorts faces across parts.
    tris, cols = [], []
    for name, part in parts.items():
        t = mesh(part)
        tris.append(t)
        cols.append(shaded(t, np.array(COLOURS.get(name, (0.8, 0.8, 0.8, 1))), light))
    tris, cols = np.concatenate(tris), np.concatenate(cols)
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    ax.add_collection3d(Poly3DCollection(tris, facecolors=cols, edgecolors="none"))
    c, r = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim, vertical_axis=vertical)
    ax.set_axis_off()


def main():
    out = mount.OUT
    out.mkdir(exist_ok=True)
    asm = mount.assembly()

    fig = plt.figure(figsize=(16, 8), facecolor="white")
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    draw(ax, asm, elev=20, azim=-35)
    ax.set_title("From behind (wall removed): tray, cleats, Pi on the monitor", fontsize=11)
    ax = fig.add_subplot(1, 2, 2, projection="3d")
    draw(ax, {k: v for k, v in asm.items() if k != "monitor (ref)"}, elev=25, azim=145)
    ax.set_title("Monitor hidden: inside the tray, Pi upper right", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "preview-assembly.png", dpi=110)

    fig = plt.figure(figsize=(9, 9), facecolor="white")
    ax = fig.add_subplot(projection="3d")
    ax.set_proj_type("ortho")
    draw(ax, asm, elev=0, azim=90, light=np.array([1.0, 0.3, 0.2]) / np.linalg.norm([1.0, 0.3, 0.2]))
    ax.set_title(f"Side view: wall (left) | cleats | tray | {mount.CAVITY} mm cavity | monitor (right)", fontsize=11)
    fig.savefig(out / "preview-side.png", dpi=110)

    fig = plt.figure(figsize=(12, 9), facecolor="white")
    ax = fig.add_subplot(projection="3d")
    draw(ax, {"tray": mount.tray()}, elev=50, azim=-60, vertical="z")
    ax.set_title("Tray as printed (back face on the bed)", fontsize=11)
    fig.savefig(out / "preview-tray.png", dpi=110)

    # Close-up of the bottom edge: cable notch, lower VESA posts, vents.
    from build123d import Box, Pos
    bottom = mount.tray() & Pos(0, 40, 25) * Box(200, 80, 60)
    fig = plt.figure(figsize=(12, 7), facecolor="white")
    ax = fig.add_subplot(projection="3d")
    draw(ax, {"tray": bottom}, elev=35, azim=-75, vertical="z")
    ax.set_title("Tray close-up: cable notch and lower VESA posts", fontsize=11)
    fig.savefig(out / "preview-notch.png", dpi=110)

    # Close-up of the Pi corner: tray, Pi, fan bracket and fan, seen from the monitor side.
    window = Pos(mount.PI_SD_END_X - 40, mount.PI_Y0 + 30, 15) * Box(120, 90, 60)
    corner = {k: v & window for k, v in asm.items() if k in ("tray", "pi (ref)", "fan-bracket", "fan (ref)")}
    fig = plt.figure(figsize=(11, 8), facecolor="white")
    ax = fig.add_subplot(projection="3d")
    draw(ax, corner, elev=35, azim=140)
    ax.set_title("Pi corner from the monitor side: posts, fan bracket, fan over the heatsink", fontsize=11)
    fig.savefig(out / "preview-fan.png", dpi=110)
    print("wrote previews to", out)


if __name__ == "__main__":
    main()
