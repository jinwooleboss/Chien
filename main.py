# ============================================================
# AUTO FORWARDER TELEGRAM
# VERSION COMPLETE
# STICKER AUTOMATIQUE APRÈS 3 MINUTES
# ============================================================

import os
import re
import json
import logging
import traceback
import asyncio

from difflib import SequenceMatcher
from urllib.parse import unquote

import requests

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = "8734390269:AAF0K4N-8Crsr1Tjsy50FQS6RwemjVShma0"

if not TOKEN:
    raise RuntimeError(
        "❌ Token Telegram manquant.\n"
        "Définis la variable BOT_TOKEN."
    )


CONFIG_FILE = "config_B.json"

# ------------------------------------------------------------
# ADMIN
# ------------------------------------------------------------

ADMIN_IDS = {
    5825526159
}


# ============================================================
# STICKER DE FIN
# ============================================================

# 3 minutes
STICKER_DELAY = 3 * 60

# Tâche actuellement programmée
completion_task = None


# ============================================================
# CONFIGURATION PAR DÉFAUT
# ============================================================

DEFAULT_CONFIG = {

    "sources": [
        -1001694110649
    ],

    "destination": -1001569253891,

    "completion_sticker_id": "",

    "animes": {

        "The Elusive Samurai": {
            "enabled": True,
            "season": 1,
            "aliases": []
        },

        "I Became a Legend After My 10 Year-Long Last Stand": {
            "enabled": True,
            "season": 1,
            "aliases": []
        },

        "Welcome to Demon School Iruma kun": {
            "enabled": True,
            "season": 4,
            "aliases": [
                "Welcome to Demon School Iruma-kun",
                "Mairimashita Iruma-kun",
                "Iruma-kun"
            ]
        }
    }
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("AUTO_FORWARDER")


# ============================================================
# SAUVEGARDE CONFIG
# ============================================================

def save_config(config):

    try:

        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                config,
                file,
                ensure_ascii=False,
                indent=4
            )

        logger.info(
            f"💾 Configuration sauvegardée : {CONFIG_FILE}"
        )

    except Exception as error:

        logger.error(
            f"❌ Erreur sauvegarde : {error}"
        )


# ============================================================
# CHARGEMENT CONFIG
# ============================================================

def load_config():

    if not os.path.exists(CONFIG_FILE):

        logger.info(
            f"📁 Création de {CONFIG_FILE}"
        )

        config = json.loads(
            json.dumps(DEFAULT_CONFIG)
        )

        save_config(config)

        return config

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            config = json.load(file)

        if not isinstance(config, dict):

            raise ValueError(
                "Le fichier JSON doit contenir un objet."
            )

        config.setdefault(
            "sources",
            []
        )

        config.setdefault(
            "destination",
            None
        )

        config.setdefault(
            "completion_sticker_id",
            ""
        )

        config.setdefault(
            "animes",
            {}
        )

        # ----------------------------------------------------
        # Sécurité des types
        # ----------------------------------------------------

        if not isinstance(
            config["sources"],
            list
        ):

            config["sources"] = []

        if not isinstance(
            config["animes"],
            dict
        ):

            config["animes"] = {}

        # ----------------------------------------------------
        # MIGRATION ANIMES
        # ----------------------------------------------------

        for name, data in list(
            config["animes"].items()
        ):

            if isinstance(data, dict):

                data.setdefault(
                    "enabled",
                    True
                )

                data.setdefault(
                    "season",
                    1
                )

                data.setdefault(
                    "aliases",
                    []
                )

                if not isinstance(
                    data["aliases"],
                    list
                ):

                    data["aliases"] = []

            else:

                config["animes"][name] = {

                    "enabled": True,

                    "season": 1,

                    "aliases": []
                }

        # ----------------------------------------------------
        # MIGRATION ANCIEN NOM DU STICKER
        # ----------------------------------------------------

        old_sticker = config.get(
            "completion_sticker"
        )

        current_sticker = config.get(
            "completion_sticker_id"
        )

        if (
            not current_sticker
            and old_sticker
        ):

            config["completion_sticker_id"] = (
                old_sticker
            )

            logger.info(
                "🔄 Ancien paramètre sticker migré."
            )

        # On garde uniquement le nouveau format
        config.pop(
            "completion_sticker",
            None
        )

        save_config(config)

        return config

    except Exception as error:

        logger.error(
            f"❌ Erreur lecture config : {error}"
        )

        logger.info(
            "🔄 Retour à la configuration par défaut."
        )

        config = json.loads(
            json.dumps(DEFAULT_CONFIG)
        )

        save_config(config)

        return config


# ============================================================
# CONFIGURATION ACTIVE
# ============================================================

CONFIG = load_config()


# ============================================================
# UTILITAIRES
# ============================================================

def is_admin(user_id):

    return user_id in ADMIN_IDS


def persist_config():

    save_config(CONFIG)


