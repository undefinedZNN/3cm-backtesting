import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

def create_sample_data(output_path='data/sample_data.parquet', num_bars=1000):
    """
    创建示例数据用于测试
    
    生成包含明确的3连阳和3连阴模式的数据
    """
    print(f"正在生成 {num_bars} 根K线的示例数据...")
    
    np.random.seed(42)
    
    # 基础价格
    base_price = 100.0
    
    data = []
    current_time = datetime(2023, 1, 1)
    i = 0
    
    while i < num_bars:
        # 每隔 20 根K线插入一个3连阳或3连阴信号
        if i > 5 and i % 30 == 10:  # 插入3连阳
            # 创建3连阳模式
            for j in range(3):
                open_price = base_price + np.random.uniform(-0.2, 0.2)
                close_price = open_price + np.random.uniform(0.8, 1.5)  # 保证是阳线
                high_price = close_price + np.random.uniform(0, 0.3)
                low_price = open_price - np.random.uniform(0, 0.3)
                
                data.append({
                    'datetime': current_time + timedelta(hours=i),
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': np.random.randint(1000, 10000),
                    'funding_rate': np.random.uniform(-0.0001, 0.0001)
                })
                base_price = close_price
                i += 1
            continue
            
        elif i > 5 and i % 30 == 20:  # 插入3连阴
            # 创建3连阴模式
            for j in range(3):
                open_price = base_price + np.random.uniform(-0.2, 0.2)
                close_price = open_price - np.random.uniform(0.8, 1.5)  # 保证是阴线
                high_price = open_price + np.random.uniform(0, 0.3)
                low_price = close_price - np.random.uniform(0, 0.3)
                
                data.append({
                    'datetime': current_time + timedelta(hours=i),
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': np.random.randint(1000, 10000),
                    'funding_rate': np.random.uniform(-0.0001, 0.0001)
                })
                base_price = close_price
                i += 1
            continue
        
        # 普通随机K线
        open_price = base_price + np.random.uniform(-0.5, 0.5)
        close_price = open_price + np.random.uniform(-1.0, 1.0)
        high_price = max(open_price, close_price) + np.random.uniform(0, 0.5)
        low_price = min(open_price, close_price) - np.random.uniform(0, 0.5)
        
        data.append({
            'datetime': current_time + timedelta(hours=i),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': np.random.randint(1000, 10000),
            'funding_rate': np.random.uniform(-0.0001, 0.0001)
        })
        
        base_price = close_price
        i += 1

    
    # 创建 DataFrame
    df = pd.DataFrame(data)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 保存为 Parquet
    df.to_parquet(output_path, index=False)
    
    print(f"✓ 示例数据已保存到: {output_path}")
    print(f"  - K线数量: {len(df)}")
    print(f"  - 时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
    print(f"  - 价格范围: {df['low'].min():.2f} - {df['high'].max():.2f}")
    
    return output_path

if __name__ == '__main__':
    create_sample_data()
