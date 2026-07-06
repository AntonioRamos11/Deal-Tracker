import os
import json
import threading
import time
import urllib.request
import email.utils
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request, send_from_directory

import database as db
import scrapers as scr
import stats_engine as st
import alerts as al

app = Flask(__name__, template_folder='templates', static_folder='static')

# Scheduler state and Network clock offset
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler_state.json")
clock_offset = 0.0
last_sync_time = 0.0

def load_scheduler_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_scan_epoch": 0.0}

def save_scheduler_state(state):
    try:
        with open(STATE_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving scheduler state: {e}")

def sync_clock_offset():
    global clock_offset, last_sync_time
    now = time.time()
    if now - last_sync_time < 3600 and last_sync_time != 0.0:
        return
        
    log_message("🔄 Syncing scheduler clock with Culiacán (UTC-7) network time sources...")
    
    # Try 1: Google Date header (High reliability, fast, standard port 443)
    try:
        req = urllib.request.Request("https://www.google.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as response:
            date_header = response.headers.get("Date")
            if date_header:
                parsed_date = email.utils.parsedate_to_datetime(date_header)
                network_epoch = parsed_date.timestamp()
                clock_offset = network_epoch - time.time()
                last_sync_time = time.time()
                log_message(f"✅ Clock synced via Google header. Offset: {clock_offset:.2f}s")
                return
    except Exception as e:
        log_message(f"⚠️ Google header time sync failed: {e}")

    # Try 2: TimeAPI.io America/Mazatlan timezone API
    try:
        req = urllib.request.Request("https://timeapi.io/api/Time/current/zone?timeZone=America/Mazatlan")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            dt_str = data.get("dateTime")
            if dt_str:
                parts = dt_str.split('.')
                if len(parts) > 1:
                    parts[1] = parts[1][:6]
                    dt_str = '.'.join(parts)
                dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f")
                dt = dt.replace(tzinfo=timezone(timedelta(hours=-7)))
                clock_offset = dt.timestamp() - time.time()
                last_sync_time = time.time()
                log_message(f"✅ Clock synced via TimeAPI.io. Offset: {clock_offset:.2f}s")
                return
    except Exception as e:
        log_message(f"⚠️ TimeAPI.io sync failed: {e}")

    # Try 3: WorldTimeAPI America/Mazatlan timezone API
    try:
        req = urllib.request.Request("http://worldtimeapi.org/api/timezone/America/Mazatlan")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            datetime_str = data.get("datetime")
            if datetime_str:
                dt = datetime.fromisoformat(datetime_str)
                clock_offset = dt.timestamp() - time.time()
                last_sync_time = time.time()
                log_message(f"✅ Clock synced via WorldTimeAPI. Offset: {clock_offset:.2f}s")
                return
    except Exception as e:
        log_message(f"⚠️ WorldTimeAPI sync failed: {e}")

    log_message("⚠️ All network time APIs failed. Using existing offset/system clock.")

def get_culiacan_datetime():
    sync_clock_offset()
    current_epoch = time.time() + clock_offset
    dt_utc = datetime.fromtimestamp(current_epoch, tz=timezone.utc)
    return dt_utc.astimezone(timezone(timedelta(hours=-7)))

def is_in_active_window(dt):
    # Active scanning window: 6:00 AM (6) to 12:00 Midnight (23:59:59) Culiacán time
    return 6 <= dt.hour <= 23

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "gpu_tracker.db")
STATIC_CHARTS_DIR = os.path.join(BASE_DIR, "static", "charts")

# Ensure directories exist
os.makedirs(STATIC_CHARTS_DIR, exist_ok=True)
db.init_db(DB_PATH)
# Remove any leftover simulated/fake listings from previous sessions
db.purge_simulated_listings(DB_PATH)

# Global tracking variables for scan status
scan_status = {
    "is_running": False,
    "last_run": "Never",
    "progress": "",
    "log": [],
    "culiacan_time": "Cargando...",
    "is_active_window": True,
    "next_scan_time": "Desconocido",
    "seconds_until_next_scan": 0
}

def log_message(msg):
    # Calculate Culiacán time using current cached offset to avoid recursion during sync calls
    current_epoch = time.time() + clock_offset
    dt_utc = datetime.fromtimestamp(current_epoch, tz=timezone.utc)
    culiacan_dt = dt_utc.astimezone(timezone(timedelta(hours=-7)))
    timestamp = culiacan_dt.strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    scan_status["log"].append(full_msg)
    if len(scan_status["log"]) > 100:
        scan_status["log"].pop(0)

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config_data):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config_data, f, indent=2)

