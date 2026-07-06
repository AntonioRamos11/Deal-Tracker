import requests as std_requests
from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

import random

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0'
]

def get_headers():
    referers = [
        'https://www.google.com/',
        'https://www.bing.com/',
        'https://search.yahoo.com/',
        'https://duckduckgo.com/'
    ]
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Referer': random.choice(referers),
        'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }

_exchange_rates_cache = {}

def get_exchange_rate(from_curr, to_curr="USD"):
    """Fetches exchange rates to USD from open API with static fallbacks."""
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()
    
    if from_curr == to_curr:
        return 1.0
        
    cache_key = f"{from_curr}_{to_curr}"
    if cache_key in _exchange_rates_cache:
        return _exchange_rates_cache[cache_key]
        
    try:
        r = std_requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        if r.status_code == 200:
            data = r.json()
            rates = data.get("rates", {})
            usd_to_from = rates.get(from_curr)
            usd_to_to = rates.get(to_curr)
            if usd_to_from is not None and usd_to_to is not None:
                rate = usd_to_to / usd_to_from
                _exchange_rates_cache[cache_key] = rate
                return rate
    except Exception as e:
        print(f"Error fetching live exchange rate for {from_curr}: {e}")
        
    # Fallback rates if external API is down
    fallbacks = {
        "MXN_USD": 1.0 / 17.5,
        "ARS_USD": 1.0 / 950.0,
        "COP_USD": 1.0 / 4000.0,
        "CLP_USD": 1.0 / 900.0,
        "BRL_USD": 1.0 / 5.4,
        "EUR_USD": 1.08,
        "GBP_USD": 1.27,
        "CAD_USD": 0.73
    }
    return fallbacks.get(cache_key, 1.0)

def parse_price(price_str):
    """Parses a price string, extracting value and currency."""
    if not price_str:
        return None, None
        
    # Strip spaces and upper case
    price_str = price_str.strip()
    price_str_upper = price_str.upper()
    
    # Identify currency
    original_currency = "USD"
    if "MXN" in price_str_upper or "M.N." in price_str_upper:
        original_currency = "MXN"
    elif "EUR" in price_str_upper or "€" in price_str_upper:
        original_currency = "EUR"
    elif "GBP" in price_str_upper or "£" in price_str_upper:
        original_currency = "GBP"
    elif "ARS" in price_str_upper:
        original_currency = "ARS"
    elif "COP" in price_str_upper:
        original_currency = "COP"
    elif "CLP" in price_str_upper:
        original_currency = "CLP"
    elif "R$" in price_str_upper or "BRL" in price_str_upper:
        original_currency = "BRL"
    elif "CAD" in price_str_upper or "C $" in price_str_upper or "C$" in price_str_upper:
        original_currency = "CAD"
        
    # If range e.g. "$650.00 to $700.00", split and take the first one
    if " TO " in price_str_upper:
        price_str = price_str.split(" to ")[0]
        
    # Remove everything except digits, dots, and commas
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if not cleaned:
        return None, None
        
    # Clean up formatting:
    # Example: "1,200.50" -> "1200.50"
    # Example: "1.200,50" -> "1200.50"
    if ',' in cleaned and '.' in cleaned:
        comma_idx = cleaned.find(',')
        dot_idx = cleaned.find('.')
        if comma_idx < dot_idx:
            cleaned = cleaned.replace(',', '')
        else:
            cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        # Check if comma is decimal (e.g. 300,50) or thousands (e.g. 1,200)
        parts = cleaned.split(',')
        if len(parts[-1]) == 3: # thousands
            cleaned = cleaned.replace(',', '')
        else: # decimal
            cleaned = cleaned.replace(',', '.')
            
    try:
        val = float(cleaned)
        return val, original_currency
    except ValueError:
        return None, None

def extract_time_left_from_segments(segments):
    """Parses text segments to identify the one that contains remaining auction time."""
    if not segments:
        return None
    time_terms = ["left", "quedan", "queda", "restante", "restan", "resta", "remaining", "tiempo"]
    # First pass: look for segment with explicit keyword and digits
    for seg in segments:
        seg_lower = seg.lower()
        if any(term in seg_lower for term in time_terms):
            if re.search(r'\d+', seg_lower):
                return seg
    # Second pass: look for patterns like 6d 3h, 5h, 30m, etc.
    for seg in segments:
        seg_lower = seg.lower()
        if re.search(r'\b\d+\s*[dhms]\b', seg_lower) or re.search(r'\b\d+\s*min\b', seg_lower):
            return seg
    return None

import random

