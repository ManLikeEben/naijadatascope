# NaijaDataScope Architecture

## Overview

NaijaDataScope is a data engineering and economic intelligence platform that collects economic indicators from the World Bank API, processes them into an analytical dataset, stores them in DuckDB, and presents them through a Streamlit dashboard.

The platform also includes EBEN, an AI assistant that uses Google Gemini to help users interpret economic data.

## Data Flow

### 1. Source

The World Bank API supplies annual economic indicators for Nigeria, Ghana, and South Africa.

### 2. Ingestion

The Python ingestion module retrieves indicator observations and saves raw API responses as JSON files in data/raw/.

### 3. Transformation

Python and Pandas process the retrieved observations into a structured dataset. The processed CSV is stored in data/processed/.

### 4. Analytical Storage

DuckDB stores the analytical observations and supporting metadata in data/warehouse/naijadatascope.duckdb.

The warehouse contains economic_indicators, indicator_catalog, and ingestion_log tables.

### 5. Visualisation

The Streamlit application queries the data and presents interactive economic analysis and visualisations using Plotly.

### 6. AI Interpretation

EBEN uses Google Gemini to generate explanations based on economic data supplied to it by the application. Its responses should be checked against the underlying data.
