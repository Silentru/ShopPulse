"""
ShopPulse Screenshot Extractor
Extracts shop and listing data from Etsy dashboard screenshots using OCR.

Supports:
- Shop Stats screenshots (views, visits, orders, revenue)
- Listing Stats screenshots (views, favorites, orders per listing)
- Search Visibility screenshots (impressions, clicks, position)
- Conversion Breakdown screenshots (views, visits, favorites, orders, conversion rate, avg order value)

Usage:
    python3 screenshot_extractor.py <image_path> [--type shop_stats|listing_stats|search_visibility|conversion_breakdown]
    python3 screenshot_extractor.py <folder_path>  (processes all images in folder)

Output: JSON to stdout (pipe to file with > output.json)
"""

import sys
import os
import re
import json
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageEnhance


def preprocess_image(image):
    """Enhance image for better OCR accuracy on Etsy dashboard screenshots."""
    # Convert to grayscale
    gray = image.convert("L")
    # Increase contrast
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(2.0)
    # Increase sharpness
    enhancer = ImageEnhance.Sharpness(gray)
    gray = enhancer.enhance(2.0)
    # Scale up small images for better OCR
    width, height = gray.size
    if width < 1500:
        scale = 1500 / width
        gray = gray.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
    return gray


def extract_text(image_path):
    """Run OCR on an image and return the raw text."""
    image = Image.open(image_path)
    processed = preprocess_image(image)
    # Save preprocessed image to temp file and call tesseract directly
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        processed.save(tmp.name)
        try:
            result = subprocess.run(
                ["tesseract", tmp.name, "stdout"],
                capture_output=True, text=True
            )
            return result.stdout
        finally:
            os.unlink(tmp.name)