def generate_simulated_listings(gpu_config, platform, status, count=30, inject_deal=False):
    """Generates realistic simulated listings for testing when real scrapers are IP-blocked."""
    listings = []
    if not gpu_config:
        gpu_config = {
            "id": "generic_gpu",
            "name": "Generic GPU",
            "min_price_usd": 100,
            "max_price_usd": 500
        }
        
    gpu_id = gpu_config["id"]
    gpu_name = gpu_config["name"]
    min_p = gpu_config["min_price_usd"]
    max_p = gpu_config["max_price_usd"]
    
    # Center price distribution around 45% of range
    center = min_p + (max_p - min_p) * 0.45
    std_dev = (max_p - min_p) * 0.12
    
    brands = ["ASUS ROG Strix", "EVGA XC3", "Gigabyte Gaming OC", "MSI Ventus 3X", "Zotac Trinity", "PNY XLR8", "ASUS TUF"]
    if "rx" in gpu_id:
        brands = ["PowerColor Hellhound", "Sapphire NITRO+", "XFX Speedster", "ASUS ROG Strix", "MSI Gaming X", "Gigabyte Gaming OC"]
        
    conditions = ["Excelente estado", "Poco uso", "Usada para gaming", "Completa en caja", "Como nueva", "Nunca minada", "Garantía vigente"]
    
    # Determine VRAM
    vram = "8GB"
    if "5090" in gpu_id:
        vram = "32GB"
    elif "4090" in gpu_id or "3090" in gpu_id:
        vram = "24GB"
    elif "5080" in gpu_id or "4080" in gpu_id or "7900" in gpu_id or "6800" in gpu_id or "7800" in gpu_id or "v100" in gpu_id:
        vram = "16GB"
    elif "4070" in gpu_id or "3080" in gpu_id or "3060" in gpu_id or "6700" in gpu_id:
        vram = "12GB"
    elif "2060" in gpu_id or "1060" in gpu_id:
        vram = "6GB"
        
    for i in range(count):
        price = random.normalvariate(center, std_dev)
        price = max(min_p, min(max_p, price)) # clamp
        
        # Inject an occasional deal for active listings (e.g. 20% cheaper than normal min center)
        if status == 'active' and inject_deal and i == 0:
            price = min_p + (center - min_p) * 0.35
            
        title = f"{gpu_name} {random.choice(brands)} {vram} - {random.choice(conditions)}"
        url = f"https://www.{platform}.com/itm/simulated_{gpu_id}_{status}_{i}_{random.randint(1000,9999)}"
        
        # Original price for ML (MXN)
        original_price = price
        currency = "USD"
        if platform == 'mercadolibre':
            currency = "MXN"
            # 1 USD = 17.4 MXN
            original_price = price * 17.4
            
        img_url = "https://img.icons8.com/color/96/nvidia.png" if ("rtx" in gpu_id or "gtx" in gpu_id) else "https://img.icons8.com/color/96/amd.png"
        
        listings.append({
            "id": f"{platform}_sim_{gpu_id}_{status}_{i}_{random.randint(100000,999999)}",
            "model_id": gpu_id,
            "title": title,
            "price_usd": round(price, 2),
            "original_price": round(original_price, 2),
            "original_currency": currency,
            "url": url,
            "image_url": img_url,
            "platform": platform,
            "status": status,
            "scraped_at": datetime.utcnow().isoformat()
        })
        
    return listings

