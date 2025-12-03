"""Visualization functions for Twitter archive data.

This module provides chart generation using Plotly for both static image export
and interactive web display.
"""

import os
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio


def create_monthly_counts_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create a time series chart of monthly record counts by type.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Plotly Figure or None if no date data available.
    """
    if "created_at" not in df.columns or not df["created_at"].notna().any():
        return None

    ts = (
        df.dropna(subset=["created_at"])
        .set_index("created_at")
        .assign(count=1)
        .groupby([pd.Grouper(freq="ME"), "record_type"])["count"]
        .sum()
        .reset_index()
    )

    if ts.empty:
        return None

    fig = px.line(
        ts,
        x="created_at",
        y="count",
        color="record_type",
        title="Monthly Record Counts by Type",
        markers=True,
    )
    fig.update_layout(hovermode="x unified")
    return fig


def create_text_length_histogram(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create a histogram of text length distribution.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Plotly Figure or None if no text length data available.
    """
    if "text_len" not in df.columns or not df["text_len"].notna().any():
        return None

    fig = px.histogram(
        df,
        x="text_len",
        nbins=60,
        color="record_type",
        title="Distribution of Text Length (characters)",
    )
    return fig


def create_top_languages_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create a bar chart of top languages.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Plotly Figure or None if no language data available.
    """
    if "lang" not in df.columns or not df["lang"].notna().any():
        return None

    top_lang = df["lang"].value_counts().head(10).reset_index()
    top_lang.columns = ["lang", "count"]

    if top_lang.empty:
        return None

    fig = px.bar(top_lang, x="lang", y="count", title="Top Languages")
    return fig


def create_top_sources_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create a bar chart of top sources (client apps).

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Plotly Figure or None if no source data available.
    """
    if "source" not in df.columns or not df["source"].notna().any():
        return None

    top_src = df["source"].value_counts().head(10).reset_index()
    top_src.columns = ["source", "count"]

    if top_src.empty:
        return None

    fig = px.bar(top_src, x="source", y="count", title="Top Sources (Client Apps)")
    fig.update_layout(xaxis={"categoryorder": "total descending"})
    return fig


def create_hourly_activity_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create a bar chart showing activity by hour of day.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Plotly Figure or None if no date data available.
    """
    if "created_at" not in df.columns or not df["created_at"].notna().any():
        return None

    df_valid = df.dropna(subset=["created_at"]).copy()
    df_valid["hour"] = df_valid["created_at"].dt.hour
    hourly = df_valid["hour"].value_counts().sort_index().reset_index()
    hourly.columns = ["hour", "count"]

    fig = px.bar(hourly, x="hour", y="count", title="Activity by Hour of Day")
    fig.update_xaxes(tickmode="linear", tick0=0, dtick=1)
    return fig


def create_day_of_week_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create a bar chart showing activity by day of week.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Plotly Figure or None if no date data available.
    """
    if "created_at" not in df.columns or not df["created_at"].notna().any():
        return None

    df_valid = df.dropna(subset=["created_at"]).copy()
    df_valid["day_of_week"] = df_valid["created_at"].dt.day_name()

    day_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    dow_counts = df_valid["day_of_week"].value_counts()
    dow_df = pd.DataFrame({"day": day_order, "count": [dow_counts.get(d, 0) for d in day_order]})

    fig = px.bar(dow_df, x="day", y="count", title="Activity by Day of Week")
    return fig


def generate_all_charts(df: pd.DataFrame) -> Dict[str, Optional[go.Figure]]:
    """Generate all available charts for the data.

    Args:
        df: DataFrame with Twitter data.

    Returns:
        Dictionary mapping chart names to Plotly Figures.
    """
    return {
        "monthly_counts": create_monthly_counts_chart(df),
        "text_length": create_text_length_histogram(df),
        "top_languages": create_top_languages_chart(df),
        "top_sources": create_top_sources_chart(df),
        "hourly_activity": create_hourly_activity_chart(df),
        "day_of_week": create_day_of_week_chart(df),
    }


def save_charts_as_images(
    charts: Dict[str, Optional[go.Figure]],
    output_dir: str,
    format: str = "png",
) -> List[str]:
    """Save charts as image files.

    Args:
        charts: Dictionary of chart name to Figure.
        output_dir: Directory to save images.
        format: Image format (png, svg, pdf, etc.).

    Returns:
        List of saved file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    saved = []

    for name, fig in charts.items():
        if fig is not None:
            filepath = os.path.join(output_dir, f"{name}.{format}")
            fig.write_image(filepath)
            saved.append(filepath)

    return saved


def get_chart_html(fig: go.Figure, include_plotlyjs: bool = False) -> str:
    """Get HTML representation of a chart for embedding.

    Args:
        fig: Plotly Figure.
        include_plotlyjs: Whether to include Plotly.js library.

    Returns:
        HTML string.
    """
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn" if include_plotlyjs else False,
    )
