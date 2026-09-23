import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

def draw_ai_chart(df, ticker, horizon_label, prob_up, prob_down, interval_label="M5"):
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.5), gridspec_kw={'height_ratios': [3, 1]})
    
    df_slice = df.tail(45).reset_index(drop=True)
    up = df_slice[df_slice['close'] >= df_slice['open']]
    down = df_slice[df_slice['close'] < df_slice['open']]
    
    ax1.bar(up.index, up['close'] - up['open'], 0.6, bottom=up['open'], color='#00ff88')
    ax1.bar(up.index, up['high'] - up['close'], 0.1, bottom=up['close'], color='#00ff88')
    ax1.bar(up.index, up['low'] - up['open'], 0.1, bottom=up['open'], color='#00ff88')
    
    ax1.bar(down.index, down['close'] - down['open'], 0.6, bottom=down['open'], color='#ff2a46')
    ax1.bar(down.index, down['high'] - down['open'], 0.1, bottom=down['open'], color='#ff2a46')
    ax1.bar(down.index, down['low'] - down['close'], 0.1, bottom=down['close'], color='#ff2a46')

    ax1.plot(df_slice.index, df_slice['close'].ewm(span=9).mean(), color='#00d4ff', linewidth=1)
    ax1.plot(df_slice.index, df_slice['close'].ewm(span=21).mean(), color='#ffea00', linewidth=1.5, linestyle='--')
    
    ax1.set_title(f"{interval_label} ML SCANNER | {ticker} -> Horizon: {horizon_label}", fontsize=12, fontweight='bold', color='white')
    ax1.grid(True, color='#222222', linestyle=':')
    
    categories = ['Bullish Expansion', 'Bearish Expansion']
    probabilities = [prob_up, prob_down]
    colors = ['#00ff88', '#ff2a46']
    
    ax2.barh(categories, probabilities, color=colors, alpha=0.8)
    ax2.set_xlim(0, 100)
    ax2.set_title(f"{interval_label} Multi-Bar Target Probability ({horizon_label})", fontsize=10, color='#aaaaaa')
    for i, v in enumerate(probabilities):
        ax2.text(v + 1, i, f"{v}%", color='white', va='center', fontweight='bold')

    plt.tight_layout()
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=130)
    img_buf.seek(0)
    plt.close(fig)
    return img_buf