def scrape_ebay(query, status='sold', buying_format='bin', max_items=100, gpu_config=None):
    """Scrapes eBay for active or sold listings. Falls back to Mobile Safari anti-block if desktop is blocked."""
    listings = []
    current_domain = "ebay.com"
    base_url = "https://www.ebay.com/sch/i.html"
    params = {
        "_nkw": query,
        "LH_ItemCondition": "3000",  # Used
        "_ipg": "100"
    }
    
    if status == 'sold':
        params["LH_Sold"] = "1"
        params["LH_Complete"] = "1"
    else:
        if buying_format == 'bin':
            params["_sop"] = "10"  # Newly listed
            params["LH_BIN"] = "1"
        elif buying_format == 'auction':
            params["_sop"] = "1"   # Ending soonest
            params["LH_Auction"] = "1"
            
    mobile_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    def attempt_request(use_mobile=False):
        req_headers = mobile_headers if use_mobile else get_headers()
        impersonate_val = 'safari' if use_mobile else 'chrome'
        return requests.get(base_url, params=params, headers=req_headers, impersonate=impersonate_val, timeout=10)
        
    def parse_html(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # Check desktop first
        items = soup.select('li.s-item')
        # Filter out s-item templates
        items = [it for it in items if not it.select_one('.s-item__title--italic') and "shop on ebay" not in it.get_text().lower()]
        
        is_mobile_layout = False
        if not items or len(items) <= 1:
            # Try mobile data-listingid
            items = soup.find_all(attrs={"data-listingid": True})
            is_mobile_layout = True
            
        parsed = []
        for item in items:
            try:
                if is_mobile_layout:
                    lid = item.get("data-listingid")
                    if not lid or lid == "0":
                        continue
                    listing_id = f"ebay_{lid}"
                    
                    img_el = item.find("img")
                    title = img_el.get("alt") if img_el else None
                    if not title:
                        header_el = item.select_one(".su-card-container__header")
                        if header_el:
                            title = header_el.get_text(strip=True)
                    if not title or title.lower() == "shop on ebay":
                        continue
                        
                    link_el = item.find("a", href=True)
                    if not link_el:
                        continue
                    url = link_el["href"]
                    match_url = re.search(r'/itm/(\d+)', url)
                    if match_url:
                        url = f"https://www.ebay.com/itm/{match_url.group(1)}"
                        
                    image_url = None
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-defer-load") or img_el.get("data-src")
                        
                    text_content = item.get_text(" | ", strip=True)
                    segments = [s.strip() for s in text_content.split(" | ")]
                    
                    price_val = None
                    original_currency = "USD"
                    shipping_usd = 0.0
                    is_auc = (buying_format == 'auction')
                    bids_count = 0
                    time_left = None
                    
                    # Try CSS selectors first for higher accuracy (e.g. s-card__time-left or s-item__time-left)
                    time_el = item.select_one('.s-card__time-left, .s-card__timeleft, .s-item__time-left, .s-item__timeleft, .s-item__time, .s-card__time')
                    if time_el:
                        time_left = time_el.get_text(strip=True)
                        is_auc = True
                        
                    bids_el = item.select_one('.s-card__bid-count, .s-card__bids, .s-card__bidCount, .s-item__bids, .s-item__bidCount')
                    if bids_el:
                        is_auc = True
                        bids_text = bids_el.get_text(strip=True)
                        match_b = re.search(r'(\d+)', bids_text)
                        if match_b:
                            bids_count = int(match_b.group(1))
                            
                    for seg in segments:
                        if (title and seg.lower() == title.lower()) or len(seg) > 50:
                            continue
                            
                        if any(cur in seg.upper() for cur in ["$", "MXN", "€", "£", "EUR", "GBP", "USD"]) and not price_val:
                            if "shipping" not in seg.lower() and "envío" not in seg.lower() and "envio" not in seg.lower():
                                price_val, original_currency = parse_price(seg)
                        
                        if "shipping" in seg.lower() or "envío" in seg.lower() or "envio" in seg.lower():
                            ship_val, ship_curr = parse_price(seg)
                            if ship_val:
                                ship_rate = get_exchange_rate(ship_curr, "USD")
                                shipping_usd = ship_val * ship_rate
                                
                        if not bids_el and any(term in seg.lower() for term in ["bid", "puja", "pujas"]):
                            is_auc = True
                            match_b = re.search(r'(\d+)', seg)
                            if match_b:
                                bids_count = int(match_b.group(1))
                                
                    if not time_left or len(time_left) < 2:
                        time_left_seg = extract_time_left_from_segments(segments)
                        if time_left_seg:
                            time_left = time_left_seg
                            is_auc = True
                            
                    if time_left:
                        time_left_lower = time_left.lower()
                        for term in ["tiempo restante", "time left", "quedan", "queda", "restante", "restan", "resta", "remaining", "anuncio nuevo", "new listing"]:
                            time_left_lower = time_left_lower.replace(term, "")
                        time_left = re.sub(r'\(.*?\)', '', time_left_lower).strip()
                        
                    if not price_val:
                        continue
                        
                    rate = get_exchange_rate(original_currency, "USD")
                    price_usd = price_val * rate
                    total_price_usd = price_usd + shipping_usd
                    
                    # Location filter (Only keep items located in the United States)
                    is_us = True
                    is_fallback_domain = (current_domain != "ebay.com")
                    
                    found_us_indicator = False
                    has_from_indicator = False
                    
                    for seg in segments:
                        seg_lower = seg.lower()
                        if seg_lower.startswith("from ") or seg_lower.startswith("desde "):
                            has_from_indicator = True
                            loc_term = seg_lower.replace("from ", "").replace("desde ", "").strip()
                            if any(term in loc_term for term in ["united states", "ee. uu.", "ee.uu.", "ee uu", "estados unidos", "usa", "u.s.a."]):
                                found_us_indicator = True
                            else:
                                is_us = False
                                break
                                
                    if is_fallback_domain:
                        if not found_us_indicator:
                            is_us = False
                    else:
                        if has_from_indicator and not found_us_indicator:
                            is_us = False
                            
                    if not is_us:
                        continue

                    parsed.append({
                        "id": listing_id,
                        "model_id": gpu_config["id"] if gpu_config else "unknown",
                        "title": title,
                        "price_usd": total_price_usd,
                        "original_price": price_val,
                        "original_currency": original_currency,
                        "url": url,
                        "image_url": image_url,
                        "platform": "ebay",
                        "status": status,
                        "scraped_at": datetime.utcnow().isoformat(),
                        "is_auction": 1 if is_auc else 0,
                        "bids_count": bids_count,
                        "time_left": time_left
                    })
                else:
                    # Desktop layout
                    title_el = item.select_one('.s-item__title')
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    
                    link_el = item.select_one('.s-item__link')
                    if not link_el:
                        continue
                    url = link_el['href']
                    
                    match = re.search(r'/itm/(\d+)', url)
                    listing_id = f"ebay_{match.group(1)}" if match else f"ebay_{hash(url)}"
                    if match:
                        url = f"https://www.ebay.com/itm/{match.group(1)}"
                        
                    price_el = item.select_one('.s-item__price')
                    if not price_el:
                        continue
                    price_str = price_el.get_text(strip=True)
                    price_val, currency = parse_price(price_str)
                    if not price_val:
                        continue
                        
                    rate = get_exchange_rate(currency, "USD")
                    price_usd = price_val * rate
                    
                    shipping_usd = 0.0
                    ship_el = item.select_one('.s-item__shipping, .s-item__logisticsCost')
                    if ship_el:
                        ship_text = ship_el.get_text(strip=True)
                        if "free" not in ship_text.lower():
                            ship_val, ship_curr = parse_price(ship_text)
                            if ship_val:
                                ship_rate = get_exchange_rate(ship_curr, "USD")
                                shipping_usd = ship_val * ship_rate
                                
                    total_price_usd = price_usd + shipping_usd
                    img_el = item.select_one('.s-item__image-img, .s-item__image img')
                    image_url = img_el.get('src') or img_el.get('data-src') if img_el else None
                    
                    # Auction details
                    is_auc = (buying_format == 'auction')
                    bids_count = 0
                    time_left = None
                    
                    segments = [s.strip() for s in item.get_text(" | ").split(" | ")]
                    
                    bids_el = item.select_one('.s-item__bids, .s-item__bidCount, .s-card__bid-count, .s-card__bids, .s-card__bidCount')
                    if bids_el:
                        is_auc = True
                        bids_text = bids_el.get_text(strip=True)
                        match_b = re.search(r'(\d+)', bids_text)
                        if match_b:
                            bids_count = int(match_b.group(1))
                            
                    time_el = item.select_one('.s-item__time-left, .s-item__timeleft, .s-item__time, .s-card__time-left, .s-card__timeleft, .s-card__time')
                    if time_el:
                        is_auc = True
                        time_left = time_el.get_text(strip=True)
                    
                    if not bids_el:
                        for seg in segments:
                            if any(term in seg.lower() for term in ["bid", "puja", "pujas"]):
                                is_auc = True
                                match_b = re.search(r'(\d+)', seg)
                                if match_b:
                                    bids_count = int(match_b.group(1))
                                    break
                    
                    if not time_left or len(time_left) < 2:
                        time_left_seg = extract_time_left_from_segments(segments)
                        if time_left_seg:
                            time_left = time_left_seg
                            is_auc = True
                                
                    if time_left:
                        time_left_lower = time_left.lower()
                        for term in ["tiempo restante", "time left", "quedan", "queda", "restante", "restan", "resta", "remaining", "anuncio nuevo", "new listing"]:
                            time_left_lower = time_left_lower.replace(term, "")
                        time_left = re.sub(r'\(.*?\)', '', time_left_lower).strip()
                        
                    # Location filter (Only keep items located in the United States)
                    is_us = True
                    is_fallback_domain = (current_domain != "ebay.com")
                    
                    found_us_indicator = False
                    has_from_indicator = False
                    
                    for seg in segments:
                        seg_lower = seg.lower()
                        if seg_lower.startswith("from ") or seg_lower.startswith("desde "):
                            has_from_indicator = True
                            loc_term = seg_lower.replace("from ", "").replace("desde ", "").strip()
                            if any(term in loc_term for term in ["united states", "ee. uu.", "ee.uu.", "ee uu", "estados unidos", "usa", "u.s.a."]):
                                found_us_indicator = True
                            else:
                                is_us = False
                                break
                                
                    if is_fallback_domain:
                        if not found_us_indicator:
                            is_us = False
                    else:
                        if has_from_indicator and not found_us_indicator:
                            is_us = False
                            
                    if not is_us:
                        continue

                    parsed.append({
                        "id": listing_id,
                        "model_id": gpu_config["id"] if gpu_config else "unknown",
                        "title": title,
                        "price_usd": total_price_usd,
                        "original_price": price_val,
                        "original_currency": currency,
                        "url": url,
                        "image_url": image_url,
                        "platform": "ebay",
                        "status": status,
                        "scraped_at": datetime.utcnow().isoformat(),
                        "is_auction": 1 if is_auc else 0,
                        "bids_count": bids_count,
                        "time_left": time_left
                    })
            except Exception as pe:
                print(f"[Parser Debug] Exception parsing eBay item: {pe}")
                
        return parsed

    try:
        # 1. Attempt standard Desktop scraper
        r = attempt_request(use_mobile=False)
        parsed_listings = []
        if r.status_code == 200:
            parsed_listings = parse_html(r.text)
            
        # 2. Self-Healing Bypass: if desktop returned blocked code (e.g. 403) or 0 items, retry with Mobile Safari
        if r.status_code != 200 or not parsed_listings:
            print(f"eBay Desktop scraper returned status {r.status_code} with {len(parsed_listings)} items. Retrying with Mobile Safari bypass...")
            r = attempt_request(use_mobile=True)
            if r.status_code == 200:
                parsed_listings = parse_html(r.text)
                print(f"Mobile Safari bypass successfully scraped {len(parsed_listings)} items!")
                
        # 3. eBay Canada (ebay.ca) Fallback: if both failed or returned 0 listings (due to Akamai block), query ebay.ca
        if not parsed_listings:
            print("eBay.com search is blocked or returned 0 items. Attempting fallback query via eBay Canada (www.ebay.ca)...")
            try:
                current_domain = "ebay.ca"
                r_ca = requests.get("https://www.ebay.ca/sch/i.html", params=params, headers=mobile_headers, impersonate='safari', timeout=10)
                if r_ca.status_code == 200:
                    parsed_listings = parse_html(r_ca.text)
                    print(f"eBay Canada fallback successfully scraped {len(parsed_listings)} items!")
            except Exception as ca_err:
                print(f"eBay Canada fallback failed: {ca_err}")
                
        # 4. eBay Spain (ebay.es) Fallback: if CA failed or returned 0 listings, query ebay.es
        if not parsed_listings:
            print("eBay.ca search also returned 0 items. Attempting fallback query via eBay Spain (www.ebay.es)...")
            try:
                current_domain = "ebay.es"
                r_es = requests.get("https://www.ebay.es/sch/i.html", params=params, headers=mobile_headers, impersonate='safari', timeout=10)
                if r_es.status_code == 200:
                    parsed_listings = parse_html(r_es.text)
                    print(f"eBay Spain fallback successfully scraped {len(parsed_listings)} items!")
            except Exception as es_err:
                print(f"eBay Spain fallback failed: {es_err}")
                
        listings = parsed_listings[:max_items]
        
    except Exception as e:
        print(f"Exception during eBay scraping: {e}. Returning empty list.")
        return []
        
    return listings

def scrape_mercadolibre_html(query, site_id="MLM", max_items=50, gpu_config=None):
    """Scrapes MercadoLibre Mexico (or other regions) HTML search page for used listings."""
    formatted_query = query.replace(" ", "-")
    domain = "listado.mercadolibre.com.mx"
    if site_id == "MLA":
        domain = "listado.mercadolibre.com.ar"
    elif site_id == "MLB":
        domain = "lista.mercadolibre.com.br"
    elif site_id == "MCO":
        domain = "listado.mercadolibre.com.co"
    elif site_id == "CLP":
        domain = "listado.mercadolibre.cl"
        
    url = f"https://{domain}/{formatted_query}_Usado_NoIndex_True"
    
    # Use search engine crawler headers to bypass Snoopy verification challenges and login walls
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
    }
    
    listings = []
    try:
        r = requests.get(url, headers=headers, impersonate='chrome', timeout=10)
        if r.status_code != 200:
            print(f"MercadoLibre HTML scraper returned HTTP {r.status_code}")
            return []
            
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select('li.ui-search-layout__item')
        
        for item in items:
            title_el = item.select_one('a.poly-component__title') or item.select_one('.ui-search-item__title')
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            
            link_el = item.select_one('a.poly-component__title') or item.select_one('a.ui-search-link')
            if not link_el:
                continue
            item_url = link_el['href']
            
            match = re.search(r'ML[A-Z]-?(\d+)', item_url)
            item_id = f"ml_{site_id}{match.group(1)}" if match else f"ml_{hash(item_url)}"
            
            price_fraction_el = item.select_one('.poly-price__current .andes-money-amount__fraction') or item.select_one('.ui-search-price__part .andes-money-amount__fraction')
            if not price_fraction_el:
                continue
            price_text = price_fraction_el.get_text(strip=True)
            
            price_cents_el = item.select_one('.ui-search-price__part .andes-money-amount__cents')
            if price_cents_el:
                price_text += "." + price_cents_el.get_text(strip=True)
                
            price_val, currency = parse_price(price_text)
            if not price_val:
                continue
                
            # Default currency for the region
            currency = "MXN"
            if site_id == "MLA":
                currency = "ARS"
            elif site_id == "MLB":
                currency = "BRL"
            elif site_id == "MCO":
                currency = "COP"
                
            rate = get_exchange_rate(currency, "USD")
            price_usd = price_val * rate
            
            img_el = item.select_one('.poly-component__picture') or item.select_one('.ui-search-result-image__element')
            image_url = img_el.get('src') or img_el.get('data-src') if img_el else None
            
            listings.append({
                "id": item_id,
                "model_id": gpu_config["id"] if gpu_config else "unknown",
                "title": title,
                "price_usd": price_usd,
                "original_price": price_val,
                "original_currency": currency,
                "url": item_url,
                "image_url": image_url,
                "platform": "mercadolibre",
                "status": "active",
                "scraped_at": datetime.utcnow().isoformat()
            })
            
            if len(listings) >= max_items:
                break
                
    except Exception as e:
        print(f"Exception during MercadoLibre HTML scraping: {e}")
        
    return listings

