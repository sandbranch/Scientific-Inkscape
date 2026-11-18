"""
Regenerate the matplotlib fixtures used by test_inkscape14.py.

    python3 make_fixtures.py   (needs matplotlib and the inkscape binary)

mpl_pdf_import.svg: a two-panel matplotlib figure saved as PDF and opened
    with Inkscape 1.4.3's internal PDF importer.
mpl_grouped.svg: that import run through the Flattener (default options,
    every child of the layer selected), then each panel's elements put in
    a group (plotL, plotR), as the README asks before running the Scaler.
"""

import os
import subprocess
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SI = os.path.join(HERE, "..", "..", "..", "scientific_inkscape")


def inkscape(*args):
    return subprocess.run(
        ["dbus-run-session", "--", "inkscape", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def main():
    x = np.linspace(0, 10, 200)
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    axs[0].plot(x, np.sin(x), label=r"$\sin(x)$")
    axs[0].plot(x, np.cos(x), "--", label=r"$\cos(x)$")
    axs[0].set_xlabel("Time (s)")
    axs[0].set_ylabel(r"Amplitude $A_0$ (mV)")
    axs[0].set_title("Oscillation")
    axs[0].legend()
    rng = np.random.default_rng(1)
    axs[1].scatter(rng.normal(size=60), rng.normal(size=60), s=12, c="tab:red")
    axs[1].set_xlabel(r"$x \times 10^{3}$")
    axs[1].set_ylabel("y")
    axs[1].set_title("Scatter")
    fig.tight_layout()
    pdf = os.path.join(HERE, "mpl.pdf")
    fig.savefig(pdf)

    imp = os.path.join(HERE, "mpl_pdf_import.svg")
    inkscape(pdf, "--export-type=svg", "--export-filename=" + imp)
    os.remove(pdf)

    lay = etree.parse(imp).getroot().find(".//{*}g[@id='g1']")
    ids = ["--id=" + c.get("id") for c in lay if isinstance(c.tag, str)]
    flat = os.path.join(HERE, "mpl_flat.svg")
    with open(flat, "wb") as f:
        subprocess.run(
            ["dbus-run-session", "--", sys.executable,
             os.path.join(SI, "flatten_plots.py"), *ids, imp],
            check=True, stdout=f,
        )

    bb = {}
    for line in inkscape(flat, "--query-all").splitlines():
        p = line.split(",")
        if len(p) == 5:
            bb[p[0]] = [float(v) for v in p[1:]]
    tree = etree.parse(flat)
    lay = tree.getroot().find(".//{*}g[@id='g1']")
    svgns = "{http://www.w3.org/2000/svg}"
    gl = etree.SubElement(lay, svgns + "g", id="plotL")
    gr = etree.SubElement(lay, svgns + "g", id="plotR")
    half = float(tree.getroot().get("width")) / 2
    for c in list(lay):
        if c in (gl, gr) or c.get("id") not in bb:
            continue
        x, _, w, _ = bb[c.get("id")]
        (gl if x + w / 2 < half else gr).append(c)
    tree.write(os.path.join(HERE, "mpl_grouped.svg"))
    os.remove(flat)


if __name__ == "__main__":
    main()
