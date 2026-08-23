# ============================================================
# ANIME FORWARDER TELEGRAM
# VERSION COMPLETE CORRIGÉE
# ============================================================
#
# FONCTIONNEMENT
#
# 1. Surveillance des canaux SOURCES configurés
# 2. Analyse uniquement du NOM DU FICHIER
# 3. Détection de l'anime configuré
# 4. Copie directe vers les DESTINATIONS
# 5. Aucun téléchargement
# 6. Aucun renommage
# 7. Ajout automatique d'une légende
#
# LANGUES :
# HARDSUB -> VOSTFR
# VOSTFR  -> VOSTFR
# VOST    -> VOSTFR
# VF      -> VF
#
# COMMANDES :
#
# /start
# /help
#
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
# Compatible python-telegram-bot 20+
# ============================================================

import os
import re
import json
import logging
import unicodedata

from difflib import SequenceMatcher

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "8734390269:AAF0K4N-8Crsr1Tjsy50FQS6RwemjVShma0").strip()

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
# OUTILS CONFIG
# ============================================================

def save_config(config):
    """
    Sauvegarde la configuration de façon atomique.
    """

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
# NORMALISATION DES SOURCES
# ============================================================

def normalize_sources(sources):
    """
    Convertit TOUS les anciens formats en dictionnaire.

    Format final :

    {
        "-100123": {
            "title": "Source",
            "destinations": []
        }
    }
    """

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

                destinations = [
                    str(x)
                    for x in destinations
                    if x is not None
                ]

                result[source_id] = {
                    "title": str(title),
                    "destinations": destinations,
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

            # Ancien format :
            # "-100123"

            if isinstance(
                item,
                str
            ):

                source_id = item

                result[source_id] = {
                    "title": source_id,
                    "destinations": [],
                }

                continue

            # Format :
            # {"id": "-100123", "name": "Source"}

            if isinstance(
                item,
                dict
            ):

                source_id = (
                    item.get("id")
                    or item.get("chat_id")
                    or item.get("source_id")
                    or item.get("channel_id")
                )

                if source_id is None:
                    continue

                source_id = str(
                    source_id
                )

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
    """
    Convertit les anciens formats de destinations
    vers un dictionnaire uniforme.

    Format final :

    {
        "-100123": {
            "title": "Destination"
        }
    }
    """

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

                # Cas ancien format étrange :
                # {"source": ["dest1", "dest2"]}

                for destination in data:

                    destination_id_2 = str(
                        destination
                    )

                    if destination_id_2 not in result:

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

                destination_id = item

                result[destination_id] = {
                    "title": destination_id
                }

                continue

            if isinstance(
                item,
                dict
            ):

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
# CHARGEMENT CONFIGURATION
# ============================================================

def load_config():

    if not os.path.exists(
        CONFIG_FILE
    ):

        config = {
            "sources": {},
            "destinations": {},
            "animes": {},
        }

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

        sources = normalize_sources(
            data.get(
                "sources",
                {}
            )
        )

        destinations = normalize_destinations(
            data.get(
                "destinations",
                {}
            )
        )

        animes = data.get(
            "animes",
            {}
        )

        if not isinstance(
            animes,
            dict
        ):
            animes = {}

        config = {
            "sources": sources,
            "destinations": destinations,
            "animes": animes,
        }

        # Réécrit automatiquement la configuration
        # dans le nouveau format.
        save_config(config)

        return config

    except Exception:

        logger.exception(
            "Erreur chargement config"
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
# NETTOYAGE TITRE
# ============================================================

def clean_anime_title(filename):

    if not filename:
        return ""

    name = os.path.basename(
        filename
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

    # [Groupe]
    name = re.sub(
        r"\[[^\]]*\]",
        " ",
        name
    )

    # Saison + épisode
    name = re.sub(
        r"\bS\d{1,2}\s*E\d{1,4}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(
        r"\bS\d{1,2}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(
        r"\bE\d{1,4}\b",
        " ",
        name,
        flags=re.IGNORECASE
    )

    # Episode seul
    name = re.sub(
        r"(?<!\w)#?\d{1,3}(?!\w)",
        " ",
        name
    )

    words = name.split()

    cleaned = []

    for word in words:

        normalized = normalize_text(
            word
        )

        if normalized in TECHNICAL_WORDS:
            continue

        cleaned.append(
            word
        )

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

        r"\bE[\s._-]*(\d{1,4})\b",

        r"\bEpisode[\s._-]*(\d{1,4})\b",
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

    # VF prioritaire
    vf_patterns = [
        r"\bvf\b",
        r"\bfrench\b",
        r"\bdub\b",
        r"\bdubbed\b",
        r"\bfrancais\b",
        r"\bfrançais\b",
    ]

    for pattern in vf_patterns:

        if re.search(
            pattern,
            text
        ):

            return "VF"

    # HARDSUB = VOSTFR
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
# DÉTECTION ANIME
# ============================================================

def find_configured_anime(filename):

    if not filename:
        return None

    filename_normalized = normalize_text(
        filename
    )

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

        # Titre principal
        title_normalized = normalize_text(
            title
        )

        if (
            title_normalized
            and title_normalized in filename_normalized
        ):

            candidates.append(
                (
                    1.0,
                    anime_id,
                    anime
                )
            )

        else:

            candidates.append(
                (
                    similarity(
                        filename_normalized,
                        title
                    ),
                    anime_id,
                    anime
                )
            )

        # Alias
        for alias in aliases:

            if not alias:
                continue

            alias_normalized = normalize_text(
                alias
            )

            if (
                alias_normalized
                and alias_normalized in filename_normalized
            ):

                candidates.append(
                    (
                        1.0,
                        anime_id,
                        anime
                    )
                )

            else:

                candidates.append(
                    (
                        similarity(
                            filename_normalized,
                            alias
                        ),
                        anime_id,
                        anime
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    best_score, anime_id, anime = candidates[0]

    logger.info(
        "Meilleur score anime : %.3f | %s",
        best_score,
        anime.get(
            "title",
            anime_id
        )
    )

    if best_score < 0.55:
        return None

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
# DESTINATIONS D'UNE SOURCE
# ============================================================

def get_destinations_for_source(
    source_id
):

    source_id = str(
        source_id
    )

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
# START / HELP
# ============================================================

START_TEXT = """
🤖 <b>ANIME FORWARDER</b>

Bienvenue !

Voici <b>TOUTES les commandes disponibles</b> :

━━━━━━━━━━━━━━━━━━
📌 <b>GÉNÉRAL</b>
━━━━━━━━━━━━━━━━━━

/start
→ Afficher toutes les commandes

/help
→ Afficher toutes les commandes

/config
→ Ouvrir le menu de configuration

━━━━━━━━━━━━━━━━━━
📡 <b>SOURCES</b>
━━━━━━━━━━━━━━━━━━

/sources
→ Afficher toutes les sources

/addsource
→ Ajouter une source

Format :
<code>/addsource ID Nom</code>

Exemple :
<code>/addsource -1001234567890 Mon Canal</code>

/removesource
→ Supprimer une source

Format :
<code>/removesource ID</code>

━━━━━━━━━━━━━━━━━━
📤 <b>DESTINATIONS</b>
━━━━━━━━━━━━━━━━━━

/destinations
→ Afficher toutes les destinations

/adddestination
→ Ajouter une destination

Format :
<code>/adddestination ID Nom</code>

Exemple :
<code>/adddestination -1009876543210 Mon Canal Final</code>

/removedestination
→ Supprimer une destination

Format :
<code>/removedestination ID</code>

/linksource
→ Relier une source à une destination

Format :
<code>/linksource SOURCE DESTINATION</code>

Plusieurs destinations :

<code>/linksource SOURCE DEST1 DEST2 DEST3</code>

━━━━━━━━━━━━━━━━━━
🎬 <b>ANIMES</b>
━━━━━━━━━━━━━━━━━━

/animes
→ Afficher les animes configurés

/addanime
→ Ajouter un anime

Format :
<code>/addanime Titre | Alias 1 | Alias 2</code>

/removeanime
→ Supprimer un anime

Format :
<code>/removeanime identifiant</code>

/aliases
→ Afficher les alias d'un anime

Format :
<code>/aliases identifiant</code>

━━━━━━━━━━━━━━━━━━
⚙️ <b>FONCTIONNEMENT</b>
━━━━━━━━━━━━━━━━━━

Le bot surveille les sources configurées.

Il regarde uniquement le <b>nom du fichier</b>.

Si l'anime est reconnu :

• 📥 aucune téléchargement
• 🔄 copie directe Telegram
• ✏️ aucun renommage
• 📝 légende automatique
• 📤 envoi vers les destinations

━━━━━━━━━━━━━━━━━━
🌐 <b>LANGUES</b>
━━━━━━━━━━━━━━━━━━

HARDSUB → VOSTFR
VOSTFR → VOSTFR
VOST → VOSTFR
VF → VF

━━━━━━━━━━━━━━━━━━
⚠️ <b>IMPORTANT</b>
━━━━━━━━━━━━━━━━━━

Le bot doit avoir accès aux canaux concernés.

Pour une source, ajoute le bot au canal afin qu'il puisse recevoir les publications.

Pour une destination, donne-lui les droits nécessaires pour publier.
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
# /SOURCES
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

    if not isinstance(
        sources,
        dict
    ):
        sources = normalize_sources(
            sources
        )

        CONFIG["sources"] = sources
        save_config(CONFIG)

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

        if not isinstance(
            destinations,
            list
        ):
            destinations = []

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
                    "   • "
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
# /ADDSOURCE
# ============================================================

async def addsource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    args = context.args

    if not args:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/addsource ID Nom de la source</code>\n\n"
            "Exemple :\n"
            "<code>/addsource -1001694110649 Anime Source</code>",
            parse_mode="HTML"
        )

        return

    source_id = str(
        args[0]
    )

    title = " ".join(
        args[1:]
    ).strip()

    if not title:
        title = source_id

    CONFIG["sources"][source_id] = {
        "title": title,
        "destinations": CONFIG[
            "sources"
        ].get(
            source_id,
            {}
        ).get(
            "destinations",
            []
        )
        if isinstance(
            CONFIG[
                "sources"
            ].get(
                source_id,
                {}
            ),
            dict
        )
        else [],
    }

    save_config(CONFIG)

    logger.info(
        "Source ajoutée : %s | %s",
        source_id,
        title
    )

    await message.reply_text(
        "✅ <b>Source ajoutée</b>\n\n"
        f"📥 {title}\n"
        f"🆔 <code>{source_id}</code>\n\n"
        "Il reste à la relier à une destination avec :\n"
        f"<code>/linksource {source_id} DESTINATION_ID</code>",
        parse_mode="HTML"
    )


# ============================================================
# /REMOVESOURCE
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

    save_config(CONFIG)

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
        "✅ Source supprimée : "
        f"<b>{title}</b>",
        parse_mode="HTML"
    )


# ============================================================
# /DESTINATIONS
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

    if not isinstance(
        destinations,
        dict
    ):

        destinations = normalize_destinations(
            destinations
        )

        CONFIG["destinations"] = destinations
        save_config(CONFIG)

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
# /ADDDESTINATION
# ============================================================

async def adddestination_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    args = context.args

    if not args:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/adddestination ID Nom de la destination</code>\n\n"
            "Exemple :\n"
            "<code>/adddestination -1009876543210 Anime Final</code>",
            parse_mode="HTML"
        )

        return

    destination_id = str(
        args[0]
    )

    title = " ".join(
        args[1:]
    ).strip()

    if not title:
        title = destination_id

    CONFIG[
        "destinations"
    ][destination_id] = {
        "title": title
    }

    save_config(CONFIG)

    logger.info(
        "Destination ajoutée : %s | %s",
        destination_id,
        title
    )

    await message.reply_text(
        "✅ <b>Destination ajoutée</b>\n\n"
        f"📤 {title}\n"
        f"🆔 <code>{destination_id}</code>\n\n"
        "Tu peux maintenant la relier à une source avec :\n"
        f"<code>/linksource SOURCE_ID {destination_id}</code>",
        parse_mode="HTML"
    )


# ============================================================
# /REMOVEDESTINATION
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

    # Retire également la destination
    # de toutes les sources.

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

        if not isinstance(
            destinations,
            list
        ):
            destinations = []

        source[
            "destinations"
        ] = [
            x
            for x in destinations
            if str(x) != destination_id
        ]

    save_config(CONFIG)

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
        "✅ Destination supprimée : "
        f"<b>{title}</b>",
        parse_mode="HTML"
    )


# ============================================================
# /LINKSOURCE
# ============================================================

async def linksource_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    args = context.args

    if len(args) < 2:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/linksource SOURCE_ID DESTINATION_ID</code>\n\n"
            "Plusieurs destinations :\n"
            "<code>/linksource SOURCE_ID DEST1 DEST2 DEST3</code>",
            parse_mode="HTML"
        )

        return

    source_id = str(
        args[0]
    )

    destination_ids = [
        str(x)
        for x in args[1:]
    ]

    if source_id not in CONFIG[
        "sources"
    ]:

        await message.reply_text(
            "❌ Cette source n'existe pas.\n\n"
            "Ajoute-la d'abord avec :\n"
            f"<code>/addsource {source_id}</code>",
            parse_mode="HTML"
        )

        return

    missing = []

    for destination_id in destination_ids:

        if destination_id not in CONFIG[
            "destinations"
        ]:

            missing.append(
                destination_id
            )

    if missing:

        await message.reply_text(
            "❌ Destination(s) introuvable(s) :\n\n"
            + "\n".join(
                f"• <code>{x}</code>"
                for x in missing
            )
            + "\n\n"
            "Ajoute-les d'abord avec /adddestination.",
            parse_mode="HTML"
        )

        return

    current = CONFIG[
        "sources"
    ][source_id].get(
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

    CONFIG[
        "sources"
    ][source_id][
        "destinations"
    ] = current

    save_config(CONFIG)

    if added:

        names = []

        for destination_id in added:

            names.append(
                f"• {destination_label(destination_id)} "
                f"(<code>{destination_id}</code>)"
            )

        await message.reply_text(
            "✅ <b>Source reliée</b>\n\n"
            f"📥 {source_label(source_id)}\n\n"
            "📤 Destinations ajoutées :\n"
            + "\n".join(names),
            parse_mode="HTML"
        )

    else:

        await message.reply_text(
            "ℹ️ Ces destinations étaient déjà liées à cette source."
        )


# ============================================================
# /ANIMES
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

    if not isinstance(
        animes,
        dict
    ) or not animes:

        await message.reply_text(
            "📭 Aucun anime configuré."
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

        if isinstance(
            aliases,
            str
        ):
            aliases = [
                aliases
            ]

        lines.append(
            f"🎬 <b>{title}</b>"
        )

        lines.append(
            f"🆔 <code>{anime_id}</code>"
        )

        if aliases:

            lines.append(
                "🔹 Alias : "
                + ", ".join(
                    str(x)
                    for x in aliases
                )
            )

        else:

            lines.append(
                "🔹 Alias : aucun"
            )

        lines.append("")

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ============================================================
# /ADDANIME
# ============================================================

async def addanime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    args = context.args

    if not args:

        await message.reply_text(
            "❌ Utilisation :\n\n"
            "<code>/addanime Titre | Alias 1 | Alias 2</code>\n\n"
            "Exemple :\n"
            "<code>/addanime One Piece | OP | One Piece TV</code>",
            parse_mode="HTML"
        )

        return

    text = " ".join(
        args
    )

    parts = [
        p.strip()
        for p in text.split("|")
        if p.strip()
    ]

    if not parts:

        await message.reply_text(
            "❌ Nom invalide."
        )

        return

    title = parts[0]

    aliases = parts[1:]

    anime_id = normalize_text(
        title
    )

    anime_id = re.sub(
        r"\s+",
        "_",
        anime_id
    )

    if not anime_id:

        await message.reply_text(
            "❌ Impossible de créer l'identifiant."
        )

        return

    CONFIG[
        "animes"
    ][anime_id] = {
        "title": title,
        "aliases": aliases,
    }

    save_config(CONFIG)

    await message.reply_text(
        "✅ <b>Anime ajouté</b>\n\n"
        f"🎬 {title}\n"
        f"🆔 <code>{anime_id}</code>\n"
        f"🔹 Alias : {len(aliases)}",
        parse_mode="HTML"
    )


# ============================================================
# /REMOVEANIME
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

    if not anime:

        await message.reply_text(
            "❌ Anime introuvable."
        )

        return

    save_config(CONFIG)

    title = anime.get(
        "title",
        anime_id
    )

    await message.reply_text(
        f"✅ Anime supprimé : <b>{title}</b>",
        parse_mode="HTML"
    )


# ============================================================
# /ALIASES
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

    if isinstance(
        aliases,
        str
    ):
        aliases = [
            aliases
        ]

    text = (
        f"🎬 <b>{anime.get('title', anime_id)}</b>\n\n"
        "🔹 <b>Alias :</b>\n"
    )

    if aliases:

        for alias in aliases:

            text += (
                f"• {alias}\n"
            )

    else:

        text += "Aucun alias."

    await message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# /CONFIG
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

    data = query.data or ""

    if data == "cfg_sources":

        await query.edit_message_text(
            "📡 <b>SOURCES</b>\n\n"
            "/sources\n"
            "→ Voir les sources\n\n"
            "/addsource\n"
            "→ Ajouter une source\n\n"
            "/removesource\n"
            "→ Supprimer une source\n\n"
            "/linksource\n"
            "→ Relier une source à une destination",
            parse_mode="HTML"
        )

        return

    if data == "cfg_destinations":

        await query.edit_message_text(
            "📤 <b>DESTINATIONS</b>\n\n"
            "/destinations\n"
            "→ Voir les destinations\n\n"
            "/adddestination\n"
            "→ Ajouter une destination\n\n"
            "/removedestination\n"
            "→ Supprimer une destination\n\n"
            "/linksource\n"
            "→ Relier une source",
            parse_mode="HTML"
        )

        return

    if data == "cfg_animes":

        await query.edit_message_text(
            "🎬 <b>ANIMES</b>\n\n"
            "/animes\n"
            "→ Voir les animes\n\n"
            "/addanime\n"
            "→ Ajouter un anime\n\n"
            "/removeanime\n"
            "→ Supprimer un anime\n\n"
            "/aliases\n"
            "→ Voir les alias",
            parse_mode="HTML"
        )

        return


# ============================================================
# NOM FICHIER
# ============================================================

def get_filename_from_message(
    message
):

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
# TRAITEMENT SOURCE
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

    # ========================================================
    # SOURCE
    # ========================================================

    sources = CONFIG.get(
        "sources",
        {}
    )

    # Protection supplémentaire
    if not isinstance(
        sources,
        dict
    ):

        logger.error(
            "CONFIG sources n'est pas un dictionnaire. Conversion..."
        )

        sources = normalize_sources(
            sources
        )

        CONFIG[
            "sources"
        ] = sources

        save_config(CONFIG)

    source = sources.get(
        source_id
    )

    if not isinstance(
        source,
        dict
    ):

        logger.info(
            "Message ignoré : source non configurée | %s",
            source_id
        )

        return

    # ========================================================
    # FICHIER
    # ========================================================

    filename = get_filename_from_message(
        message
    )

    if not filename:

        logger.info(
            "Message ignoré : aucun fichier | source=%s",
            source_id
        )

        return

    logger.info(
        "Message reçu | source=%s | fichier=%s",
        source_id,
        filename
    )

    # ========================================================
    # DESTINATIONS
    # ========================================================

    destinations = get_destinations_for_source(
        source_id
    )

    if not destinations:

        logger.warning(
            "Aucune destination liée à la source %s",
            source_id
        )

        return

    # ========================================================
    # ANIME
    # ========================================================

    detected = find_configured_anime(
        filename
    )

    if not detected:

        logger.info(
            "IGNORÉ : anime non configuré | %s",
            filename
        )

        return

    anime_id, anime = detected

    title = anime.get(
        "title",
        anime_id
    )

    logger.info(
        "Anime détecté : %s",
        title
    )

    # ========================================================
    # LANGUE
    # ========================================================

    language = detect_language(
        filename
    )

    logger.info(
        "Langue détectée : %s",
        language
    )

    # ========================================================
    # CAPTION
    # ========================================================

    caption = build_caption(
        anime,
        filename
    )

    logger.info(
        "Légende : %s",
        caption.replace(
            "\n",
            " | "
        )
    )

    # ========================================================
    # COPIE DIRECTE
    # ========================================================

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

            logger.info(
                "Copie : %s -> %s",
                source_id,
                destination_id
            )

            await context.bot.copy_message(

                chat_id=destination_id_int,

                from_chat_id=chat.id,

                message_id=message.message_id,

                caption=caption,
            )

            logger.info(
                "Copie réussie | destination=%s",
                destination_id
            )

        except TelegramError as error:

            logger.error(
                "Erreur Telegram destination=%s : %s",
                destination_id,
                error
            )

        except Exception:

            logger.exception(
                "Erreur inattendue destination=%s",
                destination_id
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
            "Erreur traitement message canal"
        )


# ============================================================
# MESSAGES NON-COMMANDES
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

        # Ne jamais traiter les messages privés
        if chat.type == "private":
            return

        await process_source_message(
            update,
            context
        )

    except Exception:

        logger.exception(
            "Erreur traitement message"
        )


# ============================================================
# ERREUR GLOBALE
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    error = context.error

    logger.error(
        "Exception Telegram : %s",
        error,
        exc_info=error
    )


# ============================================================
# CONFIG AU DÉMARRAGE
# ============================================================

def log_configuration():

    logger.info(
        "Sources configurées :"
    )

    sources = CONFIG.get(
        "sources",
        {}
    )

    if not isinstance(
        sources,
        dict
    ):

        sources = normalize_sources(
            sources
        )

        CONFIG[
            "sources"
        ] = sources

    if sources:

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

            logger.info(
                "  - %s | %s | destinations=%s",
                source_id,
                title,
                destinations
            )

    else:

        logger.info(
            "  - Aucune source"
        )

    logger.info(
        "Destinations configurées :"
    )

    destinations = CONFIG.get(
        "destinations",
        {}
    )

    if not isinstance(
        destinations,
        dict
    ):

        destinations = normalize_destinations(
            destinations
        )

        CONFIG[
            "destinations"
        ] = destinations

    if destinations:

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
                "  - %s | %s",
                destination_id,
                title
            )

    else:

        logger.info(
            "  - Aucune destination"
        )

    save_config(
        CONFIG
    )


# ============================================================
# COMMANDES TELEGRAM
# ============================================================

async def post_init(
    application: Application
):

    """
    Configure automatiquement la liste des commandes
    visible dans Telegram.
    """

    commands = [

        (
            "start",
            "Afficher toutes les commandes"
        ),

        (
            "help",
            "Afficher toutes les commandes"
        ),

        (
            "config",
            "Configuration"
        ),

        (
            "sources",
            "Voir les sources"
        ),

        (
            "addsource",
            "Ajouter une source"
        ),

        (
            "removesource",
            "Supprimer une source"
        ),

        (
            "destinations",
            "Voir les destinations"
        ),

        (
            "adddestination",
            "Ajouter une destination"
        ),

        (
            "removedestination",
            "Supprimer une destination"
        ),

        (
            "linksource",
            "Relier une source à une destination"
        ),

        (
            "animes",
            "Voir les animes"
        ),

        (
            "addanime",
            "Ajouter un anime"
        ),

        (
            "removeanime",
            "Supprimer un anime"
        ),

        (
            "aliases",
            "Voir les alias"
        ),
    ]

    try:

        from telegram import BotCommand

        await application.bot.set_my_commands(
            [
                BotCommand(
                    command,
                    description
                )
                for command, description
                in commands
            ]
        )

        logger.info(
            "Liste des commandes Telegram configurée."
        )

    except Exception:

        logger.exception(
            "Impossible de configurer les commandes Telegram."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN manquant.\n\n"
            "Configure la variable BOT_TOKEN."
        )

    logger.info(
        "Démarrage du bot..."
    )

    log_configuration()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
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
            "config",
            config_command
        )
    )

    # SOURCES
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

    # DESTINATIONS
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

    # ANIMES
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

    # ========================================================
    # CALLBACKS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # ========================================================
    # CANAUX
    # ========================================================
    #
    # channel_post est spécifique aux publications de canaux.
    #
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST
            & ~filters.COMMAND,
            channel_post_handler
        )
    )

    # ========================================================
    # MESSAGES DE GROUPES / SUPERGROUPS
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & ~filters.COMMAND,
            normal_message_handler
        ),
        group=10
    )

    # ========================================================
    # ERREURS
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Bot prêt."
    )

    # ========================================================
    # POLLING
    # ========================================================

    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "channel_post",
            "callback_query",
        ]
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()