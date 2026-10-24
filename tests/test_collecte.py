"""Vérifie la lecture d'une réponse Yahoo (format quoteSummary)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collecte import _extraire  # noqa: E402

REPONSE = {"quoteSummary": {"result": [{
    "price": {"regularMarketPrice": 45.0, "currency": "GBp", "marketCap": 101_000_000,
              "longName": "Afentra plc"},
    "summaryDetail": {"trailingAnnualDividendYield": 0, "dividendYield": None,
                      "fiftyTwoWeekHigh": 55.0, "fiftyTwoWeekLow": 35.0, "beta": 0.9},
    "defaultKeyStatistics": {"sharesOutstanding": 226_000_000, "trailingEps": 0.02,
                             "bookValue": 0.6, "52WeekChange": 0.05,
                             "lastFiscalYearEnd": 1735603200},
    "financialData": {"financialCurrency": "USD", "totalRevenue": 150_000_000,
                      "ebitda": 70_000_000, "totalCash": 24_000_000, "totalDebt": 31_500_000,
                      "revenueGrowth": -0.2, "profitMargins": 0.08, "targetMeanPrice": 100.0,
                      "numberOfAnalystOpinions": 2, "recommendationMean": 1.5},
    "earningsTrend": {"trend": [
        {"period": "0q", "endDate": "2025-12-31"},
        {"period": "0y", "endDate": "2025-12-31",
         "earningsEstimate": {"avg": {"raw": 0.05}, "low": {"raw": 0.03}, "high": {"raw": 0.07},
                              "numberOfAnalysts": {"raw": 2}, "earningsCurrency": "USD"},
         "revenueEstimate": {"avg": {"raw": 120e6}, "low": {"raw": 110e6}, "high": {"raw": 130e6},
                             "numberOfAnalysts": {"raw": 2}, "growth": {"raw": -0.3},
                             "revenueCurrency": "USD"},
         "epsTrend": {"current": {"raw": 0.05}, "7daysAgo": {"raw": 0.05},
                      "90daysAgo": {"raw": 0.04}}},
        {"period": "+1y", "endDate": "2026-12-31",
         "earningsEstimate": {"avg": {"raw": 0.12}, "low": {"raw": 0.08}, "high": {"raw": 0.15},
                              "numberOfAnalysts": {"raw": 2}},
         "revenueEstimate": {"avg": {"raw": 200e6}, "growth": {"raw": 0.66}},
         "epsTrend": {"current": {"raw": 0.12}, "7daysAgo": {"raw": 0.11},
                      "90daysAgo": {"raw": 0.10}}},
    ]},
    "earningsHistory": {"history": [
        {"quarter": {"raw": 1719705600, "fmt": "2024-06-30"}, "surprisePercent": {"raw": 0.1}},
        {"quarter": {"raw": 1735603200, "fmt": "2024-12-31"}, "surprisePercent": {"raw": -0.05}},
    ]},
}]}}


def test_extraction():
    ligne, archive = _extraire("AET.L", REPONSE)
    assert ligne["cours"] == 45.0 and ligne["devise_cours"] == "GBp"
    assert ligne["devise_comptes"] == "USD"
    assert ligne["ca"] == 150e6 and ligne["dette"] == 31.5e6
    assert ligne["rendement"] == 0
    assert ligne["ex_a0"] == "2025-12-31" and ligne["ex_a1"] == "2026-12-31"
    assert ligne["bpa_a1_moy"] == 0.12 and ligne["bpa_a1_j90"] == 0.10
    assert ligne["croiss_ca_a1"] == 0.66
    assert ligne["fin_exercice"] == "2024-12-31"
    assert ligne["surprises"] == "2024-06-30:0.1000;2024-12-31:-0.0500"
    assert len(archive) == 2 and archive[1]["exercice"] == "2026-12-31"


if __name__ == "__main__":
    test_extraction()
    print("OK")
