# ShopPulse — Weekly Action Plans for Etsy Sellers

## Project summary

ShopPulse tells existing Etsy sellers what to fix this week, ranked by impact, tracks whether changes helped, and learns from outcomes. It combines three proven feature categories that don't exist for Etsy: profit analytics, store health diagnostics, and competitive pricing intelligence.

## Current state

- Phase: Phase 0 — manual validation with design partners
- Landing page: Netlify (needs URL rename from auto-generated slug)
- Etsy API: BANNED first attempt (bad URL). Resubmit with clean URL. Do NOT mention AI/ML
- Scoring engine: `scorer.py` v0.1 — working, tested
- Report generator: `report.py` v0.3 — working, tested, personalized HTML output
- Design partners: 0 recruited. Facebook failed. Reddit ongoing
- Founder: Mac, Python basics, learning to build

## Files

```
shoppulse-engine/
├── CLAUDE.md        ← this file (project context, read every session)
├── scorer.py        ← gap scoring engine (working)
├── report.py        ← HTML report generator (working)
└── website/
    └── index.html   ← landing page (deployed on Netlify)
```

## Commands

```bash
python3 scorer.py              # runs example diagnosis, outputs diagnosis_result.json
python3 report.py              # reads diagnosis_result.json, outputs report_shopname.html
python3 report.py input.json   # custom input
python3 report.py input.json output.html  # custom input and output
```

---

## Tech stack

- Python 3 (no external deps for scorer — keep it simple)
- HTML/CSS/JS (single-file reports, inline everything)
- JSON for data interchange between scorer and report generator
- Future: Chrome extension (WXT + TypeScript), FastAPI backend, PostgreSQL, Stripe

---

## CRITICAL: Etsy API restrictions

### AI/ML prohibition
Etsy API Terms ban using API data for "analytics, machine learning, training AI models" without written authorization. In March 2025, an app called "Optimsy" was rejected for this exact use case.

### Our architecture navigates this
The scoring engine is DETERMINISTIC PYTHON CODE with rule-based checks and hardcoded thresholds. No AI decides what gaps exist. The LLM layer (added later) only writes plain-language explanations of what the code already determined.

### When resubmitting Etsy developer app
- Name: ShopPulse
- Description: "ShopPulse is a seller tool that helps existing Etsy sellers manage and optimize their listings. It connects via OAuth to read the seller's own shop and listing data, compares listings against competitive benchmarks, identifies areas for improvement, and produces a ranked list of recommended changes. It does not scrape Etsy pages or access data beyond what the seller authorizes."
- Type: Seller Tools
- Users: Just myself or colleagues (Personal Access, up to 5 shops)
- NEVER mention: AI, LLM, machine learning, ChatGPT, analytics, or data mining

### API doesn't have the data we need anyway
Etsy API v3 provides: listing management (titles, tags, prices, photos), order/receipt data.
Etsy API v3 LACKS: views, visits, conversion rates, traffic sources, search rankings, Etsy Ads performance.
The diagnostic data lives in the seller's dashboard, not the API.

### Data collection architecture (priority order)
1. Chrome extension reading seller's logged-in dashboard (Phase 1 primary)
2. Manual screenshot/CSV upload (Phase 0 now, permanent fallback)
3. Etsy OAuth API (supplementary, if approved — listing metadata only)

Architecture treats data source as a SWAPPABLE LAYER. Scorer takes structured JSON regardless of source.

---

## Architecture: deterministic scoring + LLM explanation

Two layers in sequence:

### Layer 1: Gap Scoring Engine (Python, deterministic, NO AI)
Input: listing data + niche benchmarks → Output: structured gap flags with severity scores

### Layer 2: LLM Explanation Layer (added later)
Input: gap flags + listing context → Output: plain-language explanations, specific recommended actions

AI does NOT decide what gaps exist. Code does that. AI only explains.

---

## Diagnostic escalation ladder

