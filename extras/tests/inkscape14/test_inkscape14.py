# coding=utf-8
"""
Regression tests for the inkscape-1.4 branch fixes, run on a real matplotlib
figure imported with Inkscape 1.4.3 (see make_fixtures.py). They need no
Inkscape binary, only the fonts DejaVu Sans (matplotlib's default).

    python3 -m pytest extras/tests/inkscape14
"""

import math
import os
import re
import sys

import pytest
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
SI = os.path.abspath(os.path.join(HERE, "..", "..", "..", "scientific_inkscape"))
sys.path.insert(0, SI)

from flatten_plots import FlattenPlots  # noqa: E402
from scale_plots import ScalePlots  # noqa: E402
from favorite_markers import FavoriteMarkers  # noqa: E402
import inkex  # noqa: E402

IMPORT = os.path.join(HERE, "mpl_pdf_import.svg")
GROUPED = os.path.join(HERE, "mpl_grouped.svg")
SVGTEXT = os.path.join(HERE, "mpl_svg_text.svg")
MINUS = "−"


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    # The extensions write Log.txt into the working directory
    monkeypatch.chdir(tmp_path)


def run(effect_class, args, infile, tmp_path, name="out.svg"):
    out = str(tmp_path / name)
    effect_class().run(list(args) + [infile], out)
    return out


def unit_variants(src, tmp_path):
    """The px document plus the same drawing in mm user units and in 2 mm per
    user unit, made by scaling the layer, as the brief's three documents."""
    paths = {"px": src}
    for name, uu_mm in (("mm", 1.0), ("scaled", 2.0)):
        tree = etree.parse(src)
        root = tree.getroot()
        w, h = float(root.get("width")), float(root.get("height"))
        wmm, hmm = w * 25.4 / 96, h * 25.4 / 96
        root.set("width", "%gmm" % wmm)
        root.set("height", "%gmm" % hmm)
        root.set("viewBox", "0 0 %g %g" % (wmm / uu_mm, hmm / uu_mm))
        k = 25.4 / 96 / uu_mm
        for lay in root.findall("{http://www.w3.org/2000/svg}g"):
            lay.set("transform", ("scale(%g) " % k + lay.get("transform", "")).strip())
        p = str(tmp_path / ("in_%s.svg" % name))
        tree.write(p)
        paths[name] = p
    return paths


def plot_area(svg, gid):
    """Width and height of the longest horizontal and vertical lines (the
    axes spines) of a grouped plot, in root user units, without stroke."""
    g = svg.getElementById(gid)
    wmax = hmax = 0
    for el in g.descendants():
        if isinstance(el, inkex.PathElement):
            bb = el.bounding_box(el.getparent().composed_transform())
            if bb is None:
                continue
            if bb.height < 1e-6 * max(bb.width, 1):
                wmax = max(wmax, bb.width)
            if bb.width < 1e-6 * max(bb.height, 1):
                hmax = max(hmax, bb.height)
    return wmax, hmax


def text_sizes(svg, gid):
    """Rendered font size of every text in a group, in root user units"""
    out = {}
    for el in svg.getElementById(gid).descendants():
        if isinstance(el, inkex.TextElement):
            t = el.composed_transform()
            fs = el.specified_style().get("font-size")
            out[el.get_id()] = float(re.match(r"[\d.]+", fs).group()) * math.sqrt(
                abs(t.a * t.d - t.b * t.c)
            )
    return out


# ---------------------------------------------------------------- Scaler


@pytest.mark.parametrize("units", ["px", "mm", "scaled"])
def test_fixed_mode_scales_plot_area(tmp_path, units):
    """The Scaler's Fixed mode tab (--tab=scaling) did nothing to the plot
    and marked the selection scale-free instead, since the Scaler refactor
    (upstream 45be6ca) dropped the mode but left the tab in the dialog."""
    src = unit_variants(GROUPED, tmp_path)[units]
    out = run(
        ScalePlots,
        ["--id=plotL", "--id=plotR", "--tab=scaling", "--hscale=150", "--vscale=70"],
        src,
        tmp_path,
    )
    before = inkex.load_svg(src).getroot()
    after = inkex.load_svg(out).getroot()
    for gid in ("plotL", "plotR"):
        w0, h0 = plot_area(before, gid)
        w1, h1 = plot_area(after, gid)
        assert w1 / w0 == pytest.approx(1.5, rel=1e-4)
        assert h1 / h0 == pytest.approx(0.7, rel=1e-4)
        # text keeps its size
        s0, s1 = text_sizes(before, gid), text_sizes(after, gid)
        assert s0 and s0.keys() == s1.keys()
        for k in s0:
            assert s1[k] == pytest.approx(s0[k], rel=1e-4)
    # Fixed mode must not tag the plots for the Advanced tab
    assert b"inkscape-scientific-scaletype" not in open(out, "rb").read()


