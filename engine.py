import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

def engineer_features(df):
    df['returns'] = df['close'].pct_change()
    df['body_size'] = abs(df['close'] - df['open'])
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = np.abs(df['high'] - df['close'].shift())
    df['low_close'] = np.abs(df['low'] - df['close'].shift())
    df['TR'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()
    
    df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['trend_distance'] = df['close'] - df['EMA_21']

    return df

def run_ml_prediction(df, horizon_bars=1, interval_label="M5"):
    df_features = engineer_features(df.copy())
    if len(df_features) < 100:
        return "NEUTRAL", 0, "Insufficient data for ML training."

    df_features['Target'] = (df_features['close'].shift(-horizon_bars) > df_features['close']).astype(int)
    df_clean = df_features.dropna().reset_index(drop=True)
    
    if len(df_clean) < max(40, horizon_bars * 1.5):
        return "NEUTRAL", 0, "Insufficient aligned horizon data after target shift."

    features = ['returns', 'body_size', 'upper_wick', 'lower_wick', 'ATR', 'trend_distance']
    X_train = df_clean[features].iloc[:-horizon_bars]
    y_train = df_clean['Target'].iloc[:-horizon_bars]
    X_live = df_clean[features].iloc[-1:]

    model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    model.fit(X_train, y_train)

    probabilities = model.predict_proba(X_live)[0]
    prob_down = probabilities[0] * 100
    prob_up = probabilities[1] * 100

    current_atr = df_clean['ATR'].iloc[-1]
    
    mins_per_bar = 15 if interval_label == "M15" else (1 if interval_label == "M1" else 5)
    window_desc = f"{horizon_bars * mins_per_bar}m ({interval_label} stream)" if horizon_bars > 1 else f"Next {mins_per_bar}m Live Bar"

    if current_atr < 0.00001:
        return "NEUTRAL", 0, f"Model paused: {interval_label} volatility flat/low."

    if prob_up >= 70:
        return "UPCOMING CALL SETUP", round(prob_up, 1), f"{interval_label} expansion projected UP over {window_desc} ({round(prob_up, 1)}% certainty)."
    elif prob_down >= 70:
        return "UPCOMING PUT SETUP", round(prob_down, 1), f"{interval_label} expansion projected DOWN over {window_desc} ({round(prob_down, 1)}% certainty)."
    else:
        return "NEUTRAL", max(round(prob_up, 1), round(prob_down, 1)), f"No high-probability setup forming for {window_desc}."
