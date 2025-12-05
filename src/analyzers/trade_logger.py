import backtrader as bt
import pandas as pd
import duckdb
import os
from datetime import datetime, time
import pytz
import math

class TradeLogger(bt.Analyzer):
    """
    自定义分析器，用于记录每一笔交易的详细信息，包括背景数据。
    """
    def __init__(self):
        self.trades = []
        # 记录已写入的 OrderGroup ID，避免重复
        self.logged_order_groups = set()
        # 暂存从 notify_order 写入的索引，便于后续用 trade 记录替换
        self._order_log_index = {}

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        # 从 trade 对象直接获取信息
        data = trade.data

        # 匹配对应的 OrderGroup
        og_dup = self._find_matching_order_group(trade)
        
        # ✅ 优先从 OrderGroup 获取精确的成交价格
        # 这避免了 Backtrader 合并多个订单导致的平均价问题
        og = self._find_matching_order_group(trade)  # 直接查找，不依赖 signal_context
        
        if og and og.entry_price is not None:
            # ✅ 使用 OrderGroup 的精确成交价
            entry_price = og.entry_price
            exit_price_calc = og.exit_price if og.exit_price is not None else 0.0
            entry_dt = og.entry_time if og.entry_time else bt.num2date(trade.dtopen)
            exit_dt = og.exit_time if og.exit_time else bt.num2date(trade.dtclose)
            is_long = og.is_long
            direction = og.direction
            
            # 使用 OrderGroup 的精确价格重新计算 PnL
            size = 1.0
            if is_long:
                pnl = (exit_price_calc - entry_price) * size * 50
            else:
                pnl = (entry_price - exit_price_calc) * size * 50
            pnlcomm = pnl - 2.0  # 扣除手续费 ($1开仓 + $1平仓)
            
        else:
            # ⚠️ 回退：使用 trade 对象（可能是平均价）
            entry_price = trade.price  # 平均开仓价（如果多笔订单会不准确）
            pnl = trade.pnl
            pnlcomm = trade.pnlcomm
            size = 1.0
            
            # 判断交易方向
            is_long = True
            if hasattr(trade, 'long'):
                try:
                    is_long = len(trade.long) > 0
                except:
                    is_long = bool(trade.long)
            else:
                try:
                    open_bar_price = data.close.array[trade.baropen]
                    close_bar_price = data.close.array[trade.barclose]
                    price_change = close_bar_price - open_bar_price
                    if pnl != 0 and price_change != 0:
                        is_long = (pnl * price_change) > 0
                except:
                    pass
            
            direction = 'LONG' if is_long else 'SHORT'
            
            # 获取时间
            try:
                entry_dt = bt.num2date(trade.dtopen)
            except Exception:
                try:
                    entry_dt = bt.num2date(data.datetime.array[trade.baropen - 1])
                except Exception:
                    entry_dt = bt.num2date(data.datetime[0])

            try:
                exit_dt = bt.num2date(trade.dtclose)
            except Exception:
                try:
                    exit_dt = bt.num2date(data.datetime.array[trade.barclose])
                except Exception:
                    exit_dt = entry_dt
            
            # 平仓价格 - 通过 PnL 反推
            if size != 0:
                if is_long:
                    exit_price_calc = entry_price + (pnl / (size * 50))
                else:
                    exit_price_calc = entry_price - (pnl / (size * 50))
            else:
                exit_price_calc = entry_price
        
        # 盈亏（统一使用已计算的值）
        
        # 资金费率
        funding_fee = 0.0
        try:
            for i in range(trade.baropen, trade.barclose + 1):
                fr = data.funding_rate.array[i]
                funding_fee += abs(entry_value) * fr
        except Exception:
            funding_fee = 0.0
        
        # --- 判断交易时段 (CME RTH/ETH) ---
        factor_entry_session = self._get_session_type(entry_dt)
        factor_exit_session = self._get_session_type(exit_dt)

        # --- 趋势/震荡背景 ---
        factor_market_direction = None
        factor_trend_alignment = None
        factor_is_choppy = None

        market_ctx = self._get_market_context(trade.baropen)
        if market_ctx:
            factor_market_direction = market_ctx.get('factor_market_direction')
            factor_is_choppy = market_ctx.get('factor_is_choppy')

            if factor_market_direction in ('BULL', 'BEAR'):
                aligned = (factor_market_direction == 'BULL' and is_long) or (factor_market_direction == 'BEAR' and not is_long)
                factor_trend_alignment = 'aligned' if aligned else 'opposite'
            else:
                factor_trend_alignment = 'neutral'

        # --- 从策略的 OrderGroup 获取精确的信号背景 ---
        signal_context = self._get_signal_context_from_strategy(trade)
        
        # 初始化 K1/K2/K3 价格点
        k1_low = k1_high = k2_low = k2_high = k3_close = k3_low = k3_high = 0.0
        
        if signal_context:
            # 使用 OrderGroup 中记录的原始信号数据（最精确）
            idx_k3 = signal_context.get('signal_bar')
            idx_k2 = idx_k3 - 1 if idx_k3 is not None else trade.baropen - 1
            idx_k1 = idx_k3 - 2 if idx_k3 is not None else trade.baropen - 2
            
            # 直接从 signal_context 获取 K1/K2/K3 数据
            k1_low = signal_context.get('k1_low', 0.0)
            k1_high = signal_context.get('k1_high', 0.0)
            k2_low = signal_context.get('k2_low', 0.0)
            k2_high = signal_context.get('k2_high', 0.0)
            k3_close = signal_context.get('k3_close', 0.0)
            k3_low = signal_context.get('k3_low', 0.0)
            k3_high = signal_context.get('k3_high', 0.0)
        else:
            # 回退到现有的启发式方法
            stop_loss_price_hint = None
            if pnl < 0:
                stop_loss_price_hint = exit_price_calc
            
            idx_k1, idx_k2, idx_k3 = self._find_signal_bars(data, trade.baropen, is_long, stop_loss_price_hint)
            
            # 从数据中提取
            try:
                k1_low = data.low.array[idx_k1]
                k1_high = data.high.array[idx_k1]
                k2_low = data.low.array[idx_k2]
                k2_high = data.high.array[idx_k2]
                k3_close = data.close.array[idx_k3]
                k3_low = data.low.array[idx_k3]
                k3_high = data.high.array[idx_k3]
            except (IndexError, TypeError): # Handle cases where idx_k1/k2/k3 might be -1 or None
                k1_low = k1_high = k2_low = k2_high = k3_close = k3_low = k3_high = 0.0
        
        # --- 计算 K3 时刻的动量指标 ---
        # 使用 K3 收盘时刻计算 DEMA 动量
        factor_dema, factor_mom1, factor_mom2 = self._calculate_momentum(data, idx_k3, lookback=6)
        context_metrics = {}
        if idx_k1 >= 0:
            def get_bar(idx):
                return {
                    'open': data.open.array[idx],
                    'high': data.high.array[idx],
                    'low': data.low.array[idx],
                    'close': data.close.array[idx]
                }
            
            k1 = get_bar(idx_k1)
            k3 = get_bar(idx_k3)
            
            # 1. 影线缺口
            shadow_gap = 0.0
            has_shadow_gap = False
            
            if is_long:  # 做多
                if k3['low'] > k1['high']:
                    shadow_gap = k3['low'] - k1['high']
                    has_shadow_gap = True
            else:  # 做空
                if k3['high'] < k1['low']:
                    shadow_gap = k1['low'] - k3['high']
                    has_shadow_gap = True
            
            signal_range = abs(k3['close'] - k1['open'])
            shadow_gap_ratio = shadow_gap / signal_range if signal_range > 0 else 0
            
            # 2. 实体缺口
            body_gap = 0.0
            has_body_gap = False
            
            k1_body_top = max(k1['open'], k1['close'])
            k1_body_bottom = min(k1['open'], k1['close'])
            k3_body_top = max(k3['open'], k3['close'])
            k3_body_bottom = min(k3['open'], k3['close'])
            
            if is_long:  # 做多
                if k3_body_bottom > k1_body_top:
                    body_gap = k3_body_bottom - k1_body_top
                    has_body_gap = True
            else:  # 做空
                if k3_body_top < k1_body_bottom:
                    body_gap = k1_body_bottom - k3_body_top
                    has_body_gap = True
            
            body_gap_ratio = body_gap / signal_range if signal_range > 0 else 0

            # 3. 重叠率
            k3_high = k3['high']
            k3_low = k3['low']
            
            overlaps = {}
            factor_crossed_k3_extreme = False
            try:
                if is_long:
                    period_highs = data.high.array[trade.baropen : trade.barclose + 1]
                    factor_crossed_k3_extreme = max(period_highs) > k3_high if len(period_highs) else False
                else:
                    period_lows = data.low.array[trade.baropen : trade.barclose + 1]
                    factor_crossed_k3_extreme = min(period_lows) < k3_low if len(period_lows) else False
            except Exception:
                factor_crossed_k3_extreme = False

            for lookback in [5, 10, 15, 20, 25, 30]:
                start_idx = idx_k3 - lookback
                if start_idx < 0:
                    overlaps[f'factor_overlap_{lookback}'] = 0.0
                    continue
                
                past_highs = data.high.array[start_idx : idx_k3]
                past_lows = data.low.array[start_idx : idx_k3]
                
                if len(past_highs) == 0:
                    overlaps[f'factor_overlap_{lookback}'] = 0.0
                    continue

                period_high = max(past_highs)
                period_low = min(past_lows)
                
                overlap_high = min(k3_high, period_high)
                overlap_low = max(k3_low, period_low)
                
                overlap_len = max(0.0, overlap_high - overlap_low)
                k3_len = k3_high - k3_low
                
                ratio = overlap_len / k3_len if k3_len > 0 else 0
                overlaps[f'factor_overlap_{lookback}'] = ratio
            
            context_metrics.update({
                'factor_shadow_gap': shadow_gap,
                'factor_has_shadow_gap': has_shadow_gap,
                'factor_shadow_gap_ratio': shadow_gap_ratio,
                'factor_body_gap': body_gap,
                'factor_has_body_gap': has_body_gap,
                'factor_body_gap_ratio': body_gap_ratio,
                'factor_crossed_k3_extreme': factor_crossed_k3_extreme,
                **overlaps
            })

        # --- 计算 AB=CD 背景因子 ---
        factor_reached_abcd = None
        factor_max_drawdown_before_abcd = None
        
        if idx_k1 >= 0:  # 确保有足够的历史数据
            try:
                k1_low = data.low.array[idx_k1]
                k1_high = data.high.array[idx_k1]
                k3_close = data.close.array[idx_k3]  # K3收盘价作为B点
                abcd_result = self._calculate_abcd_factors(
                    trade, data, is_long, k3_close, k1_low, k1_high  # 使用K3收盘价而不是实际成交价
                )
                factor_reached_abcd = abcd_result['reached_abcd']
                factor_max_drawdown_before_abcd = abcd_result['max_drawdown_ratio']
            except Exception:
                factor_reached_abcd = None
                factor_max_drawdown_before_abcd = None



        # 记录数据
        self.trades.append({
            'entry_time': entry_dt,
            'exit_time': exit_dt,
            'symbol': data._name,
            'direction': 'LONG' if is_long else 'SHORT',
            'size': size,
            'entry_price': entry_price,
            'exit_price': exit_price_calc,
            'pnl': pnl,
            'pnl_net': pnlcomm,
            'funding_fee': funding_fee,
            'bars_held': trade.barlen,
            'source': 'trade',
            'factor_entry_session': factor_entry_session,
            'factor_exit_session': factor_exit_session,
            'factor_mom1': factor_mom1,
            'factor_mom2': factor_mom2,
            'factor_market_direction': factor_market_direction,
            'factor_trend_alignment': factor_trend_alignment,
            'factor_is_choppy': factor_is_choppy,
            'factor_reached_abcd': factor_reached_abcd,
            'factor_max_drawdown_before_abcd': factor_max_drawdown_before_abcd,
            **context_metrics
        })

        # 如果之前有同一 OG 的 order 记录，移除，以 trade 记录为准
        if og_dup and og_dup.id in self._order_log_index:
            idx = self._order_log_index.pop(og_dup.id)
            try:
                self.trades.pop(idx)
            except Exception:
                pass

        # 标记已记录的 OrderGroup，避免 notify_order 再次写入
        if og_dup:
            self.logged_order_groups.add(og_dup.id)

    def notify_order(self, order):
        """
        捕获 OrderGroup 层面的平仓，以便记录每个 bracket 的交易明细。
        Backtrader 的 trade 是净头寸级别，可能不会为同向加仓单触发关闭事件，这里补充记录。
        """
        strategy = getattr(self, 'strategy', None)
        if not strategy:
            return
        order_groups = getattr(strategy, 'order_groups', None)
        if not order_groups:
            return

        # 匹配 order 属于哪个 OrderGroup
        og = None
        for g in order_groups:
            if order in [g.main_order, g.stop_order, g.limit_order]:
                og = g
                break
        if not og:
            return

        # 只有止损/止盈完成且未记录过时写入
        if order.status != order.Completed:
            return
        if og.id in self.logged_order_groups:
            return
        if order not in [og.stop_order, og.limit_order]:
            return  # 只在平仓时记录
        if not og.entry_time or og.exit_time is None or og.entry_price is None or og.exit_price is None:
            return

        # 计算基础字段
        entry_dt = og.entry_time
        exit_dt = og.exit_time
        is_long = og.is_long
        size = 1.0
        mult = 50  # 默认 ES 合约乘数
        pnl = (og.exit_price - og.entry_price) * size * mult if is_long else (og.entry_price - og.exit_price) * size * mult
        pnlcomm = pnl - 2.0  # 与策略保持一致：$1 开仓 + $1 平仓

        # 会话因子
        try:
            factor_entry_session = self._get_session_type(entry_dt)
            factor_exit_session = self._get_session_type(exit_dt)
        except Exception:
            factor_entry_session = None
            factor_exit_session = None

        record = {
            'entry_time': entry_dt,
            'exit_time': exit_dt,
            'symbol': getattr(strategy.datas[0], '_name', ''),
            'direction': 'LONG' if is_long else 'SHORT',
            'size': size,
            'entry_price': og.entry_price,
            'exit_price': og.exit_price,
            'pnl': pnl,
            'pnl_net': pnlcomm,
            'funding_fee': 0.0,
            'bars_held': None,
            'source': 'order',
            'factor_entry_session': factor_entry_session,
            'factor_exit_session': factor_exit_session,
            # 下方因子无法精确重建，填 None 以保持 schema 对齐
            'factor_mom1': None,
            'factor_mom2': None,
            'factor_market_direction': None,
            'factor_trend_alignment': None,
            'factor_is_choppy': None,
            'factor_reached_abcd': None,
            'factor_max_drawdown_before_abcd': None,
            'factor_shadow_gap': None,
            'factor_has_shadow_gap': None,
            'factor_shadow_gap_ratio': None,
            'factor_body_gap': None,
            'factor_has_body_gap': None,
            'factor_body_gap_ratio': None,
            'factor_crossed_k3_extreme': None,
            'factor_overlap_5': None,
            'factor_overlap_10': None,
            'factor_overlap_15': None,
            'factor_overlap_20': None,
            'factor_overlap_25': None,
            'factor_overlap_30': None,
        }

        self.trades.append(record)
        # 记录索引，若后续收到 notify_trade 用 trade 记录替换
        self._order_log_index[og.id] = len(self.trades) - 1
        self.logged_order_groups.add(og.id)


    def get_analysis(self):
        return self.trades

    def save_to_parquet(self, filepath):
        if not self.trades:
            return
        
        df = pd.DataFrame(self.trades)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # 使用 DuckDB 保存 (或者直接 pandas to_parquet)
        # 这里演示用 DuckDB
        conn = duckdb.connect()
        conn.execute(f"CREATE TABLE trades AS SELECT * FROM df")
        conn.execute(f"COPY trades TO '{filepath}' (FORMAT PARQUET)")
        conn.close()

    def _get_signal_context_from_strategy(self, trade):
        """
        从策略的 OrderGroup 中获取信号上下文
        
        Args:
            trade: backtrader trade object
        
        Returns:
            signal_context dict or None
        """
        strategy = getattr(self, 'strategy', None)
        if not strategy:
            return None
        
        order_groups = getattr(strategy, 'order_groups', None)
        if not order_groups:
            return None
        
        # 尝试通过时间和价格匹配 OrderGroup
        entry_price = trade.price
        entry_bar = trade.baropen
        
        for og in order_groups:
            if og.is_closed() and og.entry_price:
                # 匹配逻辑：价格接近 + bar 接近
                if abs(og.entry_price - entry_price) < 0.01:
                    # 进一步验证 bar 范围（允许一定偏差）
                    signal_bar = og.signal_context.get('signal_bar', -999)
                    if abs(signal_bar - entry_bar) < 5:
                        return og.signal_context
        
        return None

    def _find_matching_order_group(self, trade):
        """
        查找与 trade 对象匹配的 OrderGroup
        
        Args:
            trade: backtrader trade object
        
        Returns:
            OrderGroup object or None
        """
        strategy = getattr(self, 'strategy', None)
        if not strategy:
            return None
        
        order_groups = getattr(strategy, 'order_groups', None)
        if not order_groups:
            return None
        
        # 通过价格和时间匹配 OrderGroup
        try:
            entry_dt = bt.num2date(trade.dtopen)
        except:
            return None
        
        for og in order_groups:
            if og.is_closed() and og.entry_price and og.entry_time:
                # 匹配逻辑：时间精确匹配（秒级）
                time_diff = abs((og.entry_time - entry_dt).total_seconds())
                if time_diff < 60:  # 1分钟内的时间差
                    return og
        
        return None

    def _get_market_context(self, bar_index):
        """
        从策略中获取某个 bar 的市场背景 (DMI) 信息，用于记录交易背景。
        """
        strategy = getattr(self, 'strategy', None)
        context = getattr(strategy, 'market_context', None) if strategy else None
        if isinstance(context, dict):
            return context.get(bar_index)
        return None

    def _get_session_type(self, dt_utc):
        """
        判断 UTC 时间属于 CME RTH 还是 ETH
        
        RTH (Regular Trading Hours): 周一-周五 08:30-15:15 CT
        ETH (Extended Trading Hours): 其他所有时间
        
        Args:
            dt_utc: datetime with UTC timezone (from bt.num2date)
            
        Returns:
            'RTH' or 'ETH'
        """
        # 转换为芝加哥时间
        chicago_tz = pytz.timezone('America/Chicago')
        dt_ct = dt_utc.astimezone(chicago_tz)
        
        # 检查是否为工作日 (Monday=0, Sunday=6)
        weekday = dt_ct.weekday()
        
        # RTH: 周一-周五 08:30-15:15
        if weekday < 5:  # Monday-Friday
            time_ct = dt_ct.time()
            rth_start = time(8, 30)
            rth_end = time(15, 15)
            
            if rth_start <= time_ct <= rth_end:
                return 'RTH'
        
        return 'ETH'

    def _calculate_momentum(self, data, idx, lookback=6):
        """
        计算指定 bar 索引的 DEMA 动量指标
        
        基于 Pine Script:
        - dema = ta.ema(ta.ema(close, lookback), lookback)
        - mom1 = ta.mom(dema, lookback/2)  # 一阶动量
        - mom2 = ta.mom(mom1, lookback/2)  # 二阶动量
        
        Args:
            data: Backtrader data feed
            idx: bar 索引 (K3 索引)
            lookback: EMA 周期，默认 6
            
        Returns:
            (dema, mom1, mom2): DEMA 值、一阶动量、二阶动量
        """
        try:
            # 需要足够的历史数据
            # DEMA 需要 2*lookback，动量需要额外的 lookback/2
            history_length = lookback * 2 + math.ceil(lookback / 2) + 10
            start_idx = max(0, idx - history_length + 1)
            
            # 提取收盘价
            close_prices = []
            for i in range(start_idx, idx + 1):
                try:
                    close_prices.append(data.close.array[i])
                except:
                    break
            
            if len(close_prices) < lookback * 2:
                # 数据不足，返回 0
                return 0.0, 0.0, 0.0
            
            # 使用 pandas 计算 EMA
            df = pd.DataFrame({'close': close_prices})
            
            # 计算 DEMA (Double EMA)
            ema1 = df['close'].ewm(span=lookback, adjust=False).mean()
            dema = ema1.ewm(span=lookback, adjust=False).mean()
            
            # 计算一阶动量 (Momentum)
            half_lookback = round(lookback / 2)
            mom1 = dema.diff(half_lookback)
            
            # 计算二阶动量 (Momentum of Momentum)
            mom2 = mom1.diff(half_lookback)
            
            # 返回最后一个值
            dema_val = dema.iloc[-1] if len(dema) > 0 and not pd.isna(dema.iloc[-1]) else 0.0
            mom1_val = mom1.iloc[-1] if len(mom1) > 0 and not pd.isna(mom1.iloc[-1]) else 0.0
            mom2_val = mom2.iloc[-1] if len(mom2) > 0 and not pd.isna(mom2.iloc[-1]) else 0.0
            
            return float(dema_val), float(mom1_val), float(mom2_val)
            
        except Exception as e:
            # 出错时返回 0
            return 0.0, 0.0, 0.0



    def _find_signal_bars(self, data, trade_open_idx, is_long, stop_loss_price=None):
        """
        寻找触发信号的 K1, K2, K3
        优先匹配 K1 极值等于止损价的信号组合
        """
        candidates = []
        
        # Search backwards for the 3-candle pattern
        for i in range(1, 6):
            k3_idx = trade_open_idx - i
            k2_idx = k3_idx - 1
            k1_idx = k2_idx - 1
            
            if k1_idx < 0:
                continue
                
            try:
                c1 = data.close.array[k1_idx]
                o1 = data.open.array[k1_idx]
                h1 = data.high.array[k1_idx]
                l1 = data.low.array[k1_idx]
                
                c2 = data.close.array[k2_idx]
                o2 = data.open.array[k2_idx]
                h2 = data.high.array[k2_idx]
                l2 = data.low.array[k2_idx]
                
                c3 = data.close.array[k3_idx]
                o3 = data.open.array[k3_idx]
                h3 = data.high.array[k3_idx]
                l3 = data.low.array[k3_idx]
                
                is_match = False
                if is_long:
                    # 三连阳 且 低点抬高
                    if (c1 > o1 and c2 > o2 and c3 > o3) and \
                       (l3 > l2 > l1):
                        is_match = True
                else:
                    # 三连阴 且 高点降低
                    if (c1 < o1 and c2 < o2 and c3 < o3) and \
                       (h3 < h2 < h1):
                        is_match = True
                
                if is_match:
                    candidates.append((k1_idx, k2_idx, k3_idx))
            except:
                continue
        
        if not candidates:
            # Fallback
            return trade_open_idx - 3, trade_open_idx - 2, trade_open_idx - 1
            
        # 如果有止损价，尝试匹配
        if stop_loss_price is not None:
            for k1, k2, k3 in candidates:
                try:
                    if is_long:
                        # 做多止损在 K1 Low
                        k1_low = data.low.array[k1]
                        if abs(k1_low - stop_loss_price) < 0.01: # 允许微小误差
                            return k1, k2, k3
                    else:
                        # 做空止损在 K1 High
                        k1_high = data.high.array[k1]
                        if abs(k1_high - stop_loss_price) < 0.01:
                            return k1, k2, k3
                except:
                    continue
        
        # 如果没有匹配或没有止损价，返回最近的一个（Offset 最小的，即列表第一个）
        # 注意：上面的循环是从 1 到 5，所以 candidates[0] 是最近的
        return candidates[0]

    def _calculate_abcd_factors(self, trade, data, is_long, entry_price, k1_low, k1_high):
        """
        计算 AB=CD 背景因子：
        1. factor_reached_abcd: 是否到达过二推目标价 D
        2. factor_max_drawdown_before_abcd: 到达 D 之前的最大回撤比率
        
        AB=CD 模式定义（以做多为例）：
        A = K1 低点
        B = K3 收盘价（入场价）
        C = 持仓期间的动态最低价（每次新低重置）
        D = C + (B - A) = C + AB幅度（二推目标价）
        
        Args:
            trade: backtrader trade object
            data: price data feed
            is_long: True if LONG, False if SHORT
            entry_price: entry price (K3 close)
            k1_low: K1 bar's low price
            k1_high: K1 bar's high price
        
        Returns:
            dict with 'reached_abcd' and 'max_drawdown_ratio'
        """
        reached_abcd = False
        max_drawdown_ratio = None
        first_reach_bar_index = None
        
        # 计算 AB 幅度
        if is_long:
            ab_range = entry_price - k1_low
        else:
            ab_range = k1_high - entry_price
        
        # 如果 AB 幅度为 0 或负数，无法计算
        if ab_range <= 0:
            return {'reached_abcd': False, 'max_drawdown_ratio': None}
        
        # 逐 bar 扫描，检查是否到达 D
        # 关键修复：必须在持仓期间到达 D 才算，如果止损先触发则不算
        if is_long:
            # 做多：C 是动态最低价，D = C + AB幅度
            # 止损价 = K1 低点
            stop_loss_price = k1_low
            running_lowest = entry_price
            
            for i in range(trade.baropen, trade.barclose + 1):
                try:
                    # 获取当前bar的最低价和最高价
                    bar_low = data.low.array[i]
                    # 获取当前bar的最高价
                    bar_high = data.high.array[i]
                    
                    # ⚠️ 关键修复：先检查止损是否触发
                    if bar_low <= stop_loss_price:
                        # 止损触发，交易结束，未到达二推
                        reached_abcd = False
                        break
                    
                    # 更新动态最低价 C
                    running_lowest = min(running_lowest, bar_low)
                    
                    # 计算当前的 D 点
                    d_target = running_lowest + ab_range
                    
                    # 检查是否到达 D（此时止损未触发）
                    if bar_high >= d_target:
                        # 到达D点
                        reached_abcd = True
                        # 记录首次到达D点的bar索引
                        first_reach_bar_index = i
                        break # 退出循环
                except (IndexError, Exception):
                    continue
            
            # 如果到达了 D，计算到达前的最大回撤比率
            if reached_abcd and first_reach_bar_index is not None:
                try:
                    lowest_before_d = entry_price
                    for i in range(trade.baropen, first_reach_bar_index + 1):
                        bar_low = data.low.array[i]
                        lowest_before_d = min(lowest_before_d, bar_low)
                    
                    # 最大回撤比率 = (入场价 - 期间最低价) / AB幅度
                    max_drawdown_ratio = (entry_price - lowest_before_d) / ab_range
                except (IndexError, Exception):
                    max_drawdown_ratio = None
        
        else:
            # 做空：C 是动态最高价，D = C - AB幅度
            # 止损价 = K1 高点
            stop_loss_price = k1_high
            running_highest = entry_price
            
            for i in range(trade.baropen, trade.barclose + 1):
                try:
                    bar_low = data.low.array[i]
                    bar_high = data.high.array[i]
                    
                    # ⚠️ 关键修复：先检查止损是否触发
                    if bar_high >= stop_loss_price:
                        # 止损触发，交易结束，未到达二推
                        reached_abcd = False
                        break
                    
                    # 更新动态最高价 C
                    running_highest = max(running_highest, bar_high)
                    
                    # 计算当前的 D 点
                    d_target = running_highest - ab_range
                    
                    # 检查是否到达 D（此时止损未触发）
                    if bar_low <= d_target:
                        # 到达D点
                        reached_abcd = True
                        # 记录首次到达D点的bar索引
                        first_reach_bar_index = i
                        break # 退出循环
                except (IndexError, Exception):
                    continue
            
            # 如果到达了 D，计算到达前的最大回撤比率
            if reached_abcd and first_reach_bar_index is not None:
                try:
                    highest_before_d = entry_price
                    for i in range(trade.baropen, first_reach_bar_index + 1):
                        bar_high = data.high.array[i]
                        highest_before_d = max(highest_before_d, bar_high)
                    
                    # 最大回撤比率 = (期间最高价 - 入场价) / AB幅度
                    max_drawdown_ratio = (highest_before_d - entry_price) / ab_range
                except (IndexError, Exception):
                    max_drawdown_ratio = None
        
        return {
            'reached_abcd': reached_abcd,
            'max_drawdown_ratio': max_drawdown_ratio
        }
