"""Interactive Plotly charts for the MMM tool."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


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
    return (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_categorical_dtype(series)
        or (pd.api.types.is_numeric_dtype(series) and series.nunique() <= 15)
    )


def make_input_target_charts(df: pd.DataFrame, input_cols: list, target_col: str):
    """Return [(col_name, fig), ...] for each input column."""
    if df is None or not input_cols or not target_col or target_col not in df.columns:
        return []

    charts = []
    for col in input_cols:
        if col not in df.columns:
            continue
        try:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                fig = _line_chart(df, col, target_col)
            elif _is_categorical(df[col]):
                fig = _bar_chart(df, col, target_col)
            else:
                fig = _scatter_chart(df, col, target_col)

            fig.update_layout(**_LAYOUT)
            charts.append((col, fig))
        except Exception:
            continue

    return charts


def _line_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    plot_df = df[[x_col, y_col]].dropna().sort_values(x_col)
    fig = px.line(
        plot_df,
        x=x_col,
        y=y_col,
        title=f"{x_col}  ↔  {y_col}",
        markers=True,
    )
    fig.update_traces(
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x}}<br>"
            f"<b>{y_col}</b>: %{{y:,.2f}}<extra></extra>"
        )
    )
    return fig


def _bar_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
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
        text=y_col,
        color=x_col,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x}}<br>"
            f"<b>{y_col}</b>: %{{y:,.2f}}<extra></extra>"
        ),
    )
    fig.update_layout(showlegend=False)
    return fig


def _scatter_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    plot_df = df[[x_col, y_col]].dropna()
    if len(plot_df) < 2:
        # Not enough points for trendline
        fig = px.scatter(plot_df, x=x_col, y=y_col, title=f"{x_col}  ↔  {y_col}")
    else:
        try:
            fig = px.scatter(
                plot_df,
                x=x_col,
                y=y_col,
                title=f"{x_col}  ↔  {y_col}",
                trendline="ols",
                trendline_color_override="crimson",
            )
        except Exception:
            fig = px.scatter(plot_df, x=x_col, y=y_col, title=f"{x_col}  ↔  {y_col}")

    fig.update_traces(
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x:,.2f}}<br>"
            f"<b>{y_col}</b>: %{{y:,.2f}}<extra></extra>"
        ),
        selector=dict(mode="markers"),
    )
    return fig