def parse_time_left_to_minutes(time_left_str):
    if not time_left_str:
        return 999999
    s = time_left_str.lower()
    total = 0
    import re
    d_match = re.search(r'(\d+)\s*d', s)
    if d_match:
        total += int(d_match.group(1)) * 1440
    h_match = re.search(r'(\d+)\s*h', s)
    if h_match:
        total += int(h_match.group(1)) * 60
    m_match = re.search(r'(\d+)\s*m', s)
    if m_match:
        total += int(m_match.group(1))
        
    if total == 0:
        num_match = re.search(r'(\d+)', s)
        if num_match:
            if 's' in s and 'm' not in s and 'h' not in s and 'd' not in s:
                return 1
            return int(num_match.group(1))
        return 999999
    return total

def cleanup_sold_deals(db_path=DB_PATH):
    import random
    log_message("🧹 Starting cleanup of sold/ended deals...")
    try:
        alerts = db.get_all_alerts(db_path)
        if not alerts:
            log_message("🧹 No active deals found in database to verify.")
            return
            
        log_message(f"🧹 Found {len(alerts)} active deals to verify.")
        cleaned_count = 0
        
        for alert in alerts:
            listing_id = alert["listing_id"]
            platform = alert["platform"]
            url = alert["url"]
            alerted_at_str = alert["alerted_at"]
            
            # Rate limit/cooldown: Skip if the deal was added less than 10 minutes ago
            try:
                alerted_at = datetime.fromisoformat(alerted_at_str)
                if alerted_at.tzinfo is None:
                    alerted_at = alerted_at.replace(tzinfo=timezone.utc)
                
                time_elapsed = datetime.now(timezone.utc) - alerted_at
                if time_elapsed < timedelta(minutes=10):
                    log_message(f"🧹 Skipping verification for new deal {listing_id} (added {time_elapsed.total_seconds()/60:.1f} mins ago).")
                    continue
            except Exception as te:
                print(f"Error checking elapsed time for {listing_id}: {te}")
                
            log_message(f"🧹 Verifying active status for {platform} deal: {listing_id}...")
            is_active = scr.verify_listing_active(platform, listing_id, url)
            
            if is_active is False:
                log_message(f"🗑️ DEAL SOLD/ENDED: Removing deal {listing_id} on {platform} from database.")
                db.delete_alert(listing_id, db_path)
                cleaned_count += 1
            elif is_active is True:
                log_message(f"🧹 Deal {listing_id} is still active.")
            else:
                log_message(f"🧹 Verification inconclusive for {listing_id} (network error/block). Retaining deal.")
                
            time.sleep(random.uniform(1.0, 2.5))
            
        if cleaned_count > 0:
            log_message(f"🧹 Completed cleanup. Removed {cleaned_count} sold/ended deals.")
        else:
            log_message("🧹 Completed cleanup. No sold deals were found.")
            
    except Exception as e:
        log_message(f"❌ Error during sold deals cleanup: {e}")

