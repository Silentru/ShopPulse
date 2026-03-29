"""
ShopPulse — One-command diagnosis pipeline.

Takes a shop screenshot (or folder of screenshots) and produces a complete
HTML report. This is the Phase 0 recruitment tool.

Usage:
    python3 diagnose.py screenshot.png --name "ShopName"
    python3 diagnose.py screenshot.png --name "ShopName" --niche custom_portraits
    python3 diagnose.py screenshots/ --name "ShopName"
    python3 diagnose.py data.json --name "ShopName"

Niche presets: default, custom_art, custom_portraits, jewelry, handmade_gifts, crystals

The pipeline:
    1. Extract data from screenshot(s) using OCR
    2. Run the gap scorer
    3. Generate an HTML report
    4. Open the report in your browser
"""

import sys
import os
import json
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import screenshot_extractor
import scorer
import report as report_mod


def extract_from_source(source_path):
    """Extract shop data from screenshots or load from JSON."""
    if source_path.endswith(".json"):
        with open(source_path) as f:
            return json.load(f)

    # Run screenshot extractor
    results = screenshot_extractor.process_path(source_path)

    # Convert extracted data to scorer format
    data = {"shop": {}, "listings": []}
    for item in results:
        t = item.get("type", "")

        if t == "shop_page":
            data["shop"].update(item.get("shop", {}))
            data["listings"].extend(item.get("listings", []))
            if item.get("categories"):
                data["categories"] = item["categories"]

        elif t == "shop_stats":
            m = item.get("metrics", {})
            if m.get("visits"): data["shop"]["visits"] = m["visits"]
            if m.get("views"): data["shop"]["views"] = m["views"]
            if m.get("orders"): data["shop"]["orders"] = m["orders"]
            if m.get("revenue"): data["shop"]["revenue"] = m["revenue"]
            if m.get("conversion_rate"): data["shop"]["conversion_rate"] = m["conversion_rate"]
            if item.get("date_range"): data["shop"]["date_range"] = item["date_range"]

        elif t == "listing_stats":
            data["listings"].extend(item.get("listings", []))

        elif t == "conversion_breakdown":
            m = item.get("metrics", {})
            for k in ["views", "visits", "favorites", "orders", "conversion_rate", "avg_order_value"]:
                if m.get(k) is not None:
                    data["shop"][k] = m[k]

        elif t == "search_visibility":
            m = item.get("metrics", {})
            for k in ["impressions", "clicks", "click_rate"]:
                if m.get(k) is not None:
                    data["shop"][k] = m[k]
            if item.get("terms"):
                data["search_terms"] = item["terms"]

    # Clean None values
    data["shop"] = {k: v for k, v in data["shop"].items() if v is not None}
    return data


