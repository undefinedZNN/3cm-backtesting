# Backtrader 回测系统 - 三连阳/阴策略

基于 Backtrader 的回测系统，使用 DuckDB + Parquet 进行数据管理，实现三连阳/阴交易策略。

## 功能特点

- ✅ 使用 DuckDB + Parquet 读取和存储数据
- ✅ 记录每笔交易的详细信息（开仓时间、盈亏、资金费率等）
- ✅ 计算丰富的背景信息（影线缺口、实体缺口、K线重叠率等）
- ✅ 自动计算止盈止损
- ✅ 支持做多和做空

## 项目结构

```
/Volumes/CODE/backtesting/
├── data/                  # 输入数据目录
│   └── sample_data.parquet
├── output/                # 输出结果目录
│   └── trade_details.parquet
├── src/
│   ├── data_loader.py     # 数据加载模块 (DuckDB)
│   ├── strategies/
│   │   └── three_candles.py  # 三连阳/阴策略
│   ├── analyzers/
│   │   └── trade_logger.py   # 交易日志记录器
│   └── main.py            # 主程序入口
├── create_sample_data.py  # 生成示例数据
├── requirements.txt
└── README.md
```

## 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 1. 生成示例数据

```bash
python create_sample_data.py
```

### 2. 运行回测

```bash
cd src
python main.py ../data/sample_data.parquet ../output/trade_details.parquet
```

### 3. 查看结果

使用 DuckDB 查看输出结果：

```bash
duckdb
D SELECT * FROM read_parquet('output/trade_details.parquet');
D SELECT direction, COUNT(*) as count, AVG(pnl) as avg_pnl FROM read_parquet('output/trade_details.parquet') GROUP BY direction;
```

或使用 Python：

```python
import pandas as pd
df = pd.read_parquet('output/trade_details.parquet')
print(df.head())
print(df.describe())
```

## 策略说明

### 入场条件

- **做多**: 连续3根阳线（收盘价 > 开盘价）
- **做空**: 连续3根阴线（收盘价 < 开盘价）

### 止盈止损

- **做多**
  - 止损: K1 的最低点
  - 止盈: K3收盘 + (K3收盘 - K1最低点)

- **做空**
  - 止损: K1 的最高点
  - 止盈: K3收盘 - (K1最高点 - K3收盘)

## 输出字段说明

| 字段 | 说明 |
|------|------|
| entry_time | 开仓时间 |
| exit_time | 平仓时间 |
| symbol | 交易品种 |
| direction | 方向 (LONG/SHORT) |
| size | 交易数量 |
| entry_price | 开仓价格 |
| exit_price | 平仓价格 |
| pnl | 盈亏金额 |
| pnl_net | 扣除手续费后的盈亏 |
| funding_fee | 资金费用 |
| bars_held | 持仓K线数 |
| shadow_gap | 影线缺口大小 |
| factor_has_shadow_gap | 是否存在影线缺口 |
| factor_shadow_gap_ratio | 影线缺口与信号K幅度的比率 |
| factor_body_gap | 实体缺口大小 |
| factor_has_body_gap | 是否存在实体缺口 |
| factor_body_gap_ratio | 实体缺口与信号K幅度的比率 |
| factor_overlap_5 ~ factor_overlap_30 | K3与前N根K线的重叠率 |
| factor_market_direction | DMI 判断的市场方向 |
| factor_trend_alignment | 交易方向是否顺势 |
| factor_is_choppy | 是否震荡 (ADX 低于阈值) |
| factor_crossed_k3_extreme | 持仓期间是否突破信号K3的高/低点 |

## 自定义配置

在 `src/main.py` 的 `run_backtest()` 函数中可以调整：

- `initial_cash`: 初始资金（默认 100,000）
- `commission`: 手续费率（默认 0.001 即 0.1%）
- `size`: 每次交易数量（默认 1.0）

## 依赖项

- backtrader: 回测引擎
- duckdb: 高性能数据库
- pandas: 数据处理
- pyarrow: Parquet 文件支持
- matplotlib: 图表绘制

## 许可证

MIT
