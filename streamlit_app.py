from pathlib import Path
import os
import re

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="NaijaDataScope | Economic Intelligence",
    page_icon="🇳🇬",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "data" / "warehouse" / "naijadatascope.duckdb"

COUNTRY_ORDER = ["Nigeria", "Ghana", "South Africa"]

INDICATOR_DESCRIPTIONS = {
    "NY.GDP.MKTP.CD": "The monetary value of a country's economic output, measured in current US dollars.",
    "NY.GDP.MKTP.KD.ZG": "Annual percentage growth in real GDP.",
    "FP.CPI.TOTL.ZG": "Annual percentage change in consumer prices.",
    "SP.POP.TOTL": "The total population of the country.",
    "SL.UEM.TOTL.ZS": "Unemployment as a percentage of the modelled total labour force.",
}

INDICATOR_FORMATS = {
    "NY.GDP.MKTP.CD": "currency",
    "NY.GDP.MKTP.KD.ZG": "percent",
    "FP.CPI.TOTL.ZG": "percent",
    "SP.POP.TOTL": "population",
    "SL.UEM.TOTL.ZS": "percent",
}


# ---------------------------------------------------------
# Data access
# ---------------------------------------------------------

@st.cache_data(ttl=300)
def load_data(db_path, db_mtime):
    """Load the warehouse tables into cached dataframes."""
    con = duckdb.connect(db_path, read_only=True)

    try:
        indicators = con.execute("""
            SELECT
                country_code,
                country_name,
                indicator_code,
                indicator_name,
                year,
                value,
                unit,
                source,
                source_url,
                fetched_at_utc
            FROM economic_indicators
            ORDER BY country_name, indicator_code, year
        """).df()

        catalog = con.execute("""
            SELECT indicator_code, indicator_name, description
            FROM indicator_catalog
            ORDER BY indicator_name
        """).df()

        logs = con.execute("""
            SELECT
                run_id,
                source,
                status,
                rows_loaded,
                started_at_utc,
                finished_at_utc,
                message
            FROM ingestion_log
            ORDER BY started_at_utc DESC
        """).df()

    finally:
        con.close()

    indicators["year"] = indicators["year"].astype(int)
    indicators["value"] = pd.to_numeric(
        indicators["value"], errors="coerce"
    )

    return indicators, catalog, logs


def format_value(value, indicator_code):
    """Format a numeric value according to its indicator."""
    if pd.isna(value):
        return "N/A"

    kind = INDICATOR_FORMATS.get(indicator_code, "number")

    if kind == "currency":
        absolute = abs(value)
        if absolute >= 1_000_000_000_000:
            return f"${value / 1_000_000_000_000:,.2f}T"
        if absolute >= 1_000_000_000:
            return f"${value / 1_000_000_000:,.2f}B"
        if absolute >= 1_000_000:
            return f"${value / 1_000_000:,.2f}M"
        return f"${value:,.0f}"

    if kind == "population":
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:,.2f}M"
        return f"{value:,.0f}"

    if kind == "percent":
        return f"{value:,.2f}%"

    return f"{value:,.2f}"


def get_latest_observations(data, indicator_code):
    """Return the latest available observation for each country."""
    subset = data[data["indicator_code"] == indicator_code].copy()

    if subset.empty:
        return subset

    subset = subset.sort_values("year")
    return subset.groupby("country_name", as_index=False).tail(1)


