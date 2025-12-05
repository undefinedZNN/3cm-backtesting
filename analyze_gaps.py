from pathlib import Path
import pandas as pd
import numpy as np
import sys

INPUT = 'output/test_run_1s.csv'
OUTPUT = 'gap_analysis_mom_session_1s.md'


def pct(x: float) -> str:
    return f"{x:.2f}%"


def currency(x: float) -> str:
    return f"${x:,.2f}"


def to_md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "| (空) |"
    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    body = ["| " + " | ".join(map(str, row)) + " |" for row in df.to_numpy()]
    return "\n".join([header, sep] + body)


def build_bins(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    max_ratio = df['factor_shadow_gap_ratio'].max()
    bins = np.arange(0, max_ratio + 0.02, 0.01)
    df = df.copy()
    df['ratio_bin'] = pd.cut(df['factor_shadow_gap_ratio'], bins=bins)
    stats = df.groupby('ratio_bin', observed=True).agg(
        交易数=('pnl', 'count'),
        胜率=('pnl', lambda x: (x > 0).mean() * 100)
    ).reset_index()
    stats = stats[stats['交易数'] > 0]
    stats['缺口比例区间'] = stats['ratio_bin'].map(lambda x: f"{x.left:.2%}-{x.right:.2%}")
    stats = stats[['缺口比例区间', '交易数', '胜率']]
    stats['胜率'] = stats['胜率'].apply(pct)
    return stats


def build_thresholds(df: pd.DataFrame, thresholds) -> pd.DataFrame:
    rows = []
    for t in thresholds:
        sub = df[df['factor_shadow_gap_ratio'] >= t]
        if len(sub) == 0:
            continue
        rows.append({
            '缺口比例 >=': f"{t:.1%} ({t:.2f})",
            '交易数': len(sub),
            '胜率': pct((sub['pnl'] > 0).mean() * 100)
        })
    return pd.DataFrame(rows)


def build_thresholds_by_alignment(df: pd.DataFrame, thresholds) -> pd.DataFrame:
    rows = []
    for t in thresholds:
        sub = df[df['factor_shadow_gap_ratio'] >= t]
        if len(sub) == 0:
            continue
        grouped = sub.groupby('mom_alignment', observed=True)
        for align, g in grouped:
            rows.append({
                '缺口比例 >=': f"{t:.1%} ({t:.2f})",
                'mom顺逆': align,
                '交易数': len(g),
                '胜率': pct((g['pnl'] > 0).mean() * 100)
            })
    return pd.DataFrame(rows)


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else INPUT
    df = pd.read_parquet(input_path) if input_path.endswith('.parquet') else pd.read_csv(input_path, parse_dates=['entry_time', 'exit_time'])

    # session 划分
    def session(row):
        return 'RTH' if row['factor_entry_session'] == 'RTH' and row['factor_exit_session'] == 'RTH' else 'ETH'

    df['session'] = df.apply(session, axis=1)

    # mom2 趋势方向
    df['mom_trend'] = np.where(df['factor_mom2'] >= 0, 'trend_up', 'trend_down')

    # 方向与 mom 顺/逆（基于 mom2）
    def mom_alignment(row):
        if (row['mom_trend'] == 'trend_up' and row['direction'] == 'LONG') or \
           (row['mom_trend'] == 'trend_down' and row['direction'] == 'SHORT'):
            return 'aligned'
        return 'opposite'

    df['mom_alignment'] = df.apply(mom_alignment, axis=1)

    # mom 顺势细分：
    #  - mom2>0 且 mom1>0 -> mom2&mom1>0
    #  - mom2>0 -> mom2>0
    #  - mom1>0 -> mom1>0
    #  其它 -> opposite
    def mom_alignment_fine(row):
        m2_up = row['factor_mom2'] > 0
        m1_up = row['factor_mom1'] > 0
        if m2_up and m1_up:
            return 'mom2&mom1>0'
        if m2_up:
            return 'mom2>0'
        if m1_up:
            return 'mom1>0'
        return 'opposite'

    df['mom_alignment_fine'] = df.apply(mom_alignment_fine, axis=1)

    # 仅有影线缺口
    df_gap = df[df['factor_has_shadow_gap'] == True].copy()

    thresholds = [0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]

    lines = []
    lines.append(f"# 影线缺口 + mom 顺/逆势 分析 ({input_path})")
    lines.append("")
    lines.append(f"- 总交易数: {len(df)}")
    lines.append(f"- 有影线缺口交易: {len(df_gap)}")
    lines.append("")

    for sess in ['ALL', 'RTH', 'ETH']:
        subset = df_gap if sess == 'ALL' else df_gap[df_gap['session'] == sess]
        lines.append(f"## {sess} 时段")
        lines.append(f"- 影线缺口交易数: {len(subset)} | 胜率: {pct((subset['pnl'] > 0).mean() * 100) if len(subset) else '0.00%'}")
        lines.append("")

        # mom 顺/逆汇总
        align_stats = subset.groupby('mom_alignment', observed=True).agg(
            交易数=('pnl', 'count'),
            胜率=('pnl', lambda x: (x > 0).mean() * 100)
        ).reset_index().rename(columns={'mom_alignment': 'mom顺逆'})
        if not align_stats.empty:
            align_stats['胜率'] = align_stats['胜率'].apply(pct)
            lines.append("### mom 顺/逆势汇总")
            lines.append(to_md_table(align_stats))
            lines.append("")

        # mom 细分汇总
        fine_stats = subset.groupby('mom_alignment_fine', observed=True).agg(
            交易数=('pnl', 'count'),
            胜率=('pnl', lambda x: (x > 0).mean() * 100)
        ).reset_index().rename(columns={'mom_alignment_fine': 'mom细分'})
        if not fine_stats.empty:
            fine_stats['胜率'] = fine_stats['胜率'].apply(pct)
            lines.append("### mom 细分汇总 (mom2/mom1)")
            lines.append(to_md_table(fine_stats))
            lines.append("")

        # 1% 分箱
        bin_stats = build_bins(subset)
        lines.append("### 按 1% 缺口分箱")
        lines.append(to_md_table(bin_stats))
        lines.append("")

        # 累积阈值
        cum_df = build_thresholds(subset, thresholds)
        lines.append("### 累积阈值 (缺口比例 >=)")
        lines.append(to_md_table(cum_df))
        lines.append("")

        # 累积阈值 + mom 顺/逆
        cum_align_df = build_thresholds_by_alignment(subset, thresholds)
        lines.append("### 累积阈值 + mom 顺/逆")
        lines.append(to_md_table(cum_align_df))
        lines.append("")

    Path(OUTPUT).write_text("\n".join(lines), encoding='utf-8')
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