# ============================================================
# NORMALISATION
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text)

    # --------------------------------------------------------
    # Décodage URL
    # --------------------------------------------------------

    text = unquote(text)

    if "%" in text:

        text = unquote(text)

    text = text.lower()

    # --------------------------------------------------------
    # Accents
    # --------------------------------------------------------

    replacements = {

        "à": "a",
        "â": "a",
        "ä": "a",
        "á": "a",
        "ã": "a",

        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",

        "î": "i",
        "ï": "i",

        "ô": "o",
        "ö": "o",

        "ù": "u",
        "û": "u",
        "ü": "u",

        "ç": "c"
    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

    # --------------------------------------------------------
    # Encodage 5B / 5D
    # --------------------------------------------------------

    text = re.sub(
        r"(?<![a-z0-9])5b",
        " ",
        text
    )

    text = re.sub(
        r"(?<![a-z0-9])5d",
        " ",
        text
    )

    # --------------------------------------------------------
    # %XX résiduels
    # --------------------------------------------------------

    text = re.sub(
        r"%[0-9a-f]{2}",
        " ",
        text,
        flags=re.I
    )

    # --------------------------------------------------------
    # Ponctuation
    # --------------------------------------------------------

    text = re.sub(
        r"[_\-.]+",
        " ",
        text
    )

    text = text.replace(
        "'",
        " "
    )

    text = re.sub(
        r"[()\[\]{}]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# MOTS TECHNIQUES
# ============================================================

TECHNICAL_WORDS = {

    "2160p",
    "1440p",
    "1080p",
    "720p",
    "576p",
    "480p",
    "360p",

    "4k",
    "2k",

    "hd",
    "fhd",
    "uhd",

    "web",
    "webdl",
    "webrip",

    "bluray",
    "brrip",
    "dvdrip",
    "hdtv",
    "hdrip",

    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",

    "aac",
    "ac3",
    "eac3",
    "flac",
    "dts",

    "10bit",
    "8bit",

    "vostfr",
    "vostf",
    "vost",

    "vf",
    "vff",
    "vf2",

    "french",
    "francais",

    "dub",
    "dubbed",

    "hardsub",
    "softsub",

    "hard",
    "sub",

    "episode",
    "episodes",
    "ep",

    "season",
    "saison",

    "streaming",

    "truefrench",

    "mkv",
    "mp4",
    "avi",
    "mov",

    "subsplease",
    "erai",
    "erai-raws"
}


# ============================================================
# NETTOYAGE NOM ANIME
# ============================================================

def clean_anime_words(text):

    text = normalize_text(text)

    # S01E07
    text = re.sub(
        r"\bs\d{1,2}e\d{1,4}\b",
        " ",
        text,
        flags=re.I
    )

    # 01x07
    text = re.sub(
        r"\b\d{1,2}x\d{1,4}\b",
        " ",
        text,
        flags=re.I
    )

    # S01 07
    text = re.sub(
        r"\bs\d{1,2}\s+\d{1,4}\b",
        " ",
        text,
        flags=re.I
    )

    # S03 - 08
    text = re.sub(
        r"\bs\d{1,2}\s*[- ]\s*\d{1,4}\b",
        " ",
        text,
        flags=re.I
    )

    # Episode 07
    text = re.sub(
        r"\b(?:episode|ep)\s*\d{1,4}\b",
        " ",
        text,
        flags=re.I
    )

    words = text.split()

    cleaned = []

    for word in words:

        if word in TECHNICAL_WORDS:

            continue

        if re.fullmatch(
            r"s\d{1,2}",
            word
        ):

            continue

        if re.fullmatch(
            r"e\d{1,4}",
            word
        ):

            continue

        if re.fullmatch(
            r"\d{3,4}p",
            word
        ):

            continue

        if re.fullmatch(
            r"\d{1,4}",
            word
        ):

            continue

        cleaned.append(
            word
        )

    return cleaned


# ============================================================
# SCORE
# ============================================================

def anime_match_score(
    configured_name,
    filename
):

    configured = normalize_text(
        configured_name
    )

    filename_normalized = normalize_text(
        filename
    )

    if not configured or not filename_normalized:

        return 0

    # --------------------------------------------------------
    # Correspondance exacte
    # --------------------------------------------------------

    if configured in filename_normalized:

        return 1.0

    configured_words = clean_anime_words(
        configured
    )

    filename_words = clean_anime_words(
        filename_normalized
    )

    if not configured_words or not filename_words:

        return 0

    # --------------------------------------------------------
    # Mots exacts
    # --------------------------------------------------------

    exact_matches = sum(
        1
        for word in configured_words
        if word in filename_words
    )

    exact_score = (
        exact_matches /
        len(configured_words)
    )

    # --------------------------------------------------------
    # Fuzzy phrase
    # --------------------------------------------------------

    phrase_score = SequenceMatcher(
        None,
        " ".join(configured_words),
        " ".join(filename_words)
    ).ratio()

    # --------------------------------------------------------
    # Fuzzy mots
    # --------------------------------------------------------

    fuzzy_matches = 0

    for wanted in configured_words:

        best_ratio = max(
            (
                SequenceMatcher(
                    None,
                    wanted,
                    found
                ).ratio()

                for found in filename_words
            ),
            default=0
        )

        if best_ratio >= 0.80:

            fuzzy_matches += 1

    fuzzy_score = (
        fuzzy_matches /
        len(configured_words)
    )

    return max(
        phrase_score,
        exact_score,
        fuzzy_score
    )


# ============================================================
# RECHERCHE ANIME
# ============================================================

def find_configured_anime(text):

    if not text:

        return None

    best_anime = None

    best_score = 0

    for anime_name, config in CONFIG["animes"].items():

        if not isinstance(
            config,
            dict
        ):

            continue

        if config.get(
            "enabled",
            True
        ) is False:

            continue

        candidates = [
            anime_name
        ]

        aliases = config.get(
            "aliases",
            []
        )

        if isinstance(
            aliases,
            list
        ):

            candidates.extend(
                aliases
            )

        anime_best_score = 0

        anime_best_candidate = anime_name

        for candidate in candidates:

            score = anime_match_score(
                candidate,
                text
            )

            if score > anime_best_score:

                anime_best_score = score

                anime_best_candidate = candidate

        logger.info(
            f"🔎 {anime_name} "
            f"(via {anime_best_candidate}) : "
            f"{anime_best_score * 100:.1f}%"
        )

        if anime_best_score > best_score:

            best_score = anime_best_score

            best_anime = anime_name

    if best_anime is None:

        logger.info(
            "❌ Aucun anime correspondant."
        )

        return None

    if best_score < 0.75:

        logger.info(
            f"❌ Anime non reconnu "
            f"({best_score * 100:.1f}%)"
        )

        return None

    logger.info(
        f"🎬 Anime reconnu : "
        f"{best_anime} "
        f"({best_score * 100:.1f}%)"
    )

    return best_anime


# ============================================================
# ANILIST
# ============================================================

ANILIST_URL = "https://graphql.anilist.co"


def fetch_anime_aliases(name):

    query = """
    query ($search: String) {
        Page(page: 1, perPage: 5) {
            media(
                search: $search,
                type: ANIME
            ) {
                id
                title {
                    romaji
                    english
                    native
                    userPreferred
                }
                synonyms
            }
        }
    }
    """

    variables = {
        "search": name
    }

    try:

        response = requests.post(
            ANILIST_URL,
            json={
                "query": query,
                "variables": variables
            },
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        media_list = (
            data
            .get("data", {})
            .get("Page", {})
            .get("media", [])
        )

        if not media_list:

            logger.info(
                f"🔍 Aucun alias AniList trouvé pour : {name}"
            )

            return []

        normalized_name = normalize_text(
            name
        )

        best_media = None

        best_score = 0

        for media in media_list:

            titles = media.get(
                "title",
                {}
            )

            candidates = []

            for key in (
                "romaji",
                "english",
                "native",
                "userPreferred"
            ):

                value = titles.get(
                    key
                )

                if value:

                    candidates.append(
                        value
                    )

            candidates.extend(
                media.get(
                    "synonyms",
                    []
                ) or []
            )

            media_score = 0

            for candidate in candidates:

                score = SequenceMatcher(
                    None,
                    normalized_name,
                    normalize_text(
                        candidate
                    )
                ).ratio()

                media_score = max(
                    media_score,
                    score
                )

            if media_score > best_score:

                best_score = media_score

                best_media = media

        if not best_media:

            return []

        if best_score < 0.55:

            logger.info(
                f"⚠️ Résultat AniList trop incertain "
                f"pour {name}: "
                f"{best_score * 100:.1f}%"
            )

            return []

        titles = best_media.get(
            "title",
            {}
        )

        aliases = []

        for key in (
            "romaji",
            "english",
            "native",
            "userPreferred"
        ):

            value = titles.get(
                key
            )

            if value:

                aliases.append(
                    value
                )

        aliases.extend(
            best_media.get(
                "synonyms",
                []
            ) or []
        )

        final_aliases = []

        normalized_main = normalize_text(
            name
        )

        existing = set()

        for alias in aliases:

            if not alias:

                continue

            alias = alias.strip()

            if not alias:

                continue

            normalized = normalize_text(
                alias
            )

            if normalized == normalized_main:

                continue

            if normalized in existing:

                continue

            existing.add(
                normalized
            )

            final_aliases.append(
                alias
            )

        logger.info(
            f"🔤 Alias automatiques pour "
            f"{name} : {final_aliases}"
        )

        return final_aliases

    except Exception as error:

        logger.warning(
            f"⚠️ Impossible de récupérer "
            f"les alias AniList : {error}"
        )

        return []


# ============================================================
# AJOUT ALIAS
# ============================================================

def add_automatic_aliases(
    anime_name,
    aliases
):

    if anime_name not in CONFIG["animes"]:

        return []

    config = CONFIG["animes"][anime_name]

    current_aliases = config.setdefault(
        "aliases",
        []
    )

    existing_normalized = {
        normalize_text(alias)
        for alias in current_aliases
    }

    main_normalized = normalize_text(
        anime_name
    )

    added = []

    for alias in aliases:

        normalized = normalize_text(
            alias
        )

        if not normalized:

            continue

        if normalized == main_normalized:

            continue

        if normalized in existing_normalized:

            continue

        current_aliases.append(
            alias
        )

        existing_normalized.add(
            normalized
        )

        added.append(
            alias
        )

    return added


# ============================================================
# NOM FICHIER
# ============================================================

def get_message_filename(message):

    if message.document:

        return (
            message.document.file_name
            or ""
        )

    if message.video:

        return (
            message.video.file_name
            or ""
        )

    if message.audio:

        return (
            message.audio.file_name
            or ""
        )

    return ""


# ============================================================
# CAPTION
# ============================================================

def get_message_caption(message):

    return message.caption or ""


# ============================================================
# LANGUE
# ============================================================

def detect_language(text):

    if not text:

        return ""

    filename = os.path.basename(
        str(text).strip()
    )

    filename_lower = filename.lower()

    # --------------------------------------------------------
    # THREE.MKV
    # --------------------------------------------------------

    if filename_lower == "three.mkv":

        logger.info(
            "🇫🇷 THREE.mkv → VF"
        )

        return "VF"

    upper = filename.upper()

    upper = re.sub(
        r"[._\-]+",
        " ",
        upper
    )

    upper = re.sub(
        r"\s+",
        " ",
        upper
    ).strip()

    # --------------------------------------------------------
    # HARDSUB
    # --------------------------------------------------------

    hardsub_patterns = [

        r"\bHARDSUB\b",
        r"\bHARD\s+SUB\b",
        r"\bHARD-SUB\b",
        r"\bHARDSUBBED\b",
        r"\bHARD\s+SUBBED\b"
    ]

    for pattern in hardsub_patterns:

        if re.search(
            pattern,
            upper,
            re.I
        ):

            logger.info(
                "🇫🇷 HARDSUB détecté → VOSTFR"
            )

            return "VOSTFR"

    # --------------------------------------------------------
    # VOSTFR
    # --------------------------------------------------------

    vostfr_patterns = [

        r"\bVOSTFR\b",
        r"\bVOSTF\b",
        r"\bVOST\b",
        r"\bSUBFRENCH\b",
        r"\bSUB\s+FRENCH\b",
        r"\bFRENCH\s+SUB\b",
        r"\bFRENCH\s+SUBS\b",
        r"\bFR\s+SUB\b",
        r"\bSUB\s*FR\b"
    ]

    for pattern in vostfr_patterns:

        if re.search(
            pattern,
            upper,
            re.I
        ):

            logger.info(
                "🇫🇷 VOSTFR détecté"
            )

            return "VOSTFR"

    # --------------------------------------------------------
    # VF
    # --------------------------------------------------------

    vf_patterns = [

        r"\bTRUEFRENCH\b",
        r"\bTRUE\s+FRENCH\b",
        r"\bFRENCH\s+DUB\b",
        r"\bFRENCH\s+DUBBED\b",
        r"\bVFF\b",
        r"\bVF2\b",
        r"\bVF\b",
        r"\bDUBBED\b",
        r"\bDUB\b",
        r"\bFRANCAIS\b",
        r"\bFRANÇAIS\b"
    ]

    for pattern in vf_patterns:

        if re.search(
            pattern,
            upper,
            re.I
        ):

            logger.info(
                "🇫🇷 VF détecté"
            )

            return "VF"

    # --------------------------------------------------------
    # GROUPES
    # --------------------------------------------------------

    if re.search(
        r"\bSUBSPLEASE\b",
        upper,
        re.I
    ):

        logger.info(
            "🇫🇷 SubsPlease détecté → VOSTFR"
        )

        return "VOSTFR"

    if re.search(
        r"\bERAI[\s\-]*RAWS\b",
        upper,
        re.I
    ):

        logger.info(
            "🇫🇷 Erai-raws détecté → VOSTFR"
        )

        return "VOSTFR"

    logger.info(
        f"🇫🇷 Langue non détectée : {filename}"
    )

    return ""


# ============================================================
# QUALITÉ
# ============================================================

def detect_quality(text):

    if not text:

        return ""

    match = re.search(
        r"(?i)\b"
        r"(2160p|1440p|1080p|720p|"
        r"576p|480p|360p|HD|FHD|UHD)"
        r"\b",
        text
    )

    if match:

        return match.group(1).upper()

    return ""


# ============================================================
# SAISON / ÉPISODE
# ============================================================

def extract_episode(text):

    if not text:

        return None, None

    cleaned = normalize_text(
        text
    )

    # S03E08
    match = re.search(
        r"\bs\s*(\d{1,2})\s*e\s*(\d{1,4})\b",
        cleaned,
        re.I
    )

    if match:

        return (
            int(match.group(1)),
            int(match.group(2))
        )

    # 03x08
    match = re.search(
        r"\b(\d{1,2})\s*x\s*(\d{1,4})\b",
        cleaned,
        re.I
    )

    if match:

        return (
            int(match.group(1)),
            int(match.group(2))
        )

    # S03 - 08
    match = re.search(
        r"\bs\s*(\d{1,2})\s*[-_ ]\s*(\d{1,4})\b",
        cleaned,
        re.I
    )

    if match:

        return (
            int(match.group(1)),
            int(match.group(2))
        )

    # Saison 3 épisode 8
    match = re.search(
        r"\b(?:saison|season)\s*(\d{1,2})"
        r".*?"
        r"(?:episode|ep)\s*(\d{1,4})\b",
        cleaned,
        re.I
    )

    if match:

        return (
            int(match.group(1)),
            int(match.group(2))
        )

    # Episode 08
    match = re.search(
        r"\b(?:episode|ep)\s*(\d{1,4})\b",
        cleaned,
        re.I
    )

    if match:

        return (
            None,
            int(match.group(1))
        )

    return None, None


# ============================================================
# ANALYSE MESSAGE
# ============================================================

def analyze_message(message):

    filename = get_message_filename(
        message
    )

    caption = get_message_caption(
        message
    )

    # --------------------------------------------------------
    # FICHIER
    # --------------------------------------------------------

    if filename:

        logger.info(
            f"📄 Fichier reçu : {filename}"
        )

        language = detect_language(
            filename
        )

        anime = find_configured_anime(
            filename
        )

        if anime:

            season, episode = extract_episode(
                filename
            )

            if season is None:

                season = CONFIG["animes"][
                    anime
                ].get(
                    "season"
                )

            return {

                "anime": anime,

                "season": season,

                "episode": episode,

                "language": language,

                "quality": detect_quality(
                    filename
                ),

                "source_text": filename,

                "source_type": "filename",

                "filename": filename
            }

    # --------------------------------------------------------
    # CAPTION
    # --------------------------------------------------------

    if caption:

        logger.info(
            f"📝 Légende : {caption}"
        )

        language = detect_language(
            caption
        )

        anime = find_configured_anime(
            caption
        )

        if anime:

            season, episode = extract_episode(
                caption
            )

            if season is None:

                season = CONFIG["animes"][
                    anime
                ].get(
                    "season"
                )

            return {

                "anime": anime,

                "season": season,

                "episode": episode,

                "language": language,

                "quality": detect_quality(
                    caption
                ),

                "source_text": caption,

                "source_type": "caption",

                "filename": filename
            }

    return None


# ============================================================
# CAPTION DESTINATION
# ============================================================

def build_caption(info):

    anime = info.get(
        "anime",
        ""
    )

    season = info.get(
        "season"
    )

    episode = info.get(
        "episode"
    )

    language = info.get(
        "language",
        ""
    )

    quality = info.get(
        "quality",
        ""
    )

    lines = []

    if anime:

        lines.append(
            f"🎬 <b>{anime}</b>"
        )

    if (
        season is not None
        and episode is not None
    ):

        lines.append(
            f"📀 Saison {season} — "
            f"Épisode {episode}"
        )

    elif season is not None:

        lines.append(
            f"📀 Saison {season}"
        )

    elif episode is not None:

        lines.append(
            f"📺 Épisode {episode}"
        )

    if language:

        if language == "VOSTFR":

            lines.append(
                "🇫🇷 VOSTFR"
            )

        elif language == "VF":

            lines.append(
                "🇫🇷 VF"
            )

        else:

            lines.append(
                f"🇫🇷 {language}"
            )

    if quality:

        lines.append(
            f"🎞 Qualité : {quality}"
        )

    return "\n".join(
        lines
    )


# ============================================================
# MESSAGES DÉJÀ TRAITÉS
# ============================================================

PROCESSED_MESSAGES = set()

MAX_PROCESSED_MESSAGES = 2000


def message_key(message):

    return (
        message.chat_id,
        message.message_id
    )


def already_processed(message):

    key = message_key(
        message
    )

    if key in PROCESSED_MESSAGES:

        return True

    PROCESSED_MESSAGES.add(
        key
    )

    if len(
        PROCESSED_MESSAGES
    ) > MAX_PROCESSED_MESSAGES:

        while len(
            PROCESSED_MESSAGES
        ) > MAX_PROCESSED_MESSAGES:

            PROCESSED_MESSAGES.pop()

    return False


# ============================================================
# ANNULATION TIMER STICKER
# ============================================================

def cancel_completion_timer():

    global completion_task

    if completion_task is not None:

        if not completion_task.done():

            completion_task.cancel()

            logger.info(
                "⏹️ Ancien timer sticker annulé."
            )

    completion_task = None


# ============================================================
# TIMER STICKER
# ============================================================

async def completion_timer(
    context
):

    global completion_task

    try:

        logger.info(
            "⏳ Attente de 3 minutes "
            "avant le sticker..."
        )

        await asyncio.sleep(
            STICKER_DELAY
        )

        destination = CONFIG.get(
            "destination"
        )

        sticker_id = CONFIG.get(
            "completion_sticker_id"
        )

        if not destination:

            logger.warning(
                "⚠️ Destination absente."
            )

            return

        if not sticker_id:

            logger.warning(
                "⚠️ Aucun sticker de fin configuré."
            )

            return

        try:

            await context.bot.send_sticker(
                chat_id=destination,
                sticker=sticker_id
            )

            logger.info(
                "🧩 Sticker de fin envoyé "
                "après 3 minutes sans nouvelle vidéo."
            )

        except Exception as error:

            logger.error(
                f"❌ Erreur envoi sticker : {error}"
            )

    except asyncio.CancelledError:

        logger.info(
            "⏹️ Timer sticker annulé "
            "car une nouvelle vidéo est arrivée."
        )

        raise

    finally:

        # Ne supprimer la référence que si
        # cette tâche est toujours la tâche active.
        current_task = asyncio.current_task()

        if completion_task is current_task:

            completion_task = None


# ============================================================
# PROGRAMMER STICKER
# ============================================================

def schedule_completion_sticker(
    context
):

    global completion_task

    # --------------------------------------------------------
    # Annuler le précédent
    # --------------------------------------------------------

    cancel_completion_timer()

    # --------------------------------------------------------
    # Vérifier qu'un sticker existe
    # --------------------------------------------------------

    sticker_id = CONFIG.get(
        "completion_sticker_id"
    )

    if not sticker_id:

        logger.info(
            "🧩 Aucun sticker configuré. "
            "Timer non démarré."
        )

        return

    # --------------------------------------------------------
    # Nouveau timer
    # --------------------------------------------------------

    completion_task = context.application.create_task(
        completion_timer(
            context
        ),
        update=None,
        name="completion_sticker_timer"
    )

    logger.info(
        "⏱️ Nouveau timer sticker lancé : 3 minutes."
    )


# ============================================================
# TRANSFERT
# ============================================================

async def forward_message(
    message,
    info,
    context
):

    destination = CONFIG.get(
        "destination"
    )

    if not destination:

        logger.error(
            "❌ Destination non configurée."
        )

        return False

    caption = build_caption(
        info
    )

    try:

        # ----------------------------------------------------
        # VIDÉO
        # ----------------------------------------------------

        if message.video:

            await context.bot.send_video(
                chat_id=destination,
                video=message.video.file_id,
                caption=caption or None,
                parse_mode=ParseMode.HTML,
                supports_streaming=True
            )

        # ----------------------------------------------------
        # DOCUMENT
        # ----------------------------------------------------

        elif message.document:

            await context.bot.send_document(
                chat_id=destination,
                document=message.document.file_id,
                caption=caption or None,
                parse_mode=ParseMode.HTML
            )

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        elif message.audio:

            await context.bot.send_audio(
                chat_id=destination,
                audio=message.audio.file_id,
                caption=caption or None,
                parse_mode=ParseMode.HTML
            )

        # ----------------------------------------------------
        # AUTRE
        # ----------------------------------------------------

        else:

            await context.bot.copy_message(
                chat_id=destination,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )

        logger.info(
            f"✅ Message publié vers {destination}"
        )

        # ----------------------------------------------------
        # NOUVEAU TIMER
        # ----------------------------------------------------
        #
        # Très important :
        # le timer est lancé SEULEMENT après
        # un transfert réussi.
        # ----------------------------------------------------

        schedule_completion_sticker(
            context
        )

        return True

    except Exception as error:

        logger.error(
            f"❌ Erreur transfert : {error}"
        )

        traceback.print_exc()

        return False


# ============================================================
# RÉCEPTION MÉDIAS
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:

        return

    chat_id = message.chat_id

    if chat_id not in CONFIG.get(
        "sources",
        []
    ):

        return

    if already_processed(
        message
    ):

        logger.info(
            "⏭️ Message déjà traité."
        )

        return

    info = analyze_message(
        message
    )

    if not info:

        logger.info(
            "⏭️ Message ignoré."
        )

        return

    logger.info(
        f"📌 Anime : {info['anime']}"
    )

    logger.info(
        f"📌 Saison : {info.get('season')}"
    )

    logger.info(
        f"📌 Épisode : {info.get('episode')}"
    )

    logger.info(
        f"📌 Langue : {info.get('language')}"
    )

    logger.info(
        f"📌 Qualité : {info.get('quality')}"
    )

    await forward_message(
        message,
        info,
        context
    )


# ============================================================
# ADMIN ONLY
# ============================================================

async def admin_only(
    update,
    context
):

    user = update.effective_user

    if not user:

        return False

    if not is_admin(
        user.id
    ):

        if update.effective_message:

            await update.effective_message.reply_text(
                "❌ Tu n'es pas autorisé à utiliser cette commande."
            )

        return False

    return True


# ============================================================
# /START
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    text = (
        "🤖 <b>AUTO FORWARDER</b>\n\n"
        "✅ Bot actif.\n\n"

        "<b>Commandes :</b>\n"
        "/status\n"
        "/sources\n"
        "/destination\n"
        "/animes\n\n"

        "/addsource ID\n"
        "/removesource ID\n"
        "/setdestination ID\n\n"

        "/addanime NOM | SAISON\n"
        "/removeanime NOM\n"
        "/enableanime NOM\n"
        "/disableanime NOM\n\n"

        "/addalias NOM | ALIAS\n"
        "/removealias NOM | ALIAS\n\n"

        "/sticker\n\n"

        "/help"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await start_command(
        update,
        context
    )


# ============================================================
# /STATUS
# ============================================================

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    sources = CONFIG.get(
        "sources",
        []
    )

    destination = CONFIG.get(
        "destination"
    )

    animes = CONFIG.get(
        "animes",
        {}
    )

    enabled = sum(
        1
        for data in animes.values()
        if isinstance(data, dict)
        and data.get(
            "enabled",
            True
        )
    )

    total_aliases = sum(
        len(
            data.get(
                "aliases",
                []
            )
        )
        for data in animes.values()
        if isinstance(data, dict)
    )

    sticker = CONFIG.get(
        "completion_sticker_id"
    )

    timer_status = (
        "⏳ Actif"
        if (
            completion_task is not None
            and not completion_task.done()
        )
        else "⏸️ Aucun"
    )

    text = (
        "🤖 <b>STATUS</b>\n\n"

        "🟢 Bot actif\n\n"

        f"📡 Sources : {len(sources)}\n"
        f"🎯 Destination : {destination}\n"

        f"🎬 Animes : {len(animes)}\n"
        f"🔤 Alias : {total_aliases}\n"
        f"✅ Animes actifs : {enabled}\n\n"

        f"🧩 Sticker : "
        f"{'✅ Configuré' if sticker else '❌ Non configuré'}\n"

        f"⏱️ Timer : {timer_status}\n"
        f"⌛ Délai : 3 minutes"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /SOURCES
# ============================================================

async def sources_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    sources = CONFIG.get(
        "sources",
        []
    )

    if not sources:

        text = (
            "📡 <b>SOURCES</b>\n\n"
            "Aucune source configurée."
        )

    else:

        lines = [
            "📡 <b>SOURCES</b>",
            ""
        ]

        for index, source in enumerate(
            sources,
            start=1
        ):

            lines.append(
                f"{index}. <code>{source}</code>"
            )

        text = "\n".join(
            lines
        )

    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /DESTINATION
# ============================================================

async def destination_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    destination = CONFIG.get(
        "destination"
    )

    text = (
        "🎯 <b>DESTINATION</b>\n\n"
        f"<code>{destination}</code>"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /ANIMES
# ============================================================

async def animes_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    animes = CONFIG.get(
        "animes",
        {}
    )

    if not animes:

        await update.effective_message.reply_text(
            "🎬 Aucun anime configuré."
        )

        return

    lines = [
        "🎬 <b>ANIMES CONFIGURÉS</b>",
        ""
    ]

    for name, data in animes.items():

        if not isinstance(
            data,
            dict
        ):

            continue

        enabled = data.get(
            "enabled",
            True
        )

        season = data.get(
            "season",
            1
        )

        aliases = data.get(
            "aliases",
            []
        )

        icon = (
            "✅"
            if enabled
            else "❌"
        )

        lines.append(
            f"{icon} <b>{name}</b>"
        )

        lines.append(
            f"   Saison : {season}"
        )

        if aliases:

            lines.append(
                "   Alias : "
                + ", ".join(
                    aliases
                )
            )

        lines.append("")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /ADDSOURCE
# ============================================================

async def addsource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    if not context.args:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n/addsource ID"
        )

        return

    try:

        source_id = int(
            context.args[0]
        )

    except ValueError:

        await update.effective_message.reply_text(
            "❌ L'ID doit être un nombre."
        )

        return

    sources = CONFIG.setdefault(
        "sources",
        []
    )

    if source_id in sources:

        await update.effective_message.reply_text(
            "⚠️ Cette source existe déjà."
        )

        return

    sources.append(
        source_id
    )

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Source ajoutée :\n"
        f"<code>{source_id}</code>",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /REMOVESOURCE
# ============================================================

async def removesource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    if not context.args:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n/removesource ID"
        )

        return

    try:

        source_id = int(
            context.args[0]
        )

    except ValueError:

        await update.effective_message.reply_text(
            "❌ ID invalide."
        )

        return

    sources = CONFIG.get(
        "sources",
        []
    )

    if source_id not in sources:

        await update.effective_message.reply_text(
            "⚠️ Cette source n'existe pas."
        )

        return

    sources.remove(
        source_id
    )

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Source supprimée :\n"
        f"<code>{source_id}</code>",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /SETDESTINATION
# ============================================================

async def setdestination_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    if not context.args:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n/setdestination ID"
        )

        return

    try:

        destination = int(
            context.args[0]
        )

    except ValueError:

        await update.effective_message.reply_text(
            "❌ ID invalide."
        )

        return

    CONFIG["destination"] = destination

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Destination définie :\n"
        f"<code>{destination}</code>",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /ADDANIME
# ============================================================

async def addanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    raw = update.effective_message.text

    raw = re.sub(
        r"^/addanime(?:@\w+)?\s*",
        "",
        raw,
        flags=re.I
    ).strip()

    parts = [
        part.strip()
        for part in raw.split("|")
    ]

    if len(parts) < 2:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n"
            "/addanime NOM | SAISON\n\n"
            "Exemple :\n"
            "/addanime Mushoku Tensei | 3"
        )

        return

    name = parts[0]

    try:

        season = int(
            parts[1]
        )

    except ValueError:

        await update.effective_message.reply_text(
            "❌ La saison doit être un nombre."
        )

        return

    manual_aliases = []

    if len(parts) >= 3:

        manual_aliases = [
            x.strip()
            for x in parts[2].split(",")
            if x.strip()
        ]

    CONFIG["animes"][name] = {

        "enabled": True,

        "season": season,

        "aliases": manual_aliases
    }

    persist_config()

    await update.effective_message.reply_text(
        "⏳ Recherche automatique des alias..."
    )

    automatic_aliases = await asyncio.to_thread(
        fetch_anime_aliases,
        name
    )

    added_aliases = add_automatic_aliases(
        name,
        automatic_aliases
    )

    persist_config()

    aliases = CONFIG["animes"][name].get(
        "aliases",
        []
    )

    if aliases:

        alias_text = "\n".join(
            f"• {alias}"
            for alias in aliases
        )

    else:

        alias_text = "Aucun alias trouvé."

    text = (
        "✅ <b>Anime ajouté</b>\n\n"

        f"🎬 <b>{name}</b>\n"
        f"📀 Saison : {season}\n\n"

        f"🔤 <b>Alias enregistrés :</b>\n"
        f"{alias_text}"
    )

    if added_aliases:

        logger.info(
            f"🔤 {len(added_aliases)} "
            f"nouveaux alias ajoutés pour {name}"
        )

    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /REMOVEANIME
# ============================================================

async def removeanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    raw = update.effective_message.text

    raw = re.sub(
        r"^/removeanime(?:@\w+)?\s*",
        "",
        raw,
        flags=re.I
    ).strip()

    if not raw:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n/removeanime NOM"
        )

        return

    animes = CONFIG["animes"]

    if raw not in animes:

        await update.effective_message.reply_text(
            "❌ Anime introuvable."
        )

        return

    del animes[raw]

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Anime supprimé : {raw}"
    )