def parse_number(text):
    """Parse a number string that may contain commas, dollar signs, or K/M suffixes."""
    text = text.strip().replace(",", "").replace("$", "")
    # Handle K/M suffixes (e.g., "1.2K" -> 1200)
    if text.upper().endswith("K"):
        return float(text[:-1]) * 1000
    if text.upper().endswith("M"):
        return float(text[:-1]) * 1000000
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def find_metric(text, patterns):
    """Search text for metric patterns and return the first match value."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = parse_number(match.group(1))
            if value is not None:
                return value
    return None


def extract_label_value_rows(text):
    """Extract metrics from OCR text where labels are on one line and values on the next.

    Etsy dashboards often render as:
        Visits Orders Revenue Conversion rate
        4,328 87 $2,847.50 2.01%
    """
    # Known label keywords and their canonical names
    # Longer keywords first so "total views" matches before "views"
    label_map = {
        "total views": "views",
        "total visits": "visits",
        "total favorites": "favorites",
        "total favourites": "favorites",
        "total orders": "orders",
        "conversion rate": "conversion_rate",
        "avg order value": "avg_order_value",
        "average order value": "avg_order_value",
        "visits": "visits",
        "orders": "orders",
        "revenue": "revenue",
        "conversion": "conversion_rate",
        "views": "views",
        "favorites": "favorites",
        "favourites": "favorites",
    }

    lines = text.split("\n")
    found = {}

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Check if this line contains multiple known labels
        matched_labels = []
        for keyword, canonical in label_map.items():
            if keyword in line_lower:
                # Record the position of this label in the line for ordering
                pos = line_lower.index(keyword)
                matched_labels.append((pos, canonical))

        if len(matched_labels) >= 2:
            # Sort labels by their position in the line
            matched_labels.sort(key=lambda x: x[0])
            label_names = [m[1] for m in matched_labels]

            # Try values on the NEXT line (labels above values)
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                value_tokens = re.findall(r"\$?[\d,]+\.?\d*[KkMm]?\s*%?", next_line)
                value_tokens = [t.strip() for t in value_tokens if t.strip()]

                if len(value_tokens) >= len(label_names):
                    for j, label in enumerate(label_names):
                        if j < len(value_tokens):
                            raw = value_tokens[j]
                            raw = raw.rstrip("%")
                            value = parse_number(raw)
                            if value is not None:
                                found[label] = value
                    continue

            # Try values on the PREVIOUS line (values above labels)
            if i > 0:
                prev_line = lines[i - 1]
                value_tokens = re.findall(r"\$?[\d,]+\.?\d*[KkMm]?\s*%?", prev_line)
                value_tokens = [t.strip() for t in value_tokens if t.strip()]

                if len(value_tokens) >= len(label_names):
                    for j, label in enumerate(label_names):
                        if j < len(value_tokens):
                            raw = value_tokens[j]
                            raw = raw.rstrip("%")
                            value = parse_number(raw)
                            if value is not None:
                                found[label] = value

    return found


def extract_shop_stats(text):
    """Extract shop-level stats from an Etsy Shop Stats screenshot."""
    data = {"type": "shop_stats", "metrics": {}}

    # First, try label-value row extraction (handles Etsy's card layout)
    row_metrics = extract_label_value_rows(text)
    data["metrics"].update(row_metrics)

    # Then fill in any missing metrics with inline pattern matching
    metrics_config = {
        "visits": [
            r"visits?\s*[:\-]?\s*([\d,]+\.?\d*[KkMm]?)",
            r"([\d,]+\.?\d*[KkMm]?)\s*visits?",
        ],
        "views": [
            r"views?\s*[:\-]?\s*([\d,]+\.?\d*[KkMm]?)",
            r"([\d,]+\.?\d*[KkMm]?)\s*views?",
        ],
        "orders": [
            r"orders?\s*[:\-]?\s*([\d,]+\.?\d*[KkMm]?)",
            r"([\d,]+\.?\d*[KkMm]?)\s*orders?",
        ],
        "revenue": [
            r"revenue\s*[:\-]?\s*\$?([\d,]+\.?\d*[KkMm]?)",
            r"\$\s*([\d,]+\.?\d*[KkMm]?)\s*revenue",
        ],
        "favorites": [
            r"favou?rites?\s*[:\-]?\s*([\d,]+\.?\d*[KkMm]?)",
            r"([\d,]+\.?\d*[KkMm]?)\s*favou?rites?",
        ],
        "conversion_rate": [
            r"conversion\s*rate?\s*[:\-]?\s*([\d.]+)\s*%",
            r"([\d.]+)\s*%\s*conversion",
        ],
    }

    for metric_name, patterns in metrics_config.items():
        if metric_name not in data["metrics"]:
            value = find_metric(text, patterns)
            if value is not None:
                data["metrics"][metric_name] = value

    # Try to extract date range
    date_match = re.search(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2})"
        r"\s*[\-–—to]+\s*"
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        data["date_range"] = f"{date_match.group(1)} - {date_match.group(2)}"

    return data


def extract_listing_stats(text):
    """Extract listing-level stats from an Etsy Listing Stats screenshot."""
    data = {"type": "listing_stats", "listings": []}

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Collect values into columns
    titles = []
    prices = []
    views_list = []
    favorites_list = []
    orders_list = []

    # Track which column section we're in based on header keywords
    current_section = None
    header_keywords = {
        "listing": "titles", "price": "prices", "views": "views",
        "favorites": "favorites", "favourites": "favorites",
        "orders": "orders",
    }

    for line in lines:
        line_lower = line.lower()

        # Check if this line is a section header
        is_header = False
        for keyword, section in header_keywords.items():
            if line_lower == keyword or line_lower == keyword + "s":
                current_section = section
                is_header = True
                break
        if is_header:
            continue

        # Skip table-level headers
        if "top listings" in line_lower or "listing stats" in line_lower:
            continue

        # Parse based on what's in the line
        view_val = find_metric(line, [r"([\d,]+)\s*views?"])
        fav_val = find_metric(line, [r"([\d,]+)\s*favou?rites?"])
        order_val = find_metric(line, [r"([\d,]+)\s*(?:orders?|sales?)"])
        price_val = find_metric(line, [r"\$\s*([\d,]+\.?\d*)"])

        # If line has multiple metrics on one row (inline layout), handle directly
        if sum(x is not None for x in [view_val, fav_val, order_val]) >= 2:
            listing = {}
            if view_val is not None:
                listing["views"] = view_val
            if fav_val is not None:
                listing["favorites"] = fav_val
            if order_val is not None:
                listing["orders"] = order_val
            if price_val is not None:
                listing["price"] = price_val
            data["listings"].append(listing)
            continue

        # Columnar layout: assign to the appropriate column
        if view_val is not None:
            views_list.append(view_val)
        elif fav_val is not None:
            favorites_list.append(fav_val)
        elif order_val is not None:
            orders_list.append(order_val)
        elif price_val is not None and current_section == "prices":
            prices.append(price_val)
        elif price_val is not None and not current_section:
            prices.append(price_val)
        elif len(line) > 15 and not re.match(r"^[\d\s,$%.]+$", line):
            # Likely a listing title — clean OCR artifacts from the start
            clean_title = re.sub(r"^[^A-Za-z]*", "", line).strip()
            if clean_title:
                titles.append(clean_title)

    # If we collected columnar data, merge into listings
    if views_list or favorites_list or orders_list:
        count = max(len(titles), len(views_list), len(favorites_list), len(orders_list))
        for i in range(count):
            listing = {}
            if i < len(titles):
                listing["title"] = titles[i]
            if i < len(prices):
                listing["price"] = prices[i]
            if i < len(views_list):
                listing["views"] = views_list[i]
            if i < len(favorites_list):
                listing["favorites"] = favorites_list[i]
            if i < len(orders_list):
                listing["orders"] = orders_list[i]
            data["listings"].append(listing)

    return data


def extract_search_visibility(text):
    """Extract Search Visibility data from an Etsy screenshot."""
    data = {"type": "search_visibility", "metrics": {}, "terms": []}

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # --- Extract top-level summary metrics ---
    # These appear as label-value pairs (value on line before or after label)
    # e.g., "18,420\nImpressions" or "2,814\nClicks" or "15.3%\nClick rate"
    for i, line in enumerate(lines):
        line_lower = line.lower()

        if line_lower == "impressions" and i > 0:
            val = parse_number(re.sub(r"[^\d,.]", "", lines[i - 1]))
            if val is not None and "impressions" not in data["metrics"]:
                data["metrics"]["impressions"] = val
        elif line_lower == "clicks" and i > 0:
            val = parse_number(re.sub(r"[^\d,.]", "", lines[i - 1]))
            if val is not None and "clicks" not in data["metrics"]:
                data["metrics"]["clicks"] = val
        elif "click rate" in line_lower or "click through" in line_lower:
            # Check line before for the percentage
            if i > 0:
                pct_match = re.search(r"([\d.]+)\s*%", lines[i - 1])
                if pct_match:
                    data["metrics"]["click_rate"] = float(pct_match.group(1))

    # --- Extract search terms table (columnar OCR layout) ---
    # OCR typically renders as: terms column, then impressions column, then clicks, then position
    terms = []
    impressions = []
    clicks = []
    positions = []

    # Find quoted search terms
    for line in lines:
        term_match = re.match(r'^["\u201c\u201d\u2018\u2019\']+(.+?)["\u201c\u201d\u2018\u2019\']+$', line)
        if term_match:
            terms.append(term_match.group(1))

    # Find the column sections: "Impressions", "Clicks", "Position"
    # and collect the numeric values that follow each header
    section = None
    for line in lines:
        line_lower = line.lower()

        # Detect column headers (but skip the top-level summary ones we already handled)
        if line_lower == "impressions":
            section = "impressions"
            continue
        elif "clicks" in line_lower and "position" in line_lower:
            # Combined "Clicks Position" header
            section = "clicks_and_positions"
            continue
        elif line_lower in ("clicks", "click"):
            section = "clicks"
            continue
        elif line_lower in ("position", "avg position"):
            section = "positions"
            continue
        elif line_lower in ("search term", "search terms"):
            section = "terms"
            continue
        # Stop collecting if we hit a different section
        elif any(kw in line_lower for kw in ["conversion", "total", "revenue", "avg order"]):
            section = None
            continue

        if section and section != "terms":
            # Try to parse numbers — may have multiple numbers on one line (e.g., "486 4.2")
            nums = re.findall(r"[\d,]+\.?\d*", line)
            if section == "impressions":
                # Only collect up to the number of terms we found
                for n in nums:
                    if len(impressions) >= len(terms):
                        break
                    val = parse_number(n)
                    if val is not None:
                        impressions.append(val)
            elif section in ("clicks", "clicks_and_positions"):
                # Lines like "486 4.2" contain clicks and position
                if len(nums) >= 2:
                    val = parse_number(nums[0])
                    if val is not None:
                        clicks.append(val)
                    val = parse_number(nums[1])
                    if val is not None:
                        positions.append(val)
                elif len(nums) == 1:
                    val = parse_number(nums[0])
                    if val is not None:
                        clicks.append(val)
            elif section == "positions":
                for n in nums:
                    val = parse_number(n)
                    if val is not None:
                        positions.append(val)

    # Merge columns into term entries
    count = max(len(terms), len(impressions), len(clicks), len(positions)) if terms else 0
    for i in range(count):
        entry = {}
        if i < len(terms):
            entry["term"] = terms[i]
        if i < len(impressions):
            entry["impressions"] = impressions[i]
        if i < len(clicks):
            entry["clicks"] = clicks[i]
        if i < len(positions):
            entry["position"] = positions[i]
        if entry:
            data["terms"].append(entry)

    # Clean up None values from metrics
    data["metrics"] = {k: v for k, v in data["metrics"].items() if v is not None}

    return data


def extract_conversion_breakdown(text):
    """Extract conversion breakdown data from an Etsy screenshot.

    OCR typically renders as value-then-label pairs:
        6,542
        Total views
        4,328
        Total visits
        709
        Total favorites
        87
        Total orders
        2.01%
        Conversion rate
        $32.73
        Avg order value
    """
    data = {"type": "conversion_breakdown", "metrics": {}}

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Map label keywords to canonical metric names
    label_map = {
        "total views": "views",
        "total visits": "visits",
        "total favorites": "favorites",
        "total favourites": "favorites",
        "total orders": "orders",
        "conversion rate": "conversion_rate",
        "avg order value": "avg_order_value",
        "average order value": "avg_order_value",
    }

    for i, line in enumerate(lines):
        line_lower = line.lower()
        for keyword, metric_name in label_map.items():
            if keyword in line_lower and i > 0:
                prev = lines[i - 1].strip()
                is_percent = "%" in prev
                is_dollar = "$" in prev
                raw = re.sub(r"[^\d,.]", "", prev)
                val = parse_number(raw)
                if val is not None:
                    if is_percent:
                        data["metrics"][metric_name] = val
                    elif is_dollar:
                        data["metrics"][metric_name] = val
                    else:
                        data["metrics"][metric_name] = val
                break

    # Also try the label-value row approach for inline layouts
    row_metrics = extract_label_value_rows(text)
    for k, v in row_metrics.items():
        if k not in data["metrics"]:
            data["metrics"][k] = v

    return data


def extract_shop_page(text):
    """Extract data from an Etsy public shop page screenshot.

    Captures:
    - Shop header: name, star rating, review count, sales, admirers, age, location
    - Category sections with counts
    - Listing cards: title, sale price, original price, sale %, free shipping, bestseller
    """
    data = {
        "type": "shop_page",
        "shop": {},
        "listings": [],
        "categories": [],
    }

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    full_text = " ".join(lines).lower()

    # --- Shop header ---

    # Star rating + review count: "5.0 (1)" or "★ 4.8 (123)" or "ye 5.0 (1)"
    star_rev = re.search(r"(\d\.\d)\s*\((\d[\d,]*)\)", text)
    if star_rev:
        data["shop"]["star_rating"] = float(star_rev.group(1))
        data["shop"]["review_count"] = parse_number(star_rev.group(2))

    # Also check "123 reviews" pattern
    if "review_count" not in data["shop"]:
        rev_match = re.search(r"(\d[\d,]*)\s*reviews?", full_text)
        if rev_match:
            data["shop"]["review_count"] = parse_number(rev_match.group(1))

    # Sales: "1sale" or "1,234 sales" or "1 Sale"
    sales_match = re.search(r"(\d[\d,]*)\s*sales?", full_text)
    if sales_match:
        data["shop"]["total_sales"] = parse_number(sales_match.group(1))

    # Admirers: "4 Admirers" or "112 admirers"
    adm_match = re.search(r"(\d[\d,]*)\s*admirers?", full_text)
    if adm_match:
        data["shop"]["admirers"] = parse_number(adm_match.group(1))

    # Item count: "All 8" or "136 items" or "Search all 8 items"
    items_match = re.search(r"(?:all\s+)?(\d[\d,]*)\s*(?:items?|results?|listings?)", full_text)
    if items_match:
        data["shop"]["item_count"] = parse_number(items_match.group(1))

    # Shop age: "8 months on Etsy" or "3 years on Etsy"
    age_match = re.search(r"(\d+)\s*(months?|years?)\s*on\s*etsy", full_text)
    if age_match:
        data["shop"]["age_on_etsy"] = f"{age_match.group(1)} {age_match.group(2)}"

    # Location: look for "City, Country" or "City, State" pattern in first 10 lines
    for line in lines[:10]:
        loc_match = re.match(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)*),\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)$", line.strip())
        if loc_match and "location" not in data["shop"]:
            data["shop"]["location"] = line.strip()

    # Star Seller badge
    if "star seller" in full_text:
        data["shop"]["star_seller"] = True

    # --- Category sections ---
    # Pattern: "Pet Portraits 1" or "Sculptures 3"
    # These appear between "All X" and the first listing
    category_pattern = re.findall(
        r"^([A-Z][A-Za-z/]+(?:\s[A-Za-z/]+)*)\s+(\d+)$",
        text, re.MULTILINE
    )
    skip_labels = {"all", "on sale", "items", "reviews", "about", "shop policies",
                   "sort", "search", "custom", "report"}
    for name, count in category_pattern:
        name_lower = name.lower()
        if name_lower not in skip_labels and len(name) > 2:
            data["categories"].append({
                "name": name,
                "count": int(count),
            })

    # --- Listing cards ---
    # Find all price lines. Etsy shows: "$111.25 $430.87 (15% off)"
    # First price = sale/current price, second = original, percentage = discount
    price_lines = []
    for i, line in enumerate(lines):
        # Match lines containing at least one dollar amount
        prices_in_line = re.findall(r"\$\s*([\d,]+\.?\d*)", line)
        if prices_in_line:
            price_lines.append((i, prices_in_line, line))

    # Deduplicate: some price lines are just the second price on a previous listing
    # Group prices that are on the same line
    seen_indices = set()

    for pi, (price_idx, prices, price_line) in enumerate(price_lines):
        if price_idx in seen_indices:
            continue
        seen_indices.add(price_idx)

        if not prices:
            continue

        sale_price = parse_number(prices[0])
        if sale_price is None or sale_price <= 0:
            continue

        listing = {"price": sale_price}

        # Original price (second dollar amount on the same line)
        if len(prices) >= 2:
            orig = parse_number(prices[1])
            if orig and orig > sale_price:
                listing["original_price"] = orig
                listing["on_sale"] = True

        # Sale percentage: "(15% off)" or "15% off"
        pct_match = re.search(r"\((\d+)%\s*off\)", price_line)
        if pct_match:
            listing["sale_percentage"] = int(pct_match.group(1))
            listing["on_sale"] = True

        # FREE shipping — check same line, next line, and line after that
        search_range = price_line.lower()
        for offset in [1, 2]:
            if price_idx + offset < len(lines):
                search_range += " " + lines[price_idx + offset].lower()
        if "free" in search_range and "shipping" in search_range:
            listing["free_shipping"] = True

        # Bestseller
        nearby = " ".join(lines[max(0, price_idx - 2):min(len(lines), price_idx + 3)]).lower()
        if "bestseller" in nearby or "best seller" in nearby:
            listing["bestseller"] = True

        # "In cart" demand signal: "4 people have this in their cart" / "Over 20 people..."
        cart_match = re.search(r"(?:over\s+)?(\d+)\s*people\s*have\s*this\s*in\s*their\s*cart", nearby)
        if cart_match:
            listing["in_cart"] = int(cart_match.group(1))

        # Title — look backwards for nearest text that looks like a listing title
        title = None
        for j in range(price_idx - 1, max(-1, price_idx - 6), -1):
            if j < 0:
                break
            candidate = lines[j].strip()

            # Skip price lines, short text, known UI elements
            if re.search(r"^\$", candidate):
                continue
            if len(candidate) < 8:
                continue
            skip_words = {"free shipping", "bestseller", "best seller", "star seller",
                          "ad", "ads", "request custom order", "contact shop owner",
                          "report this shop", "search all", "sort:", "hand-made"}
            if candidate.lower() in skip_words or any(candidate.lower().startswith(s) for s in skip_words):
                continue
            # Skip category lines (single word + number)
            if re.match(r"^[A-Za-z/\s]+\d+$", candidate) and len(candidate) < 25:
                continue

            # Skip if this line is closer to the previous price
            if pi > 0 and j <= price_lines[pi - 1][0]:
                break

            # Clean OCR artifacts from start
            clean = re.sub(r"^[^A-Za-z]*", "", candidate).strip()
            if clean and len(clean) >= 8:
                title = clean
                break

        if title:
            listing["title"] = title

        data["listings"].append(listing)

    # Remove duplicate listings (same price + same title)
    seen = set()
    unique_listings = []
    for l in data["listings"]:
        key = (l.get("title", ""), l.get("price", 0))
        if key not in seen:
            seen.add(key)
            unique_listings.append(l)
    data["listings"] = unique_listings

    return data


def detect_screenshot_type(text):
    """Auto-detect what type of Etsy screenshot this is."""
    text_lower = text.lower()

    conversion_signals = ["conversion breakdown", "total views", "total visits", "total favorites", "avg order value"]
    search_signals = ["search visibility", "impressions", "click rate", "search term", "position"]
    listing_signals = ["listing stats", "listing views", "per listing", "active listings"]
    shop_dashboard_signals = ["shop stats", "how you're doing"]
    shop_page_signals = ["sales", "reviews", "admirers", "items", "star seller", "free shipping"]

    conversion_score = sum(1 for s in conversion_signals if s in text_lower)
    search_score = sum(1 for s in search_signals if s in text_lower)
    listing_score = sum(1 for s in listing_signals if s in text_lower)
    shop_dash_score = sum(1 for s in shop_dashboard_signals if s in text_lower)
    shop_page_score = sum(1 for s in shop_page_signals if s in text_lower)

    # Count dollar-sign prices — shop pages have many listing prices
    price_count = len(re.findall(r"\$\d", text))
    if price_count >= 3:
        shop_page_score += 2

    best = max(conversion_score, search_score, listing_score, shop_dash_score, shop_page_score)
    if best == 0:
        return "shop_page"  # default to shop page if nothing matches
    if conversion_score == best:
        return "conversion_breakdown"
    if search_score == best:
        return "search_visibility"
    if listing_score == best:
        return "listing_stats"
    if shop_dash_score >= shop_page_score:
        return "shop_stats"
    return "shop_page"


def extract_from_screenshot(image_path, screenshot_type=None):
    """Main extraction function. Takes an image path, returns structured data."""
    text = extract_text(image_path)

    if screenshot_type is None:
        screenshot_type = detect_screenshot_type(text)

    extractors = {
        "shop_stats": extract_shop_stats,
        "listing_stats": extract_listing_stats,
        "search_visibility": extract_search_visibility,
        "conversion_breakdown": extract_conversion_breakdown,
        "shop_page": extract_shop_page,
    }

    extractor = extractors.get(screenshot_type, extract_shop_stats)
    result = extractor(text)
    result["source_file"] = str(image_path)
    result["raw_text"] = text

    return result


def process_path(path, screenshot_type=None):
    """Process a single image or all images in a folder."""
    path = Path(path)
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

    if path.is_file():
        return [extract_from_screenshot(path, screenshot_type)]

    if path.is_dir():
        results = []
        for file in sorted(path.iterdir()):
            if file.suffix.lower() in image_extensions:
                print(f"Processing: {file.name}", file=sys.stderr)
                results.append(extract_from_screenshot(file, screenshot_type))
        return results

    print(f"Error: {path} is not a valid file or directory", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target_path = os.path.expanduser(sys.argv[1])
    forced_type = None

    if "--type" in sys.argv:
        type_idx = sys.argv.index("--type") + 1
        if type_idx < len(sys.argv):
            forced_type = sys.argv[type_idx]

    results = process_path(target_path, forced_type)
    print(json.dumps(results, indent=2))
