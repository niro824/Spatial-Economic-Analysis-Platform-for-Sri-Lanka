"""Sri Lanka Spatial Economic Analysis Platform.

Deployment-ready single-file Streamlit application.  It works with the files
already committed in the repository root and can optionally use official
administrative boundary polygons when they are added later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st


st.set_page_config(
    page_title="Sri Lanka Spatial Economic Analysis Platform",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded",
)


# The app first looks in the repository root, then in data/processed.
ROOT = Path(__file__).resolve().parent
SEARCH_DIRECTORIES = (ROOT, ROOT / "data", ROOT / "data" / "processed")


def find_file(filename: str) -> Path | None:
    """Return the first matching file in a supported project location."""
    for directory in SEARCH_DIRECTORIES:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def find_official_gdp_file() -> Path | None:
    """Find the Central Bank provincial-GDP CSV without hard-coding its long name."""
    excluded = {"province_yearly.csv", "district_yearly.csv"}
    for directory in SEARCH_DIRECTORIES:
        if not directory.exists():
            continue
        for candidate in directory.glob("*.csv"):
            name = candidate.name.lower()
            if candidate.name.lower() not in excluded and "gdp" in name and "province" in name:
                return candidate
    return None


GPKG_PATH = find_file("spatial_aggregates.gpkg")
PROVINCE_CSV_PATH = find_file("province_yearly.csv")
DISTRICT_CSV_PATH = find_file("district_yearly.csv")

# Optional: official polygons.  Expected layers are named provinces and districts.
BOUNDARY_GPKG_PATH = find_file("sri_lanka_admin_boundaries.gpkg")
OFFICIAL_GDP_PATH = find_official_gdp_file()


def clean_name(value: object) -> str:
    """Create a robust join key for province and district names."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find a column case-insensitively, allowing simple spelling variations."""
    normalised = {clean_name(column): column for column in frame.columns}
    for candidate in candidates:
        found = normalised.get(clean_name(candidate))
        if found:
            return found
    return None


@st.cache_data(show_spinner=False)
def load_geo_layer(path_string: str, layer_name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path_string, layer=layer_name)


@st.cache_data(show_spinner=False)
def load_table(path_string: str) -> pd.DataFrame:
    return pd.read_csv(path_string)


