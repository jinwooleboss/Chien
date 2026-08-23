# ============================================================
# ANIME FORWARDER TELEGRAM
# VERSION COMPLETE
# ============================================================
#
# FONCTIONS
#
# - Surveillance des sources Telegram
# - Détection automatique de l'anime
# - Recherche automatique des alias
#   1. Nautiljon
#   2. AniList en fallback
# - Aucun alias à saisir manuellement
# - Copie directe Telegram
# - Aucun téléchargement
# - Aucun renommage
# - Légende automatique
# - Gestion VF / VOSTFR
# - Plusieurs destinations par source
# - Configuration persistante JSON
#
# COMMANDES
#
# /start
# /help
# /config
#
# /sources
# /addsource
# /removesource
#
# /destinations
# /adddestination
# /removedestination
# /linksource
#
# /animes
# /addanime
# /removeanime
# /aliases
#
# ============================================================

import os
import re
import json
import logging
import unicodedata
import asyncio
import requests

from difflib import SequenceMatcher

from bs4 import BeautifulSoup

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from telegram.error import TelegramError


# ============================================================
# CONFIGURATION
# ============================================================

CONFIG_FILE = "config_B.json"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | AnimeForwarder | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("AnimeForwarder")


# ============================================================
# CONFIGURATION PAR DÉFAUT
# ============================================================

DEFAULT_CONFIG = {
    "sources": {},
    "destinations": {},
    "animes": {},
}


# ============================================================
# SAUVEGARDE CONFIG
# ============================================================

def save_config(config):
    tmp_file = CONFIG_FILE + ".tmp"

    try:
        with open(
            tmp_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                config,
                f,
                ensure_ascii=False,
                indent=4
            )

        os.replace(
            tmp_file,
            CONFIG_FILE
        )

    except Exception:
        logger.exception(
            "Erreur sauvegarde configuration"
        )


# ============================================================
# NORMALISATION SOURCES
# ============================================================

def normalize_sources(sources):

    result = {}

    if isinstance(sources, dict):

        for source_id, data in sources.items():

            source_id = str(source_id)

            if isinstance(data, dict):

                title = (
                    data.get("title")
                    or data.get("name")
                    or source_id
                )

                destinations = data.get(
                    "destinations",
                    []
                )

                if isinstance(
                    destinations,
                    str
                ):
                    destinations = [
                        destinations
                    ]

                if not isinstance(
                    destinations,
                    list
                ):
                    destinations = []

                result[source_id] = {
                    "title": str(title),
                    "destinations": [
                        str(x)
                        for x in destinations
                        if x is not None
                    ],
                }

            elif isinstance(data, list):

                result[source_id] = {
                    "title": source_id,
                    "destinations": [
                        str(x)
                        for x in data
                    ],
                }

            else:

                result[source_id] = {
                    "title": str(data),
                    "destinations": [],
                }

    elif isinstance(sources, list):

        for item in sources:

            if isinstance(item, str):

                result[item] = {
                    "title": item,
                    "destinations": [],
                }

                continue

            if not isinstance(item, dict):
                continue

            source_id = (
                item.get("id")
                or item.get("chat_id")
                or item.get("source_id")
                or item.get("channel_id")
            )

            if source_id is None:
                continue

            source_id = str(source_id)

            title = (
                item.get("title")
                or item.get("name")
                or source_id
            )

            destinations = item.get(
                "destinations",
                []
            )

            if isinstance(
                destinations,
                str
            ):
                destinations = [
                    destinations
                ]

            if not isinstance(
                destinations,
                list
            ):
                destinations = []

            result[source_id] = {
                "title": str(title),
                "destinations": [
                    str(x)
                    for x in destinations
                ],
            }

    return result


# ============================================================
# NORMALISATION DESTINATIONS
# ============================================================

def normalize_destinations(destinations):

    result = {}

    if isinstance(
        destinations,
        dict
    ):

        for destination_id, data in destinations.items():

            destination_id = str(
                destination_id
            )

            if isinstance(
                data,
                dict
            ):

                title = (
                    data.get("title")
                    or data.get("name")
                    or destination_id
                )

                result[destination_id] = {
                    "title": str(title)
                }

            elif isinstance(
                data,
                list
            ):

                for destination in data:

                    destination_id_2 = str(
                        destination
                    )

                    result[destination_id_2] = {
                        "title": destination_id_2
                    }

            else:

                result[destination_id] = {
                    "title": str(data)
                }

    elif isinstance(
        destinations,
        list
    ):

        for item in destinations:

            if isinstance(
                item,
                str
            ):

                result[item] = {
                    "title": item
                }

                continue

            if not isinstance(
                item,
                dict
            ):
                continue

            destination_id = (
                item.get("id")
                or item.get("chat_id")
                or item.get("destination_id")
            )

            if destination_id is None:
                continue

            destination_id = str(
                destination_id
            )

            title = (
                item.get("title")
                or item.get("name")
                or destination_id
            )

            result[destination_id] = {
                "title": str(title)
            }

    return result


# ============================================================
# CHARGEMENT CONFIG
# ============================================================

def load_config():

    if not os.path.exists(
        CONFIG_FILE
    ):

        config = DEFAULT_CONFIG.copy()

        save_config(config)

        return config

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(
            data,
            dict
        ):
            data = {}

        config = {
            "sources": normalize_sources(
                data.get(
                    "sources",
                    {}
                )
            ),

            "destinations": normalize_destinations(
                data.get(
                    "destinations",
                    {}
                )
            ),

            "animes": (
                data.get(
                    "animes",
                    {}
                )
                if isinstance(
                    data.get(
                        "animes",
                        {}
                    ),
                    dict
                )
                else {}
            ),
        }

        save_config(config)

        return config

    except Exception:

        logger.exception(
            "Erreur chargement configuration"
        )

        return {
            "sources": {},
            "destinations": {},
            "animes": {},
        }


