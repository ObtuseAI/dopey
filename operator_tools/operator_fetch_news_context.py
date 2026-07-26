"""Stage source-provenanced official and global news events for paper research."""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlencode, urljoin, urlparse

import requests


class FeedSpec(TypedDict):
    source_id: str
    source_type: str
    url: str
    lane: str
    authority: str


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "news"
OUTPUT_PATH = OUTPUT_DIR / "news_events.jsonl"
LEDGER_PATH = OUTPUT_DIR / "news_event_ledger.jsonl"
MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "news_context_manifest.json"
SNAPSHOT_ROOT = OUTPUT_DIR / "snapshots"
MANIFEST_SNAPSHOT_ROOT = REPO_ROOT / "dopey_data" / "real" / "manifests" / "news_snapshots"
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 35
USER_AGENT = "DOPEY-paper-research/1.0 local operator news context"
NEWS_SOURCE_COVERAGE_POLICY_VERSION = "dopey-news-source-coverage-v2"

RSS_FEEDS: tuple[FeedSpec, ...] = (
    {"source_id": "federal_reserve", "source_type": "official_rss", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "lane": "monetary_policy_financial_stability", "authority": "official_us_government"},
    {"source_id": "sec", "source_type": "official_rss", "url": "https://www.sec.gov/news/pressreleases.rss", "lane": "securities_regulation_enforcement", "authority": "official_us_government"},
    {"source_id": "cftc_general", "source_type": "official_rss", "url": "https://www.cftc.gov/RSS/RSSGP/rssgp.xml", "lane": "derivatives_commodities_regulation", "authority": "official_us_government"},
    {"source_id": "cftc_enforcement", "source_type": "official_rss", "url": "https://www.cftc.gov/RSS/RSSENF/rssenf.xml", "lane": "derivatives_enforcement", "authority": "official_us_government"},
    {"source_id": "eia_today_in_energy", "source_type": "official_rss", "url": "https://www.eia.gov/rss/todayinenergy.xml", "lane": "energy_supply_demand", "authority": "official_us_government"},
    {"source_id": "eia_press", "source_type": "official_rss", "url": "https://www.eia.gov/rss/press_rss.xml", "lane": "energy_disruption_outlook", "authority": "official_us_government"},
)

TREASURY_PRESS_RELEASES_URL = "https://home.treasury.gov/news/press-releases"
TREASURY_SPEC = FeedSpec(
    source_id="us_treasury_press_releases",
    source_type="official_html",
    url=TREASURY_PRESS_RELEASES_URL,
    lane="global_geopolitical_financial",
    authority="official_us_government",
)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = (
    '(war OR invasion OR ceasefire OR sanctions OR tariff OR blockade OR "central bank" OR inflation '
    'OR recession OR default OR "bank failure" OR cyberattack OR oil OR "natural gas" OR semiconductor)'
)
GDELT_MAX_RECORDS = 100
REQUIRED_SOURCE_IDS: frozenset[str] = frozenset(
    {spec["source_id"] for spec in RSS_FEEDS} | {TREASURY_SPEC["source_id"]}
)
SUPPLEMENTAL_SOURCE_IDS: frozenset[str] = frozenset({"gdelt_doc_2"})