def scan_products(products, category_name, settings, global_negatives, ml_site):
    """Generic scan logic for a list of products (GPUs or phones)."""
    for idx, product in enumerate(products):
        product_id = product["id"]
        product_name = product["name"]
        scan_status["progress"] = f"Scanning {product_name} ({idx+1}/{len(products)})..."
        log_message(f"--- Processing {product_name} [{category_name}] ---")
        
        # 1. Scrape eBay completed (sold) listings to establish baseline
        log_message(f"Scraping eBay SOLD listings for: {product['ebay_query']}")
        raw_sold = scr.scrape_ebay(product["ebay_query"], status='sold', max_items=80, gpu_config=product)
        clean_sold = scr.clean_and_filter_listings(raw_sold, product, global_negatives)
        log_message(f"Found {len(raw_sold)} raw sold listings, {len(clean_sold)} after filtering.")
        
        # Save sold listings to database
        if clean_sold:
            db.save_listings(clean_sold, DB_PATH)
            
        # 2. Calculate Statistics
        sold_prices = db.get_listings_for_stats(product_id, status='sold', limit=150, db_path=DB_PATH)
        log_message(f"Total sold sample size for calculations: {len(sold_prices)}")
        
        stats = None
        if len(sold_prices) >= 3:
            stats = st.calculate_statistics(sold_prices)
            if stats:
                db.save_stats(product_id, stats, DB_PATH)
                log_message(f"Calculated Stats -> Mode: ${stats['mode_price_usd']} | Median: ${stats['median_price_usd']} | Samples: {stats['sample_count']}")
                
                chart_path = os.path.join(STATIC_CHARTS_DIR, f"{product_id}.png")
                st.generate_price_distribution_chart(sold_prices, stats, product_name, chart_path)
                log_message(f"Generated distribution chart for {product_name}")
        
        if stats is None:
            stats = db.get_latest_stats(product_id, DB_PATH)
            if stats:
                log_message(f"Loaded existing stats from DB -> Mode: ${stats['mode_price_usd']} (Samples: {stats['sample_count']})")
                
        if stats is None:
            fallback_price = product.get("market_price_usd") or ((product["min_price_usd"] + product["max_price_usd"]) / 2.0)
            stats = {
                "mode_price_usd": fallback_price,
                "median_price_usd": fallback_price,
                "mean_price_usd": fallback_price,
                "min_price_usd": product["min_price_usd"],
                "max_price_usd": product["max_price_usd"],
                "sample_count": 0
            }
            log_message(f"Using fallback stats from config -> Mode: ${stats['mode_price_usd']}")
            
        # 3. Scrape Active Listings
        log_message(f"Scraping Active listings from eBay, Best Buy, MercadoLibre, and Facebook...")
        active_ebay_bin = scr.scrape_ebay(product["ebay_query"], status='active', buying_format='bin', max_items=40, gpu_config=product)
        active_ebay_auc = scr.scrape_ebay(product["ebay_query"], status='active', buying_format='auction', max_items=40, gpu_config=product)
        
        active_ml = scr.query_mercadolibre(product["ml_query"], site_id=ml_site, max_items=40, gpu_config=product)
        
        fb_cities = ["culiacan", "losmochis", "tijuana", "guadalajara"]
        active_fb = []
        for city in fb_cities:
            log_message(f"Scraping Facebook Marketplace in {city} for: {product['ml_query']}")
            city_listings = scr.scrape_facebook_marketplace(product["ml_query"], city_slug=city, max_items=10, gpu_config=product)
            active_fb.extend(city_listings)
        
        log_message(f"Scraping Best Buy USA for: {product['ebay_query']}")
        active_bestbuy = scr.scrape_bestbuy(product["ebay_query"], max_items=20, gpu_config=product)
        log_message(f"Best Buy found {len(active_bestbuy)} items.")

        all_active = active_ebay_bin + active_ebay_auc + active_ml + active_fb + active_bestbuy
        clean_active = scr.clean_and_filter_listings(all_active, product, global_negatives)
        log_message(f"Found {len(all_active)} raw active listings ({len(active_ebay_bin)} eBay BIN, {len(active_ebay_auc)} eBay Auction, {len(active_ml)} MercadoLibre, {len(active_fb)} Facebook, {len(active_bestbuy)} Best Buy). {len(clean_active)} after cleaning.")
        
        db.clear_active_listings_for_model(product_id, DB_PATH)
        
        if clean_active:
            db.save_listings(clean_active, DB_PATH)
            
        # 4. Check for deals and alert
        if stats and stats['mode_price_usd'] > 0:
            deals_found = 0
            for item in clean_active:
                listing_id = item["id"]
                
                if item.get("is_auction") == 1:
                    time_left_str = item.get("time_left")
                    minutes_left = parse_time_left_to_minutes(time_left_str)
                    if minutes_left > 60:
                        continue
                
                if not db.has_been_alerted(listing_id, DB_PATH):
                    discount_pct = (stats['mode_price_usd'] - item['price_usd']) / stats['mode_price_usd']
                    if discount_pct >= settings.get("discount_alert_threshold", 0.15):
                        log_message(f"🚨 DEAL DETECTED: {item['title']} for ${item['price_usd']:.2f} USD (Market: ${stats['mode_price_usd']:.2f} USD, -{discount_pct*100:.1f}%)")
                        al.trigger_alerts(item, stats, settings)
                        db.mark_as_alerted(listing_id, product_id, item['price_usd'], discount_pct, DB_PATH)
                        deals_found += 1
                        
            log_message(f"Finished active scan for {product_name}. Triggered {deals_found} new alerts.")
        else:
            log_message(f"Skipping deal detection for {product_name} due to lack of baseline market stats.")
            
        import random
        time.sleep(random.uniform(2.0, 5.0))

