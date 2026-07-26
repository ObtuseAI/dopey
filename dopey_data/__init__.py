"""Dopey data adapters + source scorecard (research stubs, no network/creds).

DOPEY-native package. Source scorecard is a stdlib dataclass; adapters are discovery/research
stubs that make NO network calls and use NO credentials in the first pass.
"""
from .source_scorecard import SourceScorecard  # noqa: F401
from .openbb_adapter import OpenBBAdapter  # noqa: F401
from .alpaca_options_data_adapter import AlpacaOptionsDataAdapter  # noqa: F401
from .tradier_options_data_adapter import TradierOptionsDataAdapter  # noqa: F401
from .sec_filing_adapter import SECFilingAdapter  # noqa: F401
from .yfinance_research_adapter import YFinanceResearchAdapter  # noqa: F401
from .robinhood_mcp_account_adapter import RobinhoodMCPAccountAdapter  # noqa: F401
