import requests
import json
import scrapers as scr

def send_discord_webhook(webhook_url, item, stats, discount_pct):
    """Sends a rich embed message to a Discord webhook showing both MXN and USD prices."""
    if not webhook_url:
        print("Discord Webhook URL is empty. Skipping notification.")
        return False
        
    price_usd = item['price_usd']
    market_price = stats['mode_price_usd']
    savings_usd = market_price - price_usd
    savings_pct = discount_pct * 100
    
    # Currency conversions
    usd_to_mxn = 1.0 / scr.get_exchange_rate("MXN", "USD")
    
    if item.get('original_currency') == 'MXN' and item.get('original_price'):
        price_mxn = item['original_price']
    else:
        price_mxn = price_usd * usd_to_mxn
        
    market_mxn = market_price * usd_to_mxn
    savings_mxn = savings_usd * usd_to_mxn

    # Embed color (dark green for normal deal, gold for massive deal > 25%, blue for auctions)
    is_auction = item.get('is_auction', 0) == 1
    if is_auction:
        color = 0x3b82f6 # blue
    else:
        color = 0x10b981 if savings_pct < 25 else 0xf59e0b # green or gold
        
    title_prefix = "🔨 [SUBASTA]" if is_auction else "🔥"
    price_label = "💰 Puja Actual" if is_auction else "💰 Precio Oferta"
    
    fields = [
        {
            "name": price_label,
            "value": f"**${price_mxn:,.2f} MXN**\n(${price_usd:,.2f} USD)",
            "inline": True
        },
        {
            "name": "📈 Valor Mercado (Moda)",
            "value": f"**${market_mxn:,.2f} MXN**\n(${market_price:,.2f} USD)",
            "inline": True
        },
        {
            "name": "⚡ Descuento/Margen",
            "value": f"**{savings_pct:.1f}% OFF**\n(Ahorras ${savings_mxn:,.2f} MXN)",
            "inline": True
        }
    ]
    
    if is_auction:
        bids = item.get('bids_count', 0)
        time_left = item.get('time_left') or "Desconocido"
        fields.append({
            "name": "📊 Estado de Subasta",
            "value": f"**{bids} pujas**\n⏳ {time_left}",
            "inline": True
        })
    else:
        fields.append({
            "name": "🛒 Plataforma",
            "value": item['platform'].upper(),
            "inline": True
        })
    
    payload = {
        "username": "Antigravity Deal Tracker",
        "avatar_url": "https://img.icons8.com/color/96/nvidia.png",
        "embeds": [
            {
                "title": f"{title_prefix} {item['title']}",
                "url": item['url'],
                "color": color,
                "fields": fields,
                "footer": {
                    "text": f"ID: {item['id']} • Detectado por Antigravity Deal Tracker"
                }
            }
        ]
    }
    
    # Add thumbnail if available
    if item.get('image_url'):
        payload["embeds"][0]["thumbnail"] = {"url": item['image_url']}
        
    try:
        r = requests.post(webhook_url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        if r.status_code in [200, 204]:
            print(f"Successfully sent Discord webhook alert for {item['id']}")
            return True
        else:
            print(f"Failed to send Discord webhook. Status code: {r.status_code}, Response: {r.text}")
            return False
    except Exception as e:
        print(f"Exception sending Discord webhook: {e}")
        return False

def send_slack_webhook(webhook_url, item, stats, discount_pct):
    """Sends a formatted block message to a Slack webhook showing both MXN and USD prices."""
    if not webhook_url:
        print("Slack Webhook URL is empty. Skipping notification.")
        return False
        
    price_usd = item['price_usd']
    market_price = stats['mode_price_usd']
    savings_usd = market_price - price_usd
    savings_pct = discount_pct * 100
    
    # Currency conversions
    usd_to_mxn = 1.0 / scr.get_exchange_rate("MXN", "USD")
    
    if item.get('original_currency') == 'MXN' and item.get('original_price'):
        price_mxn = item['original_price']
    else:
        price_mxn = price_usd * usd_to_mxn
        
    market_mxn = market_price * usd_to_mxn
    savings_mxn = savings_usd * usd_to_mxn

    # Block layout for Slack
    is_auction = item.get('is_auction', 0) == 1
    platform_name = "EBAY (SUBASTA)" if is_auction else item['platform'].upper()
    header_text = f"🚨 Nueva Subasta Detectada: {platform_name}" if is_auction else f"🚨 Nueva Oferta Encontrada: {item['platform'].upper()}"
    
    price_label = "Puja Actual" if is_auction else "Precio"
    
    desc_text = f"*<{item['url']}|{item['title']}>*\n" \
                f"*{price_label}:* `${price_mxn:,.2f} MXN` (${price_usd:,.2f} USD)\n" \
                f"*Valor Mercado (Moda):* `${market_mxn:,.2f} MXN` (${market_price:,.2f} USD)\n" \
                f"*Margen/Descuento:* `{savings_pct:.1f}% OFF` (Ahorras `${savings_mxn:,.2f} MXN` / `${savings_usd:,.2f} USD`)"
                
    if is_auction:
        bids = item.get('bids_count', 0)
        time_left = item.get('time_left') or "Desconocido"
        desc_text += f"\n*Bids/Pujas:* `{bids}` | *Tiempo Restante:* `{time_left}`"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": desc_text
            }
        }
    ]
    
    # Add image if available
    if item.get('image_url'):
        blocks[1]["accessory"] = {
            "type": "image",
            "image_url": item['image_url'],
            "alt_text": "GPU Thumbnail"
        }
        
    # Divider and footer
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"ID: `{item['id']}` | Detectado por Antigravity Deal Tracker"
            }
        ]
    })
    
    payload = {"blocks": blocks}
    
    try:
        r = requests.post(webhook_url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        if r.status_code == 200 or r.text == 'ok':
            print(f"Successfully sent Slack webhook alert for {item['id']}")
            return True
        else:
            print(f"Failed to send Slack webhook. Status code: {r.status_code}, Response: {r.text}")
            return False
    except Exception as e:
        print(f"Exception sending Slack webhook: {e}")
        return False

def trigger_alerts(item, stats, config_settings):
    """Triggers both Slack and Discord webhooks if configured."""
    price_usd = item['price_usd']
    market_price = stats['mode_price_usd']
    
    if market_price <= 0:
        return False
        
    discount_pct = (market_price - price_usd) / market_price
    
    # Check if meets threshold
    threshold = config_settings.get("discount_alert_threshold", 0.15)
    if discount_pct >= threshold:
        discord_url = config_settings.get("discord_webhook_url")
        slack_url = config_settings.get("slack_webhook_url")
        
        discord_sent = False
        slack_sent = False
        
        if discord_url:
            discord_sent = send_discord_webhook(discord_url, item, stats, discount_pct)
        if slack_url:
            slack_sent = send_slack_webhook(slack_url, item, stats, discount_pct)
            
        return discord_sent or slack_sent
        
    return False