def run_diagnosis(source_path, shop_name, niche_preset="default", output_dir=None):
    """Full pipeline: extract → score → report."""

    if output_dir is None:
        output_dir = PROJECT_DIR

    safe_name = "".join(c if c.isalnum() else "_" for c in shop_name).lower()

    # Step 1: Extract
    print(f"Extracting data from {source_path}...", file=sys.stderr)
    data = extract_from_source(source_path)

    # Apply shop name and niche preset
    data["shop"]["name"] = shop_name
    data["niche_preset"] = niche_preset

    # Save extracted data
    data_path = os.path.join(output_dir, f"{safe_name}_data.json")
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Extracted: {len(data.get('listings', []))} listings, shop data saved to {data_path}", file=sys.stderr)

    # Step 2: Score
    print(f"Running diagnosis...", file=sys.stderr)
    result = scorer.score_shop(data)

    result_path = os.path.join(output_dir, f"{safe_name}_result.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)

    gaps = result.get("gaps", [])
    health = result.get("shop_health", {})
    diag = result.get("shop_diagnosis", {})
    patterns = result.get("patterns", [])
    print(f"  Found {len(gaps)} gaps, {len(patterns)} patterns", file=sys.stderr)
    print(f"  Diagnosis: {diag.get('primary_problem', 'unknown').upper()}", file=sys.stderr)

    # Step 3: Generate report
    print(f"Generating report...", file=sys.stderr)
    html = report_mod.generate_report(result, shop_name)

    report_path = os.path.join(output_dir, f"{safe_name}_report.html")
    with open(report_path, "w") as f:
        f.write(html)
    print(f"  Report: {report_path}", file=sys.stderr)

    # Step 4: Save baseline snapshot for follow-up comparison
    from datetime import date
    today = date.today().isoformat()
    health_score = report_mod.compute_health(gaps, health.get("listing_count", len(data.get("listings", []))), result.get("shop_maturity"))

    baseline = {
        "shop_name": shop_name,
        "diagnosis_date": today,
        "niche_preset": niche_preset,
        "health_score": health_score,
        "top_3_actions": [
            {
                "listing": g.get("listing", ""),
                "action": g.get("action", ""),
                "gap_type": g.get("gap_type", ""),
                "sub_type": g.get("sub_type", ""),
                "layer": g.get("layer", 1),
                "severity": g.get("severity", 0),
            }
            for g in gaps[:3]
        ],
        "listings": [
            {
                "title": l.get("title", ""),
                "price": l.get("price"),
                "views_at_diagnosis": l.get("views", 0),
                "orders_at_diagnosis": l.get("orders", 0),
                "favorites_at_diagnosis": l.get("favorites", 0),
                "review_count": l.get("review_count", data.get("shop", {}).get("review_count", 0)),
                "photo_count": l.get("photo_count"),
                "has_video": l.get("has_video"),
                "free_shipping": l.get("free_shipping"),
                "on_sale": l.get("on_sale"),
                "original_price": l.get("original_price"),
                "gaps_flagged": list(set(
                    g["gap_type"] for g in gaps if g.get("listing") == l.get("title", "")
                )),
                "top_action": next(
                    (g["action"] for g in gaps if g.get("listing") == l.get("title", "")),
                    None
                ),
                "action_layer": next(
                    (g.get("layer", 1) for g in gaps if g.get("listing") == l.get("title", "")),
                    None
                ),
            }
            for l in data.get("listings", [])
        ],
        "shop": {k: v for k, v in health.items() if k in [
            "total_views", "total_orders", "total_favorites", "listing_count",
            "shop_conversion_rate", "estimated_revenue", "net_after_fees",
            "review_count", "total_sales", "star_rating",
        ]},
    }

    baseline_path = os.path.join(output_dir, f"baseline_{safe_name}_{today}.json")
    with open(baseline_path, "w") as f:
        json.dump(baseline, f, indent=2)
    print(f"  Baseline: {baseline_path}", file=sys.stderr)

    # Summary
    print(f"\n{'=' * 50}", file=sys.stderr)
    print(f"  {shop_name}", file=sys.stderr)
    print(f"  Health: {health_score}/100", file=sys.stderr)
    print(f"  Listings: {health.get('listing_count', 0)}", file=sys.stderr)
    if health.get("estimated_revenue"):
        print(f"  Revenue: {report_mod.fmt(health['estimated_revenue'])}", file=sys.stderr)
    if health.get("net_after_fees"):
        print(f"  Net after fees: {report_mod.fmt(health['net_after_fees'])}", file=sys.stderr)
    print(f"  Top action: {gaps[0]['action'][:80]}..." if gaps else "  No gaps found", file=sys.stderr)
    print(f"{'=' * 50}\n", file=sys.stderr)

    return report_path, result_path, data_path, baseline_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    source = None
    name = None
    niche = "default"
    no_open = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif args[i] == "--niche" and i + 1 < len(args):
            niche = args[i + 1]
            i += 2
        elif args[i] == "--no-open":
            no_open = True
            i += 1
        else:
            source = os.path.expanduser(args[i])
            i += 1

    if not source:
        print("Error: provide a screenshot path or JSON file", file=sys.stderr)
        sys.exit(1)

    if not name:
        # Try to infer from filename
        base = os.path.splitext(os.path.basename(source))[0]
        name = base.replace("_", " ").replace("-", " ").title()
        print(f"No --name provided, using: {name}", file=sys.stderr)

    report_path, *_ = run_diagnosis(source, name, niche)

    if not no_open:
        if sys.platform == "darwin":
            subprocess.run(["open", report_path])
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", report_path])
        elif sys.platform == "win32":
            os.startfile(report_path)
