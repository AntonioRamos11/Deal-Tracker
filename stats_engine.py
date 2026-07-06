import math
import os
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

def calculate_percentile(data, percentile):
    """Calculates a percentile of a list of numbers."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1

def remove_outliers_iqr(prices):
    """Removes outliers using the Interquartile Range (IQR) method."""
    if len(prices) < 4:
        return prices
        
    q1 = calculate_percentile(prices, 0.25)
    q3 = calculate_percentile(prices, 0.75)
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    # We also clamp to non-negative prices
    lower_bound = max(0, lower_bound)
    
    return [p for p in prices if lower_bound <= p <= upper_bound]

def calculate_mode(prices, bin_size=None):
    """Calculates the statistical mode of prices by grouping into bins."""
    if not prices:
        return 0.0
        
    if len(prices) == 1:
        return prices[0]
        
    min_p = min(prices)
    max_p = max(prices)
    price_range = max_p - min_p
    
    if price_range == 0:
        return min_p
        
    # Determine bin size dynamically if not provided
    if bin_size is None:
        if price_range <= 100:
            bin_size = 10
        elif price_range <= 300:
            bin_size = 20
        elif price_range <= 800:
            bin_size = 50
        else:
            bin_size = 100
            
    # Create bins
    num_bins = max(1, math.ceil(price_range / bin_size))
    bins = [min_p + i * bin_size for i in range(num_bins + 1)]
    
    # Count occurrences in each bin
    counts = [0] * num_bins
    for p in prices:
        # Assign to bin
        bin_idx = int((p - min_p) // bin_size)
        if bin_idx >= num_bins:
            bin_idx = num_bins - 1
        counts[bin_idx] += 1
        
    # Find the bin with max occurrences
    max_count = max(counts)
    max_bin_idx = counts.index(max_count)
    
    # Mode is the midpoint of the bin with the most items
    mode_val = bins[max_bin_idx] + (bin_size / 2.0)
    
    # Adjust mode to not exceed absolute max
    return min(mode_val, max_p)

def calculate_statistics(raw_prices):
    """Calculates mode, median, mean, min, and max for raw prices."""
    if not raw_prices:
        return None
        
    # First remove outliers
    clean_prices = remove_outliers_iqr(raw_prices)
    if not clean_prices:
        clean_prices = raw_prices  # fallback if all removed
        
    n = len(clean_prices)
    mean_val = sum(clean_prices) / n
    median_val = calculate_percentile(clean_prices, 0.5)
    mode_val = calculate_mode(clean_prices)
    min_val = min(clean_prices)
    max_val = max(clean_prices)
    
    return {
        "mode_price_usd": round(mode_val, 2),
        "median_price_usd": round(median_val, 2),
        "mean_price_usd": round(mean_val, 2),
        "min_price_usd": round(min_val, 2),
        "max_price_usd": round(max_val, 2),
        "sample_count": len(raw_prices)  # record total before IQR cleaning
    }

def generate_price_distribution_chart(prices, stats, gpu_name, output_path):
    """Generates a beautiful histogram plot showing price distribution, mode, median."""
    if not prices or not stats:
        return
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    clean_prices = remove_outliers_iqr(prices)
    if not clean_prices:
        clean_prices = prices
        
    plt.figure(figsize=(10, 6))
    
    # Set dark theme styling
    plt.style.use('dark_background')
    fig = plt.gcf()
    fig.patch.set_facecolor('#0f172a') # Tailwind Slate 900
    ax = plt.gca()
    ax.set_facecolor('#1e293b') # Tailwind Slate 800
    
    # Calculate sensible bin count
    bins_count = min(15, len(set(clean_prices)))
    bins_count = max(5, bins_count)
    
    # Draw histogram with nice gradient colors
    n, bins, patches = plt.hist(
        clean_prices, 
        bins=bins_count, 
        color='#3b82f6', 
        alpha=0.75, 
        edgecolor='#1d4ed8', 
        linewidth=1.2,
        rwidth=0.85
    )
    
    # Add vertical lines for statistical indicators
    plt.axvline(stats['mode_price_usd'], color='#10b981', linestyle='-', linewidth=2.5, 
                label=f"Moda (Market Price): ${stats['mode_price_usd']:.2f}")
    plt.axvline(stats['median_price_usd'], color='#f59e0b', linestyle='--', linewidth=2, 
                label=f"Mediana: ${stats['median_price_usd']:.2f}")
    plt.axvline(stats['mean_price_usd'], color='#ec4899', linestyle=':', linewidth=2, 
                label=f"Promedio: ${stats['mean_price_usd']:.2f}")
    
    # Highlight normal price range (IQR area)
    q1 = calculate_percentile(clean_prices, 0.25)
    q3 = calculate_percentile(clean_prices, 0.75)
    plt.axvspan(q1, q3, color='#3b82f6', alpha=0.1, label=f"Rango Común: ${q1:.0f} - ${q3:.0f}")
    
    plt.title(f"Distribución de Precios Usados: {gpu_name}", fontsize=14, fontweight='bold', color='#f8fafc', pad=15)
    plt.xlabel("Precio (USD)", fontsize=11, color='#94a3b8')
    plt.ylabel("Cantidad de Listados", fontsize=11, color='#94a3b8')
    
    # Grid and legend formatting
    plt.grid(True, linestyle=':', alpha=0.3, color='#475569')
    plt.legend(facecolor='#0f172a', edgecolor='#334155', loc='upper right', fontsize=10)
    
    # Adjust layout
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
