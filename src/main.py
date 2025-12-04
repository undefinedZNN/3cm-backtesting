import backtrader as bt
import sys
import os
from datetime import datetime

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_data
from strategies.three_candles import ThreeCandlesStrategy
from analyzers.trade_logger import TradeLogger

def run_backtest(parquet_path, output_path='output/trade_details.parquet', 
                 initial_cash=100000.0, commission=0.001, size=1.0,
                 resample='5T', contract_multiplier=50, margin=0.007, 
                 tick_size=0.25, timeframe='timestamp'):
    """
    运行回测
    
    Args:
        parquet_path (str): 输入数据的 Parquet 文件路径
        output_path (str): 输出交易明细的 Parquet 文件路径
        initial_cash (float): 初始资金
        commission (float): 手续费率
        size (float): 交易数量（手数）
        resample (str): 重采样周期，如 '5T' 表示5分钟
        contract_multiplier (float): 合约乘数
        margin (float): 保证金比例
        tick_size (float): 最小变动价位
        timeframe (str): 时间列名称
    """
    print(f"\n{'='*60}")
    print(f"开始回测 - 三连阳/阴策略 (ES 期货)")
    print(f"{'='*60}")
    print(f"数据源: {parquet_path}")
    print(f"初始资金: {initial_cash:,.2f}")
    print(f"合约乘数: {contract_multiplier}")
    print(f"保证金比例: {margin*100:.2f}%")
    print(f"最小变动价位: {tick_size}")
    print(f"手续费率: {commission*100:.3f}%")
    print(f"交易数量: {size} 手")
    print(f"数据重采样: {resample}")
    print(f"{'='*60}\n")

    # 创建 Cerebro 引擎
    cerebro = bt.Cerebro()

    # 加载数据
    print("正在加载数据...")
    try:
        data = load_data(parquet_path, resample=resample, timeframe=timeframe)
        cerebro.adddata(data)
        print("✓ 数据加载成功")
    except Exception as e:
        print(f"✗ 数据加载失败: {e}")
        import traceback
        traceback.print_exc()
        return None

    # 添加策略
    cerebro.addstrategy(ThreeCandlesStrategy, size=size)
    print("✓ 策略已添加: 三连阳/阴策略")

    # 添加分析器
    cerebro.addanalyzer(TradeLogger, _name='trade_logger')
    print("✓ 分析器已添加: TradeLogger")

    # 设置初始资金
    cerebro.broker.setcash(initial_cash)

    # 设置手续费 - 对于期货，使用固定佣金模式
    # 每手每点的价值 = 合约乘数
    # 手续费 = 每手固定费用
    cerebro.broker.setcommission(
        commission=commission,  # 如果是百分比
        mult=contract_multiplier,  # 合约乘数
        margin=margin  # 保证金比例
    )
    
    print(f"✓ 交易参数已配置")

    # 运行回测
    print(f"\n{'='*60}")
    print("开始执行回测...")
    print(f"{'='*60}\n")
    
    start_value = cerebro.broker.getvalue()
    print(f"初始资金: {start_value:,.2f}")
    
    results = cerebro.run()
    
    end_value = cerebro.broker.getvalue()
    print(f"\n{'='*60}")
    print("回测完成")
    print(f"{'='*60}")
    print(f"最终资金: {end_value:,.2f}")
    print(f"总盈亏: {end_value - start_value:,.2f}")
    print(f"收益率: {((end_value - start_value) / start_value * 100):.2f}%")
    print(f"{'='*60}\n")

    # 获取交易记录
    strategy = results[0]
    trade_logger = strategy.analyzers.trade_logger
    
    trades = trade_logger.get_analysis()
    print(f"交易笔数: {len(trades)}")
    
    if trades:
        # 保存到 Parquet
        print(f"\n正在保存交易明细到: {output_path}")
        try:
            trade_logger.save_to_parquet(output_path)
            print(f"✓ 交易明细已保存")
            
            # 打印交易统计
            import pandas as pd
            df = pd.DataFrame(trades)
            
            print(f"\n{'='*60}")
            print("交易统计")
            print(f"{'='*60}")
            print(f"总交易数: {len(df)}")
            print(f"做多交易: {len(df[df['direction'] == 'LONG'])}")
            print(f"做空交易: {len(df[df['direction'] == 'SHORT'])}")
            print(f"盈利交易: {len(df[df['pnl'] > 0])}")
            print(f"亏损交易: {len(df[df['pnl'] < 0])}")
            
            if len(df) > 0:
                print(f"胜率: {len(df[df['pnl'] > 0]) / len(df) * 100:.2f}%")
                
            if len(df[df['pnl'] > 0]) > 0:
                print(f"平均盈利: {df[df['pnl'] > 0]['pnl'].mean():.2f}")
            else:
                print(f"平均盈利: N/A")
                
            if len(df[df['pnl'] < 0]) > 0:
                print(f"平均亏损: {df[df['pnl'] < 0]['pnl'].mean():.2f}")
            else:
                print(f"平均亏损: N/A")
                
            print(f"最大单笔盈利: {df['pnl'].max():.2f}")
            print(f"最大单笔亏损: {df['pnl'].min():.2f}")
            print(f"平均持仓K线数: {df['bars_held'].mean():.1f}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"✗ 保存失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("⚠ 未产生任何交易")

    # 可选：绘制图表
    # cerebro.plot()

    return results

if __name__ == '__main__':
    # ES 期货参数
    data_file = '../data/batch_18.parquet'
    output_file = '../output/es_trade_details.parquet'
    
    # 如果命令行提供了参数
    if len(sys.argv) > 1:
        data_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    # 检查数据文件是否存在
    if not os.path.exists(data_file):
        print(f"错误: 数据文件不存在: {data_file}")
        print(f"\n请确保数据文件存在")
        sys.exit(1)
    
    # 运行回测 - ES 期货配置
    run_backtest(
        parquet_path=data_file,
        output_path=output_file,
        initial_cash=100000.0,
        commission=0.0001,  # 0.01% 手续费
        size=1.0,  # 1手
        resample='5T',  # 5分钟
        contract_multiplier=50,  # ES 合约乘数
        margin=0.007,  # 0.7% 保证金
        tick_size=0.25,  # 最小变动价位
        timeframe='timestamp'  # 时间列名称
    )
