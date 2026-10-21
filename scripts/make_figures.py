"""Regenerate the README figures in docs/assets.

Run from the repo root:

    pytest --cov=src --cov-report=json --junitxml=junit.xml   # writes coverage.json and junit.xml
    python scripts/make_figures.py

plan_budget.png runs the heuristic planner on one thesis (no LLM, no services).
tests.png reads junit.xml and coverage.json; it is skipped if either file is missing.
"""

import asyncio
import collections
import json
import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "assets"

BG, PANEL = "#0d0c0b", "#131211"
INK, INK2, INK3 = "#ede7de", "#aaa299", "#7a736c"
GRID = "#24221f"
EMBER, TEMPER, PURPLE, GREEN = "#d95926", "#3987e5", "#9085e9", "#199e70"
SERIES = [EMBER, TEMPER, PURPLE, GREEN, "#e8b44c", "#c0509c"]
HEAT = LinearSegmentedColormap.from_list("heat", ["#141110", "#2a1410", "#4b170c", "#7a1f0a", "#ad320c",
                                                  "#d9520f", "#f07a1e", "#f9a63b", "#fccf6b", "#fff0c2"])
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": PANEL, "savefig.facecolor": BG,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titleweight": "semibold",
    "axes.titlesize": 12.5, "axes.titlelocation": "left", "axes.titlepad": 12, "axes.labelsize": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
    "xtick.color": INK3, "ytick.color": INK3, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 6, "ytick.major.pad": 6,
    "axes.axisbelow": True, "font.family": ["Segoe UI", "DejaVu Sans"], "lines.linewidth": 2,
    "lines.solid_capstyle": "round", "legend.frameon": False, "legend.fontsize": 9.5, "legend.labelcolor": INK2,
    "figure.dpi": 110, "savefig.dpi": 200,
})

THESIS = ("This study examines how remote work affects code review quality and onboarding "
          "in software teams, using survey data and repository analysis.")

# test file -> package it exercises (directories under tests/core map to themselves)
TEST_AREA = {
    "test_config": "config", "test_core_config_py": "config", "test_pydantic_config": "config",
    "test_auth": "auth", "test_rbac": "auth",
    "test_connection": "database", "test_models": "database", "test_repositories": "database",
    "test_evidence_validator": "schemas", "test_schemas": "schemas", "test_schema_integration": "schemas",
    "test_validators": "schemas", "test_simple_coverage": "schemas",
    "test_artifact_store": "storage", "test_file_manager": "storage", "test_s3_client": "storage",
}
PACKAGES = ["config", "auth", "database", "schemas", "storage", "events", "logging",
            "monitoring", "embeddings", "llm", "planning", "web"]


def run_planner():
    logging.disable(logging.CRITICAL)
    from src.services.planning import PlanningService, PlanRequest

    request = PlanRequest(thesis=THESIS, target_word_count=5000)
    return asyncio.run(PlanningService().plan(request))


def fig_plan_budget():
    plan = run_planner()
    sections = sorted(plan.sections, key=lambda s: s.order)
    template = {"Introduction", "Literature Review", "Methodology", "Results", "Discussion", "Conclusion"}

    def short(t, n=46):
        return t if len(t) <= n else t[: n - 1].rstrip() + "…"

    labels = [short(s.title) for s in sections][::-1]
    values = [s.word_budget for s in sections][::-1]
    colors = [EMBER if s.title in template else TEMPER for s in sections][::-1]

    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    bars = ax.barh(labels, values, color=colors, height=0.62)
    for b, v in zip(bars, values):
        ax.text(b.get_width() + 12, b.get_y() + b.get_height() / 2, f"{v}", va="center",
                ha="left", color=INK2, fontsize=9)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("word budget")
    ax.set_xlim(0, max(values) * 1.12)
    ax.set_title(f"Planner output: word budget per section ({sum(values):,} words, "
                 f"{len(plan.search_plan.queries)} search queries)")
    ax.legend(handles=[Patch(color=EMBER, label="research_paper template section"),
                       Patch(color=TEMPER, label="section added per extracted subtopic")],
              loc="upper right")
    fig.text(0.012, -0.015,
             "Heuristic mode (no LLM, no services). Thesis:\n“" + THESIS + "”",
             color=INK3, fontsize=8.5, ha="left", va="top", linespacing=1.5)
    path = OUT / "plan_budget.png"
    fig.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))


