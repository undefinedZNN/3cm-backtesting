"""
调试特定交易的订单执行时间问题

检查 2022-12-15 03:25:00 这笔交易的详细情况
"""

import pandas as pd
import sys
import os

# 切换到src目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from data_loader import load_data
import backtrader as bt
from strategies.three_candles import ThreeCandlesStrategy
from analyzers.trade_logger import TradeLogger

class DebugStrategy(ThreeCandlesStrategy):
    """
    调试版策略：打印详细的订单创建和执行信息
    """
    def next(self):
        current_time = self.datas[0].datetime.datetime(0)
        
        # 只关注2022-12-15 03:00到04:00之间的信号
        if current_time.date() != pd.Timestamp('2022-12-15').date():
            return super().next()
        
        if current_time.hour != 3:
            return super().next()
        
        # 记录市场背景
        self.market_context[len(self)] = self._get_market_context_snapshot()
        
        # 统计当前活跃订单数量
        active_long_count = sum(1 for og in self.order_groups if og.is_long and og.is_active())
        active_short_count = sum(1 for og in self.order_groups if og.is_short and og.is_active())
        
        # 获取最近3根K线
        k3_close = self.dataclose[0]
        k3_open = self.dataopen[0]
        k3_low = self.datalow[0]
        k3_high = self.datahigh[0]
        
        k2_close = self.dataclose[-1]
        k2_open = self.dataopen[-1]
        k2_low = self.datalow[-1]
        k2_high = self.datahigh[-1]
        
        k1_close = self.dataclose[-2]
        k1_open = self.dataopen[-2]
        k1_low = self.datalow[-2]
        k1_high = self.datahigh[-2]
        
        # 判断趋势
        is_three_bull = (k1_close > k1_open) and (k2_close > k2_open) and (k3_close > k3_open) and \
                        (k3_low > k2_low > k1_low)
        
        is_three_bear = (k1_close < k1_open) and (k2_close < k2_open) and (k3_close < k3_open) and \
                        (k3_high < k2_high < k1_high)
        
        if is_three_bull or is_three_bear:
            print(f'\n{"="*80}')
            print(f'[{current_time}] 信号触发!')
            print(f'K1 (bar {len(self)-2}): O={k1_open:.2f}, H={k1_high:.2f}, L={k1_low:.2f}, C={k1_close:.2f}')
            print(f'K2 (bar {len(self)-1}): O={k2_open:.2f}, H={k2_high:.2f}, L={k2_low:.2f}, C={k2_close:.2f}')
            print(f'K3 (bar {len(self)}):   O={k3_open:.2f}, H={k3_high:.2f}, L={k3_low:.2f}, C={k3_close:.2f}')
            print(f'方向: {"LONG" if is_three_bull else "SHORT"}')
            print(f'活跃做多: {active_long_count}, 活跃做空: {active_short_count}')
        
        # 调用父类方法创建订单
        return super().next()
    
    def notify_order(self, order):
        """订单通知"""
        current_time = self.datas[0].datetime.datetime(0)
        
        # 只关注2022-12-15的订单
        if current_time.date() != pd.Timestamp('2022-12-15').date():
            return super().notify_order(order)
        
        if order.status in [order.Submitted, order.Accepted]:
            print(f'  [{current_time}] 订单状态: {order.status} (提交/接受)')
            return super().notify_order(order)
        
        if order.status == order.Completed:
            print(f'  [{current_time}] 订单成交: Price={order.executed.price:.2f}, '
                  f'Size={order.executed.size}, Bar={len(self)}')
        
        return super().notify_order(order)


# 运行回测
if __name__ == '__main__':
    print('加载数据...')
    cerebro = bt.Cerebro()
    
    # 加载数据
    data = load_data('data/batch_18.parquet', resample='5T', timeframe='timestamp')
    cerebro.adddata(data)
    
    # 添加调试策略
    cerebro.addstrategy(DebugStrategy, size=1.0)
    
    # 添加分析器
    cerebro.addanalyzer(TradeLogger, _name='trade_logger')
    
    # 设置资金和佣金
    cerebro.broker.setcash(10000000.0)
    cerebro.broker.setcommission(
        commission=1.0,
        commtype=bt.CommInfoBase.COMM_FIXED,
        mult=50,
        margin=0.007
    )
    
    print('开始回测...\n')
    results = cerebro.run()
    
    # 检查交易记录
    strategy = results[0]
    trades = strategy.analyzers.trade_logger.get_analysis()
    
    print('\n' + '='*80)
    print(f'回测完成，共 {len(trades)} 笔交易')
    print('='*80)
    
    # 找到03:25这笔交易
    import pandas as pd
    df = pd.DataFrame(trades)
    target = df[df['entry_time'] == pd.Timestamp('2022-12-15 03:25:00')]
    
    if len(target) > 0:
        print('\n找到目标交易:')
        print(target[['entry_time', 'exit_time', 'direction', 'entry_price', 'exit_price', 'pnl']].to_string())
    else:
        print('\n未找到 entry_time = 2022-12-15 03:25:00 的交易')
