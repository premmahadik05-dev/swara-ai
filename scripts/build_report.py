"""Build the project report from the stored results, so no number in it is typed by hand.

   python scripts/build_report.py            # writes docs/PROJECT_REPORT.md and docs/report-figures/*.png
   python scripts/build_report.py --files    # also writes docs/PROJECT_REPORT.docx and .pdf (needs pandoc and Playwright's Chromium)

Reads:   docs/report/PROJECT_REPORT.template.md      the prose, with {{value}}, {{fig:name}}, {{table:name}} and {{ref:fig:name}} markers
         eval/results/evaluation_summary.json         scripts/build_evaluation_summary.py
         eval/results/verification_summary.json       scripts/build_verification_summary.py (optional: the table says "Not run" without it)
         eval/results/api_latency.json                scripts/benchmark_api.py (optional)
         docs/report-data/demo_activity.json          scripts/demo_activity.py --payments on a throw-away database (the demo-shop tables and charts, and the payment tables and chart)
         docs/test-results/*.txt                      the saved test logs (coverage, file counts and the update check are read from them)
Needs matplotlib (not part of the app: `pip install matplotlib`). A marker with no value stops the build instead of printing a blank.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
RES = ROOT / "eval" / "results"
TEMPLATE = DOCS / "report" / "PROJECT_REPORT.template.md"
FIGS = DOCS / "report-figures"
DEMO = DOCS / "report-data" / "demo_activity.json"

# brand tokens (frontend/src/styles/tokens.css)
BLUE, ORANGE, GREEN, AMBER, MUTED, GOLD = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8578", "#d6b574"
INK, INK2, GRID, OK, BAD = "#242424", "#686868", "#eae7df", "#0a6c47", "#b02a1f"
HEAT = LinearSegmentedColormap.from_list("gold", ["#fbf7ec", "#e6cf9a", "#cda254"])
plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.dpi": 100, "savefig.dpi": 200,
    "legend.frameon": False, "legend.fontsize": 8,
})

S: dict = {}
V: dict | None = None
A: dict | None = None
D: dict = {}


def load() -> None:
    global S, V, A, D
    S = json.loads((RES / "evaluation_summary.json").read_text(encoding="utf-8"))
    for name, path in (("V", RES / "verification_summary.json"), ("A", RES / "api_latency.json")):
        globals()[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not DEMO.exists():
        sys.exit("docs/report-data/demo_activity.json is missing. Start a throw-away server and run scripts/demo_activity.py --json docs/report-data/demo_activity.json")
    D = json.loads(DEMO.read_text(encoding="utf-8"))
    if "payments" not in D:
        sys.exit("docs/report-data/demo_activity.json has no payment activity. Run scripts/demo_activity.py with --payments on a throw-away 2.7 server.")


# ------------------------------------------------------------------------------------------------ helpers
def pct(n: float, d: float, nd: int = 1) -> str:
    return "n/a" if not d else f"{100 * n / d:.{nd}f}%"


def inr(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


def md_table(headers: list[str], rows: list[list], align: list[str] | None = None) -> str:
    esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    sep = [{"r": "---:", "c": ":---:"}.get((align or [""] * len(headers))[i], "---") for i in range(len(headers))]
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |"] + ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows])


def lang_name(key: str) -> str:
    return next((l["name"] for l in S["languages"] if l["key"] == key), key)


def lang_keys() -> list[str]:
    return [l["key"] for l in S["languages"]]


def save(fig, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGS / f"{name}.png", facecolor="white")
    plt.close(fig)
    return f"report-figures/{name}.png"


def heat(ax, data, rows, cols, fmt=lambda v: f"{v:g}", vmax=None, na="n/a", kind="seq", mask_text=None) -> None:
    import numpy as np
    arr = np.array([[np.nan if v is None else v for v in r] for r in data], dtype=float)
    ax.grid(False)
    ax.imshow(arr, cmap=HEAT, vmin=0, vmax=vmax if vmax is not None else (np.nanmax(arr) or 1), aspect="auto")
    ax.set_xticks(range(len(cols)), cols, rotation=0)
    ax.set_yticks(range(len(rows)), rows)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            ax.text(j, i, na if np.isnan(v) else fmt(v), ha="center", va="center", fontsize=8, color=INK if not np.isnan(v) else INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)


# ------------------------------------------------------------------------------------------------ figures
def fig_datasets() -> str:
    ds = S["datasets"]
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    names = [d["name"] for d in ds]
    n_all = [d["n"] for d in ds]
    n_ord = [d["n_order"] for d in ds]
    y = range(len(names))
    ax.barh(y, n_all, color=GOLD, height=0.55, label="All sentences")
    ax.barh(y, n_ord, color=BLUE, height=0.55, label="Order sentences (scored)")
    for i, (a, o) in enumerate(zip(n_all, n_ord)):
        ax.text(a + 4, i, f"{a}" if a == o else f"{o} of {a}", va="center", fontsize=8)
    ax.set_yticks(list(y), names)
    ax.invert_yaxis()
    ax.set_xlabel("Sentences")
    ax.set_xlim(0, max(n_all) * 1.18)
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    ax.set_title("Evaluation sentences by dataset")
    return save(fig, "fig-datasets")


def _lang_dataset_matrix():
    cols = [("handwritten", "Handwritten"), ("templated", "Templated"), ("authored", "Authored"), ("branded", "Held-out brands")]
    cell = {(r["lang"], r["dataset"]): r for r in S["sentence_check"]}
    rows = lang_keys()
    return rows, cols, cell


def fig_language_heatmap() -> str:
    rows, cols, cell = _lang_dataset_matrix()
    data = [[(cell[(l, d)]["exact_pct"] if (l, d) in cell else None) for d, _ in cols] for l in rows]
    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    heat(ax, data, [lang_name(l) for l in rows], [c for _, c in cols], fmt=lambda v: f"{v:.0f}%", vmax=100, na="not in set")
    ax.set_title("Exact order match by language and sentence set (% of sentences)")
    ax.set_xlabel("Sentence set (text only)")
    return save(fig, "fig-language-heatmap")


def fig_branded_by_language() -> str:
    b = S["branded"]["by_language"]
    keys = [k for k in lang_keys() if k in b]
    parts = [("exact", "Exact product", GREEN), ("ambiguous_contains_expected", "Asked which pack", AMBER), ("not_recognised", "Not recognised", MUTED), ("wrong_product", "Wrong product", ORANGE)]
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    left = [0.0] * len(keys)
    for key, label, color in parts:
        vals = [b[k].get(key, 0) for k in keys]
        ax.barh(range(len(keys)), vals, left=left, color=color, label=label, height=0.62, edgecolor="white", linewidth=1.2)
        left = [l + v for l, v in zip(left, vals)]
    ax.set_yticks(range(len(keys)), [lang_name(k) for k in keys])
    ax.invert_yaxis()
    ax.set_xlabel("Held-out branded sentences (count)")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.16))
    ax.set_title("How each held-out branded sentence ended, by language")
    return save(fig, "fig-branded-by-language")


def fig_category_confusion() -> str:
    c = S["branded"]["confusion"]
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    wrap = {"Biscuits & Sweets": "Biscuits\n& Sweets", "Breakfast & Noodles": "Breakfast\n& Noodles", "Sauces & Spreads": "Sauces\n& Spreads", "Dairy & Bakery": "Dairy\n& Bakery", "Other category": "Other\ncategory", "Asked which pack": "Asked\nwhich\npack", "Not recognised": "Not\nrecog-\nnised"}
    heat(ax, c["matrix"], c["labels_rows"], [wrap.get(l, l) for l in c["labels_cols"]], fmt=lambda v: f"{v:.0f}")
    ax.tick_params(axis="x", labelsize=7)
    ax.set_xlabel("What the parser returned")
    ax.set_ylabel("Category of the expected product")
    ax.set_title("Held-out branded sentences: expected category against outcome (count)")
    return save(fig, "fig-category-confusion")


def fig_language_labels() -> str:
    ld = S["language_detection"]
    labels = ld["labels"]
    rows = [[100 * v / max(1, sum(r)) for v in r] for r in ld["matrix"]]
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    heat(ax, rows, [lang_name(l) for l in labels], [l for l in labels], fmt=lambda v: "" if v == 0 else f"{v:.0f}", vmax=100)
    ax.set_xlabel("Language label the parser gave (key)")
    ax.set_ylabel("Language the sentence was written in")
    ax.set_title("Language label returned for each sentence (% of row)")
    return save(fig, "fig-language-labels")


def fig_noise() -> str:
    lv = S["noise"]["levels"]
    x = [100 * l["cer"] for l in lv]
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.fill_between(x, [100 * l["utterance_exact_min"] for l in lv], [100 * l["utterance_exact_max"] for l in lv], color=BLUE, alpha=0.15, linewidth=0, label=f"Min to max over {S['noise']['seeds']} random seeds")
    ax.plot(x, [100 * l["utterance_exact"] for l in lv], color=BLUE, marker="o", linewidth=2, markersize=6, markeredgecolor="white", label="Whole order exact (mean)")
    ax.plot(x, [100 * l["line_f1"] for l in lv], color=ORANGE, marker="s", linewidth=2, markersize=6, markeredgecolor="white", label="Order lines F1")
    ax.plot(x, [100 * l["product_f1"] for l in lv], color=GREEN, marker="^", linewidth=2, markersize=6, markeredgecolor="white", label="Product-only F1")
    ax.set_xlabel("Simulated character damage (% of characters)")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 102)
    ax.set_xticks(x)
    ax.legend(loc="lower left")
    ax.set_title("Robustness to damaged text")
    return save(fig, "fig-noise")


def fig_ablation() -> str:
    ab = [a for a in S["noise"]["ablation"] if abs(a["cer"] - 0.06) < 1e-9] or S["noise"]["ablation"][-4:]
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    labels = [a["label"] for a in ab]
    ax.barh(range(len(ab)), [100 * a["utterance_exact"] for a in ab], color=BLUE, height=0.55, label="Whole order exact")
    for i, a in enumerate(ab):
        ax.text(100 * a["utterance_exact"] + 1, i, f"{100 * a['utterance_exact']:.1f}%", va="center", fontsize=8)
    ax.set_yticks(range(len(ab)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Whole order exact at 6% simulated damage (%)")
    ax.set_title("What each matching stage adds")
    return save(fig, "fig-ablation")


def fig_end_to_end() -> str:
    e, g = S["end_to_end"], S["end_to_end"]["stock_guard"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.6, 3.3), gridspec_kw={"width_ratios": [1, 1.5]})
    out = e["outcomes"]
    names = ["Order saved correctly", "Wrong order saved", "Not completed"]
    vals = [out.get("order_correct", 0), out.get("order_wrong", 0), sum(v for k, v in out.items() if k not in ("order_correct", "order_wrong", "skipped_gold_not_convertible"))]
    a1.bar(range(3), vals, color=[GREEN, ORANGE, MUTED], width=0.6)
    for i, v in enumerate(vals):
        a1.text(i, v + max(vals) * 0.02, str(v), ha="center", fontsize=8)
    a1.set_xticks(range(3), ["Correct", "Wrong", "Not\ncompleted"])
    a1.set_ylim(0, max(vals) * 1.12)
    a1.set_ylabel("Typed orders")
    a1.set_title(f"End to end ({e['n_scored']} scored)")
    cats = ["Empty shelf\nrefused", "Empty shelf\nnegative\nstock", "Half stock\nasked or\noffered", "Half stock\nrefused", "Half stock\nover-\nstock"]
    vv = [g["empty_refused"], g["empty_negative_stock"], g["half_asked_or_offered"], g["half_refused"], g["half_negative_stock"]]
    a2.bar(range(5), vv, color=[GREEN, ORANGE, GREEN, GREEN, ORANGE], width=0.6)
    for i, v in enumerate(vv):
        a2.text(i, v + max(vv) * 0.02, str(v), ha="center", fontsize=8)
    a2.set_xticks(range(5), cats, fontsize=7)
    a2.set_ylim(0, max(vv) * 1.12)
    a2.set_ylabel("Orders")
    a2.set_title("Stock guard")
    return save(fig, "fig-end-to-end")


def fig_error_distribution() -> str:
    v = S["branded"]["verdicts"]
    names = ["Exact product", "Asked which pack", "Not recognised", "Wrong product"]
    vals = [v["exact"], v["ambiguous_contains_expected"], v["not_recognised"], v["wrong_product"]]
    fig, ax = plt.subplots(figsize=(7.0, 2.8))
    ax.barh(range(4), vals, color=[GREEN, AMBER, MUTED, ORANGE], height=0.55)
    for i, x in enumerate(vals):
        ax.text(x + 3, i, f"{x} ({pct(x, S['branded']['cases'])})", va="center", fontsize=8)
    ax.set_yticks(range(4), names)
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.25)
    ax.set_xlabel(f"Held-out branded sentences, n = {S['branded']['cases']}")
    ax.set_title("Outcome of held-out branded sentences")
    return save(fig, "fig-error-distribution")


def fig_demo_sales() -> str:
    days = D["overview"]["sales_by_day"]
    typed = [o["created_at"] for o in D["orders"] if not o["is_synthetic"]]
    last_partial = False
    if typed:
        from datetime import timedelta
        ist = datetime.fromisoformat(max(typed).replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=5, minutes=30)))
        last_partial = ist.strftime("%Y-%m-%d") == days[-1]["date"]
    x = list(range(len(days)))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, 4.6), sharex=True, gridspec_kw={"height_ratios": [1, 1]})
    for ax, key, scale, color, label in ((a1, "orders", 1, GOLD, "Orders"), (a2, "revenue_paise", 100000, BLUE, "Revenue (Rs thousand)")):
        vals = [d[key] / scale for d in days]
        bars = ax.bar(x, vals, color=color, width=0.7)
        if last_partial:
            bars[-1].set_alpha(0.45)
            bars[-1].set_hatch("///")
            bars[-1].set_edgecolor("white")
        ax.set_ylabel(label)
    a2.set_xticks(range(0, len(days), 5), [days[i]["date"][5:] for i in range(0, len(days), 5)])
    a2.set_xlabel("Day (month-day, IST)" + ("; hatched bar is the unfinished day" if last_partial else ""))
    a1.set_title("Demo shop: orders and revenue per day (generated data)")
    return save(fig, "fig-demo-sales")


def fig_demo_mix() -> str:
    ov = D["overview"]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(7.4, 3.2), gridspec_kw={"width_ratios": [1.3, 1, 1]})
    tp = ov["top_products"][:6]
    a1.barh(range(len(tp)), [p["revenue_paise"] / 100000 for p in tp], color=BLUE, height=0.6)
    a1.set_yticks(range(len(tp)), [p["name"].split(" (")[0][:22] for p in tp], fontsize=7)
    a1.invert_yaxis()
    a1.set_xlabel("Revenue (Rs thousand)")
    a1.set_title("Top products")
    ol = ov["orders_by_language"]
    a2.bar(range(len(ol)), [o["orders"] for o in ol], color=GOLD, width=0.65)
    a2.set_xticks(range(len(ol)), [lang_name(o["language"]) for o in ol], rotation=45, ha="right", fontsize=7)
    a2.set_ylabel("Orders")
    a2.set_title("By language")
    st = ov["orders_by_status"]
    a3.bar(range(len(st)), [s["orders"] for s in st], color=[GOLD, GREEN, MUTED], width=0.6)
    a3.set_xticks(range(len(st)), [s["status"].capitalize() for s in st], rotation=30, fontsize=7)
    a3.set_ylabel("Orders")
    a3.set_title("By status")
    return save(fig, "fig-demo-mix")


def fig_stock_movement() -> str:
    rows = D["stock_movement"]["rows"][:8]
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    w = 0.26
    xs = range(len(rows))
    ax.bar([x - w for x in xs], [r["sold"] for r in rows], width=w, color=ORANGE, label="Sold")
    ax.bar(list(xs), [r["added"] for r in rows], width=w, color=GREEN, label="Restocked")
    ax.bar([x + w for x in xs], [r["returned"] for r in rows], width=w, color=BLUE, label="Returned by a cancelled order")
    ax.set_xticks(list(xs), [r["name"].split(" (")[0][:16] for r in rows], fontsize=8)
    for off, key in ((-w, "sold"), (0, "added"), (w, "returned")):
        for x_, r in zip(xs, rows):
            if r[key]:
                ax.text(x_ + off, r[key] + 0.12, f"{r[key]:g}", ha="center", fontsize=7)
    ax.set_ylabel("Quantity (kg, litre or pack)")
    ax.legend()
    ax.set_title("Stock movement recorded by the demo run")
    return save(fig, "fig-stock-movement")


def fig_payments() -> str:
    a = D["payments"]["analytics"]
    k = a["kpis"]
    by = {m["method"]: m for m in a["by_method"]}
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.3), gridspec_kw={"width_ratios": [1, 1.15]})
    ways = [("cash", "Cash", GOLD), ("upi", "UPI QR,\nconfirmed\nby hand", BLUE), ("razorpay", "Razorpay\n(not used\nhere)", MUTED)]
    vals = [by.get(w, {}).get("collected_paise", 0) / 100 for w, _, _ in ways]
    a1.bar(range(3), vals, color=[c for _, _, c in ways], width=0.6)
    for i, v in enumerate(vals):
        a1.text(i, v + max(vals) * 0.02, f"{v:,.0f}", ha="center", fontsize=8)
    a1.set_xticks(range(3), [l for _, l, _ in ways], fontsize=7.5)
    a1.set_ylim(0, max(vals) * 1.15)
    a1.set_ylabel("Rupees")
    a1.set_title("Collected, by way paid")
    parts = [("Collected", k["collected_paise"], BLUE), ("Refunded", k["refunds_paise"], ORANGE), ("Net", k["net_paise"], GREEN), ("Waiting\nfor payment", k["pending_paise"], AMBER)]
    v2 = [v / 100 for _, v, _ in parts]
    a2.bar(range(len(parts)), v2, color=[c for _, _, c in parts], width=0.6)
    for i, v in enumerate(v2):
        a2.text(i, v + max(v2) * 0.02, f"{v:,.0f}", ha="center", fontsize=8)
    a2.set_xticks(range(len(parts)), [l for l, _, _ in parts], fontsize=7.5)
    a2.set_ylim(0, max(v2) * 1.15)
    a2.set_ylabel("Rupees")
    a2.set_title("Money picture of the session")
    fig.suptitle("Payments recorded by the scripted demo session (not real sales)", fontsize=10, fontweight="bold", color=INK)
    return save(fig, "fig-payments")


def fig_latency() -> str:
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    items = [("Parser alone", S["parser_latency"]["p50_ms"], S["parser_latency"]["p95_ms"])]
    labels = {"text_turn": "One order turn", "confirm_order_with_stock_update": "Confirm and take stock", "inventory_list": "Product list", "orders_page_20": "Orders page (20)", "analytics_overview_30d": "Analytics overview"}
    if A:
        items += [(lab, A[k]["p50_ms"], A[k]["p95_ms"]) for k, lab in labels.items() if k in A]
    y = list(range(len(items)))
    ax.hlines(y, [i[1] for i in items], [i[2] for i in items], color=GRID, linewidth=3, zorder=1)
    ax.scatter([i[1] for i in items], y, s=46, color=BLUE, zorder=3, label="Median", edgecolor="white", linewidth=1)
    ax.scatter([i[2] for i in items], y, s=46, color=AMBER, zorder=3, label="95th percentile", edgecolor="white", linewidth=1, marker="D")
    for k, it in enumerate(items):
        ax.text(it[2] * 1.18, k, f"{it[1]:g} / {it[2]:g} ms", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(y, [i[0] for i in items])
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(0.08, 400)
    ax.set_xlabel("Milliseconds (log scale); labels read median / 95th percentile")
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    ax.set_title("Measured response times (one machine, no Gnani call)")
    return save(fig, "fig-latency")


FIGURES = {
    "datasets": (fig_datasets, "Evaluation sentences by dataset", "Count of all sentences and of the order sentences that are scored, per dataset.", "eval/results/evaluation_summary.json, key datasets and branded"),
    "language-heatmap": (fig_language_heatmap, "Exact order match by language and sentence set", "Share of sentences for which every parsed line (product, quantity, unit) equals the gold lines. Empty cells are sets that do not contain that language.", "evaluation_summary.json, key sentence_check"),
    "branded-by-language": (fig_branded_by_language, "How each held-out branded sentence ended, by language", "Counts of the four outcomes for the 300 held-out branded sentences in the four original languages.", "evaluation_summary.json, key branded.by_language"),
    "category-confusion": (fig_category_confusion, "Expected category against outcome for held-out branded sentences", "Rows are the category of the product the sentence asked for; columns are the category of the product the parser returned, or one of the two safe outcomes. Off-diagonal cells in a category column are wrong products.", "evaluation_summary.json, key branded.confusion"),
    "language-labels": (fig_language_labels, "Language label returned for each sentence", "Confusion matrix of the language the parser reported against the language the sentence was written in, as a share of each row.", "evaluation_summary.json, key language_detection"),
    "error-distribution": (fig_error_distribution, "Outcome of held-out branded sentences", "The four possible outcomes with counts and shares.", "evaluation_summary.json, key branded.verdicts"),
    "noise": (fig_noise, "Robustness to damaged text", "Score against the share of characters randomly damaged, with the spread over random seeds for the whole-order measure.", "evaluation_summary.json, key noise.levels"),
    "ablation": (fig_ablation, "What each matching stage adds at 6% damage", "Whole-order accuracy as matching stages are switched on one after another.", "evaluation_summary.json, key noise.ablation"),
    "end-to-end": (fig_end_to_end, "End-to-end typed orders and the stock guard", "Left: outcome of sentences taken through the dialogue to a saved order. Right: what happened when the same orders met an empty shelf or half the needed stock.", "evaluation_summary.json, key end_to_end"),
    "payments": (fig_payments, "Payments of the scripted demo session", "Left: money collected by way paid, from the payment analytics. Right: collected, refunded, net and still waiting. Four payments and one part refund made through the app's own routes on a throw-away database; Razorpay was not used.", "docs/report-data/demo_activity.json, payments.analytics"),
    "latency": (fig_latency, "Measured response times", "Median and 95th percentile of the parser alone and of local HTTP requests, on a logarithmic axis because the values differ by orders of magnitude. The parser timing is from the 2.7.0 evaluation build; the HTTP timings were measured on the 2.6.0 backend and not repeated for 2.7.0.", "evaluation_summary.json parser_latency; eval/results/api_latency.json"),
    "demo-sales": (fig_demo_sales, "Demo shop, orders and revenue per day", "Generated demo orders over the last 30 days (not real sales).", "docs/report-data/demo_activity.json, overview.sales_by_day"),
    "demo-mix": (fig_demo_mix, "Demo shop, top products, language and status mix", "Revenue of the six best sellers, orders by language, and orders by status, from generated demo orders plus the six typed orders placed by scripts/demo_activity.py.", "docs/report-data/demo_activity.json, overview"),
    "stock-movement": (fig_stock_movement, "Stock movement recorded by the demo run", "Quantities sold, restocked and returned for the products touched by six typed orders, two restocks and one cancellation.", "docs/report-data/demo_activity.json, stock_movement"),
}


# ------------------------------------------------------------------------------------------------ tables
def table_technology() -> str:
    return md_table(["Component", "Technology", "Purpose", "Implementation status"], [[t["component"], t["technology"], t["purpose"], t["status"]] for t in S["technology"]])


def table_datasets() -> str:
    return md_table(["Dataset", "Sentences", "Order sentences", "Languages", "How it was made"], [[d["name"], d["n"], d["n_order"], ", ".join(d["languages"]), d["provenance"]] for d in S["datasets"]], ["", "r", "r", "", ""])


def table_languages() -> str:
    rows, cols, cell = _lang_dataset_matrix()
    out = []
    ld = {r["lang"]: r for r in S["language_detection"]["per_language"]}
    e2e = S["end_to_end"]["by_language"]
    for l in rows:
        n = sum(cell[(l, d)]["n"] for d, _ in cols if (l, d) in cell and d != "branded")
        ex = sum(cell[(l, d)]["exact"] for d, _ in cols if (l, d) in cell and d != "branded")
        br = cell.get((l, "branded"))
        e = e2e.get(l, {})
        out.append([lang_name(l), n, pct(ex, n), f"{br['exact']} of {br['n']} ({br['exact_pct']:.1f}%)" if br else "not in set", f"{ld[l]['correct']} of {ld[l]['n']} ({ld[l]['pct']:.1f}%)" if l in ld else "n/a", f"{e.get('order_correct', 0)} of {sum(e.values())}" if e else "n/a"])
    return md_table(["Language", "Sentences (non-brand sets)", "Exact order match", "Held-out brands exact", "Language label correct", "Typed order correct"], out, ["", "r", "r", "r", "r", "r"])


def table_metrics() -> str:
    b, v, e, g = S["branded"], S["branded"]["verdicts"], S["end_to_end"], S["end_to_end"]["stock_guard"]
    sc = lambda ds: (sum(r["n"] for r in S["sentence_check"] if r["dataset"] == ds), sum(r["exact"] for r in S["sentence_check"] if r["dataset"] == ds))
    rows = []
    for ds, label, note in (("handwritten", "Exact order match, handwritten sentences", "Written by the parser's author: a ceiling, not a forecast"), ("templated", "Exact order match, templated sentences", "Generated from templates over the staples"), ("authored", "Exact order match, authored sentences, 11 languages", "Seven languages have no native-speaker review")):
        n, x = sc(ds)
        rows.append([label, f"{pct(x, n)} ({x} of {n})", f"{ds} set", "Every parsed line must equal the gold lines", note])
    rows += [
        ["Held-out brands: exact product", f"{b['exact_pct']}% ({v['exact']} of {b['cases']})", "Held-out branded sentences", "The single product returned must be the expected one", "Optimistic: sentences are built from the product name and never name a pack size"],
        ["Held-out brands: wrong product", f"{b['wrong_product_pct']}% ({v['wrong_product']} of {b['cases']})", "Held-out branded sentences", "One product returned and it is not the expected one", "The costly error; listed pair by pair in the report"],
        ["Held-out brands: asked which pack", f"{pct(v['ambiguous_contains_expected'], b['cases'])} ({v['ambiguous_contains_expected']} of {b['cases']})", "Held-out branded sentences", "Several plausible products; the right one is among the options offered", "Safe: the shopkeeper chooses"],
        ["Held-out brands: not recognised", f"{pct(v['not_recognised'], b['cases'])} ({v['not_recognised']} of {b['cases']})", "Held-out branded sentences", "No product returned", "Safe: becomes a question"],
        ["Typed order end to end", f"{e['outcomes'].get('order_correct', 0)} of {e['n_scored']} correct", f"All {e['n_sentences']} sentences, 11 languages", "Sentence, \"that's all\", \"confirm\" through the real dialogue; stored lines must equal gold", f"{e['n_sentences'] - e['n_scored']} sentences whose gold cannot be written as an order are not scored"],
        ["Stock guard, empty shelf", f"{g['empty_refused']} of {g['empty_checked']} refused; {g['empty_negative_stock']} negative stock", "Orders from the end-to-end set", "Every needed item at zero stock", "No order may be created"],
        ["Stock guard, half stock", f"{g['half_asked_or_offered']} asked or offered, {g['half_refused']} refused; {g['half_negative_stock']} over-stock orders", "Orders from the end-to-end set", "Half the needed quantity on the shelf", "The assistant offers what is left"],
    ]
    for l in S["noise"]["levels"]:
        rows.append([f"Noise {round(100 * l['cer'])}%: whole order exact", f"{100 * l['utterance_exact']:.1f}% (range {100 * l['utterance_exact_min']:.1f} to {100 * l['utterance_exact_max']:.1f})", f"Handwritten order sentences x {S['noise']['seeds']} seeds", "Random character damage; the whole order must equal gold", "Simulated typing damage, not acoustic noise"])
    pl = S["parser_latency"]
    rows.append(["Parser time per sentence", f"p50 {pl['p50_ms']} ms, p95 {pl['p95_ms']} ms", f"{pl['n']} timings", "Wall-clock time of the parser alone", "Excludes speech and the network"])
    if A:
        rows.append(["Server response, one order turn", f"p50 {A['text_turn']['p50_ms']} ms, p95 {A['text_turn']['p95_ms']} ms", f"{A['text_turn']['n']} requests, {A['machine']}", "Local loopback HTTP, signed in, throw-away database", "One machine, one process; measured on the 2.6.0 backend and not repeated for 2.7.0; not what a shop on a real network sees"])
    rows += [
        ["Speech recognition time (Prisma)", "Not measured", "None", "Would need live Gnani calls", "No live call has been made"],
        ["Speech synthesis time (Timbre)", "Not measured", "None", "Would need live Gnani calls", "No live call has been made"],
        ["Word error rate", "Not measured", "None", "Needs recorded speech with reference transcripts and live calls", "No such recordings exist in this project"],
    ]
    return md_table(["Metric", "Result", "Dataset", "Method", "Interpretation"], rows)


def table_prf() -> str:
    return md_table(["Simulated damage", "Order-line precision", "Order-line recall", "Order-line F1", "Product precision", "Product recall", "Product F1", "Whole order exact"], [[f"{round(100 * l['cer'])}%", *(f"{l[k]:.3f}" for k in ("line_precision", "line_recall", "line_f1", "product_precision", "product_recall", "product_f1", "utterance_exact"))] for l in S["noise"]["levels"]], ["r"] * 8)


def table_wrong_pairs() -> str:
    w = S["branded"]["confusion"]["wrong_pairs"]
    return md_table(["Expected product", "Product returned instead", "Sentences"], [[p["expected"], p["got"], p["count"]] for p in w], ["", "", "r"])


def table_catalogue() -> str:
    items = [i for i in D["inventory"] if i["source"] == "curated"][:12] + [i for i in D["inventory"] if i["source"] != "curated"][:4]
    st = {"ok": "In stock", "low": "Low stock", "out": "Out of stock"}
    return md_table(["Product", "Brand", "Category", "Pack size", "Unit price", "Stock", "Status"], [[i["name_en"], i["brand"] or "-", i["category"], (f"{i['pack_size']:g} {i['pack_size_unit']}" if i["pack_size"] else "sold loose"), f"{inr(i['price_paise'])} ({'demo price' if i['price_basis'] == 'demo' else 'shop price'})", f"{i['stock']:g} {i['unit']}", st.get(i["stock_status"], i["stock_status"])] for i in items], ["", "", "", "", "r", "r", ""])


def table_orders() -> str:
    rows = []
    for o in D["orders"][:12]:
        items = ", ".join(f"{i['name']} x {i['qty']:g} {i['unit']}" for i in o["items"])
        when = datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %H:%M")
        rows.append([o["code"], o["customer_name"] + (" (demo)" if o["is_synthetic"] else " (typed in the demo run)"), items, f"{sum(i['qty'] for i in o['items']):g}", inr(o["total_paise"]), o["language"], o["status"].capitalize(), when])
    return md_table(["Order", "Customer", "Products and quantities", "Units", "Total", "Language", "Status", "When (UTC)"], rows, ["", "", "", "r", "r", "", "", ""])


def table_inventory_performance() -> str:
    st = {"ok": "OK", "low": "Reorder soon", "out": "Out of stock"}
    return md_table(["Product", "Opening", "Added", "Returned", "Sold", "Current", "Reorder status"], [[r["name"], f"{r['opening']:g}", f"{r['added']:g}", f"{r['returned']:g}", f"{r['sold']:g}", f"{r['current']:g}", st.get(r["status"], r["status"])] for r in D["stock_movement"]["rows"]], ["", "r", "r", "r", "r", "r", ""])


_WAY = {"cash": "Cash", "upi": "UPI QR (shop's own ID)", "razorpay": "Razorpay"}
_PSTATUS = {"pending": "Waiting", "paid": "Paid", "failed": "Failed", "cancelled": "Cancelled", "partially_refunded": "Partly refunded", "refunded": "Refunded"}


def table_payments() -> str:
    rows = sorted(D["payments"]["history"]["items"], key=lambda r: r["id"])
    return md_table(["Payment", "Order", "Way", "Status", "How it was confirmed", "Bill", "Refunded"],
                    [[r["code"], r["order_code"], _WAY.get(r["method"], r["method"]), _PSTATUS.get(r["status"], r["status"]), r["verification_label"], inr(r["amount_paise"]), inr(r["refunded_paise"]) if r["refunded_paise"] else "-"] for r in rows],
                    ["", "", "", "", "", "r", "r"])


def table_payment_kpis() -> str:
    k = D["payments"]["analytics"]["kpis"]
    rows = [
        ["Collected", inr(k["collected_paise"]), f"{k['paid_count']} payments that reached paid, before refunds"],
        ["Refunded", inr(k["refunds_paise"]), f"{k['refund_count']} refund, processed"],
        ["Net", inr(k["net_paise"]), "Collected minus refunded"],
        ["Average payment", inr(k["average_paise"]), "Collected divided by paid payments"],
        ["Cash", inr(k["cash_paise"]), "Recorded by a person"],
        ["UPI", inr(k["upi_paise"]), f"Of which confirmed by hand and not verified by any provider: {inr(k['upi_manual_paise'])}"],
        ["Razorpay", inr(k["razorpay_paise"]), "Not used in this session"],
        ["Waiting for payment", inr(k["pending_paise"]), f"{k['pending_count']} payment, not counted as collected"],
        ["Failed", inr(k["failed_paise"]), f"{k['failed_count']} payments"],
        ["Refunds waiting for Razorpay", inr(k["refunds_waiting_paise"]), f"{k['refunds_waiting_count']} refunds"],
        ["Needs the owner's attention", k["needs_attention"], "Payments flagged for a mismatch, a late or a duplicate collection"],
    ]
    return md_table(["Measure", "Value", "What it counts"], rows, ["", "r", ""])


def table_invoice() -> str:
    inv = D["payments"]["invoice"]
    rows = [[i["name"], f"{i['qty']:g} {i['unit']}", inr(i["unit_price_paise"]), inr(i["line_total_paise"])] for i in inv["items"]]
    rows += [["Subtotal", "", "", inr(inv["subtotal_paise"])], ["Discount", "", "", inr(inv["discount_paise"])], ["Total", "", "", inr(inv["total_paise"])],
             [f"Paid: {inv['payment']['label']}", "", "", inr(inv["payment"]["amount_paise"])]]
    return md_table(["Item", "Quantity", "Unit price", "Amount"], rows, ["", "r", "r", "r"])


def table_tests() -> str:
    if not V:
        return "*No test record exists yet. Run the checks in docs/TESTING.md and then python scripts/build_verification_summary.py.*"
    f = lambda x: "-" if x is None else x
    return md_table(["Category", "Total", "Passed", "Failed", "Skipped", "Status", "How and when it ran"], [[r["category"], f(r["total"]), f(r["passed"]), f(r["failed"]), f(r["skipped"]), r["status"], f"{r['how']}. {r['ran']}"] for r in V["rows"]], ["", "r", "r", "r", "r", "", ""])


def table_http() -> str:
    if not A:
        return "*No HTTP benchmark file exists. Run scripts/benchmark_api.py against a throw-away database.*"
    labels = {"text_turn": "One order turn", "confirm_order_with_stock_update": "Confirm an order and take stock", "inventory_list": "Product list", "orders_page_20": "Orders page, 20 rows", "analytics_overview_30d": "Analytics overview, 30 days", "analytics_stock_movement_30d": "Stock movement, 30 days", "catalogue_search": "Catalogue search", "global_search": "Search everything", "evaluation_summary": "Evaluation results file"}
    return md_table(["Request", "Median (ms)", "95th percentile (ms)", "Slowest (ms)", "Requests"], [[lab, A[k]["p50_ms"], A[k]["p95_ms"], A[k]["max_ms"], A[k]["n"]] for k, lab in labels.items() if k in A], ["", "r", "r", "r", "r"])


TABLES = {
    "technology": (table_technology, "Technology stack and implementation status", "eval/results/evaluation_summary.json, key technology"),
    "datasets": (table_datasets, "Evaluation datasets", "evaluation_summary.json, keys datasets and branded; files eval/utterances.jsonl and eval/language_sentences.jsonl"),
    "languages": (table_languages, "Language evaluation (text only)", "evaluation_summary.json, keys sentence_check, language_detection and end_to_end"),
    "metrics": (table_metrics, "AI evaluation metrics", "evaluation_summary.json and eval/results/api_latency.json"),
    "prf": (table_prf, "Precision, recall and F1 under simulated text damage", "evaluation_summary.json, key noise.levels"),
    "wrong-pairs": (table_wrong_pairs, "Every wrong product returned for a held-out branded sentence", "evaluation_summary.json, key branded.confusion.wrong_pairs"),
    "catalogue": (table_catalogue, "Product catalogue of the demo shop (sample)", "docs/report-data/demo_activity.json, inventory. Demo data: prices are placeholders; the last four rows were imported from the public catalogue at prices typed for the demo"),
    "orders": (table_orders, "Orders of the demo shop (latest twelve)", "docs/report-data/demo_activity.json, orders. Rows marked (demo) are generated; the others were typed through the order desk by scripts/demo_activity.py"),
    "inventory-performance": (table_inventory_performance, "Inventory performance of the demo run", "docs/report-data/demo_activity.json, stock_movement (read from the stock ledger; opening = current minus net movements)"),
    "payments": (table_payments, "Payments recorded by the scripted demo session", "docs/report-data/demo_activity.json, payments.history (the app's own payment list; one order was left without a payment record on purpose and one had been cancelled before any payment)"),
    "payment-kpis": (table_payment_kpis, "Payment analytics of the scripted demo session", "docs/report-data/demo_activity.json, payments.analytics.kpis (summed from the payments and refunds tables only)"),
    "invoice": (table_invoice, "An invoice as the app issues it", "docs/report-data/demo_activity.json, payments.invoice (a receipt for a demo order; it is not a GST tax invoice)"),
    "tests": (table_tests, "Test and verification record", "eval/results/verification_summary.json, counted from the saved test logs"),
    "http": (table_http, "Local HTTP response times", "eval/results/api_latency.json (scripts/benchmark_api.py, throw-away database, no Gnani calls; measured on the 2.6.0 backend and not repeated for 2.7.0)"),
}


# ------------------------------------------------------------------------------------------------ values
BACKEND_ROWS = ("Accounts, sessions and security", "Order parser and dialogue", "Gnani client (mocked HTTP, not live)", "Shop API, data and evaluation files",
                "Voice path, diagnostics and update safety (2.6)", "Payments, refunds, invoices and migration (2.7, Razorpay simulated)", "Branding, wording and Windows scripts")


OTHER_ROWS = ("Front-end tests", "Front-end build", "Real-browser end-to-end checks", "Real-browser control sweep", "Dependency audits", "Parser regression check", "Stock guard")


def _grab(log: str, pattern: str):
    f = DOCS / "test-results" / log
    m = re.search(pattern, f.read_text(encoding="utf-8", errors="replace")) if f.exists() else None
    return m.groups() if m else None


def values() -> dict[str, str]:
    b, v, e, g, n = S["branded"], S["branded"]["verdicts"], S["end_to_end"], S["end_to_end"]["stock_guard"], S["noise"]
    lv = {round(100 * l["cer"]): l for l in n["levels"]}
    ab = {a["label"]: a for a in n["ablation"] if abs(a["cer"] - 0.06) < 1e-9}
    ld = S["language_detection"]
    diag = sum(ld["matrix"][i][i] for i in range(len(ld["labels"])))
    sc = lambda ds: (sum(r["n"] for r in S["sentence_check"] if r["dataset"] == ds), sum(r["exact"] for r in S["sentence_check"] if r["dataset"] == ds))
    vals = {
        "version": S["app_version"], "built": S["generated_at"][:10], "date": datetime.now().strftime("%-d %B %Y"),
        "b_cases": b["cases"], "b_exact": v["exact"], "b_wrong": v["wrong_product"], "b_notrec": v["not_recognised"], "b_asked": v["ambiguous_contains_expected"],
        "b_exact_pct": b["exact_pct"], "b_wrong_pct": b["wrong_product_pct"], "b_notrec_pct": pct(v["not_recognised"], b["cases"]).rstrip("%"), "b_asked_pct": pct(v["ambiguous_contains_expected"], b["cases"]).rstrip("%"),
        "b_safe_pct": b["recognised_or_asked_pct"],
        "e_total": e["n_sentences"], "e_scored": e["n_scored"], "e_correct": e["outcomes"].get("order_correct", 0), "e_skipped": e["n_sentences"] - e["n_scored"], "e_wrong": e["outcomes"].get("order_wrong", 0),
        "g_empty": g["empty_checked"], "g_empty_refused": g["empty_refused"], "g_neg": g["empty_negative_stock"] + g["half_negative_stock"], "g_half": g["half_checked"], "g_half_asked": g["half_asked_or_offered"], "g_half_refused": g["half_refused"],
        "n_seeds": n["seeds"], "n_sent": n["n_sentences"], "n0": f"{100 * lv[0]['utterance_exact']:.0f}", "n3": f"{100 * lv[3]['utterance_exact']:.1f}", "n6": f"{100 * lv[6]['utterance_exact']:.1f}", "n10": f"{100 * lv[10]['utterance_exact']:.1f}", "n15": f"{100 * lv[15]['utterance_exact']:.1f}",
        "n6_prec": f"{lv[6]['line_precision']:.3f}", "n6_rec": f"{lv[6]['line_recall']:.3f}", "n6_f1": f"{lv[6]['line_f1']:.3f}",
        "ab_first": f"{100 * list(ab.values())[0]['utterance_exact']:.1f}", "ab_last": f"{100 * list(ab.values())[-1]['utterance_exact']:.1f}",
        "p50": S["parser_latency"]["p50_ms"], "p95": S["parser_latency"]["p95_ms"], "p_n": S["parser_latency"]["n"],
        "ld_n": ld["n"], "ld_diag": diag, "ld_pct": pct(diag, ld["n"]), "ld_mr": next((f"{r['pct']:.1f}" for r in ld["per_language"] if r["lang"] == "mr"), "n/a"),
        "ds_hand": S["datasets"][0]["n"], "ds_templ": S["datasets"][1]["n"], "ds_auth": S["datasets"][2]["n"],
        "hand_pct": pct(sc("handwritten")[1], sc("handwritten")[0]), "templ_pct": pct(sc("templated")[1], sc("templated")[0]), "auth_pct": pct(sc("authored")[1], sc("authored")[0]),
        "demo_orders": len(D["orders_placed"]), "demo_moves": D["stock_movement"]["movements"], "demo_products_moved": D["stock_movement"]["products_moved"], "demo_imported": len(D["imported"]),
        "demo_in": inr(D["stock_movement"]["totals"]["in_paise"]), "demo_out": inr(D["stock_movement"]["totals"]["out_paise"]),
        "kpi_orders": D["overview"]["kpis"]["orders"], "kpi_revenue": inr(D["overview"]["kpis"]["revenue_paise"]), "kpi_aov": inr(D["overview"]["kpis"]["avg_basket_paise"]),
    }
    if A:
        vals.update({"http_orders": f"{A['orders_in_database']:,}", "http_turn_p50": A["text_turn"]["p50_ms"], "http_turn_p95": A["text_turn"]["p95_ms"], "http_confirm_p50": A["confirm_order_with_stock_update"]["p50_ms"], "http_confirm_p95": A["confirm_order_with_stock_update"]["p95_ms"], "http_machine": A["machine"]})
    else:
        vals.update({k: "not measured" for k in ("http_orders", "http_turn_p50", "http_turn_p95", "http_confirm_p50", "http_confirm_p95", "http_machine")})
    if V:
        by = {r["category"]: r for r in V["rows"]}
        back = [r for r in V["rows"] if r["category"] in BACKEND_ROWS]
        unknown = [r["category"] for r in V["rows"] if r["total"] is not None and r["category"] not in BACKEND_ROWS and r["category"] not in OTHER_ROWS]
        if unknown:
            sys.exit("verification_summary.json has rows the report does not know how to count: " + ", ".join(unknown))
        pay = next((r for r in V["rows"] if r["category"].startswith("Payments, refunds, invoices and migration")), None)
        vals.update({"t_back_total": sum(r["total"] or 0 for r in back), "t_back_passed": sum(r["passed"] or 0 for r in back), "t_back_failed": sum(r["failed"] or 0 for r in back), "t_back_skipped": sum(r["skipped"] or 0 for r in back),
                     "t_front_total": by["Front-end tests"]["total"], "t_front_passed": by["Front-end tests"]["passed"], "t_e2e": f"{by['Real-browser end-to-end checks']['passed']} of {by['Real-browser end-to-end checks']['total']}", "t_ctl": f"{by['Real-browser control sweep']['passed']} of {by['Real-browser control sweep']['total']}",
                     "t_nlu": f"{by['Parser regression check']['passed']} of {by['Parser regression check']['total']}", "t_when": V["generated_at"][:10],
                     "t_pay_total": pay["total"] if pay else "not recorded", "t_pay_passed": pay["passed"] if pay else "not recorded"})
    else:
        vals.update({k: "not recorded" for k in ("t_back_total", "t_back_passed", "t_back_failed", "t_back_skipped", "t_front_total", "t_front_passed", "t_e2e", "t_ctl", "t_nlu", "t_when", "t_pay_total", "t_pay_passed")})
    # facts that only the saved logs hold: statement coverage, the number of front-end test files, the update check
    cov = _grab("backend_pytest.txt", r"TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%")
    vf = _grab("frontend_vitest.txt", r"Test Files\s+(\d+) passed \((\d+)\)")
    up = _grab("update_in_place_check.txt", r"(\d+) of (\d+) checks passed")
    vals.update({"t_cov_pct": cov[2] if cov else "not recorded", "t_cov_stmts": f"{int(cov[0]):,}" if cov else "not recorded", "t_front_files": vf[0] if vf else "not recorded",
                 "t_update": f"{up[0]} of {up[1]}" if up else "not recorded"})
    P = D["payments"]
    # the template states three things about the scripted session; refuse to build if the data says otherwise
    if P["cancel_paid_order"]["http_status"] != 409 or not P["invoice_number_stable"] or not P["stock_unchanged"]["all_same"] or P["stock_unchanged"]["movements_before"] != P["stock_unchanged"]["movements_after"]:
        sys.exit("the payment session data contradicts what the template says (cancel refused, invoice number kept, stock unchanged). Look at docs/report-data/demo_activity.json before building")
    k = P["analytics"]["kpis"]
    vals.update({
        "pay_n": len(P["history"]["items"]), "pay_paid_n": k["paid_count"], "pay_pending_n": k["pending_count"],
        "pay_collected": inr(k["collected_paise"]), "pay_refunded": inr(k["refunds_paise"]), "pay_net": inr(k["net_paise"]), "pay_cash": inr(k["cash_paise"]),
        "pay_upi": inr(k["upi_paise"]), "pay_pending": inr(k["pending_paise"]), "pay_razorpay": inr(k["razorpay_paise"]),
        "pay_cancel_status": P["cancel_paid_order"]["http_status"], "pay_cancel_code": P["cancel_paid_order"]["code"], "pay_invoice_no": P["invoice"]["number"],
        "pay_stock_products": P["stock_unchanged"]["products_compared"], "pay_moves": P["stock_unchanged"]["movements_after"],
    })
    return {k: (f"{x:,}" if isinstance(x, int) and abs(x) >= 1000 else str(x)) for k, x in vals.items()}


# ------------------------------------------------------------------------------------------------ render
def render() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    vals = values()
    fig_no: dict[str, int] = {}
    tab_no: dict[str, int] = {}
    for kind, store in (("fig", fig_no), ("table", tab_no)):
        for m in re.finditer(r"\{\{%s:([\w-]+)\}\}" % kind, text):
            store.setdefault(m.group(1), len(store) + 1)
    missing = []

    def ref(m):
        kind, name = m.group(1), m.group(2)
        store = fig_no if kind == "fig" else tab_no
        if name not in store:
            missing.append(m.group(0))
            return "??"
        return f"{'Figure' if kind == 'fig' else 'Table'} {store[name]}"

    text = re.sub(r"\{\{ref:(fig|table):([\w-]+)\}\}", ref, text)

    def fig(m):
        name = m.group(1)
        if name not in FIGURES:
            missing.append(m.group(0))
            return "??"
        fn, title, what, source = FIGURES[name]
        path = fn()
        return f"![Figure {fig_no[name]}. {title}]({path}){{ width=100% }}\n\n*Figure {fig_no[name]}. {title}.* {what} *Source: {source}.*"

    def table(m):
        name = m.group(1)
        if name not in TABLES:
            missing.append(m.group(0))
            return "??"
        fn, title, source = TABLES[name]
        return f"**Table {tab_no[name]}. {title}.**\n\n{fn()}\n\n*Source: {source}.*"

    text = re.sub(r"\{\{fig:([\w-]+)\}\}", fig, text)
    text = re.sub(r"\{\{table:([\w-]+)\}\}", table, text)

    def val(m):
        k = m.group(1).strip()
        if k not in vals:
            missing.append(m.group(0))
            return "??"
        return vals[k]

    text = re.sub(r"\{\{\s*([a-z0-9_]+)\s*\}\}", val, text)
    if missing:
        sys.exit("report template has markers with no value: " + ", ".join(sorted(set(missing))))
    return text


def build_files() -> None:
    css = DOCS / "report" / "report.css"
    html = Path("/tmp/swara-report.html") if sys.platform != "win32" else Path(ROOT / "docs" / "report" / "_report.html")
    subprocess.run(["pandoc", "PROJECT_REPORT.md", "-s", "--embed-resources", "-c", str(css), "--resource-path=.:..", "-o", str(html)], cwd=DOCS, check=True)
    subprocess.run(["pandoc", "PROJECT_REPORT.md", "--resource-path=.:..", "-o", "PROJECT_REPORT.docx"], cwd=DOCS, check=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(html.resolve().as_uri())
        pg.pdf(path=str(DOCS / "PROJECT_REPORT.pdf"), format="A4", print_background=True, prefer_css_page_size=True)
        b.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", action="store_true", help="also write PROJECT_REPORT.docx and .pdf")
    a = ap.parse_args()
    load()
    out = render()
    (DOCS / "PROJECT_REPORT.md").write_text(out, encoding="utf-8")
    print(f"wrote docs/PROJECT_REPORT.md ({len(out.split()):,} words) and {len(list(FIGS.glob('*.png')))} figures")
    if a.files:
        build_files()
        print("wrote docs/PROJECT_REPORT.docx and docs/PROJECT_REPORT.pdf")


if __name__ == "__main__":
    main()