# ============================================================
# /ENABLEANIME
# ============================================================

async def enableanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    raw = update.effective_message.text

    raw = re.sub(
        r"^/enableanime(?:@\w+)?\s*",
        "",
        raw,
        flags=re.I
    ).strip()

    if raw not in CONFIG["animes"]:

        await update.effective_message.reply_text(
            "❌ Anime introuvable."
        )

        return

    CONFIG["animes"][raw]["enabled"] = True

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Anime activé : {raw}"
    )


# ============================================================
# /DISABLEANIME
# ============================================================

async def disableanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    raw = update.effective_message.text

    raw = re.sub(
        r"^/disableanime(?:@\w+)?\s*",
        "",
        raw,
        flags=re.I
    ).strip()

    if raw not in CONFIG["animes"]:

        await update.effective_message.reply_text(
            "❌ Anime introuvable."
        )

        return

    CONFIG["animes"][raw]["enabled"] = False

    persist_config()

    await update.effective_message.reply_text(
        f"❌ Anime désactivé : {raw}"
    )


# ============================================================
# /ADDALIAS
# ============================================================

async def addalias_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    raw = update.effective_message.text

    raw = re.sub(
        r"^/addalias(?:@\w+)?\s*",
        "",
        raw,
        flags=re.I
    ).strip()

    parts = [
        part.strip()
        for part in raw.split("|", 1)
    ]

    if len(parts) != 2:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n"
            "/addalias NOM | ALIAS\n\n"
            "Exemple :\n"
            "/addalias The 100 Girlfriends | Hyakkano"
        )

        return

    anime_name = parts[0]

    alias = parts[1]

    if anime_name not in CONFIG["animes"]:

        await update.effective_message.reply_text(
            "❌ Anime introuvable."
        )

        return

    aliases = CONFIG["animes"][
        anime_name
    ].setdefault(
        "aliases",
        []
    )

    if normalize_text(alias) in {
        normalize_text(x)
        for x in aliases
    }:

        await update.effective_message.reply_text(
            "⚠️ Cet alias existe déjà."
        )

        return

    aliases.append(
        alias
    )

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Alias ajouté.\n\n"
        f"🎬 Anime : {anime_name}\n"
        f"🔤 Alias : {alias}"
    )


