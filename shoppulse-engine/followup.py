"""
ShopPulse — Follow-up comparison tool.

Compares a new diagnosis against a saved baseline to measure what changed.
Generates a before/after report and logs outcomes.

Usage:
    python3 followup.py new_screenshot.png --baseline baseline_shopname_2026-03-28.json
    python3 followup.py new_data.json --baseline baseline_shopname_2026-03-28.json

Output:
    - Comparison report (HTML)
    - Appends to outcomes.jsonl
"""

import sys
import os
import json
from datetime import date

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import diagnose
import report as report_mod


OUTCOME_FILE = os.path.join(PROJECT_DIR, "outcomes.jsonl")


def classify_outcome(pre_views, post_views, pre_orders, post_orders):
    """Classify the outcome of a recommendation."""
    views_changed = post_views - pre_views
    orders_changed = post_orders - pre_orders

    if pre_views == 0 and post_views == 0:
        return "no_data"
    if orders_changed > 0:
        return "helped"
    if views_changed > 0 and orders_changed == 0:
        return "inconclusive"
    if views_changed <= 0 and orders_changed <= 0:
        return "no_clear_evidence"
    return "inconclusive"


def detect_changes(base_listing, new_listing):
    """Detect what changed between baseline and follow-up for a listing."""
    changes = []

    bt = base_listing.get("title", "")
    nt = new_listing.get("title", "")
    if bt and nt and bt != nt:
        changes.append(f"Title changed")

    bp = base_listing.get("price")
    np = new_listing.get("price")
    if bp and np and bp != np:
        changes.append(f"Price: ${bp} -> ${np}")

    bph = base_listing.get("photo_count")
    nph = new_listing.get("photo_count")
    if bph is not None and nph is not None and nph > bph:
        changes.append(f"Photos: {bph} -> {nph}")

    bv = base_listing.get("has_video")
    nv = new_listing.get("has_video")
    if bv is False and nv is True:
        changes.append("Video added")

    bs = base_listing.get("on_sale")
    ns = new_listing.get("on_sale")
    if bs is True and ns is not True:
        changes.append("Sale removed")

    bf = base_listing.get("free_shipping")
    nf = new_listing.get("free_shipping")
    if bf is not True and nf is True:
        changes.append("Free shipping added")

    return changes


def match_listings(base_listings, new_listings):
    """Match baseline listings to new listings by title similarity."""
    matches = []
    used_new = set()

    for bl in base_listings:
        bt = bl.get("title", "").lower().replace("...", "").strip()
        if not bt:
            continue
        best_match = None
        best_score = 0

        for j, nl in enumerate(new_listings):
            if j in used_new:
                continue
            nt = nl.get("title", "").lower().replace("...", "").strip()
            if not nt:
                continue

            # Simple overlap score
            bw = set(bt.split())
            nw = set(nt.split())
            if not bw or not nw:
                continue
            overlap = len(bw & nw) / max(len(bw | nw), 1)
            if overlap > best_score and overlap > 0.3:
                best_score = overlap
                best_match = j

        if best_match is not None:
            used_new.add(best_match)
            matches.append((bl, new_listings[best_match]))
        else:
            matches.append((bl, None))

    return matches


