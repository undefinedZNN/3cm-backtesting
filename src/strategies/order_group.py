# -*- coding: utf-8 -*-
"""
OrderGroup - 订单组追踪系统

用于追踪 Backtrader bracket order 的完整生命周期，
包括主订单、止损订单和止盈订单。
"""

from enum import Enum
from datetime import datetime
import backtrader as bt


class OrderStatus(Enum):
    """订单组状态"""
    PENDING = 'PENDING'      # 主订单未成交
    ACTIVE = 'ACTIVE'        # 主订单成交，持仓中
    CLOSED = 'CLOSED'        # 止损或止盈触发，已平仓
    CANCELLED = 'CANCELLED'  # 订单被取消


class OrderGroup:
    """
    订单组类 - 追踪一个 bracket order 的完整生命周期
    
    Attributes:
        main_order: 主订单（入场订单）
        stop_order: 止损订单
        limit_order: 止盈订单
        signal_context: 信号背景数据（K1/K2/K3等）
        status: 订单组状态
        entry_price: 实际入场价格
        entry_time: 入场时间
        exit_price: 退出价格
        exit_time: 退出时间
        exit_reason: 退出原因（'STOP', 'LIMIT', 'OTHER'）
    """
    
    # 类变量：用于生成唯一ID
    _next_id = 1
    
    def __init__(self, orders, signal_context):
        """
        初始化订单组
        
        Args:
            orders: [main_order, stop_order, limit_order] from buy_bracket/sell_bracket
            signal_context: dict 包含信号背景信息
                {
                    'direction': 'LONG' or 'SHORT',
                    'k1_low': float,
                    'k1_high': float,
                    'k2_low': float,
                    'k2_high': float,
                    'k3_close': float,
                    'k3_low': float,
                    'k3_high': float,
                    'signal_bar': int,
                    'stop_price': float,
                    'limit_price': float,
                }
        """
        # 订单引用
        self.main_order = orders[0] if len(orders) > 0 else None
        self.stop_order = orders[1] if len(orders) > 1 else None
        self.limit_order = orders[2] if len(orders) > 2 else None
        
        # 信号背景
        self.signal_context = signal_context or {}
        
        # 状态追踪
        self.status = OrderStatus.PENDING
        self.entry_price = None
        self.entry_time = None
        self.exit_price = None
        self.exit_time = None
        self.exit_reason = None  # 'STOP', 'LIMIT', 'OTHER'
        
        # 唯一ID
        self.id = OrderGroup._next_id
        OrderGroup._next_id += 1
    
    @property
    def direction(self):
        """获取交易方向"""
        return self.signal_context.get('direction')
    
    @property
    def is_long(self):
        """是否为做多"""
        return self.direction == 'LONG'
    
    @property
    def is_short(self):
        """是否为做空"""
        return self.direction == 'SHORT'
    
    def is_pending(self):
        """是否为待成交状态"""
        return self.status == OrderStatus.PENDING
    
    def is_active(self):
        """是否为持仓中状态"""
        return self.status == OrderStatus.ACTIVE
    
    def is_closed(self):
        """是否已平仓"""
        return self.status in (OrderStatus.CLOSED, OrderStatus.CANCELLED)
    
    def activate(self, price, dt):
        """
        激活订单组（主订单成交）
        
        Args:
            price: 成交价格
            dt: 成交时间
        """
        self.status = OrderStatus.ACTIVE
        self.entry_price = price
        self.entry_time = dt
    
    def close(self, price, dt, reason):
        """
        平仓订单组
        
        Args:
            price: 平仓价格
            dt: 平仓时间
            reason: 平仓原因 ('STOP', 'LIMIT', 'OTHER')
        """
        self.status = OrderStatus.CLOSED
        self.exit_price = price
        self.exit_time = dt
        self.exit_reason = reason
    
    def cancel(self):
        """取消订单组"""
        self.status = OrderStatus.CANCELLED
    
    def __repr__(self):
        """字符串表示"""
        return (f"OrderGroup(id={self.id}, direction={self.direction}, "
                f"status={self.status.value}, entry_price={self.entry_price}, "
                f"exit_price={self.exit_price})")