def perform_scan_task():
    global scan_status
    scan_status["is_running"] = True
    scan_status["progress"] = "Starting scan..."
    log_message("=== Starting GPU Price Tracker Scan ===")
    
    try:
        config = load_config()
        settings = config.get("settings", {})
        global_negatives = config.get("global_negative_keywords", [])
        ml_site = settings.get("mercadolibre_site_id", "MLM")
        
        gpus = config.get("gpus", [])
        phones = config.get("phones", [])
        
        log_message(f"Loaded {len(gpus)} GPU models and {len(phones)} phone models to scan.")
        
        if gpus:
            log_message(f"=== Scanning GPUs ({len(gpus)} models) ===")
            scan_products(gpus, "GPU", settings, global_negatives, ml_site)
        
        if phones:
            log_message(f"=== Scanning Phones ({len(phones)} models) ===")
            scan_products(phones, "Phone", settings, global_negatives, ml_site)
        
        # Clean up database
        purged = db.purge_old_listings(days=30, db_path=DB_PATH)
        log_message(f"Purged {purged} raw listings older than 30 days.")
        
        cleanup_sold_deals(DB_PATH)
        
        cul_dt = get_culiacan_datetime()
        scan_status["last_run"] = cul_dt.strftime("%Y-%m-%d %H:%M:%S")
        log_message("=== Scan Completed Successfully ===")
        
        state = load_scheduler_state()
        state["last_scan_epoch"] = cul_dt.timestamp()
        save_scheduler_state(state)
        
    except Exception as e:
        log_message(f"❌ Scan failed with exception: {e}")
        import traceback
        log_message(traceback.format_exc())
    finally:
        scan_status["is_running"] = False
        scan_status["progress"] = "Idle"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    stats = db.get_latest_stats(db_path=DB_PATH)
    config = load_config()
    usd_to_mxn = 1.0 / scr.get_exchange_rate("MXN", "USD")
    
    enriched_stats = []
    all_products = []
    for g in config.get("gpus", []):
        g['category'] = 'gpu'
        all_products.append(g)
    for p in config.get("phones", []):
        p['category'] = 'phone'
        all_products.append(p)
    
    products_dict = {p['id']: p for p in all_products}
    
    for product_id, s in stats.items():
        if product_id in products_dict:
            info = products_dict[product_id]
            s['name'] = info['name']
            s['category'] = info.get('category', 'gpu')
            s['min_price_limit'] = info['min_price_usd']
            s['max_price_limit'] = info['max_price_usd']
            s['min_price_limit_mxn'] = round(info['min_price_usd'] * usd_to_mxn, 2)
            s['max_price_limit_mxn'] = round(info['max_price_usd'] * usd_to_mxn, 2)
            s['viability'] = info.get('viability', 'no_sirve')
            s['viability_reason'] = info.get('viability_reason', '')
            
            s['mode_price_mxn'] = round(s['mode_price_usd'] * usd_to_mxn, 2)
            s['median_price_mxn'] = round(s['median_price_usd'] * usd_to_mxn, 2)
            s['min_price_mxn'] = round(s['min_price_usd'] * usd_to_mxn, 2)
            s['max_price_mxn'] = round(s['max_price_usd'] * usd_to_mxn, 2)
            s['usd_to_mxn_rate'] = round(usd_to_mxn, 4)
            s['is_fallback'] = False
            
            chart_filename = f"{product_id}.png"
            if os.path.exists(os.path.join(STATIC_CHARTS_DIR, chart_filename)):
                s['chart_url'] = f"/static/charts/{chart_filename}"
            else:
                s['chart_url'] = None
            enriched_stats.append(s)
            
    # Include products that have no stats yet as fallbacks
    for product in all_products:
        if product['id'] not in stats:
            fallback_price = product.get("market_price_usd") or ((product["min_price_usd"] + product["max_price_usd"]) / 2.0)
            enriched_stats.append({
                "model_id": product['id'],
                "name": product['name'],
                "category": product.get('category', 'gpu'),
                "mode_price_usd": fallback_price,
                "median_price_usd": fallback_price,
                "mean_price_usd": fallback_price,
                "min_price_usd": product['min_price_usd'],
                "max_price_usd": product['max_price_usd'],
                "mode_price_mxn": round(fallback_price * usd_to_mxn, 2),
                "median_price_mxn": round(fallback_price * usd_to_mxn, 2),
                "min_price_mxn": round(product['min_price_usd'] * usd_to_mxn, 2),
                "max_price_mxn": round(product['max_price_usd'] * usd_to_mxn, 2),
                "sample_count": 0,
                "chart_url": None,
                "min_price_limit": product['min_price_usd'],
                "max_price_limit": product['max_price_usd'],
                "min_price_limit_mxn": round(product['min_price_usd'] * usd_to_mxn, 2),
                "max_price_limit_mxn": round(product['max_price_usd'] * usd_to_mxn, 2),
                "viability": product.get('viability', 'no_sirve'),
                "viability_reason": product.get('viability_reason', ''),
                "is_fallback": True
            })
            
    return jsonify(enriched_stats)

