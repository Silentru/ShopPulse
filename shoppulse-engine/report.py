"""
ShopPulse HTML Report Generator v0.5
Turns diagnosis_result.json into a shareable single-file HTML report.

Usage:
    python3 report.py                              # uses diagnosis_result.json
    python3 report.py diagnosis_result.json        # specify input
    python3 report.py input.json -o report.html    # specify input and output
"""

import sys
import os
import json
from datetime import date


def escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fmt_price(p):
    return f"${p:,.2f}" if p else ""


def short_title(title, max_len=50):
    if len(title) <= max_len:
        return title
    return title[:max_len].rsplit(" ", 1)[0] + "..."


def compute_health_score(gaps, listing_count):
    if not gaps or listing_count == 0:
        return 100
    total_severity = sum(g.get("severity", 0) for g in gaps)
    max_possible = listing_count * 10
    return max(0, round(100 - (total_severity / max_possible) * 100))


GAP_LABELS = {
    "visibility": "Visibility", "conversion": "Conversion", "pricing": "Pricing",
    "trust": "Trust", "content": "Content", "competitiveness": "Competitiveness",
}
GAP_QUESTIONS = {
    "visibility": "Are buyers finding you?",
    "conversion": "Are browsers buying?",
    "pricing": "Is pricing competitive?",
    "trust": "Do buyers trust you?",
    "content": "Do listings sell themselves?",
    "competitiveness": "Can you compete?",
}
ESCALATION = {
    1: "If no improvement in 2-3 weeks, we escalate to conversion optimization.",
    2: "If no improvement in 3-4 weeks, we look at competitive positioning.",
    3: "If no movement in 1-2 months, we assess product-market fit.",
}
DIFF_LABELS = {"quick fix": "Quick fix", "moderate effort": "Moderate effort", "requires testing": "Requires testing", "strategic move": "Strategic"}


