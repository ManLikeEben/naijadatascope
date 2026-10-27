import unittest
from pathlib import Path

import duckdb


PROJECT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_DIR / "data" / "warehouse" / "naijadatascope.duckdb"


class TestNaijaDataScopeWarehouse(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not DB_PATH.exists():
            raise FileNotFoundError(f"Warehouse not found: {DB_PATH}")

        cls.con = duckdb.connect(str(DB_PATH), read_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_warehouse_contains_expected_rows(self):
        count = self.con.execute(
            "SELECT COUNT(*) FROM economic_indicators"
        ).fetchone()[0]
        self.assertEqual(count, 390)

    def test_expected_countries_exist(self):
        countries = {
            row[0] for row in self.con.execute(
                "SELECT DISTINCT country_code FROM economic_indicators"
            ).fetchall()
        }
        self.assertEqual(countries, {"NGA", "GHA", "ZAF"})

    def test_all_five_indicators_exist(self):
        indicators = {
            row[0] for row in self.con.execute(
                "SELECT DISTINCT indicator_code FROM economic_indicators"
            ).fetchall()
        }
        self.assertEqual(
            indicators,
            {
                "NY.GDP.MKTP.CD",
                "NY.GDP.MKTP.KD.ZG",
                "FP.CPI.TOTL.ZG",
                "SP.POP.TOTL",
                "SL.UEM.TOTL.ZS",
            },
        )

    def test_no_duplicate_observation_keys(self):
        duplicates = self.con.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT country_code, indicator_code, year
                FROM economic_indicators
                GROUP BY country_code, indicator_code, year
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        self.assertEqual(duplicates, 0)

    def test_no_missing_required_values(self):
        missing = self.con.execute("""
            SELECT COUNT(*)
            FROM economic_indicators
            WHERE country_code IS NULL
               OR country_name IS NULL
               OR indicator_code IS NULL
               OR indicator_name IS NULL
               OR year IS NULL
               OR value IS NULL
               OR unit IS NULL
               OR source IS NULL
        """).fetchone()[0]

        self.assertEqual(missing, 0)

    def test_each_country_indicator_has_26_years(self):
        results = self.con.execute("""
            SELECT country_code, indicator_code, COUNT(DISTINCT year)
            FROM economic_indicators
            GROUP BY country_code, indicator_code
        """).fetchall()

        self.assertEqual(len(results), 15)

        for country, indicator, year_count in results:
            with self.subTest(country=country, indicator=indicator):
                self.assertEqual(year_count, 26)

    def test_year_range_is_2000_to_2025(self):
        minimum, maximum = self.con.execute("""
            SELECT MIN(year), MAX(year)
            FROM economic_indicators
        """).fetchone()

        self.assertEqual(minimum, 2000)
        self.assertEqual(maximum, 2025)

    def test_units_are_correct(self):
        expected_units = {
            "NY.GDP.MKTP.CD": "Current US dollars",
            "NY.GDP.MKTP.KD.ZG": "Percent per year",
            "FP.CPI.TOTL.ZG": "Percent per year",
            "SP.POP.TOTL": "People",
            "SL.UEM.TOTL.ZS": "Percent of labour force",
        }

        results = self.con.execute("""
            SELECT DISTINCT indicator_code, unit
            FROM economic_indicators
        """).fetchall()

        actual_units = {}

        for indicator, unit in results:
            if indicator in actual_units:
                self.assertEqual(actual_units[indicator], unit)
            actual_units[indicator] = unit

        self.assertEqual(actual_units, expected_units)


if __name__ == "__main__":
    unittest.main(verbosity=2)
