#!/usr/bin/env python3
"""Local dashboard server with a small Clip Mix YouTube search endpoint."""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HISTORY_PATH = Path("/tmp/browser-dashboard-clip-history.json")
CLIP_CACHE_PATH = Path("/tmp/browser-dashboard-clip-cache.json")
CHANNEL_CACHE_PATH = Path("/tmp/browser-dashboard-clip-channel-cache.json")
CLIP_CACHE_LOCK = threading.Lock()
CHANNEL_CACHE_LOCK = threading.Lock()
CHANNEL_RESOLVE_PENDING: set[str] = set()
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

TOPIC_BY_KEY = {topic["key"]: topic for topic in TOPICS}
EXPLORE_CHOICES = {"close", "explore", "surprise"}
DURATION_CHOICES = {"short", "medium", "long"}

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
    "reaction video",
    "minecraft",
    "roblox",
    "celebrity gossip",
    "control anyone",
    "dark psychology",
    "dark psychology manipulation",
    "wealth manifestation",
]
GOOD_TERMS = [
    "short",
    "quick",
    "tips",
    "explained",
    "example",
    "examples",
    "practical",
    "exercise",
    "exercises",
    "role play",
    "role-play",
    "english",
    "conversation",
    "facts",
    "habit",
    "story",
    "storytelling",
    "articulation",
    "interview",
    "#shorts",
]
LOW_QUALITY_TERMS = [
    "alpha male",
    "attitude status",
    "billionaire mindset",
    "compilation",
    "emotional status",
    "hustle",
    "inspirational",
    "inspirational status",
    "life changing speech",
    "mind blowing facts",
    "motivation shorts",
    "motivational status",
    "part 1",
    "part 2",
    "sigma",
    "sigma mindset",
    "success secrets",
    "status video",
    "tiktok compilation",
    "top 10 facts",
    "viral shorts",
    "whatsapp status",
]
WATCH_BAIT_TERMS = [
    "before you sleep",
    "changed my life",
    "control anyone",
    "do this every day",
    "everyone should know",
    "hack",
    "life changing",
    "mind blowing",
    "must watch",
    "secret",
    "secret trick",
    "success secret",
    "this will change",
    "watch till end",
    "you need to hear this",
]
QUALITY_BONUS_TERMS = {
    "articulation": 8,
    "body language": 7,
    "case study": 6,
    "cognitive bias": 8,
    "conversation example": 8,
    "decision making": 8,
    "demonstration": 7,
    "examples": 7,
    "explained simply": 7,
    "interview": 6,
    "observable behavior": 8,
    "practical advice": 8,
    "practice": 5,
    "research": 5,
    "role play": 9,
    "role-play": 9,
    "study": 5,
    "storytelling": 7,
}
PACING_BONUS_TERMS = {
    "balanced": 5,
    "calm": 6,
    "clear": 5,
    "clearly": 5,
    "simple": 4,
    "slowly": 3,
}
TITLE_PENALTY_TERMS = [
    "alpha",
    "control anyone",
    "hack",
    "hustle",
    "inspirational",
    "motivation",
    "motivational",
    "secret",
    "sigma",
]
FAST_CUT_PENALTY_TERMS = [
    "fast cuts",
    "hyper edited",
    "quick cuts",
    "rapid fire",
]
SOURCE_TIERS = {
    "tier_1": [
        "aevy tv",
        "vinh giang",
        "think fast talk smart",
        "charisma on command",
        "linguamarina",
        "english with lucy",
        "big think",
        "ali abdaal",
        "think school",
        "johnny harris",
        "soch by mohak mangal",
        "colin and samir",
    ],
    "tier_2": [
        "the school of life",
        "braincraft",
        "jeff su",
        "bbc learning english",
        "easy english",
        "great big story",
        "modern mba",
        "half as interesting",
        "abhi and niyu",
        "wendover productions",
        "dan koe",
        "max klymenko",
    ],
    "tier_3": [
        "psych2go",
        "ted-ed",
        "kurzgesagt",
        "asapscience",
        "life noggin",
        "science of people",
        "the art of improvement",
        "speak english with vanessa",
        "dhruv rathee",
        "my first million",
    ],
}
STATIC_CHANNEL_IDENTITIES = {
    "aevy tv": ("Aevy TV", "UCA295QVkf9O1RQ8_-s3FVXg"),
    "vinh giang": ("Vinh Giang", "UC9K9Wnz6t4cLnCdTzAVrXqQ"),
    "think fast talk smart": ("Think Fast Talk Smart", "UC5rhde2RHYNSF8aYKO-OHlw"),
    "charisma on command": ("Charisma on Command", "UCU_W0oE_ock8bWKjALiGs8Q"),
    "linguamarina": ("linguamarina", "UCAQg09FkoobmLquNNoO4ulg"),
    "english with lucy": ("English with Lucy", "UCz4tgANd4yy8Oe0iXCdSWfA"),
    "big think": ("Big Think", "UCvQECJukTDE2i6aCoMnS-Vg"),
    "ali abdaal": ("Ali Abdaal", "UCoOae5nYA7VqaXzerajD0lg"),
    "think school": ("Think School", "UCKZozRVHRYsYHGEyNKuhhdA"),
    "johnny harris": ("Johnny Harris", "UCmGSJVG3mCRXVOP4yZrU1Dw"),
    "soch by mohak mangal": ("Mohak Mangal", "UCz4a7agVFr1TxU-mpAP8hkw"),
    "colin and samir": ("Colin and Samir", "UCamLstJyCa-t5gfZegxsFMw"),
    "the school of life": ("The School of Life", "UC7IcJI8PUf5Z3zKxnZvTBog"),
    "braincraft": ("BrainCraft", "UCt_t6FwNsqr3WWoL6dFqG9w"),
    "jeff su": ("Jeff Su", "UCwAnu01qlnVg1Ai2AbtTMaA"),
    "bbc learning english": ("BBC Learning English", "UCHaHD477h-FeBbVh9Sh7syA"),
    "easy english": ("Easy English", "UCTRHegh7UqWuKRymXoqzbzA"),
    "great big story": ("Great Big Story", "UCajXeitgFL-rb5-gXI-aG8Q"),
    "modern mba": ("Modern MBA", "UCbzVRTkX3bzNZuBd9In4XyA"),
    "half as interesting": ("Half as Interesting", "UCuCkxoKLYO_EQ2GeFtbM_bw"),
    "abhi and niyu": ("Abhi and Niyu", "UCsDTy8jvHcwMvSZf_JGi-FA"),
    "wendover productions": ("Wendover Productions", "UC9RM-iSvTu1uPJb8X5yp3EQ"),
    "dan koe": ("Dan Koe", "UCWXYDYv5STLk-zoxMP2I1Lw"),
    "max klymenko": ("Max Klymenko", "UCisy6taOAeLfyaCqcMQDfig"),
    "psych2go": ("Psych2Go", "UCkJEpR7JmS36tajD34Gp4VA"),
    "ted ed": ("TED-Ed", "UCsooa4yRKGN_zEE8iknghZA"),
    "kurzgesagt": ("Kurzgesagt - In a Nutshell", "UCsXVk37bltHxD1rDPwtNM8Q"),
    "asapscience": ("AsapSCIENCE", "UCC552Sd-3nyi_tk2BudLUzA"),
    "life noggin": ("Life Noggin", "UCpJmBQ8iNHXeQ7jQWDyGe3A"),
    "science of people": ("Vanessa Van Edwards", "UCj9QBB4bNTv29f4oFIreNmw"),
    "the art of improvement": ("The Art of Improvement", "UCtYzVCmNxrshH4_bPO_-Y-A"),
    "speak english with vanessa": ("Speak English With Vanessa", "UCxJGMJbjokfnr2-s4_RXPxQ"),
    "dhruv rathee": ("Dhruv Rathee", "UC-CSyyi47VX1lD9zyeABW3w"),
    "my first million": ("My First Million", "UCyaN6mg5u8Cjy2ZI4ikWaug"),
}
SOURCE_TIER_ORDER = ("tier_1", "tier_2", "tier_3")
SOURCE_TIER_WEIGHTS = {"tier_1": 28, "tier_2": 18, "tier_3": 10}
SOURCE_TIER_ALIASES = {
    "tier_1": "tier_1",
    "tier1": "tier_1",
    "tier_1_must_have": "tier_1",
    "tier_2": "tier_2",
    "tier2": "tier_2",
    "tier_2_expand": "tier_2",
    "tier_3": "tier_3",
    "tier3": "tier_3",
    "tier_3_experimental": "tier_3",
}
SOURCE_BONUS_TERMS = {
    source: weight
    for tier, sources in SOURCE_TIERS.items()
    for weight in [SOURCE_TIER_WEIGHTS[tier]]
    for source in sources
}
SOURCE_PENALTY_TERMS = [
    "clips",
    "official music",
    "podcast",
    "reaction",
    "shorts feed",
    "status",
]
TOPIC_QUERY_REFINEMENTS = {
    "communication": [
        "how to ask better questions",
        "speak clearly articulation exercises",
        "cross cultural communication examples",
        "communication skills practical examples under 5 minutes",
        "how to explain ideas clearly short lesson",
        "active listening communication skills short lesson",
        "body language communication tips under 3 minutes",
    ],
    "lifestyle": [
        "everyday english while cooking",
        "small habits for better daily routine short lesson",
        "simple life improvement habits under 5 minutes",
        "healthy daily routine practical tips short video",
        "minimal habits better lifestyle short lesson",
    ],
    "motivation": [
        "calm discipline advice short practical video",
        "self discipline practical tips under 5 minutes",
        "focus mindset short lesson no yelling",
        "motivation practical habit advice short video",
    ],
    "facts": [
        "interesting facts explained under 5 minutes",
        "science facts short animated explainer",
        "history facts explained short video",
        "fun facts educational shorts",
    ],
    "vocabulary": [
        "english expressions in real conversations",
        "everyday english while cooking",
        "english vocabulary daily conversation short lesson",
        "useful english phrases for daily life under 5 minutes",
        "english pronunciation vocabulary short lesson",
        "bbc learning english vocabulary short",
    ],
    "conversation_english": [
        "english expressions in real conversations",
        "everyday english while cooking",
        "speak clearly articulation exercises",
        "english speaking practice real life conversation under 5 minutes",
        "daily english conversation phrases short lesson",
        "speak english naturally common phrases short",
        "english conversation practice with subtitles short",
    ],
    "social_skills": [
        "body language explained simply",
        "cross cultural communication examples",
        "social skills practical tips under 5 minutes",
        "how to make better conversation short lesson",
        "confidence in social situations short tips",
        "first impression body language short lesson",
    ],
    "career": [
        "career mistakes in your 20s",
        "business vs job practical advice",
        "how to ask better questions",
        "career advice practical tips under 5 minutes",
        "work communication tips short lesson",
        "professional communication examples short video",
        "productivity at work practical tips short",
    ],
    "psychology": [
        "psychology explained with examples",
        "why people procrastinate psychology",
        "decision making cognitive biases",
        "human behavior psychology explained under 5 minutes",
        "psychology facts practical short explainer",
        "why people behave this way short psychology",
        "attention and habits psychology short video",
    ],
    "story": [
        "short historical stories with lessons",
        "short inspiring story with life lesson",
        "biography short story life lesson under 5 minutes",
        "animated short story meaningful lesson",
        "real life story lesson short video",
    ],
    "culture": [
        "cross cultural communication examples",
        "short historical stories with lessons",
        "world culture facts explained under 5 minutes",
        "interesting traditions around the world short",
        "language and culture explained short video",
        "history culture facts short educational video",
    ],
}
TOPIC_SOURCE_HINTS = {
    "communication": ["vinh giang", "think fast talk smart", "charisma on command", "max klymenko"],
    "facts": ["big think", "half as interesting", "asapscience", "ted-ed", "kurzgesagt"],
    "vocabulary": ["linguamarina", "english with lucy", "bbc learning english", "easy english", "speak english with vanessa"],
    "conversation_english": ["linguamarina", "english with lucy", "easy english", "speak english with vanessa"],
    "social_skills": ["charisma on command", "vinh giang", "science of people", "think fast talk smart"],
    "career": ["ali abdaal", "jeff su", "modern mba", "colin and samir", "dan koe"],
    "psychology": ["big think", "braincraft", "psych2go", "the school of life"],
    "story": ["great big story", "johnny harris", "ted-ed"],
    "culture": ["johnny harris", "soch by mohak mangal", "think school", "dhruv rathee", "aevy tv"],
}

