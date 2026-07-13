import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st


st.set_page_config(
    page_title="Sri Lanka Spatial Economic Analysis Platform",
    page_icon="🌏",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
GPKG_PATH = ROOT / "spatial_aggregates.gpkg"


def go_to(page_name: str) -> None:
    st.session_state["page"] = page_name


@st.cache_data
def load_geo_layer(level: str, year: int) -> gpd.GeoDataFrame:
    layer_name = f"{level}_{year}"
    return gpd.read_file(GPKG_PATH, layer=layer_name)


def get_fill_color(value: float, low: float, high: float, variable: str) -> list[int]:
    palettes = {
        "GDP": ([31, 11, 73], [250, 204, 21]),
        "GDP_per_capita": ([8, 25, 69], [32, 218, 255]),
        "Population": ([12, 55, 39], [239, 208, 56]),
    }

    if pd.isna(value):
        return [85, 95, 110]

    start, end = palettes[variable]
    ratio = 0.5 if high == low else max(0, min(1, (value - low) / (high - low)))

    return [
        round(start[i] + (end[i] - start[i]) * ratio)
        for i in range(3)
    ]


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #0B1220;
            color: #F5F7FA;
        }

        [data-testid="stSidebar"] {
            background: #101B2E;
        }

        .metric-card {
            background: #162032;
            border: 1px solid #2B3A55;
            border-radius: 14px;
            padding: 20px;
            min-height: 160px;
        }

        .muted {
            color: #A9B4C5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def home_page() -> None:
    st.title("Spatial Economic Analysis Platform for Sri Lanka")

    st.markdown(
        "<p class='muted'>Grid-based economic estimates, administrative aggregation, "
        "and spatial exploration for Sri Lanka.</p>",
        unsafe_allow_html=True,
    )

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            <div class="metric-card">
            <h3>🗺 Spatial Explorer</h3>
            Interactive maps of GDP, GDP per capita, and population.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.button(
            "Open Spatial Explorer",
            key="home_explorer",
            on_click=go_to,
            args=("Spatial Explorer",),
            use_container_width=True,
        )

    with c2:
        st.markdown(
            """
            <div class="metric-card">
            <h3>📈 Validation Laboratory</h3>
            Provincial GDP comparison with Central Bank of Sri Lanka data.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
            <div class="metric-card">
            <h3>📊 Temporal Analysis</h3>
            Explore changes across 2012–2022.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    st.subheader("Academic context")
    st.markdown(
        """
        Developed by **Niromi Rajapaksha**  
        Graduate School of International Development (GSID), Nagoya University.

        Academic guidance and economic grid data: **Professor Carlos Mendez**  
        Official provincial GDP data: **Central Bank of Sri Lanka**
        """
    )


def spatial_explorer_page() -> None:
    st.title("🗺 Spatial Explorer")
    st.caption("Explore grid-based estimates aggregated to Sri Lankan provinces and districts.")

    c1, c2, c3 = st.columns(3)

    with c1:
        year = st.selectbox("Year", list(range(2012, 2023)), index=10)

    with c2:
        level_label = st.selectbox(
            "Administrative level",
            ["Provinces", "Districts"],
        )

    level = "provinces" if level_label == "Provinces" else "districts"

    try:
        gdf = load_geo_layer(level, year).to_crs(epsg=4326)
    except Exception as error:
        st.error(f"Could not load the layer: `{level}_{year}`")
        st.code(str(error))
        st.stop()

    available_variables = [
        column
        for column in ["GDP_per_capita", "GDP", "Population"]
        if column in gdf.columns
    ]

    with c3:
        variable = st.selectbox("Indicator", available_variables)

    region_column = "province" if level == "provinces" else "name_1"
    gdf["region_name"] = gdf[region_column].astype(str)

    values = pd.to_numeric(gdf[variable], errors="coerce")
    low = values.min()
    high = values.max()

    gdf["_fill_color"] = values.apply(
        lambda value: get_fill_color(value, low, high, variable)
    )
    gdf["value_display"] = values.map(lambda value: f"{value:,.2f}")

    centre = gdf.geometry.centroid
    view = pdk.ViewState(
        latitude=float(centre.y.mean()),
        longitude=float(centre.x.mean()),
        zoom=6.7,
    )

    geojson = json.loads(gdf.to_json())

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        opacity=0.82,
        stroked=True,
        filled=True,
        pickable=True,
        get_fill_color="properties._fill_color",
        get_line_color=[210, 220, 235],
        line_width_min_pixels=1,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={
            "html": (
                "<b>{region_name}</b><br/>"
                + variable.replace("_", " ")
                + ": {value_display}"
            ),
            "style": {
                "backgroundColor": "#162032",
                "color": "#F5F7FA",
            },
        },
    )

    st.pydeck_chart(deck, height=620)

    st.divider()

    m1, m2, m3 = st.columns(3)
    m1.metric("Regions", len(gdf))
    m2.metric("Average", f"{values.mean():,.2f}")
    m3.metric("Maximum", f"{values.max():,.2f}")

    st.subheader("Regional ranking")

    ranking = (
        gdf[["region_name", variable]]
        .sort_values(variable, ascending=False)
        .rename(columns={"region_name": "Region"})
    )

    st.dataframe(ranking, use_container_width=True, hide_index=True)


def main() -> None:
    apply_theme()

    if "page" not in st.session_state:
        st.session_state["page"] = "Home"

    st.sidebar.title("Sri Lanka Spatial Analysis")

    page = st.sidebar.radio(
        "Navigate",
        ["Home", "Spatial Explorer"],
        key="page",
    )

    if page == "Home":
        home_page()
    else:
        spatial_explorer_page()


if __name__ == "__main__":
    main()
