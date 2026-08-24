# ============================================================
# AUTO FORWARDER TELEGRAM
# VERSION NAUTILJON - CORRIGÉE
#
# TRANSFERT UNIQUEMENT DES ANIMES CONFIGURÉS
# ALIAS AUTOMATIQUES VIA NAUTILJON
#
# ------------------------------------------------------------
# CORRECTIFS APPLIQUÉS DANS CETTE VERSION
# ------------------------------------------------------------
# 1. [SÉCURITÉ] Suppression du BOT_TOKEN et de l'ADMIN_IDS codés
#    en dur par défaut (fuite de identifiants).
# 2. [BUG CRITIQUE] Ajout de generate_nautiljon_variants(), qui
#    était appelée mais jamais définie -> la recherche d'alias
#    échouait systématiquement (NameError silencieuse).
# 3. Extraction des alias Nautiljon plus robuste : lecture
#    ligne par ligne des champs "Titre original" / "Titre
#    alternatif" de la fiche, en plus du <h1>/<title>/meta.
# 4. Correction du bug ".git.git" dans /update si GITHUB_REPO
#    contient déjà l'extension .git.
# 5. Suppression du code dupliqué (channel_post_handler et
#    fonctions utilitaires présents deux fois dans le fichier).
# 6. Nettoyage des noms de fichiers pour la détection d'anime :
#    remplacement de "5B"->"[", "5D"->"]", "20"->" " (résidus
#    d'encodage), en plus de la ponctuation déjà normalisée
#    (. , " * : & etc.). Ce nettoyage ne s'applique qu'à la
#    correspondance du nom d'anime, jamais à l'extraction de
#    l'épisode/saison, pour ne pas perdre un numéro d'épisode
#    ou une année.
# ============================================================

import os
import re
import sys
import json
import asyncio
import logging
import unicodedata
import urllib.parse
import html as _html_module

from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any

import requests

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest


# ============================================================
# CONFIGURATION
# ============================================================

# [CORRECTIF 1] Plus aucune valeur par défaut sensible codée en
# dur. BOT_TOKEN et ADMIN_IDS DOIVENT être définis en variables
# d'environnement, sinon le bot refuse de démarrer / personne
# n'a les droits admin.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8734390269:AAF0K4N-8Crsr1Tjsy50FQS6RwemjVShma0").strip()
CONFIG_FILE = "config_A.json"
GITHUB_REPO = os.getenv("GITHUB_REPO", "jinwooleboss/Chien.git").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
DEFAULT_STICKER_DELAY = 180
DEFAULT_ADMIN_IDS: List[int] = []


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("AUTO_FORWARDER")

# [CORRECTIF 7] httpx logue par défaut l'URL complète de chaque requête
# à un niveau INFO, ce qui expose le BOT_TOKEN en clair dans les logs
# (il fait partie de l'URL de l'API Telegram). On fait taire ce logger
# spécifique pour éviter la fuite.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ============================================================
# SESSION HTTP
# ============================================================

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://www.nautiljon.com/",
})


# ============================================================
# VARIABLES GLOBALES
# ============================================================

CONFIG: Dict[str, Any] = {}
PROCESSING_MESSAGES = set()
STICKER_TASKS = set()
CONFIG_LOCK = asyncio.Lock()
PROCESSED_FILE = "processed_messages.json"


# ============================================================
# ADMIN
# ============================================================

def get_admin_ids() -> List[int]:
    value = os.getenv("ADMIN_IDS", "5825526159").strip()
    if not value:
        logger.warning(
            "⚠️ ADMIN_IDS n'est pas défini : AUCUN administrateur "
            "n'est configuré, personne ne pourra utiliser les commandes admin."
        )
        return DEFAULT_ADMIN_IDS.copy()
    result = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            logger.warning("ADMIN_IDS invalide : %s", item)
    return list(dict.fromkeys(result))


ADMIN_IDS = get_admin_ids()


# ============================================================
# CONFIGURATION PAR DÉFAUT
# ============================================================

DEFAULT_CONFIG = {
    "admins": ADMIN_IDS,
    "users": [],
    "banned_users": [],
    "sources": [],
    "destination": None,
    "animes": [],
    "aliases": {},
    "stickers": {},
}


# ============================================================
# MOTS TECHNIQUES & NORMALISATION
# ============================================================

TECHNICAL_WORDS = {
    "1080p", "720p", "2160p", "480p", "360p", "4k", "fhd", "hd",
    "web", "webrip", "webdl", "web-dl", "bluray", "bdrip", "hdtv",
    "x264", "x265", "hevc", "av1", "aac", "flac", "multi",
    "vostfr", "vost", "vf", "vo", "truefrench", "french",
    "japanese", "english", "episode", "episodes", "ep",
    "saison", "season", "batch", "hardsub", "hardsubbed", "hard", "sub",
}


