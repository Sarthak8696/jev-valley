"""Draws the three result charts as SVG. matplotlib is an optional dependency.

Colors follow the entity: a brain keeps its color in every chart. The palette is the
validated reference palette (blue, aqua, violet, magenta) plus a neutral gray
for the random floor. Aqua and magenta sit below 3:1 contrast on the light surface, so
every series also has its own marker shape, a legend, and a table in `summary.md`.
"""

import logging
import warnings

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

BRAIN_COLORS = {"jev": "#2a78d6", "rules": "#1baf7a", "random": "#898781"}
BRAIN_MARKERS = {"jev": "o", "rules": "^", "random": "D"}
EXTRA_COLORS = ["#6250d6", "#e87ba4", "#008300", "#e34948"]
EXTRA_MARKERS = ["v", "P", "X", "h"]
CONDITION_STYLES = {"off": "-", "p10": (0, (5, 2)), "p25": (0, (1.2, 1.6))}

SPECIES_TITLES = {"rabbit": "Rabbits", "deer": "Deer", "wolf": "Wolves"}
LINE_WIDTH = 1.5  # points: 2px
MARKER_SIZE = 6.5  # points: about 8px
PX = 0.75  # points per pixel at 96 dpi


def available() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


def brain_of(group: str) -> str:
    """The brain part of a group label such as `jev`, `jev-h-p10` or `wolf-jev_prey-rules`."""
    return group.split("-h-")[0]


def condition_of(group: str) -> str | None:
    return group.split("-h-")[1] if "-h-" in group else None


class Style:
    """Assigns each group a stable color and marker, by brain name first and then in sorted order."""

    def __init__(self, groups):
        self.colors, self.markers = {}, {}
        extras = [g for g in sorted(set(groups)) if brain_of(g) not in BRAIN_COLORS]
        extra_for = {brain_of(g): i for i, g in enumerate(dict.fromkeys(brain_of(g) for g in extras))}
        for group in groups:
            brain = brain_of(group)
            if brain in BRAIN_COLORS:
                self.colors[group], self.markers[group] = BRAIN_COLORS[brain], BRAIN_MARKERS[brain]
            else:
                i = extra_for[brain] % len(EXTRA_COLORS)
                self.colors[group], self.markers[group] = EXTRA_COLORS[i], EXTRA_MARKERS[i]

    def line_style(self, group: str):
        return CONDITION_STYLES.get(condition_of(group) or "off", "-")


def _pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message="findfont")
    plt.rcParams.update({
        "svg.fonttype": "none",
        "svg.hashsalt": "jev-valley",
        "font.family": "sans-serif",
        "font.sans-serif": ["system-ui", "-apple-system", "Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9.5,
        "axes.unicode_minus": False,
    })
    return plt


def _new_figure(plt, width_px: int, height_px: int):
    fig = plt.figure(figsize=(width_px / 96, height_px / 96), dpi=96, facecolor=SURFACE)
    return fig


def _style_axes(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.spines["bottom"].set_linewidth(PX)
    ax.tick_params(axis="both", colors=INK_MUTED, length=0, labelsize=9)
    ax.grid(axis=grid_axis, color=GRID, linewidth=PX, linestyle="-")
    ax.set_axisbelow(True)


def _headline(fig, title: str, subtitle: str, width_px: int):
    fig.text(24 / width_px, 1 - 22 / fig.get_figheight() / 96, title, fontsize=12.5, fontweight="semibold",
             color=INK, ha="left", va="top")
    fig.text(24 / width_px, 1 - 44 / fig.get_figheight() / 96, subtitle, fontsize=9.5, color=INK_SECONDARY,
             ha="left", va="top")


def _legend(fig, ax, groups, style, y_px: int, width_px: int):
    """A legend in a row under the headline. Text stays in ink; the key carries the color and shape."""
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color=style.colors[g], linestyle=style.line_style(g), linewidth=LINE_WIDTH,
                      marker=style.markers[g], markersize=MARKER_SIZE * 0.8,
                      markerfacecolor=style.colors[g], markeredgecolor=SURFACE, markeredgewidth=1.5 * PX)
               for g in groups]
    legend = fig.legend(handles, [_pretty(g) for g in groups], loc="upper left",
                        bbox_to_anchor=(24 / width_px, 1 - y_px / fig.get_figheight() / 96), ncol=len(groups),
                        frameon=False, fontsize=9.5, labelcolor=INK_SECONDARY, handlelength=2.6,
                        columnspacing=1.8, handletextpad=0.6, borderaxespad=0)
    return legend