def query_mercadolibre(query, site_id="MLM", max_items=50, gpu_config=None):
    """Queries MercadoLibre. Tries HTML scraper first, then fallback to JSON API, then simulated fallback."""
    print(f"Attempting MercadoLibre HTML scraping for: {query}")
    listings = scrape_mercadolibre_html(query, site_id=site_id, max_items=max_items, gpu_config=gpu_config)
    if listings:
        print(f"MercadoLibre HTML scraper successfully fetched {len(listings)} items.")
        return listings
        
    print("MercadoLibre HTML scraper failed or was blocked. Trying official API...")
    url = f"https://api.mercadolibre.com/sites/{site_id}/search"
    params = {
        "q": query,
        "condition": "used",
        "limit": max_items
    }
    
    try:
        r = requests.get(url, params=params, headers=get_headers(), impersonate='chrome', timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            
            for item in results:
                item_id = f"ml_{item.get('id')}"
                title = item.get("title")
                price_val = float(item.get("price", 0))
                currency = item.get("currency_id", "USD")
                url = item.get("permalink")
                image_url = item.get("thumbnail")
                
                if not price_val:
                    continue
                    
                rate = get_exchange_rate(currency, "USD")
                price_usd = price_val * rate
                
                listings.append({
                    "id": item_id,
                    "model_id": gpu_config["id"] if gpu_config else "unknown",
                    "title": title,
                    "price_usd": price_usd,
                    "original_price": price_val,
                    "original_currency": currency,
                    "url": url,
                    "image_url": image_url,
                    "platform": "mercadolibre",
                    "status": "active",
                    "scraped_at": datetime.utcnow().isoformat()
                })
                
            if listings:
                print(f"MercadoLibre API successfully fetched {len(listings)} items.")
                return listings
                
        else:
            print(f"MercadoLibre API returned status code {r.status_code}")
            
    except Exception as e:
        print(f"Exception during MercadoLibre API query: {e}")
        
    print("Both HTML scraping and API failed (IP likely blocked). Returning empty list.")
    return []

def scrape_bestbuy(query, max_items=20, gpu_config=None):
    """Scrapes Best Buy USA by parsing the Apollo GraphQL cache embedded in the search page HTML.
    Extracts product name ('short' field) + customerPrice + skuId from the page's JS data."""
    formatted_query = query.replace(" ", "+")
    listings = []

    bestbuy_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "cross-site",
    }

    def parse_apollo_cache(html_text):
        """Extract products from Best Buy's Apollo/GraphQL cache embedded in the page JS."""
        results = []
        seen_skus = set()

        # Best Buy embeds product data in Apollo cache via window[Symbol.for("ApolloSSRDataTransport")]
        # Structure: ..."short":"PRODUCT NAME"...then later..."customerPrice":PRICE,"skuId":"SKU"...
        # We extract all name blocks and match them to the following price+sku block

        # Step 1: Extract all (name, position) pairs
        name_pattern = re.compile(r'"short"\s*:\s*"([^"]{5,200})"')
        price_sku_pattern = re.compile(r'customerPrice"\s*:\s*(\d+\.?\d*)\s*,\s*"skuId"\s*:\s*"(\d+)"')

        # Collect all names with their positions
        names_with_pos = [(m.start(), m.group(1)) for m in name_pattern.finditer(html_text)]
        # Collect all price+SKU pairs with positions
        prices_with_pos = [(m.start(), float(m.group(1)), m.group(2)) for m in price_sku_pattern.finditer(html_text)]

        # Match each name to the closest following price (within 10000 chars)
        for name_pos, name in names_with_pos:
            # Find the next price after this name
            for price_pos, price, sku in prices_with_pos:
                if price_pos > name_pos and price_pos - name_pos < 10000:
                    if sku not in seen_skus and 30 < price < 15000:
                        seen_skus.add(sku)
                        # Determine condition from URL context around the SKU
                        sku_ctx = html_text[max(0, price_pos-2000):price_pos+200]
                        is_openbox = "openbox" in sku_ctx.lower() or "open-box" in sku_ctx.lower() or "openBoxCondition" in sku_ctx
                        condition = "Open Box" if is_openbox else "New"

                        # Extract image URL near the name
                        img_m = re.search(r'piscesHref"\s*:\s*"(https://pisces\.bbystatic\.com[^"]+\.(?:png|jpg|jpeg|webp))"',
                                          html_text[name_pos:name_pos+2000])
                        img_url = img_m.group(1) if img_m else None

                        item_url = f"https://www.bestbuy.com/site/product/{sku}.p?skuId={sku}"
                        results.append({
                            "id": f"bestbuy_{sku}",
                            "model_id": gpu_config["id"] if gpu_config else "unknown",
                            "title": f"[Best Buy {condition}] {name}",
                            "price_usd": round(price, 2),
                            "original_price": round(price, 2),
                            "original_currency": "USD",
                            "url": item_url,
                            "image_url": img_url,
                            "platform": "bestbuy",
                            "status": "active",
                            "scraped_at": datetime.utcnow().isoformat(),
                            "is_auction": 0,
                            "bids_count": 0,
                            "time_left": None
                        })
                    break  # Move to next name after first match
        return results

    search_urls = [
        f"https://www.bestbuy.com/site/searchpage.jsp?st={formatted_query}+graphics+card&intl=nosplash",
        f"https://www.bestbuy.com/site/searchpage.jsp?st={formatted_query}+gpu&intl=nosplash",
    ]

    for search_url in search_urls:
        try:
            r = requests.get(search_url, headers=bestbuy_headers, impersonate="chrome", timeout=15)
            if r.status_code == 200 and len(r.text) > 50000:
                parsed = parse_apollo_cache(r.text)
                listings.extend(parsed)
                if parsed:
                    print(f"Best Buy scraped {len(parsed)} items from: {search_url[-60:]}")
                    break  # one successful URL is enough
            else:
                print(f"Best Buy returned HTTP {r.status_code} for: {search_url[-60:]}")
        except Exception as e:
            print(f"Best Buy scraping exception: {e}")

    if not listings:
        print(f"Best Buy: no results for '{query}'. Returning empty list.")
    else:
        print(f"Best Buy total: {len(listings)} listings for '{query}'")
    return listings[:max_items]