CONFIG = load_config()


# ============================================================
# NORMALISATION TEXTE
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text)

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text = text.lower()

    text = text.replace(
        "_",
        " "
    )

    text = text.replace(
        ".",
        " "
    )

    text = text.replace(
        "-",
        " "
    )

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
        flags=re.UNICODE
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# ============================================================
# MOTS TECHNIQUES
# ============================================================

TECHNICAL_WORDS = {
    "1080p",
    "720p",
    "2160p",
    "480p",
    "360p",
    "4k",
    "fhd",
    "uhd",
    "hd",

    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "avc",

    "aac",
    "ac3",
    "flac",
    "opus",

    "web",
    "webdl",
    "webrip",

    "bluray",
    "bdrip",
    "bd",

    "multi",
    "dual",
    "audio",

    "vostfr",
    "vost",
    "vf",
    "vo",

    "hardsub",
    "softsub",
    "subbed",
    "dubbed",

    "complete",
    "episode",
    "ep",

    "proper",
    "repack",
    "batch",

    "mkv",
    "mp4",
    "avi",
    "mov",
    "webm",

    "10bit",
    "8bit",

    "aac2",
    "5",
    "1",
    "2",
    "0",
}


# ============================================================
# NETTOYAGE TITRE FICHIER
# ============================================================

