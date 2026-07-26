"""Tests: options ontology serialize/validate (test 11)."""
from dopey_options import Underlying, OptionContract, OptionChain


def test_underlying_serialize_roundtrip():
    u = Underlying(symbol="SPY", price=450.0)
    u2 = Underlying.from_dict(u.to_dict())
    assert u2.symbol == "SPY" and u2.price == 450.0


def test_option_contract_mid_and_roundtrip():
    c = OptionContract(symbol="SPY240119C00400000", underlying_symbol="SPY",
                       option_type="call", strike=400.0, expiry="2024-01-19",
                       bid=5.0, ask=5.5, open_interest=1000, volume=200, iv=0.3)
    assert c.mid() == 5.25
    c2 = OptionContract.from_dict(c.to_dict())
    assert c2.strike == 400.0 and c2.defined_risk is True


def test_option_chain_serialize_roundtrip():
    u = Underlying(symbol="SPY", price=450.0)
    c = OptionContract(symbol="SPY240119C00400000", underlying_symbol="SPY",
                       option_type="call", strike=400.0, expiry="2024-01-19",
                       bid=5.0, ask=5.5, open_interest=1000, volume=200, iv=0.3)
    chain = OptionChain(underlying=u, contracts=[c], as_of="2024-01-01")
    d = chain.to_dict()
    chain2 = OptionChain.from_dict(d)
    assert chain2.underlying.symbol == "SPY"
    assert len(chain2.contracts) == 1
    assert chain2.calls()[0].option_type == "call"
    assert chain.min_open_interest(500) == [c]
