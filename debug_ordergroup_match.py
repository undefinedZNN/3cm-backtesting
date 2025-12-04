"""
调试 TradeLogger 是否正确使用了 OrderGroup 的价格
"""
import pandas as pd
import sys
sys.path.insert(0, 'src')

from data_loader import load_data
import backtrader as bt
from strategies.three_candles import ThreeCandlesStrategy
from analyzers.trade_logger import TradeLogger

# 添加调试的 TradeLogger
class DebugTradeLogger(TradeLogger):
    def notify_trade(self, trade):
        if not trade.isclosed:
            return  
        
        # 在父类方法之前检查
        signal_context = self._get_signal_context_from_strategy(trade)
        og = self._find_matching_order_group(trade) if signal_context else None
        
        current_time = self.datas[0].datetime.datetime(0)
        
        # 只看2022-12-15的交易
        if current_time.date() == pd.Timestamp('2022-12-15').date():
            print(f'\n[{current_time}] Trade Closed')
            print(f'  trade.price: {trade.price:.6f}')
            print(f'  signal_context found: {signal_context is not None}')
            print(f'  OrderGroup found: {og is not None}')
            if og:
                print(f'  OG ID: {og.id}')
                print(f'  OG entry_price: {og.entry_price:.6f}')
                print(f'  OG exit_price: {og.exit_price:.6f}')
                print(f'  OG entry_time: {og.entry_time}')
        
        # 调用父类
        return super().notify_trade(trade)

# 运行回测
cerebro = bt.Cerebro()
data = load_data('data/batch_18.parquet', resample='5T', timeframe='timestamp')
cerebro.adddata(data)

cerebro.addstrategy(ThreeCandlesStrategy, size=1.0)
cerebro.addanalyzer(DebugTradeLogger, _name='trade_logger')

cerebro.broker.setcash(10000000.0)
cerebro.broker.setcommission(commission=1.0, commtype=bt.CommInfoBase.COMM_FIXED, mult=50, margin=0.007)

print('运行回测...\n')
results = cerebro.run()

print('\n完成')