def generate_simulated_facebook_listings(gpu_config, city_slug, count=10):
    """Generates realistic Facebook Marketplace simulated listings for specific Mexican cities."""
    listings = []
    if not gpu_config:
        gpu_config = {
            "id": "generic_gpu",
            "name": "Generic GPU",
            "min_price_usd": 100,
            "max_price_usd": 500
        }
        
    gpu_id = gpu_config["id"]
    gpu_name = gpu_config["name"]
    min_p = gpu_config["min_price_usd"]
    max_p = gpu_config["max_price_usd"]
    
    # Facebook local listings are often a bit cheaper than retail ML/eBay due to cash/no shipping
    # Let's skew it slightly lower
    center = min_p + (max_p - min_p) * 0.38
    std_dev = (max_p - min_p) * 0.10
    
    city_names = {
        "culiacan": "Culiacán",
        "losmochis": "Los Mochis",
        "tijuana": "Tijuana",
        "guadalajara": "Guadalajara"
    }
    city_name = city_names.get(city_slug, city_slug.capitalize())
    
    brands = ["ASUS ROG Strix", "EVGA XC3", "Gigabyte Gaming OC", "MSI Ventus 3X", "Zotac Trinity", "PNY XLR8", "ASUS TUF"]
    if "rx" in gpu_id:
        brands = ["PowerColor Hellhound", "Sapphire NITRO+", "XFX Speedster", "ASUS ROG Strix", "MSI Gaming X", "Gigabyte Gaming OC"]
        
    conditions = ["Trato directo", "Entrego en plaza", "Como nueva en caja", "Funciona al 100", "Poco uso", "Solo efectivo", "Probada en mi casa"]
    
    # VRAM
    vram = "8GB"
    if "5090" in gpu_id:
        vram = "32GB"
    elif "4090" in gpu_id or "3090" in gpu_id:
        vram = "24GB"
    elif "5080" in gpu_id or "4080" in gpu_id or "7900" in gpu_id or "6800" in gpu_id or "7800" in gpu_id or "v100" in gpu_id:
        vram = "16GB"
    elif "4070" in gpu_id or "3080" in gpu_id or "3060" in gpu_id or "6700" in gpu_id:
        vram = "12GB"
    elif "2060" in gpu_id or "1060" in gpu_id:
        vram = "6GB"
        
    for i in range(count):
        price = random.normalvariate(center, std_dev)
        price = max(min_p, min(max_p, price))
        
        # Occasional local hot deal (30% cheaper)
        if i == 0 and random.random() < 0.35:
            price = min_p + (center - min_p) * 0.25
            
        title = f"[Venta Local - {city_name}] {gpu_name} {random.choice(brands)} {vram} - {random.choice(conditions)}"
        url = f"https://www.facebook.com/marketplace/{city_slug}/item/simulated_{gpu_id}_{i}_{random.randint(1000,9999)}"
        
        # Local FB is in MXN
        currency = "MXN"
        original_price = price * 17.4 # 17.4 exchange rate
        
        img_url = "https://img.icons8.com/color/96/nvidia.png" if ("rtx" in gpu_id or "gtx" in gpu_id) else "https://img.icons8.com/color/96/amd.png"
        
        listings.append({
            "id": f"facebook_sim_{gpu_id}_{city_slug}_{i}_{random.randint(100000,999999)}",
            "model_id": gpu_id,
            "title": title,
            "price_usd": round(price, 2),
            "original_price": round(original_price, 2),
            "original_currency": currency,
            "url": url,
            "image_url": img_url,
            "platform": "facebook",
            "status": "active",
            "scraped_at": datetime.utcnow().isoformat()
        })
        
    return listings

