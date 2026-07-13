import streamlit as st
from pathlib import Path
import geopandas as gpd
import pandas as pd
import plotly.express as px
import pydeck as pdk

ROOT = Path(__file__).resolve().parent

GPKG_PATH = ROOT / "spatial_aggregates.gpkg"
PROVINCE_CSV_PATH = ROOT / "province_yearly.csv"
DISTRICT_CSV_PATH = ROOT / "district_yearly.csv"

def go_to(page_name: str) -> None:
    st.session_state["page"] = page_name
    
@st.cache_data
def load_geo_layer(layer_name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(GPKG_PATH, layer=layer_name)


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def render_dark_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #0B1220;
            color: #F5F7FA;
        }

        h1, h2, h3 {
            color: #F5F7FA;
        }

        h2 {
            color: #F2C94C;
        }

        h3 {
            color: #2F80ED;
        }

        .metric-card {
            background: #162032;
            border: 1px solid #2B3A55;
            padding: 20px;
            border-radius: 15px;
            min-height: 180px;
        }

        .card-button {
            text-align: left;
        }

        .footer {
            font-size: 12px;
            color: #A9B4C5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def spatial_explorer_page() -> None:
    st.title("🗺 Spatial Explorer")
    st.write(
        """
        Explore spatial patterns of economic estimates aggregated from grid cells
        to Sri Lankan provinces and districts.
        """
    )
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.selectbox("Select Year", list(range(2012, 2023)), index=10)
    with col2:
        level = st.selectbox("Administrative Level", ["provinces", "districts"])
    with col3:
        variable = st.selectbox("Indicator", ["GDP_per_capita", "Population", "GDP"])

    layer_name = f"{level}_{year}"
    gdf = load_geo_layer(layer_name)
    gdf = gdf.to_crs(4326)
    gdf["longitude"] = gdf.geometry.centroid.x
    gdf["latitude"] = gdf.geometry.centroid.y

    st.subheader(f"{variable.replace('_', ' ')} ({year})")
    layer = pdk.Layer(
        "GeoJsonLayer",
        data=gdf,
        opacity=0.7,
        stroked=True,
        filled=True,
        get_fill_color="[47, 128, 237, 160]",
        get_line_color=[200, 200, 200],
    )

    view = pdk.ViewState(latitude=7.8, longitude=80.7, zoom=7)
    deck = pdk.Deck(layers=[layer], initial_view_state=view, map_style="dark")
    st.pydeck_chart(deck, height=650)

    st.divider()
    st.subheader("Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Regions", len(gdf))
    c2.metric("Average", round(gdf[variable].mean(), 2))
    c3.metric("Maximum", round(gdf[variable].max(), 2))

    st.divider()
    st.subheader("Regional Ranking")

    label_column = "name_1" if level == "districts" else "province"
    table = (
        gdf[[label_column, variable]]
        .sort_values(variable, ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(table, use_container_width=True)


def placeholder_page(title: str, description: str) -> None:
    st.title(title)
    st.info(description)


def validation_laboratory_page() -> None:
    st.title("📈 Validation Laboratory")
    st.write(
        """
        Compare aggregated grid estimates with official provincial and district
        statistics using the provided validation datasets.
        """
    )
    st.divider()

    level = st.radio("Validation level", ["Province", "District"], horizontal=True)
    csv_path = PROVINCE_CSV_PATH if level == "Province" else DISTRICT_CSV_PATH
    df = load_csv(csv_path)
    label_column = "province" if level == "Province" else "name_1"

    year_options = sorted(df["year"].unique())
    year = st.selectbox("Select Year", year_options, index=len(year_options) - 1)
    filtered = df[df["year"] == year]

    indicator = st.selectbox("Indicator", ["GDP", "Population", "GDP_per_capita"])
    display_title = f"{level} {indicator} ({year})"

    st.subheader(display_title)
    fig = px.bar(
        filtered,
        x=label_column,
        y=indicator,
        title=display_title,
        labels={label_column: level, indicator: indicator.replace("_", " ")},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader(f"{level} Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Total {level}s", len(filtered))
    c2.metric("Average", round(filtered[indicator].mean(), 2))
    c3.metric("Max", round(filtered[indicator].max(), 2))

    st.divider()
    st.subheader(f"{level} Table")
    st.dataframe(filtered.sort_values(indicator, ascending=False), use_container_width=True)


def home_page() -> None:
    st.title("Spatial Economic Analysis Platform for Sri Lanka")
    st.write(
        """
        Interactive research platform for exploring grid-based economic estimates,
        administrative aggregation, and validation using Sri Lankan official data.
        """
    )
    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class='metric-card'>
            <h3>🗺 Spatial Explorer</h3>
            Interactive maps of GDP, GDP per capita, and population.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
    "Open Spatial Explorer",
    key="home_explorer",
    on_click=go_to,
    args=("Spatial Explorer",),
)

    with c2:
        st.markdown(
            """
            <div class='metric-card'>
            <h3>📈 Validation Laboratory</h3>
            Compare grid estimates with official provincial statistics.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open Validation Laboratory", key="home_validation"):
  

    with c3:
        st.markdown(
            """
            <div class='metric-card'>
            <h3>📊 Temporal Analysis</h3>
            Explore changes in economic patterns from 2012–2022.
            </div>
            """,
            unsafe_allow_html=True,
       

    st.divider()
    st.subheader("Project Overview")
    st.write(
        """
        This platform supports interactive mapping, administrative aggregation,
        validation against official statistics, and temporal trend analysis.
        """
    )

    st.divider()
    st.header("Data and Academic Context")
    st.write(
        """
        Developed by **Niromi Rajapaksha**, Graduate School of International
        Development (GSID), Nagoya University.

        Official provincial GDP statistics are sourced from the Central Bank of
        Sri Lanka.
        """
    )
    st.divider()
    st.markdown(
        """
        <div class='footer'>
        Sri Lanka Spatial Economic Analysis Platform | GSID, Nagoya University
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Sri Lanka Spatial Economic Analysis Platform",
        page_icon="🌏",
        layout="wide",
    )
    render_dark_theme()


    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
    "Navigate",
    ["Home", "Spatial Explorer", "Validation Laboratory", "Temporal Analysis"],
    key="page",
)
        ],
        index=["Home", "Spatial Explorer", "Validation Laboratory", "Temporal Analysis", "Methodology"].index(
            st.session_state.page
        ),
        key="page",
    )

    if page == "Home":
        home_page()
    elif page == "Spatial Explorer":
        spatial_explorer_page()
    elif page == "Validation Laboratory":
        validation_laboratory_page()
    elif page == "Temporal Analysis":
        placeholder_page(
            "📊 Temporal Analysis",
            "Examine temporal trends in Sri Lankan regional economic data.",
        )
    else:
        placeholder_page(
            "ℹ Methodology",
            "Describe the data sources, model assumptions, and analytical methods.",
        )


if __name__ == "__main__":
    main()
