"""Paper-money tournament engine for model-priced long premium candidates."""
from __future__ import annotations

import math
from collections import defaultdict

from dopey_wealth_engine.common import stable_hash


def simulate_paper_tournament(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    trades: list[dict] = []
    capital_by_family: dict[str, float] = defaultdict(lambda: 100_000.0)
    for index, candidate in enumerate(candidates, start=1):
        if not candidate.get("paper_trade_allowed"):
            continue
        premium = float(candidate["model_price"])
        if premium <= 0:
            continue
        family = str(candidate["strategy_family"])
        allocation = min(capital_by_family[family] * 0.015, 2_500.0)
        contracts = max(1, int(allocation / max(premium * 100.0, 1.0)))
        pnl = _paper_pnl(candidate, contracts)
        trade = {
            "artifact_type": "paper_tournament_trade",
            "trade_id": f"paper-trade-{index:05d}",
            "signal_id": candidate["signal_id"],
            "underlying_symbol": candidate["underlying_symbol"],
            "strategy_family": family,
            "trade_intent": candidate["trade_intent"],
            "option_side": candidate["option_side"],
            "contracts": contracts,
            "entry_model_price": premium,
            "gross_premium_paid": round(premium * 100.0 * contracts, 4),
            "paper_pnl": round(pnl, 4),
            "return_on_premium": round(pnl / max(premium * 100.0 * contracts, 1.0), 6),
            "max_loss": round(premium * 100.0 * contracts, 4),
            "slippage_stress": candidate["slippage_stress"],
            "theta_bleed_stress": candidate["theta_decay_stress"],
            "iv_shock_stress": candidate["iv_shock_stress"],
            "volatility_regime": candidate["volatility_regime"],
            "trend_regime": candidate["trend_regime"],
            "market_data_source_type": candidate.get("market_data_source_type", "fixture_fallback"),
            "paper_only": True,
            "live_blocked": True,
        }
        trade["record_hash"] = stable_hash(trade)
        trades.append(trade)
    scores = _score_strategies(trades)
    return trades, scores


def _paper_pnl(candidate: dict, contracts: int) -> float:
    direction = 1.0 if candidate["trade_intent"] == "long_call" else -1.0
    quality = float(candidate["position_quality_score"])
    risk = float(candidate["risk_score"])
    model_price = float(candidate["model_price"])
    target_move = float(candidate["target_move"])
    symbol_seed = sum(ord(char) for char in str(candidate["underlying_symbol"]))
    realized_direction = math.sin(symbol_seed * 0.17 + quality * 4.0)
    directional_move = direction * realized_direction * target_move * 0.55
    intrinsic_capture = max(directional_move, -model_price * 0.85) * 100.0 * contracts * 0.42
    stress = (float(candidate["slippage_stress"]) + float(candidate["theta_decay_stress"]) * 0.08 + float(candidate["iv_shock_stress"]) * 0.18) * 100.0 * contracts
    quality_bonus = max(0.0, quality - 0.45) * model_price * 100.0 * contracts * 0.75
    risk_penalty = risk * model_price * 100.0 * contracts * 0.25
    return intrinsic_capture + quality_bonus - stress - risk_penalty


def _score_strategies(trades: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        grouped[f"{trade['strategy_family']}|{trade.get('market_data_source_type', 'fixture_fallback')}"].append(trade)
    scores: list[dict] = []
    for group_key, family_trades in sorted(grouped.items()):
        family, source_type = group_key.split("|", 1)
        pnls = [float(trade["paper_pnl"]) for trade in family_trades]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value <= 0]
        equity = 100_000.0
        peak = equity
        max_drawdown = 0.0
        loss_streak = 0
        max_loss_streak = 0
        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
            if pnl <= 0:
                loss_streak += 1
            else:
                loss_streak = 0
            max_loss_streak = max(max_loss_streak, loss_streak)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        expectancy = sum(pnls) / len(pnls) if pnls else 0.0
        score = {
            "artifact_type": "paper_tournament_strategy_score",
            "strategy_family": family,
            "market_data_source_type": source_type,
            "trade_count": len(family_trades),
            "net_paper_pnl": round(sum(pnls), 4),
            "cagr_proxy": round((equity / 100_000.0 - 1.0) * 2.0, 6),
            "expectancy": round(expectancy, 4),
            "average_win": round(sum(wins) / len(wins), 4) if wins else 0.0,
            "average_loss": round(sum(losses) / len(losses), 4) if losses else 0.0,
            "win_rate": round(len(wins) / len(pnls), 6) if pnls else 0.0,
            "payoff_skew": round((sum(wins) / len(wins)) / max(abs(sum(losses) / len(losses)), 1.0), 6) if wins and losses else 0.0,
            "max_drawdown": round(max_drawdown, 4),
            "drawdown_duration": max_loss_streak,
            "recovery_time": max_loss_streak,
            "sharpe_like": round(expectancy / max(_std(pnls), 1.0), 6),
            "sortino_like": round(expectancy / max(_std(losses), 1.0), 6),
            "profit_factor": round(gross_profit / max(gross_loss, 1.0), 6),
            "capital_efficiency": round(sum(pnls) / max(sum(float(trade["gross_premium_paid"]) for trade in family_trades), 1.0), 6),
            "turnover": len(family_trades),
            "loss_streak": max_loss_streak,
            "overtrade_penalty": round(max(0, len(family_trades) - 12) * 0.02, 6),
            "regime_robustness": round(len({trade["volatility_regime"] for trade in family_trades}) / 4.0, 6),
            "slippage_sensitivity": round(sum(float(trade["slippage_stress"]) for trade in family_trades), 4),
            "theta_bleed_sensitivity": round(sum(float(trade["theta_bleed_stress"]) for trade in family_trades), 4),
            "iv_shock_sensitivity": round(sum(float(trade["iv_shock_stress"]) for trade in family_trades), 4),
            "paper_only": True,
            "live_blocked": True,
            "public_data_paper_score": source_type.startswith("public"),
            "fixture_only_score": source_type == "fixture_fallback",
        }
        score["record_hash"] = stable_hash(score)
        scores.append(score)
    return sorted(scores, key=lambda item: (float(item["net_paper_pnl"]), float(item["profit_factor"])), reverse=True)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