def clean_anime_title(filename):

    if not filename:
        return ""

    name = os.path.basename(
        str(filename)
    )

    name = re.sub(
        r"\.(mkv|mp4|avi|mov|webm)$",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = name.replace(
        "_",
        " "
    )

    name = name.replace(
        ".",
        " "
    )

    # Groupe de fansub
    name = re.sub(
        r"\[[^\]]*\]",
        " ",
        name
    )

    # S01E01
    name = re.sub(
        r"\bS\d{1,2}\s*E\d{1,4}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    # S01
    name = re.sub(
        r"\bS\d{1,2}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    # E01
    name = re.sub(
        r"\bE\d{1,4}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    # Episode 01
    name = re.sub(
        r"\bEpisode[\s._-]*\d{1,4}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    words = name.split()

    cleaned = []

    for word in words:

        normalized = normalize_text(
            word
        )

        if normalized in TECHNICAL_WORDS:
            continue

        cleaned.append(word)

    name = " ".join(
        cleaned
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    ).strip()

    return name


# ============================================================
# SAISON
# ============================================================

def extract_season(filename):

    if not filename:
        return 1

    patterns = [
        r"\bS(\d{1,2})\b",
        r"\bSeason[\s._-]*(\d{1,2})\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            filename,
            flags=re.IGNORECASE
        )

        if match:

            try:
                return int(
                    match.group(1)
                )
            except Exception:
                pass

    return 1


# ============================================================
# EPISODE
# ============================================================

def extract_episode(filename):

    if not filename:
        return None

    patterns = [
        r"\bS\d{1,2}\s*E(\d{1,4})\b",
        r"\bS\d{1,2}E(\d{1,4})\b",
        r"\bEP[\s._-]*(\d{1,4})\b",
        r"\bEpisode[\s._-]*(\d{1,4})\b",
        r"\bE[\s._-]*(\d{1,4})\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            filename,
            flags=re.IGNORECASE
        )

        if match:

            try:
                return int(
                    match.group(1)
                )
            except Exception:
                pass

    return None


# ============================================================
# LANGUE
# ============================================================

def detect_language(filename):

    text = normalize_text(
        filename
    )

    vf_patterns = [
        r"\bvf\b",
        r"\bfrench\b",
        r"\bdub\b",
        r"\bdubbed\b",
        r"\bfrancais\b",
    ]

    for pattern in vf_patterns:

        if re.search(
            pattern,
            text
        ):
            return "VF"

    vostfr_patterns = [
        r"\bhardsub\b",
        r"\bvostfr\b",
        r"\bvost\b",
        r"\bsoftsub\b",
        r"\bsubbed\b",
    ]

    for pattern in vostfr_patterns:

        if re.search(
            pattern,
            text
        ):
            return "VOSTFR"

    return "VOSTFR"


# ============================================================
# SIMILARITÉ
# ============================================================

def similarity(a, b):

    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a in b or b in a:
        return 0.95

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


# ============================================================
# NORMALISATION ALIAS
# ============================================================

def normalize_aliases(aliases):

    result = []
    seen = set()

    for alias in aliases:

        if not alias:
            continue

        alias = str(
            alias
        ).strip()

        if len(alias) < 2:
            continue

        normalized = normalize_text(
            alias
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            alias
        )

    return result


# ============================================================
# RECHERCHE NAUTILJON
# ============================================================

def search_nautiljon_aliases(title):

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Linux; Android 13) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Mobile Safari/537.36"
        }

        search_url = (
            "https://www.nautiljon.com/animes/"
            "?q="
            + requests.utils.quote(title)
        )

        response = requests.get(
            search_url,
            headers=headers,
            timeout=15
        )

        if response.status_code != 200:

            logger.warning(
                "Nautiljon HTTP %s",
                response.status_code
            )

            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        best_link = None
        best_score = 0.0

        # ----------------------------------------------------
        # Recherche des résultats
        # ----------------------------------------------------

        for link in soup.find_all(
            "a",
            href=True
        ):

            href = link.get(
                "href",
                ""
            )

            text = link.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            if "/animes/" not in href:
                continue

            score = similarity(
                title,
                text
            )

            if score > best_score:

                best_score = score
                best_link = link

        if not best_link:
            return None

        if best_score < 0.65:

            logger.info(
                "Résultat Nautiljon trop éloigné : %s | %.3f",
                title,
                best_score
            )

            return None

        anime_url = best_link.get(
            "href"
        )

        if anime_url.startswith("/"):

            anime_url = (
                "https://www.nautiljon.com"
                + anime_url
            )

        # ----------------------------------------------------
        # Page anime
        # ----------------------------------------------------

        page = requests.get(
            anime_url,
            headers=headers,
            timeout=15
        )

        if page.status_code != 200:
            return None

        anime_soup = BeautifulSoup(
            page.text,
            "html.parser"
        )

        aliases = []

        # Titre trouvé
        found_title = best_link.get_text(
            " ",
            strip=True
        )

        if found_title:
            aliases.append(
                found_title
            )

        # Titre recherché
        aliases.append(
            title
        )

        # ----------------------------------------------------
        # Recherche des titres dans la page
        # ----------------------------------------------------

        all_text = anime_soup.get_text(
            "\n",
            strip=True
        )

        lines = [
            line.strip()
            for line in all_text.splitlines()
            if line.strip()
        ]

        for index, line in enumerate(lines):

            normalized_line = normalize_text(
                line
            )

            if (
                "titre alternatif" in normalized_line
                or "titres alternatifs" in normalized_line
                or "autre titre" in normalized_line
                or "autres titres" in normalized_line
            ):

                for next_line in lines[
                    index + 1:index + 15
                ]:

                    if len(next_line) > 150:
                        continue

                    if next_line in (
                        title,
                        found_title
                    ):
                        continue

                    aliases.append(
                        next_line
                    )

        # ----------------------------------------------------
        # Métadonnées
        # ----------------------------------------------------

        for meta in anime_soup.find_all(
            "meta"
        ):

            content = meta.get(
                "content"
            )

            if not content:
                continue

            if len(content) > 120:
                continue

            normalized_content = normalize_text(
                content
            )

            if (
                normalized_content
                and (
                    normalize_text(title)
                    in normalized_content
                    or
                    normalized_content
                    in normalize_text(title)
                )
            ):

                aliases.append(
                    content
                )

        aliases = normalize_aliases(
            aliases
        )

        if not aliases:
            return None

        logger.info(
            "Nautiljon trouvé : %s | %s",
            title,
            aliases
        )

        return {
            "aliases": aliases,
            "source": "Nautiljon"
        }

    except Exception:

        logger.exception(
            "Erreur Nautiljon"
        )

        return None


# ============================================================
# RECHERCHE ANILIST
# ============================================================

def search_anilist_aliases(title):

    try:

        url = "https://graphql.anilist.co"

        query = """
        query ($search: String) {
            Media(
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
        """

        response = requests.post(
            url,
            json={
                "query": query,
                "variables": {
                    "search": title
                }
            },
            headers={
                "User-Agent": "AnimeForwarder"
            },
            timeout=15
        )

        if response.status_code != 200:

            logger.warning(
                "AniList HTTP %s",
                response.status_code
            )

            return None

        data = response.json()

        media = (
            data
            .get("data", {})
            .get("Media")
        )

        if not media:
            return None

        aliases = []

        media_title = media.get(
            "title",
            {}
        )

        for key in (
            "romaji",
            "english",
            "native",
            "userPreferred"
        ):

            value = media_title.get(
                key
            )

            if value:
                aliases.append(
                    value
                )

        synonyms = media.get(
            "synonyms",
            []
        )

        if isinstance(
            synonyms,
            list
        ):

            aliases.extend(
                synonyms
            )

        aliases.append(
            title
        )

        aliases = normalize_aliases(
            aliases
        )

        if not aliases:
            return None

        logger.info(
            "AniList trouvé : %s | %s",
            title,
            aliases
        )

        return {
            "aliases": aliases,
            "source": "AniList"
        }

    except Exception:

        logger.exception(
            "Erreur AniList"
        )

        return None


# ============================================================
# RECHERCHE AUTOMATIQUE
# ============================================================

def search_anime_automatically(title):

    logger.info(
        "Recherche automatique : %s",
        title
    )

    # --------------------------------------------------------
    # 1. NAUTILJON
    # --------------------------------------------------------

    result = search_nautiljon_aliases(
        title
    )

    if result:

        return result

    # --------------------------------------------------------
    # 2. ANILIST
    # --------------------------------------------------------

    logger.info(
        "Nautiljon sans résultat. "
        "Fallback AniList."
    )

    result = search_anilist_aliases(
        title
    )

    if result:

        return result

    # --------------------------------------------------------
    # 3. Aucun résultat
    # --------------------------------------------------------

    return {
        "aliases": [
            title
        ],
        "source": "Aucune"
    }


# ============================================================
# DÉTECTION ANIME
# ============================================================

def find_configured_anime(filename):

    if not filename:
        return None

    raw_filename = os.path.basename(
        str(filename)
    )

    cleaned_filename = clean_anime_title(
        raw_filename
    )

    normalized_filename = normalize_text(
        cleaned_filename
    )

    if not normalized_filename:
        return None

    candidates = []

    animes = CONFIG.get(
        "animes",
        {}
    )

    if not isinstance(
        animes,
        dict
    ):
        return None

    for anime_id, anime in animes.items():

        if not isinstance(
            anime,
            dict
        ):
            continue

        title = anime.get(
            "title",
            anime_id
        )

        names = [
            str(title)
        ]

        aliases = anime.get(
            "aliases",
            []
        )

        if isinstance(
            aliases,
            str
        ):
            aliases = [
                aliases
            ]

        if isinstance(
            aliases,
            list
        ):

            names.extend(
                str(alias)
                for alias in aliases
                if alias
            )

        unique_names = []

        seen = set()

        for name in names:

            normalized_name = normalize_text(
                name
            )

            if not normalized_name:
                continue

            if normalized_name in seen:
                continue

            seen.add(
                normalized_name
            )

            unique_names.append(
                normalized_name
            )

        for name in unique_names:

            score = 0.0

            # Exact
            if normalized_filename == name:

                score = 1.0

            # Contenu
            elif (
                len(name) >= 3
                and name in normalized_filename
            ):

                score = 0.97

            else:

                filename_words = (
                    normalized_filename.split()
                )

                name_words = [
                    word
                    for word in name.split()
                    if len(word) >= 3
                ]

                if name_words:

                    matched = 0

                    for word in name_words:

                        for file_word in filename_words:

                            if (
                                word == file_word
                                or similarity(
                                    word,
                                    file_word
                                ) >= 0.92
                            ):

                                matched += 1
                                break

                    word_score = (
                        matched
                        / len(name_words)
                    )

                    full_score = similarity(
                        normalized_filename,
                        name
                    )

                    score = max(
                        full_score,
                        word_score * 0.95
                    )

            candidates.append(
                (
                    score,
                    anime_id,
                    anime,
                    name
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    best_score, anime_id, anime, matched_name = (
        candidates[0]
    )

    if best_score < 0.70:

        logger.info(
            "Anime non reconnu | fichier=%s | score=%.3f",
            filename,
            best_score
        )

        return None

    logger.info(
        "Anime reconnu | %s | alias=%s | score=%.3f",
        anime.get(
            "title",
            anime_id
        ),
        matched_name,
        best_score
    )

    return anime_id, anime


# ============================================================
# CAPTION
# ============================================================

def build_caption(
    anime,
    filename
):

    title = anime.get(
        "title",
        "Anime"
    )

    season = extract_season(
        filename
    )

    episode = extract_episode(
        filename
    )

    language = detect_language(
        filename
    )

    if episode is not None:

        return (
            f"🎬 {title}\n"
            f"📀 Saison {season:02d} — "
            f"Épisode {episode:02d}\n"
            f"🌐 {language}"
        )

    return (
        f"🎬 {title}\n"
        f"📀 Saison {season:02d}\n"
        f"🌐 {language}"
    )


# ============================================================
# LABEL SOURCE
# ============================================================

def source_label(source_id):

    source = CONFIG.get(
        "sources",
        {}
    ).get(
        str(source_id),
        {}
    )

    if isinstance(
        source,
        dict
    ):

        return source.get(
            "title",
            str(source_id)
        )

    return str(source_id)


# ============================================================
# LABEL DESTINATION
# ============================================================

def destination_label(destination_id):

    destination = CONFIG.get(
        "destinations",
        {}
    ).get(
        str(destination_id),
        {}
    )

    if isinstance(
        destination,
        dict
    ):

        return destination.get(
            "title",
            str(destination_id)
        )

    return str(destination_id)


# ============================================================
# DESTINATIONS SOURCE
# ============================================================

def get_destinations_for_source(
    source_id
):

    source = CONFIG.get(
        "sources",
        {}
    ).get(
        str(source_id)
    )

    if not isinstance(
        source,
        dict
    ):
        return []

    destinations = source.get(
        "destinations",
        []
    )

    if isinstance(
        destinations,
        str
    ):
        destinations = [
            destinations
        ]

    if not isinstance(
        destinations,
        list
    ):
        return []

    return [
        str(x)
        for x in destinations
        if x is not None
    ]


# ============================================================
# START
# ============================================================

START_TEXT = """
🤖 <b>ANIME FORWARDER</b>

Voici <b>toutes les commandes disponibles</b> :

━━━━━━━━━━━━━━━━━━
📌 <b>GÉNÉRAL</b>
━━━━━━━━━━━━━━━━━━

/start
→ Afficher toutes les commandes

/help
→ Afficher toutes les commandes

/config
→ Menu de configuration

━━━━━━━━━━━━━━━━━━
📡 <b>SOURCES</b>
━━━━━━━━━━━━━━━━━━

/sources
→ Voir les sources

/addsource
→ Ajouter une source

Format :
<code>/addsource ID Nom</code>

/removesource
→ Supprimer une source

Format :
<code>/removesource ID</code>

━━━━━━━━━━━━━━━━━━
📤 <b>DESTINATIONS</b>
━━━━━━━━━━━━━━━━━━

/destinations
→ Voir les destinations

/adddestination
→ Ajouter une destination

Format :
<code>/adddestination ID Nom</code>

/removedestination
→ Supprimer une destination

Format :
<code>/removedestination ID</code>

/linksource
→ Relier source et destination

Format :
<code>/linksource SOURCE DESTINATION</code>

Plusieurs destinations :

<code>/linksource SOURCE DEST1 DEST2 DEST3</code>

━━━━━━━━━━━━━━━━━━
🎬 <b>ANIMES</b>
━━━━━━━━━━━━━━━━━━

/animes
→ Voir les animes

/addanime
→ Ajouter un anime

Format :

<code>/addanime Nom de l'anime</code>

💡 Les alias sont recherchés automatiquement.

Nautiljon est utilisé en premier.

AniList est utilisé automatiquement
si Nautiljon ne trouve rien.

/removeanime
→ Supprimer un anime

Format :
<code>/removeanime identifiant</code>

/aliases
→ Voir les alias récupérés

Format :
<code>/aliases identifiant</code>

━━━━━━━━━━━━━━━━━━
⚙️ <b>FONCTIONNEMENT</b>
━━━━━━━━━━━━━━━━━━

Le bot surveille les sources.

Il analyse le nom du fichier.

Il recherche automatiquement
l'anime configuré.

Puis il copie directement
le message vers les destinations.

📥 Aucun téléchargement
🔄 Copie Telegram
✏️ Aucun renommage
📝 Légende automatique

━━━━━━━━━━━━━━━━━━
🌐 <b>LANGUES</b>
━━━━━━━━━━━━━━━━━━

HARDSUB → VOSTFR
VOSTFR → VOSTFR
VOST → VOSTFR
VF → VF
"""


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    await message.reply_text(
        START_TEXT,
        parse_mode="HTML"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await start_command(
        update,
        context
    )


# ============================================================
# SOURCES
# ============================================================

async def sources_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    sources = CONFIG.get(
        "sources",
        {}
    )

    if not sources:

        await message.reply_text(
            "📭 Aucune source configurée.\n\n"
            "Utilise :\n"
            "<code>/addsource ID Nom</code>",
            parse_mode="HTML"
        )

        return

    lines = [
        "📡 <b>SOURCES CONFIGURÉES</b>\n"
    ]

    for source_id, source in sources.items():

        if not isinstance(
            source,
            dict
        ):
            continue

        title = source.get(
            "title",
            source_id
        )

        destinations = source.get(
            "destinations",
            []
        )

        lines.append(
            f"📥 <b>{title}</b>"
        )

        lines.append(
            f"🆔 <code>{source_id}</code>"
        )

        if destinations:

            lines.append(
                "📤 Destinations :"
            )

            for destination_id in destinations:

                lines.append(
                    f"   • "
                    f"{destination_label(destination_id)} "
                    f"(<code>{destination_id}</code>)"
                )

        else:

            lines.append(
                "⚠️ Aucune destination liée"
            )

        lines.append("")

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ============================================================
# ADDSOURCE
# ============================================================

async def addsource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/addsource ID Nom de la source</code>",
            parse_mode="HTML"
        )

        return

    source_id = str(
        context.args[0]
    )

    title = " ".join(
        context.args[1:]
    ).strip()

    if not title:
        title = source_id

    old_source = CONFIG[
        "sources"
    ].get(
        source_id,
        {}
    )

    old_destinations = []

    if isinstance(
        old_source,
        dict
    ):

        old_destinations = old_source.get(
            "destinations",
            []
        )

        if not isinstance(
            old_destinations,
            list
        ):
            old_destinations = []

    CONFIG[
        "sources"
    ][source_id] = {
        "title": title,
        "destinations": old_destinations,
    }

    save_config(
        CONFIG
    )

    await message.reply_text(
        "✅ <b>Source ajoutée</b>\n\n"
        f"📥 {title}\n"
        f"🆔 <code>{source_id}</code>\n\n"
        "Relie-la maintenant avec :\n"
        f"<code>/linksource {source_id} DESTINATION_ID</code>",
        parse_mode="HTML"
    )


# ============================================================
# REMOVESOURCE
# ============================================================

async def removesource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ Utilisation :\n"
            "<code>/removesource ID</code>",
            parse_mode="HTML"
        )

        return

    source_id = str(
        context.args[0]
    )

    source = CONFIG[
        "sources"
    ].pop(
        source_id,
        None
    )

    if source is None:

        await message.reply_text(
            "❌ Source introuvable."
        )

        return

    save_config(
        CONFIG
    )

    title = (
        source.get(
            "title",
            source_id
        )
        if isinstance(
            source,
            dict
        )
        else source_id
    )

    await message.reply_text(
        f"✅ Source supprimée : <b>{title}</b>",
        parse_mode="HTML"
    )


# ============================================================
# DESTINATIONS
# ============================================================

async def destinations_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    destinations = CONFIG.get(
        "destinations",
        {}
    )

    if not destinations:

        await message.reply_text(
            "📭 Aucune destination configurée.\n\n"
            "Utilise :\n"
            "<code>/adddestination ID Nom</code>",
            parse_mode="HTML"
        )

        return

    lines = [
        "📤 <b>DESTINATIONS CONFIGURÉES</b>\n"
    ]

    for destination_id, destination in destinations.items():

        if not isinstance(
            destination,
            dict
        ):
            continue

        title = destination.get(
            "title",
            destination_id
        )

        lines.append(
            f"📤 <b>{title}</b>"
        )

        lines.append(
            f"🆔 <code>{destination_id}</code>"
        )

        lines.append("")

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ============================================================
# ADDDESTINATION
# ============================================================

async def adddestination_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/adddestination ID Nom</code>",
            parse_mode="HTML"
        )

        return

    destination_id = str(
        context.args[0]
    )

    title = " ".join(
        context.args[1:]
    ).strip()

    if not title:
        title = destination_id

    CONFIG[
        "destinations"
    ][destination_id] = {
        "title": title
    }

    save_config(
        CONFIG
    )

    await message.reply_text(
        "✅ <b>Destination ajoutée</b>\n\n"
        f"📤 {title}\n"
        f"🆔 <code>{destination_id}</code>\n\n"
        "Relie-la avec :\n"
        f"<code>/linksource SOURCE_ID {destination_id}</code>",
        parse_mode="HTML"
    )


# ============================================================
# REMOVEDESTINATION
# ============================================================

async def removedestination_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ Utilisation :\n"
            "<code>/removedestination ID</code>",
            parse_mode="HTML"
        )

        return

    destination_id = str(
        context.args[0]
    )

    destination = CONFIG[
        "destinations"
    ].pop(
        destination_id,
        None
    )

    if destination is None:

        await message.reply_text(
            "❌ Destination introuvable."
        )

        return

    for source in CONFIG[
        "sources"
    ].values():

        if not isinstance(
            source,
            dict
        ):
            continue

        destinations = source.get(
            "destinations",
            []
        )

        if isinstance(
            destinations,
            list
        ):

            source[
                "destinations"
            ] = [
                x
                for x in destinations
                if str(x) != destination_id
            ]

    save_config(
        CONFIG
    )

    title = (
        destination.get(
            "title",
            destination_id
        )
        if isinstance(
            destination,
            dict
        )
        else destination_id
    )

    await message.reply_text(
        f"✅ Destination supprimée : <b>{title}</b>",
        parse_mode="HTML"
    )


# ============================================================
# LINKSOURCE
# ============================================================

async def linksource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if len(
        context.args
    ) < 2:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/linksource SOURCE DESTINATION</code>\n\n"
            "Plusieurs destinations :\n"
            "<code>/linksource SOURCE DEST1 DEST2 DEST3</code>",
            parse_mode="HTML"
        )

        return

    source_id = str(
        context.args[0]
    )

    destination_ids = [
        str(x)
        for x in context.args[1:]
    ]

    if source_id not in CONFIG[
        "sources"
    ]:

        await message.reply_text(
            "❌ Source introuvable.\n\n"
            "Ajoute-la avec :\n"
            f"<code>/addsource {source_id} Nom</code>",
            parse_mode="HTML"
        )

        return

    missing = [
        destination_id
        for destination_id in destination_ids
        if destination_id not in CONFIG[
            "destinations"
        ]
    ]

    if missing:

        await message.reply_text(
            "❌ Destination(s) introuvable(s) :\n\n"
            + "\n".join(
                f"• <code>{x}</code>"
                for x in missing
            ),
            parse_mode="HTML"
        )

        return

    source = CONFIG[
        "sources"
    ][source_id]

    current = source.get(
        "destinations",
        []
    )

    if not isinstance(
        current,
        list
    ):
        current = []

    added = []

    for destination_id in destination_ids:

        if destination_id not in current:

            current.append(
                destination_id
            )

            added.append(
                destination_id
            )

    source[
        "destinations"
    ] = current

    save_config(
        CONFIG
    )

    if not added:

        await message.reply_text(
            "ℹ️ Ces destinations sont déjà liées."
        )

        return

    lines = [
        "✅ <b>SOURCE RELIÉE</b>\n",
        f"📥 {source_label(source_id)}",
        f"🆔 <code>{source_id}</code>",
        "",
        "📤 Destinations :",
    ]

    for destination_id in added:

        lines.append(
            f"• {destination_label(destination_id)} "
            f"(<code>{destination_id}</code>)"
        )

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ============================================================
# ANIMES
# ============================================================

async def list_animes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    animes = CONFIG.get(
        "animes",
        {}
    )

    if not animes:

        await message.reply_text(
            "📭 Aucun anime configuré.\n\n"
            "Ajoute-en un avec :\n"
            "<code>/addanime Nom de l'anime</code>",
            parse_mode="HTML"
        )

        return

    lines = [
        "📚 <b>ANIMES CONFIGURÉS</b>\n"
    ]

    for anime_id, anime in animes.items():

        if not isinstance(
            anime,
            dict
        ):
            continue

        title = anime.get(
            "title",
            anime_id
        )

        aliases = anime.get(
            "aliases",
            []
        )

        source = anime.get(
            "alias_source",
            "Inconnue"
        )

        lines.append(
            f"🎬 <b>{title}</b>"
        )

        lines.append(
            f"🆔 <code>{anime_id}</code>"
        )

        lines.append(
            f"🔹 Alias : {len(aliases)}"
        )

        lines.append(
            f"🌐 Source : {source}"
        )

        lines.append("")

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ============================================================
# ADDANIME AUTOMATIQUE
# ============================================================

async def addanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ <b>Nom de l'anime manquant.</b>\n\n"
            "Utilisation :\n"
            "<code>/addanime Nom de l'anime</code>\n\n"
            "Les alias seront recherchés automatiquement.",
            parse_mode="HTML"
        )

        return

    title = " ".join(
        context.args
    ).strip()

    if not title:

        await message.reply_text(
            "❌ Nom invalide."
        )

        return

    status = await message.reply_text(
        "🔎 <b>RECHERCHE AUTOMATIQUE</b>\n\n"
        f"🎬 {title}\n\n"
        "🌐 Recherche sur Nautiljon...",
        parse_mode="HTML"
    )

    try:

        result = await asyncio.to_thread(
            search_anime_automatically,
            title
        )

        aliases = result.get(
            "aliases",
            [title]
        )

        source = result.get(
            "source",
            "Aucune"
        )

        aliases = normalize_aliases(
            aliases
        )

        if title not in aliases:

            aliases.insert(
                0,
                title
            )

        # ----------------------------------------------------
        # ID
        # ----------------------------------------------------

        anime_id = normalize_text(
            title
        )

        anime_id = re.sub(
            r"\s+",
            "_",
            anime_id
        )

        if not anime_id:

            await status.edit_text(
                "❌ Impossible de créer l'identifiant."
            )

            return

        # ----------------------------------------------------
        # Sauvegarde
        # ----------------------------------------------------

        CONFIG[
            "animes"
        ][anime_id] = {
            "title": title,
            "aliases": aliases,
            "alias_source": source,
        }

        save_config(
            CONFIG
        )

        # ----------------------------------------------------
        # Affichage
        # ----------------------------------------------------

        lines = [
            "✅ <b>ANIME AJOUTÉ</b>\n",
            f"🎬 <b>{title}</b>",
            f"🆔 <code>{anime_id}</code>",
            "",
            f"🌐 Source : <b>{source}</b>",
            f"🔹 Alias trouvés : <b>{len(aliases)}</b>",
            "",
            "📋 <b>Alias :</b>",
        ]

        for alias in aliases[:30]:

            lines.append(
                f"• {alias}"
            )

        if len(aliases) > 30:

            lines.append(
                f"\n... et {len(aliases) - 30} autres"
            )

        lines.extend([
            "",
            "🤖 Aucun alias manuel nécessaire."
        ])

        await status.edit_text(
            "\n".join(lines),
            parse_mode="HTML"
        )

        logger.info(
            "Anime ajouté | %s | %s alias | source=%s",
            title,
            len(aliases),
            source
        )

    except Exception:

        logger.exception(
            "Erreur /addanime"
        )

        await status.edit_text(
            "❌ Une erreur est survenue "
            "pendant la recherche automatique."
        )