def generate_report(data, shop_name=None):
    health = data.get("shop_health", {})
    listings = data.get("listings", [])
    gaps = data.get("gaps", [])
    breakdown = data.get("gap_breakdown", {})
    search_terms = data.get("search_terms", [])
    niche = data.get("niche", {})
    patterns = data.get("patterns", [])
    shop_diag = data.get("shop_diagnosis", {})
    report_date = date.today().strftime("%B %d, %Y")

    if not shop_name:
        shop_name = health.get("name", "Your Shop")

    total_views = health.get("total_views", 0)
    total_orders = health.get("total_orders", 0)
    listing_count = health.get("listing_count", 0)
    conv_rate = health.get("shop_conversion_rate")
    conv_pos = health.get("conversion_position", "")
    est_revenue = health.get("estimated_revenue")
    niche_conv = niche.get("median_conversion_rate", 2.0)
    total_fees = health.get("total_fees_estimate")
    net_after = health.get("net_after_fees")
    fee_rate = health.get("avg_fee_rate", 0)

    score = compute_health_score(gaps, listing_count)
    diag_problem = shop_diag.get("primary_problem", "")
    quick_fixes = sum(1 for g in gaps if g.get("difficulty") == "quick fix")

    # --- Narrative ---
    parts = []
    if listing_count:
        parts.append(f"We analyzed {listing_count} listings against niche benchmarks.")
    if diag_problem == "visibility":
        parts.append("Your primary bottleneck is visibility — most listings aren't getting enough search traffic.")
    elif diag_problem == "conversion":
        parts.append(f"You're getting traffic but it's not converting. {total_views:,} views produced {total_orders} orders.")
    elif diag_problem == "both":
        parts.append("Some listings need more traffic, others need better conversion. We've prioritized each based on its bottleneck.")
    elif diag_problem == "healthy":
        parts.append("Your shop is performing well overall.")
    if quick_fixes:
        parts.append(f"We found {quick_fixes} quick fix{'es' if quick_fixes != 1 else ''} you can start today.")
    narrative = " ".join(parts)

    # --- Gap overview rows ---
    all_types = ["visibility", "conversion", "pricing", "trust", "content", "competitiveness"]
    gap_rows = ""
    for gt in all_types:
        info = breakdown.get(gt, {"count": 0, "max_severity": 0})
        c = info["count"]
        ms = info["max_severity"]
        label = GAP_LABELS.get(gt, gt)
        q = GAP_QUESTIONS.get(gt, "")
        sev_word = "Critical" if ms >= 7 else ("Moderate" if ms >= 4 else ("Low" if c > 0 else "Clear"))
        sev_cls = "sev-crit" if ms >= 7 else ("sev-mod" if ms >= 4 else ("sev-low" if c > 0 else "sev-clear"))
        gap_rows += f'<tr class="{sev_cls}"><td class="gap-name">{label}</td><td class="gap-q">{q}</td><td class="gap-c">{c}</td><td class="gap-sev">{sev_word}</td></tr>'

    # --- Highest-traffic callout ---
    callout = ""
    if listings:
        top = sorted(listings, key=lambda l: l.get("views", 0), reverse=True)[0]
        tv = top.get("views", 0)
        to = top.get("orders", 0)
        ts = round(top.get("traffic_share", 0) * 100)
        tt = escape(short_title(top.get("title", ""), 50))
        callout = f"""<p class="callout">Your highest-traffic listing is <strong>{tt}</strong> — {tv:,} views, {ts}% of your total traffic, {to} orders. Improvements here have the largest impact because even a small conversion gain on {tv:,} views means more orders than a big improvement on a low-traffic listing.</p>"""

    # --- Diagnosis ---
    diag_note = shop_diag.get("note", "")
    per_listing = shop_diag.get("per_listing", [])
    diag_items = ""
    for ld in per_listing:
        prob = ld["primary_problem"]
        t = escape(short_title(ld["listing"], 35))
        diag_items += f'<li><span class="dl-prob dl-{prob}">{prob}</span> {t}</li>'

    # --- Listings table ---
    l_rows = ""
    for l in sorted(listings, key=lambda x: x.get("orders", 0), reverse=True):
        t = escape(short_title(l.get("title", ""), 38))
        p = l.get("price")
        o = l.get("orders", 0)
        m = l.get("metrics", {})
        ps = m.get("per_sale", {})
        fees = ps.get("fees", {})
        pp = m.get("price_position", {}).get("position", "")
        tier = l.get("tier", "")

        fee_s = fmt_price(fees.get("total_fees")) if fees.get("total_fees") else "—"
        profit_s = "—"
        margin_s = ""
        if ps.get("net_profit") is not None:
            profit_s = fmt_price(ps["net_profit"])
            mg = ps.get("profit_margin")
            if mg is not None:
                margin_s = f' <span class="dim">({mg}%)</span>'
        total_s = fmt_price(m.get("total_net_profit")) if m.get("total_net_profit") is not None and o > 0 else "—"
        pp_s = f' <span class="dim tag-{pp}">{pp}</span>' if pp and pp != "competitive" else ""
        row_cls = ' class="row-under"' if tier == "underperforming" else ""

        l_rows += f"<tr{row_cls}><td>{t}</td><td>{fmt_price(p) if p else '—'}{pp_s}</td><td>{o}</td><td>{fee_s}</td><td>{profit_s}{margin_s}</td><td>{total_s}</td></tr>"

    # --- Fee breakdown ---
    fee_html = ""
    if health.get("avg_fee_per_sale") and health.get("avg_price"):
        ap = health["avg_price"]
        sample = health["avg_fee_per_sale"]
        offsite_rate = health.get("fee_rate_with_offsite_ads", 0)
        offsite_total = health.get("total_fees_with_offsite", 0)
        fee_html = f"""
  <div class="section-block">
    <div class="label">Your real margins</div>
    <p class="body-sm">On your average {fmt_price(ap)} sale, Etsy takes {fmt_price(sample)} in fees ({fee_rate}% effective rate). That's $0.20 listing + $0.20 auto-renew + {round(ap * 0.065, 2)} transaction + {round(ap * 0.03 + 0.25, 2)} processing.</p>
    <p class="body-sm">Across {total_orders} orders: <strong>{fmt_price(total_fees)}</strong> in fees on {fmt_price(est_revenue)} revenue. Net: <strong>{fmt_price(net_after)}</strong>.</p>
    <p class="body-sm muted">If Offsite Ads apply (mandatory over $10K/year): effective rate jumps to {offsite_rate}%, worst case {fmt_price(offsite_total)} total fees.</p>
  </div>"""

    # --- Search terms ---
    search_html = ""
    if search_terms:
        s_rows = ""
        for t in search_terms[:7]:
            term = t.get("term", "")
            if not term: continue
            imp = f"{t['impressions']:,}" if t.get("impressions") else "—"
            cl = f"{t['clicks']:,}" if t.get("clicks") else "—"
            po = str(t["position"]) if t.get("position") else "—"
            s_rows += f'<tr><td>"{escape(term)}"</td><td>{imp}</td><td>{cl}</td><td>{po}</td></tr>'
        if s_rows:
            search_html = f"""
  <div class="section-block">
    <div class="label">How buyers find you</div>
    <table class="tbl"><thead><tr><th>Search term</th><th>Impressions</th><th>Clicks</th><th>Pos.</th></tr></thead><tbody>{s_rows}</tbody></table>
  </div>"""

    # --- Actions ---
    actions_html = ""
    for i, g in enumerate(gaps[:3], 1):
        sev = g["severity"]
        listing_name = escape(short_title(g.get("listing", ""), 50))
        layer = g.get("layer", 1)
        diff = g.get("difficulty", "")
        diff_label = DIFF_LABELS.get(diff, diff)
        priority = g.get("priority_score", 0)
        pr = g.get("priority_reason", "")
        esc = ESCALATION.get(layer, "")
        timeline = g.get("timeline", "")
        measurement = g.get("measurement", "")

        why = f"Priority {priority}"
        if pr == "matches primary bottleneck":
            why += " — directly addresses your shop's main bottleneck"

        meta_parts = []
        if diff_label:
            meta_parts.append(diff_label)
        meta_parts.append(g.get("gap_type", "").upper())
        meta_parts.append(f"severity {sev}/10")
        meta_line = " · ".join(meta_parts)

        tm = ""
        if timeline:
            tm += f"<p class='body-sm muted'><strong>Timeline:</strong> {escape(timeline)}</p>"
        if measurement:
            tm += f"<p class='body-sm muted'><strong>Measurement:</strong> {escape(measurement)}</p>"

        actions_html += f"""
  <div class="action-block">
    <div class="action-head">
      <span class="action-n">{i}</span>
      <span class="action-meta">{meta_line}</span>
    </div>
    <p class="action-listing">{listing_name}</p>
    <p class="action-text">{escape(g['action'])}</p>
    <p class="body-sm muted">{escape(g['evidence'])}</p>
    <p class="body-sm dim">{why}</p>
    {tm}
    {'<p class="body-sm esc">' + esc + '</p>' if esc else ''}
  </div>"""

    # --- Cross-listing patterns ---
    patterns_html = ""
    if patterns:
        p_items = ""
        for p in patterns:
            conf = p.get("confidence", "")
            conf_note = f' <span class="dim">({conf} confidence)</span>' if conf else ""
            p_items += f"""
    <div class="pattern">
      <p class="pattern-insight">{escape(p['insight'])}</p>
      <p class="body-sm">{escape(p['action'])}{conf_note}</p>
    </div>"""
        patterns_html = f"""
  <div class="section-block">
    <div class="label">What your best listings have in common</div>
    <p class="body-sm muted" style="margin-bottom:16px">We compared your top performers against your bottom performers. These patterns are specific to your shop.</p>
    {p_items}
  </div>"""

    # --- More findings ---
    more_html = ""
    rest = gaps[3:]
    if rest:
        items = ""
        for g in rest[:8]:
            t = escape(short_title(g.get("listing", ""), 30))
            d = DIFF_LABELS.get(g.get("difficulty", ""), "")
            items += f'<li><span class="dim">{d} · {g.get("gap_type","").upper()}</span> {escape(g["action"][:100])} <span class="dim">— {t}</span></li>'
        extra = len(gaps) - 11
        extra_note = f"<p class='body-sm muted' style='margin-top:12px'>+ {extra} more in the full export</p>" if extra > 0 else ""
        more_html = f"""
  <div class="section-block">
    <div class="label">More findings</div>
    <ol class="findings-list">{items}</ol>
    {extra_note}
  </div>"""

    # --- Closing ---
    if score >= 70:
        closing = f"{escape(shop_name)} is in good shape. The recommendations above are incremental gains, not fundamental problems. Start with the quick fixes — they're low-risk and can move your numbers within two weeks."
    elif score >= 40:
        closing = f"There's real opportunity here. We found {len(gaps)} gaps across {escape(shop_name)}, but {quick_fixes} are quick fixes you can start today. Targeted changes, measured over 14-day windows. That's how this works."
    else:
        closing = f"{escape(shop_name)} has significant gaps to address. Don't try to fix everything at once. Start with action #1, give it 14 days. If it doesn't move, that tells us something too. Optimization is experimentation, not magic."

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShopPulse — {escape(shop_name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #FAFAF8; --fg: #1A1A1A; --accent: #D35400; --accent-light: #FDF2E9;
    --muted: #6B7280; --light: #9CA3AF; --border: #E5E5E3; --green: #1B7A3D; --amber: #92400E; --red: #991B1B;
  }}
  *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--fg); line-height: 1.65; -webkit-font-smoothing: antialiased; }}
  .page {{ max-width: 640px; margin: 0 auto; padding: 56px 24px 96px; }}

  /* Typography */
  h1 {{ font-family: 'DM Serif Display', serif; font-size: 2rem; font-weight: 400; letter-spacing: -0.03em; line-height: 1.15; margin-bottom: 4px; }}
  .label {{ font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: var(--accent); margin-bottom: .5rem; }}
  h2 {{ font-family: 'DM Serif Display', serif; font-size: 1.5rem; font-weight: 400; letter-spacing: -0.02em; margin-bottom: .3rem; }}
  .sub {{ font-size: .85rem; color: var(--muted); }}
  .body-sm {{ font-size: .85rem; line-height: 1.55; margin-bottom: 6px; }}
  .muted {{ color: var(--muted); }}
  .dim {{ color: var(--light); font-size: .8rem; }}
  strong {{ font-weight: 600; }}

  /* Logo */
  .logo {{ font-family: 'DM Serif Display', serif; font-size: 1rem; color: var(--light); margin-bottom: 40px; }}
  .logo span {{ color: var(--accent); }}

  /* Dividers */
  .divider {{ border: none; border-top: 1px solid var(--border); margin: 48px 0; }}

  /* Score */
  .score-row {{ display: flex; align-items: baseline; gap: 12px; margin: 24px 0 16px; }}
  .score {{ font-size: 3rem; font-weight: 700; line-height: 1; letter-spacing: -0.02em; }}
  .score-g {{ color: var(--green); }}
  .score-o {{ color: var(--accent); }}
  .score-r {{ color: var(--red); }}
  .score-label {{ font-size: .82rem; color: var(--light); }}
  .narrative {{ font-size: .95rem; margin-bottom: 20px; }}

  /* Stats */
  .stats {{ display: flex; gap: 32px; flex-wrap: wrap; margin: 20px 0; }}
  .stat-val {{ font-size: 1.4rem; font-weight: 700; line-height: 1.2; }}
  .stat-lbl {{ font-size: .75rem; color: var(--muted); }}

  /* Gap table */
  .tbl {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  .tbl th {{ text-align: left; font-size: .7rem; text-transform: uppercase; letter-spacing: .05em; color: var(--light); padding: 6px 0; border-bottom: 2px solid var(--border); font-weight: 500; }}
  .tbl td {{ padding: 8px 0; border-bottom: 1px solid var(--border); }}
  .tbl tr:last-child td {{ border-bottom: none; }}
  .gap-name {{ font-weight: 600; width: 110px; }}
  .gap-q {{ color: var(--muted); }}
  .gap-c {{ width: 40px; text-align: center; }}
  .gap-sev {{ width: 70px; text-align: right; font-size: .8rem; font-weight: 600; }}
  .sev-crit .gap-sev {{ color: var(--red); }}
  .sev-mod .gap-sev {{ color: var(--accent); }}
  .sev-low .gap-sev {{ color: var(--green); }}
  .sev-clear .gap-sev {{ color: var(--light); }}

  /* Callout */
  .callout {{ font-size: .9rem; color: var(--fg); padding: 16px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin: 24px 0; line-height: 1.6; }}

  /* Diagnosis list */
  .diag-list {{ list-style: none; display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 8px; }}
  .diag-list li {{ font-size: .82rem; }}
  .dl-prob {{ font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; margin-right: 4px; }}
  .dl-visibility {{ color: #1D4ED8; }}
  .dl-conversion {{ color: var(--accent); }}
  .dl-both {{ color: var(--amber); }}
  .dl-healthy {{ color: var(--green); }}

  /* Listings table */
  .row-under {{ background: #FFFBF5; }}
  .tag-overpriced {{ color: var(--amber); }}
  .tag-budget {{ color: var(--amber); }}
  .tag-premium {{ color: var(--green); }}

  /* Section blocks */
  .section-block {{ margin: 48px 0; }}

  /* Actions */
  .action-block {{ padding: 24px 0; border-bottom: 1px solid var(--border); }}
  .action-block:last-of-type {{ border-bottom: none; }}
  .action-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .action-n {{ font-size: .85rem; font-weight: 700; color: var(--accent); }}
  .action-meta {{ font-size: .72rem; color: var(--light); letter-spacing: .02em; }}
  .action-listing {{ font-size: .88rem; font-weight: 600; margin-bottom: 6px; }}
  .action-text {{ font-size: .95rem; font-weight: 500; line-height: 1.5; margin-bottom: 8px; }}
  .esc {{ font-style: italic; color: var(--light); margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); }}

  /* Findings list */
  .findings-list {{ padding-left: 20px; }}
  .findings-list li {{ font-size: .85rem; margin-bottom: 8px; line-height: 1.5; }}

  /* Patterns */
  .pattern {{ padding: 12px 0; border-bottom: 1px solid var(--border); }}
  .pattern:last-child {{ border-bottom: none; }}
  .pattern-insight {{ font-size: .92rem; font-weight: 600; margin-bottom: 4px; line-height: 1.45; }}

  /* Methodology */
  .method {{ counter-reset: step; margin: 16px 0; }}
  .method li {{ list-style: none; font-size: .88rem; margin-bottom: 12px; padding-left: 32px; position: relative; }}
  .method li::before {{ counter-increment: step; content: counter(step); position: absolute; left: 0; width: 22px; height: 22px; background: var(--fg); color: #fff; border-radius: 50%; font-size: .72rem; font-weight: 700; display: flex; align-items: center; justify-content: center; top: 1px; }}
  .method li strong {{ font-weight: 600; }}

  /* CTA */
  .cta {{ text-align: center; padding: 40px 24px; margin: 48px -24px; background: #232347; color: #fff; }}
  .cta h2 {{ color: #fff; margin-bottom: 8px; font-size: 1.3rem; }}
  .cta p {{ color: #a0a0c0; font-size: .88rem; max-width: 440px; margin: 0 auto; }}

  /* Footer */
  .foot {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border); font-size: .78rem; color: var(--light); }}
  .foot a {{ color: var(--accent); text-decoration: none; }}

  @media (max-width: 480px) {{
    .stats {{ gap: 20px; }}
    .tbl {{ font-size: .78rem; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="logo">Shop<span>Pulse</span></div>

  <h1>{escape(shop_name)}</h1>
  <p class="sub">{report_date}</p>

  <div class="score-row">
    <div class="score {"score-g" if score >= 70 else ("score-o" if score >= 40 else "score-r")}">{score}</div>
    <div class="score-label">shop health<br>out of 100</div>
  </div>

  <p class="narrative">{narrative}</p>

  <div class="stats">
    {'<div><div class="stat-val">' + f"{total_views:,}" + '</div><div class="stat-lbl">views</div></div>' if total_views else ''}
    {'<div><div class="stat-val">' + str(total_orders) + '</div><div class="stat-lbl">orders</div></div>' if total_orders else ''}
    {'<div><div class="stat-val">' + str(conv_rate) + '%</div><div class="stat-lbl">conversion ' + ("(above avg)" if conv_pos == "above average" else "(below avg)" if conv_pos == "below average" else "") + '</div></div>' if conv_rate is not None else ''}
    {'<div><div class="stat-val">' + fmt_price(est_revenue) + '</div><div class="stat-lbl">revenue</div></div>' if est_revenue else ''}
    {'<div><div class="stat-val">' + fmt_price(net_after) + '</div><div class="stat-lbl">net after fees</div></div>' if net_after else ''}
  </div>

  <hr class="divider">

  <div class="label">Gap overview</div>
  <table class="tbl">
    <thead><tr><th>Area</th><th>Question</th><th>Issues</th><th>Severity</th></tr></thead>
    <tbody>{gap_rows}</tbody>
  </table>

  {callout}

  {'<div class="section-block"><div class="label">Diagnosis</div><p class="body-sm">' + escape(diag_note) + '</p><ul class="diag-list">' + diag_items + '</ul></div>' if diag_note else ''}

  {patterns_html}

  <hr class="divider">

  <div class="label">Your listings</div>
  <div style="overflow-x:auto">
  <table class="tbl">
    <thead><tr><th>Listing</th><th>Price</th><th>Orders</th><th>Fees/sale</th><th>Profit/sale</th><th>Total profit</th></tr></thead>
    <tbody>{l_rows}</tbody>
  </table>
  </div>

  {fee_html}

  {search_html}

  <hr class="divider">

  <div class="label">What to fix this week</div>
  <p class="body-sm muted" style="margin-bottom:16px">3 actions, ranked by impact. Start with #1.</p>

  {actions_html}

  <p class="body-sm muted" style="text-align:center;padding:20px 0">Want a deeper analysis with your actual traffic data? Share your Etsy Stats screenshots and we'll run {escape(shop_name)} through the full diagnostic.</p>

  {more_html}

  <hr class="divider">

  <div class="label">How this works</div>
  <ol class="method">
    <li><strong>Detect gaps.</strong> We check every listing against six dimensions using niche-specific benchmarks.</li>
    <li><strong>Rank by impact.</strong> Gaps are scored by severity and weighted by traffic share. High-severity gaps on high-traffic listings come first.</li>
    <li><strong>Track outcomes.</strong> After you make changes, we measure before/after. If a fix didn't work, we escalate instead of repeating the same advice.</li>
  </ol>
  <p class="body-sm dim">Where confidence is low, we say so. We'd rather be honest about uncertainty than pretend we know something we don't.</p>

  <hr class="divider">

  <p class="narrative">{closing}</p>

  <div class="cta">
    <h2>Get weekly plans for {escape(shop_name)}</h2>
    <p>This is a one-time diagnosis. ShopPulse can track your changes, measure what worked, and escalate when fixes don't move the needle.</p>
  </div>

  <div class="foot">
    <p><a href="#">ShopPulse</a> — we tell you what to fix, not what to sell.</p>
    <p style="margin-top:6px">Niche benchmarks are estimates. Revenue and fees calculated from data you provided. Outcome labels: helped / no clear evidence / inconclusive / hurt.</p>
  </div>

</div>
</body>
</html>"""

    return html


if __name__ == "__main__":
    input_file = "diagnosis_result.json"
    output_file = "report.html"
    shop_name = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "-o" and i + 1 < len(args):
            output_file = args[i + 1]
            i += 2
        elif args[i] == "--name" and i + 1 < len(args):
            shop_name = args[i + 1]
            i += 2
        else:
            input_file = os.path.expanduser(args[i])
            i += 1

    with open(input_file) as f:
        data = json.load(f)

    html = generate_report(data, shop_name)

    with open(output_file, "w") as f:
        f.write(html)

    print(f"Report written to: {output_file}", file=sys.stderr)
