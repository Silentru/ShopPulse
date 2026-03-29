"""
ShopPulse Gap Scoring Engine v0.2
Deterministic scorer — no AI. Takes shop/listing data and produces structured
gap flags with severity scores ranked by priority.

Usage:
    python3 scorer.py                          # run with built-in example data
    python3 scorer.py shop_data.json           # run with extracted data file
    python3 scorer.py -o diagnosis_result.json # specify output file

Input: JSON with shop_stats, listings, and optionally search_visibility and niche_context
Output: diagnosis_result.json with scored gaps and prioritized recommendations
"""

import sys
import os
import json
from collections import defaultdict


# ---------------------------------------------------------------------------
# Default niche benchmarks (crystals/healing stones on Etsy)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Niche presets — use niche_context in input to override any field
# ---------------------------------------------------------------------------
NICHE_PRESETS = {
    "default": {
        "median_price": 25.00,
        "median_views_per_listing": 400,
        "median_favorites_per_listing": 50,
        "median_orders_per_listing": 8,
        "median_conversion_rate": 2.0,
        "median_fav_to_order_ratio": 0.16,
        "median_review_count": 500,
        "top10_review_avg": 5000,
        "median_photo_count": 5,
        "has_video_pct": 0.30,
        "median_description_words": 150,
        "median_title_words": 10,
        "free_shipping_pct": 0.60,
        "niche_saturation": 0.5,
        "total_niche_listings": None,
    },
    "custom_art": {
        "median_price": 120.00,
        "median_views_per_listing": 120,
        "median_favorites_per_listing": 15,
        "median_orders_per_listing": 3,
        "median_conversion_rate": 2.5,
        "median_fav_to_order_ratio": 0.20,
        "median_review_count": 400,
        "top10_review_avg": 10000,
        "median_photo_count": 7,
        "has_video_pct": 0.20,
        "median_description_words": 200,
        "median_title_words": 12,
        "free_shipping_pct": 0.50,
        "niche_saturation": 0.65,
        "total_niche_listings": None,
    },
    "custom_portraits": {
        "median_price": 130.00,
        "median_views_per_listing": 150,
        "median_favorites_per_listing": 20,
        "median_orders_per_listing": 5,
        "median_conversion_rate": 2.5,
        "median_fav_to_order_ratio": 0.25,
        "median_review_count": 500,
        "top10_review_avg": 12000,
        "median_photo_count": 8,
        "has_video_pct": 0.25,
        "median_description_words": 220,
        "median_title_words": 11,
        "free_shipping_pct": 0.55,
        "niche_saturation": 0.70,
        "total_niche_listings": None,
    },
    "jewelry": {
        "median_price": 35.00,
        "median_views_per_listing": 300,
        "median_favorites_per_listing": 40,
        "median_orders_per_listing": 6,
        "median_conversion_rate": 2.0,
        "median_fav_to_order_ratio": 0.15,
        "median_review_count": 800,
        "top10_review_avg": 20000,
        "median_photo_count": 6,
        "has_video_pct": 0.35,
        "median_description_words": 160,
        "median_title_words": 12,
        "free_shipping_pct": 0.65,
        "niche_saturation": 0.80,
        "total_niche_listings": None,
    },
    "handmade_gifts": {
        "median_price": 30.00,
        "median_views_per_listing": 250,
        "median_favorites_per_listing": 35,
        "median_orders_per_listing": 5,
        "median_conversion_rate": 2.0,
        "median_fav_to_order_ratio": 0.14,
        "median_review_count": 600,
        "top10_review_avg": 15000,
        "median_photo_count": 6,
        "has_video_pct": 0.25,
        "median_description_words": 170,
        "median_title_words": 11,
        "free_shipping_pct": 0.55,
        "niche_saturation": 0.60,
        "total_niche_listings": None,
    },
    "crystals": {
        "median_price": 25.00,
        "median_views_per_listing": 400,
        "median_favorites_per_listing": 50,
        "median_orders_per_listing": 8,
        "median_conversion_rate": 2.0,
        "median_fav_to_order_ratio": 0.16,
        "median_review_count": 500,
        "top10_review_avg": 5000,
        "median_photo_count": 5,
        "has_video_pct": 0.30,
        "median_description_words": 150,
        "median_title_words": 10,
        "free_shipping_pct": 0.60,
        "niche_saturation": 0.50,
        "total_niche_listings": None,
    },
}

DEFAULT_NICHE = NICHE_PRESETS["default"]


def clamp(value, lo=0, hi=10):
    return max(lo, min(hi, value))


def fmt_price(p):
    return f"${p:,.2f}"


def short_title(title, max_len=45):
    """Shorten a listing title for display."""
    if len(title) <= max_len:
        return title
    return title[:max_len].rsplit(" ", 1)[0] + "..."


# ---------------------------------------------------------------------------
# Etsy fee calculator
# ---------------------------------------------------------------------------

def calculate_etsy_fees(sale_price, shipping_charged=0, offsite_ads_triggered=False):
    """Calculate all Etsy fees for a single sale.

    Fee structure (current as of March 2026):
    - $0.20 listing fee (charged at listing and each renewal/sale)
    - 6.5% transaction fee on (sale_price + shipping_charged)
    - ~3% + $0.25 payment processing fee
    - 15% Offsite Ads fee (mandatory for sellers >$10K/year revenue)
    - $0.20 auto-renew fee when item sells
    """
    listing_fee = 0.20
    auto_renew_fee = 0.20
    transaction_fee = round((sale_price + shipping_charged) * 0.065, 2)
    processing_fee = round((sale_price + shipping_charged) * 0.03 + 0.25, 2)
    offsite_ads_fee = round(sale_price * 0.15, 2) if offsite_ads_triggered else 0

    total = round(listing_fee + auto_renew_fee + transaction_fee +
                  processing_fee + offsite_ads_fee, 2)
    effective_rate = round(total / sale_price * 100, 1) if sale_price > 0 else 0

    return {
        "listing_fee": listing_fee,
        "auto_renew_fee": auto_renew_fee,
        "transaction_fee": transaction_fee,
        "processing_fee": processing_fee,
        "offsite_ads_fee": offsite_ads_fee,
        "total_fees": total,
        "effective_fee_rate": effective_rate,
    }


def calculate_listing_profit(sale_price, shipping_charged=0,
                             materials_cost=None, packaging_cost=None,
                             shipping_actual=None, labor_hours=None,
                             labor_rate=0, etsy_ads_cost=0,
                             offsite_ads_triggered=False):
    """Calculate net profit for a single listing sale.

    Returns a dict with full fee breakdown, costs, and profit metrics.
    Seller costs default to None (unknown). Pass 0 explicitly to indicate
    "I have no costs" vs not providing the data at all.
    """
    fees = calculate_etsy_fees(sale_price, shipping_charged, offsite_ads_triggered)
    fees["etsy_ads_cost"] = round(etsy_ads_cost, 2)
    fees["total_fees"] = round(fees["total_fees"] + etsy_ads_cost, 2)

    gross_revenue = round(sale_price + shipping_charged, 2)
    mat = materials_cost if materials_cost is not None else 0
    pkg = packaging_cost if packaging_cost is not None else 0
    shp = shipping_actual if shipping_actual is not None else 0
    lab = labor_hours if labor_hours is not None else 0
    total_costs = round(mat + pkg + shp + lab * labor_rate, 2)
    # Costs are "known" if ANY cost field was explicitly provided (even as 0)
    costs_known = any(v is not None for v in [materials_cost, packaging_cost, shipping_actual, labor_hours])

    net_after_fees = round(gross_revenue - fees["total_fees"], 2)
    net_profit = round(net_after_fees - total_costs, 2) if costs_known else None
    profit_margin = round(net_profit / gross_revenue * 100, 1) if (
        net_profit is not None and gross_revenue > 0) else None

    return {
        "gross_revenue": gross_revenue,
        "fees": fees,
        "seller_costs": {
            "materials": round(mat, 2),
            "packaging": round(pkg, 2),
            "shipping_actual": round(shp, 2),
            "labor": round(lab * labor_rate, 2),
            "total_costs": total_costs,
            "costs_known": costs_known,
        },
        "net_after_fees": net_after_fees,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
    }


def price_position(price, niche_median, niche_25th=None, niche_75th=None,
                   review_count=None):
    """Determine where a listing's price sits in the niche.

    Returns: budget / competitive / premium / overpriced
    Plus a recommended price range based on the seller's review count.
    """
    if niche_median <= 0:
        return {"position": "unknown", "recommended_range": None}

    # Default percentiles if not provided
    if niche_25th is None:
        niche_25th = round(niche_median * 0.65, 2)
    if niche_75th is None:
        niche_75th = round(niche_median * 1.45, 2)

    deviation = (price - niche_median) / niche_median
    reviews = review_count or 0

    if deviation < -0.25:
        position = "budget"
    elif deviation < 0.10:
        position = "competitive"
    elif deviation < 0.35 and reviews > 20:
        position = "premium"
    elif deviation >= 0.35:
        position = "overpriced"
    else:
        position = "competitive"

    # Recommended range based on trust level (review count)
    if reviews < 10:
        rec_range = (niche_25th, niche_median)
    elif reviews < 50:
        rec_range = (round(niche_median * 0.9, 2), niche_75th)
    else:
        rec_range = (niche_median, round(niche_75th * 1.1, 2))

    return {
        "position": position,
        "deviation_pct": round(deviation * 100, 1),
        "recommended_range": rec_range,
        "niche_25th": niche_25th,
        "niche_median": niche_median,
        "niche_75th": niche_75th,
    }


