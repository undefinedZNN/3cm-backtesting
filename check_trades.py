import pandas as pd

trades = pd.read_parquet('output/test_abcd_fixed_v2.parquet')

# 查看订单 #4, #5, #6
print('订单 #4, #5, #6 的详细信息:')
print('='*100)
for idx in [4, 5, 6]:
    trade = trades.loc[idx]
    print(f'\n订单 #{idx}:')
    print(f'  Direction: {trade["direction"]}')
    print(f'  Entry: {trade["entry_time"]} @ {trade["entry_price"]:.2f}')
    print(f'  Exit:  {trade["exit_time"]} @ {trade["exit_price"]:.2f}')
    print(f'  PnL: {trade["pnl"]:.2f}')
    print(f'  Bars Held: {trade["bars_held"]}')
