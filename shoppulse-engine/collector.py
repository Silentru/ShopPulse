"""
ShopPulse Data Collector
Local web tool for entering Etsy shop data and generating diagnosis reports.

Usage:
    python3 collector.py
    Then open http://localhost:8765 in your browser.

Features:
- Enter shop-level info (name, reviews, sales)
- Add listings manually (title, price, photos, etc.)
- Upload screenshots for OCR extraction
- Generate diagnosis report with one click
"""

import http.server
import json
import os
import sys
import tempfile
import urllib.parse
import cgi
from pathlib import Path

PORT = 8765
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShopPulse — Data Collector</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #FAFAF8; --fg: #1A1A1A; --accent: #D35400; --accent-light: #FDF2E9;
    --muted: #6B7280; --light: #9CA3AF; --border: #E5E5E3; --green: #1B7A3D;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--fg); line-height: 1.6; }
  .page { max-width: 720px; margin: 0 auto; padding: 40px 24px 80px; }
  .logo { font-family: 'DM Serif Display', serif; font-size: 1rem; color: var(--light); margin-bottom: 32px; }
  .logo span { color: var(--accent); }
  h1 { font-family: 'DM Serif Display', serif; font-size: 1.8rem; font-weight: 400; margin-bottom: 8px; }
  h2 { font-family: 'DM Serif Display', serif; font-size: 1.2rem; font-weight: 400; margin: 32px 0 12px; }
  .sub { font-size: .85rem; color: var(--muted); margin-bottom: 24px; }
  .label { font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: var(--accent); margin-bottom: 8px; }

  /* Forms */
  .field { margin-bottom: 16px; }
  .field label { display: block; font-size: .82rem; font-weight: 600; margin-bottom: 4px; }
  .field .hint { font-size: .75rem; color: var(--muted); margin-bottom: 4px; }
  input[type="text"], input[type="number"], textarea, select {
    width: 100%; padding: 8px 12px; border: 1.5px solid var(--border); border-radius: 6px;
    font-family: inherit; font-size: .9rem; background: #fff;
  }
  input:focus, textarea:focus { outline: none; border-color: var(--accent); }
  textarea { min-height: 60px; resize: vertical; }
  .row { display: flex; gap: 12px; }
  .row .field { flex: 1; }
  .checkbox { display: flex; align-items: center; gap: 8px; font-size: .85rem; }
  .checkbox input { width: auto; }

  /* Buttons */
  .btn {
    display: inline-block; padding: 10px 20px; border: none; border-radius: 6px;
    font-family: inherit; font-size: .88rem; font-weight: 600; cursor: pointer;
  }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { opacity: .9; }
  .btn-secondary { background: #fff; color: var(--fg); border: 1.5px solid var(--border); }
  .btn-secondary:hover { background: var(--accent-light); }
  .btn-sm { padding: 6px 14px; font-size: .8rem; }
  .btn-danger { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }

  /* Listings */
  .listing-card {
    padding: 16px; margin-bottom: 12px; background: #fff;
    border: 1px solid var(--border); border-radius: 6px;
  }
  .listing-card .listing-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .listing-card .listing-title { font-weight: 600; font-size: .9rem; }
  .listing-card .listing-meta { font-size: .8rem; color: var(--muted); }
  .listing-count { font-size: .85rem; color: var(--muted); margin-bottom: 12px; }

  /* Upload area */
  .upload-area {
    border: 2px dashed var(--border); border-radius: 8px; padding: 32px;
    text-align: center; cursor: pointer; margin-bottom: 16px;
    transition: border-color .2s;
  }
  .upload-area:hover { border-color: var(--accent); }
  .upload-area.dragover { border-color: var(--accent); background: var(--accent-light); }
  .upload-area p { font-size: .85rem; color: var(--muted); }
  .upload-area input { display: none; }

  /* Status */
  .status { padding: 12px 16px; border-radius: 6px; margin: 16px 0; font-size: .85rem; }
  .status-success { background: #EEFBF3; border: 1px solid #C6F0D6; color: var(--green); }
  .status-error { background: #FEF2F2; border: 1px solid #FECACA; color: #991B1B; }
  .status-info { background: var(--accent-light); border: 1px solid #FBBF6E; color: var(--accent); }

  /* Divider */
  hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }

  /* Niche context */
  .niche-toggle { font-size: .82rem; color: var(--accent); cursor: pointer; border: none; background: none; font-family: inherit; padding: 0; }
  .niche-fields { display: none; margin-top: 12px; }
  .niche-fields.visible { display: block; }

  /* Actions bar */
  .actions-bar { display: flex; gap: 12px; margin-top: 24px; flex-wrap: wrap; }
</style>
</head>
<body>
<div class="page">
  <div class="logo">Shop<span>Pulse</span></div>
  <h1>Data Collector</h1>
  <p class="sub">Enter what you can see on the shop's public page. Leave fields blank if you don't have the data — the scorer handles missing data gracefully.</p>

  <div class="label">Shop info</div>
  <div class="row">
    <div class="field"><label>Shop name</label><input type="text" id="shop_name" placeholder="e.g. SattvaSoulIndia"></div>
    <div class="field"><label>Total reviews</label><input type="number" id="review_count" min="0" placeholder="0"></div>
  </div>
  <div class="row">
    <div class="field"><label>Total sales</label><input type="number" id="total_sales" min="0" placeholder="0"></div>
    <div class="field"><label>Admirers</label><input type="number" id="admirers" min="0" placeholder="0"></div>
  </div>
  <div class="row">
    <div class="field"><label>Processing days (avg)</label><input type="number" id="processing_days" min="0" placeholder="e.g. 7"></div>
    <div class="field">
      <label>Shop completeness</label>
      <div class="checkbox"><input type="checkbox" id="has_about" checked> Has About section</div>
      <div class="checkbox"><input type="checkbox" id="has_policies" checked> Has shop policies</div>
    </div>
  </div>

  <hr>

  <div class="label">Screenshot upload</div>
  <p class="sub" style="margin-bottom:12px">Upload screenshots from the shop's Etsy page. OCR will extract listing data automatically.</p>
  <div class="upload-area" id="upload-area">
    <p>Drop screenshots here or click to upload</p>
    <input type="file" id="file-input" accept="image/*" multiple>
  </div>
  <div id="upload-status"></div>

  <hr>

  <div style="display:flex;justify-content:space-between;align-items:center">
    <div class="label" style="margin:0">Listings</div>
    <button class="btn btn-secondary btn-sm" onclick="addListing()">+ Add listing</button>
  </div>
  <p class="listing-count" id="listing-count">0 listings</p>
  <div id="listings-container"></div>

  <hr>

  <div class="field" style="margin-bottom:16px">
    <label>Niche preset</label>
    <select id="niche_preset" style="width:100%;padding:8px 12px;border:1.5px solid var(--border);border-radius:6px;font-family:inherit;font-size:.9rem">
      <option value="default">General (default)</option>
      <option value="custom_art">Custom Art</option>
      <option value="custom_portraits">Custom Portraits</option>
      <option value="jewelry">Jewelry</option>
      <option value="handmade_gifts">Handmade Gifts</option>
      <option value="crystals">Crystals / Healing Stones</option>
    </select>
  </div>

  <button class="niche-toggle" onclick="toggleNiche()">Custom benchmarks (advanced — click to override)</button>
  <div class="niche-fields" id="niche-fields">
    <p class="sub">Override individual benchmarks if you know the seller's specific niche numbers.</p>
    <div class="row">
      <div class="field"><label>Median price</label><input type="number" id="niche_price" step="0.01" value="45.00"></div>
      <div class="field"><label>Median views/listing</label><input type="number" id="niche_views" value="150"></div>
    </div>
    <div class="row">
      <div class="field"><label>Median orders/listing</label><input type="number" id="niche_orders" value="5"></div>
      <div class="field"><label>Median conversion %</label><input type="number" id="niche_conv" step="0.1" value="3.0"></div>
    </div>
    <div class="row">
      <div class="field"><label>Median review count</label><input type="number" id="niche_reviews" value="800"></div>
      <div class="field"><label>Top 10 avg reviews</label><input type="number" id="niche_top10" value="15000"></div>
    </div>
    <div class="row">
      <div class="field"><label>Median photos</label><input type="number" id="niche_photos" value="7"></div>
      <div class="field"><label>Median description words</label><input type="number" id="niche_desc" value="200"></div>
    </div>
  </div>

  <hr>

  <div class="actions-bar">
    <button class="btn btn-primary" onclick="generateReport()">Generate report</button>
    <button class="btn btn-secondary" onclick="exportJSON()">Export JSON</button>
    <button class="btn btn-secondary" onclick="importJSON()">Import JSON</button>
    <input type="file" id="import-input" accept=".json" style="display:none" onchange="handleImport(event)">
  </div>
  <div id="report-status"></div>
</div>

<script>
let listings = [];
let listingId = 0;

function val(id) { return document.getElementById(id).value; }
function numVal(id) { const v = document.getElementById(id).value; return v === '' ? null : Number(v); }
function checked(id) { return document.getElementById(id).checked; }

function addListing(data) {
  const id = listingId++;
  const l = data || { title: '', price: null, views: null, favorites: null, orders: null, photo_count: null, has_video: false, description_words: null };
  listings.push({ id, ...l });
  renderListings();
  return id;
}

function removeListing(id) {
  listings = listings.filter(l => l.id !== id);
  renderListings();
}

function renderListings() {
  const container = document.getElementById('listings-container');
  document.getElementById('listing-count').textContent = listings.length + ' listing' + (listings.length !== 1 ? 's' : '');

  container.innerHTML = listings.map(l => `
    <div class="listing-card" data-id="${l.id}">
      <div class="listing-head">
        <span class="listing-title">${l.title || 'New listing'}</span>
        <button class="btn btn-danger btn-sm" onclick="removeListing(${l.id})">Remove</button>
      </div>
      <div class="field"><label>Title</label><input type="text" value="${esc(l.title || '')}" onchange="updateListing(${l.id}, 'title', this.value)" placeholder="Full listing title"></div>
      <div class="row">
        <div class="field"><label>Price ($)</label><input type="number" step="0.01" value="${l.price || ''}" onchange="updateListing(${l.id}, 'price', Number(this.value))"></div>
        <div class="field"><label>Views</label><input type="number" value="${l.views ?? ''}" onchange="updateListing(${l.id}, 'views', Number(this.value))"></div>
        <div class="field"><label>Favorites</label><input type="number" value="${l.favorites ?? ''}" onchange="updateListing(${l.id}, 'favorites', Number(this.value))"></div>
        <div class="field"><label>Orders</label><input type="number" value="${l.orders ?? ''}" onchange="updateListing(${l.id}, 'orders', Number(this.value))"></div>
      </div>
      <div class="row">
        <div class="field"><label>Photos</label><input type="number" value="${l.photo_count ?? ''}" onchange="updateListing(${l.id}, 'photo_count', Number(this.value))"></div>
        <div class="field"><label>Desc. words (est.)</label><input type="number" value="${l.description_words ?? ''}" onchange="updateListing(${l.id}, 'description_words', Number(this.value))"></div>
        <div class="field"><label>Has video?</label><select onchange="updateListing(${l.id}, 'has_video', this.value === 'true')">
          <option value="false" ${!l.has_video ? 'selected' : ''}>No</option>
          <option value="true" ${l.has_video ? 'selected' : ''}>Yes</option>
        </select></div>
      </div>
      <div class="row">
        <div class="field"><label>Materials cost ($)</label><input type="number" step="0.01" value="${l.materials_cost || ''}" onchange="updateListing(${l.id}, 'materials_cost', Number(this.value))"></div>
        <div class="field"><label>Packaging ($)</label><input type="number" step="0.01" value="${l.packaging_cost || ''}" onchange="updateListing(${l.id}, 'packaging_cost', Number(this.value))"></div>
        <div class="field"><label>Shipping actual ($)</label><input type="number" step="0.01" value="${l.shipping_actual || ''}" onchange="updateListing(${l.id}, 'shipping_actual', Number(this.value))"></div>
      </div>
    </div>
  `).join('');
}

function updateListing(id, key, value) {
  const l = listings.find(l => l.id === id);
  if (l) l[key] = value;
}

function esc(s) { return s.replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

function toggleNiche() {
  document.getElementById('niche-fields').classList.toggle('visible');
}

function buildData() {
  const shop = { name: val('shop_name') };
  const niche_preset = val('niche_preset');
  const rc = numVal('review_count'); if (rc !== null) shop.review_count = rc;
  const ts = numVal('total_sales'); if (ts !== null) shop.total_sales = ts;
  const ad = numVal('admirers'); if (ad !== null) shop.admirers = ad;
  const pd = numVal('processing_days'); if (pd !== null) shop.avg_processing_days = pd;
  shop.has_about_section = checked('has_about');
  shop.has_shop_policies = checked('has_policies');

  const cleanListings = listings.map(l => {
    const cl = {};
    if (l.title) cl.title = l.title;
    if (l.price) cl.price = l.price;
    if (l.views !== null && l.views !== undefined) cl.views = l.views;
    if (l.favorites !== null && l.favorites !== undefined) cl.favorites = l.favorites;
    if (l.orders !== null && l.orders !== undefined) cl.orders = l.orders;
    if (l.photo_count !== null && l.photo_count !== undefined) cl.photo_count = l.photo_count;
    if (l.has_video !== undefined) cl.has_video = l.has_video;
    if (l.description_words) cl.description_words = l.description_words;
    if (l.materials_cost) cl.materials_cost = l.materials_cost;
    if (l.packaging_cost) cl.packaging_cost = l.packaging_cost;
    if (l.shipping_actual) cl.shipping_actual = l.shipping_actual;
    return cl;
  });

  return {
    shop,
    niche_preset,
    listings: cleanListings,
    niche_context: {
      median_price: numVal('niche_price') || 45,
      median_views_per_listing: numVal('niche_views') || 150,
      median_orders_per_listing: numVal('niche_orders') || 5,
      median_conversion_rate: numVal('niche_conv') || 3.0,
      median_review_count: numVal('niche_reviews') || 800,
      top10_review_avg: numVal('niche_top10') || 15000,
      median_photo_count: numVal('niche_photos') || 7,
      median_description_words: numVal('niche_desc') || 200,
    }
  };
}

function exportJSON() {
  const data = buildData();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (val('shop_name') || 'shop') + '_data.json';
  a.click();
}

function importJSON() {
  document.getElementById('import-input').click();
}

function handleImport(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const data = JSON.parse(e.target.result);
      // Fill shop fields
      if (data.shop) {
        document.getElementById('shop_name').value = data.shop.name || '';
        document.getElementById('review_count').value = data.shop.review_count ?? '';
        document.getElementById('total_sales').value = data.shop.total_sales ?? '';
        document.getElementById('admirers').value = data.shop.admirers ?? '';
        document.getElementById('processing_days').value = data.shop.avg_processing_days ?? '';
        document.getElementById('has_about').checked = data.shop.has_about_section !== false;
        document.getElementById('has_policies').checked = data.shop.has_shop_policies !== false;
      }
      // Load listings
      listings = [];
      listingId = 0;
      if (data.listings) {
        data.listings.forEach(l => addListing(l));
      }
      showStatus('report-status', 'Imported ' + (data.listings || []).length + ' listings', 'success');
    } catch (err) {
      showStatus('report-status', 'Invalid JSON: ' + err.message, 'error');
    }
  };
  reader.readAsText(file);
}

async function generateReport() {
  const data = buildData();
  if (data.listings.length === 0) {
    showStatus('report-status', 'Add at least one listing before generating a report.', 'error');
    return;
  }
  showStatus('report-status', 'Generating report...', 'info');
  try {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await resp.json();
    if (result.error) {
      showStatus('report-status', 'Error: ' + result.error, 'error');
    } else {
      showStatus('report-status', 'Report generated: <a href="/report/' + result.filename + '" target="_blank">' + result.filename + '</a>', 'success');
    }
  } catch (err) {
    showStatus('report-status', 'Server error: ' + err.message, 'error');
  }
}

// Screenshot upload
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');

uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

async function handleFiles(files) {
  for (const file of files) {
    showStatus('upload-status', 'Processing ' + file.name + '...', 'info');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch('/upload', { method: 'POST', body: formData });
      const result = await resp.json();
      if (result.error) {
        showStatus('upload-status', file.name + ': ' + result.error, 'error');
      } else {
        // Add extracted data
        let added = 0;
        let shopInfo = [];
        if (result.data) {
          for (const item of result.data) {
            if (item.type === 'listing_stats' && item.listings) {
              item.listings.forEach(l => { addListing(l); added++; });
            } else if (item.type === 'shop_page') {
              // Fill shop info from public page
              if (item.shop) {
                const s = item.shop;
                if (s.review_count != null) { document.getElementById('review_count').value = s.review_count; shopInfo.push(s.review_count + ' reviews'); }
                if (s.total_sales != null) { document.getElementById('total_sales').value = s.total_sales; shopInfo.push(s.total_sales + ' sales'); }
                if (s.admirers != null) { document.getElementById('admirers').value = s.admirers; shopInfo.push(s.admirers + ' admirers'); }
                if (s.item_count != null) shopInfo.push(s.item_count + ' items');
                if (s.star_rating != null) shopInfo.push(s.star_rating + ' stars');
              }
              // Add listings from shop page
              if (item.listings) {
                item.listings.forEach(l => { addListing(l); added++; });
              }
            } else if (item.type === 'shop_stats' && item.metrics) {
              const m = item.metrics;
              if (m.views) shopInfo.push(m.views + ' views');
              if (m.orders) shopInfo.push(m.orders + ' orders');
            } else if (item.type === 'conversion_breakdown' && item.metrics) {
              const m = item.metrics;
              if (m.views) shopInfo.push(m.views + ' views');
              if (m.orders) shopInfo.push(m.orders + ' orders');
            }
          }
        }
        let msg = file.name + ': extracted ' + added + ' listing' + (added !== 1 ? 's' : '');
        if (shopInfo.length > 0) msg += ' + shop info (' + shopInfo.join(', ') + ')';
        showStatus('upload-status', msg, 'success');
      }
    } catch (err) {
      showStatus('upload-status', file.name + ': ' + err.message, 'error');
    }
  }
}

function showStatus(elementId, html, type) {
  const el = document.getElementById(elementId);
  el.innerHTML = '<div class="status status-' + type + '">' + html + '</div>';
}

renderListings();
</script>
</body>
</html>"""


class CollectorHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path.startswith("/report/"):
            filename = os.path.basename(self.path[8:])
            filepath = os.path.join(PROJECT_DIR, filename)
            if os.path.exists(filepath):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/generate":
            self._handle_generate()
        elif self.path == "/upload":
            self._handle_upload()
        else:
            self.send_error(404)

    def _handle_generate(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            # Import and run scorer
            sys.path.insert(0, PROJECT_DIR)
            import scorer
            import report as report_mod
            # Reload in case they were already imported
            import importlib
            importlib.reload(scorer)
            importlib.reload(report_mod)

            result = scorer.score_shop(data)
            shop_name = data.get("shop", {}).get("name", "shop")
            safe_name = "".join(c if c.isalnum() else "_" for c in shop_name)
            report_filename = f"report_{safe_name}.html"
            report_path = os.path.join(PROJECT_DIR, report_filename)

            html = report_mod.generate_report(result, shop_name)
            with open(report_path, "w") as f:
                f.write(html)

            # Also save the JSON
            json_path = os.path.join(PROJECT_DIR, f"{safe_name}_result.json")
            with open(json_path, "w") as f:
                json.dump(result, f, indent=2)

            self._json_response({"filename": report_filename, "json_file": f"{safe_name}_result.json"})
        except Exception as e:
            self._json_response({"error": str(e)})

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._json_response({"error": "Expected multipart/form-data"})
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type}
        )

        file_item = form["file"]
        if not file_item.file:
            self._json_response({"error": "No file uploaded"})
            return

        # Save to temp file
        suffix = os.path.splitext(file_item.filename)[1] or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_item.file.read())
            tmp_path = tmp.name

        try:
            sys.path.insert(0, PROJECT_DIR)
            import screenshot_extractor
            import importlib
            importlib.reload(screenshot_extractor)

            results = screenshot_extractor.process_path(tmp_path)
            self._json_response({"data": results})
        except Exception as e:
            self._json_response({"error": str(e)})
        finally:
            os.unlink(tmp_path)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quieter logging
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("localhost", PORT), CollectorHandler)
    print(f"ShopPulse Data Collector running at http://localhost:{PORT}")
    print(f"Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