@app.route('/api/auctions')
def get_auctions():
    auctions = db.get_active_auctions(limit=100, db_path=DB_PATH)
    config = load_config()
    usd_to_mxn = 1.0 / scr.get_exchange_rate("MXN", "USD")
    gpus_dict = {g['id']: g for g in config.get("gpus", [])}
    
    # Get latest statistics for calculations
    stats = db.get_latest_stats(db_path=DB_PATH)
    
    enriched_auctions = []
    for d in auctions:
        if d['model_id'] in gpus_dict:
            d['model_name'] = gpus_dict[d['model_id']]['name']
            
            # Get market baseline (Mode price)
            mode_price = 0.0
            if d['model_id'] in stats:
                mode_price = stats[d['model_id']]['mode_price_usd']
            if mode_price <= 0:
                mode_price = gpus_dict[d['model_id']].get("market_price_usd", 0)
        else:
            d['model_name'] = d['model_id'].upper()
            mode_price = 0.0
            
        d['mode_price_usd'] = mode_price
        d['price_mxn'] = round(d['price_usd'] * usd_to_mxn, 2)
        d['mode_price_mxn'] = round(mode_price * usd_to_mxn, 2)
        
        # Calculate Margin
        if mode_price > 0:
            d['margin_usd'] = round(mode_price - d['price_usd'], 2)
            d['margin_mxn'] = round(d['mode_price_mxn'] - d['price_mxn'], 2)
            d['margin_percent'] = round((d['margin_usd'] / mode_price) * 100, 1)
            
            # Filter: only keep auctions with positive profit margin
            if d['margin_usd'] <= 0:
                continue
        else:
            # Skip if baseline statistics are missing (cannot determine margin)
            continue
            
        enriched_auctions.append(d)
        
    return jsonify(enriched_auctions)