# ============================================================
# REMOVEANIME
# ============================================================

async def removeanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ Utilisation :\n"
            "<code>/removeanime identifiant</code>",
            parse_mode="HTML"
        )

        return

    anime_id = normalize_text(
        " ".join(
            context.args
        )
    ).replace(
        " ",
        "_"
    )

    anime = CONFIG[
        "animes"
    ].pop(
        anime_id,
        None
    )

    if anime is None:

        await message.reply_text(
            "❌ Anime introuvable."
        )

        return

    save_config(
        CONFIG
    )

    title = anime.get(
        "title",
        anime_id
    )

    await message.reply_text(
        f"✅ Anime supprimé : <b>{title}</b>",
        parse_mode="HTML"
    )


# ============================================================
# ALIASES
# ============================================================

async def aliases_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if not context.args:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/aliases identifiant</code>",
            parse_mode="HTML"
        )

        return

    anime_id = normalize_text(
        " ".join(
            context.args
        )
    ).replace(
        " ",
        "_"
    )

    anime = CONFIG[
        "animes"
    ].get(
        anime_id
    )

    if not anime:

        await message.reply_text(
            "❌ Anime introuvable."
        )

        return

    aliases = anime.get(
        "aliases",
        []
    )

    if not aliases:

        await message.reply_text(
            "📭 Aucun alias enregistré."
        )

        return

    source = anime.get(
        "alias_source",
        "Inconnue"
    )

    lines = [
        f"🎬 <b>{anime.get('title', anime_id)}</b>",
        f"🌐 Source : <b>{source}</b>",
        "",
        "🔹 <b>Alias :</b>",
    ]

    for alias in aliases:

        lines.append(
            f"• {alias}"
        )

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ============================================================
# CONFIG
# ============================================================

