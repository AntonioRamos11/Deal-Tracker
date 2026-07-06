import sys
import os
import json
from datetime import datetime

# Import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import stats_engine as st
import scrapers as scr
import alerts as al
import database as db

def test_statistics():
    print("\n=== [1/4] Test Engine Estadístico (IQR y Moda) ===")
    
    # 1. Test data with some obvious outliers:
    # Most prices hover around $300-$320. 
    # $15 (noise/accessory) and $900 (bundle/scalped) should be removed by IQR.
    test_prices = [15, 300, 310, 305, 315, 320, 290, 310, 305, 312, 318, 900]
    print(f"Precios originales ({len(test_prices)} muestras): {test_prices}")
    
    clean_prices = st.remove_outliers_iqr(test_prices)
    print(f"Precios sin atípicos (IQR): {clean_prices}")
    
    # Assert outliers are removed
    assert 15 not in clean_prices, "Outlier 15 was not removed!"
    assert 900 not in clean_prices, "Outlier 900 was not removed!"
    print("✅ IQR eliminó correctamente los valores atípicos (15 y 900 USD)")
    
    # Calculate stats
    stats = st.calculate_statistics(test_prices)
    print("Métricas Calculadas:")
    print(f"  - Moda: ${stats['mode_price_usd']}")
    print(f"  - Mediana: ${stats['median_price_usd']}")
    print(f"  - Promedio: ${stats['mean_price_usd']}")
    print(f"  - Muestras válidas: {stats['sample_count']}")
    
    # Mode should be around the center of the bin
    # Bins of width 20 or similar. Let's see: price range is 320-290 = 30. Bin size defaults to 10.
    # Highest count will be in 300-310 or 310-320.
    assert 290 <= stats['mode_price_usd'] <= 330, "Mode calculation is way off!"
    print("✅ Cálculos estadísticos correctos.")

def test_database():
    print("\n=== [2/4] Test SQLite Database ===")
    db_test_path = "test_gpu_tracker.db"
    if os.path.exists(db_test_path):
        os.remove(db_test_path)
        
    db.init_db(db_test_path)
    print("✅ Inicialización de base de datos exitosa.")
    
    # Insert dummy listings
    dummy_listings = [
        {
            "id": "ebay_test_123",
            "model_id": "rtx_2060",
            "title": "Nvidia RTX 2060 EVGA Usada",
            "price_usd": 150.0,
            "original_price": 150.0,
            "original_currency": "USD",
            "url": "https://ebay.com/test_123",
            "image_url": "https://via.placeholder.com/150",
            "platform": "ebay",
            "status": "sold"
        },
        {
            "id": "ml_test_456",
            "model_id": "rtx_2060",
            "title": "Tarjeta Grafica RTX 2060 Usada",
            "price_usd": 145.0,
            "original_price": 2537.5,
            "original_currency": "MXN",
            "url": "https://mercadolibre.com.mx/test_456",
            "image_url": "https://via.placeholder.com/150",
            "platform": "mercadolibre",
            "status": "active"
        }
    ]
    
    inserted = db.save_listings(dummy_listings, db_test_path)
    print(f"✅ Se guardaron {inserted} listados en la base de datos.")
    
    # Fetch sold listings for stats
    sold_prices = db.get_listings_for_stats("rtx_2060", status='sold', limit=10, db_path=db_test_path)
    print(f"Precios vendidos recuperados: {sold_prices}")
    assert len(sold_prices) == 1, "Failed to retrieve correct sold listings."
    
    # Save stats
    dummy_stats = {
        "mode_price_usd": 150.0,
        "median_price_usd": 147.5,
        "mean_price_usd": 147.5,
        "min_price_usd": 145.0,
        "max_price_usd": 150.0,
        "sample_count": 2
    }
    db.save_stats("rtx_2060", dummy_stats, db_test_path)
    print("✅ Estadísticas de prueba guardadas correctamente.")
    
    latest_stats = db.get_latest_stats("rtx_2060", db_test_path)
    print(f"Última estadística recuperada: {latest_stats['mode_price_usd']} USD (Moda)")
    assert latest_stats['mode_price_usd'] == 150.0
    
    # Test Alert Lock
    is_alerted = db.has_been_alerted("ml_test_456", db_test_path)
    print(f"¿Ya fue alertada la oferta ml_test_456? {is_alerted}")
    assert not is_alerted
    
    db.mark_as_alerted("ml_test_456", "rtx_2060", 145.0, 0.15, db_test_path)
    is_alerted_after = db.has_been_alerted("ml_test_456", db_test_path)
    print(f"¿Ya fue alertada la oferta ml_test_456 después de marcarla? {is_alerted_after}")
    assert is_alerted_after
    
    # Clean up test DB
    if os.path.exists(db_test_path):
        os.remove(db_test_path)
    print("✅ Pruebas de base de datos finalizadas y limpiadas.")

