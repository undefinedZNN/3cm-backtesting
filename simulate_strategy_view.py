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

print("模拟策略在不同时刻看到的K线数据\n")
print("="*80)

# Order #5 执行在 09:35
# 我们需要检查策略在 09:25, 09:30, 09:35 收盘时看到的数据

times_to_check = [
    ('2022-12-15 09:25:00', '当前bar=09:25收盘'),
    ('2022-12-15 09:30:00', '当前bar=09:30收盘'),
    ('2022-12-15 09:35:00', '当前bar=09:35收盘'),
]

for time_str, desc in times_to_check:
    target_time = pd.Timestamp(time_str, tz='UTC')
    try:
        current_idx = df_5min[df_5min['timestamp'] == target_time].index[0]
    except:
        print(f"找不到时间: {time_str}")
        continue
    
    # 策略在当前bar收盘时看到的K1, K2, K3
    k3_idx = current_idx  # [0]
    k2_idx = current_idx - 1  # [-1]
    k1_idx = current_idx - 2  # [-2]
    
    if k1_idx < 0:
        continue
    
    k1 = df_5min.iloc[k1_idx]
    k2 = df_5min.iloc[k2_idx]
    k3 = df_5min.iloc[k3_idx]
    
    print(f"\n{desc} (在 {target_time} 时刻)")
    print("-"*80)
    print(f"K1 ({k1['timestamp']}): O={k1['open']:.2f}, C={k1['close']:.2f} | {'阴' if k1['close'] < k1['open'] else '阳'}")
    print(f"K2 ({k2['timestamp']}): O={k2['open']:.2f}, C={k2['close']:.2f} | {'阴' if k2['close'] < k2['open'] else '阳'}")
    print(f"K3 ({k3['timestamp']}): O={k3['open']:.2f}, C={k3['close']:.2f} | {'阴' if k3['close'] < k3['open'] else '阳'}")
    
    is_three_bear = (k1['close'] < k1['open']) and (k2['close'] < k2['open']) and (k3['close'] < k3['open'])
    is_three_bull = (k1['close'] > k1['open']) and (k2['close'] > k2['open']) and (k3['close'] > k3['open'])
    
    if is_three_bear:
        print(">>> 触发做空信号! (三连阴)")
    elif is_three_bull:
        print(">>> 触发做多信号! (三连阳)")
    else:
        print(">>> 无信号")