async def config_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📡 Sources",
                callback_data="cfg_sources"
            ),
            InlineKeyboardButton(
                "📤 Destinations",
                callback_data="cfg_destinations"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎬 Animes",
                callback_data="cfg_animes"
            ),
        ],
    ]

    await message.reply_text(
        "⚙️ <b>CONFIGURATION</b>\n\n"
        "Choisis une section :",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML"
    )


# ============================================================
# CALLBACK
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "cfg_sources":

        await query.edit_message_text(
            "📡 <b>SOURCES</b>\n\n"
            "/sources → Voir\n"
            "/addsource → Ajouter\n"
            "/removesource → Supprimer\n"
            "/linksource → Relier",
            parse_mode="HTML"
        )

    elif query.data == "cfg_destinations":

        await query.edit_message_text(
            "📤 <b>DESTINATIONS</b>\n\n"
            "/destinations → Voir\n"
            "/adddestination → Ajouter\n"
            "/removedestination → Supprimer\n"
            "/linksource → Relier",
            parse_mode="HTML"
        )

    elif query.data == "cfg_animes":

        await query.edit_message_text(
            "🎬 <b>ANIMES</b>\n\n"
            "/animes → Voir\n"
            "/addanime → Ajouter automatiquement\n"
            "/removeanime → Supprimer\n"
            "/aliases → Voir les alias",
            parse_mode="HTML"
        )