@st.cache_data(show_spinner=False)
def load_official_gdp(path_string: str) -> pd.DataFrame:
    """Turn a wide provincial GDP CSV (one column per year) into a tidy table."""
    raw = pd.read_csv(path_string)
    province_column = find_column(raw, ["province", "provinces"])
    if province_column is None:
        raise ValueError("The official GDP CSV needs a Province column.")

    year_columns = [
        column for column in raw.columns if re.search(r"\b20\d{2}\b", str(column))
    ]
    if not year_columns:
        raise ValueError("No year columns such as 2012 or 2022 were found in the official GDP CSV.")

    tidy = raw.melt(
        id_vars=[province_column],
        value_vars=year_columns,
        var_name="year_label",
        value_name="official_gdp",
    )
    tidy["year"] = tidy["year_label"].astype(str).str.extract(r"(20\d{2})")[0]
    tidy["year"] = pd.to_numeric(tidy["year"], errors="coerce")
    tidy["official_gdp"] = pd.to_numeric(
        tidy["official_gdp"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    tidy = tidy.rename(columns={province_column: "province"})
    tidy["province_key"] = tidy["province"].map(clean_name)

    return tidy[["province", "province_key", "year", "official_gdp"]].dropna()


def load_validation_data() -> pd.DataFrame:
    """Join grid-derived provincial GDP with official provincial GDP."""
    if PROVINCE_CSV_PATH is None:
        raise FileNotFoundError("province_yearly.csv is missing.")
    if OFFICIAL_GDP_PATH is None:
        raise FileNotFoundError("An official provincial GDP CSV is missing.")

    estimates = load_table(str(PROVINCE_CSV_PATH)).copy()
    province_column = find_column(estimates, ["province"])
    year_column = find_column(estimates, ["year"])
    gdp_column = find_column(estimates, ["GDP", "estimated_gdp"])

    if not all([province_column, year_column, gdp_column]):
        raise ValueError(
            "province_yearly.csv must contain province, year, and GDP columns."
        )

    estimates = estimates.rename(
        columns={
            province_column: "province",
            year_column: "year",
            gdp_column: "estimated_gdp",
        }
    )
    estimates["year"] = pd.to_numeric(estimates["year"], errors="coerce")
    estimates["estimated_gdp"] = pd.to_numeric(estimates["estimated_gdp"], errors="coerce")
    estimates["province_key"] = estimates["province"].map(clean_name)

    official = load_official_gdp(str(OFFICIAL_GDP_PATH))
    merged = estimates.merge(
        official[["province_key", "year", "official_gdp"]],
        on=["province_key", "year"],
        how="inner",
    )

    return merged.dropna(subset=["estimated_gdp", "official_gdp"]).copy()


def add_validation_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate comparable within-year spatial measures.

    The estimates use 2021 PPP terminology while the official series uses
    current LKR.  Shares and ranks are therefore used for validation instead
    of invalid raw-currency residuals.
    """
    data = frame.copy()
    data["estimated_share"] = data["estimated_gdp"] / data["estimated_gdp"].sum() * 100
    data["official_share"] = data["official_gdp"] / data["official_gdp"].sum() * 100
    data["share_residual_pp"] = data["estimated_share"] - data["official_share"]
    data["estimated_rank"] = data["estimated_share"].rank(ascending=False, method="min").astype(int)
    data["official_rank"] = data["official_share"].rank(ascending=False, method="min").astype(int)
    data["rank_difference"] = data["estimated_rank"] - data["official_rank"]
    return data


def validation_summary(data: pd.DataFrame) -> dict[str, float]:
    pearson = data["estimated_share"].corr(data["official_share"], method="pearson")
    spearman = data["estimated_share"].corr(data["official_share"], method="spearman")
    share_rmse = float(np.sqrt(np.mean(data["share_residual_pp"] ** 2)))
    rank_match = float((data["rank_difference"] == 0).mean() * 100)
    return {
        "pearson": pearson,
        "spearman": spearman,
        "share_rmse": share_rmse,
        "rank_match": rank_match,
    }


def validation_explainer(data: pd.DataFrame, metrics: dict[str, float], year: int) -> str:
    r = metrics["pearson"]
    strength = "strong" if r >= 0.80 else "moderate" if r >= 0.50 else "weak"
    highest_over = data.loc[data["share_residual_pp"].idxmax()]
    highest_under = data.loc[data["share_residual_pp"].idxmin()]

    return (
        f"In {year}, the grid-derived and official provincial GDP distributions show a "
        f"**{strength} positive spatial association** (Pearson r = {r:.2f}; "
        f"Spearman ρ = {metrics['spearman']:.2f}). The model assigns the largest extra "
        f"share to **{highest_over['province']}** (+{highest_over['share_residual_pp']:.2f} "
        f"percentage points) and the smallest share relative to the official distribution "
        f"to **{highest_under['province']}** ({highest_under['share_residual_pp']:.2f} "
        f"percentage points). This is a comparison of spatial distribution and ranking, "
        f"not raw monetary levels."
    )


def hex_to_rgb(value: str) -> list[int]:
    value = value.lstrip("#")
    return [int(value[index:index + 2], 16) for index in (0, 2, 4)]


def colour_scale(value: float, low: float, high: float, colours: list[str]) -> list[int]:
    if pd.isna(value):
        return [65, 75, 90]

    fraction = 0.5 if high == low else min(1, max(0, (value - low) / (high - low)))
    position = fraction * (len(colours) - 1)
    left = int(position)
    right = min(left + 1, len(colours) - 1)
    blend = position - left
    start, end = hex_to_rgb(colours[left]), hex_to_rgb(colours[right])
    return [round(start[i] + (end[i] - start[i]) * blend) for i in range(3)]


PALETTES = {
    "GDP": ["#21113F", "#0F5D73", "#F4D35E"],
    "GDP_per_capita": ["#071E3D", "#146C94", "#51E5FF"],
    "Population": ["#0B3D2E", "#3D8B5F", "#F4D35E"],
    "share": ["#21113F", "#0F5D73", "#F4D35E"],
    "residual": ["#1D4E89", "#E9EEF5", "#9B174D"],
}


def legend(title: str, low: float, high: float, colours: list[str], midpoint: str | None = None) -> None:
    gradient = ", ".join(colours)
    middle = f"<span>{midpoint}</span>" if midpoint else ""
    st.markdown(
        f"""
        <div class="legend-box">
          <div><b>{title}</b></div>
          <div class="legend-gradient" style="background: linear-gradient(90deg, {gradient});"></div>
          <div class="legend-labels"><span>{low:,.2f}</span>{middle}<span>{high:,.2f}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def region_column(frame: pd.DataFrame, level: str) -> str:
    candidates = ["province", "name_1"] if level == "provinces" else ["name_1", "district", "district_name"]
    column = find_column(frame, candidates)
    if column is None:
        raise ValueError(f"No region-name column was found for {level}.")
    return column


def map_geometry(level: str, year: int) -> tuple[gpd.GeoDataFrame, str]:
    """Prefer optional official boundaries; otherwise use the assigned-grid footprint."""
    if GPKG_PATH is None:
        raise FileNotFoundError("spatial_aggregates.gpkg is missing.")

    values = load_geo_layer(str(GPKG_PATH), f"{level}_{year}")
    source_label = "assigned grid coverage"

    if BOUNDARY_GPKG_PATH is not None:
        try:
            boundaries = load_geo_layer(str(BOUNDARY_GPKG_PATH), level)
            boundary_region = region_column(boundaries, level)
            values_region = region_column(values, level)
            boundaries = boundaries.copy()
            values = values.drop(columns="geometry").copy()
            boundaries["join_key"] = boundaries[boundary_region].map(clean_name)
            values["join_key"] = values[values_region].map(clean_name)
            values = values.drop(columns=[values_region], errors="ignore")
            merged = boundaries.merge(values, on="join_key", how="left")
            source_label = "official administrative boundaries"
            return merged, source_label
        except Exception:
            # The app remains usable even if optional boundaries have different layer names.
            pass

    return values, source_label


def draw_map(
    frame: gpd.GeoDataFrame,
    value_column: str,
    label: str,
    palette: list[str],
    geography: str,
    diverging: bool = False,
) -> None:
    data = frame.copy().to_crs(epsg=4326)
    name_column = region_column(data, geography)
    data["region_name"] = data[name_column].astype(str)
    data["map_value"] = pd.to_numeric(data[value_column], errors="coerce")

    if diverging:
        limit = float(data["map_value"].abs().max())
        low, high = -limit, limit
        midpoint = "0"
    else:
        low, high = float(data["map_value"].min()), float(data["map_value"].max())
        midpoint = None

    data["fill_color"] = data["map_value"].map(
        lambda value: colour_scale(value, low, high, palette)
    )
    data["value_display"] = data["map_value"].map(
        lambda value: "No data" if pd.isna(value) else f"{value:,.2f}"
    )

    centroids = data.geometry.centroid
    view_state = pdk.ViewState(
        latitude=float(centroids.y.mean()),
        longitude=float(centroids.x.mean()),
        zoom=6.6,
    )

    geojson = json.loads(data.to_json())
    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        opacity=0.84,
        filled=True,
        stroked=True,
        pickable=True,
        get_fill_color="properties.fill_color",
        get_line_color=[210, 220, 235],
        line_width_min_pixels=1,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={
            "html": f"<b>{{region_name}}</b><br/>{label}: {{value_display}}",
            "style": {"backgroundColor": "#162032", "color": "#F5F7FA"},
        },
    )
    st.pydeck_chart(deck, height=600)
    legend(label, low, high, palette, midpoint)


def spatial_explorer_page() -> None:
    st.title("🗺 Spatial Explorer")
    st.caption("Map-first exploration of grid-based economic estimates.")

    c1, c2, c3 = st.columns(3)
    with c1:
        year = st.selectbox("Year", list(range(2012, 2023)), index=10)
    with c2:
        level_label = st.selectbox("Administrative level", ["Provinces", "Districts"])
    with c3:
        indicator_label = st.selectbox("Indicator", ["GDP per capita", "GDP", "Population"])

    level = "provinces" if level_label == "Provinces" else "districts"
    indicator = {
        "GDP per capita": "GDP_per_capita",
        "GDP": "GDP",
        "Population": "Population",
    }[indicator_label]

    try:
        mapped, geometry_note = map_geometry(level, year)
    except Exception as error:
        st.error("The selected spatial layer could not be loaded.")
        st.code(str(error))
        return

    if indicator not in mapped.columns:
        st.error(f"The {level}_{year} layer does not contain a {indicator} column.")
        return

    if level == "districts" and "province" in mapped.columns:
        options = ["All provinces"] + sorted(mapped["province"].dropna().unique().tolist())
        selected_province = st.selectbox("Filter districts by province", options)
        if selected_province != "All provinces":
            mapped = mapped[mapped["province"] == selected_province]

    st.caption(f"Map geometry: {geometry_note}.")
    draw_map(mapped, indicator, indicator_label, PALETTES[indicator], level)

    values = pd.to_numeric(mapped[indicator], errors="coerce")
    m1, m2, m3 = st.columns(3)
    m1.metric("Regions", len(mapped))
    m2.metric("Average", f"{values.mean():,.2f}")
    m3.metric("Maximum", f"{values.max():,.2f}")

    name = region_column(mapped, level)
    ranking = mapped[[name, indicator]].rename(columns={name: "Region", indicator: indicator_label})
    ranking = ranking.sort_values(indicator_label, ascending=False)

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Regional ranking")
        st.dataframe(ranking, hide_index=True, use_container_width=True)
    with right:
        st.subheader("Distribution")
        st.bar_chart(ranking.set_index("Region"), use_container_width=True)


def scatter_plot(data: pd.DataFrame, year: int) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=data["official_share"],
            y=data["estimated_share"],
            mode="markers+text",
            text=data["province"],
            textposition="top center",
            marker={"size": 11, "color": "#F4D35E", "line": {"color": "#FFFFFF", "width": 1}},
            name="Province",
        )
    )

    maximum = float(max(data["official_share"].max(), data["estimated_share"].max())) * 1.08
    figure.add_trace(
        go.Scatter(
            x=[0, maximum],
            y=[0, maximum],
            mode="lines",
            line={"dash": "dash", "color": "#A9B4C5"},
            name="Equal share",
        )
    )

    if len(data) >= 2:
        slope, intercept = np.polyfit(data["official_share"], data["estimated_share"], 1)
        x_values = np.linspace(0, maximum, 100)
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=slope * x_values + intercept,
                mode="lines",
                line={"color": "#51E5FF"},
                name="Fitted relationship",
            )
        )

    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0B1220",
        plot_bgcolor="#162032",
        title=f"Provincial GDP share agreement — {year}",
        xaxis_title="Official provincial GDP share (%)",
        yaxis_title="Grid-derived GDP share (%)",
        height=520,
    )
    return figure


