"""
深入调试：为什么 trade.price 和 order.executed.price 不一致？

检查 Backtrader 的 trade 对象如何计算平均价格
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from data_loader import load_data
import backtrader as bt
from strategies.three_candles import ThreeCandlesStrategy

class InspectTradeStrategy(ThreeCandlesStrategy):
    """
    检查 trade 对象的详细信息
    """
    def notify_trade(self, trade):
        """捕获 trade 关闭事件"""
        if not trade.isclosed:
            return
        
        current_time = self.datas[0].datetime.datetime(0)
        
        # 只关注2022-12-15的交易
        if current_time.date() != pd.Timestamp('2022-12-15').date():
            return
        
        print('\n' + '='*80)
        print(f'[{current_time}] TRADE CLOSED')
        print('='*80)
        
        # Trade 对象属性
        print(f'trade.price (平均价): {trade.price:.6f}')
        print(f'trade.value: {trade.value:.2f}')
        print(f'trade.commission: {trade.commission:.2f}')
        print(f'trade.pnl: {trade.pnl:.2f}')
        print(f'trade.pnlcomm: {trade.pnlcomm:.2f}')
        print(f'trade.size: {trade.size}')
        print(f'trade.baropen: {trade.baropen}')
        print(f'trade.barclose: {trade.barclose}')
        print(f'trade.barlen: {trade.barlen}')
        
        # 检查 trade 的方向
        print(f'\ntrade 方向判断:')
        if hasattr(trade, 'long'):
            print(f'  trade.long: {trade.long}')
            is_long = bool(trade.long) if not isinstance(trade.long, list) else len(trade.long) > 0
            print(f'  是否做多: {is_long}')
        
        # 获取开仓和平仓的bar数据
        data = trade.data
        print(f'\n开仓Bar {trade.baropen}:')
        try:
            open_dt = bt.num2date(data.datetime.array[trade.baropen])
            print(f'  时间: {open_dt}')
            print(f'  Open: {data.open.array[trade.baropen]:.2f}')
            print(f'  High: {data.high.array[trade.baropen]:.2f}')
            print(f'  Low: {data.low.array[trade.baropen]:.2f}')
            print(f'  Close: {data.close.array[trade.baropen]:.2f}')
        except:
            print('  无法获取数据')
        
        print(f'\n平仓Bar {trade.barclose}:')
        try:
            close_dt = bt.num2date(data.datetime.array[trade.barclose])
            print(f'  时间: {close_dt}')
            print(f'  Open: {data.open.array[trade.barclose]:.2f}')
            print(f'  High: {data.high.array[trade.barclose]:.2f}')
            print(f'  Low: {data.low.array[trade.barclose]:.2f}')
            print(f'  Close: {data.close.array[trade.barclose]:.2f}')
        except:
            print('  无法获取数据')
        
        # 尝试获取更多细节
        print(f'\ntrade.dtopen: {bt.num2date(trade.dtopen)}')
        print(f'trade.dtclose: {bt.num2date(trade.dtclose)}')
        
        # 检查对应的 OrderGroup
        for og in self.order_groups:
            if og.is_closed() and og.entry_price:
                # 通过时间匹配
                if abs((og.entry_time - bt.num2date(trade.dtopen)).total_seconds()) < 60:
                    print(f'\n匹配的 OrderGroup:')
                    print(f'  OG ID: {og.id}')
                    print(f'  OG Entry Price: {og.entry_price:.6f}')
                    print(f'  OG Exit Price: {og.exit_price:.6f}')
                    print(f'  OG Direction: {og.direction}')
                    print(f'  Signal Context K3 Close: {og.signal_context.get("k3_close", "N/A")}')
                    break

# 运行回测
if __name__ == '__main__':
    print('加载数据...')
    cerebro = bt.Cerebro()
    
    data = load_data('data/batch_18.parquet', resample='5T', timeframe='timestamp')
    cerebro.adddata(data)
    
    cerebro.addstrategy(InspectTradeStrategy, size=1.0)
    
    cerebro.broker.setcash(10000000.0)
    cerebro.broker.setcommission(
        commission=1.0,
        commtype=bt.CommInfoBase.COMM_FIXED,
        mult=50,
        margin=0.007
    )
    
    print('开始回测...\n')
    results = cerebro.run()
    
    print('\n' + '='*80)
    print('回测完成')
    print('='*80)