HUMAN_LINK_INTENTS = {
    "english": {
        "label": "English",
        "queries": [
            "language exchange english speaking practice partner",
            "english conversation practice looking for partner",
            "english practice accountability partner",
        ],
        "subreddits": ["language_exchange", "EnglishLearning", "languagelearning"],
        "mastodon_tags": ["languageexchange", "languagelearning", "englishlearning"],
        "starter": "English practice",
        "opener": "Hey, I saw your public post about English practice. I am also looking for a low-pressure 10 minute practice chat. Would you be open to that?",
    },
    "friends": {
        "label": "Friends",
        "queries": [
            "looking for friends casual chat",
            "anyone want to talk make friends",
            "looking for conversation friend online",
        ],
        "subreddits": ["MakeNewFriendsHere", "Needafriend", "CasualConversation"],
        "mastodon_tags": ["makefriends"],
        "starter": "Casual chat",
        "opener": "Hey, I saw your public post and liked the vibe. I am looking for a simple, respectful conversation too. Would you be open to chatting for a bit?",
    },
    "study": {
        "label": "Study",
        "queries": [
            "looking for study partner accountability",
            "study buddy looking for partner",
            "anyone want to study together accountability",
        ],
        "subreddits": ["GetStudying", "study", "productivity"],
        "mastodon_tags": ["studybuddy", "studytogether"],
        "starter": "Study partner",
        "opener": "Hey, I saw your public post about studying. I am looking for a focused study/accountability partner too. Want to try one short session and see if it helps?",
    },
    "feedback": {
        "label": "Feedback",
        "queries": [
            "looking for feedback project",
            "need feedback on my idea",
            "would love feedback on this",
        ],
        "subreddits": ["SideProject", "Entrepreneur", "Design_Critiques"],
        "mastodon_tags": ["buildinpublic", "indiehackers", "feedback"],
        "hn_queries": ["Show HN feedback", "need feedback project"],
        "starter": "Feedback exchange",
        "opener": "Hey, I saw your public post asking for feedback. I can share one clear thought if useful. I would also enjoy exchanging feedback sometime.",
    },
    "accountability": {
        "label": "Accountability",
        "queries": [
            "looking for accountability partner",
            "accountability buddy goals",
            "daily accountability partner habits",
        ],
        "subreddits": ["GetMotivatedBuddies", "productivity", "DecidingToBeBetter"],
        "mastodon_tags": [],
        "hn_queries": ["accountability partner goals"],
        "starter": "Accountability",
        "opener": "Hey, I saw your public post about accountability. I am looking for a lightweight check-in setup too. Want to try a simple daily check-in for a few days?",
    },
    "career": {
        "label": "Career",
        "queries": [
            "career advice looking for mentor feedback",
            "resume feedback looking for advice",
            "interview practice partner",
        ],
        "subreddits": ["careerguidance", "resumes", "interviews"],
        "mastodon_tags": ["career", "jobsearch", "interview"],
        "hn_queries": ["career advice feedback mentor", "interview practice"],
        "starter": "Career chat",
        "opener": "Hey, I saw your public post about career advice. I am working on similar growth and would be happy to exchange one useful thought or practice together.",
    },
}
HUMAN_BAD_TERMS = [
    "18+",
    "adult",
    "betting",
    "boyfriend",
    "buy now",
    "crypto",
    "dating",
    "discount",
    "doj",
    "election",
    "free trial",
    "gambling",
    "girlfriend",
    "guarantee",
    "hookup",
    "investment",
    "nsfw",
    "onlyfans",
    "petition",
    "chemistry",
    "physics",
    "politic",
    "politics",
    "promote",
    "romance",
    "sale",
    "sext",
    "sponsored",
    "subscribe",
    "war",
    "zero risk",
]
HUMAN_OPEN_TERMS = [
    "accountability",
    "advice",
    "anyone",
    "buddy",
    "chat",
    "conversation",
    "exchange",
    "feedback",
    "friend",
    "introduction",
    "introductions",
    "looking for",
    "mentor",
    "partner",
    "practice",
    "study",
    "talk",
]
HUMAN_INTENT_TERMS = {
    "english": ["english", "language exchange", "languageexchange"],
    "friends": ["friend", "chat", "conversation", "talk", "introduction", "introductions", "casualconversation"],
    "study": ["study", "learn", "buddy", "partner", "studytogether"],
    "feedback": ["feedback", "critique", "review", "what do you think", "thoughts"],
    "accountability": ["accountability", "check-in", "goals", "habits", "partner"],
    "career": ["career", "resume", "interview", "mentor", "advice"],
}
HUMAN_LINK_MAX_AGE_HOURS = 24
HUMAN_LINK_HOT_AGE_HOURS = 8


