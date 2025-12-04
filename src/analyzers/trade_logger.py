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

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        # 从 trade 对象直接获取信息
        data = trade.data
        
        # 开仓和平仓信息
        entry_price = trade.price  # 平均开仓价
        exit_price_calc = 0.0
        
        # trade.size 在某些情况下可能为 0（因为已经平仓）
        # 我们需要通过其他方式判断方向
        # 对于 bracket orders，我们可以通过止损/止盈价格关系判断
        
        # 从 baropen 和 barclose 的价格变化判断方向
        try:
            open_bar_price = data.close.array[trade.baropen]
            close_bar_price = data.close.array[trade.barclose]
        except:
            open_bar_price = entry_price
            close_bar_price = entry_price
        
        
        # 获取 PnL（后续需要用于反推平仓价格）
        pnl = trade.pnl
        price_change = close_bar_price - open_bar_price
        
        # 判断交易方向
        # Backtrader 的 trade 对象有一个 'long' 属性用于记录原始开仓方向
        # 即使在平仓后，这个属性仍然保留原始方向信息
        is_long = True  # 默认值
        
        if hasattr(trade, 'long'):
            # trade.long 是一个列表，包含所有做多的事件
            # 如果 len(trade.long) > 0，说明是做多交易
            # 否则是做空交易
            try:
                is_long = len(trade.long) > 0
            except:
                # 如果 trade.long 不是列表而是布尔值
                is_long = bool(trade.long)
        else:
            # 备用方案：使用 PnL 和价格变化推断
            if pnl != 0 and price_change != 0:
                is_long = (pnl * price_change) > 0
        
        direction = 'LONG' if is_long else 'SHORT'
        size = 1.0  # 固定为 1 手
        
        # 使用 trade.dtopen/dtclose 获取成交时间，避免 baropen 偏移导致的 1 根（5 分钟）延迟
        # dtopen/dtclose 是实际成交时刻；若不可用再回退到 bar 索引
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
        entry_value = entry_price * size * 50  # 合约价值 = 价格 * 手数 * 合约乘数
        
        if size != 0:
            # pnl = (exit_price - entry_price) * size * multiplier (做多)
            # pnl = (entry_price - exit_price) * size * multiplier (做空)
            if is_long:
                exit_price_calc = entry_price + (pnl / (size * 50))
            else:
                exit_price_calc = entry_price - (pnl / (size * 50))
        else:
            exit_price_calc = entry_price
        
        # 盈亏
        pnlcomm = trade.pnlcomm  # 扣除佣金后的盈亏
        
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

        # --- 计算背景信息 ---
        # 使用 _find_signal_bars 找到正确的 K1, K2, K3
        # 如果是亏损单，尝试使用 exit_price 作为止损价来辅助定位 K1
        # 注意：这假设亏损是因为触及止损，对于手动平仓或反向信号平仓可能不适用，但作为启发式方法很有用
        stop_loss_price_hint = None
        if pnl < 0:
            # 如果是亏损，exit_price 很可能就是止损价
            # 但要注意滑点，所以 _find_signal_bars 中允许微小误差
            stop_loss_price_hint = exit_price_calc
            
        # 确定 K1, K2, K3 的索引
        idx_k1, idx_k2, idx_k3 = self._find_signal_bars(data, trade.baropen, is_long, stop_loss_price_hint)
        
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