def get_gemini_key():
    """Read an optional API key without requiring one for the dashboard."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    try:
        key = key or st.secrets.get("GEMINI_API_KEY", "")
        key = key or st.secrets.get("GOOGLE_API_KEY", "")
    except Exception:
        pass

    return key.strip() if key else ""


# ---------------------------------------------------------
# Load data
# ---------------------------------------------------------

if not DB_PATH.exists():
    st.error(
        "The DuckDB warehouse was not found. "
        "Run `python -m src.ingestion.world_bank` from the project root first."
    )
    st.stop()

try:
    data, catalog, logs = load_data(
        str(DB_PATH),
        DB_PATH.stat().st_mtime,
    )
except Exception as exc:
    st.error(f"Could not load the analytical warehouse: {exc}")
    st.stop()

if data.empty:
    st.error("The warehouse contains no observations.")
    st.stop()


# ---------------------------------------------------------
# Header and sidebar
# ---------------------------------------------------------

st.title("🇳🇬 NaijaDataScope")
st.subheader("Nigeria Economic Intelligence Platform")
st.caption(
    "Explore the Numbers Behind Nigeria. "
    "Explore economic indicators, compare countries, and discover historical trends."
)

with st.sidebar:
    st.header("Explore the data")

    indicator_options = (
        catalog[["indicator_code", "indicator_name"]]
        .drop_duplicates()
        .sort_values("indicator_name")
    )

    selected_code = st.selectbox(
        "Economic indicator",
        indicator_options["indicator_code"].tolist(),
        format_func=lambda code: indicator_options.loc[
            indicator_options["indicator_code"] == code,
            "indicator_name",
        ].iloc[0],
    )

    selected_name = data.loc[
        data["indicator_code"] == selected_code,
        "indicator_name",
    ].iloc[0]

    available_countries = [
        country for country in COUNTRY_ORDER
        if country in data["country_name"].unique()
    ]

    selected_countries = st.multiselect(
        "Countries",
        options=available_countries,
        default=available_countries,
    )

    min_year = int(data["year"].min())
    max_year = int(data["year"].max())

    year_range = st.slider(
        "Historical period",
        min_value=min_year,
        max_value=max_year,
        value=(min_year, max_year),
        step=1,
    )

    st.divider()
    st.caption("Data provider: World Bank")
    st.caption(f"Warehouse observations: {len(data):,}")
    st.caption(f"Coverage: {min_year}–{max_year}")


filtered = data[
    (data["indicator_code"] == selected_code)
    & data["country_name"].isin(selected_countries)
    & data["year"].between(year_range[0], year_range[1])
].copy()

indicator_unit = (
    data.loc[data["indicator_code"] == selected_code, "unit"]
    .dropna()
    .iloc[0]
)

st.info(
    f"**Selected indicator:** {selected_name}  \n"
    f"**What it measures:** {INDICATOR_DESCRIPTIONS.get(selected_code, selected_name)}  \n"
    f"**Unit:** {indicator_unit}"
)


# ---------------------------------------------------------
# Tabs
# ---------------------------------------------------------

overview_tab, comparison_tab, explorer_tab, quality_tab, ai_tab = st.tabs(
    [
        "📊 Economic Overview",
        "🌍 Country Comparison",
        "🔎 Data Explorer",
        "🛡️ Data Quality",
        "🤖 Ask EBEN AI",
    ]
)


# ---------------------------------------------------------
# Tab 1: Overview
# ---------------------------------------------------------

with overview_tab:
    st.subheader("Latest available observations")

    latest = get_latest_observations(data, selected_code)
    latest = latest[
        latest["country_name"].isin(selected_countries)
    ]

    if latest.empty:
        st.warning("No observations are available for the selected countries.")
    else:
        columns = st.columns(max(1, len(latest)))

        for col, (_, row) in zip(columns, latest.iterrows()):
            with col:
                st.metric(
                    label=row["country_name"],
                    value=format_value(row["value"], selected_code),
                    delta=f"Reporting year: {int(row['year'])}",
                )

    st.subheader("Historical trend")

    if filtered.empty:
        st.warning("No observations match the selected filters.")
    else:
        fig = px.line(
            filtered,
            x="year",
            y="value",
            color="country_name",
            markers=True,
            title=f"{selected_name}: {year_range[0]}–{year_range[1]}",
            labels={
                "year": "Year",
                "value": indicator_unit,
                "country_name": "Country",
            },
            hover_data={
                "country_name": True,
                "year": True,
                "value": ":,.3f",
                "unit": True,
            },
        )
        fig.update_layout(
            hovermode="x unified",
            legend_title_text="Country",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Latest available values by country")

    if not latest.empty:
        latest_table = latest[
            ["country_name", "year", "value", "unit", "source"]
        ].sort_values("value", ascending=False)

        st.dataframe(
            latest_table,
            use_container_width=True,
            hide_index=True,
        )


# ---------------------------------------------------------
# Tab 2: Country comparison
# ---------------------------------------------------------

with comparison_tab:
    st.subheader("Compare economic performance")

    if filtered.empty:
        st.warning("Choose at least one country with available observations.")
    else:
        latest_filtered = get_latest_observations(filtered, selected_code)

        if not latest_filtered.empty:
            bar_fig = px.bar(
                latest_filtered,
                x="country_name",
                y="value",
                color="country_name",
                text="year",
                title=f"Latest available {selected_name}",
                labels={
                    "country_name": "Country",
                    "value": indicator_unit,
                    "year": "Reporting year",
                },
            )
            bar_fig.update_traces(
                texttemplate="%{text}",
                textposition="outside",
            )
            st.plotly_chart(bar_fig, use_container_width=True)

        st.markdown("#### Compare countries in the same reporting year")

        common_years = set.intersection(
            *[
                set(
                    filtered.loc[
                        filtered["country_name"] == country, "year"
                    ].tolist()
                )
                for country in selected_countries
                if country in filtered["country_name"].unique()
            ]
        ) if selected_countries else set()

        if common_years:
            common_year = st.selectbox(
                "Choose a year available for all selected countries",
                sorted(common_years),
                index=len(common_years) - 1,
                key="common_year",
            )

            common_data = filtered[filtered["year"] == common_year]

            st.dataframe(
                common_data[
                    ["country_name", "year", "value", "unit"]
                ].sort_values("value", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(
                "A common reporting year is unavailable for the current selection."
            )


# ---------------------------------------------------------
# Tab 3: Data Explorer
# ---------------------------------------------------------

with explorer_tab:
    st.subheader("Explore the underlying observations")

    all_indicator_codes = sorted(data["indicator_code"].unique())

    explorer_codes = st.multiselect(
        "Filter indicators",
        options=all_indicator_codes,
        default=[selected_code],
        format_func=lambda code: data.loc[
            data["indicator_code"] == code, "indicator_name"
        ].iloc[0],
    )

    explorer_data = data[
        data["indicator_code"].isin(explorer_codes)
        & data["country_name"].isin(selected_countries)
        & data["year"].between(year_range[0], year_range[1])
    ].copy()

    st.write(f"**Matching observations:** {len(explorer_data):,}")

    st.dataframe(
        explorer_data.sort_values(
            ["country_name", "indicator_code", "year"]
        ),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = explorer_data.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download filtered observations (CSV)",
        data=csv_bytes,
        file_name="naijadatascope_observations.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------
# Tab 4: Data Quality and lineage
# ---------------------------------------------------------

with quality_tab:
    st.subheader("Warehouse health")

    total_rows = len(data)
    distinct_keys = data.drop_duplicates(
        subset=["country_code", "indicator_code", "year"]
    ).shape[0]

    missing_values = int(data["value"].isna().sum())
    duplicate_rows = total_rows - distinct_keys
    missing_units = int(data["unit"].isna().sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Observations", f"{total_rows:,}")
    k2.metric("Duplicate keys", f"{duplicate_rows:,}")
    k3.metric("Missing values", f"{missing_values:,}")
    k4.metric("Missing units", f"{missing_units:,}")

    st.markdown("#### Coverage by country and indicator")

    coverage = (
        data.groupby(
            ["country_name", "indicator_name", "indicator_code"],
            as_index=False,
        )
        .agg(
            observations=("value", "size"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            missing_values=("value", lambda s: int(s.isna().sum())),
            missing_units=("unit", lambda s: int(s.isna().sum())),
        )
    )

    st.dataframe(coverage, use_container_width=True, hide_index=True)

    st.markdown("#### Ingestion history")

    if logs.empty:
        st.warning("No ingestion history was found.")
    else:
        st.dataframe(logs, use_container_width=True, hide_index=True)

    st.markdown("#### Source information")

    source_table = (
        data[["source", "source_url", "fetched_at_utc"]]
        .drop_duplicates()
        .sort_values("fetched_at_utc", ascending=False)
    )

    st.dataframe(source_table, use_container_width=True, hide_index=True)

    st.markdown(
        "Data source: [World Bank Indicators API]"
        "(https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)"
    )


# ---------------------------------------------------------
# Tab 5: EBEN AI
# ---------------------------------------------------------

with ai_tab:
    st.subheader("EBEN — Enhanced Being for Exploration and Navigation")
    st.write(
        "Ask questions about the indicators in this dashboard. "
        "EBEN receives a compact summary of the selected dataset and "
        "must distinguish observations from interpretation."
    )

    api_key = get_gemini_key()

    if not api_key:
        st.warning(
            "AI is not configured yet. The dashboard works without an API key. "
            "To enable EBEN, add GEMINI_API_KEY to your local environment or "
            "Streamlit secrets. Never paste your key into this chat or commit it "
            "to GitHub."
        )

    question = st.text_area(
        "Your question",
        placeholder=(
            "Example: Compare Nigeria's GDP growth with Ghana's over the "
            "last ten years. What patterns can we see?"
        ),
        height=100,
        key="eben_question",
    )

    if st.button("Ask EBEN", type="primary", disabled=not bool(api_key)):
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            try:
                from google import genai

                ai_data = data[
                    data["indicator_code"].isin(all_indicator_codes)
                    & data["country_name"].isin(selected_countries)
                    & data["year"].between(year_range[0], year_range[1])
                ].copy()

                # Build a readable AI context while preserving warehouse values.
                ai_context = ai_data[
                    [
                        "country_name",
                        "indicator_code",
                        "indicator_name",
                        "year",
                        "value",
                        "unit",
                    ]
                ].sort_values(
                    ["indicator_code", "country_name", "year"]
                ).copy()

                ai_context["formatted_value"] = ai_context.apply(
                    lambda row: format_value(
                        row["value"], row["indicator_code"]
                    ),
                    axis=1,
                )

                context = ai_context[
                    [
                        "country_name",
                        "indicator_code",
                        "indicator_name",
                        "year",
                        "formatted_value",
                        "unit",
                    ]
                ].rename(
                    columns={"formatted_value": "value"}
                ).to_string(index=False)

                # Calculate coverage using the selected year range.
                # A year is missing if it has no row with a non-null value.
                expected_years = set(
                    range(year_range[0], year_range[1] + 1)
                )
                coverage_lines = []

                for country in selected_countries:
                    for code in all_indicator_codes:
                        indicator_rows = ai_data[
                            (ai_data["country_name"] == country)
                            & (ai_data["indicator_code"] == code)
                        ]

                        indicator_name = (
                            indicator_rows["indicator_name"].iloc[0]
                            if not indicator_rows.empty
                            else code
                        )

                        valid_rows = indicator_rows[
                            indicator_rows["value"].notna()
                        ]

                        observed_years = set(
                            valid_rows["year"].astype(int).tolist()
                        )

                        missing_years = sorted(
                            expected_years - observed_years
                        )

                        coverage_lines.append(
                            f"{country} | {indicator_name} ({code}) | "
                            f"Expected years: {len(expected_years)} | "
                            f"Available years: {len(expected_years) - len(missing_years)} | "
                            f"Missing years: "
                            f"{', '.join(map(str, missing_years)) if missing_years else 'None'}"
                        )

                coverage_context = "\n".join(coverage_lines)

                prompt = f"""