# ============================================================
# NOM FICHIER
# ============================================================

def get_filename_from_message(message):

    if not message:
        return None

    if message.document:

        return (
            message.document.file_name
            or "document"
        )

    if message.video:

        return (
            message.video.file_name
            or "video"
        )

    if message.audio:

        return (
            message.audio.file_name
            or "audio"
        )

    return None


# ============================================================
# TRAITEMENT MESSAGE
# ============================================================

async def process_source_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    chat = update.effective_chat

    if not chat:
        return

    source_id = str(
        chat.id
    )

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    source = CONFIG.get(
        "sources",
        {}
    ).get(
        source_id
    )

    if not isinstance(
        source,
        dict
    ):

        return

    # --------------------------------------------------------
    # Fichier
    # --------------------------------------------------------

    filename = get_filename_from_message(
        message
    )

    if not filename:
        return

    logger.info(
        "Fichier reçu | source=%s | %s",
        source_id,
        filename
    )

    # --------------------------------------------------------
    # Destinations
    # --------------------------------------------------------

    destinations = get_destinations_for_source(
        source_id
    )

    if not destinations:

        logger.warning(
            "Aucune destination pour %s",
            source_id
        )

        return

    # --------------------------------------------------------
    # Anime
    # --------------------------------------------------------

    detected = find_configured_anime(
        filename
    )

    if not detected:

        logger.info(
            "Anime non configuré : %s",
            filename
        )

        return

    anime_id, anime = detected

    # --------------------------------------------------------
    # Caption
    # --------------------------------------------------------

    caption = build_caption(
        anime,
        filename
    )

    logger.info(
        "Copie de %s | %s",
        anime.get(
            "title",
            anime_id
        ),
        filename
    )

    # --------------------------------------------------------
    # Copie
    # --------------------------------------------------------

    for destination_id in destinations:

        try:

            destination_id_int = int(
                destination_id
            )

        except ValueError:

            logger.error(
                "ID destination invalide : %s",
                destination_id
            )

            continue

        try:

            await context.bot.copy_message(
                chat_id=destination_id_int,
                from_chat_id=chat.id,
                message_id=message.message_id,
                caption=caption,
            )

            logger.info(
                "Copie réussie : %s -> %s",
                source_id,
                destination_id
            )

        except TelegramError as error:

            logger.error(
                "Erreur Telegram : %s",
                error
            )

        except Exception:

            logger.exception(
                "Erreur copie"
            )