This is the core product logic. When fixes at one layer don't produce results, the system escalates to the next layer. Most tools only operate at Layer 1. ShopPulse goes through all five.

### Layer 1: Listing content fixes (easy wins, 7-14 day signal)
- Photo count vs niche avg (flag if < 5 or below niche)
- Title structure: product-type-first, under 15 words per Etsy Feb 2026 guidance
- Description length (flag if < 50 words)
- Video presence (Etsy gives ranking boost)
- All 13 tag slots filled
- Tag alignment with Etsy autocomplete suggestions
- IF NO IMPROVEMENT AFTER 2-3 WEEKS → escalate to Layer 2

### Layer 2: Conversion optimization (moderate effort, 7-14 day signal)
- Price vs niche median (flag if >30% deviation)
- Free shipping check (flag if competitors offer it and seller doesn't — affects ranking)
- Permanent sales (flag — signals desperation)
- Favorites-to-orders ratio vs shop average
- Review count vs niche competitors
- Shop policies completeness
- Processing time (flag if >7 days)
- IF NO IMPROVEMENT AFTER 3-4 WEEKS → escalate to Layer 3

### Layer 3: Competitive positioning (strategic, 1-2 month signal)
- Niche listing count (flag if >100K — extremely saturated)
- Top-10 review avg vs seller's reviews (flag if >20x gap)
- Niche spread (flag if shop competes in >5 niches with 2-3 listings each)
- Clear differentiator assessment
- IF NO IMPROVEMENT AFTER 1-2 MONTHS → escalate to Layer 4

### Layer 4: Product-market fit (hard question, 1-3 month assessment)
- Etsy autocomplete demand signals for product type
- Google Trends direction (growing/declining/flat)
- Seasonal patterns
- Whether niche is structurally viable given seller's cost structure
- Adjacent niche recommendations based on seller's existing strengths
- IF STILL NO IMPROVEMENT → escalate to Layer 5

### Layer 5: Beyond ShopPulse's scope (transparent limit)
- Platform-level forces (Etsy marketplace declining)
- Business model issues
- Recommend: diversify to other platforms, build direct traffic, adjust product line
- This honesty IS a feature — builds trust and referrals

---

## Six gap types scored by the engine

Each gap produces a severity score (0-10). Priority Score = Gap Severity × Listing Importance.

### 1. Visibility gap
```
Checks:
- monthly_views < niche_avg * 0.3 → severity +3
- monthly_views < niche_avg * 0.6 → severity +1
- tag_count < 13 → severity +2
- tags_matching_autocomplete < tag_count * 0.5 → severity +2
Data needed: monthly_views, tag_count, tags_matching_autocomplete
Niche data: avg_monthly_views
```

### 2. Conversion gap
```
Checks:
- monthly_views < 20 → skip (not enough data, focus on visibility first)
- conversion_rate < shop_avg * 0.5 AND monthly_views >= 50 → severity +3
- favorites > 10 AND orders == 0 → severity +3
- favorites > orders * 10 → severity +2
Data needed: monthly_views, monthly_orders, monthly_favorites
Shop data: avg_conversion_rate
```

### 3. Pricing gap
```
Checks:
- price deviation > -30% from niche median → severity +3 (too cheap)
- price deviation > +40% AND reviews < 20 → severity +3 (too expensive without trust)
- on_sale permanently → severity +2
- no free_shipping AND niche pct_free_shipping > 60% → severity +2
Data needed: price, on_sale, sale_percentage, free_shipping
Niche data: median_price, pct_free_shipping
```

### 4. Trust gap
```
Checks:
- review_count == 0 → severity +3
- review_count < 10 AND niche avg > 50 → severity +2
- missing About section → severity +1
- incomplete shop policies → severity +2
- processing_days > 7 → severity +2
Data needed: review_count
Shop data: has_about_section, has_shop_policies, avg_processing_days
Niche data: avg_reviews
```

### 5. Content gap
```
Checks:
- photo_count < 3 → severity +3
- photo_count < niche avg → severity +1
- no video → severity +1
- description < 50 words → severity +2
- description < 100 words → severity +1
- title > 15 words → severity +2
- title starts with brand name → severity +2
Data needed: photo_count, has_video, description_word_count, title, brand_name
Niche data: avg_photos
```

### 6. Competitiveness gap
```
Checks:
- niche total_listings > 100,000 → severity +3
- niche total_listings > 50,000 → severity +1
- review_count < niche top_10_avg * 0.05 → severity +2
- shop competes in > 5 niches → severity +2
Data needed: review_count, shop_niche_count
Niche data: total_listings, top_10_avg_reviews
```

---

## Profit analytics feature (HIGH PRIORITY — add to scorer)

This is the single highest-retention feature across all e-commerce platforms. SellerBoard ($19-79/mo) has 4.9/5 rating. TrueProfit has 70K+ installs. NO good equivalent exists for Etsy.

### Why it matters for Etsy specifically
Etsy has 5-7 layered fee types that sellers consistently miscalculate:
- $0.20 listing fee per item
- 6.5% transaction fee
- ~3% payment processing fee
- 15% Offsite Ads fee (mandatory for sellers >$10K/year revenue)
- Optional Etsy Ads spend
- $0.20 auto-renew fee when item sells

On a $30 item, Etsy takes $3-4 in base fees. With Offsite Ads: $3.60-4.50 additional.

### Data model for profit tracking
```python
class ListingProfit:
    sale_price: float        # what buyer pays
    shipping_charged: float  # shipping charged to buyer
    quantity: int

    # Etsy fees (calculated automatically)
    listing_fee: float       # $0.20 per listing
    transaction_fee: float   # 6.5% of (sale_price + shipping_charged)
    processing_fee: float    # ~3% + $0.25 of total
    offsite_ads_fee: float   # 12-15% of sale_price (if triggered)
    etsy_ads_cost: float     # optional, seller-set daily budget

    # Seller costs (entered by seller)
    materials_cost: float    # COGS
    labor_hours: float       # optional
    labor_rate: float        # optional, default from settings
    packaging_cost: float
    shipping_actual: float   # actual shipping cost paid

    # Calculated
    @property
    def total_fees(self):
        return (self.listing_fee + self.transaction_fee +
                self.processing_fee + self.offsite_ads_fee +
                self.etsy_ads_cost)

    @property
    def total_costs(self):
        return (self.materials_cost +
                self.labor_hours * self.labor_rate +
                self.packaging_cost + self.shipping_actual)

    @property
    def net_profit(self):
        return (self.sale_price + self.shipping_charged -
                self.total_fees - self.total_costs)

    @property
    def profit_margin(self):
        revenue = self.sale_price + self.shipping_charged
        return (self.net_profit / revenue * 100) if revenue > 0 else 0
```

### Etsy fee calculator logic
```python
def calculate_etsy_fees(sale_price, shipping_charged, offsite_ads_triggered=False):
    listing_fee = 0.20
    transaction_fee = (sale_price + shipping_charged) * 0.065
    processing_fee = (sale_price + shipping_charged) * 0.03 + 0.25
    offsite_ads_fee = sale_price * 0.15 if offsite_ads_triggered else 0

    total = listing_fee + transaction_fee + processing_fee + offsite_ads_fee
    return {
        "listing_fee": round(listing_fee, 2),
        "transaction_fee": round(transaction_fee, 2),
        "processing_fee": round(processing_fee, 2),
        "offsite_ads_fee": round(offsite_ads_fee, 2),
        "total_fees": round(total, 2),
        "effective_fee_rate": round(total / sale_price * 100, 1)
    }
```

---

## Competitive pricing intelligence (add to scorer)

Zero dedicated pricing tools exist for Etsy. Etsy launched a basic beta but it covers limited items.

### What to build
```python
class NichePriceAnalysis:
    keyword: str
    seller_price: float
    niche_median: float
    niche_25th_percentile: float
    niche_75th_percentile: float
    seller_review_count: int
    niche_avg_reviews: int

    @property
    def price_position(self):
        """Where seller sits: budget / competitive / premium / overpriced"""
        deviation = (self.seller_price - self.niche_median) / self.niche_median
        if deviation < -0.25:
            return "budget"  # may signal low quality
        elif deviation < 0.10:
            return "competitive"  # sweet spot
        elif deviation < 0.35 and self.seller_review_count > 20:
            return "premium"  # justified by trust
        elif deviation >= 0.35:
            return "overpriced"  # needs more reviews to justify
        return "competitive"

    @property
    def recommended_range(self):
        """Price range where seller should compete"""
        if self.seller_review_count < 10:
            return (self.niche_25th_percentile, self.niche_median)
        elif self.seller_review_count < 50:
            return (self.niche_median * 0.9, self.niche_75th_percentile)
        else:
            return (self.niche_median, self.niche_75th_percentile * 1.1)
```

---

## Outcome tracking data model (Phase 2)

```python
class Recommendation:
    id: str
    shop_id: str
    listing_id: str
    gap_type: str            # visibility/conversion/pricing/trust/content/competitive
    escalation_layer: int    # 1-5
    action_description: str
    expected_impact: str     # high/medium/low
    confidence: str          # high/medium/low
    created_date: datetime

class OutcomeRecord:
    recommendation_id: str
    seller_response: str     # accepted/snoozed/dismissed
    was_implemented: bool
    implementation_date: datetime

    # Before metrics (captured at recommendation time)
    pre_views_14d: int
    pre_orders_14d: int
    pre_favorites_14d: int
    pre_conversion_rate: float

    # After metrics (captured 14 days post-implementation)
    post_views_14d: int
    post_orders_14d: int
    post_favorites_14d: int
    post_conversion_rate: float

    # Outcome
    outcome_label: str       # helped/no_clear_evidence/inconclusive/hurt
    seller_feedback: str     # thumbs_up/thumbs_down/not_sure

    @property
    def views_change_pct(self):
        if self.pre_views_14d == 0: return None
        return ((self.post_views_14d - self.pre_views_14d) / self.pre_views_14d) * 100

class SellerPriors:
    """Accumulated learning about what works for this specific seller"""
    shop_id: str
    total_recommendations: int
    total_acted_on: int

    # Per gap type: success rate
    gap_type_outcomes: dict   # {"content": {"helped": 3, "no_evidence": 1, "hurt": 0}, ...}

    # Per action type: what moves the needle
    title_changes_success_rate: float
    price_changes_success_rate: float
    photo_additions_success_rate: float
    tag_changes_success_rate: float

    # Niche-specific patterns
    responsive_niches: list   # niches where optimization consistently helps
    unresponsive_niches: list # niches where nothing moves
```

---

## Report output specification

Every generated report MUST include:

### Shop overview section
- Shop name, URL, analysis date
- Health score (0-100, computed from total gap severity)
- Stats: listings analyzed, monthly views, monthly orders, conversion rate
- Personalized narrative summary (2-3 sentences referencing actual numbers)

### Gap overview section
- 6 gap cards in grid layout
- Each card: gap name, colored severity dot, issue count, one-line description, proportional bar

### Callout card
- Highlight highest-traffic listing by name
- Explain why improvements there have the largest impact

### Action plan section (3 ranked actions)
Each action card MUST include:
- Action number with timeline connector between cards
- Gap type badge (colored)
- Difficulty badge (quick fix / moderate effort / requires testing / strategic move)
- Listing title (linked to Etsy)
- Priority score
- "Why this is ranked here" paragraph (personalized, references specific data)
- "What to focus on" paragraph (conversational, gap-type-specific)
- "Specific issues found" bullet list
- "If this doesn't work" escalation note (what to check next)

### CTA sections
- Inline CTA: invite to share private data for deeper analysis
- Bottom CTA: join waitlist for automated weekly plans
- Both reference shop name for personalization

### Methodology section
- Three-step explanation: detect gaps → rank by impact → track outcomes
- Note: "Where confidence is low, we say so"

### Closing paragraph
- Personalized based on how many quick fixes are available and health score
- Sets expectations: experimentation, not guaranteed growth

---

## Proven features from other platforms to incorporate

### From SellerBoard (Amazon, $19-79/mo, 4.9★, 10K+ sellers)
- Real-time profit dashboard showing net profit after ALL fees per listing per day
- "Money Back" feature identifying reimbursement opportunities
- Adapt for Etsy: fee calculator + COGS tracking + daily profit view

### From TrueProfit (Shopify, $25-149/mo, 70K+ installs)
- Broadest ad platform coverage, mobile app
- LTV cohort analysis
- Adapt for Etsy: track Etsy Ads spend + Offsite Ads costs per listing

### From Shopify Sidekick Pulse (free, built-in)
- Proactive AI recommendations surfaced without user asking
- Up to 5 tailored recommendations with citations
- Creates actionable to-do lists
- Adapt for Etsy: the Action Feed is our version of this

### From Glowtify (Shopify, $3.4M seed, $1,999/mo)
- Scoring dashboard with prioritized recommendations
- Learns merchant's "Business DNA"
- No-prompt AI content generation
- Adapt for Etsy: store health score + gap scoring is our affordable version

### From Intelligems (Shopify, $79-999/mo, 96% YoY growth)
- True A/B testing for prices, content, shipping thresholds
- Statistical significance tracking
- Adapt for Etsy: time-based A/B testing (change, measure 14 days, compare) since Etsy doesn't support simultaneous split tests

### From Judge.me (Shopify, free-$15/mo, on 19.3% of ALL Shopify stores)
- Automated review request sequences
- Review analytics dashboard
- Adapt for Etsy: review velocity tracking + reminder to follow up with buyers + negative review alerts

### From SellerBoard/Fetcher (Amazon, profit analytics)
- Per-product, per-day profitability view
- Automated fee tracking across all fee types
- Adapt for Etsy: the most painful gap — sellers don't know their true margins

---

## Competitive landscape (reference only)

| Tool | Users | Price | What they do | What they DON'T do |
|------|-------|-------|-------------|-------------------|
| EverBee | 900K | $29.99-99 | Product research, sales estimates | No prioritized actions, no outcome tracking, no profit analytics |
| eRank | 1M+ | $5.99-29.99 | Keywords, listing audit, change tracking | No prioritization, no learning loop, no profit analytics |
| Alura | 848K | $7.99-69.99 | Research, A/B testing, Pinterest automation | No store health score, no escalation logic, no profit analytics |
| RankHero | claims 500K | $5.99-29.99 | A-F listing grades, generators | No prioritization, no tracking, no profit analytics, no extension |
| Marmalead | 325K | $19 | Keywords, Marma AI chatbot | No store health, no tracking, no profit analytics |
| ProfitTree | claims 80K | free-paid | Basic profit tracking | Mixed reviews, accuracy issues, not real-time |
| Etsy native | all sellers | free/$10 | Stats, Search Visibility, Marketplace Insights | No health score, no actions, no AI diagnostics, no profit dashboard |

Gap: NO tool combines profit analytics + diagnostic escalation + outcome tracking + seller-specific learning.

---

## Pricing strategy

| Tier | Price | Includes |
|------|-------|---------|
| Free | $0 | Sample diagnosis (5 listings), fee calculator, one-time report |
| Standard | $14.99/mo | Full diagnosis, weekly action feed, profit tracking, outcome monitoring |
| Pro (later) | $29.99/mo | Seller-specific memory, A/B testing framework, competitive alerts, priority support |

Revenue math: ~5,560 subscribers at $14.99 for $1M ARR. Realistic: 3-4 years.
Break-even (~$5K MRR): ~334 subscribers. Realistic: 12-18 months.

---

## ICP

- Existing Etsy sellers, 50-300 active listings
- Already paying for at least one tool
- Enough traffic to diagnose (not zero-visibility)
- Frustrated by "what to do next" not "what to sell"
- NOT beginners, NOT casual hobbyists
- 88% of Etsy sellers are solo operators, 83% self-taught

---

## Build sequence

### NOW: Phase 0 — manual validation
- [ ] Fix Netlify URL → resubmit Etsy developer app
- [ ] Recruit 5-10 design partners (use reports as recruitment hook)
- [ ] Run scorer on real shops, generate personalized reports
- [ ] 14-day action sprints: recommend → seller acts → measure → learn
- [ ] Test pricing question with every partner

### NEXT: Add profit calculator to scorer
- [ ] Build Etsy fee calculator (all 5-7 fee types)
- [ ] Add COGS/labor input fields
- [ ] Show per-listing net profit in reports
- [ ] This alone may be enough to recruit design partners ("see your REAL profit")

### Phase 1: Chrome extension + web app
- [ ] Extension reads seller's Stats dashboard + public search pages
- [ ] Manual upload as fallback
- [ ] Web app: shop diagnosis, action feed, listing workbench, profit dashboard
- [ ] Stripe integration

### Phase 2: Outcome tracking + seller memory
- [ ] Before/after metrics from extension re-sync
- [ ] One-click feedback (thumbs up/down)
- [ ] Seller-specific priors computed from accumulated outcomes
- [ ] Escalation logic: auto-suggest next layer when current layer isn't working

### Phase 3: Advanced features
- [ ] Niche Reality Check (go/watch/skip)
- [ ] A/B testing framework (time-based variant testing)
- [ ] Competitive pricing intelligence
- [ ] AI shopping optimization (ChatGPT/Gemini discovery signals)
- [ ] Pro tier launch

---

## Phase 0 success criteria

- [ ] 3 of 5 sellers say diagnosis surfaced something non-obvious
- [ ] 1 of 5 acts on a recommendation within 14 days
- [ ] 1 of 5 says they'd pay for this
- [ ] 1 of 5 wants the next cycle
- [ ] Know realistic price point from direct seller answers
- [ ] Know what Etsy API data is available vs needs screenshots

---

## Key risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Etsy API AI/ML ban | CRITICAL | Rule-based framing. Extension as primary. Never mention AI to Etsy |
| Screen-scraping TOS | HIGH | User-initiated sync only. Manual upload fallback |
| Revenue at small scale | HIGH | Profit analytics feature has near-zero churn on other platforms |
| 20+ competitors | HIGH | None combine profit + diagnosis + tracking + learning |
| AI agents commoditize advice | MEDIUM | Outcome data is proprietary. Profit calc is AI-resistant |
| Attribution uncertainty | MEDIUM | Outcome labels: helped / no evidence / inconclusive / hurt |
| Price sensitivity | MEDIUM | $14.99 anchored to proven SellerBoard/eRank range |

---

## Coding conventions

- Python 3, no external dependencies for scorer
- JSON for data interchange
- HTML reports: single-file, inline CSS/JS, shareable as attachment
- Every recommendation includes: listing ref, gap type, specific action, evidence, impact level, confidence level, escalation path
- Never mention AI/ML in Etsy-facing code, descriptions, or API calls
- Outcome labels: helped / no clear evidence / inconclusive / hurt
- Round all displayed numbers (no float artifacts)
- Mobile-responsive reports (test at 375px width)

## AI disruption notes

- ChatGPT Shopping + Etsy Instant Checkout already live (Sep 2025)
- Some sellers see 20%+ referral traffic from AI sources
- Position for "listing quality optimization" not "keyword SEO"
- Profit analytics is AI-resistant (requires structured seller cost data)
- Outcome database is the long-term moat — accumulate data fast
- Build for daily-use habit (profit check every morning) not occasional use
