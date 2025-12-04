import pandas as pd

df = pd.read_parquet('data/batch_18.parquet')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').resample('5min').agg({
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
}).dropna()

bar_930 = df.loc['2022-12-15 09:30:00']
bar_935 = df.loc['2022-12-15 09:35:00']

print(f'09:30 bar: Open={bar_930["open"]:.2f}, Close={bar_930["close"]:.2f}')
print(f'09:35 bar: Open={bar_935["open"]:.2f}, Close={bar_935["close"]:.2f}')
print(f'\nOrder #5 Entry Price: 3989.50')
print(f'匹配: 09:30 Open? {abs(bar_930["open"] - 3989.50) < 0.01}')
print(f'匹配: 09:35 Open? {abs(bar_935["open"] - 3989.50) < 0.01}')

# 更重要：检查 09:25 信号（三连阳）的参数
print('\n\n09:25 三连阳信号分析:')
b_925 = df.loc['2022-12-15 09:25:00']
b_920 = df.loc['2022-12-15 09:20:00']
b_915 = df.loc['2022-12-15 09:15:00']
print(f'K1 (09:15): C={b_915["close"]:.2f}')
print(f'K2 (09:20): C={b_920["close"]:.2f}')
print(f'K3 (09:25): C={b_925["close"]:.2f}')

# 做多参数
stop_loss = b_915['low']
entry_price_signal = b_925['close']
risk = entry_price_signal - stop_loss
take_profit = entry_price_signal + risk

print(f'\n做多信号参数:')
print(f'  Entry (K3 Close): {entry_price_signal:.2f}')
print(f'  Stop Loss (K1 Low): {stop_loss:.2f}')
print(f'  Take Profit: {take_profit:.2f}')
print(f'  预期执行: 09:30 Open = {bar_930["open"]:.2f}')

print(f'\n关键匹配:')
print(f'  09:30 Open = {bar_930["open"]:.2f}')
print(f'  Order #5 Entry = 3989.50')
print(f'  是否匹配: {abs(bar_930["open"] - 3989.50) < 0.01}')