# ---------------------------------------------------------------------------
# Per-listing computed metrics
# ---------------------------------------------------------------------------

def compute_listing_metrics(listing, niche, shop=None):
    """Compute derived metrics for a single listing including profit analytics."""
    views = listing.get("views", 0)
    orders = listing.get("orders", 0)
    favorites = listing.get("favorites", 0)
    price = listing.get("price")
    shipping_charged = listing.get("shipping_charged", 0)

    m = {}
    m["conversion_rate"] = round((orders / views) * 100, 2) if views > 0 else None
    m["fav_to_order_ratio"] = round(orders / favorites, 3) if favorites > 0 else None
    m["revenue_estimate"] = round(orders * price, 2) if price and orders else None

    # Percentile estimates vs niche
    niche_views = niche.get("median_views_per_listing", 400)
    niche_orders = niche.get("median_orders_per_listing", 8)
    niche_price = niche.get("median_price", 25)

    m["views_vs_niche"] = round(views / niche_views, 2) if niche_views > 0 else None
    m["orders_vs_niche"] = round(orders / niche_orders, 2) if niche_orders > 0 else None
    m["price_vs_niche"] = round(price / niche_price, 2) if price and niche_price > 0 else None

    # --- Profit analytics ---
    if price:
        # Fee calculation per sale
        offsite_ads = listing.get("offsite_ads_triggered", False)
        per_sale = calculate_listing_profit(
            sale_price=price,
            shipping_charged=shipping_charged,
            materials_cost=listing.get("materials_cost"),
            packaging_cost=listing.get("packaging_cost"),
            shipping_actual=listing.get("shipping_actual"),
            labor_hours=listing.get("labor_hours"),
            labor_rate=listing.get("labor_rate", 0),
            etsy_ads_cost=listing.get("etsy_ads_cost_per_sale", 0),
            offsite_ads_triggered=offsite_ads,
        )
        m["per_sale"] = per_sale

        # Scale to total orders
        if orders > 0:
            m["total_fees"] = round(per_sale["fees"]["total_fees"] * orders, 2)
            m["total_revenue"] = round(per_sale["gross_revenue"] * orders, 2)
            m["total_net_after_fees"] = round(per_sale["net_after_fees"] * orders, 2)
            if per_sale["net_profit"] is not None:
                m["total_net_profit"] = round(per_sale["net_profit"] * orders, 2)
            else:
                m["total_net_profit"] = None
            m["fee_rate"] = per_sale["fees"]["effective_fee_rate"]

    # --- Competitive pricing position ---
    if price:
        review_count = (shop or {}).get("review_count")
        niche_25 = niche.get("niche_25th_percentile")
        niche_75 = niche.get("niche_75th_percentile")
        m["price_position"] = price_position(
            price, niche_price, niche_25, niche_75, review_count
        )

    return m


# ---------------------------------------------------------------------------
# Gap scorers — personalized, specific recommendations
# ---------------------------------------------------------------------------

FILLER_TITLE_WORDS = [
    "beautiful", "handmade", "custom", "unique", "vintage", "lovely",
    "gorgeous", "stunning", "elegant", "cute", "pretty", "perfect",
    "amazing", "wonderful", "special", "personalized", "personalised",
]


def suggest_title_restructure(title):
    """Generate a restructured title suggestion: product-type-first, under 15 words.

    Tries to identify the product type and move it to the front.
    Returns (suggestion, explanation) or (None, None) if title looks OK.
    """
    # Don't restructure truncated titles from OCR (ending with "...")
    if title.endswith("...") or title.endswith(".."):
        return None, None

    words = title.split()
    if len(words) <= 3:
        return None, None

    filler_starts = FILLER_TITLE_WORDS

    # Check if title starts with filler/adjective words
    first_word = words[0].lower().rstrip(",")
    starts_with_filler = first_word in filler_starts

    if not starts_with_filler and len(words) <= 15:
        return None, None

    # Split into filler prefix and product core
    # "Beautiful Handmade Custom Dog Portrait Oil Painting from Photo Pet Memorial Gift"
    # -> filler: [Beautiful, Handmade, Custom]  core: [Dog, Portrait, Oil, Painting, ...]
    filler_prefix = []
    core_start = 0
    for i, w in enumerate(words):
        if w.lower().rstrip(",-") in filler_starts:
            filler_prefix.append(w)
            core_start = i + 1
        else:
            break

    if core_start == 0 and len(words) <= 15:
        return None, None  # No filler prefix and under 15 words — title is fine

    core_words = words[core_start:]
    if not core_words:
        return None, None

    # Build suggestion: core words first, keep it under 14 words, end on a complete word
    suggestion_words = core_words[:12]

    # Add one useful descriptor back if we have room (e.g., "Handmade" or "Custom")
    useful_fillers = [w for w in filler_prefix if w.lower() in ("handmade", "custom", "personalized", "vintage")]
    if useful_fillers and len(suggestion_words) < 13:
        suggestion_words.append(useful_fillers[0])

    suggestion = " ".join(suggestion_words)

    # Clean up: remove trailing punctuation/pipes
    suggestion = suggestion.rstrip(" |,;-")

    original_preview = " ".join(words[:6])
    if len(words) > 6:
        original_preview += "..."
    explanation = f'Restructure from "{original_preview}" to lead with the product type'

    return suggestion, explanation


def score_visibility(listing, shop, niche, metrics):
    """Layer 1. Additive severity from CLAUDE.md spec."""
    gaps = []
    views = listing.get("views", 0)
    title = listing.get("title", "")
    short = short_title(title)
    niche_avg = niche.get("median_views_per_listing", 400)
    tag_count = listing.get("tag_count")
    tags_matching = listing.get("tags_matching_autocomplete")

    severity = 0
    evidence_parts = []

    # Views checks
    if niche_avg > 0 and views < niche_avg * 0.3:
        severity += 3
        pct = round((1 - views / niche_avg) * 100)
        evidence_parts.append(f'{views} views — {pct}% below the niche average of {niche_avg}')
    elif niche_avg > 0 and views < niche_avg * 0.6:
        severity += 1
        evidence_parts.append(f'{views} views — below the niche average of {niche_avg}')

    # Tag checks
    if tag_count is not None and tag_count < 13:
        severity += 2
        evidence_parts.append(f'only {tag_count} of 13 tag slots used')

    if tags_matching is not None and tag_count and tags_matching < tag_count * 0.5:
        severity += 2
        evidence_parts.append(f'only {tags_matching} of {tag_count} tags match Etsy autocomplete')

    if severity > 0:
        severity = clamp(severity)
        evidence = f'"{short}": ' + '; '.join(evidence_parts) + '.'
        action_parts = []
        if tag_count is not None and tag_count < 13:
            action_parts.append(f'Fill all 13 tag slots — you\'re using {tag_count}')
        if tags_matching is not None and tag_count and tags_matching < tag_count * 0.5:
            action_parts.append('Replace low-performing tags with terms from Etsy autocomplete suggestions')
        if views < niche_avg * 0.6:
            action_parts.append('Check Etsy Search Analytics and replace any tags with zero impressions')
        action = '. '.join(action_parts) + '.' if action_parts else 'Review your tags and title for search relevance.'
        gaps.append({
            "gap_type": "visibility",
            "sub_type": "low_visibility",
            "severity": severity,
            "evidence": evidence,
            "action": action,
            "impact": "high" if severity >= 5 else "medium",
            "confidence": "high",
            "layer": 1,
            "difficulty": "quick fix",
            "timeline": "Tag and title changes reflect in Etsy search within 24 hours. Meaningful traffic signal in 7-14 days.",
            "measurement": "Compare listing views 14 days before vs 14 days after. Check Search Visibility to confirm impressions increased.",
        })

    # Title structure — product-type-first, under 15 words
    word_count = len(title.split()) if title else 0
    suggested, explanation = suggest_title_restructure(title)
    brand_name = listing.get("brand_name")
    has_title_issue = False
    title_evidence = []
    title_action_parts = []

    if word_count > 15:
        has_title_issue = True
        title_evidence.append(f'{word_count} words (Etsy recommends under 15)')

    if brand_name and title.lower().startswith(brand_name.lower()):
        has_title_issue = True
        title_evidence.append(f'starts with brand name "{brand_name}" — buyers search for product type, not brand')
        title_action_parts.append(f'Move "{brand_name}" to the end')

    # Check for filler-word starts even without brand name
    filler_starts = FILLER_TITLE_WORDS
    first_word = title.split()[0].lower().rstrip(",") if title else ""
    if first_word in filler_starts:
        has_title_issue = True
        title_evidence.append(f'starts with "{title.split()[0]}" — lead with the product type instead')

    if has_title_issue:
        sev = 0
        if word_count > 15:
            sev += 2
        if brand_name and title.lower().startswith(brand_name.lower()):
            sev += 2
        if first_word in filler_starts:
            sev += 1
        sev = clamp(sev) if sev > 0 else 2

        if suggested:
            title_action_parts.append(f'Suggested restructure: "{suggested}"')
        else:
            title_action_parts.append('Lead with the product type. Etsy\'s algorithm weighs the first few words most heavily')

        if word_count > 15:
            title_action_parts.append(f'Trim from {word_count} to under 15 words')

        gaps.append({
            "gap_type": "visibility",
            "sub_type": "title_structure",
            "severity": sev,
            "evidence": f'"{short}": ' + '; '.join(title_evidence) + '.',
            "action": '. '.join(title_action_parts) + '.',
            "impact": "medium",
            "confidence": "high",
            "layer": 1,
            "difficulty": "quick fix",
            "timeline": "Title changes reflect in search within 24 hours. Allow 7-14 days to measure impact on impressions and clicks.",
            "measurement": "Check Search Visibility page — did impressions for this listing increase? Compare click-through rate before vs after.",
        })

    return gaps


