# NaijaDataScope

### Nigeria Economic Intelligence Platform

NaijaDataScope is an interactive economic intelligence platform that transforms World Bank economic indicators into an analytical warehouse and dashboard. It combines data engineering, visual analytics, and generative AI to explore Nigeria economic performance alongside Ghana and South Africa.

**Built with:** Python, Pandas, DuckDB, Streamlit, Plotly, World Bank API, and Google Gemini.

## Project Overview

The project collects economic indicators from the World Bank API, stores raw responses, transforms the data into a clean analytical dataset, and loads it into DuckDB for querying and analysis.

Users can explore economic trends through an interactive Streamlit dashboard and use EBEN, the AI assistant, to interpret selected data.

## Key Features

- Automated ingestion of World Bank economic data.
- Data cleaning and transformation using Python and Pandas.
- Analytical storage using DuckDB.
- Interactive dashboards and visualisations using Streamlit and Plotly.
- AI-powered data interpretation using Google Gemini.
- Automated data-quality tests.
- Documented data definitions and system architecture.

## Economic Indicators

| Indicator | World Bank Code | Unit |
|---|---|---|
| GDP (current US$) | NY.GDP.MKTP.CD | US dollars |
| GDP growth (annual %) | NY.GDP.MKTP.KD.ZG | Percent per year |
| Inflation (consumer prices, annual %) | FP.CPI.TOTL.ZG | Percent per year |
| Population, total | SP.POP.TOTL | People |
| Unemployment (ILO modelled estimate) | SL.UEM.TOTL.ZS | Percent of labour force |

## Geographic and Time Coverage

- Nigeria (NGA)
- Ghana (GHA)
- South Africa (ZAF)
- Annual observations covering 2000–2025.

Data availability may vary by indicator, country, and year. Missing observations should not be interpreted as zero.

## Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Data manipulation | Pandas |
| Analytical database | DuckDB |
| Dashboard | Streamlit |
| Visualisation | Plotly |
| Data source | World Bank API |
| AI assistant | Google Gemini |
| Testing | Python unittest |

## Data Pipeline Architecture

1. Retrieve economic indicators from the World Bank API.
2. Save raw API responses as JSON files.
3. Transform and validate observations using Python and Pandas.
4. Export the processed dataset to CSV.
5. Load analytical data and supporting metadata into DuckDB.
6. Query the warehouse through the Streamlit dashboard.
7. Use EBEN AI to interpret selected data when a Gemini API key is configured.

See [docs/architecture.md](docs/architecture.md) for more details.

## Getting Started

### Prerequisites

- Python 3.13 or a compatible Python version.
- Git.
- A Google Gemini API key for AI functionality.

### 1. Clone the repository

    git clone https://github.com/ManLikeEben/naijadatascope.git
    cd naijadatascope

### 2. Create a virtual environment

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

### 3. Install dependencies

    python -m pip install -r requirements.txt
### 4. Build or refresh the data warehouse

    python -m src.ingestion.world_bank

This downloads the configured World Bank indicators, processes the observations, and updates the local analytical warehouse.

### 5. Launch the dashboard

    streamlit run streamlit_app.py

Open the local address displayed in your terminal to explore the dashboard.

## Configure EBEN AI

EBEN uses Google Gemini to help interpret economic data displayed in the dashboard.

Configure your Gemini API key using the GEMINI_API_KEY environment variable or Streamlit secrets when deploying the application.

Never commit API keys, passwords, or other secrets to GitHub.


Run the automated warehouse tests with:

    python -m unittest discover -s tests -p "test_*.py" -v

The current test suite checks warehouse row counts, country and indicator coverage, duplicate observations, missing required values, year coverage, and units.

## Data Limitations

- Data is sourced from the World Bank API and may be revised over time.
- Data availability can differ by country, indicator, and year.
- GDP, inflation, unemployment, and population measure different aspects of an economy.
- Historical trends alone do not establish causation.
- AI-generated explanations can be incorrect and should be checked against the underlying data.

## Project Structure

```text
naijadatascope/
|-- data/
|   |-- raw/
|   |-- processed/
|   `-- warehouse/
|-- docs/
|-- src/
|   |-- ingestion/
|   |-- transformation/
|   |-- ai/
|   `-- utils/
|-- tests/
|-- streamlit_app.py
|-- requirements.txt
`-- README.md
```

## Author

Built by [ManLikeEben](https://github.com/ManLikeEben) as a data engineering and economic intelligence portfolio project.