class TreasuryPressReleaseParser(HTMLParser):
    """External-source connector for the Treasury press-release index."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.published_at = ""
        self.capture_url = ""
        self.capture_text: list[str] = []
        self.entries: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "time" and attributes.get("datetime"):
            self.published_at = attributes["datetime"]
            return
        if tag != "a" or not self.published_at:
            return
        href = attributes.get("href", "")
        path = urlparse(href).path
        if not re.fullmatch(r"/news/press-releases/[A-Za-z0-9_-]+", path):
            return
        self.capture_url = urljoin(TREASURY_PRESS_RELEASES_URL, href)
        self.capture_text = []

    def handle_data(self, data: str) -> None:
        if self.capture_url:
            self.capture_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.capture_url:
            return
        title = " ".join(" ".join(self.capture_text).split())
        if title:
            self.entries.append((title, self.capture_url, self.published_at))
        self.capture_url = ""
        self.capture_text = []
        self.published_at = ""


def fetch_bytes(url: str, params: dict[str, str] | None) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_delay_seconds = float(attempt * 3)
        try:
            response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 200:
                if response.status_code == 429:
                    retry_delay_seconds = float(attempt * 8)
                body = response.text[:500].replace("\n", " ")
                raise RuntimeError(
                    f"HTTP request failed: url={response.url} status={response.status_code} body={body}"
                )
            if not response.content:
                raise RuntimeError(f"HTTP request returned empty body: url={response.url} status={response.status_code}")
            return response.content
        except requests.RequestException as error:
            last_error = error
        except RuntimeError as error:
            last_error = error
        print(
            f"WARNING news source attempt failed: url={url} attempt={attempt}/{MAX_ATTEMPTS} error={last_error}",
            flush=True,
        )
        if attempt < MAX_ATTEMPTS:
            time.sleep(retry_delay_seconds)
    raise RuntimeError(f"news source exhausted retries: url={url} params={params} last_error={last_error}") from last_error


def parse_rss(content: bytes, spec: FeedSpec) -> list[dict[str, Any]]:
    root = ET.fromstring(content)
    items = root.findall(".//item")
    events: list[dict[str, Any]] = []
    for item in items:
        title = _element_text(item, "title")
        url = _element_text(item, "link")
        published = _parse_timestamp(_element_text(item, "pubDate"))
        summary = _clean_text(_element_text(item, "description"))
        if not title or not url:
            continue
        events.append(_event(spec, title, summary, url, published, {}))
    return events


def parse_treasury_press_releases(content: bytes, spec: FeedSpec) -> list[dict[str, Any]]:
    parser = TreasuryPressReleaseParser()
    parser.feed(content.decode("utf-8"))
    parser.close()
    return [
        _event(spec, title, "", url, published_at, {})
        for title, url, published_at in parser.entries
    ]


def news_source_coverage(source_statuses: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for status in source_statuses:
        source_id = str(status.get("source_id", ""))
        if not source_id:
            raise ValueError(f"news source status is missing source_id: status={status}")
        if source_id in by_source:
            raise ValueError(f"duplicate news source status: source_id={source_id}")
        by_source[source_id] = status
    required_staged = sorted(
        source_id
        for source_id in REQUIRED_SOURCE_IDS
        if by_source.get(source_id, {}).get("status") == "staged"
    )
    required_failed = sorted(REQUIRED_SOURCE_IDS - set(required_staged))
    supplemental_staged = sorted(
        source_id
        for source_id in SUPPLEMENTAL_SOURCE_IDS
        if by_source.get(source_id, {}).get("status") == "staged"
    )
    supplemental_failed = sorted(SUPPLEMENTAL_SOURCE_IDS - set(supplemental_staged))
    return {
        "news_source_coverage_policy_version": NEWS_SOURCE_COVERAGE_POLICY_VERSION,
        "required_source_ids": sorted(REQUIRED_SOURCE_IDS),
        "supplemental_source_ids": sorted(SUPPLEMENTAL_SOURCE_IDS),
        "required_source_count": len(REQUIRED_SOURCE_IDS),
        "required_source_count_staged": len(required_staged),
        "required_source_failure_ids": required_failed,
        "supplemental_source_count": len(SUPPLEMENTAL_SOURCE_IDS),
        "supplemental_source_count_staged": len(supplemental_staged),
        "supplemental_source_failure_ids": supplemental_failed,
        "required_coverage_complete": not required_failed,
        "pipeline_status": "complete" if not required_failed else "partial_explicit_source_failures",
    }


def fetch_gdelt_events() -> list[dict[str, Any]]:
    params = {
        "query": GDELT_QUERY,
        "mode": "artlist",
        "maxrecords": str(GDELT_MAX_RECORDS),
        "format": "json",
        "sort": "datedesc",
        "timespan": "7d",
    }
    content = fetch_bytes(GDELT_URL, params)
    parsed = json.loads(content.decode("utf-8"))
    articles = parsed.get("articles", [])
    if not isinstance(articles, list):
        raise ValueError(f"GDELT response articles must be a list: request={GDELT_URL}?{urlencode(params)}")
    spec = FeedSpec(
        source_id="gdelt_doc_2",
        source_type="global_news_index",
        url=GDELT_URL,
        lane="global_geopolitical_financial",
        authority="secondary_global_coverage_index",
    )
    events: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title", "")).strip()
        url = str(article.get("url", "")).strip()
        if not title or not url:
            continue
        metadata = {
            "source_domain": str(article.get("domain", "")),
            "source_country": str(article.get("sourcecountry", "")),
            "language": str(article.get("language", "")),
        }
        events.append(_event(spec, title, "", url, _parse_gdelt_timestamp(str(article.get("seendate", ""))), metadata))
    return events


def deduplicate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        key = str(event["event_id"])
        if key not in unique or str(event["published_at"]) > str(unique[key]["published_at"]):
            unique[key] = event
    return sorted(unique.values(), key=lambda event: (str(event["published_at"]), str(event["event_id"])), reverse=True)


def write_outputs(
    events: list[dict[str, Any]],
    source_statuses: list[dict[str, Any]],
    run_stamp: str,
    ingested_at: str,
) -> dict[str, Any]:
    if not events:
        raise ValueError("news snapshot cannot be written without source-provenanced events")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamped_events = [{**event, "ingested_at": ingested_at} for event in events]
    temp = OUTPUT_PATH.with_suffix(".jsonl.tmp")
    payload = "\n".join(json.dumps(event, sort_keys=True, ensure_ascii=False) for event in stamped_events) + "\n"
    temp.write_text(payload, encoding="utf-8")
    temp.replace(OUTPUT_PATH)
    snapshot_dir = SNAPSHOT_ROOT / run_stamp
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = snapshot_dir / OUTPUT_PATH.name
    snapshot_path.write_bytes(OUTPUT_PATH.read_bytes())
    existing_ids: set[str] = set()
    if LEDGER_PATH.exists():
        with LEDGER_PATH.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                parsed = json.loads(line)
                if not isinstance(parsed, dict) or "event_id" not in parsed:
                    raise ValueError(f"news event ledger row is invalid: path={LEDGER_PATH}, line={line_number}")
                existing_ids.add(str(parsed["event_id"]))
    new_events = [event for event in stamped_events if str(event["event_id"]) not in existing_ids]
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        for event in new_events:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
    staged = sum(status["status"] == "staged" for status in source_statuses)
    official_staged = sum(
        status["status"] == "staged" and status["authority"] == "official_us_government"
        for status in source_statuses
    )
    coverage = news_source_coverage(source_statuses)
    manifest: dict[str, Any] = {
        "manifest_id": f"news-context-{datetime.now(timezone.utc).date().isoformat()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_family": "source_provenanced_news_context",
        "pipeline_status": coverage["pipeline_status"],
        "provider_terms_reviewed": True,
        "license_status": "reviewed_public_links_and_metadata_internal_research",
        "full_text_stored": False,
        "redistribution_allowed": False,
        "local_file_path": OUTPUT_PATH.relative_to(REPO_ROOT).as_posix(),
        "file_sha256": hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest(),
        "immutable_snapshot_path": snapshot_path.relative_to(REPO_ROOT).as_posix(),
        "immutable_snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "event_ledger_path": LEDGER_PATH.relative_to(REPO_ROOT).as_posix(),
        "event_ledger_sha256": hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest(),
        "event_ledger_new_event_count": len(new_events),
        "event_ledger_unique_event_count": len(existing_ids) + len(new_events),
        "event_count": len(stamped_events),
        "source_count_staged": staged,
        "official_source_count_staged": official_staged,
        "source_statuses": source_statuses,
        "source_coverage": coverage,
        "source_documentation": {
            "federal_reserve": "https://www.federalreserve.gov/newsevents/pressreleases.htm",
            "sec": "https://www.sec.gov/about/rss-feeds",
            "cftc": "https://www.cftc.gov/RSS/index.htm",
            "eia": "https://www.eia.gov/tools/rssfeeds/index.php",
            "us_treasury_press_releases": TREASURY_PRESS_RELEASES_URL,
            "gdelt_doc_2": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/",
        },
        "paper_only": True,
        "live_blocked": True,
        "not_credentials": True,
        "not_broker_data": True,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest_temp = MANIFEST_PATH.with_suffix(".json.tmp")
    manifest_temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_temp.replace(MANIFEST_PATH)
    (snapshot_path.parent / "news_context_manifest.json").write_bytes(MANIFEST_PATH.read_bytes())
    MANIFEST_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_snapshot = MANIFEST_SNAPSHOT_ROOT / f"news_context_manifest_{run_stamp}.json"
    manifest_snapshot.write_bytes(MANIFEST_PATH.read_bytes())
    return manifest


def main() -> int:
    run_time = datetime.now(timezone.utc)
    run_stamp = run_time.strftime("%Y%m%dT%H%M%SZ")
    ingested_at = run_time.isoformat()
    events: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for spec in RSS_FEEDS:
        try:
            fetched = parse_rss(fetch_bytes(spec["url"], None), spec)
            if not fetched:
                raise ValueError(f"RSS source parsed zero events: source_id={spec['source_id']} url={spec['url']}")
        except (ET.ParseError, RuntimeError, ValueError) as error:
            statuses.append({**spec, "status": "failed_after_retries_or_parse", "event_count": 0, "error": str(error)})
            continue
        events.extend(fetched)
        statuses.append({**spec, "status": "staged", "event_count": len(fetched), "error": ""})
        time.sleep(0.5)
    try:
        treasury = parse_treasury_press_releases(
            fetch_bytes(TREASURY_SPEC["url"], None),
            TREASURY_SPEC,
        )
        if not treasury:
            raise ValueError("Treasury press-release index parsed zero events")
    except (RuntimeError, UnicodeDecodeError, ValueError) as error:
        statuses.append({**TREASURY_SPEC, "status": "failed_after_retries_or_parse", "event_count": 0, "error": str(error)})
    else:
        events.extend(treasury)
        statuses.append({**TREASURY_SPEC, "status": "staged", "event_count": len(treasury), "error": ""})
    time.sleep(0.5)
    gdelt_spec: dict[str, Any] = {
        "source_id": "gdelt_doc_2",
        "source_type": "global_news_index",
        "url": GDELT_URL,
        "lane": "global_geopolitical_financial",
        "authority": "secondary_global_coverage_index",
    }
    try:
        gdelt = fetch_gdelt_events()
        if not gdelt:
            raise ValueError("GDELT parsed zero events")
    except (json.JSONDecodeError, RuntimeError, UnicodeDecodeError, ValueError) as error:
        statuses.append({**gdelt_spec, "status": "failed_after_retries_or_parse", "event_count": 0, "error": str(error)})
    else:
        events.extend(gdelt)
        statuses.append({**gdelt_spec, "status": "staged", "event_count": len(gdelt), "error": ""})
    official_staged = sum(
        status["status"] == "staged" and status["authority"] == "official_us_government"
        for status in statuses
    )
    if official_staged < 4:
        raise RuntimeError(f"news official-source coverage floor failed: staged={official_staged}, required=4, statuses={statuses}")
    manifest = write_outputs(deduplicate_events(events), statuses, run_stamp, ingested_at)
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


def _event(
    spec: FeedSpec,
    title: str,
    summary: str,
    url: str,
    published_at: str,
    metadata: dict[str, str],
) -> dict[str, Any]:
    canonical_title = " ".join(title.split())
    event_id = hashlib.sha256(f"{spec['source_id']}|{url}|{canonical_title}".encode("utf-8")).hexdigest()
    return {
        "event_id": event_id,
        "source_id": spec["source_id"],
        "source_type": spec["source_type"],
        "source_authority": spec["authority"],
        "query_lane": spec["lane"],
        "published_at": published_at,
        "title": canonical_title,
        "summary": summary[:1000],
        "url": url,
        **metadata,
    }


def _element_text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return "" if child is None or child.text is None else child.text.strip()


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return " ".join(without_tags.split())


def _parse_timestamp(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _parse_gdelt_timestamp(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return value
    return parsed.isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