You are EBEN (Enhanced Being for Exploration and Navigation), the economic intelligence assistant for NaijaDataScope.

Rules:
1. Base factual claims only on the supplied data context.
2. Do not invent statistics, reporting years, sources, or causal explanations.
3. If the data does not answer a question, say so clearly.
4. Distinguish observed patterns from possible explanations.
5. Use clear language suitable for students, citizens, journalists, and analysts.
6. Mention the relevant indicator, country, and year when quoting figures.
7. Interpret each indicator according to its indicator code and unit.
8. NY.GDP.MKTP.CD is GDP in current US dollars (nominal GDP), not real GDP growth.
9. NY.GDP.MKTP.KD.ZG is annual real GDP growth in percent.
10. FP.CPI.TOTL.ZG is annual consumer-price inflation in percent.
11. SP.POP.TOTL is population; SL.UEM.TOTL.ZS is the unemployment rate in percent.
12. Format percentages to two decimal places and large values using readable units. Preserve currency symbols, units, signs, and the meaning of values. For GDP in current US dollars, display monetary values consistently as $574.18B or US$574.18 billion. Always include the currency symbol for monetary values. Write GDP values as plain text, for example US$574.18 billion in 2014. Never put backticks around currency amounts. Keep a space between every number, unit, and word. Do not join words together. Backticks may be used for indicator codes only.
13. Do not imply that correlation proves causation.
14. The supplied rows may be filtered and may not represent all available data.
15. Do not compare values from different indicators as if they share the same unit.
16. If a requested indicator is absent from the supplied context, say so clearly.
17. For questions about missing years or data completeness, use DATA COVERAGE CHECK. Do not claim a series is complete unless the coverage check confirms it. A year with no non-null observation is missing. Report the missing years explicitly when relevant.

