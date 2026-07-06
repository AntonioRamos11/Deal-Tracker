import sqlite3
import os
from datetime import datetime

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpu_tracker.db")

def get_db_connection(db_path=DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=DEFAULT_DB_PATH):
    """Initializes the SQLite database with required tables and handles schema migrations."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Check if table exists and inspect columns
    cursor.execute("PRAGMA table_info(listings)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if not columns:
        # Table for storing scraped listings
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            title TEXT NOT NULL,
            price_usd REAL NOT NULL,
            original_price REAL,
            original_currency TEXT,
            url TEXT NOT NULL,
            image_url TEXT,
            platform TEXT NOT NULL, -- 'ebay', 'mercadolibre', 'facebook'
            status TEXT NOT NULL, -- 'active', 'sold'
            scraped_at TEXT NOT NULL,
            is_auction INTEGER DEFAULT 0,
            bids_count INTEGER DEFAULT 0,
            time_left TEXT
        )
        """)
    else:
        # Alter table to add auction columns if missing (self-migration)
        if "is_auction" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN is_auction INTEGER DEFAULT 0")
        if "bids_count" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN bids_count INTEGER DEFAULT 0")
        if "time_left" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN time_left TEXT")
            
    # Table for storing historical calculations of GPU prices
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS statistics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT NOT NULL,
        calculated_at TEXT NOT NULL,
        mode_price_usd REAL NOT NULL,
        median_price_usd REAL NOT NULL,
        mean_price_usd REAL NOT NULL,
        min_price_usd REAL NOT NULL,
        max_price_usd REAL NOT NULL,
        sample_count INTEGER NOT NULL
    )
    """)
    
    # Table for storing already alerted deals to avoid duplicates
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        listing_id TEXT PRIMARY KEY,
        model_id TEXT NOT NULL,
        price_usd REAL NOT NULL,
        discount_percent REAL NOT NULL,
        alerted_at TEXT NOT NULL,
        FOREIGN KEY (listing_id) REFERENCES listings(id)
    )
    """)
    
    # Create indexes for fast query execution
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_listings_model_status ON listings(model_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_listings_scraped ON listings(scraped_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_model_date ON statistics(model_id, calculated_at)")
    
    conn.commit()
    conn.close()

def save_listings(listings, db_path=DEFAULT_DB_PATH):
    """Inserts or replaces listings into the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    inserted_or_updated = 0
    for l in listings:
        try:
            cursor.execute("""
            INSERT OR REPLACE INTO listings 
            (id, model_id, title, price_usd, original_price, original_currency, url, image_url, platform, status, scraped_at, is_auction, bids_count, time_left)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                l['id'], l['model_id'], l['title'], l['price_usd'],
                l.get('original_price'), l.get('original_currency'),
                l['url'], l.get('image_url'), l['platform'], l['status'],
                l.get('scraped_at') or datetime.utcnow().isoformat(),
                l.get('is_auction', 0), l.get('bids_count', 0), l.get('time_left')
            ))
            inserted_or_updated += 1
        except Exception as e:
            print(f"Error inserting listing {l.get('id')}: {e}")
            
    conn.commit()
    conn.close()
    return inserted_or_updated

def get_active_auctions(model_id=None, limit=100, db_path=DEFAULT_DB_PATH):
    """Gets active eBay auctions from database, ordered by scraped timestamp or margin."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if model_id:
        cursor.execute("""
        SELECT * FROM listings 
        WHERE model_id = ? AND status = 'active' AND is_auction = 1
        ORDER BY scraped_at DESC
        LIMIT ?
        """, (model_id, limit))
    else:
        cursor.execute("""
        SELECT * FROM listings 
        WHERE status = 'active' AND is_auction = 1
        ORDER BY scraped_at DESC
        LIMIT ?
        """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_stats(model_id, stats, db_path=DEFAULT_DB_PATH):
    """Saves calculations of market prices for a GPU model."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT INTO statistics 
    (model_id, calculated_at, mode_price_usd, median_price_usd, mean_price_usd, min_price_usd, max_price_usd, sample_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        model_id,
        datetime.utcnow().isoformat(),
        stats['mode_price_usd'],
        stats['median_price_usd'],
        stats['mean_price_usd'],
        stats['min_price_usd'],
        stats['max_price_usd'],
        stats['sample_count']
    ))
    
    conn.commit()
    conn.close()

