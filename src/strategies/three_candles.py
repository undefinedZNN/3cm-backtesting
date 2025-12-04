import backtrader as bt
import math

class ThreeCandlesStrategy(bt.Strategy):
    """
    连续3根K线同方向策略
    """
    params = (
        ('stop_loss_k1', True), # 是否使用 K1 作为止损
        ('risk_reward_ratio', 1.0), # 盈亏比，虽然需求里是具体的公式，但这里保留参数扩展性
        ('size', 1.0), # 固定交易数量，或者可以使用 percent
        # 以下参数仅用于记录背景信息，不影响交易逻辑
        ('dmi_period', 14),
        ('dmi_adx_threshold', 25.0),
        ('dmi_buffer', 1.0),
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        
        self.order = None
        # DMI 指标用于记录市场趋势背景，非交易决策
        self.dmi = bt.indicators.DMI(period=self.params.dmi_period)
        self.market_context = {}  # 以 bar 序号为键缓存 DMI 背景信息

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}')
            else:
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}')
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        # print(f'{dt.isoformat()}, {txt}')  # 启用日志用于调试



    def next(self):
        # 记录当前 bar 的市场背景（趋势/震荡），不影响下方交易逻辑
        self.market_context[len(self)] = self._get_market_context_snapshot()

        # 如果有订单正在挂着，不操作
        if self.order:
            return

        # 如果已经持仓，不操作 (简单模式，每次只持有一单)
        if self.position:
            return

        # 获取最近3根K线 (包括当前这根，如果是在收盘时运行)
        # Backtrader 的 next() 是在当前 bar 结束时调用的 (默认)
        # 所以 index 0 是当前 bar (K3), -1 是 K2, -2 是 K1
        
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
        # 做多：三连阳 且 低点抬高
        is_three_bull = (k1_close > k1_open) and (k2_close > k2_open) and (k3_close > k3_open) and \
                        (k3_low > k2_low > k1_low)
        
        # 做空：三连阴 且 高点降低
        is_three_bear = (k1_close < k1_open) and (k2_close < k2_open) and (k3_close < k3_open) and \
                        (k3_high < k2_high < k1_high)
        
        if is_three_bull:
            # 做多
            # 止损：K1 低点
            stop_loss_price = self.datalow[-2]
            
            # 止盈：K3收盘价格 + (K3收盘价格 - K1 低点)
            # 风险 = K3 Close - K1 Low
            risk = k3_close - stop_loss_price
            take_profit_price = k3_close + risk
            
            self.log(f'BUY CREATE, Price: {k3_close:.2f}, TP: {take_profit_price:.2f}, SL: {stop_loss_price:.2f}')
            
            # 使用 Bracket Order (主订单 + 止盈 + 止损)
            self.buy_bracket(
                size=self.params.size,
                price=None, # Market order for entry (next open)
                stopprice=stop_loss_price,
                limitprice=take_profit_price,
                exectype=bt.Order.Market # Entry execution type
            )
            
        elif is_three_bear:
            # 做空
            # 止损：K1 高点
            stop_loss_price = self.datahigh[-2]
            
            # 止盈：K3收盘价格 - (K1 高点 - K3收盘价格)
            # 风险 = K1 High - K3 Close
            risk = stop_loss_price - k3_close
            take_profit_price = k3_close - risk
            
            self.log(f'SELL CREATE, Price: {k3_close:.2f}, TP: {take_profit_price:.2f}, SL: {stop_loss_price:.2f}')
            
            self.sell_bracket(
                size=self.params.size,
                price=None, # Market order for entry
                stopprice=stop_loss_price,
                limitprice=take_profit_price,
                exectype=bt.Order.Market
            )

    def _get_market_context_snapshot(self):
        """
        获取当前 bar 的 DMI 指标快照，用于记录交易背景。
        """
        # Backtrader 的 DMI 输出的线名称为 plusDI/minusDI/ADX
        plus_di = float(self.dmi.plusDI[0])
        minus_di = float(self.dmi.minusDI[0])
        adx = float(self.dmi.adx[0])

        # 处理初期 NaN
        if any(math.isnan(x) for x in (plus_di, minus_di, adx)):
            market_direction = 'NEUTRAL'
            is_choppy = True
        else:
            buffer = self.params.dmi_buffer
            if plus_di > minus_di + buffer:
                market_direction = 'BULL'
            elif minus_di > plus_di + buffer:
                market_direction = 'BEAR'
            else:
                market_direction = 'NEUTRAL'
            is_choppy = adx < self.params.dmi_adx_threshold

        return {
            'factor_plus_di': plus_di,
            'factor_minus_di': minus_di,
            'factor_adx': adx,
            'factor_market_direction': market_direction,
            'factor_is_choppy': is_choppy
        }
