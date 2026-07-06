import scrapers as scr

query = 'RTX 3090 24GB'
gpu = {'id': 'rtx_3090', 'name': 'NVIDIA RTX 3090', 'min_price_usd': 400, 'max_price_usd': 1200}

print("Testing scrape_ebay directly (active auctions)...")
listings = scr.scrape_ebay(query, status='active', buying_format='auction', max_items=10, gpu_config=gpu)
print("Scrape count returned:", len(listings))
for i, item in enumerate(listings[:5]):
    print(f"{i+1}. {item['title'][:50]}... | Price: ${item['price_usd']:.2f} USD | Bids: {item['bids_count']} | Time: {item['time_left']}")