def test_fixed_mode_on_a_dragged_plot(tmp_path):
    """A plot that was stretched by dragging is corrected first, then scaled"""
    tree = etree.parse(GROUPED)
    tree.getroot().find(".//{*}g[@id='plotL']").set(
        "transform", "matrix(1.5,0,0,0.7,-80,40)"
    )
    src = str(tmp_path / "dragged.svg")
    tree.write(src)
    out = run(
        ScalePlots,
        ["--id=plotL", "--tab=scaling", "--hscale=50", "--vscale=100"],
        src,
        tmp_path,
    )
    w0, h0 = plot_area(inkex.load_svg(GROUPED).getroot(), "plotL")
    after = inkex.load_svg(out).getroot()
    w1, h1 = plot_area(after, "plotL")
    assert w1 / w0 == pytest.approx(1.5 * 0.5, rel=1e-4)
    assert h1 / h0 == pytest.approx(0.7, rel=1e-4)
    s0 = text_sizes(inkex.load_svg(GROUPED).getroot(), "plotL")
    s1 = text_sizes(after, "plotL")
    for k in s0:
        assert s1[k] == pytest.approx(s0[k], rel=1e-4)


def test_matching_mode_on_a_dragged_plot(tmp_path):
    """Matching still works, including the pre-correction of a dragged plot"""
    tree = etree.parse(GROUPED)
    root = tree.getroot()
    root.find(".//{*}g[@id='plotL']").set("transform", "matrix(1.5,0,0,0.7,-80,40)")
    lay = root.find(".//{*}g[@id='g1']")
    lay.insert(
        0,
        etree.Element(
            "{http://www.w3.org/2000/svg}rect",
            id="target", x="40", y="20", width="200", height="120",
            style="fill:none;stroke:#00f;stroke-width:1",
        ),
    )
    src = str(tmp_path / "match.svg")
    tree.write(src)
    out = run(
        ScalePlots,
        ["--id=target", "--id=plotL", "--tab=matching",
         "--hmatchopts=3", "--vmatchopts=3"],
        src,
        tmp_path,
    )
    w, h = plot_area(inkex.load_svg(out).getroot(), "plotL")
    assert w == pytest.approx(200, abs=0.01)
    assert h == pytest.approx(120, abs=0.01)


# ---------------------------------------------------------------- Flattener


def flatten_import(tmp_path, src=IMPORT):
    lay = etree.parse(src).getroot().find(".//{*}g[@id='g1']")
    ids = ["--id=" + c.get("id") for c in lay if isinstance(c.tag, str)]
    return run(FlattenPlots, ids, src, tmp_path)


def test_flattener_reverts_matplotlib_minus_in_dejavu(tmp_path):
    """Matplotlib draws U+2212 as a path. The Flattener turns it back into a
    character, but set it in the generic sans-serif at an offset tuned for
    another font: on Linux (Noto Sans) the minus came out narrower and
    'Merge nearby text' then put a space after it ('- 1.0')."""
    out = flatten_import(tmp_path)
    svg = inkex.load_svg(out).getroot()
    negs = [
        t for t in svg.descendants()
        if isinstance(t, inkex.TextElement) and "".join(t.itertext()).startswith(MINUS)
    ]
    labels = sorted("".join(t.itertext()) for t in negs)
    assert labels == sorted(
        [MINUS + "1.0", MINUS + "0.5", MINUS + "2", MINUS + "1", MINUS + "2", MINUS + "1"]
    )
    for t in negs:
        minus = next(
            d for d in t.iter() if isinstance(d.tag, str) and (d.text or "").startswith(MINUS)
        )
        fam = minus.specified_style().get("font-family")
        assert fam.replace('"', "'").startswith("'DejaVu Sans'")


@pytest.mark.parametrize("units", ["mm", "scaled"])
def test_flattener_same_text_in_all_unit_systems(tmp_path, units):
    (tmp_path / "ref").mkdir()
    ref = flatten_import(tmp_path / "ref")
    src = unit_variants(IMPORT, tmp_path)[units]
    out = flatten_import(tmp_path, src)

    def texts(p):
        svg = inkex.load_svg(p).getroot()
        return sorted(
            "".join(t.itertext()) for t in svg.descendants() if isinstance(t, inkex.TextElement)
        )

    assert texts(out) == texts(ref)


def test_flattener_keeps_matplotlib_svg_mathtext_words(tmp_path):
    """Matplotlib's own SVG with svg.fonttype 'none' (what upstream advises
    for scaling) writes mathtext one glyph per tspan, with newlines between
    them. Flattening kept the collapsed spaces: "A m p l i t u d e",
    "s i n ( x )", visibly spaced out in the result."""
    out = run(FlattenPlots, ["--id=figure_1"], SVGTEXT, tmp_path)
    svg = inkex.load_svg(out).getroot()
    texts = [
        "".join(t.itertext()) for t in svg.descendants() if isinstance(t, inkex.TextElement)
    ]
    for want in ("sin(x)", "cos(x)", "Time (s)", "Oscillation", "x \u00d7 10"):
        assert want in texts
    assert any(t.startswith("Amplitude") for t in texts)
    spaced = [t for t in texts if re.search(r"\w \w \w", t)]
    assert not spaced


# ---------------------------------------------------------- Favorite Markers


def test_favorite_markers_help_strings_format():
    """Python 3.14 argparse rejects a bare % in a help string when the
    argument is added, so Favorite Markers failed to start at all."""
    ext = FavoriteMarkers()
    ext.arg_parser.format_help()  # raises ValueError on a bad help string