# ============================================================
# CHANNEL POST
# ============================================================

async def channel_post_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        await process_source_message(
            update,
            context
        )

    except Exception:

        logger.exception(
            "Erreur channel_post"
        )


# ============================================================
# MESSAGES GROUPES
# ============================================================

async def normal_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        message = update.effective_message

        if not message:
            return

        chat = update.effective_chat

        if not chat:
            return

        if chat.type == "private":
            return

        await process_source_message(
            update,
            context
        )

    except Exception:

        logger.exception(
            "Erreur message"
        )


# ============================================================
# COMMANDES TELEGRAM
# ============================================================

async def post_init(
    application: Application
):

    commands = [
        BotCommand(
            "start",
            "Afficher toutes les commandes"
        ),
        BotCommand(
            "help",
            "Afficher toutes les commandes"
        ),
        BotCommand(
            "config",
            "Configuration"
        ),
        BotCommand(
            "sources",
            "Voir les sources"
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
            "destinations",
            "Voir les destinations"
        ),
        BotCommand(
            "adddestination",
            "Ajouter une destination"
        ),
        BotCommand(
            "removedestination",
            "Supprimer une destination"
        ),
        BotCommand(
            "linksource",
            "Relier source et destination"
        ),
        BotCommand(
            "animes",
            "Voir les animes"
        ),
        BotCommand(
            "addanime",
            "Ajouter automatiquement un anime"
        ),
        BotCommand(
            "removeanime",
            "Supprimer un anime"
        ),
        BotCommand(
            "aliases",
            "Voir les alias"
        ),
    ]

    try:

        await application.bot.set_my_commands(
            commands
        )

        logger.info(
            "Commandes Telegram configurées."
        )

    except Exception:

        logger.exception(
            "Erreur configuration commandes"
        )


