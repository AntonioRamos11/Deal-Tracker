import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpu_tracker.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get stats
cursor.execute("""
SELECT s1.* FROM statistics s1
INNER JOIN (
    SELECT model_id, MAX(calculated_at) as max_date 
    FROM statistics 
    GROUP BY model_id
) s2 ON s1.model_id = s2.model_id AND s1.calculated_at = s2.max_date
""")
stats = {row['model_id']: row['mode_price_usd'] for row in cursor.fetchall()}
print("Baselines (Mode Price USD):", stats)

print("\n--- All Active Listings in DB ---")
cursor.execute("SELECT id, model_id, title, price_usd, platform, is_auction, time_left FROM listings WHERE status = 'active'")
rows = cursor.fetchall()
for idx, r in enumerate(rows):
    baseline = stats.get(r['model_id'], 0.0)
    discount_pct = 0.0
    if baseline > 0:
        discount_pct = (baseline - r['price_usd']) / baseline
    print(f"{idx+1}. Model: {r['model_id']} | Platform: {r['platform']} | Title: {r['title'][:40]}... | Price: ${r['price_usd']:.2f} USD | Baseline: ${baseline:.2f} | Discount: {discount_pct*100:.1f}% | Auction: {r['is_auction']} | Time: {r['time_left']}")

conn.close()
