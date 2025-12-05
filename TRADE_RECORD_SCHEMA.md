# Trade Record Schema

交易明细由 `TradeLogger` 分析器生成，包含交易本身的信息、影线/实体缺口背景和 DMI 趋势背景。趋势字段仅用于记录，不参与交易决策。

## 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `entry_time` | datetime | 开仓成交时间（Backtrader `dtopen`，UTC） |
| `exit_time` | datetime | 平仓成交时间（Backtrader `dtclose`，UTC） |
| `symbol` | string | 交易品种名称 |
| `direction` | string | 方向：`LONG` / `SHORT` |
| `size` | float | 交易数量（手） |
| `entry_price` | float | 开仓价 |
| `exit_price` | float | 平仓价（根据 PnL 反推） |
| `pnl` | float | 毛盈亏 |
| `pnl_net` | float | 扣除手续费后的盈亏 |
| `funding_fee` | float | 资金费用累计 |
| `bars_held` | int | 持仓的 K 线数量 |
| `factor_entry_session` | string | 入场所在交易时段：`RTH` / `ETH` |
| `factor_exit_session` | string | 出场所在交易时段：`RTH` / `ETH` |
| `factor_mom1` | float | K3 时刻 DEMA 一阶动量 速度|
| `factor_mom2` | float | K3 时刻 DEMA 二阶动量 加速度 |
| `factor_market_direction` | string | DMI 判断的市场方向：`BULL` / `BEAR` / `NEUTRAL` |
| `factor_trend_alignment` | string | 交易方向与市场方向是否一致：`aligned` / `opposite` / `neutral`（仅记录，不影响交易逻辑） |
| `factor_is_choppy` | bool | 是否震荡：根据 ADX 是否低于阈值（默认 25） |
| `factor_shadow_gap` | float | 影线缺口大小 |
| `factor_has_shadow_gap` | bool | 是否存在影线缺口 |
| `factor_shadow_gap_ratio` | float | 影线缺口占信号 K 幅度比例 |
| `factor_body_gap` | float | 实体缺口大小 |
| `factor_has_body_gap` | bool | 是否存在实体缺口 |
| `factor_body_gap_ratio` | float | 实体缺口占信号 K 幅度比例 |
| `factor_crossed_k3_extreme` | bool | 持仓期间（止盈/止损前）是否突破过 K3 的高/低点；多头看高于 K3 高点，空头看低于 K3 低点 |
| `factor_overlap_5`~`factor_overlap_30` | float | K3 与前 N 根 K 线的重叠率（N=5,10,15,20,25,30） |

> 时间字段说明：`entry_time` / `exit_time` 直接来源于 Backtrader 的成交时间 (`dtopen`/`dtclose`)，为 UTC 时区；若转换本地时间，请自行转换时区。

## 趋势背景的计算方式

- 指标：Backtrader 内置 `DMI`（默认周期 14）。  
- 市场方向：`+DI` 与 `-DI` 差值大于缓冲（默认 1.0）则判为多/空，否则为 `NEUTRAL`。  
- 震荡判断：`ADX` 低于阈值（默认 25）则 `factor_is_choppy=True`。  
- 所有 `factor_` 字段仅作为背景记录，不改变下单逻辑。