# ============================================================
# ERREUR
# ============================================================

async def error_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Erreur Telegram : %s",
        context.error,
        exc_info=context.error
    )


# ============================================================
# CONFIG AU DÉMARRAGE
# ============================================================

def log_configuration():

    logger.info(
        "=========================================="
    )

    logger.info(
        "CONFIGURATION DU BOT"
    )

    logger.info(
        "=========================================="
    )

    sources = CONFIG.get(
        "sources",
        {}
    )

    logger.info(
        "Sources : %d",
        len(sources)
    )

    for source_id, source in sources.items():

        if not isinstance(
            source,
            dict
        ):
            continue

        logger.info(
            "Source : %s | %s | destinations=%s",
            source_id,
            source.get(
                "title",
                source_id
            ),
            source.get(
                "destinations",
                []
            )
        )

    destinations = CONFIG.get(
        "destinations",
        {}
    )

    logger.info(
        "Destinations : %d",
        len(destinations)
    )

    for destination_id, destination in destinations.items():

        if isinstance(
            destination,
            dict
        ):

            title = destination.get(
                "title",
                destination_id
            )

        else:

            title = destination_id

        logger.info(
            "Destination : %s | %s",
            destination_id,
            title
        )

    animes = CONFIG.get(
        "animes",
        {}
    )

    logger.info(
        "Animes : %d",
        len(animes)
    )

    for anime_id, anime in animes.items():

        if not isinstance(
            anime,
            dict
        ):
            continue

        logger.info(
            "Anime : %s | alias=%d | source=%s",
            anime.get(
                "title",
                anime_id
            ),
            len(
                anime.get(
                    "aliases",
                    []
                )
            ),
            anime.get(
                "alias_source",
                "?"
            )
        )

    logger.info(
        "=========================================="
    )

    save_config(
        CONFIG
    )


# ============================================================
# MAIN
# ============================================================

def main():

    log_configuration()

    application = (
        Application.builder()
        .token(
            os.getenv(
                "BOT_TOKEN",
                "8734390269:AAF0K4N-8Crsr1Tjsy50FQS6RwemjVShma0"
            )
        )
        .post_init(
            post_init
        )
        .build()
    )

    # --------------------------------------------------------
    # COMMANDES
    # --------------------------------------------------------

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
            "config",
            config_command
        )
    )

    # --------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "sources",
            sources_command
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

    # --------------------------------------------------------
    # DESTINATIONS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "destinations",
            destinations_command
        )
    )

    application.add_handler(
        CommandHandler(
            "adddestination",
            adddestination_command
        )
    )

    application.add_handler(
        CommandHandler(
            "removedestination",
            removedestination_command
        )
    )

    application.add_handler(
        CommandHandler(
            "linksource",
            linksource_command
        )
    )

    # --------------------------------------------------------
    # ANIMES
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "animes",
            list_animes
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
            "aliases",
            aliases_command
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # --------------------------------------------------------
    # PUBLICATIONS CANAUX
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST
            & ~filters.COMMAND,
            channel_post_handler
        )
    )

    # --------------------------------------------------------
    # MESSAGES GROUPES
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & ~filters.COMMAND,
            normal_message_handler
        ),
        group=10
    )

    # --------------------------------------------------------
    # ERREURS
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "=========================================="
    )

    logger.info(
        "BOT PRÊT"
    )

    logger.info(
        "=========================================="
    )

    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "channel_post",
            "callback_query",
        ]
    )


# ============================================================
# START PROGRAMME
# ============================================================

if __name__ == "__main__":
    main()