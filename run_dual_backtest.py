"""
Run two independent backtests for long-only and short-only accounts.

Each run uses the same data and strategy, but forces direction:
  - LONG_ONLY: 只做多
  - SHORT_ONLY: 只做空

Outputs:
  output/es_trade_details_long.parquet
  output/es_trade_details_short.parquet
  output/es_trade_details_combined.parquet (合并并打上 account 标签)
"""

import os
from pathlib import Path
import pandas as pd

from src.main import run_backtest


def main():
    data_path = 'data/batch_18.parquet'
    out_dir = Path('output')
    out_dir.mkdir(exist_ok=True)

    long_path = out_dir / 'es_trade_details_long.parquet'
    short_path = out_dir / 'es_trade_details_short.parquet'
    combined_path = out_dir / 'es_trade_details_combined.parquet'

    print('\n=== 运行 LONG_ONLY 账户 ===')
    run_backtest(
        parquet_path=data_path,
        output_path=str(long_path),
        direction_mode='LONG_ONLY',
    )

    print('\n=== 运行 SHORT_ONLY 账户 ===')
    run_backtest(
        parquet_path=data_path,
        output_path=str(short_path),
        direction_mode='SHORT_ONLY',
    )

    # 合并并打上 account 标签，便于后续统计
    df_long = pd.read_parquet(long_path)
    df_long['account'] = 'LONG_ONLY'

    df_short = pd.read_parquet(short_path)
    df_short['account'] = 'SHORT_ONLY'

    combined = pd.concat([df_long, df_short], ignore_index=True)
    if 'entry_time' in combined.columns:
        combined = combined.sort_values('entry_time').reset_index(drop=True)
    combined.to_parquet(combined_path)

    print('\n=== 合并结果 ===')
    print(f'  LONG_ONLY 交易数: {len(df_long)}')
    print(f'  SHORT_ONLY 交易数: {len(df_short)}')
    print(f'  合并交易数: {len(combined)} -> {combined_path}')


if __name__ == '__main__':
    main()
