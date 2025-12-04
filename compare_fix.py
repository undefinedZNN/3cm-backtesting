import pandas as pd

# 比较修复前后
old = pd.read_parquet('output/test_abcd_fixed_v2.parquet')
new = pd.read_parquet('output/test_long_fix_v2.parquet')

print('订单 #5 修复前后对比:')
print('='*100)

old5 = old.loc[5]
new5 = new.loc[5]

print('\n修复前:')
print(f'  Direction: {old5["direction"]}')
print(f'  Entry: {old5["entry_price"]:.2f} @ {old5["entry_time"]}')
print(f'  Exit: {old5["exit_price"]:.2f} @ {old5["exit_time"]}')
print(f'  PnL: {old5["pnl"]:.2f}')

print('\n修复后:')
print(f'  Direction: {new5["direction"]}')
print(f'  Entry: {new5["entry_price"]:.2f} @ {new5["entry_time"]}')
print(f'  Exit: {new5["exit_price"]:.2f} @ {new5["exit_time"]}')
print(f'  PnL: {new5["pnl"]:.2f}')

print(f'\n修复成功: {new5["direction"] == "LONG"}')

# 检查方向变化的订单数量
direction_changed = (old['direction'] != new['direction']).sum()
print(f'\n\n总共有 {direction_changed} 笔交易的方向被修正')

# 找出所有方向变化的订单
if direction_changed > 0:
    changed_trades = old[old['direction'] != new['direction']]
    print(f'\n方向变化的订单索引: {list(changed_trades.index[:20])}... (显示前20个)')
    
print('\n\n整体方向分布对比:')
print('='*100)
print(f'修复前: LONG={len(old[old["direction"]=="LONG"])}, SHORT={len(old[old["direction"]=="SHORT"])}')
print(f'修复后: LONG={len(new[new["direction"]=="LONG"])}, SHORT={len(new[new["direction"]=="SHORT"])}')