# ============================================================
# /REMOVEALIAS
# ============================================================

async def removealias_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    raw = update.effective_message.text

    raw = re.sub(
        r"^/removealias(?:@\w+)?\s*",
        "",
        raw,
        flags=re.I
    ).strip()

    parts = [
        part.strip()
        for part in raw.split("|", 1)
    ]

    if len(parts) != 2:

        await update.effective_message.reply_text(
            "❌ Utilisation :\n"
            "/removealias NOM | ALIAS"
        )

        return

    anime_name = parts[0]

    alias = parts[1]

    if anime_name not in CONFIG["animes"]:

        await update.effective_message.reply_text(
            "❌ Anime introuvable."
        )

        return

    aliases = CONFIG["animes"][
        anime_name
    ].get(
        "aliases",
        []
    )

    found = None

    for existing in aliases:

        if normalize_text(
            existing
        ) == normalize_text(
            alias
        ):

            found = existing

            break

    if found is None:

        await update.effective_message.reply_text(
            "❌ Alias introuvable."
        )

        return

    aliases.remove(
        found
    )

    persist_config()

    await update.effective_message.reply_text(
        f"✅ Alias supprimé : {found}"
    )


# ============================================================
# /STICKER
# ============================================================

async def set_sticker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(
        update,
        context
    ):

        return

    context.user_data[
        "waiting_for_sticker"
    ] = True

    await update.effective_message.reply_text(
        "🧩 <b>Configuration du sticker</b>\n\n"
        "Envoie maintenant le sticker que le bot "
        "doit envoyer après 3 minutes sans nouvelle vidéo.",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# RÉCEPTION STICKER
# ============================================================

async def receive_sticker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:

        return

    if not update.message.sticker:

        return

    user = update.effective_user

    if not user:

        return

    if not is_admin(
        user.id
    ):

        return

    # --------------------------------------------------------
    # On n'enregistre le sticker que si /sticker a été utilisé
    # --------------------------------------------------------

    if not context.user_data.get(
        "waiting_for_sticker",
        False
    ):

        return

    sticker = update.message.sticker

    sticker_id = sticker.file_id

    CONFIG[
        "completion_sticker_id"
    ] = sticker_id

    persist_config()

    context.user_data[
        "waiting_for_sticker"
    ] = False

    await update.message.reply_text(
        "✅ <b>Sticker enregistré !</b>\n\n"
        "🧩 Il sera envoyé automatiquement "
        "après 3 minutes sans nouvelle vidéo.",
        parse_mode=ParseMode.HTML
    )

    logger.info(
        "🧩 Nouveau sticker de fin enregistré."
    )


# ============================================================
# MENU TELEGRAM
# ============================================================

async def post_init(
    application: Application
):

    commands = [

        BotCommand(
            "start",
            "Démarrer le bot"
        ),

        BotCommand(
            "status",
            "Voir le statut"
        ),

        BotCommand(
            "sources",
            "Voir les sources"
        ),

        BotCommand(
            "destination",
            "Voir la destination"
        ),

        BotCommand(
            "animes",
            "Voir les animes"
        ),

        BotCommand(
            "addsource",
            "Ajouter une source"
        ),

        BotCommand(
            "removesource",
            "Supprimer une source"
        ),

        BotCommand(
            "setdestination",
            "Changer la destination"
        ),

        BotCommand(
            "addanime",
            "Ajouter un anime"
        ),

        BotCommand(
            "removeanime",
            "Supprimer un anime"
        ),

        BotCommand(
            "enableanime",
            "Activer un anime"
        ),

        BotCommand(
            "disableanime",
            "Désactiver un anime"
        ),

        BotCommand(
            "addalias",
            "Ajouter un alias"
        ),

        BotCommand(
            "removealias",
            "Supprimer un alias"
        ),

        BotCommand(
            "sticker",
            "Configurer le sticker"
        ),

        BotCommand(
            "help",
            "Afficher l'aide"
        )
    ]

    await application.bot.set_my_commands(
        commands
    )

    logger.info(
        "📋 Menu Telegram configuré."
    )


# ============================================================
# ERREUR GLOBALE
# ============================================================

async def error_handler(
    update,
    context
):

    logger.error(
        f"❌ Exception : {context.error}"
    )

    if context.error:

        traceback.print_exception(
            type(context.error),
            context.error,
            context.error.__traceback__
        )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "🤖 AUTO FORWARDER démarré..."
    )

    logger.info(
        f"📁 Configuration : {CONFIG_FILE}"
    )

    logger.info(
        f"📡 Sources : "
        f"{CONFIG.get('sources', [])}"
    )

    logger.info(
        f"🎯 Destination : "
        f"{CONFIG.get('destination')}"
    )

    logger.info(
        f"🎬 Animes configurés : "
        f"{len(CONFIG.get('animes', {}))}"
    )

    logger.info(
        "⏱️ Délai sticker : 3 minutes"
    )

    # ========================================================
    # HTTP
    # ========================================================

    request = HTTPXRequest(

        connect_timeout=30.0,

        read_timeout=60.0,

        write_timeout=60.0,

        pool_timeout=30.0
    )

    # ========================================================
    # APPLICATION
    # ========================================================

    application = (
        Application
        .builder()
        .token(TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # ========================================================
    # COMMANDES
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status_command
        )
    )

    application.add_handler(
        CommandHandler(
            "sources",
            sources_command
        )
    )

    application.add_handler(
        CommandHandler(
            "destination",
            destination_command
        )
    )

    application.add_handler(
        CommandHandler(
            "animes",
            animes_command
        )
    )

    application.add_handler(
        CommandHandler(
            "addsource",
            addsource_command
        )
    )

    application.add_handler(
        CommandHandler(
            "removesource",
            removesource_command
        )
    )

    application.add_handler(
        CommandHandler(
            "setdestination",
            setdestination_command
        )
    )

    application.add_handler(
        CommandHandler(
            "addanime",
            addanime_command
        )
    )

    application.add_handler(
        CommandHandler(
            "removeanime",
            removeanime_command
        )
    )

    application.add_handler(
        CommandHandler(
            "enableanime",
            enableanime_command
        )
    )

    application.add_handler(
        CommandHandler(
            "disableanime",
            disableanime_command
        )
    )

    application.add_handler(
        CommandHandler(
            "addalias",
            addalias_command
        )
    )

    application.add_handler(
        CommandHandler(
            "removealias",
            removealias_command
        )
    )

    # ========================================================
    # STICKER
    # ========================================================

    application.add_handler(
        CommandHandler(
            "sticker",
            set_sticker
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Sticker.ALL,
            receive_sticker
        )
    )

    # ========================================================
    # MÉDIAS
    # ========================================================

    media_filter = (
        filters.Document.ALL
        | filters.VIDEO
        | filters.AUDIO
    )

    application.add_handler(
        MessageHandler(
            media_filter,
            handle_message
        )
    )

    # ========================================================
    # ERREURS
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    # ========================================================
    # POLLING
    # ========================================================

    application.run_polling(
        drop_pending_updates=False
    )


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":

    main()