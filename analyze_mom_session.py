from pathlib import Path
import pandas as pd
import numpy as np
import sys

INPUT = "output/es_trade_details_combined_1s.parquet"
OUTPUT = "mom_session_analysis.md"


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


def agg_stats(df: pd.DataFrame, group_cols) -> pd.DataFrame:
    grouped = df.groupby(group_cols, observed=True)
    stats = grouped.agg(
        交易数=("pnl", "count"),
        胜率=("pnl", lambda x: (x > 0).mean() * 100),
        平均盈亏=("pnl", "mean"),
    ).reset_index()
    stats["胜率"] = stats["胜率"].apply(pct)
    stats["平均盈亏"] = stats["平均盈亏"].apply(currency)
    return stats


def add_session(df: pd.DataFrame) -> pd.DataFrame:
    def session(row):
        return "RTH" if row["factor_entry_session"] == "RTH" and row["factor_exit_session"] == "RTH" else "ETH"

    df = df.copy()
    df["session"] = df.apply(session, axis=1)
    return df


def add_mom_labels(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mom2_dir"] = np.where(df["factor_mom2"] > 0, "mom2_up", "mom2_down")
    df["mom1_dir"] = np.where(df["factor_mom1"] > 0, "mom1_up", "mom1_down")
    df["mom_quadrant"] = df["mom2_dir"] + " & " + df["mom1_dir"]
    return df


def add_alignment(df: pd.DataFrame) -> pd.DataFrame:
    def alignment(row):
        if (row["direction"] == "LONG" and row["factor_mom2"] > 0) or (row["direction"] == "SHORT" and row["factor_mom2"] < 0):
            return "aligned_with_mom2"
        return "opposite_to_mom2"

    df = df.copy()
    df["direction_vs_mom2"] = df.apply(alignment, axis=1)
    return df


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else INPUT
    df = pd.read_parquet(input_path) if input_path.endswith(".parquet") else pd.read_csv(
        input_path, parse_dates=["entry_time", "exit_time"]
    )

    df = add_session(df)
    df = add_mom_labels(df)
    df = add_alignment(df)

    lines = []
    lines.append(f"# mom 因子 + 时段 分析 ({input_path})")
    lines.append("")
    lines.append(f"- 总交易数: {len(df)}")
    lines.append(f"- 胜率: {pct((df['pnl'] > 0).mean() * 100)}")
    lines.append("")

    for sess in ["ALL", "RTH", "ETH"]:
        subset = df if sess == "ALL" else df[df["session"] == sess]
        lines.append(f"## {sess} 时段")
        lines.append(f"- 交易数: {len(subset)} | 胜率: {pct((subset['pnl'] > 0).mean() * 100) if len(subset) else '0.00%'}")
        lines.append("")

        # mom2 正/负
        m2_stats = agg_stats(subset, ["mom2_dir"]).rename(columns={"mom2_dir": "mom2方向"})
        lines.append("### mom2 正/负")
        lines.append(to_md_table(m2_stats))
        lines.append("")

        # mom2 正/负 + 方向
        m2_dir_stats = agg_stats(subset, ["direction", "mom2_dir"]).rename(
            columns={"direction": "方向", "mom2_dir": "mom2方向"}
        )
        lines.append("### mom2 正/负 + 方向")
        lines.append(to_md_table(m2_dir_stats))
        lines.append("")

        # mom1 正/负
        m1_stats = agg_stats(subset, ["mom1_dir"]).rename(columns={"mom1_dir": "mom1方向"})
        lines.append("### mom1 正/负")
        lines.append(to_md_table(m1_stats))
        lines.append("")

        # mom1 正/负 + 方向
        m1_dir_stats = agg_stats(subset, ["direction", "mom1_dir"]).rename(
            columns={"direction": "方向", "mom1_dir": "mom1方向"}
        )
        lines.append("### mom1 正/负 + 方向")
        lines.append(to_md_table(m1_dir_stats))
        lines.append("")

        # mom1/mom2 组合
        quad_stats = agg_stats(subset, ["mom_quadrant"]).rename(columns={"mom_quadrant": "mom组合"})
        lines.append("### mom1/mom2 组合")
        lines.append(to_md_table(quad_stats))
        lines.append("")

        # mom1/mom2 组合 + 方向
        quad_dir_stats = agg_stats(subset, ["direction", "mom_quadrant"]).rename(
            columns={"direction": "方向", "mom_quadrant": "mom组合"}
        )
        lines.append("### mom1/mom2 组合 + 方向")
        lines.append(to_md_table(quad_dir_stats))
        lines.append("")

        # 方向与 mom2 顺逆
        align_stats = agg_stats(subset, ["direction", "direction_vs_mom2"]).rename(
            columns={"direction": "方向", "direction_vs_mom2": "mom2顺逆"}
        )
        lines.append("### 方向 vs mom2 顺逆")
        lines.append(to_md_table(align_stats))
        lines.append("")

    Path(OUTPUT).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