def score_conversion(listing, shop, niche, metrics):
    """Layer 2. Uses shop average for comparison per spec."""
    gaps = []
    views = listing.get("views", 0)
    orders = listing.get("orders", 0)
    favorites = listing.get("favorites", 0)
    price = listing.get("price")
    title = listing.get("title", "")
    short = short_title(title)

    # Skip if not enough data
    if views < 20:
        return gaps

    conv_rate = metrics.get("conversion_rate")
    shop_conv = shop.get("shop_conversion_rate") or niche.get("median_conversion_rate", 2.0)

    severity = 0
    evidence_parts = []

    # Conversion vs shop average
    if conv_rate is not None and views >= 50 and conv_rate < shop_conv * 0.5:
        severity += 3
        evidence_parts.append(f'{conv_rate}% conversion — less than half your shop average of {shop_conv}%')

    # Favorites with zero orders
    if favorites > 10 and orders == 0:
        severity += 3
        evidence_parts.append(f'{favorites} favorites but zero orders — people love it but won\'t buy')

    # Favorites way outpacing orders
    if orders > 0 and favorites > orders * 10:
        severity += 2
        evidence_parts.append(f'{favorites} favorites vs {orders} orders (ratio: {favorites // orders}:1)')

    if severity > 0:
        severity = clamp(severity)
        evidence = f'"{short}": ' + '; '.join(evidence_parts) + '.'

        # Build specific action
        suggestion = ""
        if price and price > niche.get("median_price", 25) * 1.3:
            test_price = round(price * 0.85, 2)
            suggestion = f' Your price ({fmt_price(price)}) is above the niche median — test {fmt_price(test_price)} for 2 weeks.'
        elif favorites > 10 and orders == 0:
            suggestion = ' With zero orders, something is blocking checkout — check price, shipping cost, and processing time.'

        extra_sales = max(1, round(views * 0.005))
        action = f'With {views} views, even a small conversion improvement means ~{extra_sales} more sales.{suggestion}'

        gaps.append({
            "gap_type": "conversion",
            "sub_type": "low_conversion",
            "severity": severity,
            "evidence": evidence,
            "action": action,
            "impact": "high" if severity >= 5 else "medium",
            "confidence": "high" if views > 200 else "medium",
            "layer": 2,
            "difficulty": "moderate effort",
            "timeline": "Conversion changes (pricing, photos, shipping) take 7-14 days to show a meaningful signal. Don't judge too early.",
            "measurement": "Compare orders-per-view ratio 14 days before vs 14 days after. Also track favorites-to-orders ratio — if that improves, the change is working.",
        })

    return gaps


def score_pricing(listing, shop, niche, metrics):
    """Layer 2. Checks per CLAUDE.md spec thresholds."""
    gaps = []
    price = listing.get("price")
    if price is None:
        return gaps

    title = listing.get("title", "")
    short = short_title(title)
    median = niche.get("median_price", 25.0)
    orders = listing.get("orders", 0)
    review_count = shop.get("review_count", 0)
    on_sale = listing.get("on_sale", None)
    has_free_shipping = listing.get("free_shipping", None)
    niche_free_pct = niche.get("free_shipping_pct", 0.6)

    severity = 0
    evidence_parts = []
    action_parts = []

    if median > 0:
        deviation = (price - median) / median

        # Too cheap (> 30% below median)
        if deviation < -0.30:
            severity += 3
            evidence_parts.append(f'{fmt_price(price)} is {abs(round(deviation * 100))}% below the niche median of {fmt_price(median)}')
            target = round(median * 0.85, 2)
            action_parts.append(f'Test raising to {fmt_price(target)} — underpricing signals low quality and leaves money on the table')

        # Too expensive without trust (> 40% above AND < 20 reviews)
        if deviation > 0.40 and review_count < 20:
            severity += 3
            evidence_parts.append(f'{fmt_price(price)} is {round(deviation * 100)}% above the niche median with only {review_count} reviews to justify it')
            target = round(median * 1.15, 2)
            action_parts.append(f'With {review_count} reviews, buyers don\'t trust a premium price yet. Test {fmt_price(target)} or invest in building reviews first')

    # Permanent sale
    if on_sale is True:
        severity += 2
        evidence_parts.append('listing is permanently on sale — this signals desperation to buyers and devalues your brand')
        action_parts.append('Remove the sale. If you want a lower price, just set it directly')

    # Free shipping
    if has_free_shipping is False and niche_free_pct > 0.6:
        severity += 2
        evidence_parts.append(f'{niche_free_pct*100:.0f}% of your niche offers free shipping — Etsy boosts these listings in search')
        action_parts.append('Build shipping into the price and enable free shipping')

    if severity > 0:
        severity = clamp(severity)
        evidence = f'"{short}": ' + '; '.join(evidence_parts) + '.'
        action = '. '.join(action_parts) + '.'
        gaps.append({
            "gap_type": "pricing",
            "sub_type": "pricing_issues",
            "severity": severity,
            "evidence": evidence,
            "action": action,
            "impact": "high" if severity >= 5 else "medium",
            "confidence": "medium",
            "layer": 2,
            "difficulty": "moderate effort",
            "timeline": "Price changes take effect immediately but need 14+ days to measure impact. Run one price test at a time so you know what worked.",
            "measurement": "Track orders and revenue for this listing 14 days before vs after. If orders increase but revenue drops, the price may be too low — find the sweet spot.",
        })

    return gaps


def score_trust(listing, shop, niche, metrics):
    """Layer 2. Additive per CLAUDE.md spec."""
    gaps = []
    title = listing.get("title", "")
    short = short_title(title)
    review_count = shop.get("review_count")
    has_about = shop.get("has_about_section")
    has_policies = shop.get("has_shop_policies")
    processing_days = shop.get("avg_processing_days")
    niche_avg_reviews = niche.get("median_review_count", 500)

    severity = 0
    evidence_parts = []
    action_parts = []

    if review_count is not None:
        if review_count == 0:
            severity += 3
            evidence_parts.append('zero reviews — this is the biggest trust barrier for new buyers')
            action_parts.append('Every early sale matters. Follow up 2-3 days after delivery with a genuine thank-you message')
        elif review_count < 10 and niche_avg_reviews > 50:
            severity += 2
            evidence_parts.append(f'{review_count} reviews vs niche average of {niche_avg_reviews}')
            action_parts.append('Focus on converting every order into a review opportunity with great packaging and follow-up')

    if has_about is False:
        severity += 1
        evidence_parts.append('missing About section')
        action_parts.append('Write your About section — buyers check this when deciding whether to trust a new shop')

    if has_policies is False:
        severity += 2
        evidence_parts.append('incomplete shop policies')
        action_parts.append('Fill out all shop policies (returns, exchanges, shipping) — incomplete policies are a red flag')

    if processing_days is not None and processing_days > 7:
        severity += 2
        evidence_parts.append(f'{processing_days}-day processing time — buyers often skip listings over 5-7 days')
        action_parts.append(f'Reduce processing time below 7 days if possible. {processing_days} days loses impatient buyers')

    if severity > 0:
        severity = clamp(severity)
        evidence = '; '.join(evidence_parts).capitalize() + '.'
        action = '. '.join(action_parts) + '.'
        gaps.append({
            "gap_type": "trust",
            "sub_type": "trust_issues",
            "severity": severity,
            "evidence": evidence,
            "action": action,
            "impact": "high" if severity >= 5 else "medium",
            "confidence": "high",
            "layer": 2,
            "difficulty": "moderate effort",
            "timeline": "Trust signals (reviews, policies, About section) build gradually. New reviews take weeks. Policy/About changes are instant but affect conversion slowly.",
            "measurement": "Track conversion rate over 3-4 weeks. If completing policies and About section doesn't improve conversion, the trust issue may be review count — which takes longer to fix.",
        })

    return gaps