DATA SOURCE: World Bank Indicators API
DASHBOARD SELECTED INDICATOR: {selected_name}
Treat the selected indicator as the dashboard's initial focus, not as a
restriction on the question. If the user asks about another indicator,
use that indicator's observations from DATA CONTEXT. If the requested
indicator is not present, say so clearly.
SELECTED COUNTRIES: {", ".join(selected_countries)}
SELECTED YEARS: {year_range[0]}–{year_range[1]}

DATA COVERAGE CHECK:
{coverage_context}

DATA CONTEXT:
{context}

USER QUESTION:
{question.strip()}

Answer in no more than 250 words, using this structure:
- Direct answer to the user's question.
- 4–6 concise bullet points with relevant figures, countries, and years.
- Clearly distinguish observed data from possible explanations.
- End with a brief takeaway and one relevant caveat.

Use only figures present in the supplied context. If the context cannot
answer the question, explain what is missing. Do not repeat your full
greeting in every response.
"""

                client = genai.Client(api_key=api_key)

                with st.spinner("EBEN is analysing the available data..."):
                    from google.genai import types
                    response = client.models.generate_content(
                        model="gemini-3.5-flash-lite",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(thinking_level="low"),
                            max_output_tokens=2048,
                            temperature=0.2,
                        ),
                    )

                answer = getattr(response, "text", None)
                # Deterministic answers for data-completeness questions.
                # Calculate coverage from the loaded warehouse data, not Gemini.
                completeness_question = bool(
                    re.search(
                        r"\b(missing years?|missing (?:annual )?observations?|"
                        r"data completeness|complete data|"
                        r"data coverage|gaps in (?:the )?data|"
                        r"fully populated|complete series)\b",
                        question,
                        flags=re.IGNORECASE,
                    )
                )

                if completeness_question:
                    question_lower = question.lower()

                    # Identify the requested country.
                    country_aliases = {
                        "nigeria": "Nigeria",
                        "ghana": "Ghana",
                        "south africa": "South Africa",
                    }

                    requested_country = next(
                        (
                            name
                            for alias, name in country_aliases.items()
                            if alias in question_lower
                        ),
                        None,
                    )

                    # Identify the requested indicator.
                    indicator_aliases = {
                        "FP.CPI.TOTL.ZG": [
                            "inflation",
                            "consumer-price",
                            "consumer price",
                        ],
                        "NY.GDP.MKTP.CD": [
                            "nominal gdp",
                            "current us dollars",
                            "gdp in current",
                        ],
                        "NY.GDP.MKTP.KD.ZG": [
                            "gdp growth",
                            "real gdp growth",
                        ],
                        "SP.POP.TOTL": ["population"],
                        "SL.UEM.TOTL.ZS": ["unemployment"],
                    }

                    requested_code = next(
                        (
                            code
                            for code, aliases in indicator_aliases.items()
                            if code.lower() in question_lower
                            or any(
                                alias in question_lower
                                for alias in aliases
                            )
                        ),
                        None,
                    )

                    # Extract an explicitly requested year range.
                    year_match = re.search(
                        r"\b(?:between|from)\s+(19\d{2}|20\d{2})"
                        r"\s+(?:and|to)\s+(19\d{2}|20\d{2})\b",
                        question,
                        flags=re.IGNORECASE,
                    )

                    if year_match:
                        start_year = int(year_match.group(1))
                        end_year = int(year_match.group(2))
                    else:
                        start_year, end_year = year_range

                    # Answer deterministically when the question is specific.
                    if (
                        requested_country
                        and requested_code
                        and start_year <= end_year
                    ):
                        series = data[
                            (data["country_name"] == requested_country)
                            & (data["indicator_code"] == requested_code)
                            & data["year"].between(start_year, end_year)
                        ].copy()

                        expected_years = set(
                            range(start_year, end_year + 1)
                        )

                        observed_years = set(
                            series.loc[
                                series["value"].notna(), "year"
                            ].astype(int)
                        )

                        missing_years = sorted(
                            expected_years - observed_years
                        )

                        available_count = len(
                            expected_years & observed_years
                        )
                        expected_count = len(expected_years)

                        indicator_name = (
                            series["indicator_name"].iloc[0]
                            if not series.empty
                            else requested_code
                        )

                        missing_text = (
                            ", ".join(map(str, missing_years))
                            if missing_years
                            else "None"
                        )

                        answer = (
                            f"Based on the loaded warehouse data, "
                            f"{requested_country}'s {indicator_name} series "
                            f"from {start_year} to {end_year} has "
                            f"{available_count} available annual observations "
                            f"out of {expected_count} expected. "
                            f"Missing years: {missing_text}.\n\n"
                            f"- **Country:** {requested_country}\n"
                            f"- **Indicator:** `{requested_code}` "
                            f"({indicator_name})\n"
                            f"- **Period:** {start_year}–{end_year}\n"
                            f"- **Expected observations:** {expected_count}\n"
                            f"- **Available observations:** {available_count}\n"
                            f"- **Missing years:** {missing_text}\n\n"
                            f"**Takeaway:** "
                            + (
                                "The series has no missing annual observations "
                                "in the requested period."
                                if not missing_years
                                else "The series has gaps in the requested period."
                            )
                            + " **Caveat:** This checks year coverage and "
                            "non-null values in the loaded warehouse; it does "
                            "not verify the source's accuracy or revisions."
                        )

                # Repair malformed USD formatting in nominal GDP responses.
                # Preserve Markdown formatting for indicator codes.
                if answer and (
                    "NY.GDP.MKTP.CD" in answer
                    or "nominal gdp" in answer.lower()
                    or "current US dollars" in answer.lower()
                ):
                    # Repair malformed currency symbols such as US`381.20.
                    answer = re.sub(
                        r"US`+\s*(?=\d)",
                        "US$",
                        answer,
                        flags=re.IGNORECASE,
                    )

                    # Insert missing spaces before monetary units.
                    answer = re.sub(
                        r"(?<=\d)(billion|million|trillion)",
                        r" \1",
                        answer,
                        flags=re.IGNORECASE,
                    )

                    # Repair missing spaces between units, years, and clauses.
                    answer = re.sub(
                        r"(billion|million|trillion)\s*in\s*(\d{4})\s*and\s*(?=US\$)",
                        r"\1 in \2 and ",
                        answer,
                        flags=re.IGNORECASE,
                    )
                    answer = re.sub(
                        r"(billion|million|trillion)\s*in\s*(\d{4})\b",
                        r"\1 in \2",
                        answer,
                        flags=re.IGNORECASE,
                    )
                    answer = re.sub(
                        r"\b(in)\s*(\d{4})\s*and\s*(?=US\$)",
                        r"\1 \2 and ",
                        answer,
                        flags=re.IGNORECASE,
                    )

                    # Remove backticks around currency amounts, not indicator codes.
                    answer = re.sub(
                        r"`(US\$|\$)(\s*\d[\d,]*(?:\.\d+)?"
                        r"(?:\s*(?:[KMBT]\b|billion\b|million\b|trillion\b))?)`",
                        r"\1\2",
                        answer,
                        flags=re.IGNORECASE,
                    )

                    # Repair a stray opening backtick before a monetary amount.
                    answer = re.sub(
                        r"`(?P<amount>\d[\d,]*(?:\.\d+)?"
                        r"\s*(?:[KMBT]\b|billion\b|million\b|trillion\b))(?!`)",
                        lambda match: "$" + match.group("amount"),
                        answer,
                        flags=re.IGNORECASE,
                    )

                # Check whether Gemini stopped because it reached its token limit.
                candidates = getattr(response, "candidates", None) or []
                finish_reason = (
                    getattr(candidates[0], "finish_reason", None)
                    if candidates
                    else None
                )
                finish_reason_text = str(finish_reason).upper()
                response_was_truncated = "MAX_TOKENS" in finish_reason_text

                if answer:
                    st.markdown("### EBEN's response")
                    st.markdown(answer)

                    if response_was_truncated:
                        st.warning(
                            "EBEN's response may be incomplete because it "
                            "reached the generation limit. Ask for a shorter "
                            "answer or narrow your question."
                        )

                    st.caption(
                        "Evidence: the selected NaijaDataScope warehouse data. "
                        "Source observations are provided by the World Bank. "
                        "AI-generated interpretations may contain errors."
                    )
                else:
                    if response_was_truncated:
                        st.warning(
                            "EBEN reached its generation limit without "
                            "returning a usable answer. Try a shorter question."
                        )
                    else:
                        st.warning(
                            "The AI service returned no text. Please try again."
                        )

            except Exception as exc:
                st.error(
                    "EBEN could not complete the request. Check the API key, "
                    "available API quota, network connection, and model access."
                )
                st.caption(f"Technical detail: {type(exc).__name__}: {exc}")

    st.divider()
    st.caption(
        "EBEN uses a generative AI model. It does not replace the source data, "
        "and its explanations should be checked against the displayed figures."
    )


# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------

st.divider()
st.caption(
    "NaijaDataScope | Nigeria Economic Intelligence Platform | "
    "Data source: World Bank | Built for transparent, data-driven exploration."
)