def test_area(classname):
    parts = classname.split(".")
    if parts[1] == "core":
        return TEST_AREA.get(parts[2], parts[2])
    if parts[1] == "services":
        return "planning"
    if parts[1] == "unit":
        return "schemas"
    return parts[1]


def coverage_package(path):
    parts = path.replace("\\", "/").split("/")
    if parts[1] == "core":
        return parts[2].removesuffix(".py")
    if parts[1] == "services":
        return parts[2]
    return parts[1]


def fig_tests(junit_path, coverage_path):
    outcomes = collections.defaultdict(collections.Counter)
    for tc in ET.parse(junit_path).getroot().iter("testcase"):
        state = "passed"
        for child in tc:
            if child.tag == "failure":
                state = "failed"
            elif child.tag == "error":
                state = "error"
            elif child.tag == "skipped":
                state = "skipped"
        outcomes[test_area(tc.get("classname"))][state] += 1

    cov = collections.defaultdict(lambda: [0, 0])
    for path, data in json.loads(Path(coverage_path).read_text())["files"].items():
        s = data["summary"]
        c = cov[coverage_package(path)]
        c[0] += s["covered_lines"] + s.get("covered_branches", 0)
        c[1] += s["num_statements"] + s.get("num_branches", 0)

    pk = PACKAGES[::-1]
    total = sum(sum(c.values()) for c in outcomes.values())
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.9), gridspec_kw={"width_ratios": [1.35, 1]})

    states = [("passed", GREEN, "passed"), ("failed", EMBER, "failed"),
              ("error", "#e8b44c", "passed, teardown error"), ("skipped", PURPLE, "skipped")]
    left = [0] * len(pk)
    for key, color, label in states:
        vals = [outcomes[p][key] for p in pk]
        a1.barh(pk, vals, left=left, color=color, height=0.62, label=label)
        left = [l + v for l, v in zip(left, vals)]
    for i, n in enumerate(left):
        a1.text(n + 2, i, str(n), va="center", ha="left", color=INK2, fontsize=9)
    a1.grid(axis="y", visible=False)
    a1.grid(axis="x", visible=True)
    a1.set_xlim(0, max(left) * 1.15)
    a1.set_xlabel("tests")
    a1.set_title(f"Test outcomes by package ({total} tests)")
    a1.legend(loc="lower right")

    pct = [100 * cov[p][0] / cov[p][1] if cov[p][1] else 0 for p in pk]
    bars = a2.barh(pk, pct, color=TEMPER, height=0.62)
    for b, v in zip(bars, pct):
        a2.text(b.get_width() + 1.2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", va="center",
                ha="left", color=INK2, fontsize=9)
    a2.grid(axis="y", visible=False)
    a2.grid(axis="x", visible=True)
    a2.set_xlim(0, 112)
    a2.set_xlabel("line + branch coverage (%)")
    tot = json.loads(Path(coverage_path).read_text())["totals"]["percent_covered"]
    a2.set_title(f"Coverage by package ({tot:.1f}% overall)")
    fig.tight_layout(w_pad=3)
    fig.text(0.012, -0.015,
             "pytest on Windows 11, Python 3.12, no Postgres, Redis or MinIO running. "
             "Database tests use SQLite; Redis, S3 and the embedding model are mocked.",
             color=INK3, fontsize=8.5, ha="left", va="top")
    path = OUT / "tests.png"
    fig.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig_plan_budget()
    junit, coverage = ROOT / "junit.xml", ROOT / "coverage.json"
    if junit.exists() and coverage.exists():
        fig_tests(junit, coverage)
    else:
        print("skipped tests.png: run pytest --cov=src --cov-report=json --junitxml=junit.xml first")