def score_content(listing, shop, niche, metrics):
    """Layer 1. Additive per CLAUDE.md spec."""
    gaps = []
    title = listing.get("title", "")
    short = short_title(title)
    photos = listing.get("photo_count")
    has_video = listing.get("has_video")
    desc_words = listing.get("description_words")
    brand_name = listing.get("brand_name")
    niche_photos = niche.get("median_photo_count", 5)

    severity = 0
    evidence_parts = []
    action_parts = []

    # Photo checks
    if photos is not None:
        if photos < 3:
            severity += 3
            evidence_parts.append(f'only {photos} photo{"s" if photos != 1 else ""} — critically low')
            action_parts.append(f'Add at least {3 - photos} more photos immediately: hand-held scale shot, close-up detail, and packaging')
        elif photos < niche_photos:
            severity += 1
            evidence_parts.append(f'{photos} photos vs niche average of {niche_photos}')
            action_parts.append(f'Add {niche_photos - photos} more photos — lifestyle context and size comparison work well')

    # Video
    if has_video is False:
        severity += 1
        evidence_parts.append('no video (videos auto-play in search and boost engagement)')
        action_parts.append('Record a 10-15 second clip — even raw phone video of the item rotating works')

    # Description length
    if desc_words is not None:
        if desc_words < 50:
            severity += 2
            evidence_parts.append(f'{desc_words}-word description — far too short')
            action_parts.append('Expand description with dimensions, materials, care instructions, and who it\'s for')
        elif desc_words < 100:
            severity += 1
            evidence_parts.append(f'{desc_words}-word description — could be more detailed')
            action_parts.append('Add more detail: materials, sizing, care instructions, gift-worthiness')

    # Title issues handled by score_visibility (title_structure gap)
    # Only flag in content if there are OTHER content issues to report alongside

    if severity > 0:
        severity = clamp(severity)
        evidence = f'"{short}": ' + '; '.join(evidence_parts) + '.'
        action = '. '.join(action_parts) + '.' if action_parts else 'Improve listing content quality.'
        gaps.append({
            "gap_type": "content",
            "sub_type": "content_issues",
            "severity": severity,
            "evidence": evidence,
            "action": action,
            "impact": "high" if severity >= 5 else "medium",
            "confidence": "high",
            "layer": 1,
            "difficulty": "quick fix",
            "timeline": "Photo/video/description changes go live immediately. Etsy re-indexes within 24 hours. Meaningful signal in 7-14 days.",
            "measurement": "Compare listing views and favorites 14 days before vs 14 days after. If views increased but orders didn't, escalate to conversion optimization.",
        })

    return gaps


def score_competitiveness(listing, shop, niche, metrics):
    """Layer 3. Additive per CLAUDE.md spec."""
    gaps = []
    title = listing.get("title", "")
    short = short_title(title)
    review_count = shop.get("review_count", 0)
    top10_avg = niche.get("top10_review_avg", 5000)
    total_listings = niche.get("total_niche_listings")
    shop_niche_count = shop.get("niche_count")

    severity = 0
    evidence_parts = []
    action_parts = []

    # Niche saturation
    if total_listings is not None:
        if total_listings > 100000:
            severity += 3
            evidence_parts.append(f'{total_listings:,} listings in this niche — extremely saturated')
            action_parts.append('In a niche this crowded, differentiation matters more than optimization. Find an angle the top sellers aren\'t covering')
        elif total_listings > 50000:
            severity += 1
            evidence_parts.append(f'{total_listings:,} listings in this niche — competitive')

    # Review barrier vs top 10
    if review_count is not None and top10_avg > 0 and review_count < top10_avg * 0.05:
        severity += 2
        evidence_parts.append(f'{review_count} reviews vs top 10 average of {top10_avg:,} — competing on trust alone is hard')
        action_parts.append('Target sub-niches where the top sellers are weakest rather than competing head-on')

    # Niche spread
    if shop_niche_count is not None and shop_niche_count > 5:
        severity += 2
        evidence_parts.append(f'shop competes in {shop_niche_count} niches — spread too thin')
        action_parts.append('Focus on your 2-3 strongest niches. Etsy\'s algorithm favors shops with clear specialization')

    if severity > 0:
        severity = clamp(severity)
        evidence = '; '.join(evidence_parts).capitalize() + '.'
        action = '. '.join(action_parts) + '.' if action_parts else 'Consider your competitive positioning.'
        gaps.append({
            "gap_type": "competitiveness",
            "sub_type": "competitive_position",
            "severity": severity,
            "evidence": evidence,
            "action": action,
            "impact": "medium",
            "confidence": "medium",
            "layer": 3,
            "difficulty": "strategic move",
            "timeline": "Competitive repositioning is a 1-2 month play. You're changing what you sell or how you position it, not just tweaking a listing.",
            "measurement": "Track overall shop views and orders month-over-month. If focused niches outperform spread niches after 6-8 weeks, the repositioning is working.",
        })

    return gaps


ALL_SCORERS = [
    score_visibility,
    score_conversion,
    score_pricing,
    score_trust,
    score_content,
    score_competitiveness,
]


# ---------------------------------------------------------------------------
# Per-listing diagnosis: visibility vs conversion
# ---------------------------------------------------------------------------

def diagnose_listing(listing, niche):
    """Determine the primary problem for a listing.

    Returns a diagnosis dict:
      - "primary_problem": "visibility" | "conversion" | "both" | "healthy"
      - "diagnosis_note": human-readable explanation
      - "priority_layers": ordered list of layers to focus on

    Logic:
      - views < 20: not enough data, visibility is the problem
      - views < niche_avg * 0.3: severe visibility problem
      - views < niche_avg * 0.6: moderate visibility problem
      - views >= niche_avg * 0.6 AND conversion below shop/niche avg: conversion problem
      - views >= niche_avg * 0.6 AND conversion OK: healthy (check competitive)
    """
    views = listing.get("views", 0)
    orders = listing.get("orders", 0)
    favorites = listing.get("favorites", 0)
    niche_views = niche.get("median_views_per_listing", 400)
    niche_conv = niche.get("median_conversion_rate", 2.0)

    conv_rate = (orders / views * 100) if views > 0 else 0
    title = short_title(listing.get("title", ""), 40)

    if views < 20:
        return {
            "primary_problem": "visibility",
            "diagnosis_note": f'"{title}" has only {views} views — not enough traffic to diagnose conversion. Focus entirely on getting found first.',
            "priority_layers": [1, 2, 3],  # content fixes → then conversion → competitive
            "skip_conversion": True,
        }

    if views < niche_views * 0.3:
        return {
            "primary_problem": "visibility",
            "diagnosis_note": f'"{title}" has {views} views (niche avg: {niche_views}). The primary problem is visibility — buyers aren\'t finding this listing. Fix discoverability before worrying about conversion.',
            "priority_layers": [1, 3, 2],
            "skip_conversion": False,
        }

    if views < niche_views * 0.6:
        # Moderate visibility issue — check if conversion is also bad
        if conv_rate < niche_conv * 0.5:
            return {
                "primary_problem": "both",
                "diagnosis_note": f'"{title}" has below-average views ({views} vs {niche_views} niche avg) AND a low conversion rate ({conv_rate:.1f}% vs {niche_conv}% niche avg). Needs work on both discoverability and listing quality.',
                "priority_layers": [1, 2, 3],
                "skip_conversion": False,
            }
        return {
            "primary_problem": "visibility",
            "diagnosis_note": f'"{title}" has moderate views ({views}) but converts OK at {conv_rate:.1f}%. The bottleneck is traffic — more views would directly translate to more sales.',
            "priority_layers": [1, 3, 2],
            "skip_conversion": False,
        }

    # Adequate views — is conversion the problem?
    if conv_rate < niche_conv * 0.5:
        return {
            "primary_problem": "conversion",
            "diagnosis_note": f'"{title}" gets decent traffic ({views} views) but only converts at {conv_rate:.1f}% (niche avg: {niche_conv}%). Buyers are finding it but not buying. Focus on pricing, photos, and trust signals.',
            "priority_layers": [2, 1, 3],
            "skip_conversion": False,
        }

    if favorites > 10 and orders == 0:
        return {
            "primary_problem": "conversion",
            "diagnosis_note": f'"{title}" has {views} views and {favorites} favorites but zero orders. People want it — something is blocking the purchase. Check price, shipping, and processing time.',
            "priority_layers": [2, 1, 3],
            "skip_conversion": False,
        }

    if conv_rate < niche_conv:
        return {
            "primary_problem": "conversion",
            "diagnosis_note": f'"{title}" has good visibility ({views} views) but converts below average at {conv_rate:.1f}% (niche: {niche_conv}%). Small conversion improvements here will have the biggest revenue impact.',
            "priority_layers": [2, 1, 3],
            "skip_conversion": False,
        }

    # Listing is performing reasonably
    return {
        "primary_problem": "healthy",
        "diagnosis_note": f'"{title}" is performing well: {views} views, {conv_rate:.1f}% conversion, {orders} orders. Look for incremental improvements and competitive positioning.',
        "priority_layers": [3, 2, 1],
        "skip_conversion": False,
    }