class ClipError(Exception):
    pass


class HumanLinkError(Exception):
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


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_weighted_topics(value: str) -> dict[str, float]:
    topics: dict[str, float] = {}
    for raw_item in (value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" in item:
            key, raw_weight = item.split(":", 1)
            try:
                weight = clamp_float(float(raw_weight), -1.0, 1.0)
            except ValueError:
                continue
        else:
            key, weight = item, 1.0
        key = key.strip()
        if key in TOPIC_BY_KEY and weight > 0:
            topics[key] = max(topics.get(key, 0.0), weight)
    return topics


def parse_topic_list(value: str) -> set[str]:
    return {
        item.strip()
        for item in (value or "").split(",")
        if item.strip() in TOPIC_BY_KEY
    }


def parse_focus_term(value: str) -> str:
    term = re.sub(r"[^a-z0-9\s'-]+", " ", (value or "").lower())
    term = re.sub(r"\s+", " ", term).strip(" '-")
    if len(term) < 3 or len(term) > 96:
        return ""
    return term


def normalize_source_name(value: object) -> str:
    source = re.sub(r"[^a-z0-9&\s.'-]+", " ", str(value or "").lower())
    source = re.sub(r"\s+", " ", source).strip(" .'-")
    if len(source) < 2 or len(source) > 80:
        return ""
    return source


def unique_sources(values: list[object]) -> list[str]:
    seen = set()
    cleaned = []
    for value in values:
        source = normalize_source_name(value)
        if not source or source in seen:
            continue
        seen.add(source)
        cleaned.append(source)
    return cleaned


def normalize_source_tiers(raw_tiers: dict | None = None) -> dict[str, list[str]]:
    source_tiers = raw_tiers if isinstance(raw_tiers, dict) else SOURCE_TIERS
    assigned = set()
    normalized: dict[str, list[str]] = {tier: [] for tier in SOURCE_TIER_ORDER}
    for raw_key, values in source_tiers.items():
        tier = SOURCE_TIER_ALIASES.get(str(raw_key).lower())
        if tier not in normalized:
            continue
        value_list = values if isinstance(values, list) else str(values or "").split(",")
        for source in unique_sources(value_list):
            if source in assigned:
                continue
            assigned.add(source)
            normalized[tier].append(source)
    return normalized


def parse_source_tiers(values: list[str]) -> dict[str, list[str]]:
    if not values:
        return normalize_source_tiers()
    merged: dict[str, list[str]] = {}
    for raw_value in values:
        text = (raw_value or "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key, sources in parsed.items():
                    merged[key] = sources
                continue
        except json.JSONDecodeError:
            pass
        merged.setdefault("tier_1", []).extend(text.split(","))
    return normalize_source_tiers(merged)


def build_source_bonus_terms(source_tiers: dict[str, list[str]]) -> dict[str, int]:
    terms = {}
    for tier in SOURCE_TIER_ORDER:
        for source in source_tiers.get(tier, []):
            terms[source] = max(terms.get(source, 0), SOURCE_TIER_WEIGHTS[tier])
    return terms


def source_tier_label(tier: str) -> str:
    return {"tier_1": "Tier 1", "tier_2": "Tier 2", "tier_3": "Tier 3"}.get(tier, "Channel")


def flatten_source_tiers(source_tiers: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [
        (tier, source)
        for tier in SOURCE_TIER_ORDER
        for source in source_tiers.get(tier, [])
    ]


def source_match_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def build_channel_identity(source: str, title: str, channel_id: str, resolved_at: int | None = None) -> dict:
    return {
        "source": source,
        "title": title or source,
        "channelId": channel_id,
        "feedUrl": f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        "resolvedAt": int(time.time()) if resolved_at is None else resolved_at,
    }


def get_static_channel_identity(source: str) -> dict | None:
    key = source_match_key(source)
    item = STATIC_CHANNEL_IDENTITIES.get(key)
    if not item:
        return None
    title, channel_id = item
    return build_channel_identity(source, title, channel_id, resolved_at=0)


def source_match(channel: str, source: str) -> bool:
    channel_key = source_match_key(channel)
    source_key = source_match_key(source)
    if not channel_key or not source_key:
        return False
    return channel_key == source_key or source_key in channel_key or channel_key in source_key


def matched_source_tier(channel: str, source_tiers: dict[str, list[str]]) -> tuple[str, str] | None:
    for tier, source in flatten_source_tiers(source_tiers):
        if source_match(channel, source):
            return tier, source
    return None


def find_configured_source(
    source_tiers: dict[str, list[str]],
    source_name: str,
    tier_hint: str = "",
) -> tuple[str, str] | None:
    source = normalize_source_name(source_name)
    if not source:
        return None
    tiers = [tier_hint] if tier_hint in SOURCE_TIER_ORDER else []
    tiers.extend(tier for tier in SOURCE_TIER_ORDER if tier not in tiers)
    for tier in tiers:
        for configured_source in source_tiers.get(tier, []):
            if source_match(configured_source, source):
                return tier, configured_source
    return None


def choose_channel_sources(
    source_tiers: dict[str, list[str]],
    count: int,
    preferred_source: str = "",
    preferred_tier: str = "",
) -> list[tuple[str, str]]:
    pool = flatten_source_tiers(source_tiers)
    random.shuffle(pool)
    selected: list[tuple[str, str]] = []
    preferred = find_configured_source(source_tiers, preferred_source, preferred_tier)
    if preferred:
        selected.append(preferred)
        preferred_key = (preferred[0], source_match_key(preferred[1]))
        pool = [
            item for item in pool
            if (item[0], source_match_key(item[1])) != preferred_key
        ]
    while pool and len(selected) < count:
        weights = [SOURCE_TIER_WEIGHTS.get(tier, 1) for tier, _source in pool]
        item = random.choices(pool, weights=weights, k=1)[0]
        selected.append(item)
        pool.remove(item)
    return selected


def ranked_sources_for_topic(topic_key: str, source_tiers: dict[str, list[str]]) -> list[str]:
    all_sources = [source for tier in SOURCE_TIER_ORDER for source in source_tiers.get(tier, [])]
    topic_hints = TOPIC_SOURCE_HINTS.get(topic_key, [])
    ranked = [source for source in topic_hints if source in all_sources]
    ranked.extend(source for source in all_sources if source not in ranked)
    return ranked


def parse_clip_taste_hints(query: dict[str, list[str]]) -> dict:
    topics = parse_weighted_topics(",".join(query.get("topics", [])))
    avoid_topics = parse_topic_list(",".join(query.get("avoidTopics", [])))
    duration = (query.get("duration", [""])[0] or "").strip().lower()
    explore = (query.get("explore", ["explore"])[0] or "explore").strip().lower()
    focus = parse_focus_term(query.get("focus", [""])[0])
    focus_mode = (query.get("focusMode", ["include"])[0] or "include").strip().lower()
    source_tiers = parse_source_tiers(query.get("sourceTiers", []))
    continuity_source = normalize_source_name(query.get("continuitySource", [""])[0])
    continuity_tier = SOURCE_TIER_ALIASES.get(
        (query.get("continuityTier", [""])[0] or "").strip().lower(),
        "",
    )
    continuity_match = find_configured_source(source_tiers, continuity_source, continuity_tier)
    if duration not in DURATION_CHOICES:
        duration = ""
    if explore not in EXPLORE_CHOICES:
        explore = "explore"
    if focus_mode not in {"include", "avoid"}:
        focus_mode = "include"
    return {
        "topics": topics,
        "avoidTopics": avoid_topics,
        "duration": duration,
        "explore": explore,
        "focus": focus,
        "focusMode": focus_mode,
        "sourceTiers": source_tiers,
        "continuitySource": continuity_match[1] if continuity_match else "",
        "continuityTier": continuity_match[0] if continuity_match else "",
        "sourceBonusTerms": build_source_bonus_terms(source_tiers),
        "hasHints": bool(topics or avoid_topics or duration or focus or explore != "explore"),
    }


def duration_band(seconds: int) -> str:
    if seconds <= 90:
        return "short"
    if seconds <= 240:
        return "medium"
    return "long"


def pick_topic(taste_hints: dict | None = None) -> dict:
    hints = taste_hints or {}
    explore = hints.get("explore", "explore")
    positive = hints.get("topics") or {}
    avoid = hints.get("avoidTopics") or set()

    if positive and explore == "close":
        pool = [
            TOPIC_BY_KEY[key]
            for key in positive
            if key in TOPIC_BY_KEY and key not in avoid
        ]
        if pool:
            weights = [max(0.2, float(positive.get(topic["key"], 0.0))) for topic in pool]
            return random.choices(pool, weights=weights, k=1)[0]

    explore_chance = {"close": 0.15, "explore": 0.35, "surprise": 0.7}.get(explore, 0.35)
    if not positive or random.random() < explore_chance:
        pool = [topic for topic in TOPICS if topic["key"] not in avoid] or TOPICS
        return random.choice(pool)

    weights = []
    for topic in TOPICS:
        key = topic["key"]
        weight = 1.0 + max(0.0, float(positive.get(key, 0.0))) * (5.0 if explore == "close" else 3.0)
        if key in avoid:
            weight *= 0.18 if explore == "close" else 0.35
        weights.append(max(0.05, weight))
    return random.choices(TOPICS, weights=weights, k=1)[0]


def load_history() -> list[str]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        items = data.get("videoIds", []) if isinstance(data, dict) else data
        return unique_video_ids(items if isinstance(items, list) else [])
    except Exception:
        return []


def unique_video_ids(video_ids: list[object]) -> list[str]:
    seen = set()
    cleaned = []
    for item in video_ids:
        video_id = str(item or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,32}", video_id):
            continue
        if video_id in seen:
            continue
        seen.add(video_id)
        cleaned.append(video_id)
    return cleaned


def save_history(video_ids: list[str]) -> None:
    cleaned = unique_video_ids(video_ids)
    payload = {"videoIds": cleaned, "count": len(cleaned), "savedAt": int(time.time())}
    HISTORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_cache_target_size() -> int:
    try:
        return max(1, min(80, int(os.environ.get("CLIP_MIX_CACHE_SIZE", "32"))))
    except ValueError:
        return 32


def get_prefetch_interval_seconds() -> int:
    try:
        return max(300, int(os.environ.get("CLIP_MIX_PREFETCH_SECONDS", "900")))
    except ValueError:
        return 900


def get_initial_prefetch_delay_seconds() -> int:
    try:
        return max(0, int(os.environ.get("CLIP_MIX_PREFETCH_START_DELAY_SECONDS", "0")))
    except ValueError:
        return 0


def get_clip_search_attempt_count() -> int:
    try:
        return max(1, min(8, int(os.environ.get("CLIP_MIX_SEARCH_ATTEMPTS", "5"))))
    except ValueError:
        return 5


def get_clip_search_worker_count() -> int:
    try:
        return max(1, min(6, int(os.environ.get("CLIP_MIX_SEARCH_WORKERS", "4"))))
    except ValueError:
        return 4


def get_clip_direct_http_timeout() -> int:
    try:
        return max(2, min(20, int(os.environ.get("CLIP_MIX_HTTP_TIMEOUT_SECONDS", "4"))))
    except ValueError:
        return 4


def get_clip_realtime_budget_seconds() -> float:
    try:
        return max(0.5, min(8.0, float(os.environ.get("CLIP_MIX_REALTIME_BUDGET_SECONDS", "2.5"))))
    except ValueError:
        return 2.5


def get_clip_direct_http_read_limit() -> int:
    try:
        return max(250_000, min(6_000_000, int(os.environ.get("CLIP_MIX_HTTP_READ_BYTES", "2500000"))))
    except ValueError:
        return 2_500_000


def get_extra_cache_per_search() -> int:
    try:
        return max(0, min(80, int(os.environ.get("CLIP_MIX_EXTRA_CACHE_PER_SEARCH", str(get_cache_target_size())))))
    except ValueError:
        return get_cache_target_size()


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


def clip_matches_source(clip: dict, source: str) -> bool:
    if not source:
        return True
    return (
        source_match(clip.get("query", ""), source)
        or source_match(clip.get("source", ""), source)
    )


def clip_matches_taste_hints(clip: dict, taste_hints: dict | None = None) -> bool:
    source_tiers = (taste_hints or {}).get("sourceTiers") or normalize_source_tiers()
    continuity_source = (taste_hints or {}).get("continuitySource") or ""
    if continuity_source and not clip_matches_source(clip, continuity_source):
        return False
    return bool(matched_source_tier(clip.get("source", ""), source_tiers))


def pop_cached_clip(avoid_ids: set[str], taste_hints: dict | None = None) -> tuple[dict, dict] | None:
    continuity_source = (taste_hints or {}).get("continuitySource") or ""
    with CLIP_CACHE_LOCK:
        items = load_clip_cache_unlocked()
        for index, item in enumerate(items):
            clip = item.get("clip", {})
            item_meta = item.get("meta", {})
            video_id = clip.get("videoId")
            if not continuity_source and item_meta.get("continuitySource"):
                continue
            if video_id and video_id not in avoid_ids and clip_matches_taste_hints(clip, taste_hints):
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


def term_hit_score(text: str, weighted_terms: dict[str, int]) -> int:
    lowered = text.lower()
    return sum(weight for term, weight in weighted_terms.items() if term in lowered)


def count_term_hits(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def unique_queries(queries: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for query in queries:
        query = re.sub(r"\s+", " ", query).strip()
        if not query:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(query)
    return cleaned


def query_has_duration_hint(query: str) -> bool:
    return bool(re.search(
        r"\b(?:under|over)\s+\d+\s+(?:seconds?|minutes?)\b|\b\d+\s*(?:to|-)\s*\d+\s+minutes?\b|\b\d+\s*(?:min|mins?)\b",
        query.lower(),
    ))


def build_clip_queries(topic: dict, taste_hints: dict | None = None) -> list[str]:
    hints = taste_hints or {}
    focus = hints.get("focus", "")
    focus_mode = hints.get("focusMode", "include")
    duration = hints.get("duration", "")
    duration_phrase = {
        "short": "under 90 seconds",
        "medium": "2 to 4 minutes",
        "long": "under 8 minutes",
    }.get(duration, "2 to 8 minutes")

    base_queries = list(TOPIC_QUERY_REFINEMENTS.get(topic["key"], [])) + list(topic.get("queries", []))
    random.shuffle(base_queries)

    queries = []
    for base in base_queries:
        query = base if query_has_duration_hint(base) else f"{base} {duration_phrase}"
        if topic.get("captions"):
            query = f"{query} subtitles"
        queries.append(query)
        if random.random() < 0.45:
            queries.append(f"{query} #shorts")

    source_queries = [
        f"{source} {topic['label']} short lesson {duration_phrase}"
        for source in ranked_sources_for_topic(topic["key"], hints.get("sourceTiers") or SOURCE_TIERS)[:3]
    ]
    if source_queries:
        queries = source_queries[:1] + queries + source_queries[1:]

    if focus and focus_mode == "include":
        focused = [f"{focus} {query}" for query in queries[:6]]
        queries = focused + queries

    if focus and focus_mode == "avoid":
        queries = [f"{query} -{focus}" for query in queries]

    return unique_queries(queries)


def build_chatgpt_prompt_url(prompt: str) -> str:
    try:
        limit = max(800, min(6000, int(os.environ.get("OPENAI_WEB_PROMPT_CHARS", "3500"))))
    except ValueError:
        limit = 3500
    prompt = compact_text(prompt, limit)
    return "https://chatgpt.com/?" + urllib.parse.urlencode({"q": prompt})


def launch_chatgpt_prompt(prompt: str) -> str:
    url = build_chatgpt_prompt_url(prompt)
    chrome = os.environ.get("OPENAI_WEB_CHROME") or os.environ.get("CLIP_MIX_CHROME", "google-chrome")
    command = [chrome, "--new-window", url]
    subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return url


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


def browse_id_from_runs(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    runs = value.get("runs")
    if isinstance(runs, list):
        for run in runs:
            browse_id = (
                run.get("navigationEndpoint", {})
                .get("browseEndpoint", {})
                .get("browseId", "")
            ) if isinstance(run, dict) else ""
            if isinstance(browse_id, str) and browse_id.startswith("UC"):
                return browse_id
    browse_id = (
        value.get("navigationEndpoint", {})
        .get("browseEndpoint", {})
        .get("browseId", "")
    )
    return browse_id if isinstance(browse_id, str) and browse_id.startswith("UC") else ""


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
    channel_id = (
        browse_id_from_runs(renderer.get("ownerText"))
        or browse_id_from_runs(renderer.get("longBylineText"))
        or browse_id_from_runs(renderer.get("shortBylineText"))
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
        "channelId": channel_id,
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


def collect_channel_renderers(value: object, candidates: list[dict]) -> None:
    if isinstance(value, list):
        for item in value:
            collect_channel_renderers(item, candidates)
        return
    if not isinstance(value, dict):
        return

    renderer = value.get("channelRenderer")
    if isinstance(renderer, dict):
        channel_id = renderer.get("channelId") or (
            renderer.get("navigationEndpoint", {})
            .get("browseEndpoint", {})
            .get("browseId", "")
        )
        title = text_from_runs(renderer.get("title"))
        if isinstance(channel_id, str) and channel_id.startswith("UC") and title:
            candidates.append({"channelId": channel_id, "title": title})

    for child in value.values():
        collect_channel_renderers(child, candidates)


def extract_channel_candidates(dom: str) -> list[dict]:
    candidates = []
    initial_data = extract_initial_data(dom)
    if initial_data:
        collect_channel_renderers(initial_data, candidates)
        for video in extract_video_candidates(dom):
            channel_id = video.get("channelId")
            source = video.get("source", "")
            if isinstance(channel_id, str) and channel_id.startswith("UC") and source:
                candidates.append({"channelId": channel_id, "title": source})

    deduped = []
    seen = set()
    for candidate in candidates:
        channel_id = candidate.get("channelId")
        if not channel_id or channel_id in seen:
            continue
        seen.add(channel_id)
        deduped.append(candidate)
    return deduped


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


def load_channel_cache_unlocked() -> dict:
    try:
        data = json.loads(CHANNEL_CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_channel_cache_unlocked(cache: dict) -> None:
    CHANNEL_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def get_cached_channel_identity(source: str) -> dict | None:
    static_identity = get_static_channel_identity(source)
    if static_identity:
        return static_identity

    key = source_match_key(source)
    if not key:
        return None
    with CHANNEL_CACHE_LOCK:
        item = load_channel_cache_unlocked().get(key)
    if not isinstance(item, dict) or not str(item.get("channelId", "")).startswith("UC"):
        return None
    return item


def store_channel_identity(source: str, identity: dict) -> dict:
    key = source_match_key(source)
    channel_id = identity.get("channelId", "")
    if not key or not isinstance(channel_id, str) or not channel_id.startswith("UC"):
        return identity
    clean = {
        **build_channel_identity(source, identity.get("title") or source, channel_id),
    }
    with CHANNEL_CACHE_LOCK:
        cache = load_channel_cache_unlocked()
        cache[key] = clean
        save_channel_cache_unlocked(cache)
    return clean


def resolve_channel_identity(source: str) -> dict | None:
    cached = get_cached_channel_identity(source)
    if cached:
        return cached

    dom = load_youtube_search_dom_http(source)
    candidates = extract_channel_candidates(dom)
    if not candidates:
        return None

    best = next(
        (candidate for candidate in candidates if source_match(candidate.get("title", ""), source)),
        candidates[0],
    )
    return store_channel_identity(source, best)


def trigger_channel_identity_resolution(source: str) -> None:
    key = source_match_key(source)
    if not key or get_cached_channel_identity(source):
        return
    with CHANNEL_CACHE_LOCK:
        if key in CHANNEL_RESOLVE_PENDING:
            return
        CHANNEL_RESOLVE_PENDING.add(key)

    def run() -> None:
        try:
            resolve_channel_identity(source)
        except Exception as err:
            print(f"Clip Mix channel resolve skipped for {source}: {err}")
        finally:
            with CHANNEL_CACHE_LOCK:
                CHANNEL_RESOLVE_PENDING.discard(key)

    threading.Thread(target=run, name=f"clip-channel-resolve-{key[:24]}", daemon=True).start()


def load_youtube_rss_candidates(source: str, resolve_missing: bool = False) -> list[dict]:
    identity = resolve_channel_identity(source) if resolve_missing else get_cached_channel_identity(source)
    if not identity:
        trigger_channel_identity_resolution(source)
        return []
    request = urllib.request.Request(
        identity["feedUrl"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=get_clip_direct_http_timeout()) as response:
            raw_xml = response.read(get_clip_direct_http_read_limit())
    except urllib.error.HTTPError as err:
        raise ClipError(f"YouTube RSS returned HTTP {err.code} for {source}.") from err
    except urllib.error.URLError as err:
        raise ClipError(f"YouTube RSS is unreachable for {source}: {err.reason}") from err
    except TimeoutError as err:
        raise ClipError(f"YouTube RSS timed out for {source}.") from err

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as err:
        raise ClipError(f"YouTube RSS could not be parsed for {source}.") from err

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    candidates = []
    for entry in root.findall("atom:entry", ns):
        video_id = (entry.findtext("yt:videoId", default="", namespaces=ns) or "").strip()
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        author = (
            entry.findtext("atom:author/atom:name", default="", namespaces=ns)
            or identity.get("title")
            or source
        )
        description = entry.findtext("media:group/media:description", default="", namespaces=ns) or ""
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        if not video_id or not title:
            continue
        candidates.append({
            "videoId": video_id,
            "title": html_lib.unescape(title),
            "source": html_lib.unescape(author),
            "channelId": identity.get("channelId", ""),
            "description": compact_text(html_lib.unescape(description), 260),
            "durationSeconds": 600,
            "durationEstimated": True,
            "viewCount": 0,
            "isShorts": "#shorts" in f"{title} {description}".lower() or " shorts" in f"{title} {description}".lower(),
            "published": published,
        })
    return candidates


def load_youtube_search_dom_http(query: str) -> str:
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": query}
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Cookie": "CONSENT=YES+cb",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=get_clip_direct_http_timeout()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read(get_clip_direct_http_read_limit()).decode(charset, errors="replace")
    except urllib.error.HTTPError as err:
        raise ClipError(f"YouTube HTTP search returned HTTP {err.code}.") from err
    except urllib.error.URLError as err:
        raise ClipError(f"YouTube HTTP search is unreachable: {err.reason}") from err
    except TimeoutError as err:
        raise ClipError("YouTube HTTP search timed out.") from err


def load_youtube_search_dom(query: str) -> str:
    http_error = ""
    if os.environ.get("CLIP_MIX_DIRECT_HTTP", "1") != "0":
        try:
            dom = load_youtube_search_dom_http(query)
            if "ytInitialData" in dom and '"videoId"' in dom:
                return dom
            if re.search(r"(?:/watch\?v=|/shorts/)[A-Za-z0-9_-]{11}", dom):
                return dom
            http_error = "YouTube HTTP search returned no parseable videos."
        except ClipError as err:
            http_error = str(err)

    chrome = os.environ.get("CLIP_MIX_CHROME", "google-chrome")
    budget_ms = os.environ.get("CLIP_MIX_HEADLESS_BUDGET_MS", "5000")
    try:
        int(budget_ms)
    except ValueError:
        budget_ms = "5000"

    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": query}
    )
    with tempfile.TemporaryDirectory(prefix="clip-mix-chrome-", ignore_cleanup_errors=True) as profile_dir:
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
        detail = f" Direct HTTP fallback failed first: {http_error}" if http_error else ""
        raise ClipError(f"{message[0]}{detail}")
    return result.stdout


def score_video(item: dict, topic: dict | None, query: str, taste_hints: dict | None = None) -> tuple[int, dict] | None:
    title = item.get("title", "")
    description = item.get("description", "")
    channel = item.get("source", "")
    video_id = item.get("videoId", "")
    text = f"{title} {description} {channel}"
    seconds = int(item.get("durationSeconds") or 0)
    is_shorts = bool(item.get("isShorts"))
    source_tiers = (taste_hints or {}).get("sourceTiers") or normalize_source_tiers()
    matched_source = matched_source_tier(channel, source_tiers)

    if not video_id:
        return None
    if not matched_source:
        return None
    if title.strip().lower() in {"youtube clip", "youtube shorts pick"} and not description.strip():
        return None
    if not is_shorts and (seconds < 18 or seconds > 1800):
        return None
    if is_shorts and seconds <= 0:
        seconds = 60
    if seconds > 1800:
        return None
    if contains_bad_term(text):
        return None

    lowered = text.lower()
    tier, configured_source = matched_source
    score = 60 + SOURCE_TIER_WEIGHTS.get(tier, 0)
    low_quality_hits = count_term_hits(lowered, LOW_QUALITY_TERMS)
    watch_bait_hits = count_term_hits(lowered, WATCH_BAIT_TERMS)
    if low_quality_hits >= 2:
        return None
    score -= low_quality_hits * 18
    score -= watch_bait_hits * 7
    score -= count_term_hits(title.lower(), TITLE_PENALTY_TERMS) * 10
    score -= count_term_hits(lowered, FAST_CUT_PENALTY_TERMS) * 12
    score -= count_term_hits(channel, SOURCE_PENALTY_TERMS) * 12

    if len(title.strip()) < 12:
        score -= 8
    if re.search(r"\b(part|pt)\s*\d+\b", lowered):
        score -= 12

    if seconds <= 60:
        score -= 2
    elif seconds <= 480:
        score += 12
    elif seconds <= 900:
        score += 8
    elif seconds > 1200:
        score -= 8

    if is_shorts or "#shorts" in lowered or "shorts" in lowered:
        score -= 3

    views = int(item.get("viewCount") or 0)
    if views:
        score += min(18, int(math.log10(max(views, 1)) * 4))
        if views < 1_000:
            score -= 10

    score += random.randint(0, 10)
    if score < 38:
        return None

    clip = {
        "title": compact_text(title, 90),
        "source": channel or "YouTube",
        "videoId": video_id,
        "start": 0,
        "end": min(seconds, 1800),
        "category": "Channel Pick",
        "description": compact_text(description)
        or f"A video from {channel or configured_source} discovered from your channel list.",
        "tags": [
            source_tier_label(tier),
            configured_source.title(),
            "Recent" if item.get("durationEstimated") else format_duration(seconds),
        ],
        "durationSeconds": seconds,
        "query": query,
        "tier": tier,
        "channelId": item.get("channelId", ""),
        "searchedAt": int(time.time()),
    }
    return score, clip


def pick_weighted(scored: list[tuple[int, dict]]) -> dict:
    scored = sorted(scored, key=lambda pair: pair[0], reverse=True)[:10]
    weights = [max(1, score - 35) for score, _clip in scored]
    return random.choices([clip for _score, clip in scored], weights=weights, k=1)[0]


def load_channel_candidates(
    channel_source: tuple[int, str],
    allow_slow_fallback: bool = False,
) -> tuple[int, str, list[dict]]:
    query_index, source = channel_source
    try:
        rss_candidates = load_youtube_rss_candidates(source)
        if rss_candidates:
            return query_index, source, rss_candidates
    except ClipError:
        pass

    if not allow_slow_fallback:
        return query_index, source, []

    try:
        rss_candidates = load_youtube_rss_candidates(source, resolve_missing=True)
        if rss_candidates:
            return query_index, source, rss_candidates
    except ClipError:
        pass

    dom = load_youtube_search_dom(source)
    return query_index, source, extract_video_candidates(dom)


def store_discovered_extras(
    scored: list[tuple[int, dict]],
    selected_video_id: str,
    meta: dict,
    avoid_ids: set[str],
) -> None:
    limit = get_extra_cache_per_search()
    if limit <= 0:
        return
    blocked = set(avoid_ids) | set(load_history()) | get_cached_video_ids() | {selected_video_id}
    stored = 0
    for score, clip in sorted(scored, key=lambda pair: pair[0], reverse=True):
        video_id = clip.get("videoId")
        if not video_id or video_id in blocked:
            continue
        store_cached_clip(
            clip,
            {
                **meta,
                "prefetched": True,
                "extraCandidate": True,
                "score": score,
                "query": clip.get("query") or meta.get("query", ""),
            },
        )
        blocked.add(video_id)
        stored += 1
        if stored >= limit:
            return


def search_fresh_clip(
    avoid_ids: set[str],
    remember: bool = True,
    taste_hints: dict | None = None,
) -> tuple[dict, dict]:
    history = load_history()
    avoid = set(history) | avoid_ids
    source_tiers = (taste_hints or {}).get("sourceTiers") or normalize_source_tiers()
    continuity_source = (taste_hints or {}).get("continuitySource") or ""
    continuity_tier = (taste_hints or {}).get("continuityTier") or ""
    attempts = get_clip_search_attempt_count()
    channel_sources = choose_channel_sources(
        source_tiers,
        attempts,
        preferred_source=continuity_source,
        preferred_tier=continuity_tier,
    )
    if not channel_sources:
        raise ClipError("No channel tiers configured for Clip Mix.")

    queries = [source for _tier, source in channel_sources]
    scored = []
    candidate_records = []
    seen_video_ids = set()
    search_errors = []
    indexed_sources = [(index, source) for index, (_tier, source) in enumerate(channel_sources)]
    worker_count = min(len(indexed_sources), get_clip_search_worker_count())

    def handle_candidates(query_index: int, query: str, candidates: list[dict]) -> None:
        candidate_records.extend((candidate, query, query_index) for candidate in candidates)
        for candidate in candidates:
            video_id = candidate.get("videoId")
            if not video_id or video_id in avoid or video_id in seen_video_ids:
                continue
            scored_item = score_video(candidate, None, query, taste_hints)
            if scored_item:
                score, clip_item = scored_item
                scored.append((score - query_index * 2, clip_item))
                seen_video_ids.add(video_id)

    if worker_count <= 1:
        for query_index, source in indexed_sources:
            try:
                query_index, query, candidates = load_channel_candidates((query_index, source))
                handle_candidates(query_index, query, candidates)
                if scored:
                    break
            except ClipError as err:
                search_errors.append(str(err))
    else:
        executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="clip-search")
        futures = {
            executor.submit(load_channel_candidates, source_item): source_item
            for source_item in indexed_sources
        }
        pending = set(futures)
        deadline = time.monotonic() + get_clip_realtime_budget_seconds()
        try:
            while pending:
                timeout = max(0.05, deadline - time.monotonic())
                done, pending = wait(pending, timeout=timeout, return_when=FIRST_COMPLETED)
                if not done:
                    break
                for future in done:
                    try:
                        query_index, query, candidates = future.result()
                        handle_candidates(query_index, query, candidates)
                    except ClipError as err:
                        search_errors.append(str(err))
                if scored and (len(scored) >= 8 or time.monotonic() >= deadline):
                    break
        finally:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    if not candidate_records:
        for query_index, source in indexed_sources[: max(1, min(2, len(indexed_sources)))]:
            try:
                query_index, query, candidates = load_channel_candidates((query_index, source), allow_slow_fallback=True)
                handle_candidates(query_index, query, candidates)
                if scored:
                    break
            except ClipError as err:
                search_errors.append(str(err))

    if not candidate_records and search_errors:
        raise ClipError(search_errors[-1])
    if not candidate_records:
        raise ClipError("Headless YouTube search returned no videos.")

    if not scored:
        for candidate, query, query_index in candidate_records:
            video_id = candidate.get("videoId")
            if not video_id or video_id in avoid or video_id in seen_video_ids:
                continue
            scored_item = score_video(candidate, None, query, taste_hints)
            if scored_item:
                score, clip_item = scored_item
                scored.append((score - query_index * 2, clip_item))
                seen_video_ids.add(video_id)
    if not scored:
        raise ClipError("No search results passed the Clip Mix filters.")

    continuity_matched = []
    if continuity_source:
        continuity_matched = [
            (score + 80, clip_item)
            for score, clip_item in scored
            if clip_matches_source(clip_item, continuity_source)
        ]
        if continuity_matched:
            scored = continuity_matched

    clip = pick_weighted(scored)
    if remember:
        history.append(clip["videoId"])
        save_history(history)
    meta = {
        "source": clip.get("source", ""),
        "tier": clip.get("tier", ""),
        "query": clip.get("query") or queries[0],
        "queriesTried": queries,
        "mode": "channel-youtube",
        "candidateCount": len(scored),
        "sourceCount": sum(len(sources) for sources in source_tiers.values()),
        "continuitySource": continuity_source,
        "continuityMatched": bool(continuity_matched),
    }
    store_discovered_extras(scored, clip["videoId"], meta, avoid)
    return clip, meta


def prefill_clip_cache(taste_hints: dict | None = None) -> None:
    target = get_cache_target_size()
    for _attempt in range(target):
        with CLIP_CACHE_LOCK:
            cache_items = load_clip_cache_unlocked()
            cache_count = sum(
                1
                for item in cache_items
                if clip_matches_taste_hints(item.get("clip", {}), taste_hints)
            )
            cache_ids = {
                item.get("clip", {}).get("videoId")
                for item in cache_items
                if item.get("clip", {}).get("videoId")
            }
        if cache_count >= target:
            return

        avoid_ids = set(load_history()) | cache_ids
        try:
            clip, meta = search_fresh_clip(avoid_ids, remember=False, taste_hints=taste_hints)
        except ClipError as err:
            print(f"Clip Mix prefetch skipped: {err}")
            return
        store_cached_clip(clip, {**meta, "prefetched": True})


def trigger_prefetch(reason: str = "cache-low", taste_hints: dict | None = None) -> None:
    with CLIP_CACHE_LOCK:
        if PREFETCH_STATE["running"]:
            return
        PREFETCH_STATE["running"] = True

    def run() -> None:
        try:
            print(f"Clip Mix prefetch start: {reason}")
            prefill_clip_cache(taste_hints)
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


def fetch_clip(avoid_ids: set[str], taste_hints: dict | None = None) -> tuple[dict, dict]:
    avoid = set(load_history()) | avoid_ids
    cached = pop_cached_clip(avoid, taste_hints)
    if cached:
        clip, meta = cached
        history = load_history()
        history.append(clip["videoId"])
        save_history(history)
        if meta.get("cacheRemaining", 0) < max(2, get_cache_target_size() // 2):
            trigger_prefetch("cache-low", taste_hints)
        return clip, meta

    clip, meta = search_fresh_clip(avoid, remember=True, taste_hints=taste_hints)
    trigger_prefetch("post-live-search", taste_hints)
    return clip, {**meta, "cached": False}


def strip_markup(value: object, limit: int = 260) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return compact_text(text, limit)


def human_intent_config(intent_key: str) -> tuple[str, dict]:
    key = intent_key if intent_key in HUMAN_LINK_INTENTS else "english"
    return key, HUMAN_LINK_INTENTS[key]


def http_get_json(url: str, timeout: int = 9) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RamanOSDashboard/1.0 public-conversation-radar",
            "Accept": "application/json,text/plain;q=0.8,*/*;q=0.6",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(900_000)
            return json.loads(raw.decode(charset, errors="replace"))
    except urllib.error.HTTPError as err:
        host = urllib.parse.urlparse(url).netloc
        raise HumanLinkError(f"{host} returned HTTP {err.code}") from err
    except urllib.error.URLError as err:
        host = urllib.parse.urlparse(url).netloc
        raise HumanLinkError(f"{host} is unreachable: {err.reason}") from err


def format_relative_age(timestamp: object) -> str:
    try:
        created = float(timestamp)
    except (TypeError, ValueError):
        return "Recent"
    delta = max(0, int(time.time() - created))
    if delta < 3600:
        return f"{max(1, delta // 60)}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    if delta < 604800:
        return f"{delta // 86400}d ago"
    return time.strftime("%b %d", time.localtime(created))


def get_human_max_age_seconds() -> int:
    try:
        hours = int(os.environ.get("HUMAN_LINK_MAX_AGE_HOURS", str(HUMAN_LINK_MAX_AGE_HOURS)))
    except ValueError:
        hours = HUMAN_LINK_MAX_AGE_HOURS
    return max(1, hours) * 3600


def get_human_hot_age_seconds() -> int:
    try:
        hours = int(os.environ.get("HUMAN_LINK_HOT_AGE_HOURS", str(HUMAN_LINK_HOT_AGE_HOURS)))
    except ValueError:
        hours = HUMAN_LINK_HOT_AGE_HOURS
    return max(1, hours) * 3600


def human_timestamp_age_seconds(timestamp: object) -> int | None:
    try:
        created = float(timestamp)
    except (TypeError, ValueError):
        return None
    return max(0, int(time.time() - created))


def human_timestamp_is_fresh(timestamp: object) -> bool:
    age_seconds = human_timestamp_age_seconds(timestamp)
    return age_seconds is not None and age_seconds <= get_human_max_age_seconds()


def parse_iso_timestamp(value: object) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def human_has_term(lowered_text: str, term: str) -> bool:
    normalized = term.lower()
    if " " in normalized or "-" in normalized:
        return normalized in lowered_text
    pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
    return re.search(pattern, lowered_text) is not None


def human_lead_allowed(text: str, intent_key: str | None = None) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in HUMAN_BAD_TERMS):
        return False
    required_terms = HUMAN_INTENT_TERMS.get(intent_key or "")
    if required_terms and not any(human_has_term(lowered, term) for term in required_terms):
        return False
    return any(human_has_term(lowered, term) for term in HUMAN_OPEN_TERMS)


def human_signal(text: str) -> str:
    lowered = text.lower()
    if "language exchange" in lowered or "english" in lowered:
        return "Practice signal"
    if "accountability" in lowered or "check-in" in lowered:
        return "Check-in signal"
    if "feedback" in lowered or "critique" in lowered or "review" in lowered:
        return "Feedback signal"
    if "study" in lowered or "buddy" in lowered:
        return "Partner signal"
    if "looking for" in lowered or "anyone" in lowered:
        return "Open invite"
    return "Public opening"


def human_lead_score(lead: dict) -> int:
    text = f"{lead.get('title', '')} {lead.get('summary', '')}".lower()
    score = 20 + random.randint(0, 8)
    age_seconds = human_timestamp_age_seconds(lead.get("_created"))
    if age_seconds is not None:
        score += max(0, 26 - int(age_seconds / 3600))
        if age_seconds <= get_human_hot_age_seconds():
            score += 18
    for term in HUMAN_OPEN_TERMS:
        if human_has_term(text, term):
            score += 5
    if human_has_term(text, "looking for"):
        score += 8
    if lead.get("platform") == "Reddit":
        score += 4
    if lead.get("platform") == "HN":
        score += 5
    if lead.get("intent") in {"feedback", "career"} and lead.get("platform") == "HN":
        score += 8
    return score


def build_human_opener(config: dict, lead: dict) -> str:
    if config.get("opener"):
        title = compact_text(lead.get("title", ""), 68)
        return config["opener"].replace("your public post", f'your public post "{title}"')
    title = compact_text(lead.get("title", "conversation"), 68)
    label = config["label"].lower()
    return (
        f'Hey, I saw your public post "{title}". I am also looking for a '
        f"low-pressure {label} conversation. Would you be open to a short chat?"
    )


def make_reddit_search_url(query: str, subreddit: str | None = None) -> str:
    if subreddit:
        base = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "restrict_sr": "on", "sort": "new", "t": "day", "limit": "8"}
    else:
        base = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": "new", "t": "day", "limit": "10"}
    return base + "?" + urllib.parse.urlencode(params)


def fetch_reddit_human_leads(intent_key: str, config: dict) -> list[dict]:
    queries = config.get("queries", [])
    if not queries:
        return []

    urls = []
    subreddits = config.get("subreddits", [])[:2]
    for subreddit in subreddits:
        urls.append(make_reddit_search_url(random.choice(queries), subreddit))
    urls.append(make_reddit_search_url(random.choice(queries)))

    leads = []
    for url in urls:
        data = http_get_json(url)
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {}) if isinstance(child, dict) else {}
            if post.get("over_18") or post.get("stickied"):
                continue
            created = post.get("created_utc")
            if not human_timestamp_is_fresh(created):
                continue
            title = strip_markup(post.get("title"), 120)
            summary = strip_markup(post.get("selftext") or post.get("selftext_html"), 260)
            full_text = f"{title} {summary}"
            if not title or not human_lead_allowed(full_text, intent_key):
                continue
            permalink = post.get("permalink") or ""
            post_url = (
                f"https://www.reddit.com{permalink}"
                if permalink.startswith("/")
                else f"https://www.reddit.com/r/{post.get('subreddit', '')}/"
            )
            lead = {
                "id": f"reddit-{post.get('id')}",
                "title": title,
                "summary": summary or "A public Reddit post where conversation or help is being invited.",
                "source": f"r/{post.get('subreddit', 'reddit')}",
                "platform": "Reddit",
                "url": post_url,
                "intent": intent_key,
                "intentLabel": config["label"],
                "age": format_relative_age(created),
                "_created": created,
                "signal": human_signal(full_text),
                "safety": "Public post",
            }
            lead["opener"] = build_human_opener(config, lead)
            leads.append(lead)
    return leads


def fetch_mastodon_human_leads(intent_key: str, config: dict) -> list[dict]:
    tags = config.get("mastodon_tags", [])
    if not tags:
        return []

    leads = []
    for tag in tags[:3]:
        url = "https://mastodon.social/api/v1/timelines/tag/" + urllib.parse.quote(
            tag
        ) + "?limit=8"
        data = http_get_json(url)
        if not isinstance(data, list):
            continue

        for status in data:
            if not isinstance(status, dict):
                continue
            account = status.get("account", {}) if isinstance(status.get("account"), dict) else {}
            acct = account.get("acct") or account.get("username") or "mastodon"
            if status.get("sensitive") or status.get("reblog") or status.get("visibility") != "public":
                continue
            if account.get("bot") or "bot" in str(acct).lower():
                continue
            created = parse_iso_timestamp(status.get("created_at"))
            if not human_timestamp_is_fresh(created):
                continue

            content = strip_markup(status.get("content"), 280)
            tag_text = " ".join(item.get("name", "") for item in status.get("tags", []) if isinstance(item, dict))
            full_text = f"{content} {tag_text}"
            if not content or not human_lead_allowed(full_text, intent_key):
                continue
            if content.lower().count("http") > 2:
                continue

            display_name = strip_markup(account.get("display_name") or acct, 48)
            title = compact_text(content, 105)
            if len(title) < 24:
                title = f"Public post by {display_name}"
            lead = {
                "id": f"mastodon-{status.get('id')}",
                "title": title,
                "summary": content,
                "source": f"@{acct}",
                "platform": "Mastodon",
                "url": status.get("url") or account.get("url") or "https://mastodon.social/",
                "intent": intent_key,
                "intentLabel": config["label"],
                "age": format_relative_age(created),
                "_created": created,
                "signal": human_signal(full_text),
                "safety": "Public post",
            }
            lead["opener"] = build_human_opener(config, lead)
            leads.append(lead)
    return leads


def fetch_hn_human_leads(intent_key: str, config: dict) -> list[dict]:
    queries = config.get("hn_queries", [])
    if not queries:
        return []

    leads = []
    for query in queries[:2]:
        url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(
            {"query": query, "tags": "story", "hitsPerPage": "8"}
        )
        data = http_get_json(url)
        for hit in data.get("hits", []):
            created = hit.get("created_at_i")
            if not human_timestamp_is_fresh(created):
                continue
            title = strip_markup(hit.get("title") or hit.get("story_title"), 120)
            summary = strip_markup(hit.get("story_text") or hit.get("comment_text"), 260)
            full_text = f"{title} {summary}"
            if not title or not human_lead_allowed(full_text, intent_key):
                continue
            object_id = hit.get("objectID")
            lead_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else "https://news.ycombinator.com/"
            lead = {
                "id": f"hn-{object_id}",
                "title": title,
                "summary": summary or "A public Hacker News thread that may invite advice, feedback, or discussion.",
                "source": "Hacker News",
                "platform": "HN",
                "url": lead_url,
                "intent": intent_key,
                "intentLabel": config["label"],
                "age": format_relative_age(created),
                "_created": created,
                "signal": human_signal(full_text),
                "safety": "Public thread",
            }
            lead["opener"] = build_human_opener(config, lead)
            leads.append(lead)
    return leads


def fallback_human_leads(intent_key: str, config: dict) -> list[dict]:
    query = random.choice(config.get("queries", [config["label"]]))
    reddit_url = "https://www.reddit.com/search/?" + urllib.parse.urlencode(
        {"q": query, "sort": "new", "t": "day"}
    )
    lead = {
        "id": f"starter-reddit-{intent_key}",
        "title": f"Search fresh {config['label'].lower()} openings",
        "summary": (
            "Opens a public search for people already asking to practice, chat, "
            "exchange feedback, or find an accountability partner."
        ),
        "source": "Public search",
        "platform": "Reddit",
        "url": reddit_url,
        "intent": intent_key,
        "intentLabel": config["label"],
        "age": "Live",
        "signal": "Starter place",
        "safety": "You choose",
    }
    lead["opener"] = config.get("opener", build_human_opener(config, lead))
    return [lead]


def public_human_lead(lead: dict) -> dict:
    return {key: value for key, value in lead.items() if not key.startswith("_")}


def fetch_human_link_leads(intent_key: str) -> tuple[list[dict], dict]:
    key, config = human_intent_config(intent_key)
    leads = []
    errors = []

    for fetcher in (fetch_mastodon_human_leads, fetch_hn_human_leads, fetch_reddit_human_leads):
        try:
            leads.extend(fetcher(key, config))
        except HumanLinkError as err:
            errors.append(str(err))
        except Exception as err:
            errors.append(f"{fetcher.__name__}: {err}")

    deduped = []
    seen = set()
    for lead in leads:
        fingerprint = (lead.get("url") or lead.get("title") or "").lower()
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(lead)

    scored = sorted(
        ((human_lead_score(lead), lead) for lead in deduped),
        key=lambda pair: pair[0],
        reverse=True,
    )
    selected = [lead for _score, lead in scored[:12]]
    fallback = False
    if not selected:
        selected = fallback_human_leads(key, config)
        fallback = True
    else:
        selected = [public_human_lead(lead) for lead in selected]

    meta = {
        "intent": key,
        "intentLabel": config["label"],
        "mode": "public-search",
        "sourceCount": len(deduped),
        "fallback": fallback,
        "freshWindowHours": get_human_max_age_seconds() // 3600,
        "hotWindowHours": get_human_hot_age_seconds() // 3600,
        "searchedAt": int(time.time()),
    }
    if errors:
        meta["warnings"] = [compact_text(error, 120) for error in errors[:3]]
    return selected, meta


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/clip":
            self.handle_clip(parsed)
            return
        if parsed.path == "/api/clip/prefetch":
            self.handle_clip_prefetch(parsed)
            return
        if parsed.path == "/api/openai/clip-tune":
            self.handle_openai_clip_tune(parsed)
            return
        if parsed.path == "/api/human-link":
            self.handle_human_link(parsed)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/clip":
            self.handle_clip(parsed, self.read_json_body())
            return
        if parsed.path == "/api/clip/prefetch":
            self.handle_clip_prefetch(parsed, self.read_json_body())
            return
        self.write_json({"ok": False, "message": "Unknown endpoint."}, HTTPStatus.NOT_FOUND)

    def write_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict:
        try:
            length = min(1_000_000, int(self.headers.get("Content-Length") or "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def request_query(self, parsed: urllib.parse.ParseResult, payload: dict | None = None) -> dict[str, list[str]]:
        query = urllib.parse.parse_qs(parsed.query)
        for key, value in (payload or {}).items():
            if isinstance(value, list):
                query[key] = [",".join(str(item) for item in value)]
            elif isinstance(value, dict):
                query[key] = [json.dumps(value)]
            elif value is not None:
                query[key] = [str(value)]
        return query

    def handle_clip(self, parsed: urllib.parse.ParseResult, payload: dict | None = None) -> None:
        query = self.request_query(parsed, payload)
        avoid_ids = {
            item.strip()
            for item in ",".join(query.get("avoid", [])).split(",")
            if item.strip()
        }
        taste_hints = parse_clip_taste_hints(query)

        status = HTTPStatus.OK
        try:
            clip, meta = fetch_clip(avoid_ids, taste_hints)
            payload = {"ok": True, "clip": clip, "meta": meta}
        except ClipError as err:
            payload = {"ok": False, "message": str(err)}
        except Exception as err:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            payload = {"ok": False, "message": f"Unexpected clip search error: {err}"}

        self.write_json(payload, status)

    def handle_clip_prefetch(self, parsed: urllib.parse.ParseResult, payload: dict | None = None) -> None:
        query = self.request_query(parsed, payload)
        taste_hints = parse_clip_taste_hints(query)
        trigger_prefetch("client-warmup", taste_hints)
        self.write_json({
            "ok": True,
            "prefetching": True,
            "cacheTarget": get_cache_target_size(),
        })

    def handle_openai_clip_tune(self, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        prompt = (query.get("prompt", [""])[0] or "").strip()
        if not prompt:
            self.write_json(
                {"ok": False, "message": "Missing ChatGPT prompt."},
                HTTPStatus.BAD_REQUEST,
            )
            return

        url = build_chatgpt_prompt_url(prompt)
        launched = False
        warning = ""
        if (query.get("launch", ["1"])[0] or "1") != "0":
            try:
                url = launch_chatgpt_prompt(prompt)
                launched = True
            except Exception as err:
                warning = compact_text(str(err), 140)

        payload = {
            "ok": True,
            "url": url,
            "launched": launched,
            "mode": "chatgpt-web-handoff",
        }
        if warning:
            payload["warning"] = warning
        self.write_json(payload)

    def handle_human_link(self, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        intent = query.get("intent", ["english"])[0]
        status = HTTPStatus.OK
        try:
            leads, meta = fetch_human_link_leads(intent)
            payload = {"ok": True, "leads": leads, "meta": meta}
        except Exception as err:
            key, config = human_intent_config(intent)
            payload = {
                "ok": True,
                "leads": fallback_human_leads(key, config),
                "meta": {
                    "intent": key,
                    "intentLabel": config["label"],
                    "mode": "fallback",
                    "fallback": True,
                    "warnings": [compact_text(str(err), 120)],
                },
            }

        self.write_json(payload, status)


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
