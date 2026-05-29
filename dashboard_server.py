#!/usr/bin/env python3
"""Local dashboard server with a small Clip Mix YouTube search endpoint."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import math
import os
import random
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HISTORY_PATH = Path("/tmp/browser-dashboard-clip-history.json")
CLIP_CACHE_PATH = Path("/tmp/browser-dashboard-clip-cache.json")
CLIP_CACHE_LOCK = threading.Lock()
PREFETCH_STATE = {"running": False}

TOPICS = [
    {
        "key": "communication",
        "label": "Communication",
        "queries": [
            "communication skills short video",
            "how to speak clearly short",
            "better conversations short tips",
            "active listening short video",
        ],
        "keywords": ["communication", "speak", "conversation", "listening", "people"],
    },
    {
        "key": "lifestyle",
        "label": "Lifestyle",
        "queries": [
            "simple lifestyle habits short",
            "better daily routine short video",
            "small life improvement tips short",
            "minimal lifestyle habits short",
        ],
        "keywords": ["life", "habit", "routine", "daily", "simple"],
    },
    {
        "key": "motivation",
        "label": "Motivation",
        "queries": [
            "calm motivation short video",
            "discipline advice short",
            "mindset shift short video",
            "motivation without yelling short",
        ],
        "keywords": ["motivation", "discipline", "mindset", "focus", "growth"],
    },
    {
        "key": "facts",
        "label": "Fun Fact",
        "queries": [
            "interesting facts short video",
            "fun facts explained short",
            "things you did not know short video",
            "amazing facts under 3 minutes",
        ],
        "keywords": ["fact", "facts", "explained", "know", "interesting"],
    },
    {
        "key": "vocabulary",
        "label": "Vocabulary",
        "queries": [
            "english vocabulary daily life short",
            "common english phrases short",
            "english words for conversation short",
            "vocabulary to sound natural short",
        ],
        "keywords": ["english", "vocabulary", "phrases", "words", "conversation"],
        "captions": True,
    },
    {
        "key": "conversation_english",
        "label": "English",
        "queries": [
            "daily english conversation short",
            "speak english naturally short",
            "english speaking practice short video",
            "real life english phrases short",
        ],
        "keywords": ["english", "speaking", "conversation", "phrases", "practice"],
        "captions": True,
    },
    {
        "key": "social_skills",
        "label": "Social Skill",
        "queries": [
            "social skills short video",
            "how to be more confident socially short",
            "body language tips short video",
            "make a good first impression short",
        ],
        "keywords": ["social", "confidence", "body language", "impression", "people"],
    },
    {
        "key": "career",
        "label": "Work Skill",
        "queries": [
            "career advice short video",
            "work communication tips short",
            "productivity at work short video",
            "professional communication short tips",
        ],
        "keywords": ["career", "work", "professional", "productivity", "communication"],
    },
    {
        "key": "psychology",
        "label": "Mind",
        "queries": [
            "psychology facts short video",
            "human behavior explained short",
            "why people think this way short",
            "psychology tips short",
        ],
        "keywords": ["psychology", "behavior", "mind", "people", "thinking"],
    },
    {
        "key": "story",
        "label": "Story",
        "queries": [
            "short inspiring story",
            "life lesson story short video",
            "interesting biography short video",
            "short story with lesson",
        ],
        "keywords": ["story", "lesson", "life", "biography", "inspiring"],
    },
    {
        "key": "culture",
        "label": "Culture",
        "queries": [
            "culture facts short video",
            "world culture explained short",
            "interesting places facts short",
            "traditions around the world short",
        ],
        "keywords": ["culture", "world", "places", "tradition", "history"],
    },
]

ORDER_CHOICES = ["relevance", "viewCount", "date"]
BAD_TERMS = [
    "tedx",
    "ted talk",
    "ted talks",
    "full podcast",
    "podcast episode",
    "full episode",
    "lecture",
    "course",
    "webinar",
    "class 10",
    "class 11",
    "class 12",
    "physics",
    "chemistry",
    "organic chemistry",
    "quantum",
    "calculus",
    "algebra",
    "news",
    "politics",
    "election",
    "breaking news",
    "nursery",
    "kids song",
    "cocomelon",
    "asmr",
    "reaction",
    "minecraft",
    "roblox",
]
GOOD_TERMS = [
    "short",
    "quick",
    "tips",
    "explained",
    "english",
    "conversation",
    "facts",
    "habit",
    "story",
    "#shorts",
]


class ClipError(Exception):
    pass


def load_env_file() -> None:
    for filename in (".dashboard.env", ".env"):
        path = ROOT / filename
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def parse_human_duration(value: str) -> int:
    text = html_lib.unescape(value or "").lower().replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return 0
    colon_match = re.search(r"\b(\d{1,2})(?::(\d{1,2}))?(?::(\d{2}))\b", text)
    if colon_match:
        parts = [int(part) for part in colon_match.groups() if part is not None]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]

    hours = re.search(r"(\d+)\s*h(?:our)?s?", text)
    minutes = re.search(r"(\d+)\s*m(?:in(?:ute)?)?s?", text)
    seconds = re.search(r"(\d+)\s*s(?:ec(?:ond)?)?s?", text)
    total = 0
    if hours:
        total += int(hours.group(1)) * 3600
    if minutes:
        total += int(minutes.group(1)) * 60
    if seconds:
        total += int(seconds.group(1))
    return total


def parse_view_count(value: str) -> int:
    text = html_lib.unescape(value or "").lower().replace(",", "")
    match = re.search(r"([\d.]+)\s*([kmb])?\s*views?", text)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1)
    return int(number * multiplier)


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def load_history() -> list[str]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return [item for item in data.get("videoIds", []) if isinstance(item, str)]
    except Exception:
        return []


def save_history(video_ids: list[str]) -> None:
    payload = {"videoIds": video_ids[-80:], "savedAt": int(time.time())}
    HISTORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_cache_target_size() -> int:
    try:
        return max(1, min(12, int(os.environ.get("CLIP_MIX_CACHE_SIZE", "5"))))
    except ValueError:
        return 5


def get_prefetch_interval_seconds() -> int:
    try:
        return max(300, int(os.environ.get("CLIP_MIX_PREFETCH_SECONDS", "3600")))
    except ValueError:
        return 3600


def get_initial_prefetch_delay_seconds() -> int:
    try:
        return max(0, int(os.environ.get("CLIP_MIX_PREFETCH_START_DELAY_SECONDS", "8")))
    except ValueError:
        return 8


def load_clip_cache_unlocked() -> list[dict]:
    try:
        data = json.loads(CLIP_CACHE_PATH.read_text(encoding="utf-8"))
        items = data.get("items", [])
        return [
            item for item in items
            if isinstance(item, dict) and item.get("clip", {}).get("videoId")
        ]
    except Exception:
        return []


def save_clip_cache_unlocked(items: list[dict]) -> None:
    payload = {
        "items": items[-get_cache_target_size():],
        "savedAt": int(time.time()),
    }
    CLIP_CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_cached_video_ids() -> set[str]:
    with CLIP_CACHE_LOCK:
        return {
            item["clip"]["videoId"]
            for item in load_clip_cache_unlocked()
            if item.get("clip", {}).get("videoId")
        }


def pop_cached_clip(avoid_ids: set[str]) -> tuple[dict, dict] | None:
    with CLIP_CACHE_LOCK:
        items = load_clip_cache_unlocked()
        for index, item in enumerate(items):
            clip = item.get("clip", {})
            video_id = clip.get("videoId")
            if video_id and video_id not in avoid_ids:
                selected = items.pop(index)
                save_clip_cache_unlocked(items)
                meta = selected.get("meta", {})
                meta = {
                    **meta,
                    "cached": True,
                    "cachedAt": selected.get("cachedAt"),
                    "cacheRemaining": len(items),
                }
                return clip, meta
        return None


def store_cached_clip(clip: dict, meta: dict) -> None:
    if not clip.get("videoId"):
        return
    with CLIP_CACHE_LOCK:
        items = load_clip_cache_unlocked()
        items = [
            item for item in items
            if item.get("clip", {}).get("videoId") != clip["videoId"]
        ]
        items.append({
            "clip": clip,
            "meta": {**meta, "cached": True},
            "cachedAt": int(time.time()),
        })
        save_clip_cache_unlocked(items)


def compact_text(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def contains_bad_term(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in BAD_TERMS)


def text_from_runs(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return html_lib.unescape(value)
    if isinstance(value, list):
        return "".join(text_from_runs(item) for item in value)
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("simpleText"), str):
        return html_lib.unescape(value["simpleText"])
    if isinstance(value.get("content"), str):
        return html_lib.unescape(value["content"])
    if isinstance(value.get("runs"), list):
        return "".join(text_from_runs(run) for run in value["runs"])
    accessibility = value.get("accessibility")
    if isinstance(accessibility, dict):
        label = accessibility.get("accessibilityData", {}).get("label")
        if isinstance(label, str):
            return html_lib.unescape(label)
    if isinstance(value.get("text"), str):
        return html_lib.unescape(value["text"])
    return ""


def find_json_object_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def extract_initial_data(dom: str) -> dict | None:
    markers = [
        "var ytInitialData =",
        "window['ytInitialData'] =",
        'window["ytInitialData"] =',
    ]
    for marker in markers:
        marker_index = dom.find(marker)
        if marker_index == -1:
            continue
        start = dom.find("{", marker_index)
        if start == -1:
            continue
        end = find_json_object_end(dom, start)
        if end == -1:
            continue
        raw_json = dom[start : end + 1]
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            continue
    return None


def parse_video_renderer(renderer: dict) -> dict | None:
    video_id = renderer.get("videoId")
    if not video_id:
        return None
    title = text_from_runs(renderer.get("title"))
    channel = (
        text_from_runs(renderer.get("ownerText"))
        or text_from_runs(renderer.get("longBylineText"))
        or text_from_runs(renderer.get("shortBylineText"))
    )
    description = text_from_runs(renderer.get("descriptionSnippet"))
    duration_text = text_from_runs(renderer.get("lengthText"))
    accessibility_label = text_from_runs(renderer.get("title", {}).get("accessibility"))
    duration = parse_human_duration(duration_text) or parse_human_duration(accessibility_label)
    view_count = parse_view_count(text_from_runs(renderer.get("viewCountText"))) or parse_view_count(accessibility_label)
    return {
        "videoId": video_id,
        "title": title,
        "source": channel,
        "description": description,
        "durationSeconds": duration,
        "viewCount": view_count,
        "isShorts": "/shorts/" in json.dumps(renderer) or "shorts" in accessibility_label.lower(),
    }


def parse_reel_renderer(renderer: dict) -> dict | None:
    video_id = renderer.get("videoId")
    if not video_id:
        return None
    title = (
        text_from_runs(renderer.get("headline"))
        or text_from_runs(renderer.get("title"))
        or "YouTube Shorts pick"
    )
    views = parse_view_count(text_from_runs(renderer.get("viewCountText")))
    return {
        "videoId": video_id,
        "title": title,
        "source": "YouTube Shorts",
        "description": "",
        "durationSeconds": 60,
        "viewCount": views,
        "isShorts": True,
    }


def collect_renderers(value: object, candidates: list[dict]) -> None:
    if isinstance(value, list):
        for item in value:
            collect_renderers(item, candidates)
        return
    if not isinstance(value, dict):
        return

    if isinstance(value.get("videoRenderer"), dict):
        candidate = parse_video_renderer(value["videoRenderer"])
        if candidate:
            candidates.append(candidate)
    if isinstance(value.get("reelItemRenderer"), dict):
        candidate = parse_reel_renderer(value["reelItemRenderer"])
        if candidate:
            candidates.append(candidate)

    for child in value.values():
        collect_renderers(child, candidates)


def extract_anchor_candidates(dom: str) -> list[dict]:
    candidates = []
    seen = set()
    anchor_pattern = re.compile(
        r"<a\b(?P<attrs>[^>]*(?:/watch\?v=|/shorts/)[^>]*)>",
        re.IGNORECASE,
    )
    attr_pattern = re.compile(r'([a-zA-Z:-]+)="([^"]*)"')
    for match in anchor_pattern.finditer(dom):
        attrs = dict(attr_pattern.findall(match.group("attrs")))
        href = html_lib.unescape(attrs.get("href", ""))
        video_match = re.search(r"(?:/watch\?v=|/shorts/)([A-Za-z0-9_-]{11})", href)
        if not video_match:
            continue
        video_id = video_match.group(1)
        if video_id in seen:
            continue
        seen.add(video_id)
        aria = html_lib.unescape(attrs.get("aria-label", ""))
        title = html_lib.unescape(attrs.get("title", "")) or aria.split(" by ")[0].strip()
        candidates.append(
            {
                "videoId": video_id,
                "title": title or "YouTube clip",
                "source": "YouTube",
                "description": aria,
                "durationSeconds": parse_human_duration(aria) or (60 if "/shorts/" in href else 0),
                "viewCount": parse_view_count(aria),
                "isShorts": "/shorts/" in href,
            }
        )
    return candidates


def extract_video_candidates(dom: str) -> list[dict]:
    candidates = []
    initial_data = extract_initial_data(dom)
    if initial_data:
        collect_renderers(initial_data, candidates)

    if not candidates:
        candidates = extract_anchor_candidates(dom)

    deduped = []
    seen = set()
    for candidate in candidates:
        video_id = candidate.get("videoId")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        deduped.append(candidate)
    return deduped


def load_youtube_search_dom(query: str) -> str:
    chrome = os.environ.get("CLIP_MIX_CHROME", "google-chrome")
    budget_ms = os.environ.get("CLIP_MIX_HEADLESS_BUDGET_MS", "5000")
    try:
        int(budget_ms)
    except ValueError:
        budget_ms = "5000"

    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": query}
    )
    with tempfile.TemporaryDirectory(prefix="clip-mix-chrome-") as profile_dir:
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-crashpad",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--mute-audio",
            f"--user-data-dir={profile_dir}",
            f"--virtual-time-budget={budget_ms}",
            "--dump-dom",
            url,
        ]
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=28,
            )
        except FileNotFoundError as err:
            raise ClipError(f"Headless Chrome not found: {chrome}") from err
        except subprocess.TimeoutExpired as err:
            raise ClipError("Headless YouTube search timed out.") from err

    if result.returncode != 0 and not result.stdout:
        message = result.stderr.strip().splitlines()[-1:] or ["Headless Chrome failed."]
        raise ClipError(message[0])
    return result.stdout


def score_video(item: dict, topic: dict, query: str) -> tuple[int, dict] | None:
    title = item.get("title", "")
    description = item.get("description", "")
    channel = item.get("source", "")
    video_id = item.get("videoId", "")
    text = f"{title} {description} {channel}"
    seconds = int(item.get("durationSeconds") or 0)
    is_shorts = bool(item.get("isShorts"))

    if not video_id:
        return None
    if not is_shorts and (seconds < 18 or seconds > 540):
        return None
    if is_shorts and seconds <= 0:
        seconds = 60
    if seconds > 540:
        return None
    if contains_bad_term(text):
        return None

    lowered = text.lower()
    score = 40

    if seconds <= 90:
        score += 18
    elif seconds <= 180:
        score += 15
    elif seconds <= 300:
        score += 8
    elif seconds > 420:
        score -= 14

    if is_shorts or "#shorts" in lowered or "shorts" in lowered:
        score += 10
    for keyword in topic.get("keywords", []):
        if keyword.lower() in lowered:
            score += 6
    for term in GOOD_TERMS:
        if term in lowered:
            score += 3

    views = int(item.get("viewCount") or 0)
    if views:
        score += min(18, int(math.log10(max(views, 1)) * 4))
        if views < 1_000:
            score -= 10

    score += random.randint(0, 10)

    clip = {
        "title": compact_text(title, 90),
        "source": channel or "YouTube",
        "videoId": video_id,
        "start": 0,
        "end": min(seconds, 540),
        "category": topic["label"],
        "description": compact_text(description)
        or f"A short {topic['label'].lower()} clip discovered with headless YouTube search.",
        "tags": [
            topic["label"],
            "Shorts-style" if seconds <= 180 else "Short video",
            format_duration(seconds),
        ],
        "durationSeconds": seconds,
        "query": query,
        "searchedAt": int(time.time()),
    }
    return score, clip


def pick_weighted(scored: list[tuple[int, dict]]) -> dict:
    scored = sorted(scored, key=lambda pair: pair[0], reverse=True)[:10]
    weights = [max(1, score - 35) for score, _clip in scored]
    return random.choices([clip for _score, clip in scored], weights=weights, k=1)[0]


def search_fresh_clip(avoid_ids: set[str], remember: bool = True) -> tuple[dict, dict]:
    history = load_history()
    avoid = set(history[-30:]) | avoid_ids
    topic = random.choice(TOPICS)
    query = random.choice(topic["queries"])
    if random.random() < 0.35:
        query = f"{query} #shorts"

    dom = load_youtube_search_dom(query)
    candidates = [
        candidate
        for candidate in extract_video_candidates(dom)
        if candidate.get("videoId") not in avoid
    ]
    if not candidates:
        candidates = extract_video_candidates(dom)
    if not candidates:
        raise ClipError("Headless YouTube search returned no videos.")

    scored = []
    for candidate in candidates:
        scored_item = score_video(candidate, topic, query)
        if scored_item:
            scored.append(scored_item)
    if not scored:
        raise ClipError("No search results passed the Clip Mix filters.")

    clip = pick_weighted(scored)
    if remember:
        history.append(clip["videoId"])
        save_history(history)
    meta = {
        "topic": topic["key"],
        "topicLabel": topic["label"],
        "query": query,
        "mode": "headless-youtube",
        "candidateCount": len(scored),
    }
    return clip, meta


def prefill_clip_cache() -> None:
    target = get_cache_target_size()
    for _attempt in range(target):
        with CLIP_CACHE_LOCK:
            cache_items = load_clip_cache_unlocked()
            cache_count = len(cache_items)
            cache_ids = {
                item.get("clip", {}).get("videoId")
                for item in cache_items
                if item.get("clip", {}).get("videoId")
            }
        if cache_count >= target:
            return

        avoid_ids = set(load_history()[-40:]) | cache_ids
        try:
            clip, meta = search_fresh_clip(avoid_ids, remember=False)
        except ClipError as err:
            print(f"Clip Mix prefetch skipped: {err}")
            return
        store_cached_clip(clip, {**meta, "prefetched": True})


def trigger_prefetch(reason: str = "cache-low") -> None:
    with CLIP_CACHE_LOCK:
        if PREFETCH_STATE["running"]:
            return
        PREFETCH_STATE["running"] = True

    def run() -> None:
        try:
            print(f"Clip Mix prefetch start: {reason}")
            prefill_clip_cache()
        finally:
            with CLIP_CACHE_LOCK:
                PREFETCH_STATE["running"] = False

    threading.Thread(target=run, name="clip-mix-prefetch", daemon=True).start()


def start_hourly_prefetcher() -> None:
    def loop() -> None:
        time.sleep(get_initial_prefetch_delay_seconds())
        while True:
            trigger_prefetch("hourly")
            time.sleep(get_prefetch_interval_seconds())

    threading.Thread(target=loop, name="clip-mix-hourly-prefetch", daemon=True).start()


def fetch_clip(avoid_ids: set[str]) -> tuple[dict, dict]:
    avoid = set(load_history()[-30:]) | avoid_ids
    cached = pop_cached_clip(avoid)
    if cached:
        clip, meta = cached
        history = load_history()
        history.append(clip["videoId"])
        save_history(history)
        if meta.get("cacheRemaining", 0) < max(2, get_cache_target_size() // 2):
            trigger_prefetch("cache-low")
        return clip, meta

    clip, meta = search_fresh_clip(avoid, remember=True)
    trigger_prefetch("post-live-search")
    return clip, {**meta, "cached": False}


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/clip":
            self.handle_clip(parsed)
            return
        super().do_GET()

    def handle_clip(self, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        avoid_ids = {
            item.strip()
            for item in ",".join(query.get("avoid", [])).split(",")
            if item.strip()
        }

        status = HTTPStatus.OK
        try:
            clip, meta = fetch_clip(avoid_ids)
            payload = {"ok": True, "clip": clip, "meta": meta}
        except ClipError as err:
            payload = {"ok": False, "message": str(err)}
        except Exception as err:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            payload = {"ok": False, "message": f"Unexpected clip search error: {err}"}

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="Run the Raman OS dashboard server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    os.chdir(ROOT)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    start_hourly_prefetcher()
    print(f"Raman OS dashboard serving http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
