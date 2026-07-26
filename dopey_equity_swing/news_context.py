"""Source-provenanced news classification, corroboration, and risk alerts."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "geopolitical_conflict": ("war", "invasion", "missile", "military", "ceasefire", "blockade", "strait", "conflict"),
    "sanctions_trade_policy": ("sanction", "tariff", "export control", "trade restriction", "embargo"),
    "monetary_policy_rates": ("federal reserve", "central bank", "interest rate", "inflation", "fomc", "monetary policy"),
    "financial_stability": ("bank failure", "default", "liquidity crisis", "credit crisis", "bailout", "systemic"),
    "energy_supply": (
        "crude oil",
        "oil production",
        "oil supply",
        "oil export",
        "oil waiver",
        "natural gas",
        "opec",
        "lng",
        "pipeline",
        "energy disruption",
        "refinery",
    ),
    "regulation_enforcement": ("sec charges", "cftc charges", "enforcement", "fraud", "market manipulation", "regulation"),
    "cyber_infrastructure": ("cyberattack", "ransomware", "data breach", "infrastructure outage"),
    "crypto_market": ("bitcoin", "ethereum", "crypto", "digital asset", "stablecoin"),
    "semiconductor_supply": ("semiconductor", "chip export", "chip shortage", "foundry"),
}

CRITICAL_TERMS = ("invasion", "missile attack", "bank failure", "sovereign default", "blockade", "cyberattack", "emergency rate cut")
HIGH_TERMS = ("war", "sanction", "tariff", "ceasefire", "default", "crisis", "disruption", "export control")
RISK_OFF_TERMS = ("war", "invasion", "attack", "blockade", "sanction", "tariff", "default", "failure", "crisis", "disruption", "cyberattack")
RISK_ON_TERMS = ("ceasefire", "agreement", "reopening", "de-escalation", "stimulus", "liquidity support")
STOP_WORDS = frozenset({"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "from", "at", "by", "as", "is", "are", "says", "new"})
GEOPOLITICAL_STRONG_PHRASES = (
    "invasion",
    "missile attack",
    "military strike",
    "airstrike",
    "drone strike",
    "ceasefire",
    "blockade",
)
GEOPOLITICAL_CONTEXT_TERMS = (
    "sanction",
    "military",
    "missile",
    "troops",
    "border",
    "iran",
    "israel",
    "gaza",
    "russia",
    "ukraine",
    "china",
    "taiwan",
    "nato",
    "oil",
    "natural gas",
    "shipping",
    "strait",
)
GEOPOLITICAL_FALSE_POSITIVE_PHRASES = (
    "gangs go to war",
    "war medals",
    "wartime atrocities",
    "culture war",
    "price war",
    "bidding war",
)

CATEGORY_EXPOSURES: dict[str, dict[str, tuple[str, ...]]] = {
    "geopolitical_conflict": {"themes": ("energy", "industrials", "defensive"), "assets": ("CL", "BZ", "GC", "DXY", "ES")},
    "sanctions_trade_policy": {"themes": ("energy", "ai", "quantum", "crypto", "industrials"), "assets": ("CL", "BZ", "HG", "DXY", "NQ")},
    "monetary_policy_rates": {"themes": ("ai", "financials", "consumer", "utilities", "crypto"), "assets": ("ZN", "ZB", "DXY", "ES", "NQ")},
    "financial_stability": {"themes": ("financials", "consumer", "crypto"), "assets": ("ES", "RTY", "ZN", "GC", "DXY")},
    "energy_supply": {"themes": ("energy", "consumer", "industrials", "utilities"), "assets": ("CL", "BZ", "NG", "DXY")},
    "regulation_enforcement": {"themes": ("financials", "crypto", "ai"), "assets": ("ES", "BTC", "ETH")},
    "cyber_infrastructure": {"themes": ("ai", "financials", "industrials", "crypto"), "assets": ("NQ", "ES", "BTC")},
    "crypto_market": {"themes": ("crypto", "financials"), "assets": ("BTC", "ETH", "DXY", "NQ")},
    "semiconductor_supply": {"themes": ("ai", "quantum", "industrials"), "assets": ("NQ", "HG", "DXY")},
}

HIGH_QUALITY_DOMAINS = frozenset(
    {
        "reuters.com", "www.reuters.com", "apnews.com", "www.apnews.com", "bloomberg.com", "www.bloomberg.com",
        "ft.com", "www.ft.com", "wsj.com", "www.wsj.com", "cnbc.com", "www.cnbc.com", "economist.com",
        "www.economist.com", "nytimes.com", "www.nytimes.com", "washingtonpost.com", "www.washingtonpost.com",
    }
)

SYMBOL_ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("apple",), "AMD": ("advanced micro devices", " amd "), "AMZN": ("amazon",),
    "COIN": ("coinbase",), "GOOGL": ("google", "alphabet"), "JPM": ("jpmorgan", "jp morgan"),
    "META": ("meta platforms", "facebook"), "MSFT": ("microsoft",), "MSTR": ("microstrategy", "strategy inc"),
    "NVDA": ("nvidia",), "PLTR": ("palantir",), "TSLA": ("tesla",),
}


def load_news_snapshot(data_path: Path, manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"news manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("provider_terms_reviewed") is not True:
        raise ValueError(f"news provider terms are not reviewed: {manifest_path}")
    if str(manifest.get("pipeline_status", "")) != "complete":
        raise ValueError(f"news manifest is not complete: status={manifest.get('pipeline_status')}")
    if not data_path.exists():
        raise FileNotFoundError(f"news event snapshot is missing: {data_path}")
    actual_hash = hashlib.sha256(data_path.read_bytes()).hexdigest()
    if actual_hash != str(manifest.get("file_sha256", "")):
        raise ValueError(
            f"news event hash mismatch: path={data_path}, expected={manifest.get('file_sha256')}, actual={actual_hash}"
        )
    events: list[dict[str, Any]] = []
    with data_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError(f"news event must be an object: path={data_path}, line={line_number}")
            events.append(parsed)
    if not events:
        raise ValueError(f"news event snapshot is empty: {data_path}")
    if int(manifest.get("event_count", -1)) != len(events):
        raise ValueError(
            f"news event count does not match manifest: path={data_path}, expected={manifest.get('event_count')}, actual={len(events)}"
        )
    return events, manifest


def classify_news_events(events: list[dict[str, Any]], decision_time: datetime) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for event in events:
        published = _parse_datetime(str(event.get("published_at", "")))
        age_hours = (decision_time - published).total_seconds() / 3600.0 if published else None
        text = f"{event.get('title', '')} {event.get('summary', '')}".lower()
        categories = [
            category
            for category, terms in CATEGORY_TERMS.items()
            if _category_matches(category, terms, text)
        ]
        critical_count = sum(term in text for term in CRITICAL_TERMS)
        high_count = sum(term in text for term in HIGH_TERMS)
        severity = min(1.0, 0.20 + 0.45 * min(critical_count, 1) + 0.15 * min(high_count, 2))
        if not categories:
            severity = min(severity, 0.25)
        risk_off = sum(term in text for term in RISK_OFF_TERMS)
        risk_on = sum(term in text for term in RISK_ON_TERMS)
        effect = "risk_off" if risk_off > risk_on else "risk_on" if risk_on > risk_off else "mixed_or_uncertain"
        affected_themes = sorted(
            {theme for category in categories for theme in CATEGORY_EXPOSURES.get(category, {}).get("themes", ())}
        )
        affected_assets = sorted(
            {asset for category in categories for asset in CATEGORY_EXPOSURES.get(category, {}).get("assets", ())}
        )
        affected_symbols = sorted(
            symbol for symbol, aliases in SYMBOL_ALIASES.items() if any(alias in f" {text} " for alias in aliases)
        )
        classified.append(
            {
                **event,
                "categories": categories or ["other_market_relevant"],
                "severity_score": round(severity, 6),
                "market_effect": effect,
                "age_hours_at_decision": round(age_hours, 4) if age_hours is not None else None,
                "freshness_status": _freshness(age_hours),
                "affected_themes": affected_themes,
                "affected_assets": affected_assets,
                "affected_symbols": affected_symbols,
                "source_quality_score": _source_quality(event),
                "headline_only_classification": True,
            }
        )
    return classified


def build_news_intelligence(events: list[dict[str, Any]], decision_time: datetime) -> dict[str, Any]:
    classified = classify_news_events(events, decision_time)
    future_rejected = [
        event for event in classified
        if event["age_hours_at_decision"] is not None and float(event["age_hours_at_decision"]) < 0.0
    ]
    fresh = [
        event for event in classified
        if event["age_hours_at_decision"] is not None and 0.0 <= float(event["age_hours_at_decision"]) <= 168.0
    ]
    recent = [event for event in fresh if float(event["age_hours_at_decision"]) <= 72.0]
    clusters = corroborate_events(recent)
    alerts = [
        cluster
        for cluster in clusters
        if float(cluster["maximum_severity"]) >= 0.65
        and int(cluster["independent_source_count"]) >= 3
        and float(cluster["source_quality_score"]) >= 1.80
    ]
    official_alerts = [
        {
            "cluster_id": f"official-{event['event_id']}",
            "representative_title": event["title"],
            "categories": event["categories"],
            "article_count": 1,
            "independent_source_count": 1,
            "source_ids": [event["source_id"]],
            "source_domains": [urlparse(str(event.get("url", ""))).netloc.lower()],
            "maximum_severity": event["severity_score"],
            "market_effects": [event["market_effect"]],
            "affected_themes": event["affected_themes"],
            "affected_assets": event["affected_assets"],
            "affected_symbols": event["affected_symbols"],
            "source_quality_score": 1.0,
            "authoritative_single_source": True,
            "corroboration_required_for_veto": False,
        }
        for event in recent
        if event.get("source_authority") == "official_us_government"
        and float(event["severity_score"]) >= 0.80
        and float(event["age_hours_at_decision"]) <= 24.0
    ]
    alerts.extend(official_alerts)
    risk_off_weight = sum(
        float(alert["maximum_severity"])
        for alert in alerts
        if "risk_off" in alert["market_effects"] and "risk_on" not in alert["market_effects"]
    )
    risk_on_weight = sum(
        float(alert["maximum_severity"])
        for alert in alerts
        if "risk_on" in alert["market_effects"] and "risk_off" not in alert["market_effects"]
    )
    denominator = risk_off_weight + risk_on_weight
    risk_tone = (risk_on_weight - risk_off_weight) / denominator if denominator > 0.0 else 0.0
    theme_risk_scores = _theme_risk_scores(alerts)
    category_counts: dict[str, int] = {}
    for event in fresh:
        for category in event["categories"]:
            category_counts[str(category)] = category_counts.get(str(category), 0) + 1
    source_ids = sorted({str(event.get("source_id", "")) for event in classified})
    return {
        "artifact_type": "news_geopolitical_financial_intelligence",
        "pipeline_status": "complete",
        "decision_time": decision_time.astimezone(timezone.utc).isoformat(),
        "event_count": len(classified),
        "fresh_7d_event_count": len(fresh),
        "recent_72h_event_count": len(recent),
        "future_event_rejected_count": len(future_rejected),
        "source_ids": source_ids,
        "category_counts_7d": dict(sorted(category_counts.items())),
        "news_risk_tone_score": round(max(-1.0, min(1.0, risk_tone)), 6),
        "news_risk_tone_basis": "corroborated_multi_domain_or_critical_official_alerts_only_query_selection_bias_excluded",
        "theme_risk_tone_scores": theme_risk_scores,
        "corroborated_alert_count": len(alerts),
        "corroborated_risk_alerts": alerts[:25],
        "top_recent_events": sorted(recent, key=lambda event: (-float(event["severity_score"]), float(event["age_hours_at_decision"])))[:50],
        "veto_policy": "news_alone_never_vetoes_requires_corroborated_alert_and_cross_asset_stress",
        "classification_policy": "deterministic_headline_metadata_only_no_full_text_no_llm_sentiment_claim",
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def corroborate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=lambda item: str(item.get("published_at", "")), reverse=True):
        tokens = _title_tokens(str(event.get("title", "")))
        placed = False
        for cluster in clusters:
            exemplar_tokens = _title_tokens(str(cluster[0].get("title", "")))
            shared_categories = set(event["categories"]) & set(cluster[0]["categories"])
            if shared_categories and _jaccard(tokens, exemplar_tokens) >= 0.38:
                cluster.append(event)
                placed = True
                break
        if not placed:
            clusters.append([event])
    output: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters):
        domains = {
            str(event.get("source_domain", "")) or urlparse(str(event.get("url", ""))).netloc.lower()
            for event in cluster
        }
        source_ids = {str(event.get("source_id", "")) for event in cluster}
        quality_by_identity: dict[str, float] = {}
        for event in cluster:
            source_id = str(event.get("source_id", ""))
            domain = str(event.get("source_domain", "")) or urlparse(str(event.get("url", ""))).netloc.lower()
            identity = f"official:{source_id}" if source_id != "gdelt_doc_2" else domain
            if identity:
                quality_by_identity[identity] = max(quality_by_identity.get(identity, 0.0), float(event["source_quality_score"]))
        independent = set(quality_by_identity)
        output.append(
            {
                "cluster_id": f"news-cluster-{index:04d}",
                "representative_title": cluster[0]["title"],
                "categories": sorted({str(category) for event in cluster for category in event["categories"]}),
                "article_count": len(cluster),
                "independent_source_count": len(independent),
                "source_ids": sorted(source_ids),
                "source_domains": sorted(domain for domain in domains if domain),
                "source_quality_score": round(sum(quality_by_identity.values()), 6),
                "maximum_severity": round(max(float(event["severity_score"]) for event in cluster), 6),
                "market_effects": sorted({str(event["market_effect"]) for event in cluster}),
                "affected_themes": sorted({str(theme) for event in cluster for theme in event["affected_themes"]}),
                "affected_assets": sorted({str(asset) for event in cluster for asset in event["affected_assets"]}),
                "affected_symbols": sorted({str(symbol) for event in cluster for symbol in event["affected_symbols"]}),
                "corroboration_required_for_veto": True,
            }
        )
    return sorted(output, key=lambda cluster: (-int(cluster["independent_source_count"]), -float(cluster["maximum_severity"])))


def _category_matches(category: str, terms: tuple[str, ...], text: str) -> bool:
    if category != "geopolitical_conflict":
        return any(term in text for term in terms)
    if any(phrase in text for phrase in GEOPOLITICAL_FALSE_POSITIVE_PHRASES):
        return False
    if any(phrase in text for phrase in GEOPOLITICAL_STRONG_PHRASES):
        return True
    tokens = set(re.findall(r"[a-z0-9]+", text))
    conflict_word_present = "war" in tokens or "conflict" in tokens
    return conflict_word_present and any(term in text for term in GEOPOLITICAL_CONTEXT_TERMS)


def apply_external_context(
    thesis: dict[str, Any],
    theme: str,
    cross_asset_regime: dict[str, Any],
    news_intelligence: dict[str, Any],
    context_evidence_gate: dict[str, Any],
) -> dict[str, Any]:
    direction = str(thesis["direction"])
    direction_sign = 1.0 if direction == "bullish" else -1.0 if direction == "bearish" else 0.0
    theme_score = float(cross_asset_regime.get("theme_context_scores", {}).get(theme, cross_asset_regime.get("risk_appetite_score", 0.0)))
    news_score = float(
        news_intelligence.get("theme_risk_tone_scores", {}).get(
            theme,
            news_intelligence.get("news_risk_tone_score", 0.0),
        )
    )
    cross_alignment = theme_score * direction_sign
    news_alignment = news_score * direction_sign
    confirmation = 0.75 * cross_alignment + 0.25 * news_alignment
    confidence_tier = "context_supported" if confirmation >= 0.25 else "context_contradicted" if confirmation <= -0.25 else "context_mixed"
    stress = float(cross_asset_regime.get("systemic_stress_score", 0.0))
    corroborated_alert = int(news_intelligence.get("corroborated_alert_count", 0)) > 0
    veto_reasons: list[str] = []
    defensive_veto_allowed = bool(context_evidence_gate.get("defensive_veto_allowed", False))
    if defensive_veto_allowed and cross_alignment <= -0.70:
        veto_reasons.append("strong_cross_asset_theme_contradiction")
    if defensive_veto_allowed and corroborated_alert and stress >= 0.65:
        veto_reasons.append("corroborated_news_alert_with_cross_asset_stress")
    updated = {**thesis}
    reason_codes = list(thesis.get("reason_codes", []))
    original_intent = str(thesis["trade_intent"])
    if original_intent != "no_trade" and veto_reasons:
        updated["trade_intent"] = "no_trade"
        updated["thesis_status"] = "no_trade_external_context_veto"
        reason_codes.extend(veto_reasons)
    updated["reason_codes"] = reason_codes
    updated["external_context"] = {
        "theme": theme,
        "cross_asset_theme_score": round(theme_score, 6),
        "cross_asset_alignment_with_equity_direction": round(cross_alignment, 6),
        "news_risk_tone_score": round(news_score, 6),
        "news_alignment_with_equity_direction": round(news_alignment, 6),
        "context_confirmation_score": round(confirmation, 6),
        "context_confidence_tier": confidence_tier,
        "systemic_stress_score": round(stress, 6),
        "corroborated_news_alert_present": corroborated_alert,
        "veto_reasons": veto_reasons,
        "original_equity_trade_intent": original_intent,
        "direction_unchanged": updated["direction"] == thesis["direction"],
        "context_direction_weight": 0.0,
        "context_role": "confirmation_contradiction_or_joint_veto_only",
        "context_evidence_status": context_evidence_gate.get("evidence_status", "unknown"),
        "positive_context_promotion_allowed": bool(context_evidence_gate.get("positive_context_promotion_allowed", False)),
        "context_sizing_allowed": bool(context_evidence_gate.get("context_sizing_allowed", False)),
    }
    return updated


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _freshness(age_hours: float | None) -> str:
    if age_hours is None:
        return "unparseable_timestamp"
    if age_hours < 0.0:
        return "future_after_decision_rejected"
    if age_hours <= 24.0:
        return "fresh_24h"
    if age_hours <= 72.0:
        return "fresh_72h"
    if age_hours <= 168.0:
        return "fresh_7d"
    return "stale_over_7d"


def _title_tokens(title: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", title.lower()) if len(token) >= 3 and token not in STOP_WORDS}


def _jaccard(first: set[str], second: set[str]) -> float:
    union = first | second
    return len(first & second) / len(union) if union else 0.0


def _source_quality(event: dict[str, Any]) -> float:
    if event.get("source_authority") == "official_us_government":
        return 1.0
    domain = str(event.get("source_domain", "")) or urlparse(str(event.get("url", ""))).netloc.lower()
    return 0.85 if domain in HIGH_QUALITY_DOMAINS else 0.35


def _theme_risk_scores(alerts: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    weights: dict[str, float] = {}
    for alert in alerts:
        effects = set(str(effect) for effect in alert["market_effects"])
        direction = -1.0 if effects == {"risk_off"} else 1.0 if effects == {"risk_on"} else 0.0
        weight = float(alert["maximum_severity"]) * min(float(alert["source_quality_score"]), 3.0) / 3.0
        for theme in alert["affected_themes"]:
            key = str(theme)
            totals[key] = totals.get(key, 0.0) + direction * weight
            weights[key] = weights.get(key, 0.0) + weight
    return {
        theme: round(max(-1.0, min(1.0, totals[theme] / weights[theme])), 6)
        for theme in sorted(totals)
        if weights[theme] > 0.0
    }