@app.route('/api/deals')
def get_deals():
    deals = db.get_recent_deals(limit=100, db_path=DB_PATH)
    config = load_config()
    usd_to_mxn = 1.0 / scr.get_exchange_rate("MXN", "USD")
    gpus_dict = {g['id']: g for g in config.get("gpus", [])}
    for d in deals:
        if d['model_id'] in gpus_dict:
            d['model_name'] = gpus_dict[d['model_id']]['name']
        else:
            d['model_name'] = d['model_id'].upper()
            
        # Add dynamic MXN price conversion if not already MXN
        if d.get('original_currency') == 'MXN':
            d['price_mxn'] = d['original_price']
        else:
            d['price_mxn'] = round(d['price_usd'] * usd_to_mxn, 2)
    # Always sort by highest discount percentage first
    deals.sort(key=lambda x: x.get('discount_percent', 0), reverse=True)
    return jsonify(deals)

@app.route('/api/deals/clear', methods=['POST'])
def clear_deals():
    deleted = db.delete_all_deals(db_path=DB_PATH)
    log_message(f"🗑️ User cleared all {deleted} deals from history.")
    return jsonify({"success": True, "deleted": deleted})

@app.route('/api/status')
def get_status():
    return jsonify(scan_status)

@app.route('/api/trigger_scan', methods=['POST'])
def trigger_scan():
    if scan_status["is_running"]:
        return jsonify({"success": False, "message": "Scan is already running"}), 400
        
    t = threading.Thread(target=perform_scan_task)
    t.daemon = True
    t.start()
    return jsonify({"success": True, "message": "Scan started in background"})

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        config = load_config()
        return jsonify(config["settings"])
    else:
        new_settings = request.json
        config = load_config()
        config["settings"].update(new_settings)
        save_config(config)
        return jsonify({"success": True, "settings": config["settings"]})

def scheduler_loop():
    """Background daemon loop that triggers periodic scans based on config interval,
    restricted to 6:00 AM - 12:00 Midnight Culiacán time."""
    log_message("Background scheduler loop initialized (6:00 AM - 12:00 Midnight Culiacán time window).")
    
    # Do an initial sync at startup
    try:
        sync_clock_offset()
    except Exception as e:
        print(f"Initial clock sync failed: {e}")
        
    while True:
        try:
            # Get current Culiacán time
            dt = get_culiacan_datetime()
            now_epoch = dt.timestamp()
            
            # Load config and settings
            config = load_config()
            interval_hours = config.get("settings", {}).get("update_interval_hours", 6)
            interval_seconds = interval_hours * 3600
            
            # Load state
            state = load_scheduler_state()
            last_scan_epoch = state.get("last_scan_epoch", 0.0)
            
            # Update scan_status keys for UI
            scan_status["culiacan_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            active_window = is_in_active_window(dt)
            scan_status["is_active_window"] = active_window
            
            time_since_last = now_epoch - last_scan_epoch
            time_remaining = max(0.0, interval_seconds - time_since_last)
            
            scan_status["seconds_until_next_scan"] = int(time_remaining)
            if last_scan_epoch > 0:
                next_dt = datetime.fromtimestamp(last_scan_epoch + interval_seconds, tz=timezone.utc).astimezone(timezone(timedelta(hours=-7)))
                scan_status["next_scan_time"] = next_dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                scan_status["next_scan_time"] = "Inmediato"
            
            # Decide if we trigger scan
            if active_window:
                if not scan_status["is_running"] and time_since_last >= interval_seconds:
                    log_message(f"⏳ Culiacán scheduler triggering periodic scan (Culiacán time: {dt.strftime('%H:%M:%S')})")
                    # Start in background thread so the scheduler loop can keep updating culiacan_time
                    t = threading.Thread(target=perform_scan_task)
                    t.daemon = True
                    t.start()
                    
                    # Update state immediately to prevent double-spawning
                    state["last_scan_epoch"] = now_epoch
                    save_scheduler_state(state)
            else:
                # If outside active window, update status progress message
                if not scan_status["is_running"]:
                    scan_status["progress"] = "Inactivo (Fuera de horario de escaneo)"
                    
        except Exception as e:
            print(f"Error in scheduler loop: {e}")
            
        time.sleep(10) # check status every 10 seconds

# Start scheduler thread
def start_scheduler():
    t = threading.Thread(target=scheduler_loop)
    t.daemon = True
    t.start()

# Start scheduler thread only in Werkzeug main thread to prevent duplicate runs under Flask reloader
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    start_scheduler()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