def validation_laboratory_page() -> None:
    st.title("📈 Validation Laboratory")
    st.caption("Testing whether grid-derived estimates reproduce known provincial economic patterns.")

    try:
        validation = load_validation_data()
    except Exception as error:
        st.error("The validation dataset is not ready.")
        st.code(str(error))
        st.info(
            "Keep province_yearly.csv and the Central Bank provincial-GDP CSV in the repository root "
            "or in data/processed."
        )
        return

    years = sorted(validation["year"].astype(int).unique().tolist())
    year = st.select_slider("Validation year", options=years, value=max(years))
    data = add_validation_metrics(validation[validation["year"] == year])
    metrics = validation_summary(data)

    st.info(
        """
        Why compare these datasets?

        The grid-based estimates and official GDP statistics are produced using
        different approaches and units. Therefore, this comparison does not test
        whether the absolute GDP values are identical.

        Instead, it evaluates whether both datasets identify similar economic
        patterns across Sri Lankan provinces.

        The comparison focuses on:

        • Which provinces contribute the largest economic shares
        • Whether provincial rankings are similar
        • Whether spatial patterns agree
        """
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Pearson r", f"{metrics['pearson']:.2f}")
    m2.metric("Spearman ρ", f"{metrics['spearman']:.2f}")
    m3.metric("Share RMSE", f"{metrics['share_rmse']:.2f} pp")
    m4.metric("Exact rank matches", f"{metrics['rank_match']:.0f}%")
    m1.metric("Pearson r", f"{metrics['pearson']:.2f}")
    m2.metric("Spearman ρ", f"{metrics['spearman']:.2f}")
    m3.metric("Share RMSE", f"{metrics['share_rmse']:.2f} pp")
    m4.metric("Exact rank matches", f"{metrics['rank_match']:.0f}%")

    st.markdown(validation_explainer(data, metrics, year))
    st.divider()

    try:
        provinces, geometry_note = map_geometry("provinces", year)
        province_name = region_column(provinces, "provinces")
        provinces["province_key"] = provinces[province_name].map(clean_name)
        mapped = provinces.merge(
            data[
                [
                    "province_key",
                    "estimated_share",
                    "official_share",
                    "share_residual_pp",
                ]
            ],
            on="province_key",
            how="left",
        )

        map_tabs = st.tabs(["Grid-derived share", "Official share", "Spatial disagreement"])
        with map_tabs[0]:
            st.caption(f"Map geometry: {geometry_note}.")
            draw_map(mapped, "estimated_share", "Grid-derived GDP share (%)", PALETTES["share"], "provinces")
        with map_tabs[1]:
            draw_map(mapped, "official_share", "Official GDP share (%)", PALETTES["share"], "provinces")
        with map_tabs[2]:
            draw_map(mapped, "share_residual_pp", "Difference in GDP share (percentage points)", PALETTES["residual"], "provinces", diverging=True)
    except Exception as error:
        st.warning("The validation statistics are available, but the validation map could not be drawn.")
        st.code(str(error))

    st.divider()
    st.plotly_chart(scatter_plot(data, year), use_container_width=True)

    ranking = data[
        [
            "province",
            "estimated_share",
            "official_share",
            "estimated_rank",
            "official_rank",
            "rank_difference",
            "share_residual_pp",
        ]
    ].sort_values("official_rank")

    ranking = ranking.rename(
        columns={
            "province": "Province",
            "estimated_share": "Grid GDP share (%)",
            "official_share": "Official GDP share (%)",
            "estimated_rank": "Grid rank",
            "official_rank": "Official rank",
            "rank_difference": "Rank difference",
            "share_residual_pp": "Difference (pp)",
        }
    )
    st.subheader("Province ranking comparison")
    st.dataframe(ranking, hide_index=True, use_container_width=True)


def temporal_analysis_page() -> None:
    st.title("📊 Temporal Analysis")
    st.caption("Track economic change through time and compare provinces.")

    if PROVINCE_CSV_PATH is None:
        st.error("province_yearly.csv is missing.")
        return

    province_data = load_table(str(PROVINCE_CSV_PATH)).copy()
    province_column = find_column(province_data, ["province"])
    year_column = find_column(province_data, ["year"])
    if province_column is None or year_column is None:
        st.error("province_yearly.csv needs province and year columns.")
        return

    province_data = province_data.rename(columns={province_column: "province", year_column: "year"})
    indicators = [column for column in ["GDP", "GDP_per_capita", "Population"] if column in province_data.columns]
    indicator = st.selectbox("Indicator", indicators)
    options = sorted(province_data["province"].dropna().unique().tolist())
    selected = st.multiselect("Provinces", options, default=options[:3])

    data = province_data[province_data["province"].isin(selected)].copy()
    data[indicator] = pd.to_numeric(data[indicator], errors="coerce")

    figure = go.Figure()
    for province in selected:
        subset = data[data["province"] == province].sort_values("year")
        figure.add_trace(
            go.Scatter(
                x=subset["year"],
                y=subset[indicator],
                mode="lines+markers",
                name=province,
            )
        )
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0B1220",
        plot_bgcolor="#162032",
        xaxis_title="Year",
        yaxis_title=indicator.replace("_", " "),
        height=560,
    )
    st.plotly_chart(figure, use_container_width=True)