def get_latest_stats(model_id=None, db_path=DEFAULT_DB_PATH):
    """Gets the latest calculated statistics. If model_id is None, returns a dict of all models."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    if model_id:
        cursor.execute("""
        SELECT * FROM statistics 
        WHERE model_id = ? 
        ORDER BY calculated_at DESC 
        LIMIT 1
        """, (model_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    else:
        # Get latest stats for each model
        cursor.execute("""
        SELECT s1.* FROM statistics s1
        INNER JOIN (
            SELECT model_id, MAX(calculated_at) as max_date 
            FROM statistics 
            GROUP BY model_id
        ) s2 ON s1.model_id = s2.model_id AND s1.calculated_at = s2.max_date
        """)
        rows = cursor.fetchall()
        conn.close()
        return {row['model_id']: dict(row) for row in rows}

def has_been_alerted(listing_id, db_path=DEFAULT_DB_PATH):
    """Checks if a listing has already triggered an alert."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM alerts WHERE listing_id = ?", (listing_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def mark_as_alerted(listing_id, model_id, price_usd, discount_percent, db_path=DEFAULT_DB_PATH):
    """Records an alert event to prevent future duplicates."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO alerts (listing_id, model_id, price_usd, discount_percent, alerted_at)
        VALUES (?, ?, ?, ?, ?)
        """, (listing_id, model_id, price_usd, discount_percent, datetime.utcnow().isoformat()))
        conn.commit()
    except Exception as e:
        print(f"Error marking alert: {e}")
    finally:
        conn.close()

def get_recent_deals(limit=20, db_path=DEFAULT_DB_PATH):
    """Gets recently alerted deals, joining with the listings table to get info."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT a.*, l.title, l.url, l.image_url, l.platform, l.original_price, l.original_currency
    FROM alerts a
    JOIN listings l ON a.listing_id = l.id
    ORDER BY a.alerted_at DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_listings_for_stats(model_id, status='sold', limit=200, db_path=DEFAULT_DB_PATH):
    """Gets historical listings to calculate stats baseline."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT price_usd FROM listings
    WHERE model_id = ? AND status = ?
    ORDER BY scraped_at DESC
    LIMIT ?
    """, (model_id, status, limit))
    rows = cursor.fetchall()
    conn.close()
    return [row['price_usd'] for row in rows]

def purge_old_listings(days=30, db_path=DEFAULT_DB_PATH):
    """Cleans up raw data that is older than X days to keep DB size optimal."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    # Do not delete listings that are referenced in alerts!
    cursor.execute("""
    DELETE FROM listings 
    WHERE scraped_at < datetime('now', ?) 
      AND id NOT IN (SELECT listing_id FROM alerts)
    """, (f"-{days} days",))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

def purge_simulated_listings(db_path=DEFAULT_DB_PATH):
    """Removes any simulated/fake listings from the database (IDs or URLs containing 'simulated')."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    # Remove simulated alerts first (FK constraint)
    cursor.execute("""
    DELETE FROM alerts 
    WHERE listing_id LIKE '%sim%' OR listing_id LIKE '%simulated%'
    """)
    # Remove simulated listings
    cursor.execute("""
    DELETE FROM listings 
    WHERE id LIKE '%sim%' OR id LIKE '%simulated%'
       OR url LIKE '%simulated%'
    """)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"[DB] Purged {deleted} simulated listings from database.")
    return deleted

def delete_all_deals(db_path=DEFAULT_DB_PATH):
    """Clears all records from the alerts table (deals history). Listings data is preserved."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

def delete_alert(listing_id, db_path=DEFAULT_DB_PATH):
    """Deletes an alert record from the alerts table."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE listing_id = ?", (listing_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

def get_all_alerts(db_path=DEFAULT_DB_PATH):
    """Gets all current alerted deals, joining with the listings table to get info."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT a.listing_id, a.alerted_at, l.platform, l.url, l.id
    FROM alerts a
    JOIN listings l ON a.listing_id = l.id
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_active_listings_for_model(model_id, db_path=DEFAULT_DB_PATH):
    """Clears old active listings for a model to keep data fresh, 
    preserving those referenced in alerts by setting their status to 'inactive'."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        # Delete active listings that are NOT referenced in alerts (to keep database size small)
        cursor.execute("""
        DELETE FROM listings 
        WHERE model_id = ? AND status = 'active'
          AND id NOT IN (SELECT listing_id FROM alerts)
        """, (model_id,))
        # Update remaining active listings (which are referenced in alerts) to 'inactive'
        cursor.execute("""
        UPDATE listings 
        SET status = 'inactive'
        WHERE model_id = ? AND status = 'active'
        """, (model_id,))
        conn.commit()
    except Exception as e:
        print(f"Error clearing active listings for {model_id}: {e}")
    finally:
        conn.close()
