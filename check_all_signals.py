import pandas as pd

# Load data
df_5min = pd.read_parquet('data/batch_18.parquet')
df_5min['timestamp'] = pd.to_datetime(df_5min['timestamp'])
df_5min = df_5min.set_index('timestamp').resample('5min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).dropna().reset_index()

print("详细检查 09:00-09:40 的所有K线和可能的信号\n")
print("="*100)

# 检查从 09:00 到 09:40 的每根K线收盘时的状态
start_idx = df_5min[df_5min['timestamp'] == pd.Timestamp('2022-12-15 09:00:00', tz='UTC')].index[0]
end_idx = df_5min[df_5min['timestamp'] == pd.Timestamp('2022-12-15 09:40:00', tz='UTC')].index[0]

for current_idx in range(start_idx, end_idx + 1):
    if current_idx < 2:
        continue
        
    k3 = df_5min.iloc[current_idx]
    k2 = df_5min.iloc[current_idx - 1]
    k1 = df_5min.iloc[current_idx - 2]
    
    is_k1_bear = k1['close'] < k1['open']
    is_k2_bear = k2['close'] < k2['open']
    is_k3_bear = k3['close'] < k3['open']
    
    is_k1_bull = k1['close'] > k1['open']
    is_k2_bull = k2['close'] > k2['open']
    is_k3_bull = k3['close'] > k3['open']
    
    is_three_bear = is_k1_bear and is_k2_bear and is_k3_bear
    is_three_bull = is_k1_bull and is_k2_bull and is_k3_bull
    
    signal = ''
    if is_three_bear:
        signal = '>>> 做空信号 (三连阴)'
    elif is_three_bull:
        signal = '>>> 做多信号 (三连阳)'
    
    if signal or k3['timestamp'].strftime('%H:%M') in ['09:25', '09:30', '09:35']:
        print(f"\n当前bar收盘: {k3['timestamp']} (idx {current_idx})")
        print(f"  K1 ({k1['timestamp'].strftime('%H:%M')}): O={k1['open']:.2f}, C={k1['close']:.2f} | {'阴' if is_k1_bear else '阳'}")
        print(f"  K2 ({k2['timestamp'].strftime('%H:%M')}): O={k2['open']:.2f}, C={k2['close']:.2f} | {'阴' if is_k2_bear else '阳'}")
        print(f"  K3 ({k3['timestamp'].strftime('%H:%M')}): O={k3['open']:.2f}, C={k3['close']:.2f} | {'阴' if is_k3_bear else '阳'}")
        if signal:
            print(f"  {signal}")
            # 预测下一根K线开盘执行
            if current_idx < len(df_5min) - 1:
                next_bar = df_5min.iloc[current_idx + 1]
                print(f"  → 预期执行时间: {next_bar['timestamp']} (下一根K线)")
