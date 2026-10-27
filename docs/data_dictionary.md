# NaijaDataScope Data Dictionary

## Dataset Overview

The dataset contains annual economic indicators retrieved from the World Bank API for Nigeria, Ghana, and South Africa, covering the period 2000–2025.

Each observation represents a country, indicator, and year.

## Economic Indicators

| Indicator | Code | Description | Unit |
|---|---|---|---|
| GDP (current US$) | NY.GDP.MKTP.CD | Monetary value of domestic production at current prices | US dollars |
| GDP growth (annual %) | NY.GDP.MKTP.KD.ZG | Annual percentage change in real GDP | Percent per year |
| Inflation (consumer prices, annual %) | FP.CPI.TOTL.ZG | Annual percentage change in consumer prices | Percent per year |
| Population, total | SP.POP.TOTL | Total population estimate | People |
| Unemployment (ILO modelled estimate) | SL.UEM.TOTL.ZS | Modelled estimate of unemployment as a share of the labour force | Percent of labour force |

## Countries

| Country | ISO3 Code |
|---|---|
| Nigeria | NGA |
| Ghana | GHA |
| South Africa | ZAF |

## Important Fields

| Field | Meaning |
|---|---|
| country_code | ISO3 country identifier |
| country_name | Country display name |
| indicator_code | World Bank indicator identifier |
| indicator_name | Human-readable indicator name |
| year | Calendar year associated with the observation |
| value | Numeric value reported for the indicator |
| unit | Measurement unit for the indicator |

## Data Quality and Interpretation

- Country, indicator, and year together identify an expected observation.
- Missing values should not be interpreted as zero.
- GDP at current prices is affected by price changes and exchange rates; it is not the same as real GDP growth.
- Correlation or co-movement between indicators does not establish causation.
- World Bank data may be revised after the dataset is downloaded.

## Source

World Bank Open Data API: https://api.worldbank.org/
