import backtrader as bt
import duckdb
import pandas as pd
import os
import glob

class DuckDBData(bt.feeds.PandasData):
    """
    扩展的 PandasData 类，支持额外的列（如 funding_rate）
    """
    lines = ('funding_rate',)
    params = (
        ('funding_rate', -1), # 如果 dataframe 中没有 funding_rate 列，则自动匹配或忽略
    )

def load_data(parquet_path, start_date=None, end_date=None, resample=None, timeframe='timestamp'):
    """
    使用 DuckDB 读取 Parquet 文件并返回 Backtrader 可用的 PandasData feed。
    
    Args:
        parquet_path (str): Parquet 文件路径或目录路径（如果是目录，会读取所有 parquet 文件）
        start_date (str, optional): 开始日期 'YYYY-MM-DD'
        end_date (str, optional): 结束日期 'YYYY-MM-DD'
        resample (str, optional): 重采样周期，如 '5T' (5分钟), '1H' (1小时) 等
        timeframe (str): 时间列名称，默认 'timestamp' 也支持 'datetime'
        
    Returns:
        bt.feeds.PandasData: Backtrader 数据源
    """
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"文件或目录未找到: {parquet_path}")

    # 判断是文件还是目录
    if os.path.isdir(parquet_path):
        # 如果是目录，查找所有 parquet 文件
        parquet_files = glob.glob(os.path.join(parquet_path, '**', '*.parquet'), recursive=True)
        if not parquet_files:
            raise FileNotFoundError(f"目录中未找到任何 parquet 文件: {parquet_path}")
        print(f"找到 {len(parquet_files)} 个 parquet 文件")
        # 使用 UNION ALL 合并所有文件，排除分区列
        file_queries = [f"SELECT timestamp, open, high, low, close, volume FROM read_parquet('{f}')" for f in parquet_files]
        base_query = " UNION ALL ".join(file_queries)
    else:
        # 单个文件，排除分区列（如果存在）
        base_query = f"SELECT timestamp, open, high, low, close, volume FROM read_parquet('{parquet_path}')"

    # 构建完整的 SQL 查询
    query = f"SELECT * FROM ({base_query})"
    
    conditions = []
    if start_date:
        conditions.append(f"{timeframe} >= '{start_date}'")
    if end_date:
        conditions.append(f"{timeframe} <= '{end_date}'")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += f" ORDER BY {timeframe}"

    # 使用 DuckDB 读取数据
    conn = duckdb.connect(database=':memory:')
    df = conn.execute(query).df()
    conn.close()

    # 确保时间列是 datetime 类型并设为索引
    if timeframe in df.columns:
        df[timeframe] = pd.to_datetime(df[timeframe])
        df.set_index(timeframe, inplace=True)
    elif 'datetime' in df.columns and timeframe != 'datetime':
        # 兼容性：尝试 datetime 列
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
    else:
        raise ValueError(f"Parquet 文件必须包含 '{timeframe}' 或 'datetime' 列")

    # 数据重采样
    if resample:
        print(f"正在将数据重采样为 {resample}...")
        original_len = len(df)
        df = df.resample(resample).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        print(f"  原始数据: {original_len} 行")
        print(f"  重采样后: {len(df)} 行")

    # 检查是否有 funding_rate 列
    if 'funding_rate' not in df.columns:
        df['funding_rate'] = 0.0 # 或者 NaN，取决于需求

    # 创建 Backtrader 数据源
    # 映射标准列
    data = DuckDBData(
        dataname=df,
        open='open',
        high='high',
        low='low',
        close='close',
        volume='volume',
        openinterest=-1, # 如果没有持仓量数据
        funding_rate='funding_rate'
    )
    
    return data

