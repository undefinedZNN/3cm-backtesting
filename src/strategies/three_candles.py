import backtrader as bt
import math
import pytz
from datetime import datetime

class ThreeCandlesStrategy(bt.Strategy):
    """
    连续3根K线同方向策略
    """
    params = (
        ('stop_loss_k1', True), # 是否使用 K1 作为止损
        ('risk_reward_ratio', 1.0), # 盈亏比，虽然需求里是具体的公式，但这里保留参数扩展性
        ('size', 1.0), # 固定交易数量，1手
        # 方向控制：BOTH / LONG_ONLY / SHORT_ONLY
        ('direction_mode', 'BOTH'),
        # 是否启用调试输出
        ('enable_debug', False),
        # 调试：可选的时间窗口打印锁定状态
        ('debug_window_start', None),  # 'YYYY-MM-DD HH:MM' or None
        ('debug_window_end', None),    # 'YYYY-MM-DD HH:MM' or None
        # 以下参数仅用于记录背景信息，不影响交易逻辑
        ('dmi_period', 14),
        ('dmi_adx_threshold', 25.0),
        ('dmi_buffer', 1.0),
        # 独立订单追踪系统参数
        ('max_concurrent_long', 20),   # 最多20笔做多订单
        ('max_concurrent_short', 20),  # 最多20笔做空订单
        ('allow_bidirectional', True), # 允许多空共存
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        # 顺势抑制状态（多/空各自独立）
        self.trend_state = {
            'LONG': {'locked': False, 'last_session': None},
            'SHORT': {'locked': False, 'last_session': None},
        }

        # 调试窗口（可选）
        self._debug_start = self._parse_debug_time(self.params.debug_window_start)
        self._debug_end = self._parse_debug_time(self.params.debug_window_end)
        
        # 独立订单追踪系统
        from .order_group import OrderGroup
        self.order_groups = []  # 所有订单组列表
        
        # DMI 指标用于记录市场趋势背景，非交易决策
        self.dmi = bt.indicators.DMI(period=self.params.dmi_period)
        self.market_context = {}  # 以 bar 序号为键缓存 DMI 背景信息

    def notify_order(self, order):
        """订单状态变化通知 - 管理 OrderGroup 状态"""
        if order.status in [order.Submitted, order.Accepted]:
            # 调试输出订单状态
            if self._in_debug_window(bt.num2date(order.created.dt)):
                print(f"[DEBUG-ORDER-STATE] {bt.num2date(order.created.dt)} status={order.getstatusname()} ref={order.ref} created_price={order.created.price} size={order.created.size}")
            return

        # 查找订单所属的 OrderGroup
        og = self._find_order_group_by_order(order)
        if not og:
            return
        
        if order.status == order.Completed:
            # 判断是主订单、止损订单还是止盈订单
            if order == og.main_order:
                # 主订单成交
                og.activate(order.executed.price, bt.num2date(order.executed.dt))
                if self._in_debug_window(bt.num2date(order.executed.dt)):
                    print(f"[DEBUG-ORDER-STATE] {bt.num2date(order.executed.dt)} MAIN Completed ref={order.ref} price={order.executed.price}")
                self.log(f'[OG-{og.id}] {og.direction} ENTRY @ {order.executed.price:.2f}')
                
            elif order == og.stop_order:
                # 止损触发
                og.close(order.executed.price, bt.num2date(order.executed.dt), 'STOP')
                if self._in_debug_window(bt.num2date(order.executed.dt)):
                    print(f"[DEBUG-ORDER-STATE] {bt.num2date(order.executed.dt)} STOP Completed ref={order.ref} price={order.executed.price}")
                self.log(f'[OG-{og.id}] {og.direction} STOP @ {order.executed.price:.2f}')
                
            elif order == og.limit_order:
                # 止盈触发
                og.close(order.executed.price, bt.num2date(order.executed.dt), 'LIMIT')
                if self._in_debug_window(bt.num2date(order.executed.dt)):
                    print(f"[DEBUG-ORDER-STATE] {bt.num2date(order.executed.dt)} LIMIT Completed ref={order.ref} price={order.executed.price}")
                self.log(f'[OG-{og.id}] {og.direction} LIMIT @ {order.executed.price:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if order == og.main_order:
                # 主订单被取消，整个 group 取消
                og.cancel()
                if self._in_debug_window(bt.num2date(order.created.dt)):
                    print(f"[DEBUG-ORDER-STATE] {bt.num2date(order.created.dt)} MAIN {order.getstatusname()} ref={order.ref}")
                self.log(f'[OG-{og.id}] Order Group Canceled')
    
    def _find_order_group_by_order(self, order):
        """根据订单对象查找对应的 OrderGroup"""
        for og in self.order_groups:
            if order in [og.main_order, og.stop_order, og.limit_order]:
                return og
        return None

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        # print(f'{dt.isoformat()}, {txt}')  # 启用日志用于调试



    def next(self):
        # 记录当前 bar 的市场背景（趋势/震荡），不影响下方交易逻辑
        self.market_context[len(self)] = self._get_market_context_snapshot()

        # ⚠️ 移除了原有的持仓限制代码
        # 现在支持多笔订单并发
        
        # 统计当前活跃订单数量
        active_long_count = sum(1 for og in self.order_groups if og.is_long and og.is_active())
        active_short_count = sum(1 for og in self.order_groups if og.is_short and og.is_active())

        direction_mode = str(self.params.direction_mode).upper()
        allow_long = direction_mode in ('BOTH', 'LONG_ONLY')
        allow_short = direction_mode in ('BOTH', 'SHORT_ONLY')

        # --- 计算当前/上一K线基本数据 ---
        if len(self) < 1:
            return  # 需要上一根K线做比较

        prev_low = self.datalow[-1]
        prev_high = self.datahigh[-1]
        curr_low = self.datalow[0]
        curr_high = self.datahigh[0]
        curr_open = self.dataopen[0]
        curr_close = self.dataclose[0]

        curr_session = self._get_session_type(self.datas[0].datetime.datetime())
        is_flat = curr_close == curr_open

        # --- 重置判定：平盘、回调、时段切换 ---
        self._update_trend_state('LONG', curr_session, is_flat,
                                 price_reset=(curr_low <= prev_low) or (curr_high <= prev_high))
        self._update_trend_state('SHORT', curr_session, is_flat,
                                 price_reset=(curr_high >= prev_high) or (curr_low >= prev_low))

        # 调试打印锁定状态（仅在窗口内）
        if self._in_debug_window(self.datas[0].datetime.datetime()):
            print(f"[DEBUG-LOCK] {self.datas[0].datetime.datetime()} L.lock={self.trend_state['LONG']['locked']} S.lock={self.trend_state['SHORT']['locked']} "
                  f"lows {prev_low:.2f}->{curr_low:.2f} highs {prev_high:.2f}->{curr_high:.2f} session={curr_session}")

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
        # 做多：三连阳 且 高低点都抬高
        is_three_bull = (
            (k1_close > k1_open) and (k2_close > k2_open) and (k3_close > k3_open) and
            (k3_low > k2_low > k1_low) and  # 低点抬高
            (k3_high > k2_high > k1_high)  # 高点抬高
        )
        
        # 做空：三连阴 且 高低点都降低
        is_three_bear = (
            (k1_close < k1_open) and (k2_close < k2_open) and (k3_close < k3_open) and
            (k3_high < k2_high < k1_high) and  # 高点降低
            (k3_low < k2_low < k1_low)   # 低点降低
        )
        
        if is_three_bull and allow_long and not self.trend_state['LONG']['locked']:
            # 检查做多订单数量上限
            if active_long_count >= self.params.max_concurrent_long:
                return  # 做多订单数量达到上限
            
            # 检查是否允许多空共存
            if not self.params.allow_bidirectional and active_short_count > 0:
                return  # 已有空仓，不允许开多
            
            # 做多
            # 止损：K1 低点
            stop_loss_price = self.datalow[-2]
            
            # 止盈：K3收盘价格 + (K3收盘价格 - K1 低点)
            # 风险 = K3 Close - K1 Low
            risk = k3_close - stop_loss_price
            take_profit_price = k3_close + risk
            
            # 创建 bracket order
            orders = self.buy_bracket(
                size=self.params.size,
                price=None, # Market order for entry (next open)
                stopprice=stop_loss_price,
                limitprice=take_profit_price,
                exectype=bt.Order.Market # Entry execution type
            )
            
            # 构建信号上下文
            signal_context = {
                'direction': 'LONG',
                'k1_low': k1_low,
                'k1_high': k1_high,
                'k2_low': k2_low,
                'k2_high': k2_high,
                'k3_close': k3_close,
                'k3_low': k3_low,
                'k3_high': k3_high,
                # len(self) 是累计 bar 数量，当前 bar 的索引应为 len(self)-1
                'signal_bar': len(self) - 1,
                'stop_price': stop_loss_price,
                'limit_price': take_profit_price,
            }
            
            # 创建 OrderGroup 并追踪
            from .order_group import OrderGroup
            og = OrderGroup(orders, signal_context)
            self.order_groups.append(og)

            self.trend_state['LONG']['locked'] = True
            self.trend_state['LONG']['last_session'] = curr_session
            self.log(f'[OG-{og.id}] LONG ORDER CREATED, TP: {take_profit_price:.2f}, SL: {stop_loss_price:.2f}')
            if self._in_debug_window(self.datas[0].datetime.datetime()):
                print(f"[DEBUG-ORDER] {self.datas[0].datetime.datetime()} LONG created ref=OG-{og.id} TP={take_profit_price:.2f} SL={stop_loss_price:.2f}")
        elif is_three_bear and allow_short and not self.trend_state['SHORT']['locked']:
            # 检查做空订单数量上限
            if active_short_count >= self.params.max_concurrent_short:
                return  # 做空订单数量达到上限
            
            # 检查是否允许多空共存
            if not self.params.allow_bidirectional and active_long_count > 0:
                return  # 已有多仓，不允许开空
            
            # 做空
            # 止损：K1 高点
            stop_loss_price = self.datahigh[-2]
            
            # 止盈：K3收盘价格 - (K1 高点 - K3收盘价格)
            # 风险 = K1 High - K3 Close
            risk = stop_loss_price - k3_close
            take_profit_price = k3_close - risk
            
            # 创建 bracket order
            orders = self.sell_bracket(
                size=self.params.size,
                price=None, # Market order for entry
                stopprice=stop_loss_price,
                limitprice=take_profit_price,
                exectype=bt.Order.Market
            )
            
            # 构建信号上下文
            signal_context = {
                'direction': 'SHORT',
                'k1_low': k1_low,
                'k1_high': k1_high,
                'k2_low': k2_low,
                'k2_high': k2_high,
                'k3_close': k3_close,
                'k3_low': k3_low,
                'k3_high': k3_high,
                'signal_bar': len(self) - 1,
                'stop_price': stop_loss_price,
                'limit_price': take_profit_price,
            }
            
            # 创建 OrderGroup 并追踪
            from .order_group import OrderGroup
            og = OrderGroup(orders, signal_context)
            self.order_groups.append(og)
            
            self.trend_state['SHORT']['locked'] = True
            self.trend_state['SHORT']['last_session'] = curr_session
            self.log(f'[OG-{og.id}] SHORT ORDER CREATED, TP: {take_profit_price:.2f}, SL: {stop_loss_price:.2f}')

        # 调试：信号被锁定时打印一条抑制信息（仅窗口内）
        if self._in_debug_window(self.datas[0].datetime.datetime()):
            if is_three_bull and allow_long and self.trend_state['LONG']['locked']:
                print(f"[DEBUG-SKIP] {self.datas[0].datetime.datetime()} LONG signal skipped due to lock")
            if is_three_bear and allow_short and self.trend_state['SHORT']['locked']:
                print(f"[DEBUG-SKIP] {self.datas[0].datetime.datetime()} SHORT signal skipped due to lock")

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

    def _update_trend_state(self, direction, curr_session, is_flat, price_reset):
        """
        根据当前K线状态更新多/空的抑制状态。
        - direction: 'LONG' or 'SHORT'
        - curr_session: 当前时段 'RTH'/'ETH'
        - is_flat: 是否收盘=开盘
        - price_reset: 是否触发价格回调（根据方向传入）
        """
        state = self.trend_state.get(direction)
        if state is None:
            return

        session_changed = state['last_session'] is not None and state['last_session'] != curr_session

        if is_flat or price_reset or session_changed:
            state['locked'] = False

        # 记录当前时段用于下一根判定
        state['last_session'] = curr_session

    def _get_session_type(self, dt_utc):
        """
        判断 UTC 时间属于 CME RTH 还是 ETH

        RTH (Regular Trading Hours): 周一-周五 08:30-15:15 CT
        ETH (Extended Trading Hours): 其他所有时间
        """
        import pytz
        from datetime import time

        chicago_tz = pytz.timezone('America/Chicago')
        dt_ct = dt_utc.astimezone(chicago_tz)

        weekday = dt_ct.weekday()  # Monday=0
        if weekday < 5:
            time_ct = dt_ct.time()
            rth_start = time(8, 30)
            rth_end = time(15, 15)
            if rth_start <= time_ct <= rth_end:
                return 'RTH'
        return 'ETH'

    def _parse_debug_time(self, s):
        """解析参数中的 debug 时间字符串为 naive datetime (UTC 基准)。"""
        if not s:
            return None
        try:
            return datetime.strptime(s, '%Y-%m-%d %H:%M')
        except Exception:
            return None

    def _in_debug_window(self, dt):
        if not self.params.enable_debug:
            return False
        if not self._debug_start or not self._debug_end:
            return False
        # 兼容 tz-aware，将其转为 naive 进行比较（假设数据为 UTC）
        if dt.tzinfo:
            dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)
        return self._debug_start <= dt <= self._debug_end