# ---------------------------------------------------------------------------
# Shop-level analysis
# ---------------------------------------------------------------------------

def analyze_shop_health(shop, listings, niche):
    """Compute shop-level health metrics and competitive position."""
    health = {}

    total_views = sum(l.get("views", 0) for l in listings)
    total_orders = sum(l.get("orders", 0) for l in listings)
    total_favorites = sum(l.get("favorites", 0) for l in listings)
    prices = [l["price"] for l in listings if l.get("price")]

    health["total_views"] = total_views
    health["total_orders"] = total_orders
    health["total_favorites"] = total_favorites
    health["listing_count"] = len(listings)

    if total_views > 0:
        health["shop_conversion_rate"] = round((total_orders / total_views) * 100, 2)
    if total_favorites > 0:
        health["shop_fav_to_order"] = round(total_orders / total_favorites, 3)
    if prices:
        health["avg_price"] = round(sum(prices) / len(prices), 2)
        health["price_range"] = [min(prices), max(prices)]
    if total_orders > 0 and prices:
        health["estimated_revenue"] = round(
            sum(l.get("orders", 0) * l.get("price", 0) for l in listings), 2
        )
        health["avg_order_value"] = round(health["estimated_revenue"] / total_orders, 2)

    # Identify strongest and weakest listings
    if listings:
        by_orders = sorted(listings, key=lambda l: l.get("orders", 0), reverse=True)
        health["top_performer"] = {
            "title": by_orders[0].get("title", ""),
            "orders": by_orders[0].get("orders", 0),
            "views": by_orders[0].get("views", 0),
        }
        health["needs_attention"] = {
            "title": by_orders[-1].get("title", ""),
            "orders": by_orders[-1].get("orders", 0),
            "views": by_orders[-1].get("views", 0),
        }

    # Niche position
    niche_conv = niche.get("median_conversion_rate", 2.0)
    shop_conv = health.get("shop_conversion_rate", 0)
    if shop_conv >= niche_conv * 1.2:
        health["conversion_position"] = "above average"
    elif shop_conv >= niche_conv * 0.8:
        health["conversion_position"] = "average"
    else:
        health["conversion_position"] = "below average"

    # Revenue per listing vs niche
    if listings and health.get("estimated_revenue"):
        rev_per_listing = health["estimated_revenue"] / len(listings)
        niche_rev = niche.get("median_orders_per_listing", 8) * niche.get("median_price", 25)
        if niche_rev > 0:
            health["revenue_per_listing_vs_niche"] = round(rev_per_listing / niche_rev, 2)

    # --- Shop-level profit analytics ---
    if total_orders > 0 and prices:
        # Calculate fees on total revenue
        avg_price = health.get("avg_price", 0)
        sample_fees = calculate_etsy_fees(avg_price)
        health["avg_fee_per_sale"] = sample_fees["total_fees"]
        health["avg_fee_rate"] = sample_fees["effective_fee_rate"]
        health["total_fees_estimate"] = round(sample_fees["total_fees"] * total_orders, 2)
        health["net_after_fees"] = round(
            health.get("estimated_revenue", 0) - health["total_fees_estimate"], 2
        )

        # With Offsite Ads scenario
        offsite_fees = calculate_etsy_fees(avg_price, offsite_ads_triggered=True)
        health["fee_rate_with_offsite_ads"] = offsite_fees["effective_fee_rate"]
        health["total_fees_with_offsite"] = round(
            offsite_fees["total_fees"] * total_orders, 2
        )

    # Merge shop metadata (name, location, etc.) without overwriting computed metrics
    computed_keys = {
        "total_views", "total_orders", "total_favorites", "listing_count",
        "shop_conversion_rate", "shop_fav_to_order", "avg_price", "price_range",
        "estimated_revenue", "avg_order_value", "top_performer", "needs_attention",
        "conversion_position", "revenue_per_listing_vs_niche",
        "avg_fee_per_sale", "avg_fee_rate", "total_fees_estimate", "net_after_fees",
        "fee_rate_with_offsite_ads", "total_fees_with_offsite",
    }
    for k, v in shop.items():
        if v is not None and k not in computed_keys:
            health[k] = v

    return health