def parse_facebook_json(html_text):
    import json
    listings = []
    
    script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
    for match in script_pattern.finditer(html_text):
        script_content = match.group(1).strip()
        if not script_content or "marketplace_search" not in script_content:
            continue
            
        try:
            if '=' in script_content:
                start_idx = script_content.find('{')
                end_idx = script_content.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    script_content = script_content[start_idx:end_idx+1]
            
            data = json.loads(script_content)
            
            def find_listings(obj):
                if isinstance(obj, dict):
                    # Check if it has title and price keys
                    title = obj.get('marketplace_listing_title') or obj.get('listing_title') or obj.get('custom_title') or obj.get('title')
                    price_obj = obj.get('listing_price') or obj.get('price')
                    
                    price_str = None
                    if price_obj and isinstance(price_obj, dict):
                        # Prefer 'amount' (e.g. '3500.00') over 'formatted_amount' (e.g. 'MX$3.500') to avoid parsing errors
                        price_str = price_obj.get('amount') or price_obj.get('formatted_amount')
                    elif isinstance(price_obj, (str, int, float)):
                        price_str = str(price_obj)
                        
                    listing_id = obj.get('id')
                    
                    if title and price_str and listing_id:
                        photo_obj = obj.get('primary_listing_photo') or obj.get('primary_photo')
                        img_url = None
                        if photo_obj and isinstance(photo_obj, dict):
                            img_obj = photo_obj.get('image') or photo_obj.get('photo')
                            if img_obj and isinstance(img_obj, dict):
                                img_url = img_obj.get('uri')
                                
                        url = f"https://www.facebook.com/marketplace/item/{listing_id}/"
                        
                        # Avoid duplicates
                        if not any(x['id'] == f"facebook_{listing_id}" for x in listings):
                            listings.append({
                                "title": title,
                                "price_str": price_str,
                                "image_url": img_url,
                                "url": url,
                                "id": f"facebook_{listing_id}"
                            })
                            # We can return because we found a listing object
                            return
                    
                    for k, v in obj.items():
                        find_listings(v)
                elif isinstance(obj, list):
                    for item in obj:
                        find_listings(item)
                        
            find_listings(data)
        except Exception:
            continue
            
    return listings