def _pretty(group: str) -> str:
    brain, condition = brain_of(group), condition_of(group)
    names = {"jev": "Jev", "rules": "Rules", "random": "Random"}
    text = names.get(brain, brain.replace("_", " ").replace("-", " "))
    if condition:
        text += {"off": ", no hesitation", "p10": ", hesitates below 10th percentile",
                 "p25": ", hesitates below 25th percentile"}.get(condition, f", {condition}")
    return text


def _save(fig, path: str) -> None:
    fig.savefig(path, format="svg", facecolor=SURFACE, metadata={"Date": None})


def _empty_message(ax, text="no valid runs to draw"):
    ax.text(0.5, 0.5, text, transform=ax.transAxes, ha="center", va="center", color=INK_MUTED, fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])


# -- population ---------------------------------------------------------------------------

def population_chart(path: str, series: dict, runs_per_group: dict, title: str = "Median population over the month",
                     steps_per_day: int = 24) -> None:
    """`series[group][species]` is the median count at every step. One panel per species, one line per group."""
    plt = _pyplot()
    groups = list(series)
    style = Style(groups)
    width, height = 960, 400 if len(groups) <= 4 else 440
    fig = _new_figure(plt, width, height)
    counts = ", ".join(f"{_pretty(g)}: {runs_per_group.get(g, 0)}" for g in groups)
    _headline(fig, title, f"Median over valid runs. Runs per line: {counts}", width)
    if groups:
        _legend(fig, None, groups, style, 66, width)
    species = ["rabbit", "deer", "wolf"]
    top = 1 - (118 if len(groups) else 80) / height
    for i, key in enumerate(species):
        ax = fig.add_axes([0.055 + i * 0.32, 0.13, 0.27, top - 0.13])
        _style_axes(ax)
        ax.set_title(SPECIES_TITLES[key], loc="left", fontsize=10, color=INK, pad=8)
        if not groups:
            _empty_message(ax)
            continue
        ymax = 1
        for group in groups:
            values = series[group][key]
            days = [s / steps_per_day for s in range(len(values))]
            ax.plot(days, values, color=style.colors[group], linestyle=style.line_style(group),
                    linewidth=LINE_WIDTH, solid_capstyle="round", solid_joinstyle="round", zorder=3)
            ax.plot(days[-1:], values[-1:], linestyle="none", marker=style.markers[group], markersize=MARKER_SIZE,
                    markerfacecolor=style.colors[group], markeredgecolor=SURFACE, markeredgewidth=2 * PX, zorder=4)
            ymax = max(ymax, max(values))
        ax.set_ylim(0, ymax * 1.12)
        max_day = max((len(series[g][key]) - 1) / steps_per_day for g in groups)
        ax.set_xlim(0, max(1, max_day) * 1.03)
        ax.set_xlabel("Day", color=INK_MUTED, fontsize=9, labelpad=6)
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=4, integer=True))
    _save(fig, path)
    plt.close(fig)


# -- blunders -----------------------------------------------------------------------------

def _rounded_bar(ax, x, height, width_data, color, px_x, px_y):
    """A bar with a 4px rounded data end and a square baseline. `px_x` and `px_y` are data units per pixel."""
    from matplotlib.patches import FancyBboxPatch, Rectangle
    if height <= 0:
        return
    radius_x = 4 * px_x
    aspect = (4 * px_y) / radius_x
    ax.add_patch(FancyBboxPatch((x - width_data / 2, 0), width_data, height,
                                boxstyle=f"round,pad=0,rounding_size={radius_x}", mutation_aspect=aspect,
                                facecolor=color, edgecolor="none", zorder=3))
    square = min(height, 4 * px_y)
    ax.add_patch(Rectangle((x - width_data / 2, 0), width_data, square, facecolor=color, edgecolor="none", zorder=3))


