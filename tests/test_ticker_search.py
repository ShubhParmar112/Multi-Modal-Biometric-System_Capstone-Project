"""Local ticker-search ranking checks.

pytest isn't installed in this repo, so this runs as a plain script:

    python -m tests.test_ticker_search

It's kept pytest-compatible anyway — the three assertions live in test_*
functions that a future pytest run would collect, and main() just calls them.
"""

from portfolio.holdings_service import search_tickers


def test_exact_symbol_beats_substring():
    # Exact symbol match must rank ahead of any substring hit.
    assert search_tickers("TCS")[0]["ticker"] == "TCS.NS"


def test_name_match_finds_infosys():
    assert any(r["ticker"] == "INFY.NS" for r in search_tickers("Infosys"))


def test_no_match_returns_empty():
    assert search_tickers("ZZZNOPE") == []


def main():
    test_exact_symbol_beats_substring()
    test_name_match_finds_infosys()
    test_no_match_returns_empty()
    print("OK - all 3 ticker-search assertions passed.")


if __name__ == "__main__":
    main()