def scrape_facebook_marketplace(query, city_slug="culiacan", max_items=20, gpu_config=None):
    """Scrapes Facebook Marketplace. Since FB blocks cloud IPs or requires login, falls back to simulated local listings."""
    url = f"https://www.facebook.com/marketplace/{city_slug}/search"
    params = {"query": query}
    
    city_names = {
        "culiacan": "Culiacán",
        "losmochis": "Los Mochis",
        "tijuana": "Tijuana",
        "guadalajara": "Guadalajara"
    }
    city_name_formatted = city_names.get(city_slug, city_slug.capitalize())
    
    listings = []
    try:
        r = requests.get(url, params=params, headers=get_headers(), impersonate='chrome', timeout=10)
        if r.status_code == 200:
            parsed_items = parse_facebook_json(r.text)
            print(f"[DEBUG] Facebook Marketplace 200 OK for {city_name_formatted}. Parsed JSON items: {len(parsed_items)}")
            for item in parsed_items:
                price_val, currency = parse_price(item["price_str"])
                if not price_val:
                    continue
                # Local Facebook Marketplace in Mexico is always in MXN
                currency = "MXN"
                    
                rate = get_exchange_rate(currency, "USD")
                price_usd = price_val * rate
                
                listings.append({
                    "id": item["id"],
                    "model_id": gpu_config["id"] if gpu_config else "unknown",
                    "title": f"[Venta Local - {city_name_formatted}] {item['title']}",
                    "price_usd": price_usd,
                    "original_price": price_val,
                    "original_currency": currency,
                    "url": item["url"],
                    "image_url": item["image_url"],
                    "platform": "facebook",
                    "status": "active",
                    "scraped_at": datetime.utcnow().isoformat()
                })
                if len(listings) >= max_items:
                    break
            
            print(f"Facebook Marketplace HTML scraper parsed {len(listings)} items for {city_name_formatted}.")
            return listings
        else:
            print(f"[DEBUG] Facebook Marketplace request failed with status code {r.status_code} for {city_name_formatted}.")
                    
        print(f"Facebook Marketplace HTML returned block page {r.status_code} for {city_name_formatted}. Returning empty list.")
        return []
            
    except Exception as e:
        print(f"Exception during Facebook Marketplace scraping: {e}. Returning empty list.")
        return []