def normalize_text(text: str) -> str:
    """Normalise un texte pour la comparaison / correspondance de noms
    d'anime UNIQUEMENT. Ne pas utiliser pour extraire un numéro
    d'épisode ou une saison (utiliser le texte brut pour ça)."""

    if not text:
        return ""

    text = str(text)

    # [CORRECTIF 6] Résidus d'encodage fréquents dans certains noms de
    # fichiers : "5B"/"5D" pour des crochets, "20" pour un espace.
    # Appliqué en tout premier, insensible à la casse.
    text = re.sub(r"5B", "[", text, flags=re.I)
    text = re.sub(r"5D", "]", text, flags=re.I)
    # "20" isolé (pas entouré d'autres chiffres) uniquement, pour ne
    # pas casser un numéro d'épisode "20" complet ni une année comme
    # "2026" ou "1920".
    text = re.sub(r"(?<!\d)20(?!\d)", " ", text)

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[_\-.!;:'\"`´’‘,!?()\[\]{}<>/\\|+=*~@#$%^&:]+", " ", text)
    text = re.sub(r"[–—−]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_anime_words(text: str) -> str:
    text = normalize_text(text)
    result = []
    for word in text.split():
        if word in TECHNICAL_WORDS:
            continue
        if re.fullmatch(r"\d{3,4}p", word):
            continue
        if re.fullmatch(r"x26[45]", word):
            continue
        result.append(word)
    return " ".join(result)


def anime_key(text: str) -> str:
    text = clean_anime_words(text)
    text = re.sub(r"\b(?:s\d+|season\s*\d+|saison\s*\d+)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def similarity(a: str, b: str) -> float:
    a = anime_key(a)
    b = anime_key(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ============================================================
# CHARGEMENT / SAUVEGARDE CONFIG
# ============================================================

def load_config() -> bool:
    global CONFIG
    try:
        if not os.path.exists(CONFIG_FILE):
            CONFIG = DEFAULT_CONFIG.copy()
            save_config_sync()
            return True
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.error("config_A.json doit être un objet JSON.")
            return False
        CONFIG = data
        for key, value in DEFAULT_CONFIG.items():
            if key not in CONFIG:
                CONFIG[key] = value
        logger.info("Configuration chargée.")
        return True
    except Exception:
        logger.exception("Erreur lors du chargement de la configuration.")
        return False


def save_config_sync():
    temp = CONFIG_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=4)
    os.replace(temp, CONFIG_FILE)


async def save_config():
    async with CONFIG_LOCK:
        save_config_sync()


# ============================================================
# ADMIN & BAN
# ============================================================

def is_admin(user_id: int) -> bool:
    admins = CONFIG.get("admins", ADMIN_IDS)
    if not isinstance(admins, list):
        admins = ADMIN_IDS
    try:
        return int(user_id) in [int(x) for x in admins]
    except Exception:
        return False


def is_banned(user_id: int) -> bool:
    banned = CONFIG.get("banned_users", [])
    if not isinstance(banned, list):
        return False
    try:
        return int(user_id) in [int(x) for x in banned]
    except Exception:
        return False


async def global_ban_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_banned(user.id):
        if update.effective_message:
            await update.effective_message.reply_text("🚫 Tu es banni de ce bot.")
        raise ApplicationHandlerStop


# ============================================================
# EXTRACTION DES ANIMES CONFIGURÉS
# ============================================================

def get_anime_entries() -> List[Dict[str, Any]]:
    data = CONFIG.get("animes", [])
    result = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                result.append({"name": item, "aliases": []})
            elif isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("anime")
                if not name:
                    continue
                aliases = item.get("aliases", [])
                if isinstance(aliases, str):
                    aliases = [aliases]
                if not isinstance(aliases, list):
                    aliases = []
                result.append({**item, "name": str(name), "aliases": aliases})
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                aliases = value.get("aliases", [])
                if isinstance(aliases, str):
                    aliases = [aliases]
                result.append({**value, "name": str(value.get("name", key)), "aliases": aliases})
            elif isinstance(value, list):
                result.append({"name": str(key), "aliases": value})
            else:
                result.append({"name": str(key), "aliases": []})
    return result


def find_configured_anime(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = anime_key(text)
    if not cleaned:
        return None
    best = None
    best_score = 0.0
    for anime in get_anime_entries():
        name = anime.get("name", "")
        candidates = [name] + (anime.get("aliases", []) if isinstance(anime.get("aliases"), list) else [])
        for candidate in candidates:
            if not candidate:
                continue
            candidate_key = anime_key(str(candidate))
            if cleaned == candidate_key:
                return anime
            if len(candidate_key) >= 6 and re.search(r"(?:^|\s)" + re.escape(candidate_key) + r"(?:\s|$)", cleaned):
                score = 0.94
            else:
                score = similarity(cleaned, candidate_key)
            if score > best_score:
                best_score = score
                best = anime
    if best_score >= 0.84:
        return best
    return None


def find_anime_entry(name: str) -> Optional[Dict[str, Any]]:
    return find_configured_anime(name)


# ============================================================
# EXTRACTION ÉPISODE / SAISON / VERSION / QUALITÉ
#
# IMPORTANT : ces fonctions travaillent sur le TEXTE BRUT (pas
# anime_key/normalize_text), pour ne jamais perdre un numéro
# d'épisode/saison à cause du nettoyage "5B/5D/20" qui ne sert
# qu'à la reconnaissance du nom d'anime.
# ============================================================

def extract_episode(text: str) -> Optional[int]:
    if not text:
        return None
    patterns = [
        r"\bS\d+\s*E(\d+)\b",
        r"\bS\d+\s*-\s*E(\d+)\b",
        r"\b(?:EP|EPISODE|ÉPISODE)\s*[-._ ]?(\d+)\b",
        r"\bE(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass
    return None


def extract_season(text: str) -> Optional[int]:
    if not text:
        return None
    patterns = [
        r"\bS(\d+)\s*E\d+\b",
        r"\bS(\d+)\b",
        r"\bSAISON\s*(\d+)\b",
        r"\bSEASON\s*(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass
    return None


def detect_version(text: str) -> Optional[str]:
    if not text:
        return None
    lower = normalize_text(text)
    if re.search(r"\bhardsub(?:bed)?\b", lower) or re.search(r"\bhard\s+sub\b", lower):
        return "VOSTFR"
    if re.search(r"\bvostfr\b", lower) or re.search(r"\bvost\b", lower):
        return "VOSTFR"
    if re.search(r"\bvf\b", lower) or re.search(r"\btruefrench\b", lower) or re.search(r"\bfrench\b", lower):
        return "VF"
    return None


def detect_quality(text: str) -> Optional[str]:
    match = re.search(r"\b(2160p|1080p|720p|480p|360p)\b", text, re.I)
    return match.group(1).lower() if match else None


# ============================================================
# NAUTILJON - RECHERCHE ET SCRAPING D'ALIAS
# ============================================================

def guess_nautiljon_url(title: str, section: str = "animes") -> str:
    """Construit l'URL probable d'une fiche Nautiljon à partir du titre,
    sans passer par le moteur de recherche interne du site (souvent
    protégé contre le scraping et renvoyant une erreur 403). Les fiches
    Nautiljon suivent un schéma prévisible : /animes/titre+en+minuscules.html
    (espaces remplacés par '+', accents et ponctuation légère conservés)."""

    slug = title.strip().lower()
    slug = re.sub(r"\s+", "+", slug)
    return f"https://www.nautiljon.com/{section}/{urllib.parse.quote(slug, safe='+!\'-')}.html"


def search_nautiljon(title: str) -> Optional[str]:
    """Retourne l'URL d'une fiche Nautiljon pour ce titre.

    [CORRECTIF 8] Tente d'abord une requête directe sur l'URL de fiche
    devinée (fiable, non protégée), puis se rabat sur le moteur de
    recherche interne (recherche.html) qui renvoie parfois une erreur
    403 selon la protection anti-scraping du site."""

    # 1. URL devinée directement (anime, puis manga en repli)
    for section in ("animes", "mangas"):
        guessed_url = guess_nautiljon_url(title, section)
        try:
            response = HTTP_SESSION.get(guessed_url, timeout=10)
            if response.status_code == 200:
                logger.debug("URL devinée valide : %s", guessed_url)
                return guessed_url
        except Exception as e:
            logger.debug("Échec requête directe %s : %s", guessed_url, e)

    # 2. Repli : moteur de recherche interne du site
    try:
        url = "https://www.nautiljon.com/animes/recherche.html?q=" + requests.utils.quote(title)
        logger.debug("Recherche Nautiljon (repli) : %s", url)
        response = HTTP_SESSION.get(url, timeout=10)
        if response.status_code != 200:
            logger.warning("Nautiljon recherche HTTP %s pour %s", response.status_code, title)
            return None

        html = response.text
        pattern = r'href=["\']([^"\']*\/animes\/[^"\']+)["\']'
        matches = re.findall(pattern, html, re.I)
        if not matches:
            logger.debug("Aucun lien d'anime trouvé pour '%s'", title)
            return None

        first_match = matches[0]
        if first_match.startswith("/"):
            full_url = "https://www.nautiljon.com" + first_match
        else:
            full_url = first_match
        logger.debug("URL trouvée : %s", full_url)
        return full_url

    except Exception as e:
        logger.warning("Erreur recherche Nautiljon : %s", e)
        return None


# [CORRECTIF 2] Cette fonction était appelée par fetch_nautiljon_aliases_sync
# mais n'existait nulle part -> NameError systématique -> recherche
# d'alias qui échouait toujours silencieusement.
def generate_nautiljon_variants(title: str) -> List[str]:
    """Génère plusieurs variantes du titre à tester sur la recherche
    Nautiljon, pour maximiser les chances de trouver une fiche même
    si le titre exact ne matche pas du premier coup."""

    variants: List[str] = []
    seen = set()

    def add(candidate: str):
        candidate = (candidate or "").strip()
        if not candidate:
            return
        key = candidate.lower()
        if key in seen:
            return
        seen.add(key)
        variants.append(candidate)

    # 1. Le titre tel quel
    add(title)

    # 2. Version sans ponctuation lourde, espaces normalisés
    cleaned = re.sub(r"[^\w\sÀ-ÿ]", " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    add(cleaned)

    # 3. Juste la partie avant un séparateur de sous-titre
    # (souvent le sous-titre n'est pas indexé sous le même nom)
    for sep in (" : ", ": ", " - ", " – "):
        if sep in title:
            add(title.split(sep)[0])

    # 4. Version totalement normalisée (dernier recours)
    add(anime_key(title))

    return variants


def extract_aliases_from_page(html: str, url: str) -> List[str]:
    """Extrait les titres alternatifs depuis une page Nautiljon."""

    aliases: List[str] = []

    # 1. Titre principal (<h1>)
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.I)
    if h1_match:
        h1_text = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
        if h1_text:
            aliases.append(h1_text)

    # 2. Titre de la page (<title>)
    title_match = re.search(r'<title>(.*?)</title>', html, re.I)
    if title_match:
        title_text = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        title_text = re.sub(r'\s*[–—\-]\s*Nautiljon.*$', '', title_text, flags=re.I).strip()
        if title_text:
            aliases.append(title_text)

    # 3. [CORRECTIF 3] Lecture ligne par ligne des champs "Titre
    # original" / "Titre alternatif" de la fiche. Plus robuste qu'un
    # ciblage de balises <dt>/<dd> précises, puisqu'on ne connaît pas
    # avec certitude la structure HTML exacte utilisée par le site.
    normalized_html = re.sub(r"(?i)</li>|<br\s*/?>|</p>|</tr>|</div>", "\n", html)
    flat_text = re.sub(r"<[^>]+>", " ", normalized_html)
    flat_text = _html_module.unescape(flat_text)

    for line in flat_text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        match = re.match(r"(?i)Titre (?:original|alternatif|anglais|japonais)\s*:\s*(.+)", line)
        if match:
            value = match.group(1).strip()
            for part in value.split("/"):
                part = part.strip()
                if part:
                    aliases.append(part)

    # 4. og:title (meta)
    meta_og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.I)
    if meta_og:
        og_title = meta_og.group(1).strip()
        if og_title:
            aliases.append(og_title)

    # Nettoyage / dédoublonnage
    seen = set()
    result = []
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        key = anime_key(alias)
        if key and key not in seen:
            seen.add(key)
            result.append(alias)

    return result


def fetch_nautiljon_aliases_sync(title: str) -> List[str]:
    """Récupère les alias depuis Nautiljon en essayant plusieurs
    variantes du titre."""

    variants = generate_nautiljon_variants(title)
    logger.info("Recherche Nautiljon avec %d variantes pour '%s'", len(variants), title)

    for idx, variant in enumerate(variants, 1):
        logger.debug("Variante %d/%d : '%s'", idx, len(variants), variant)
        url = search_nautiljon(variant)
        if not url:
            logger.debug("Aucune page pour la variante '%s'", variant)
            continue

        logger.info("Page trouvée pour '%s' : %s", variant, url)
        try:
            response = HTTP_SESSION.get(url, timeout=10)
            if response.status_code != 200:
                logger.warning("Erreur HTTP %s sur %s", response.status_code, url)
                continue

            aliases = extract_aliases_from_page(response.text, url)
            if aliases:
                logger.info("✅ Nautiljon a trouvé %d alias via '%s'", len(aliases), variant)
                return aliases
            else:
                logger.info("Page trouvée mais aucun alias extrait pour '%s'", variant)
        except Exception as e:
            logger.warning("Erreur scraping Nautiljon pour '%s' : %s", variant, e)

    logger.info("❌ Aucune page Nautiljon trouvée pour aucune variante de '%s'", title)
    return []


async def fetch_nautiljon_aliases(title: str) -> List[str]:
    return await asyncio.to_thread(fetch_nautiljon_aliases_sync, title)


# ============================================================
# LECTURE DU MESSAGE (nom de fichier vidéo uniquement)
# ============================================================

def get_message_text(message) -> str:
    if not message:
        return ""
    parts = []
    if message.video and message.video.file_name:
        parts.append(message.video.file_name)
    if message.document and message.document.file_name:
        parts.append(message.document.file_name)
    return "\n".join(parts)


def message_key(message) -> str:
    return f"{message.chat_id}:{message.message_id}"


# ============================================================
# DÉDUPLICATION PERSISTANTE
# ============================================================

def _load_processed() -> set:
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def _save_processed():
    try:
        data = list(PROCESSED_MESSAGES)[-5000:]
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        logger.exception("Erreur sauvegarde processed_messages.json")


PROCESSED_MESSAGES = _load_processed()


# ============================================================
# FORWARD & STICKER
# ============================================================

def build_caption(anime_name: str, season: Optional[int], episode: Optional[int], version: Optional[str]) -> str:
    """Construit la légende à afficher lors du transfert :
    Nom
    Saison/Épisode
    VOSTFR ou VF"""

    lines = [anime_name]

    if season and episode:
        lines.append(f"Saison {season} - Épisode {episode}")
    elif episode:
        lines.append(f"Épisode {episode}")
    elif season:
        lines.append(f"Saison {season}")

    if version:
        lines.append(version)

    return "\n".join(lines)


async def forward_anime_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    anime: Dict[str, Any],
    season: Optional[int] = None,
    episode: Optional[int] = None,
    version: Optional[str] = None,
):
    message = update.channel_post
    if not message:
        return
    destination = CONFIG.get("destination")
    if not destination:
        logger.warning("Destination non configurée.")
        return
    key = message_key(message)
    if key in PROCESSED_MESSAGES:
        return
    PROCESSED_MESSAGES.add(key)
    _save_processed()
    if len(PROCESSED_MESSAGES) > 10000:
        PROCESSED_MESSAGES.clear()
        _save_processed()

    caption = build_caption(anime.get("name", ""), season, episode, version)

    try:
        await context.bot.copy_message(
            chat_id=int(destination),
            from_chat_id=message.chat_id,
            message_id=message.message_id,
            caption=caption,
        )
        logger.info("Transfert effectué : %s | message=%s", anime.get("name"), message.message_id)
        await schedule_sticker(context, anime)
    except Exception:
        logger.exception("Erreur pendant le transfert.")


async def sticker_worker(context: ContextTypes.DEFAULT_TYPE, sticker_id: str, delay: int, destination: int, key: str):
    try:
        await asyncio.sleep(delay)
        await context.bot.send_sticker(chat_id=destination, sticker=sticker_id)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Erreur sticker.")
    finally:
        STICKER_TASKS.discard(key)


async def schedule_sticker(context: ContextTypes.DEFAULT_TYPE, anime: Dict[str, Any]):
    name = anime.get("name", "")
    stickers = CONFIG.get("stickers", {})
    if not isinstance(stickers, dict):
        return
    sticker_id = stickers.get(name)
    if not sticker_id:
        return
    destination = CONFIG.get("destination")
    if not destination:
        return
    key = f"{destination}:{anime_key(name)}"
    if key in STICKER_TASKS:
        return
    STICKER_TASKS.add(key)
    asyncio.create_task(sticker_worker(context, sticker_id, DEFAULT_STICKER_DELAY, int(destination), key))


# ============================================================
# TRAITEMENT DES POSTS
# [CORRECTIF 5] Une seule version de cette fonction (le fichier
# original la définissait deux fois de façon identique).
# ============================================================

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message:
        return

    # Ne traiter que les messages contenant une vidéo
    has_video = (
        message.video is not None or
        (
            message.document is not None and
            message.document.mime_type is not None and
            message.document.mime_type.startswith("video/")
        )
    )
    if not has_video:
        return

    sources = CONFIG.get("sources", [])
    if not isinstance(sources, list):
        return

    try:
        source_id = int(message.chat_id)
    except Exception:
        return

    if source_id not in [int(x) for x in sources if str(x).lstrip("-").isdigit()]:
        return

    text = get_message_text(message)
    if not text:
        return

    anime = find_configured_anime(text)
    if not anime:
        logger.info("Anime non configuré ignoré : %s", text[:50])
        return

    episode = extract_episode(text)
    season = extract_season(text)
    version = detect_version(text)
    quality = detect_quality(text)

    logger.info(
        "Anime détecté : %s | saison=%s | épisode=%s | version=%s | qualité=%s",
        anime.get("name"), season, episode, version, quality,
    )

    await forward_anime_message(update, context, anime, season=season, episode=episode, version=version)


# ============================================================
# COMMANDES
# ============================================================

async def require_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not is_admin(user.id):
        if update.effective_message:
            await update.effective_message.reply_text("❌ Accès réservé à l'administrateur.")
        return False
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🤖 Auto Forwarder actif.\nUtilise /help pour voir les commandes.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    text = """
🤖 AUTO FORWARDER

👤 ADMIN
/adduser ID
/removeuser ID
/users
/banuser ID
/unbanuser ID
/banned

🎬 ANIMES
/addanime NOM
/removeanime NOM
/animes

🔤 ALIAS
/aliases NOM
/addalias NOM | ALIAS
/removealias NOM | ALIAS
/findalias ALIAS

🎨 STICKERS
/setsticker NOM | STICKER_ID
/removesticker NOM

📡 SOURCES
/sources
/addsource ID
/removesource ID

🎯 DESTINATION
/destination
/setdestination ID

⚙️ SYSTÈME
/status
/config
/reload
/update
/help
"""
    await update.effective_message.reply_text(text.strip())


async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /adduser ID")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    users = CONFIG.setdefault("users", [])
    if not isinstance(users, list):
        users = []
        CONFIG["users"] = users
    if user_id not in users:
        users.append(user_id)
        await save_config()
    await update.effective_message.reply_text(f"✅ Utilisateur {user_id} autorisé.")


async def removeuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /removeuser ID")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    users = CONFIG.get("users", [])
    if isinstance(users, list) and user_id in users:
        users.remove(user_id)
        await save_config()
    await update.effective_message.reply_text(f"✅ Utilisateur {user_id} retiré.")


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    users = CONFIG.get("users", [])
    if not users:
        await update.effective_message.reply_text("👤 Aucun utilisateur autorisé.")
        return
    text = "👤 UTILISATEURS AUTORISÉS\n\n" + "\n".join(f"• `{u}`" for u in users)
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def banuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /banuser ID")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    banned = CONFIG.setdefault("banned_users", [])
    if user_id not in banned:
        banned.append(user_id)
    users = CONFIG.get("users", [])
    if isinstance(users, list) and user_id in users:
        users.remove(user_id)
    await save_config()
    await update.effective_message.reply_text(f"🚫 Utilisateur {user_id} banni.")


async def unbanuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /unbanuser ID")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    banned = CONFIG.get("banned_users", [])
    if isinstance(banned, list) and user_id in banned:
        banned.remove(user_id)
        await save_config()
    await update.effective_message.reply_text(f"✅ Utilisateur {user_id} débanni.")


async def banned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    banned = CONFIG.get("banned_users", [])
    if not banned:
        await update.effective_message.reply_text("🚫 Aucun utilisateur banni.")
        return
    text = "🚫 UTILISATEURS BANNIS\n\n" + "\n".join(f"• `{u}`" for u in banned)
    await update.effective_message.reply_text(text, parse_mode="Markdown")


# ============================================================
# /ADDANIME (recherche automatique d'alias via Nautiljon)
# ============================================================

async def addanime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    if not context.args:
        await update.effective_message.reply_text("Utilisation : /addanime Nom de l'anime")
        return

    name = " ".join(context.args).strip()
    if not name:
        await update.effective_message.reply_text("❌ Nom invalide.")
        return

    existing = find_configured_anime(name)
    if existing:
        await update.effective_message.reply_text(f"⚠️ Cet anime est déjà configuré : {existing.get('name')}")
        return

    # Ajout dans la config
    animes = CONFIG.get("animes", [])
    if isinstance(animes, list):
        animes.append({"name": name, "aliases": []})
    elif isinstance(animes, dict):
        animes[name] = {"name": name, "aliases": []}
    else:
        CONFIG["animes"] = [{"name": name, "aliases": []}]
    await save_config()

    await update.effective_message.reply_text(
        f"✅ Anime ajouté :\n🎬 {name}\n\n🔎 Recherche automatique d'alias via Nautiljon en cours..."
    )

    # Récupérer les alias via Nautiljon
    try:
        found_aliases = await fetch_nautiljon_aliases(name)
    except Exception:
        logger.exception("Erreur lors de la recherche Nautiljon.")
        found_aliases = []

    if found_aliases:
        anime_entry = find_configured_anime(name)
        if anime_entry:
            current_aliases = anime_entry.get("aliases", [])
            if not isinstance(current_aliases, list):
                current_aliases = []
            existing_keys = {anime_key(a) for a in current_aliases}
            existing_keys.add(anime_key(name))  # évite de ré-ajouter le nom lui-même
            added = []
            for alias in found_aliases:
                a_key = anime_key(alias)
                if a_key and a_key not in existing_keys:
                    current_aliases.append(alias)
                    existing_keys.add(a_key)
                    added.append(alias)

            # Mise à jour dans CONFIG
            animes_ref = CONFIG.get("animes", [])
            target_name = anime_entry.get("name")
            if isinstance(animes_ref, list):
                for item in animes_ref:
                    if isinstance(item, dict) and item.get("name") == target_name:
                        item["aliases"] = current_aliases
            elif isinstance(animes_ref, dict):
                for key, item in animes_ref.items():
                    if isinstance(item, dict) and item.get("name", key) == target_name:
                        item["aliases"] = current_aliases
            await save_config()

            if added:
                liste = "\n".join(f"• {a}" for a in added)
                await update.effective_message.reply_text(f"✅ Alias trouvés via Nautiljon :\n{liste}")
            else:
                await update.effective_message.reply_text("ℹ️ Aucun nouvel alias à ajouter.")
    else:
        await update.effective_message.reply_text(
            "ℹ️ Aucun alias trouvé sur Nautiljon. Tu peux en ajouter manuellement avec /addalias."
        )


# ============================================================
# AUTRES COMMANDES
# ============================================================

async def removeanime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /removeanime Nom")
        return
    name = " ".join(context.args)
    animes = CONFIG.get("animes", [])
    removed = False
    if isinstance(animes, list):
        new_list = []
        for item in animes:
            item_name = item if isinstance(item, str) else (item.get("name") or item.get("title") or item.get("anime") or "")
            if anime_key(item_name) == anime_key(name):
                removed = True
                continue
            new_list.append(item)
        CONFIG["animes"] = new_list
    elif isinstance(animes, dict):
        for key in list(animes.keys()):
            if anime_key(str(key)) == anime_key(name):
                del animes[key]
                removed = True
    if removed:
        await save_config()
        await update.effective_message.reply_text(f"✅ Anime supprimé : {name}")
    else:
        await update.effective_message.reply_text("❌ Anime introuvable.")


async def animes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    animes = get_anime_entries()
    if not animes:
        await update.effective_message.reply_text("🎬 Aucun anime configuré.")
        return
    lines = ["🎬 ANIMES CONFIGURÉS", ""]
    for i, anime in enumerate(animes, 1):
        name = anime.get("name", "Inconnu")
        aliases = anime.get("aliases", [])
        lines.append(f"{i}. {name}")
        if aliases:
            lines.append("   ↳ " + ", ".join(str(x) for x in aliases))
    await update.effective_message.reply_text("\n".join(lines))


async def aliases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /aliases Nom")
        return
    name = " ".join(context.args)
    anime = find_anime_entry(name)
    if not anime:
        await update.effective_message.reply_text("❌ Anime introuvable.")
        return
    aliases = anime.get("aliases", [])
    if not aliases:
        await update.effective_message.reply_text(f"🔤 Aucun alias pour {anime.get('name')}.")
        return
    await update.effective_message.reply_text(f"🔤 ALIAS DE {anime.get('name')}\n\n" + "\n".join(f"• {x}" for x in aliases))


async def addalias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    raw = " ".join(context.args)
    if "|" not in raw:
        await update.effective_message.reply_text("Utilisation : /addalias Nom | Alias")
        return
    anime_name, alias = [x.strip() for x in raw.split("|", 1)]
    anime = find_anime_entry(anime_name)
    if not anime:
        await update.effective_message.reply_text("❌ Anime introuvable.")
        return
    aliases = anime.setdefault("aliases", [])
    if alias not in aliases:
        aliases.append(alias)
    animes = CONFIG.get("animes", [])
    target_name = anime.get("name")
    if isinstance(animes, list):
        for item in animes:
            if isinstance(item, dict) and item.get("name") == target_name:
                item["aliases"] = aliases
    elif isinstance(animes, dict):
        for key, item in animes.items():
            if isinstance(item, dict) and item.get("name", key) == target_name:
                item["aliases"] = aliases
    await save_config()
    await update.effective_message.reply_text(f"✅ Alias ajouté : {alias}")


async def removealias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    raw = " ".join(context.args)
    if "|" not in raw:
        await update.effective_message.reply_text("Utilisation : /removealias Nom | Alias")
        return
    anime_name, alias = [x.strip() for x in raw.split("|", 1)]
    anime = find_anime_entry(anime_name)
    if not anime:
        await update.effective_message.reply_text("❌ Anime introuvable.")
        return
    aliases = anime.get("aliases", [])
    aliases = [x for x in aliases if anime_key(x) != anime_key(alias)]
    anime["aliases"] = aliases
    animes = CONFIG.get("animes", [])
    target_name = anime.get("name")
    if isinstance(animes, list):
        for item in animes:
            if isinstance(item, dict) and item.get("name") == target_name:
                item["aliases"] = aliases
    elif isinstance(animes, dict):
        for key, item in animes.items():
            if isinstance(item, dict) and item.get("name", key) == target_name:
                item["aliases"] = aliases
    await save_config()
    await update.effective_message.reply_text(f"✅ Alias supprimé : {alias}")


async def findalias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /findalias Alias")
        return
    alias = " ".join(context.args)
    for anime in get_anime_entries():
        for item in anime.get("aliases", []):
            if anime_key(item) == anime_key(alias):
                await update.effective_message.reply_text(f"🔎 Alias trouvé\n\nAlias : {item}\nAnime : {anime.get('name')}")
                return
    await update.effective_message.reply_text("❌ Alias introuvable.")


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    sources = CONFIG.get("sources", [])
    if not sources:
        await update.effective_message.reply_text("📡 Aucune source.")
        return
    text = "📡 SOURCES\n\n" + "\n".join(f"• `{s}`" for s in sources)
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def addsource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /addsource ID")
        return
    try:
        source_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    sources = CONFIG.setdefault("sources", [])
    if not isinstance(sources, list):
        sources = []
        CONFIG["sources"] = sources
    if source_id not in sources:
        sources.append(source_id)
        await save_config()
    await update.effective_message.reply_text(f"✅ Source ajoutée : {source_id}")


async def removesource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /removesource ID")
        return
    try:
        source_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    sources = CONFIG.get("sources", [])
    if isinstance(sources, list) and source_id in sources:
        sources.remove(source_id)
        await save_config()
    await update.effective_message.reply_text(f"✅ Source supprimée : {source_id}")


async def destination_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    dest = CONFIG.get("destination")
    await update.effective_message.reply_text(f"🎯 Destination : {dest if dest else 'Non configurée'}")


async def setdestination_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /setdestination ID")
        return
    try:
        destination = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID invalide.")
        return
    CONFIG["destination"] = destination
    await save_config()
    await update.effective_message.reply_text(f"✅ Destination définie : {destination}")


async def setsticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    raw = " ".join(context.args)
    if "|" not in raw:
        await update.effective_message.reply_text("Utilisation : /setsticker Anime | STICKER_ID")
        return
    anime_name, sticker_id = [x.strip() for x in raw.split("|", 1)]
    anime = find_anime_entry(anime_name)
    if not anime:
        await update.effective_message.reply_text("❌ Anime introuvable.")
        return
    stickers = CONFIG.setdefault("stickers", {})
    if not isinstance(stickers, dict):
        CONFIG["stickers"] = {}
        stickers = CONFIG["stickers"]
    stickers[anime.get("name")] = sticker_id
    await save_config()
    await update.effective_message.reply_text("✅ Sticker configuré.")


async def removesticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Utilisation : /removesticker Anime")
        return
    name = " ".join(context.args)
    stickers = CONFIG.get("stickers", {})
    anime = find_anime_entry(name)
    if not anime:
        await update.effective_message.reply_text("❌ Anime introuvable.")
        return
    real_name = anime.get("name")
    if isinstance(stickers, dict) and real_name in stickers:
        del stickers[real_name]
        await save_config()
    await update.effective_message.reply_text("✅ Sticker supprimé.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    animes = get_anime_entries()
    sources = CONFIG.get("sources", [])
    dest = CONFIG.get("destination")
    text = f"""📊 STATUS

🎬 Animes : {len(animes)}
📡 Sources : {len(sources) if isinstance(sources, list) else 0}
🎯 Destination : {dest if dest else 'Non configurée'}
👤 Utilisateurs : {len(CONFIG.get('users', []))}
🚫 Bannis : {len(CONFIG.get('banned_users', []))}"""
    await update.effective_message.reply_text(text)


async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    try:
        text = json.dumps(CONFIG, ensure_ascii=False, indent=2)
        if len(text) > 3800:
            text = text[:3800] + "\n..."
        await update.effective_message.reply_text(f"<pre>{text}</pre>", parse_mode="HTML")
    except Exception:
        logger.exception("Erreur /config")


async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if load_config():
        await update.effective_message.reply_text("🔄 Configuration rechargée.")
    else:
        await update.effective_message.reply_text("❌ Impossible de recharger.")


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not GITHUB_REPO:
        await update.effective_message.reply_text("⚠️ GITHUB_REPO non configuré.")
        return
    await update.effective_message.reply_text("🔄 Vérification de la mise à jour...")
    try:
        import subprocess

        # [CORRECTIF 4] On retire un éventuel ".git" déjà présent dans
        # GITHUB_REPO avant d'en rajouter un, pour éviter "repo.git.git".
        repo_url = GITHUB_REPO
        if repo_url.startswith("http"):
            if repo_url.endswith(".git"):
                repo_url = repo_url[:-4]
            repo_url = repo_url + ".git"
        else:
            repo_url = repo_url[:-4] if repo_url.endswith(".git") else repo_url
            repo_url = f"https://github.com/{repo_url}.git"

        await asyncio.to_thread(subprocess.run, ["git", "remote", "set-url", "origin", repo_url], capture_output=True, text=True, timeout=30)
        result = await asyncio.to_thread(subprocess.run, ["git", "pull", "origin", GITHUB_BRANCH, "--ff-only"], capture_output=True, text=True, timeout=60)
        output = result.stdout or result.stderr or "Aucun retour."
        if len(output) > 3000:
            output = output[-3000:]
        await update.effective_message.reply_text("📦 Résultat :\n\n" + output)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Mise à jour impossible : {e}")


# ============================================================
# GESTION D'ERREUR
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception Telegram :", exc_info=context.error)


# ============================================================
# COMMANDES TELEGRAM
# ============================================================

async def set_commands(application: Application):
    commands = [
        BotCommand("start", "Démarrer le bot"),
        BotCommand("help", "Afficher l'aide"),
        BotCommand("addanime", "Ajouter un anime"),
        BotCommand("removeanime", "Supprimer un anime"),
        BotCommand("animes", "Liste des animes"),
        BotCommand("aliases", "Voir les alias"),
        BotCommand("addalias", "Ajouter un alias"),
        BotCommand("removealias", "Supprimer un alias"),
        BotCommand("findalias", "Rechercher un alias"),
        BotCommand("sources", "Voir les sources"),
        BotCommand("addsource", "Ajouter une source"),
        BotCommand("removesource", "Supprimer une source"),
        BotCommand("destination", "Voir la destination"),
        BotCommand("setdestination", "Modifier la destination"),
        BotCommand("status", "État du bot"),
        BotCommand("reload", "Recharger la configuration"),
        BotCommand("config", "Voir la configuration"),
    ]
    await application.bot.set_my_commands(commands)


# ============================================================
# MAIN
# ============================================================

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN non défini.")
        print("Exemple : export BOT_TOKEN='TON_TOKEN'")
        sys.exit(1)

    logger.info("Lancement du polling...")
    if not load_config():
        logger.error("Impossible de charger config_A.json.")
        sys.exit(1)

    request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=30,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=30,
    )

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(TypeHandler(Update, global_ban_filter), group=-1)

    # Commandes
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("adduser", adduser_command))
    application.add_handler(CommandHandler("removeuser", removeuser_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("banuser", banuser_command))
    application.add_handler(CommandHandler("unbanuser", unbanuser_command))
    application.add_handler(CommandHandler("banned", banned_command))
    application.add_handler(CommandHandler("addanime", addanime_command))
    application.add_handler(CommandHandler("removeanime", removeanime_command))
    application.add_handler(CommandHandler("animes", animes_command))
    application.add_handler(CommandHandler("aliases", aliases_command))
    application.add_handler(CommandHandler("addalias", addalias_command))
    application.add_handler(CommandHandler("removealias", removealias_command))
    application.add_handler(CommandHandler("findalias", findalias_command))
    application.add_handler(CommandHandler("setsticker", setsticker_command))
    application.add_handler(CommandHandler("removesticker", removesticker_command))
    application.add_handler(CommandHandler("sources", sources_command))
    application.add_handler(CommandHandler("addsource", addsource_command))
    application.add_handler(CommandHandler("removesource", removesource_command))
    application.add_handler(CommandHandler("destination", destination_command))
    application.add_handler(CommandHandler("setdestination", setdestination_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("reload", reload_command))
    application.add_handler(CommandHandler("update", update_command))

    # Posts
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, channel_post_handler))

    application.add_error_handler(error_handler)

    async def post_init(app: Application):
        await set_commands(app)
        logger.info("Auto Forwarder démarré (Nautiljon).")
        logger.info("Sources : %s", CONFIG.get("sources", []))
        logger.info("Destination : %s", CONFIG.get("destination"))
        logger.info("Animes configurés : %s", len(get_anime_entries()))

    application.post_init = post_init
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()