def methodology_page() -> None:
    st.title("ℹ Methodology and Data Notes")

    st.subheader("Spatial units")
    st.write(
        "The original dataset contains 120 model-derived economic grid cells. "
        "Cells are aggregated to districts and provinces for reporting and comparison."
    )

    st.subheader("Aggregation")
    st.latex(r"GDP_{region} = \sum GDP_{cell}")
    st.latex(r"Population_{region} = \sum Population_{cell}")
    st.latex(r"GDPpc_{region} = \frac{\sum GDP_{cell}}{\sum Population_{cell}}")

    st.subheader("Validation")
    st.write(
        "Because the grid GDP field is labelled 2021 PPP and the Central Bank series is in current-price LKR, "
        "the app validates spatial distribution using provincial GDP shares, ranks, Pearson correlation, "
        "Spearman correlation, and share-based RMSE. Raw monetary residuals are intentionally not reported."
    )

    st.subheader("Boundary geometry")
    st.write(
        "Without an official boundary file, maps show the dissolved footprint of grid cells assigned to each region. "
        "For publication-quality administrative maps, add sri_lanka_admin_boundaries.gpkg with provinces and districts layers."
    )

    st.subheader("Acknowledgement")
    st.write(
        "Developed by Niromi Rajapaksha, GSID, Nagoya University. Academic guidance and economic grid data: "
        "Professor Carlos Mendez. Provincial GDP: Central Bank of Sri Lanka."
    )


