"""
ShopPulse HTML Report Generator v0.7
"""

import sys
import os
import json
from datetime import date


def escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def fmt(p):
    return f"${p:,.2f}" if p else ""

def shorten(title, n=45):
    if len(title) <= n: return title
    return title[:n].rsplit(" ", 1)[0] + "..."

def health_word(s):
    if s >= 75: return "strong"
    if s >= 50: return "needs work"
    if s >= 25: return "struggling"
    return "critical"

def compute_health(gaps, count):
    if not gaps or count == 0: return 100
    t = sum(g.get("severity", 0) for g in gaps)
    return max(0, round(100 - (t / (count * 10)) * 100))


def generate_report(data, shop_name=None):
    h = data.get("shop_health", {})
    listings = data.get("listings", [])
    gaps = data.get("gaps", [])
    patterns = data.get("patterns", [])
    diag = data.get("shop_diagnosis", {})
    today = date.today().strftime("%b %d, %Y")

    if not shop_name:
        shop_name = h.get("name", "Your Shop")

    n = h.get("listing_count", len(listings))
    views = h.get("total_views", 0)
    orders = h.get("total_orders", 0)
    revenue = h.get("estimated_revenue")
    fees = h.get("total_fees_estimate")
    net = h.get("net_after_fees")
    conv = h.get("shop_conversion_rate")
    score = compute_health(gaps, n)
    hw = health_word(score)
    quick_fixes = sum(1 for g in gaps if g.get("difficulty") == "quick fix")

    problem = diag.get("primary_problem", "")
    story_map = {
        "visibility": "Buyers aren't finding your listings. More traffic is the priority before anything else matters.",
        "conversion": f"You're getting traffic ({views:,} views) but not enough turns into sales ({orders} orders). Something is stopping people from buying.",
        "both": "Some listings need more traffic, others need to convert better. We figured out which is which.",
        "healthy": "Your shop is performing well. What follows is fine-tuning, not damage control.",
    }
    story = story_map.get(problem, "")

    # Money
    money_html = ""
    if revenue and fees and net:
        fee_rate = h.get("avg_fee_rate", 0)
        money_html = f"""
  <div class="money">
    <div class="money-r"><span>Revenue</span><span>{fmt(revenue)}</span></div>
    <div class="money-r take"><span>Etsy fees ({fee_rate}%)</span><span>-{fmt(fees)}</span></div>
    <div class="money-r keep"><span>You keep</span><span>{fmt(net)}</span></div>
  </div>"""

    # Actions
    actions_html = ""
    for i, g in enumerate(gaps[:3], 1):
        ln = escape(shorten(g.get("listing", ""), 50))
        diff = g.get("difficulty", "")
        timeline = g.get("timeline", "")
        esc = {1: "If this doesn't help in 2-3 weeks, we look at pricing and trust next.",
               2: "If no change in 3-4 weeks, we check competitive positioning.",
               3: "Longer play. Give it 1-2 months."}.get(g.get("layer", 1), "")
        actions_html += f"""
      <div class="act">
        <div class="act-side"><span class="act-num">{i}</span></div>
        <div class="act-main">
          <p class="act-listing">{ln}{f'<span class="act-diff">{escape(diff)}</span>' if diff else ''}</p>
          <p class="act-do">{escape(g["action"])}</p>
          <p class="act-because">{escape(g["evidence"])}</p>
          {f'<p class="act-meta">{escape(timeline)}</p>' if timeline else ''}
          {f'<p class="act-meta i">{esc}</p>' if esc else ''}
        </div>
      </div>"""

    # Patterns (top 3)
    pat_html = ""
    if patterns:
        top_p = sorted(patterns, key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(p.get("confidence", "low"), 2))[:3]
        items = ""
        for p in top_p:
            items += f"""
      <div class="pat">
        <p class="pat-find">{escape(p["insight"])}</p>
        <p class="pat-so">{escape(p["action"])}</p>
      </div>"""
        pat_html = f"""
    <div class="block">
      <div class="block-label">Patterns in your shop</div>
      {items}
    </div>"""

    # Listings
    rows = ""
    for l in sorted(listings, key=lambda x: x.get("orders", 0), reverse=True):
        t = escape(shorten(l.get("title", ""), 32))
        p = l.get("price")
        o = l.get("orders", 0)
        m = l.get("metrics", {})
        ps = m.get("per_sale", {})
        profit = ps.get("net_profit")
        margin = ps.get("profit_margin")
        d = l.get("diagnosis", {})
        prob = d.get("primary_problem", "")
        pstr = fmt(profit) if profit is not None else "—"
        mstr = f'{margin}%' if margin is not None else ""
        tag = ""
        if prob == "visibility": tag = '<td class="tag tag-v">low traffic</td>'
        elif prob == "conversion": tag = '<td class="tag tag-c">low conversion</td>'
        else: tag = '<td></td>'
        rows += f'<tr><td class="l-title">{t}</td><td class="l-num">{fmt(p) if p else "—"}</td><td class="l-num">{o}</td><td class="l-num">{pstr}</td><td class="l-num l-dim">{mstr}</td>{tag}</tr>'

    # Fee detail (collapsed)
    fee_html = ""
    if h.get("avg_fee_per_sale") and h.get("avg_price"):
        ap = h["avg_price"]
        fr = h.get("avg_fee_rate", 0)
        osr = h.get("fee_rate_with_offsite_ads", 0)
        fee_html = f"""
    <details class="detail-block">
      <summary>Fee breakdown on a {fmt(ap)} sale</summary>
      <div class="detail-inner">
        <table class="fee-tbl">
          <tr><td>Listing fee</td><td>$0.20</td></tr>
          <tr><td>Auto-renew</td><td>$0.20</td></tr>
          <tr><td>Transaction (6.5%)</td><td>{fmt(round(ap * 0.065, 2))}</td></tr>
          <tr><td>Processing (~3% + $0.25)</td><td>{fmt(round(ap * 0.03 + 0.25, 2))}</td></tr>
          <tr class="fee-total"><td>Total per sale</td><td>{fmt(h["avg_fee_per_sale"])}</td></tr>
        </table>
        <p class="detail-note">That's {fr}% of the sale price. With Offsite Ads: {osr}%.</p>
      </div>
    </details>"""

    # More findings (collapsed)
    more_html = ""
    rest = gaps[3:]
    if rest:
        items = "".join(f'<li>{escape(g["action"][:90])} <span class="act-meta">— {escape(shorten(g.get("listing",""),25))}</span></li>' for g in rest[:8])
        extra = len(gaps) - 11
        more_html = f"""
    <details class="detail-block">
      <summary>{len(rest)} more finding{"s" if len(rest) != 1 else ""}</summary>
      <ol class="detail-list">{items}</ol>
      {"<p class='detail-note'>+ " + str(extra) + " more in the full data</p>" if extra > 0 else ""}
    </details>"""

    # Per-listing diagnosis
    diag_items = ""
    for ld in diag.get("per_listing", []):
        prob = ld["primary_problem"]
        label = {"visibility": "low traffic", "conversion": "low conversion", "both": "both", "healthy": "OK"}.get(prob, "")
        cls = f"tag-{'v' if prob == 'visibility' else 'c' if prob == 'conversion' else 'ok'}"
        diag_items += f'<span class="d-pill {cls}">{escape(shorten(ld["listing"], 20))}<small>{label}</small></span>'

    # Closing
    if score >= 70:
        closing = f"Your shop is in good shape. Start with action #1 — low risk, fast signal, measurable within two weeks."
    elif score >= 40:
        closing = f"{quick_fixes} of the fixes above are quick wins. One change, 14 days, then measure. That's the rhythm."
    else:
        closing = f"Don't fix everything at once. Action #1, 14 days. If it works, great. If not, that's data too."

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(shop_name)} — ShopPulse</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #FAFAF8; --fg: #1A1A1A; --accent: #D35400; --accent-light: #FDF2E9;
    --muted: #6B7280; --light: #C0C4CC; --rule: #E0DDD8;
    --green: #1B7A3D; --amber: #92400E; --red: #991B1B; --blue: #1D4ED8;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--fg); -webkit-font-smoothing: antialiased; }}

  .page {{ max-width: 580px; margin: 0 auto; padding: 64px 24px 96px; }}

  /* ── Masthead ── */
  .mast {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 48px; }}
  .mast-logo {{ font-family: 'DM Serif Display', serif; font-size: .9rem; color: var(--light); }}
  .mast-logo span {{ color: var(--accent); }}
  .mast-date {{ font-size: .75rem; color: var(--light); letter-spacing: .03em; }}

  /* ── Score + Name ── */
  .hero-grid {{ display: grid; grid-template-columns: auto 1fr; gap: 24px; align-items: end; margin-bottom: 20px; }}
  .hero-score {{ font-family: 'DM Serif Display', serif; font-size: 5.5rem; font-weight: 400; line-height: .85; letter-spacing: -.04em; }}
  .c-strong {{ color: var(--green); }}
  .c-needs {{ color: var(--accent); }}
  .c-struggling {{ color: var(--amber); }}
  .c-critical {{ color: var(--red); }}
  .hero-right {{ padding-bottom: 6px; }}
  .hero-name {{ font-family: 'DM Serif Display', serif; font-size: 1.6rem; font-weight: 400; letter-spacing: -.02em; line-height: 1.15; }}
  .hero-hw {{ font-size: .78rem; color: var(--muted); margin-top: 2px; letter-spacing: .02em; }}

  .story {{ font-size: .92rem; line-height: 1.65; margin-bottom: 28px; color: var(--fg); }}

  /* ── Ticker ── */
  .ticker {{ display: flex; border-top: 2px solid var(--fg); border-bottom: 1px solid var(--rule); }}
  .tick {{ flex: 1; padding: 14px 0; text-align: center; border-right: 1px solid var(--rule); }}
  .tick:last-child {{ border-right: none; }}
  .tick-n {{ font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .tick-l {{ font-size: .65rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-top: 2px; }}

  /* ── Money ── */
  .money {{ margin: 28px 0; padding: 20px 0; border-bottom: 1px solid var(--rule); }}
  .money-r {{ display: flex; justify-content: space-between; font-size: .88rem; padding: 3px 0; font-variant-numeric: tabular-nums; }}
  .money-r.take {{ color: var(--amber); }}
  .money-r.keep {{ font-weight: 700; margin-top: 6px; padding-top: 8px; border-top: 2px solid var(--fg); }}

  /* ── Block sections ── */
  .block {{ margin: 40px 0; }}
  .block-label {{ font-size: .65rem; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: var(--accent); margin-bottom: 16px; }}

  .rule {{ border: none; border-top: 1px solid var(--rule); margin: 40px 0; }}

  /* ── Actions ── */
  .act {{ display: flex; gap: 0; margin-bottom: 0; }}
  .act-side {{ width: 48px; flex-shrink: 0; padding-top: 20px; text-align: center; border-right: 2px solid var(--rule); }}
  .act-num {{ font-family: 'DM Serif Display', serif; font-size: 1.4rem; color: var(--accent); }}
  .act-main {{ padding: 20px 0 20px 20px; border-bottom: 1px solid var(--rule); flex: 1; }}
  .act:last-child .act-main {{ border-bottom: none; }}
  .act-listing {{ font-size: .82rem; font-weight: 600; margin-bottom: 8px; }}
  .act-diff {{ font-size: .62rem; font-weight: 600; padding: 2px 5px; border-radius: 2px; margin-left: 6px; background: var(--accent-light); color: var(--accent); vertical-align: middle; text-transform: uppercase; letter-spacing: .04em; }}
  .act-do {{ font-size: .9rem; line-height: 1.55; margin-bottom: 8px; }}
  .act-because {{ font-size: .82rem; color: var(--muted); line-height: 1.5; }}
  .act-meta {{ font-size: .75rem; color: var(--light); margin-top: 6px; }}
  .act-meta.i {{ font-style: italic; }}

  /* ── Patterns ── */
  .pat {{ padding: 14px 0; border-bottom: 1px solid var(--rule); }}
  .pat:last-child {{ border-bottom: none; }}
  .pat-find {{ font-size: .88rem; font-weight: 600; margin-bottom: 4px; line-height: 1.4; }}
  .pat-so {{ font-size: .82rem; color: var(--muted); line-height: 1.5; }}

  /* ── Table ── */
  .ltbl {{ width: 100%; border-collapse: collapse; font-size: .78rem; margin-top: 8px; }}
  .ltbl th {{ text-align: left; font-size: .6rem; text-transform: uppercase; letter-spacing: .08em; color: var(--light); padding: 6px 6px; border-bottom: 2px solid var(--fg); font-weight: 500; }}
  .ltbl td {{ padding: 7px 6px; border-bottom: 1px solid var(--rule); font-variant-numeric: tabular-nums; }}
  .l-title {{ font-weight: 500; max-width: 160px; }}
  .l-num {{ text-align: right; }}
  .l-dim {{ color: var(--light); font-size: .72rem; }}
  .tag {{ font-size: .6rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; text-align: right; }}
  .tag-v {{ color: var(--blue); }}
  .tag-c {{ color: var(--accent); }}

  /* ── Diagnosis pills ── */
  .d-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }}
  .d-pill {{ font-size: .7rem; padding: 4px 8px; border-radius: 3px; background: #fff; border: 1px solid var(--rule); }}
  .d-pill small {{ display: block; font-size: .58rem; color: var(--muted); margin-top: 1px; }}
  .d-pill.tag-v {{ border-color: #BFDBFE; background: #F0F7FF; }}
  .d-pill.tag-c {{ border-color: #FBBF6E; background: #FFF8F0; }}
  .d-pill.tag-ok {{ border-color: #C6F0D6; background: #F0FFF5; }}

  /* ── Details/collapsed ── */
  .detail-block {{ margin: 20px 0; }}
  .detail-block summary {{ font-size: .82rem; color: var(--muted); cursor: pointer; padding: 6px 0; }}
  .detail-block summary:hover {{ color: var(--fg); }}
  .detail-inner {{ padding: 12px 0; }}
  .fee-tbl {{ border-collapse: collapse; font-size: .82rem; width: 100%; }}
  .fee-tbl td {{ padding: 3px 0; }}
  .fee-tbl td:last-child {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .fee-total td {{ border-top: 2px solid var(--fg); padding-top: 6px; margin-top: 4px; font-weight: 700; }}
  .detail-note {{ font-size: .75rem; color: var(--light); margin-top: 8px; }}
  .detail-list {{ padding-left: 18px; margin: 8px 0; }}
  .detail-list li {{ font-size: .82rem; margin-bottom: 5px; line-height: 1.4; }}

  /* ── Method ── */
  .method-text {{ font-size: .82rem; color: var(--muted); line-height: 1.6; }}
  .method-text strong {{ color: var(--fg); }}

  /* ── Closing + CTA ── */
  .closing {{ font-size: .92rem; line-height: 1.65; margin: 32px 0; }}
  .cta {{ border-top: 2px solid var(--fg); padding: 28px 0; margin-top: 40px; }}
  .cta-inner {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .cta-text {{ font-family: 'DM Serif Display', serif; font-size: 1.1rem; }}
  .cta-sub {{ font-size: .78rem; color: var(--muted); margin-top: 4px; }}
  .cta-link {{ font-size: .82rem; font-weight: 600; color: var(--accent); text-decoration: none; white-space: nowrap; }}

  .foot {{ margin-top: 40px; font-size: .7rem; color: var(--light); }}
  .foot a {{ color: var(--accent); text-decoration: none; }}

  @media (max-width: 480px) {{
    .hero-grid {{ grid-template-columns: 1fr; gap: 8px; }}
    .hero-score {{ font-size: 4rem; }}
    .ticker {{ flex-wrap: wrap; }}
    .tick {{ min-width: 33%; }}
    .cta-inner {{ flex-direction: column; gap: 8px; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="mast">
    <div class="mast-logo">Shop<span>Pulse</span></div>
    <div class="mast-date">{today}</div>
  </div>

  <div class="hero-grid">
    <div class="hero-score c-{hw.split()[0]}">{score}</div>
    <div class="hero-right">
      <div class="hero-name">{escape(shop_name)}</div>
      <div class="hero-hw">{hw}</div>
    </div>
  </div>

  <p class="story">{story}</p>

  <div class="ticker">
    {f'<div class="tick"><div class="tick-n">{n}</div><div class="tick-l">Listings</div></div>' if n else ''}
    {f'<div class="tick"><div class="tick-n">{views:,}</div><div class="tick-l">Views</div></div>' if views else ''}
    {f'<div class="tick"><div class="tick-n">{orders}</div><div class="tick-l">Orders</div></div>' if orders else ''}
    {f'<div class="tick"><div class="tick-n">{conv}%</div><div class="tick-l">Conversion</div></div>' if conv is not None else ''}
  </div>

  {money_html}

  <div class="block">
    <div class="block-label">This week</div>
    {actions_html}
  </div>

  {pat_html}

  {fee_html}

  <hr class="rule">

  <div class="block">
    <div class="block-label">Your listings</div>
    <div style="overflow-x:auto">
    <table class="ltbl">
      <thead><tr><th>Listing</th><th style="text-align:right">Price</th><th style="text-align:right">Orders</th><th style="text-align:right">Profit</th><th style="text-align:right">Margin</th><th></th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    {f'<div class="d-row">{diag_items}</div>' if diag_items else ''}
  </div>

  {more_html}

  <hr class="rule">

  <details class="detail-block">
    <summary>How we figured this out</summary>
    <p class="method-text"><strong>We checked six things</strong> on every listing: whether buyers can find it, whether they're buying, if the price is right, whether they trust you, if the content sells, and how tough the competition is. <strong>We ranked by impact</strong> — problems on your highest-traffic listings come first. <strong>We looked at your shop as a whole</strong> — patterns across your best vs worst sellers tell a story that per-listing tools miss. Where we're not confident, we say so.</p>
  </details>

  <p class="closing">{closing}</p>

  <div class="cta">
    <div class="cta-inner">
      <div>
        <div class="cta-text">Weekly plans for {escape(shop_name)}</div>
        <div class="cta-sub">Track changes. Measure results. Escalate when fixes don't work.</div>
      </div>
      <a href="#" class="cta-link">Join waitlist</a>
    </div>
  </div>

  <div class="foot">
    <a href="#">ShopPulse</a> — we tell you what to fix, not what to sell.
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