def clean_and_filter_listings(raw_listings, gpu_config, global_negatives):
    """Filters out accessory items, boxes, scam listings, and items out of price boundaries."""
    filtered = []
    min_price = gpu_config.get("min_price_usd", 0)
    max_price = gpu_config.get("max_price_usd", 99999)
    gpu_id = gpu_config.get("id", "")
    gpu_name = gpu_config.get("name", "").lower()

    # --- Dynamic model number extraction from gpu_id ---
    # Extract all digit-only tokens from the ID, e.g.:
    #   "rx_6600"      -> ["6600"]
    #   "rtx_3090"     -> ["3090"]
    #   "rtx_3060_ti"  -> ["3060"]
    #   "tesla_v100"   -> ["100"]  (handled specially below as "v100")
    numeric_tokens = re.findall(r'\d+', gpu_id)
    # Special case: "v100" must appear as "v100" (not just "100") to avoid matching "1080 Ti"
    if "v100" in gpu_id:
        numeric_tokens = ["v100"]

    # Simple keyword regex for exclusion
    exclusion_patterns = [re.compile(rf"\b{word}\b", re.IGNORECASE) for word in global_negatives]

    for item in raw_listings:
        title = item["title"]
        price = item["price_usd"]
        words = title.lower()

        # 1. Price Bounds Filter
        if price < min_price or price > max_price:
            continue

        # 2. Exclude negative keywords
        excluded = False
        for pattern in exclusion_patterns:
            if pattern.search(title):
                excluded = True
                break
        if excluded:
            continue

        # 3. Dynamic model-number check — every numeric token from the GPU ID must
        #    appear in the listing title. This prevents e.g. an "RX 580" listing from
        #    matching a scan for "RX 6600" because "6600" won't be in the title.
        model_match = all(token in words for token in numeric_tokens)
        if not model_match:
            continue

        filtered.append(item)

    return filtered

def verify_listing_active(platform, listing_id, url=None):
    """Verifies if a listing is still active on its respective platform.
    Returns:
      True if active,
      False if sold/ended/deleted,
      None if inconclusive (e.g. connection error, rate limit).
    """
    if "sim" in listing_id or "test" in listing_id:
        return True
        
    platform = platform.lower()
    
    if platform == "mercadolibre":
        ml_id = listing_id.replace("ml_", "")
        try:
            r = std_requests.get(f"https://api.mercadolibre.com/items/{ml_id}", timeout=5)
            if r.status_code == 200:
                data = r.json()
                status = data.get("status")
                if status == "active":
                    return True
                else:
                    return False
            elif r.status_code == 404:
                return False
        except Exception as e:
            print(f"[Verification ML] Exception for {listing_id}: {e}")
        return None

    elif platform == "ebay":
        num_id = listing_id.replace("ebay_", "")
        item_url = url or f"https://www.ebay.com/itm/{num_id}"
        try:
            r = requests.get(item_url, headers=get_headers(), impersonate='safari', timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                text_lower = soup.get_text().lower()
                
                ended_phrases = [
                    "this listing has ended",
                    "este anuncio ha finalizado",
                    "this item is out of stock",
                    "bidding has ended",
                    "la subasta de este artículo ha finalizado",
                    "this item was sold",
                    "este artículo se ha vendido"
                ]
                
                if any(phrase in text_lower for phrase in ended_phrases):
                    return False
                
                ended_banners = soup.select('.msg-content, .msg-header, .non-active, .msg-header__title')
                if ended_banners:
                    banner_text = " ".join([b.get_text().lower() for b in ended_banners])
                    if any(w in banner_text for w in ["ended", "finalizado", "sold", "vendido", "no disponible", "out of stock"]):
                        return False
                        
                return True
            elif r.status_code == 404:
                return False
        except Exception as e:
            print(f"[Verification eBay] Exception for {listing_id}: {e}")
        return None

    elif platform == "bestbuy":
        sku = listing_id.replace("bestbuy_", "")
        item_url = url or f"https://www.bestbuy.com/site/{sku}.p?skuId={sku}"
        try:
            r = requests.get(item_url, headers=get_headers(), impersonate='chrome', timeout=10)
            if r.status_code == 200:
                text_lower = r.text.lower()
                
                sold_phrases = [
                    "sold out",
                    "unavailable",
                    "agotado",
                    "no disponible"
                ]
                if any(phrase in text_lower for phrase in sold_phrases):
                    return False
                
                if "add to cart" not in text_lower and "añadir al carrito" not in text_lower:
                    return False
                    
                return True
            elif r.status_code == 404:
                return False
        except Exception as e:
            print(f"[Verification Best Buy] Exception for {listing_id}: {e}")
        return None

    elif platform == "facebook":
        fb_id = listing_id.replace("facebook_", "")
        item_url = url or f"https://www.facebook.com/marketplace/item/{fb_id}/"
        try:
            r = requests.get(item_url, headers=get_headers(), impersonate='safari', timeout=10)
            if r.status_code == 200:
                text_lower = r.text.lower()
                
                sold_phrases = [
                    "este artículo ya no está disponible",
                    "this item is no longer available",
                    "este anuncio se ha eliminado",
                    "anuncio finalizado",
                    "no está disponible"
                ]
                if any(phrase in text_lower for phrase in sold_phrases):
                    return False
                return True
            elif r.status_code == 404:
                return False
        except Exception as e:
            print(f"[Verification Facebook] Exception for {listing_id}: {e}")
        return None

    return True
