import pandas as pd

# Load new data
df = pd.read_parquet('output/test_new_entry_logic.parquet')

# Generate lists
def classify_exit(row):
    if row['pnl'] < 0:
        return 'stop_loss'
    elif row['pnl'] > 0:
        return 'take_profit'
    else:
        return 'breakeven'

df['exit_type'] = df.apply(classify_exit, axis=1)
df['entry_time_utc8'] = pd.to_datetime(df['entry_time']).dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
df['exit_time_utc8'] = pd.to_datetime(df['exit_time']).dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')

take_profit = df[df['exit_type'] == 'take_profit'].head(10)
stop_loss = df[df['exit_type'] == 'stop_loss'].head(10)
take_profit_abcd = df[(df['exit_type'] == 'take_profit') & (df['factor_reached_abcd'] == True)].head(10)
stop_loss_abcd = df[(df['exit_type'] == 'stop_loss') & (df['factor_reached_abcd'] == True)].head(10)

print(f'\nStats (New Entry Logic):')
print(f'Total Trades: {len(df)}')
print(f'Win Rate: {len(df[df["pnl"] > 0]) / len(df):.2%}')

def print_trades(trades, title):
    print(f'\n{"="*110}')
    print(f'{title}')
    print(f'{"="*110}\n')
    for idx, row in trades.iterrows():
        print(f'订单 #{idx}:')
        print(f'  方向: {row["direction"]:5s} | 入场: {row["entry_price"]:8.2f} | 出场: {row["exit_price"]:8.2f} | PnL: {row["pnl"]:9.2f}')
        print(f'  持仓K线数: {row["bars_held"]:3d}', end='')
        if pd.notna(row.get('factor_max_drawdown_before_abcd')):
            print(f' | 二推回撤: {row["factor_max_drawdown_before_abcd"]:7.2%}', end='')
        print()
        print(f'  入场时间(UTC+8): {row["entry_time_utc8"].strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'  出场时间(UTC+8): {row["exit_time_utc8"].strftime("%Y-%m-%d %H:%M:%S")}')
        print()

print_trades(take_profit, '10笔止盈订单')
print_trades(stop_loss, '10笔止损订单')
print_trades(take_profit_abcd, '10笔止盈有二推订单')
print_trades(stop_loss_abcd, '10笔止损有二推订单')
