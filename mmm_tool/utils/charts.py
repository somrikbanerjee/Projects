"""Interactive Plotly charts for the MMM tool.

This module generates Plotly figures that are rendered in the Tab 1 "Input ↔
Target Charts" section.  The charts help the user visually explore the
bivariate relationship between each input column and the target (KPI) column
before applying any transformations.

Chart type selection
--------------------
The chart type is chosen automatically based on the dtype of the input column:

  - Datetime    → Line chart (time-series view)
  - Categorical / low-cardinality numeric (≤ 15 unique values)
                → Bar chart (mean KPI per category, sorted descending)
  - Continuous numeric
                → Scatter plot with optional OLS trendline

All figures share the ``_LAYOUT`` base style (white background, subtle grid
lines, 400 px height) to give a consistent look and feel.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ─────────────────────────── SHARED LAYOUT ────────────────────────────────────
# Applied to every chart via ``fig.update_layout(**_LAYOUT)``.
# Using a shared dict ensures visual consistency across all chart types.
_LAYOUT = dict(
    height=400,
    margin=dict(l=50, r=30, t=55, b=50),
    hovermode="closest",
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(size=12),
    xaxis=dict(showgrid=True, gridcolor="#e8e8e8", zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="#e8e8e8", zeroline=False),
)


def _is_categorical(series: pd.Series) -> bool:
    """Return True if the series should be treated as categorical for charting.

    A series is considered categorical (and will get a bar chart) if:
    - Its dtype is object or the pandas Categorical type, OR
    - It is numeric but has ≤ 15 distinct values (i.e. it encodes a small set
      of discrete categories such as region codes or year numbers).

    Parameters
    ----------
    series : pd.Series
        Column to classify.

    Returns
    -------
    bool
        True → use a bar chart; False → use a scatter chart.
    """
    return (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_categorical_dtype(series)
        or (pd.api.types.is_numeric_dtype(series) and series.nunique() <= 15)
    )


def make_input_target_charts(df: pd.DataFrame, input_cols: list, target_col: str):
    """Build one Plotly figure per input column showing its relationship to the target.

    The function auto-selects the best chart type per column (see module
    docstring).  Columns not found in df and any that raise an exception are
    silently skipped so that partial success is always returned.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with both input columns and the target column.
    input_cols : list[str]
        Column names to plot on the x-axis (one chart per column).
    target_col : str
        Column name to use as the y-axis (the KPI / dependent variable).

    Returns
    -------
    list[tuple[str, go.Figure]]
        List of (column_name, figure) pairs in the same order as input_cols.
        Returns an empty list if df is None, input_cols is empty, or
        target_col is not found in df.
    """
    if df is None or not input_cols or not target_col or target_col not in df.columns:
        return []

    charts = []
    for col in input_cols:
        if col not in df.columns:
            continue
        try:
            # Choose chart type based on the column's dtype
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                fig = _line_chart(df, col, target_col)
            elif _is_categorical(df[col]):
                fig = _bar_chart(df, col, target_col)
            else:
                fig = _scatter_chart(df, col, target_col)

            # Apply the shared layout to every chart
            fig.update_layout(**_LAYOUT)
            charts.append((col, fig))
        except Exception:
            # Skip any column that causes a rendering failure
            continue

    return charts


def _line_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Create a time-series line chart: x = datetime column, y = target.

    Drops NaN rows, sorts by x, and adds markers at each data point.
    The hover tooltip shows the exact x value and a formatted y value.

    Parameters
    ----------
    df : pd.DataFrame
        Source DataFrame.
    x_col : str
        Datetime column for the x-axis.
    y_col : str
        Numeric target column for the y-axis.

    Returns
    -------
    go.Figure
    """
    # Drop NaN in either column and sort chronologically for a clean line
    plot_df = df[[x_col, y_col]].dropna().sort_values(x_col)
    fig = px.line(
        plot_df,
        x=x_col,
        y=y_col,
        title=f"{x_col}  ↔  {y_col}",
        markers=True,  # Show data-point markers on the line
    )
    fig.update_traces(
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x}}<br>"
            f"<b>{y_col}</b>: %{{y:,.2f}}<extra></extra>"
        )
    )
    return fig


def _bar_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Create a grouped bar chart showing mean target per category.

    Aggregates df by x_col (computing the mean of y_col), then sorts
    categories from highest to lowest mean to make patterns easy to spot.
    Each bar is coloured with Plotly's Pastel palette.

    Parameters
    ----------
    df : pd.DataFrame
        Source DataFrame.
    x_col : str
        Categorical column for the x-axis grouping.
    y_col : str
        Numeric target column whose mean is shown per category.

    Returns
    -------
    go.Figure
    """
    # Compute mean KPI per category and sort descending for easy ranking
    agg = (
        df.groupby(x_col)[y_col]
        .mean()
        .reset_index()
        .sort_values(y_col, ascending=False)
    )
    fig = px.bar(
        agg,
        x=x_col,
        y=y_col,
        title=f"{x_col}  ↔  {y_col}  (mean)",
        text=y_col,           # Show numeric value inside / above each bar
        color=x_col,          # Colour each bar by its category label
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",   # Format bar label as integer with commas
        textposition="outside",        # Place the label above the bar
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x}}<br>"
            f"<b>{y_col}</b>: %{{y:,.2f}}<extra></extra>"
        ),
    )
    fig.update_layout(showlegend=False)  # Legend is redundant since x-axis labels the bars
    return fig


def _scatter_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Create a scatter plot with an optional OLS (linear) trendline.

    Requires at least 2 non-NaN points for plotly's OLS trendline; falls back
    to a plain scatter if fewer points are available or if the OLS fit fails.

    Parameters
    ----------
    df : pd.DataFrame
        Source DataFrame.
    x_col : str
        Continuous numeric column for the x-axis.
    y_col : str
        Numeric target column for the y-axis.

    Returns
    -------
    go.Figure
    """
    plot_df = df[[x_col, y_col]].dropna()
    if len(plot_df) < 2:
        # Not enough points for a trendline — render plain scatter
        fig = px.scatter(plot_df, x=x_col, y=y_col, title=f"{x_col}  ↔  {y_col}")
    else:
        try:
            # OLS trendline requires statsmodels (via plotly's trendline engine)
            fig = px.scatter(
                plot_df,
                x=x_col,
                y=y_col,
                title=f"{x_col}  ↔  {y_col}",
                trendline="ols",
                trendline_color_override="crimson",  # Red trendline for contrast
            )
        except Exception:
            # statsmodels not installed, or OLS failed — fall back to plain scatter
            fig = px.scatter(plot_df, x=x_col, y=y_col, title=f"{x_col}  ↔  {y_col}")

    # Apply hover tooltip only to the scatter markers (not the trendline trace)
    fig.update_traces(
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x:,.2f}}<br>"
            f"<b>{y_col}</b>: %{{y:,.2f}}<extra></extra>"
        ),
        selector=dict(mode="markers"),
    )
    return fig