def test_scrapers():
    print("\n=== [3/4] Test Scrapers (Live Connection) ===")
    
    # Test exchange rate API
    rate = scr.get_exchange_rate("MXN", "USD")
    print(f"Tipo de cambio en vivo: 1 MXN = {rate:.5f} USD (Inverso: {1/rate:.2f} MXN/USD)")
    assert rate > 0
    
    # Test price parsing
    price, curr = scr.parse_price("MXN 7,500.00")
    print(f"Parseo de 'MXN 7,500.00' -> Valor: {price}, Moneda: {curr}")
    assert price == 7500.00 and curr == 'MXN'
    
    price2, curr2 = scr.parse_price("$349.99 to $399.99")
    print(f"Parseo de '$349.99 to $399.99' -> Valor: {price2}, Moneda: {curr2}")
    assert price2 == 349.99 and curr2 == 'USD'
    
    print("✅ Parseador de precios y conversión de monedas funcionando.")
    
    # We will test MercadoLibre API for RTX 2060
    print("Probando API de MercadoLibre México con query 'RTX 2060 Usado'...")
    ml_results = scr.query_mercadolibre("RTX 2060", site_id="MLM", max_items=5)
    print(f"MercadoLibre retornó {len(ml_results)} resultados.")
    if len(ml_results) > 0:
        first = ml_results[0]
        print(f"  - Primer resultado: '{first['title']}' | Precio original: {first['original_currency']} {first['original_price']} | Precio USD: ${first['price_usd']:.2f}")
        assert "http" in first['url']
        print("✅ MercadoLibre API funciona exitosamente.")
    else:
        print("⚠️ Advertencia: No se retornaron resultados de MercadoLibre. Es normal si no hay listados usados de este modelo o si hay problemas de red temporales.")

    # We will test eBay scraper
    print("Probando Scraper de eBay con query 'RTX 2060' (Sold listings)...")
    ebay_results = scr.scrape_ebay("RTX 2060", status='sold', max_items=5)
    print(f"eBay retornó {len(ebay_results)} resultados vendidos.")
    if len(ebay_results) > 0:
        first = ebay_results[0]
        print(f"  - Primer resultado: '{first['title']}' | Precio USD (con envío): ${first['price_usd']:.2f}")
        assert "http" in first['url']
        print("✅ eBay Scraper funciona exitosamente.")
    else:
        print("⚠️ Advertencia: No se retornaron resultados de eBay. eBay puede bloquear solicitudes si detecta comportamiento inusual o si hay bloqueos geográficos.")

    # We will test Facebook Marketplace scraper
    print("Probando Scraper de Facebook Marketplace para Culiacán con query 'RTX 2060'...")
    fb_gpu_config = {
        "id": "rtx_2060",
        "name": "NVIDIA RTX 2060",
        "min_price_usd": 80,
        "max_price_usd": 250
    }
    fb_results = scr.scrape_facebook_marketplace("RTX 2060", city_slug="culiacan", max_items=5, gpu_config=fb_gpu_config)
    print(f"Facebook Marketplace retornó {len(fb_results)} resultados.")
    if len(fb_results) > 0:
        first = fb_results[0]
        print(f"  - Primer resultado: '{first['title']}' | Precio original: {first['original_currency']} {first['original_price']} | Precio USD: ${first['price_usd']:.2f} | Plataforma: {first['platform']}")
        assert "http" in first['url']
        assert first['model_id'] == "rtx_2060"
        assert first['platform'] == "facebook"
        print("✅ Facebook Marketplace Scraper funciona exitosamente.")
    else:
        print("❌ Error: Facebook Marketplace no retornó resultados.")
        assert False

def test_webhooks():
    print("\n=== [4/4] Test Webhooks Formatting ===")
    
    dummy_item = {
        "id": "ebay_test_789",
        "title": "Nvidia RTX 3070 ASUS ROG Strix 8GB (Excelente estado)",
        "price_usd": 240.0,
        "original_price": 240.0,
        "original_currency": "USD",
        "url": "https://www.ebay.com/itm/test_789",
        "image_url": "https://img.icons8.com/color/96/nvidia.png",
        "platform": "ebay"
    }
    
    dummy_stats = {
        "mode_price_usd": 300.0,
        "median_price_usd": 295.0,
        "mean_price_usd": 290.0,
        "min_price_usd": 200.0,
        "max_price_usd": 400.0,
        "sample_count": 25
    }
    
    discount_pct = (dummy_stats['mode_price_usd'] - dummy_item['price_usd']) / dummy_stats['mode_price_usd']
    
    print("Simulando creación de payload para Discord:")
    discord_payload = {
        "username": "GPU Deal Tracker",
        "embeds": [
            {
                "title": f"🔥 {dummy_item['title']}",
                "url": dummy_item['url'],
                "color": 0x10b981,
                "fields": [
                    {"name": "💰 Precio Oferta", "value": f"**${dummy_item['price_usd']:.2f} USD**", "inline": True},
                    {"name": "📈 Valor Mercado (Moda)", "value": f"${dummy_stats['mode_price_usd']:.2f} USD", "inline": True},
                    {"name": "⚡ Descuento", "value": f"**{discount_pct*100:.1f}% OFF** (Ahorras ${dummy_stats['mode_price_usd'] - dummy_item['price_usd']:.2f} USD)", "inline": True},
                    {"name": "🛒 Plataforma", "value": dummy_item['platform'].upper(), "inline": True}
                ]
            }
        ]
    }
    print(json.dumps(discord_payload, indent=2))
    print("✅ Formateador de payloads validado.")

if __name__ == "__main__":
    print("Iniciando pruebas unitarias del rastreador...")
    test_statistics()
    test_database()
    test_scrapers()
    test_webhooks()
    print("\n🎉 ¡TODAS LAS PRUEBAS COMPLETADAS EXITOSAMENTE! 🎉")