def log_outcome(shop_name, listing_title, action, gap_type, layer,
                was_implemented, pre_views, post_views, pre_orders,
                post_orders, pre_favorites, post_favorites,
                outcome, date_recommended, date_measured):
    """Append one outcome record to outcomes.jsonl."""
    record = {
        "shop": shop_name,
        "listing": listing_title,
        "action": action,
        "gap_type": gap_type,
        "layer": layer,
        "was_implemented": was_implemented,
        "pre_views": pre_views,
        "post_views": post_views,
        "pre_orders": pre_orders,
        "post_orders": post_orders,
        "pre_favorites": pre_favorites,
        "post_favorites": post_favorites,
        "outcome": outcome,
        "date_recommended": date_recommended,
        "date_measured": date_measured,
    }
    with open(OUTCOME_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def generate_followup_report(shop_name, baseline, comparisons, today):
    """Generate an HTML comparison report."""
    base_date = baseline.get("diagnosis_date", "unknown")
    base_score = baseline.get("health_score", 0)
    days_elapsed = "14"
    try:
        from datetime import datetime
        d1 = datetime.fromisoformat(base_date)
        d2 = datetime.fromisoformat(today)
        days_elapsed = str((d2 - d1).days)
    except Exception:
        pass

    rows = ""
    for comp in comparisons:
        bl = comp["baseline"]
        nl = comp["new"]
        title = report_mod.escape(report_mod.shorten(bl.get("title", ""), 35))
        changes = comp["changes"]
        outcome = comp["outcome"]

        bv = bl.get("views_at_diagnosis", 0)
        nv = nl.get("views", 0) if nl else 0
        bo = bl.get("orders_at_diagnosis", 0)
        no = nl.get("orders", 0) if nl else 0
        bf = bl.get("favorites_at_diagnosis", 0)
        nf = nl.get("favorites", 0) if nl else 0

        def delta(old, new):
            d = new - old
            if d > 0: return f'<span style="color:#1B7A3D">+{d}</span>'
            if d < 0: return f'<span style="color:#991B1B">{d}</span>'
            return '<span style="color:#9CA3AF">0</span>'

        action = bl.get("top_action", "—")
        if action and len(action) > 80:
            action = action[:80] + "..."

        change_str = ", ".join(changes) if changes else "No changes detected"
        impl = "yes" if changes else "no"
        outcome_cls = {"helped": "color:#1B7A3D", "no_clear_evidence": "color:#9CA3AF",
                       "inconclusive": "color:#92400E", "no_data": "color:#9CA3AF"}.get(outcome, "")
        outcome_label = outcome.replace("_", " ")

        rows += f"""
    <div class="comp">
      <p class="comp-title">{title}</p>
      <p class="comp-action">{report_mod.escape(action or "—")}</p>
      <p class="comp-changes">Changes: {report_mod.escape(change_str)}</p>
      <div class="comp-metrics">
        <div>Views: {bv} -> {nv} {delta(bv, nv)}</div>
        <div>Orders: {bo} -> {no} {delta(bo, no)}</div>
        <div>Favorites: {bf} -> {nf} {delta(bf, nf)}</div>
      </div>
      <p class="comp-outcome" style="{outcome_cls}">Outcome: {outcome_label}</p>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report_mod.escape(shop_name)} — Follow-up</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
  :root {{ --bg: #FAFAF8; --fg: #1A1A1A; --accent: #D35400; --muted: #6B7280; --light: #9CA3AF; --rule: #E0DDD8; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--fg); -webkit-font-smoothing: antialiased; }}
  .page {{ max-width: 580px; margin: 0 auto; padding: 64px 24px 96px; }}
  .mast {{ display: flex; justify-content: space-between; margin-bottom: 48px; font-size: .75rem; color: var(--light); }}
  .mast-logo {{ font-family: 'DM Serif Display', serif; font-size: .9rem; }}
  .mast-logo span {{ color: var(--accent); }}
  h1 {{ font-family: 'DM Serif Display', serif; font-size: 1.6rem; font-weight: 400; margin-bottom: 8px; }}
  .sub {{ font-size: .88rem; color: var(--muted); margin-bottom: 32px; }}
  .label {{ font-size: .65rem; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: var(--accent); margin-bottom: 16px; }}
  .comp {{ padding: 20px 0; border-bottom: 1px solid var(--rule); }}
  .comp:last-child {{ border-bottom: none; }}
  .comp-title {{ font-weight: 600; font-size: .88rem; margin-bottom: 6px; }}
  .comp-action {{ font-size: .82rem; color: var(--muted); margin-bottom: 6px; }}
  .comp-changes {{ font-size: .82rem; margin-bottom: 8px; }}
  .comp-metrics {{ display: flex; gap: 20px; font-size: .85rem; font-variant-numeric: tabular-nums; margin-bottom: 6px; }}
  .comp-outcome {{ font-size: .82rem; font-weight: 600; }}
  .summary {{ margin: 32px 0; padding: 20px; border-top: 2px solid var(--fg); }}
  .summary p {{ font-size: .88rem; margin-bottom: 4px; }}
  .foot {{ margin-top: 40px; font-size: .7rem; color: var(--light); }}
  .foot a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="page">
  <div class="mast">
    <div class="mast-logo">Shop<span>Pulse</span></div>
    <div>{report_mod.escape(today)}</div>
  </div>

  <h1>{report_mod.escape(shop_name)} — Follow-up</h1>
  <p class="sub">Comparing against baseline from {report_mod.escape(base_date)} ({days_elapsed} days ago). Health score at baseline: {base_score}/100.</p>

  <div class="label">Per-listing comparison</div>
  {rows}

  <div class="summary">
    <p><strong>{sum(1 for c in comparisons if c['changes'])}</strong> of {len(comparisons)} listings showed changes</p>
    <p><strong>{sum(1 for c in comparisons if c['outcome'] == 'helped')}</strong> helped, <strong>{sum(1 for c in comparisons if c['outcome'] == 'inconclusive')}</strong> inconclusive, <strong>{sum(1 for c in comparisons if c['outcome'] == 'no_clear_evidence')}</strong> no clear evidence</p>
  </div>

  <div class="foot"><a href="#">ShopPulse</a> — we tell you what to fix, not what to sell.</div>
</div>
</body>
</html>"""
    return html


def run_followup(source_path, baseline_path, output_dir=None):
    """Run follow-up comparison against a baseline."""
    if output_dir is None:
        output_dir = PROJECT_DIR

    with open(baseline_path) as f:
        baseline = json.load(f)

    shop_name = baseline["shop_name"]
    safe_name = "".join(c if c.isalnum() else "_" for c in shop_name).lower()
    today = date.today().isoformat()

    # Extract new data
    print(f"Extracting new data from {source_path}...", file=sys.stderr)
    new_data = diagnose.extract_from_source(source_path)
    new_listings = new_data.get("listings", [])
    print(f"  Found {len(new_listings)} listings", file=sys.stderr)

    # Match and compare
    print(f"Comparing against baseline from {baseline['diagnosis_date']}...", file=sys.stderr)
    base_listings = baseline.get("listings", [])
    matches = match_listings(base_listings, new_listings)

    comparisons = []
    outcomes_logged = 0

    for bl, nl in matches:
        changes = detect_changes(bl, nl) if nl else []
        bv = bl.get("views_at_diagnosis", 0)
        nv = nl.get("views", 0) if nl else 0
        bo = bl.get("orders_at_diagnosis", 0)
        no = nl.get("orders", 0) if nl else 0
        bf = bl.get("favorites_at_diagnosis", 0)
        nf = nl.get("favorites", 0) if nl else 0

        outcome = classify_outcome(bv, nv, bo, no)

        comparisons.append({
            "baseline": bl,
            "new": nl or {},
            "changes": changes,
            "outcome": outcome,
        })

        # Log outcome for each action that was recommended
        if bl.get("top_action"):
            log_outcome(
                shop_name=shop_name,
                listing_title=bl.get("title", ""),
                action=bl.get("top_action", ""),
                gap_type=bl.get("gaps_flagged", ["unknown"])[0] if bl.get("gaps_flagged") else "unknown",
                layer=bl.get("action_layer", 1),
                was_implemented=len(changes) > 0,
                pre_views=bv, post_views=nv,
                pre_orders=bo, post_orders=no,
                pre_favorites=bf, post_favorites=nf,
                outcome=outcome,
                date_recommended=baseline.get("diagnosis_date", ""),
                date_measured=today,
            )
            outcomes_logged += 1

    print(f"  {sum(1 for c in comparisons if c['changes'])} listings changed", file=sys.stderr)
    print(f"  Logged {outcomes_logged} outcomes to {OUTCOME_FILE}", file=sys.stderr)

    # Generate comparison report
    html = generate_followup_report(shop_name, baseline, comparisons, today)
    report_path = os.path.join(output_dir, f"{safe_name}_followup_{today}.html")
    with open(report_path, "w") as f:
        f.write(html)
    print(f"  Report: {report_path}", file=sys.stderr)

    return report_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    source = None
    baseline_path = None
    no_open = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--baseline" and i + 1 < len(args):
            baseline_path = os.path.expanduser(args[i + 1])
            i += 2
        elif args[i] == "--no-open":
            no_open = True
            i += 1
        else:
            source = os.path.expanduser(args[i])
            i += 1

    if not source or not baseline_path:
        print("Error: provide a source and --baseline path", file=sys.stderr)
        print("Usage: python3 followup.py new_data.png --baseline baseline_shop_2026-03-28.json", file=sys.stderr)
        sys.exit(1)

    report_path = run_followup(source, baseline_path)

    if not no_open:
        import subprocess
        if sys.platform == "darwin":
            subprocess.run(["open", report_path])
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", report_path])