def rank_listings(listings, niche, shop=None):
    """Rank listings within the shop and vs niche, return enriched listing data."""
    enriched = []
    total_views = sum(l.get("views", 0) for l in listings)

    # Pre-compute ranks using dense ranking (no gaps on ties)
    order_counts = [l.get("orders", 0) for l in listings]
    sorted_unique = sorted(set(order_counts), reverse=True)
    rank_map = {val: idx + 1 for idx, val in enumerate(sorted_unique)}

    for i, listing in enumerate(listings):
        entry = dict(listing)
        entry["metrics"] = compute_listing_metrics(listing, niche, shop)
        entry["traffic_share"] = round(
            listing.get("views", 0) / total_views, 4
        ) if total_views > 0 else 0

        # Performance tier within shop (dense ranking)
        orders = listing.get("orders", 0)
        rank = rank_map.get(orders, len(listings))
        entry["shop_rank"] = rank
        total_ranks = len(sorted_unique)
        if rank <= max(1, total_ranks // 3):
            entry["tier"] = "top"
        elif rank <= max(2, total_ranks * 2 // 3):
            entry["tier"] = "middle"
        else:
            entry["tier"] = "underperforming"

        enriched.append(entry)

    return enriched


# ---------------------------------------------------------------------------
# Main scoring pipeline
# ---------------------------------------------------------------------------

def detect_cross_listing_patterns(enriched_listings, niche):
    """Find what top-performing listings have in common vs underperformers.

    Compares the top third of listings (by orders) against the bottom third
    across every available attribute. Returns a list of pattern insights
    that are specific to THIS shop — not generic advice.
    """
    if len(enriched_listings) < 4:
        return []  # Need at least 4 listings to split meaningfully

    by_orders = sorted(enriched_listings, key=lambda l: l.get("orders", 0), reverse=True)
    split = max(3, len(by_orders) // 3)
    top = by_orders[:split]
    bottom = by_orders[-split:]

    patterns = []

    def avg(lst, key):
        vals = [l.get(key) for l in lst if l.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def pct(lst, key, value=True):
        vals = [l.get(key) for l in lst if l.get(key) is not None]
        return round(sum(1 for v in vals if v == value) / len(vals) * 100) if vals else None

    def avg_metric(lst, metric_key):
        vals = [l.get("metrics", {}).get(metric_key) for l in lst
                if l.get("metrics", {}).get(metric_key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    top_titles = [short_title(l.get("title", ""), 35) for l in top]
    bottom_titles = [short_title(l.get("title", ""), 35) for l in bottom]

    # --- Photo count ---
    top_photos = avg(top, "photo_count")
    bot_photos = avg(bottom, "photo_count")
    if top_photos is not None and bot_photos is not None and top_photos > bot_photos + 1:
        patterns.append({
            "type": "content",
            "attribute": "photo_count",
            "insight": f"Your top sellers average {top_photos} photos per listing. Your bottom sellers average {bot_photos}.",
            "action": f"Add {round(top_photos - bot_photos)} more photos to your underperforming listings — match what's working in your own shop.",
            "confidence": "high",
            "top_val": top_photos,
            "bottom_val": bot_photos,
        })

    # --- Video ---
    top_video = pct(top, "has_video", True)
    bot_video = pct(bottom, "has_video", True)
    if top_video is not None and bot_video is not None and top_video > bot_video + 30:
        patterns.append({
            "type": "content",
            "attribute": "has_video",
            "insight": f"{top_video}% of your top sellers have video vs {bot_video}% of your bottom sellers.",
            "action": "Add video to your underperforming listings — the pattern in your own shop is clear.",
            "confidence": "high",
            "top_val": top_video,
            "bottom_val": bot_video,
        })

    # --- Price ---
    top_price = avg(top, "price")
    bot_price = avg(bottom, "price")
    if top_price is not None and bot_price is not None:
        if top_price > bot_price * 1.3:
            patterns.append({
                "type": "pricing",
                "attribute": "price",
                "insight": f"Your top sellers average {fmt_price(top_price)} vs {fmt_price(bot_price)} for bottom sellers. Higher-priced listings are outperforming in your shop.",
                "action": f"Your lower-priced listings may be undervalued. Test raising prices on bottom performers closer to {fmt_price(round(top_price * 0.85, 2))}.",
                "confidence": "medium",
                "top_val": top_price,
                "bottom_val": bot_price,
            })
        elif bot_price > top_price * 1.3:
            patterns.append({
                "type": "pricing",
                "attribute": "price",
                "insight": f"Your bottom sellers average {fmt_price(bot_price)} — higher than your top sellers at {fmt_price(top_price)}. Overpricing may be hurting these listings.",
                "action": f"Test lower prices on your underperformers. Your buyers clearly respond to the {fmt_price(top_price)} range.",
                "confidence": "medium",
                "top_val": top_price,
                "bottom_val": bot_price,
            })

    # --- Description length ---
    top_desc = avg(top, "description_words")
    bot_desc = avg(bottom, "description_words")
    if top_desc is not None and bot_desc is not None and top_desc > bot_desc * 1.5:
        patterns.append({
            "type": "content",
            "attribute": "description_words",
            "insight": f"Top sellers average {round(top_desc)}-word descriptions vs {round(bot_desc)} words for bottom sellers.",
            "action": f"Expand descriptions on underperformers to at least {round(top_desc)} words — match the detail level of your best listings.",
            "confidence": "medium",
            "top_val": top_desc,
            "bottom_val": bot_desc,
        })

    # --- Conversion rate ---
    top_conv = avg_metric(top, "conversion_rate")
    bot_conv = avg_metric(bottom, "conversion_rate")
    if top_conv is not None and bot_conv is not None and bot_conv > 0 and top_conv > bot_conv * 1.5:
        patterns.append({
            "type": "conversion",
            "attribute": "conversion_rate",
            "insight": f"Top sellers convert at {top_conv}% vs {bot_conv}% for bottom sellers — a {round(top_conv / bot_conv, 1)}x difference.",
            "action": "Study your top-converting listings closely. What do their first two photos show? How is the price positioned? What's in the description? Mirror those choices on your low converters.",
            "confidence": "high",
            "top_val": top_conv,
            "bottom_val": bot_conv,
        })

    # --- Profit margin ---
    top_margins = []
    bot_margins = []
    for l in top:
        ps = l.get("metrics", {}).get("per_sale", {})
        if ps.get("profit_margin") is not None:
            top_margins.append(ps["profit_margin"])
    for l in bottom:
        ps = l.get("metrics", {}).get("per_sale", {})
        if ps.get("profit_margin") is not None:
            bot_margins.append(ps["profit_margin"])
    if top_margins and bot_margins:
        avg_top_m = round(sum(top_margins) / len(top_margins), 1)
        avg_bot_m = round(sum(bot_margins) / len(bot_margins), 1)
        if avg_top_m > avg_bot_m + 10:
            patterns.append({
                "type": "pricing",
                "attribute": "profit_margin",
                "insight": f"Top sellers have {avg_top_m}% profit margins vs {avg_bot_m}% for bottom sellers.",
                "action": f"Your bottom performers are working harder for less profit. Either raise prices or reduce costs on these listings.",
                "confidence": "medium",
                "top_val": avg_top_m,
                "bottom_val": avg_bot_m,
            })

    # --- Title word count ---
    top_words = [len(l.get("title", "").split()) for l in top if l.get("title")]
    bot_words = [len(l.get("title", "").split()) for l in bottom if l.get("title")]
    if top_words and bot_words:
        avg_tw = round(sum(top_words) / len(top_words))
        avg_bw = round(sum(bot_words) / len(bot_words))
        if abs(avg_tw - avg_bw) >= 3:
            shorter = "shorter" if avg_tw < avg_bw else "longer"
            patterns.append({
                "type": "visibility",
                "attribute": "title_length",
                "insight": f"Top sellers average {avg_tw}-word titles vs {avg_bw} words for bottom sellers — your winners use {shorter} titles.",
                "action": f"Adjust underperforming listing titles to around {avg_tw} words to match your best performers.",
                "confidence": "low",
                "top_val": avg_tw,
                "bottom_val": avg_bw,
            })

    # --- Favorites-to-orders ratio ---
    top_fav_ratio = []
    bot_fav_ratio = []
    for l in top:
        f, o = l.get("favorites", 0), l.get("orders", 0)
        if f > 0:
            top_fav_ratio.append(o / f)
    for l in bottom:
        f, o = l.get("favorites", 0), l.get("orders", 0)
        if f > 0:
            bot_fav_ratio.append(o / f)
    if top_fav_ratio and bot_fav_ratio:
        avg_tfr = round(sum(top_fav_ratio) / len(top_fav_ratio), 3)
        avg_bfr = round(sum(bot_fav_ratio) / len(bot_fav_ratio), 3)
        if avg_bfr > 0 and avg_tfr > avg_bfr * 2:
            patterns.append({
                "type": "conversion",
                "attribute": "fav_to_order",
                "insight": f"Top sellers convert {round(avg_tfr * 100, 1)}% of favorites into orders vs {round(avg_bfr * 100, 1)}% for bottom sellers.",
                "action": "Your bottom listings get favorited but don't convert. The gap is likely pricing or shipping — people want these items but something stops them at checkout.",
                "confidence": "high",
                "top_val": round(avg_tfr * 100, 1),
                "bottom_val": round(avg_bfr * 100, 1),
            })

    # --- Tag count (if available) ---
    top_tags = avg(top, "tag_count")
    bot_tags = avg(bottom, "tag_count")
    if top_tags is not None and bot_tags is not None and top_tags > bot_tags + 2:
        patterns.append({
            "type": "visibility",
            "attribute": "tag_count",
            "insight": f"Top sellers use {round(top_tags)} tags on average vs {round(bot_tags)} for bottom sellers.",
            "action": f"Fill tag slots on underperformers to at least {round(top_tags)}.",
            "confidence": "medium",
            "top_val": top_tags,
            "bottom_val": bot_tags,
        })

    return patterns


def detect_shop_level_issues(listings, shop, niche):
    """Detect shop-wide issues that per-listing scorers miss.

    Returns a list of gap dicts for:
    1. Fake/inflated original prices on sales
    2. Duplicate/interchangeable listings
    3. Over-reliance on a single product type
    4. Every listing on sale (shop-wide desperation signal)
    """
    gaps = []
    if not listings:
        return gaps

    # --- Fake/inflated original prices ---
    sale_listings = [l for l in listings if l.get("on_sale")]
    if sale_listings:
        inflated = []
        for l in sale_listings:
            orig = l.get("original_price")
            price = l.get("price")
            if orig and price and orig > price * 3:
                inflated.append(l)

        if inflated:
            example = inflated[0]
            ex_price = fmt_price(example.get("price"))
            ex_orig = fmt_price(example.get("original_price"))
            ex_title = short_title(example.get("title", ""), 40)
            gaps.append({
                "gap_type": "pricing",
                "sub_type": "inflated_original_price",
                "severity": 7,
                "evidence": (
                    f'{len(inflated)} of {len(listings)} listings show original prices that look '
                    f'inflated. "{ex_title}" is listed at {ex_price} with a crossed-out '
                    f'price of {ex_orig}. Experienced Etsy buyers recognize this pattern '
                    f'and it signals a scam or low-quality seller. Etsy has also '
                    f'cracked down on misleading sale pricing.'
                ),
                "action": (
                    f'Remove the fake original prices immediately. If your real price is '
                    f'{ex_price}, list it at {ex_price} with no sale. An honest price '
                    f'from a new shop builds more trust than a "75% off" sale that nobody '
                    f'believes. If you want to run a real promotion, discount by 10-15% '
                    f'from a genuine original price for a limited time.'
                ),
                "impact": "high",
                "confidence": "high",
                "layer": 2,
                "difficulty": "quick fix",
                "timeline": "Remove fake sales now. The trust damage is ongoing — every buyer who sees the inflated price and doesn't buy is a lost opportunity.",
                "measurement": "Track favorites-to-orders ratio. If it improves after removing the fake sale, the inflated price was the barrier.",
                "listing": f"{len(inflated)} listings affected",
                "listing_index": 0,
            })

    # --- Every listing on sale ---
    if sale_listings and len(sale_listings) == len(listings) and len(listings) > 2:
        gaps.append({
            "gap_type": "pricing",
            "sub_type": "permanent_shop_wide_sale",
            "severity": 5,
            "evidence": (
                f'All {len(listings)} listings are on sale. When everything is always on sale, '
                f'nothing is actually on sale. This tells buyers your "regular" prices aren\'t real, '
                f'which undermines trust — especially for a shop with {shop.get("review_count", 0)} '
                f'review{"s" if shop.get("review_count", 0) != 1 else ""}.'
            ),
            "action": (
                f'Set your real prices as the regular prices and remove all sales. '
                f'Save promotions for genuine events (holidays, shop anniversary, clearing old stock). '
                f'A shop-wide permanent sale is one of the strongest "this isn\'t a serious business" '
                f'signals on Etsy.'
            ),
            "impact": "high",
            "confidence": "high",
            "layer": 2,
            "difficulty": "quick fix",
            "timeline": "Do this today. It takes 5 minutes and removes a major trust barrier.",
            "measurement": "Monitor shop favorites and conversion rate over 2 weeks. Honest pricing builds trust even if it doesn't immediately increase orders.",
            "listing": "All listings",
            "listing_index": 0,
        })

    # --- Listing similarity detection ---
    # Check if multiple listings are essentially the same product with different keywords.
    # Uses light stop-word removal so product-type words (oil, painting, portrait) are
    # kept for comparison — they're what makes listings look the same to a buyer.
    titles = [(i, l.get("title", "")) for i, l in enumerate(listings) if l.get("title")]
    if len(titles) >= 3:
        # Only remove truly generic words — keep product-type words
        stop_words = {"the", "a", "an", "and", "of", "for", "with", "in", "on", "to",
                      "from", "|", "...", "..", "—", "-"}

        def key_words(title):
            words = set()
            for w in title.lower().replace("|", " ").replace("...", " ").replace("..", " ").split():
                w = w.strip(",.!?()[]")
                if w and w not in stop_words and len(w) > 2:
                    words.add(w)
            return words

        # Also check price similarity — same price + similar title = very likely duplicate
        def is_similar(idx_a, title_a, idx_b, title_b):
            words_a = key_words(title_a)
            words_b = key_words(title_b)
            if not words_a or not words_b:
                return False
            overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
            # Lower threshold (40%) + same price = strong signal
            price_a = listings[idx_a].get("price")
            price_b = listings[idx_b].get("price")
            same_price = price_a and price_b and price_a == price_b
            if same_price and overlap >= 0.3:
                return True
            # Higher threshold if prices differ
            return overlap >= 0.4

        # Find groups of similar listings
        similar_groups = []
        used = set()
        for i, (idx_a, title_a) in enumerate(titles):
            if idx_a in used:
                continue
            group = [idx_a]
            for j, (idx_b, title_b) in enumerate(titles):
                if j <= i or idx_b in used:
                    continue
                if is_similar(idx_a, title_a, idx_b, title_b):
                    group.append(idx_b)
            if len(group) >= 3:
                for idx in group:
                    used.add(idx)
                similar_groups.append(group)

        for group in similar_groups:
            group_listings = [listings[i] for i in group]
            sample_titles = [short_title(l.get("title", ""), 35) for l in group_listings[:3]]
            same_price = len(set(l.get("price") for l in group_listings)) == 1
            price_note = f" — all at the same price of {fmt_price(group_listings[0].get('price'))}" if same_price else ""

            gaps.append({
                "gap_type": "content",
                "sub_type": "duplicate_listings",
                "severity": 6,
                "evidence": (
                    f'{len(group)} of {len(listings)} listings look nearly interchangeable to a buyer{price_note}. '
                    f'Examples: "{sample_titles[0]}", "{sample_titles[1]}"'
                    f'{", " + chr(34) + sample_titles[2] + chr(34) if len(sample_titles) > 2 else ""}. '
                    f'Etsy\'s search algorithm deprioritizes shops with duplicate-looking listings, and '
                    f'buyers who see the same product repeated assume the shop lacks variety.'
                ),
                "action": (
                    f'Differentiate these {len(group)} listings. Options: '
                    f'different subjects (couple vs pet vs family), '
                    f'different sizes or formats (8x10 vs 16x20, framed vs unframed), '
                    f'different styles (realistic vs impressionist), '
                    f'or bundle them into a single listing with variations. '
                    f'Each listing should have a clearly different first photo so buyers '
                    f'can tell them apart in search results.'
                ),
                "impact": "high",
                "confidence": "high",
                "layer": 1,
                "difficulty": "moderate effort",
                "timeline": "This is a bigger change — plan the differentiation, take new photos, rewrite titles. Allow 1-2 weeks to implement.",
                "measurement": "Track total shop views. If Etsy is suppressing duplicate listings, you should see a view increase within 2-3 weeks of differentiation.",
                "listing": f"{len(group)} similar listings",
                "listing_index": group[0],
            })

    # --- Over-concentration in one product type ---
    # Check if the shop has very few categories relative to listings
    prices = [l.get("price") for l in listings if l.get("price")]
    if prices:
        unique_prices = set(prices)
        if len(unique_prices) <= 2 and len(listings) >= 5:
            gaps.append({
                "gap_type": "competitiveness",
                "sub_type": "no_price_variety",
                "severity": 3,
                "evidence": (
                    f'{len(listings)} listings but only {len(unique_prices)} unique price '
                    f'point{"s" if len(unique_prices) > 1 else ""}. '
                    f'This limits your addressable market — buyers with different budgets '
                    f'have no entry point to your shop.'
                ),
                "action": (
                    f'Add product tiers: a lower-priced entry point '
                    f'(like a smaller size or simpler style) and a premium option. '
                    f'This captures both budget-conscious browsers and buyers looking for '
                    f'something special. Even 3 price points significantly increases reach.'
                ),
                "impact": "medium",
                "confidence": "medium",
                "layer": 3,
                "difficulty": "strategic move",
                "timeline": "Creating new product tiers takes time — new photos, listings, possibly new products. Plan for 2-4 weeks.",
                "measurement": "Track whether new price tiers attract different buyer segments. Lower-priced items should have higher conversion rates.",
                "listing": "Shop-wide",
                "listing_index": 0,
            })

    return gaps


def score_shop(data):
    shop = data.get("shop", {})
    listings = data.get("listings", [])
    # Load niche preset, then override with any custom context
    preset_name = data.get("niche_preset", "default")
    base_niche = NICHE_PRESETS.get(preset_name, DEFAULT_NICHE)
    niche = {**base_niche, **data.get("niche_context", {})}
    search_terms = data.get("search_terms", [])

    if not listings:
        return {"error": "No listings provided", "gaps": [], "recommendations": []}

    # Enrich listings
    enriched_listings = rank_listings(listings, niche, shop)

    # Shop health
    health = analyze_shop_health(shop, listings, niche)

    # Inject computed shop metrics so scorers can reference them
    shop_with_metrics = dict(shop)
    if health.get("shop_conversion_rate") is not None:
        shop_with_metrics["shop_conversion_rate"] = health["shop_conversion_rate"]

    # --- Diagnose each listing: visibility vs conversion ---
    PRIORITY_BOOST = 1.5
    DEPRIORITY = 0.5

    # If ALL listings have zero views, traffic_share is meaningless — use severity alone
    total_shop_views = sum(l.get("views", 0) for l in enriched_listings)
    all_zero_traffic = total_shop_views == 0

    listing_diagnoses = []
    all_gaps = []

    for idx, listing in enumerate(enriched_listings):
        listing_ref = listing.get("title", f"Listing #{listing.get('shop_rank', '?')}")
        traffic_share = listing.get("traffic_share", 0)
        metrics = listing.get("metrics", {})

        # Diagnose this listing
        diagnosis = diagnose_listing(listing, niche)
        listing["diagnosis"] = diagnosis
        listing_diagnoses.append({
            "listing": listing_ref,
            "primary_problem": diagnosis["primary_problem"],
            "note": diagnosis["diagnosis_note"],
        })

        priority_layers = diagnosis["priority_layers"]
        top_layer = priority_layers[0] if priority_layers else 1

        for scorer in ALL_SCORERS:
            # Skip conversion scoring when views are too low
            if diagnosis.get("skip_conversion") and scorer == score_conversion:
                continue

            gaps = scorer(listing, shop_with_metrics, niche, metrics)
            for gap in gaps:
                gap["listing"] = listing_ref
                gap["listing_index"] = idx
                gap["traffic_share"] = traffic_share
                gap["primary_problem"] = diagnosis["primary_problem"]

                # Weight priority based on diagnosis
                gap_layer = gap.get("layer", 1)
                if all_zero_traffic:
                    # No traffic data — rank purely by severity
                    base_score = gap["severity"] * 1.5
                else:
                    # Use traffic_share with a minimum floor
                    effective_share = max(traffic_share, 1.0 / max(len(enriched_listings), 1))
                    base_score = gap["severity"] * effective_share * 10

                if gap_layer == top_layer:
                    gap["priority_score"] = round(base_score * PRIORITY_BOOST, 2)
                    gap["priority_reason"] = "matches primary bottleneck"
                elif gap_layer in priority_layers[:2]:
                    gap["priority_score"] = round(base_score, 2)
                    gap["priority_reason"] = "relevant"
                else:
                    gap["priority_score"] = round(base_score * DEPRIORITY, 2)
                    gap["priority_reason"] = "not the current bottleneck"

                all_gaps.append(gap)

    all_gaps.sort(key=lambda g: g["priority_score"], reverse=True)

    # Deduplicate — keep highest priority per listing+gap combo
    seen_actions = set()
    unique_gaps = []
    for g in all_gaps:
        full_key = (g["listing"], g["gap_type"], g["sub_type"])
        if full_key not in seen_actions:
            seen_actions.add(full_key)
            unique_gaps.append(g)
    all_gaps = unique_gaps

    # --- Shop-level diagnosis ---
    vis_count = sum(1 for d in listing_diagnoses if d["primary_problem"] == "visibility")
    conv_count = sum(1 for d in listing_diagnoses if d["primary_problem"] == "conversion")
    both_count = sum(1 for d in listing_diagnoses if d["primary_problem"] == "both")
    healthy_count = sum(1 for d in listing_diagnoses if d["primary_problem"] == "healthy")

    if vis_count > conv_count:
        shop_diag = "visibility"
        shop_diag_note = f'{vis_count} of {len(listings)} listings have a visibility problem — buyers aren\'t finding them. Priority: get found before optimizing conversion.'
    elif conv_count > vis_count:
        shop_diag = "conversion"
        shop_diag_note = f'{conv_count} of {len(listings)} listings have a conversion problem — views but not enough sales. Priority: convert the traffic you already have.'
    elif both_count > 0:
        shop_diag = "both"
        shop_diag_note = f'Your shop has both visibility and conversion issues across different listings. Recommendations are prioritized per listing based on each one\'s bottleneck.'
    else:
        shop_diag = "healthy"
        shop_diag_note = f'{healthy_count} of {len(listings)} listings are performing reasonably. Focus on incremental improvements and competitive positioning.'

    # Build gap breakdown
    gap_type_counts = defaultdict(int)
    gap_type_max_severity = defaultdict(int)
    for g in all_gaps:
        gap_type_counts[g["gap_type"]] += 1
        gap_type_max_severity[g["gap_type"]] = max(
            gap_type_max_severity[g["gap_type"]], g["severity"]
        )

    # --- Shop-level issue detection ---
    shop_gaps = detect_shop_level_issues(enriched_listings, shop_with_metrics, niche)
    for g in shop_gaps:
        if "traffic_share" not in g:
            g["traffic_share"] = 1.0  # shop-wide issues affect everything
        if "primary_problem" not in g:
            g["primary_problem"] = shop_diag
        # Shop-level issues get high priority since they affect the entire shop
        if "priority_score" not in g:
            g["priority_score"] = round(g["severity"] * 1.5, 2)
        if "priority_reason" not in g:
            g["priority_reason"] = "affects entire shop"
        all_gaps.append(g)

    # Re-sort after adding shop-level gaps
    all_gaps.sort(key=lambda g: g["priority_score"], reverse=True)

    # --- Cross-listing pattern detection ---
    patterns = detect_cross_listing_patterns(enriched_listings, niche)

    return {
        "shop_health": health,
        "patterns": patterns,
        "shop_diagnosis": {
            "primary_problem": shop_diag,
            "note": shop_diag_note,
            "per_listing": listing_diagnoses,
            "visibility_count": vis_count,
            "conversion_count": conv_count,
            "both_count": both_count,
            "healthy_count": healthy_count,
        },
        "listings": enriched_listings,
        "search_terms": search_terms,
        "gap_breakdown": {
            gtype: {
                "count": gap_type_counts[gtype],
                "max_severity": gap_type_max_severity[gtype],
            }
            for gtype in gap_type_counts
        },
        "gaps": all_gaps,
        "niche": niche,
    }


def load_input(path):
    """Load input data from a JSON file."""
    with open(path) as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "listings" in raw:
        return raw

    if isinstance(raw, list):
        data = {"shop": {}, "listings": []}
        for item in raw:
            item_type = item.get("type", "")
            metrics = item.get("metrics", {})

            if item_type == "shop_stats":
                data["shop"]["visits"] = metrics.get("visits")
                data["shop"]["views"] = metrics.get("views")
                data["shop"]["orders"] = metrics.get("orders")
                data["shop"]["revenue"] = metrics.get("revenue")
                data["shop"]["conversion_rate"] = metrics.get("conversion_rate")
                if item.get("date_range"):
                    data["shop"]["date_range"] = item["date_range"]

            elif item_type == "listing_stats":
                for listing in item.get("listings", []):
                    data["listings"].append(listing)

            elif item_type == "conversion_breakdown":
                data["shop"]["views"] = metrics.get("views", data["shop"].get("views"))
                data["shop"]["visits"] = metrics.get("visits", data["shop"].get("visits"))
                data["shop"]["favorites"] = metrics.get("favorites")
                data["shop"]["orders"] = metrics.get("orders", data["shop"].get("orders"))
                data["shop"]["conversion_rate"] = metrics.get("conversion_rate", data["shop"].get("conversion_rate"))
                data["shop"]["avg_order_value"] = metrics.get("avg_order_value")

            elif item_type == "search_visibility":
                data["shop"]["impressions"] = metrics.get("impressions")
                data["shop"]["clicks"] = metrics.get("clicks")
                data["shop"]["click_rate"] = metrics.get("click_rate")
                data["search_terms"] = item.get("terms", [])

        data["shop"] = {k: v for k, v in data["shop"].items() if v is not None}
        return data

    return raw


# ---------------------------------------------------------------------------
# Example data
# ---------------------------------------------------------------------------
EXAMPLE_DATA = {
    "shop": {
        "name": "CrystalMoonCo",
        "review_count": 234,
        "has_about_section": True,
        "has_shop_policies": True,
        "avg_processing_days": 5,
    },
    "listings": [
        {
            "title": "Amethyst Cluster Raw Crystal Geode Healing Stone Natural Purple",
            "price": 34.99, "views": 812, "favorites": 145, "orders": 18,
            "photo_count": 7, "has_video": True, "description_words": 180,
            "materials_cost": 8.50, "packaging_cost": 2.00, "shipping_actual": 5.50,
        },
        {
            "title": "Rose Quartz Tower Point Crystal Wand Pink Heart Chakra Gift",
            "price": 22.50, "views": 643, "favorites": 98, "orders": 14,
            "photo_count": 5, "has_video": False, "description_words": 120,
            "materials_cost": 5.00, "packaging_cost": 1.50, "shipping_actual": 4.50,
        },
        {
            "title": "Selenite Charging Plate Round Crystal Cleansing Slab White",
            "price": 18.99, "views": 521, "favorites": 67, "orders": 11,
            "photo_count": 4, "has_video": False, "description_words": 95,
            "materials_cost": 3.50, "packaging_cost": 1.50, "shipping_actual": 4.00,
        },
        {
            "title": "Black Tourmaline Raw Stone Protection Crystal EMF Shield Chunk",
            "price": 12.99, "views": 489, "favorites": 72, "orders": 9,
            "photo_count": 3, "has_video": False, "description_words": 60,
            "materials_cost": 2.00, "packaging_cost": 1.00, "shipping_actual": 3.50,
            "tag_count": 8, "tags_matching_autocomplete": 3,
        },
        {
            "title": "Crystal Mystery Box Healing Stones Gift Set Surprise Bag Crystals",
            "price": 44.99, "views": 467, "favorites": 134, "orders": 12,
            "photo_count": 6, "has_video": True, "description_words": 200,
            "materials_cost": 15.00, "packaging_cost": 3.50, "shipping_actual": 7.00,
        },
        {
            "title": "Citrine Point Natural Yellow Crystal Abundance Manifestation Tower",
            "price": 28.00, "views": 398, "favorites": 56, "orders": 7,
            "photo_count": 4, "has_video": False, "description_words": 110,
            "materials_cost": 7.00, "packaging_cost": 1.50, "shipping_actual": 4.50,
        },
        {
            "title": "Labradorite Palm Stone Polished Flash Crystal Meditation Worry Stone",
            "price": 16.50, "views": 341, "favorites": 48, "orders": 6,
            "photo_count": 5, "has_video": False, "description_words": 130,
            "materials_cost": 4.00, "packaging_cost": 1.00, "shipping_actual": 3.50,
        },
        {
            "title": "Moonstone Ring Sterling Silver Crystal Jewelry Rainbow Flash Boho",
            "price": 52.00, "views": 305, "favorites": 89, "orders": 4,
            "photo_count": 8, "has_video": True, "description_words": 220,
            "materials_cost": 18.00, "packaging_cost": 2.50, "shipping_actual": 5.00,
        },
    ],
}


if __name__ == "__main__":
    output_file = "diagnosis_result.json"
    input_data = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "-o" and i + 1 < len(args):
            output_file = args[i + 1]
            i += 2
        else:
            input_data = load_input(os.path.expanduser(args[i]))
            i += 1

    if input_data is None:
        print("No input file provided — running with example data.", file=sys.stderr)
        input_data = EXAMPLE_DATA

    result = score_shop(input_data)

    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary
    health = result["shop_health"]
    gaps = result["gaps"]
    print(f"\nShopPulse Diagnosis Complete", file=sys.stderr)
    print(f"{'='*40}", file=sys.stderr)
    print(f"Listings analyzed: {health.get('listing_count', 0)}", file=sys.stderr)
    print(f"Total gaps found:  {len(gaps)}", file=sys.stderr)
    if health.get("shop_conversion_rate") is not None:
        print(f"Shop conversion:   {health['shop_conversion_rate']}% ({health.get('conversion_position', '')})", file=sys.stderr)
    if health.get("estimated_revenue"):
        print(f"Est. revenue:      ${health['estimated_revenue']:,.2f}", file=sys.stderr)
    if health.get("total_fees_estimate"):
        print(f"Est. Etsy fees:    ${health['total_fees_estimate']:,.2f} ({health.get('avg_fee_rate', 0)}% effective rate)", file=sys.stderr)
    if health.get("net_after_fees"):
        print(f"Net after fees:    ${health['net_after_fees']:,.2f}", file=sys.stderr)
    if health.get("fee_rate_with_offsite_ads"):
        print(f"  (with Offsite Ads: {health['fee_rate_with_offsite_ads']}% fee rate)", file=sys.stderr)
    print(f"\nTop 3 actions:", file=sys.stderr)
    for i, g in enumerate(gaps[:3], 1):
        print(f"  {i}. {g['action'][:100]}", file=sys.stderr)
    print(f"\nFull results: {output_file}", file=sys.stderr)

    print(json.dumps(result, indent=2))