def blunders_chart(path: str, rates: dict, title: str = "Blunder rate") -> None:
    """`rates[group]` is the overall blunder rate of each valid run. Bars show the mean; dots show each run."""
    plt = _pyplot()
    groups = list(rates)
    style = Style(groups)
    width, height = 720, 400
    fig = _new_figure(plt, width, height)
    _headline(fig, title, "Share of blunder opportunities where the choice was clearly bad. Bar is the mean; dots are runs.",
              width)
    left, bottom, plot_w, plot_h = 0.09, 0.2, 0.88, 0.58
    ax = fig.add_axes([left, bottom, plot_w, plot_h])
    _style_axes(ax)
    if not groups or not any(rates[g] for g in groups):
        _empty_message(ax)
        _save(fig, path)
        plt.close(fig)
        return
    top = max(max(v) for v in rates.values() if v) * 100
    ymax = max(top * 1.3, 1.0)
    ax.set_xlim(-0.6, len(groups) - 0.4)
    ax.set_ylim(0, ymax)
    px_x = (len(groups) + 0.2) / (plot_w * width)
    px_y = ymax / (plot_h * height)
    bar_w = min(24 * px_x, 0.6)
    for i, group in enumerate(groups):
        values = [v * 100 for v in rates[group]]
        if not values:
            continue
        mean = sum(values) / len(values)
        _rounded_bar(ax, i, mean, bar_w, style.colors[group], px_x, px_y)
        spread = [(j - (len(values) - 1) / 2) * 7 * px_x for j in range(len(values))]
        ax.plot([i + s for s in spread], values, linestyle="none", marker="o", markersize=MARKER_SIZE,
                markerfacecolor=INK_SECONDARY, markeredgecolor=SURFACE, markeredgewidth=2 * PX, zorder=5)
        ax.text(i, max(max(values), mean) + 12 * px_y, f"{mean:.1f}%", ha="center", va="bottom", color=INK,
                fontsize=9.5, zorder=6)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([_pretty(g) for g in groups], color=INK_SECONDARY, fontsize=9.5)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:g}%")
    _save(fig, path)
    plt.close(fig)


# -- calibration --------------------------------------------------------------------------

def calibration_chart(path: str, bins: dict, title: str = "Blunders by confidence") -> None:
    """`bins[group]` is a list of {bin, decisions_with_opportunity, blunder_rate} for each confidence bin."""
    plt = _pyplot()
    groups = list(bins)
    style = Style(groups)
    width, height = 720, 400
    fig = _new_figure(plt, width, height)
    _headline(fig, title, "Blunder rate among decisions with a blunder opportunity, by the model's stated confidence.",
              width)
    if groups:
        _legend(fig, None, groups, style, 66, width)
    ax = fig.add_axes([0.09, 0.17, 0.88, 0.58 if groups else 0.62])
    _style_axes(ax)
    if not groups:
        _empty_message(ax, "no model decisions to draw")
        _save(fig, path)
        plt.close(fig)
        return
    labels = [row["bin"] for row in next(iter(bins.values()))]
    ymax = 1.0
    for group in groups:
        xs = [i for i, row in enumerate(bins[group]) if row["blunder_rate"] is not None]
        ys = [bins[group][i]["blunder_rate"] * 100 for i in xs]
        if not xs:
            continue
        ymax = max(ymax, max(ys))
        ax.plot(xs, ys, color=style.colors[group], linestyle=style.line_style(group), linewidth=LINE_WIDTH,
                marker=style.markers[group], markersize=MARKER_SIZE, markerfacecolor=style.colors[group],
                markeredgecolor=SURFACE, markeredgewidth=2 * PX, solid_capstyle="round", zorder=3)
    ax.set_xlim(-0.4, len(labels) - 0.6)
    ax.set_ylim(0, ymax * 1.2)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, color=INK_SECONDARY, fontsize=9.5)
    ax.set_xlabel("Confidence", color=INK_MUTED, fontsize=9, labelpad=6)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:g}%")
    _save(fig, path)
    plt.close(fig)