def render_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp { background-color: #0B1220; color: #F5F7FA; }
        [data-testid="stSidebar"] { background-color: #101B2E; }
        .metric-card {
            background: #162032;
            border: 1px solid #2B3A55;
            border-radius: 16px;
            padding: 20px;
            min-height: 155px;
        }
        .legend-box {
            background: #162032;
            border: 1px solid #2B3A55;
            border-radius: 10px;
            margin: 8px 0 24px 0;
            padding: 10px 14px;
        }
        .legend-gradient { height: 13px; border-radius: 8px; margin-top: 8px; }
        .legend-labels { display: flex; justify-content: space-between; color: #C7D2E1; font-size: 0.85rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
def home_page() -> None:

    st.title("Sri Lanka Spatial Economic Analysis Platform")

    st.markdown(
        """
        ## Understanding Sri Lanka's Economic Geography Through Spatial Data
        This platform explores how economic activity is distributed across Sri Lanka.
        It combines spatial economic estimates derived from grid data with official
        provincial GDP statistics to examine regional patterns and disparities.
        """

    )

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            <div class="metric-card">
            <h3>🗺 Spatial Explorer</h3>

            Explore spatial patterns of:
            <br>
            • GDP
            <br>
            • GDP per capita
            <br>
            • Population

            across provinces and districts.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
            <div class="metric-card">
            <h3>📈 Validation Laboratory</h3>

            Compare grid-derived economic estimates
            with official Provincial GDP statistics
            from the Central Bank of Sri Lanka.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
            <div class="metric-card">
            <h3>📊 Temporal Analysis</h3>

            Examine regional economic changes
            between 2012 and 2022.
            </div>
            """,
            unsafe_allow_html=True,
        )


    st.divider()

    st.subheader("Research Framework")

    st.write(
        """
        The analytical framework follows four stages:

        **1. Spatial economic estimation**

        Grid-based economic estimates are processed at fine spatial
        resolution.

        **2. Regional aggregation**

        Grid cells are aggregated into Sri Lankan provinces and districts.

        **3. Validation**

        Estimated regional economic patterns are compared with official
        Provincial GDP statistics published by the Central Bank of Sri Lanka.

        **4. Spatial inequality analysis**

        The validated dataset supports analysis of regional economic
        disparities.
        """
    )


    st.divider()

    st.subheader("Validation Approach")

    st.info(
        """
        The validation compares spatial distribution rather than absolute
        monetary values.

        The analysis evaluates:

        • Provincial GDP shares

        • Regional ranking consistency

        • Pearson correlation

        • Spearman rank correlation

        • Spatial agreement between datasets

        This approach avoids direct comparison between different GDP
        measurement frameworks.
        """
    )


    st.divider()

    st.markdown(
        """
        Developed by **Niromi Rajapaksha** at the Graduate School of International
        Development, Nagoya University.

        This platform uses gridded GDP estimates from the University of Chicago's
        Local GDP Estimates project and official Provincial GDP statistics from the
        Central Bank of Sri Lanka to explore regional economic patterns.

        Research guidance and academic support from **Professor Carlos Mendez**.
        """
    )
def main() -> None:
    render_theme()

    pages = [
        "Home",
        "Spatial Explorer",
        "Validation Laboratory",
        "Temporal Analysis",
    ]
    if "page" not in st.session_state:
        st.session_state["page"] = "Home"

    st.sidebar.title("Sri Lanka Spatial Analysis")
    st.sidebar.caption("Research platform for spatial economic exploration and validation.")
    page = st.sidebar.radio("Navigate", pages, key="page")

    st.sidebar.divider()
    st.sidebar.caption("Developed by Niromi Rajapaksha | GSID, Nagoya University")
    st.sidebar.caption("Academic guidance: Professor Carlos Mendez")

    if page == "Home":
        home_page()
    elif page == "Spatial Explorer":
        spatial_explorer_page()
    elif page == "Validation Laboratory":
        validation_laboratory_page()
    elif page == "Temporal Analysis":
        temporal_analysis_page()



if __name__ == "__main__":
    main()

