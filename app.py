import json
import os
import re
import time
import uuid
import urllib.request
import urllib.error
import base64
import mimetypes
import threading
import subprocess
import shutil
import zipfile
import zlib
import gzip
import sqlite3
import uuid
import io
import socket
import hashlib
from pathlib import Path

import webview
from PIL import Image
from PIL.PngImagePlugin import PngInfo

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
EXPORT_DIR = APP_DIR / "exports"
SETTINGS_FILE = DATA_DIR / "settings.json"
TEMPLATE_FILE = DATA_DIR / "template.json"
TEMPLATES_DIR = DATA_DIR / "templates"
LOG_FILE = DATA_DIR / "debug.log"
LIBRARY_DB_FILE = DATA_DIR / "character_library.sqlite3"
DATA_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
CARD_IMAGES_DIR = DATA_DIR / "card_images"
CARD_IMAGES_DIR.mkdir(exist_ok=True)
GENERATED_IMAGES_DIR = CARD_IMAGES_DIR / "generated"
GENERATED_IMAGES_DIR.mkdir(exist_ok=True)
VISION_IMAGES_DIR = DATA_DIR / "vision_images"
VISION_IMAGES_DIR.mkdir(exist_ok=True)
CONCEPT_ATTACHMENTS_DIR = DATA_DIR / "concept_attachments"
CONCEPT_ATTACHMENTS_DIR.mkdir(exist_ok=True)
IMPORT_UPLOADS_DIR = DATA_DIR / "import_uploads"
IMPORT_UPLOADS_DIR.mkdir(exist_ok=True)
# Character workspace/library lives beside exports so every character keeps card, project, images, emotion prompts, and zips together.
CHARACTER_LIBRARY_DIR = EXPORT_DIR


class TextRefusalForLiteFallback(Exception):
    """Raised when the primary text model refuses and backup Lite Mode should take over."""

    def __init__(self, primary_response=""):
        super().__init__("Primary text model refused; backup Lite Mode fallback required.")
        self.primary_response = primary_response or ""

DEFAULT_SETTINGS = {
    "apiBaseUrl": "https://nano-gpt.com/api/v1",
    "apiKey": "",
    "model": "",
    "aiSuggestionModel": "",
    "backupTextModel": "",
    "backupTextMode": "same",
    "temperature": 0.75,
    "maxInputTokens": 200000,
    "maxOutputTokens": 131000,
    "apiTimeoutSeconds": 300,
    "apiRetryCount": 2,
    "mode": "full",
    "frontend": "front_porch",
    "firstMessageStyle": "cinematic",
    "alternateFirstMessages": 2,
    "exportFormat": "chara_v2_png",
    "cardImagePath": "",
    "sdBaseUrl": "http://127.0.0.1:7860",
    "sdModel": "",
    "sdSteps": 28,
    "sdCfgScale": 7.0,
    "sdSampler": "Euler a",
    "emotionImageEmotions": ["neutral"],
    "alternateFirstMessageStyles": [],
    "cardMode": "single",
    "multiCharacterCount": 2,
    "sharedScenePolicy": "ai_reconcile",
    "visionApiBaseUrl": "",
    "visionApiKey": "",
    "visionModel": "",
    "visionImagePath": "",
    "activeTemplateName": "Default",
    "frontPorchDataFolder": "",
    "browserTagMerges": {},
    "browserVirtualFolders": [],
    "browserVirtualFolderAssignments": {},
    "browserShowSubfolders": False,
}

DEFAULT_TEMPLATE = {'globalRules': ['You are a fictional character generator and formatter.',
                 "Convert the user's concept into a concise roleplay character card.",
                 'Use only the enabled sections in this template and keep the same section order.',
                 'Do not add extra sections unless the user asks for them.',
                 'All primary characters and romantic participants must be 18 or older.',
                 'Use {{char}} for the character and {{user}} for the user when useful.',
                 'Keep details specific, playable, and consistent instead of overly long.',
                 'Prefer compact paragraphs and short bullet lists that work in smaller context '
                 'windows.'],
 'sections': [{'id': 'name',
               'title': 'Name',
               'enabled': True,
               'category': 'core',
               'description': "The character's full name or display name.",
               'fields': []},
              {'id': 'description',
               'title': 'Description',
               'enabled': True,
               'category': 'core',
               'description': 'Visible appearance and quick external summary only. Keep it '
                              'compact.',
               'fields': [{'id': 'age', 'label': 'Age', 'enabled': True, 'hint': '18+ only.'},
                          {'id': 'appearance',
                           'label': 'Appearance',
                           'enabled': True,
                           'hint': 'Face, hair, eyes, body type, notable features.'},
                          {'id': 'outfit',
                           'label': 'Outfit Style',
                           'enabled': True,
                           'hint': 'Usual clothing or starting outfit.'}]},
              {'id': 'personality',
               'title': 'Personality',
               'enabled': True,
               'category': 'core',
               'description': 'Core traits and behavior. Focus on what affects roleplay.',
               'fields': [{'id': 'traits',
                           'label': 'Personality Traits',
                           'enabled': True,
                           'hint': '3-6 defining traits.'},
                          {'id': 'motivation',
                           'label': 'Motivation',
                           'enabled': True,
                           'hint': 'What they want and why.'},
                          {'id': 'behavior',
                           'label': 'Behavior Toward {{user}}',
                           'enabled': True,
                           'hint': 'How they act with {{user}} at the start.'},
                          {'id': 'speech',
                           'label': 'Speech Style',
                           'enabled': True,
                           'hint': 'Tone, vocabulary, quirks, formality.'}]},
              {'id': 'scenario',
               'title': 'Scenario',
               'enabled': True,
               'category': 'core',
               'description': 'The starting situation for the chat. Mention {{user}} and keep it '
                              'immediately playable.',
               'fields': []},
              {'id': 'first_message',
               'title': 'First Message',
               'enabled': True,
               'category': 'core',
               'description': 'Opening message from {{char}}. Include a small scene setup and '
                              'natural dialogue to {{user}}.',
               'fields': []},
              {'id': 'alternate_first_messages',
               'title': 'Alternative First Messages',
               'enabled': False,
               'category': 'extras',
               'description': 'Optional alternate openings. Disabled by default for small-context '
                              'cards.',
               'fields': []},
              {'id': 'example_dialogues',
               'title': 'Example Dialogues',
               'enabled': True,
               'category': 'core',
               'description': '2-3 short examples in SillyTavern-compatible style. No # prefix.',
               'fields': []},
              {'id': 'tags',
               'title': 'Tags',
               'enabled': True,
               'category': 'core',
               'description': '6-10 lowercase comma-separated tags.',
               'fields': []},
              {'id': 'lorebook',
               'title': 'Lorebook Entries',
               'enabled': False,
               'category': 'extras',
               'description': 'Optional concise lore entries. Disabled by default for smaller '
                              'context windows.',
               'fields': []},
              {'id': 'system_prompt',
               'title': 'Custom System Prompt',
               'enabled': False,
               'category': 'advanced',
               'description': 'Optional behavior rules. Leave disabled unless needed.',
               'fields': []},
              {'id': 'state_tracking',
               'title': 'State Tracking',
               'enabled': False,
               'category': 'front_porch',
               'description': 'Optional Front Porch realism/state values. Disabled by default for '
                              'compact cards.',
               'fields': [{'id': 'emotion',
                           'label': 'Starting Emotion',
                           'enabled': True,
                           'hint': 'Primary emotional state.'},
                          {'id': 'objective',
                           'label': 'Current Objective',
                           'enabled': True,
                           'hint': 'Immediate goal.'}]},
              {'id': 'stable_diffusion',
               'title': 'Stable Diffusion Prompt',
               'enabled': False,
               'category': 'image',
               'description': 'Optional image prompt. Disabled by default for text-only '
                              'small-context card creation.',
               'fields': [{'id': 'positive',
                           'label': 'Positive Prompt',
                           'enabled': True,
                           'hint': 'Comma-separated visual descriptors.'},
                          {'id': 'negative',
                           'label': 'Negative Prompt',
                           'enabled': True,
                           'hint': 'low quality, bad anatomy, blurry, watermark, text'}]}],
 'qa': {'enabled': False,
        'questions': ['What does this character want from {{user}} at the start?',
                      'What personality flaw or contradiction makes them interesting?',
                      'What should the first scene feel like?'],
        'sections': [{'id': 'qa_basic',
                      'title': 'Basic Character Depth',
                      'enabled': True,
                      'collapsed': False,
                      'questions': [{'enabled': True,
                                     'text': 'What does this character want from {{user}} at the '
                                             'start?'},
                                    {'enabled': True,
                                     'text': 'What personality flaw or contradiction makes them '
                                             'interesting?'},
                                    {'enabled': True,
                                     'text': 'What should the first scene feel like?'}]}]}}

FIRST_MESSAGE_STYLES = {
    "cinematic": "Cinematic: vivid environmental setup, sensory detail, natural transition into dialogue.",
    "direct_chat": "Direct Chat: short, natural, immediately interactive, less narration.",
    "slow_burn": "Slow Burn: atmospheric, emotionally restrained, subtle tension.",
    "flirty": "Flirty: playful, teasing, confident, but still character-consistent.",
    "dramatic": "Dramatic: heightened stakes, strong emotional hook, scene-forward.",
    "comedic": "Comedic: light, expressive, characterful, with a funny opening beat.",
    "explicit": "Explicit: intense, adult, direct, sensual, and unfiltered while staying character-consistent."
}


EMOTION_OPTIONS = [
    "admiration", "affection", "amusement", "anger", "annoyance", "anticipation", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment", "disapproval", "disgust",
    "embarrassment", "excitement", "fear", "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse", "sadness", "surprise", "neutral"
]

class Api:
    def __init__(self):
        self.settings = self._load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        self.template = self._normalise_template(self._load_json(TEMPLATE_FILE, DEFAULT_TEMPLATE))
        self._save_json(TEMPLATE_FILE, self.template)
        self.cancel_event = threading.Event()
        self._last_browser_description_source = "extracted"
        self._init_library_db()

    def _load_json(self, path, default):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        path.write_text(json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.loads(json.dumps(default))

    def _save_json(self, path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _library_connect(self):
        conn = sqlite3.connect(str(LIBRARY_DB_FILE))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_library_db(self):
        """Create the browser library database and migrate old settings-based folders/assignments."""
        DATA_DIR.mkdir(exist_ok=True)
        with self._library_connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS browser_folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS browser_cards (
                    project_path TEXT PRIMARY KEY,
                    folder_path TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    virtual_folder_id TEXT NOT NULL DEFAULT '',
                    updated_ts REAL NOT NULL DEFAULT 0,
                    last_seen_ts REAL NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    project_hash TEXT NOT NULL DEFAULT '',
                    output_hash TEXT NOT NULL DEFAULT '',
                    card_png_path TEXT NOT NULL DEFAULT '',
                    card_png_hash TEXT NOT NULL DEFAULT '',
                    image_path TEXT NOT NULL DEFAULT '',
                    image_hash TEXT NOT NULL DEFAULT '',
                    thumbnail_data_url TEXT NOT NULL DEFAULT '',
                    browser_description TEXT NOT NULL DEFAULT '',
                    browser_description_source TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    output_preview TEXT NOT NULL DEFAULT '',
                    has_emotion_images INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_cards_virtual_folder ON browser_cards(virtual_folder_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_cards_last_seen ON browser_cards(last_seen_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_folders_parent ON browser_folders(parent_id)")
            # Lightweight migrations for older browser-library databases.
            existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(browser_cards)").fetchall()}
            new_cols = {
                "project_hash": "TEXT NOT NULL DEFAULT ''",
                "output_hash": "TEXT NOT NULL DEFAULT ''",
                "card_png_path": "TEXT NOT NULL DEFAULT ''",
                "card_png_hash": "TEXT NOT NULL DEFAULT ''",
                "image_path": "TEXT NOT NULL DEFAULT ''",
                "image_hash": "TEXT NOT NULL DEFAULT ''",
                "thumbnail_data_url": "TEXT NOT NULL DEFAULT ''",
                "browser_description": "TEXT NOT NULL DEFAULT ''",
                "browser_description_source": "TEXT NOT NULL DEFAULT ''",
                "tags_json": "TEXT NOT NULL DEFAULT '[]'",
                "output_preview": "TEXT NOT NULL DEFAULT ''",
                "has_emotion_images": "INTEGER NOT NULL DEFAULT 0",
                "metadata_json": "TEXT NOT NULL DEFAULT ''",
            }
            for col, ddl in new_cols.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE browser_cards ADD COLUMN {col} {ddl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_cards_project_hash ON browser_cards(project_hash)")

            # Migrate old settings virtual folders into DB. This is idempotent.
            folders = self.settings.get("browserVirtualFolders") if isinstance(self.settings.get("browserVirtualFolders"), list) else []
            for item in folders:
                if not isinstance(item, dict):
                    continue
                fid = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
                parent = str(item.get("parentId") or "").strip()
                if fid and name:
                    conn.execute(
                        "INSERT INTO browser_folders(id, name, parent_id) VALUES(?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, parent_id=excluded.parent_id, updated_at=CURRENT_TIMESTAMP",
                        (fid, name[:120], parent),
                    )
            conn.commit()

    def _library_folders(self):
        self._init_library_db()
        with self._library_connect() as conn:
            rows = conn.execute("SELECT id, name, parent_id FROM browser_folders ORDER BY lower(name), id").fetchall()
        return [{"id": r["id"], "name": r["name"], "parentId": r["parent_id"] or ""} for r in rows]

    def _library_known_folder_ids(self):
        return {f["id"] for f in self._library_folders()}

    def _library_card_exists(self, project_path):
        self._init_library_db()
        key = str(Path(project_path).resolve())
        with self._library_connect() as conn:
            row = conn.execute("SELECT 1 FROM browser_cards WHERE project_path=?", (key,)).fetchone()
        return row is not None

    def _library_get_card_folder(self, project_path, fallback=""):
        self._init_library_db()
        key = str(Path(project_path).resolve())
        with self._library_connect() as conn:
            row = conn.execute("SELECT virtual_folder_id FROM browser_cards WHERE project_path=? AND deleted=0", (key,)).fetchone()
        return str(row["virtual_folder_id"] or "").strip() if row else str(fallback or "").strip()

    def _library_upsert_card(self, project_path, folder_path, name, virtual_folder_id=None, updated_ts=None, metadata=None):
        """Upsert a card row. Existing DB folder assignment wins unless virtual_folder_id is explicitly supplied.

        metadata is the cached browser/index payload. It lets the browser use SQLite
        instead of reparsing every project/image on each refresh.
        """
        self._init_library_db()
        key = str(Path(project_path).resolve())
        folder = str(Path(folder_path).resolve()) if folder_path else ""
        name = str(name or "").strip()
        now = time.time()
        if updated_ts is None:
            try:
                updated_ts = Path(project_path).stat().st_mtime
            except Exception:
                updated_ts = now
        metadata = metadata if isinstance(metadata, dict) else {}
        with self._library_connect() as conn:
            existing = conn.execute("SELECT * FROM browser_cards WHERE project_path=?", (key,)).fetchone()
            existing_d = dict(existing) if existing else {}
            if not metadata and existing_d:
                # Folder-only updates should not wipe cached card metadata/images.
                try:
                    existing_tags = json.loads(existing_d.get("tags_json") or "[]")
                except Exception:
                    existing_tags = []
                metadata = {
                    "projectHash": existing_d.get("project_hash") or "",
                    "outputHash": existing_d.get("output_hash") or "",
                    "cardPngPath": existing_d.get("card_png_path") or "",
                    "cardPngHash": existing_d.get("card_png_hash") or "",
                    "imagePath": existing_d.get("image_path") or "",
                    "imageHash": existing_d.get("image_hash") or "",
                    "thumbnail": existing_d.get("thumbnail_data_url") or "",
                    "browserDescription": existing_d.get("browser_description") or "",
                    "browserDescriptionSource": existing_d.get("browser_description_source") or "",
                    "tags": existing_tags if isinstance(existing_tags, list) else [],
                    "outputPreview": existing_d.get("output_preview") or "",
                    "hasEmotionImages": bool(existing_d.get("has_emotion_images")),
                }
            if virtual_folder_id is None:
                chosen_folder = str(existing_d.get("virtual_folder_id") or "").strip() if existing_d else ""
            else:
                chosen_folder = str(virtual_folder_id or "").strip()
            conn.execute(
                "INSERT INTO browser_cards(" 
                "project_path, folder_path, name, virtual_folder_id, updated_ts, last_seen_ts, deleted, "
                "project_hash, output_hash, card_png_path, card_png_hash, image_path, image_hash, "
                "thumbnail_data_url, browser_description, browser_description_source, tags_json, "
                "output_preview, has_emotion_images, metadata_json" 
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(project_path) DO UPDATE SET "
                "folder_path=excluded.folder_path, name=excluded.name, "
                "updated_ts=excluded.updated_ts, last_seen_ts=excluded.last_seen_ts, deleted=0, "
                "virtual_folder_id=excluded.virtual_folder_id, "
                "project_hash=excluded.project_hash, output_hash=excluded.output_hash, "
                "card_png_path=excluded.card_png_path, card_png_hash=excluded.card_png_hash, "
                "image_path=excluded.image_path, image_hash=excluded.image_hash, "
                "thumbnail_data_url=excluded.thumbnail_data_url, "
                "browser_description=excluded.browser_description, browser_description_source=excluded.browser_description_source, "
                "tags_json=excluded.tags_json, output_preview=excluded.output_preview, "
                "has_emotion_images=excluded.has_emotion_images, metadata_json=excluded.metadata_json",
                (
                    key, folder, name, chosen_folder, float(updated_ts or 0), now, 0,
                    str(metadata.get("projectHash") or ""),
                    str(metadata.get("outputHash") or ""),
                    str(metadata.get("cardPngPath") or ""),
                    str(metadata.get("cardPngHash") or ""),
                    str(metadata.get("imagePath") or ""),
                    str(metadata.get("imageHash") or ""),
                    str(metadata.get("thumbnail") or ""),
                    str(metadata.get("browserDescription") or ""),
                    str(metadata.get("browserDescriptionSource") or ""),
                    json.dumps(metadata.get("tags") if isinstance(metadata.get("tags"), list) else [], ensure_ascii=False),
                    str(metadata.get("outputPreview") or ""),
                    1 if metadata.get("hasEmotionImages") else 0,
                    json.dumps(metadata.get("extra") if isinstance(metadata.get("extra"), dict) else {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return chosen_folder

    def _library_get_card_row(self, project_path):
        self._init_library_db()
        key = str(Path(project_path).resolve())
        with self._library_connect() as conn:
            row = conn.execute("SELECT * FROM browser_cards WHERE project_path=? AND deleted=0", (key,)).fetchone()
        return dict(row) if row else None

    def _hash_file(self, path):
        try:
            p = Path(str(path or ""))
            if not p.exists() or not p.is_file():
                return ""
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def _hash_text(self, text):
        try:
            return hashlib.sha256(str(text or "").encode("utf-8", errors="ignore")).hexdigest()
        except Exception:
            return ""

    def _latest_card_png_for_folder(self, folder, name):
        folder = Path(folder)
        latest_pngs = [folder / f"{self._safe_slug(name)}_latest_cardv2.png"] + sorted(folder.glob("*_cardv2.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        return next((p for p in latest_pngs if p and Path(p).exists()), None)

    def _browser_card_from_db_row(self, row):
        try:
            tags = json.loads(row.get("tags_json") or "[]")
            if not isinstance(tags, list):
                tags = []
        except Exception:
            tags = []
        updated_ts = float(row.get("updated_ts") or 0)
        return {
            "name": row.get("name") or Path(row.get("folder_path") or "").name,
            "folder": row.get("folder_path") or "",
            "projectPath": row.get("project_path") or "",
            "updated": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated_ts or time.time())),
            "thumbnail": row.get("thumbnail_data_url") or "",
            "browserDescription": row.get("browser_description") or "",
            "browserDescriptionSource": row.get("browser_description_source") or "extracted",
            "tags": tags,
            "virtualFolderId": str(row.get("virtual_folder_id") or ""),
            "outputPreview": row.get("output_preview") or "",
            "hasEmotionImages": bool(row.get("has_emotion_images")),
            "cached": True,
            "projectHash": row.get("project_hash") or "",
            "cardPngHash": row.get("card_png_hash") or "",
            "imageHash": row.get("image_hash") or "",
        }

    def _refresh_library_cache_for_project(self, project_path, force=False):
        """Refresh one project cache if its project/card/image hashes changed."""
        path = Path(project_path)
        if not path.exists():
            return None
        folder = path.parent
        project_hash = self._hash_file(path)
        row = self._library_get_card_row(path)
        if row and not force and str(row.get("project_hash") or "") == project_hash:
            # Do a quick real-file hash check for the cached images too.
            card_png_path = str(row.get("card_png_path") or "")
            image_path = str(row.get("image_path") or "")
            card_hash_ok = (not card_png_path) or self._hash_file(card_png_path) == str(row.get("card_png_hash") or "")
            image_hash_ok = (not image_path) or self._hash_file(image_path) == str(row.get("image_hash") or "")
            if card_hash_ok and image_hash_ok:
                return self._browser_card_from_db_row(row)

        payload = json.loads(path.read_text(encoding="utf-8"))
        project = payload.get("project", payload) if isinstance(payload, dict) else {}
        if not isinstance(project, dict):
            return None
        workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
        name = project.get("name") or self._extract_name(project.get("output") or "") or folder.name
        output = project.get("output") or ""
        concept = project.get("concept") or ""
        image_path = project.get("imagePath") or project.get("cardImagePath") or workspace.get("cardImagePath") or ""
        card_png = self._latest_card_png_for_folder(folder, name)
        thumb_source = str(card_png) if card_png else image_path
        browser_description = str(project.get("browserDescription") or "").strip()
        browser_description_source = str(project.get("browserDescriptionSource") or "").strip().lower()
        if browser_description:
            browser_description_source = browser_description_source or "ai"
        if not browser_description:
            browser_description = self._fallback_browser_description(output, concept)
            browser_description_source = "extracted"
        tags = project.get("tags") if isinstance(project.get("tags"), list) else []
        if not tags:
            tags = self._extract_tags_from_output(output, project.get("template") or self.template)
        old_assignment = self._get_virtual_folder_assignment(path, folder, name, project.get("virtualFolderId") or "")
        if row:
            virtual_folder_id = self._library_upsert_card(path, folder, name, None, path.stat().st_mtime, {
                "projectHash": project_hash,
                "outputHash": self._hash_text(output),
                "cardPngPath": str(card_png or ""),
                "cardPngHash": self._hash_file(card_png) if card_png else "",
                "imagePath": str(image_path or ""),
                "imageHash": self._hash_file(image_path) if image_path else "",
                "thumbnail": self._image_data_url(thumb_source or image_path),
                "browserDescription": browser_description,
                "browserDescriptionSource": browser_description_source,
                "tags": tags,
                "outputPreview": output[:500],
                "hasEmotionImages": any((folder / f"{e}.png").exists() for e in EMOTION_OPTIONS),
                "extra": {"conceptHash": self._hash_text(concept)},
            })
        else:
            virtual_folder_id = self._library_upsert_card(path, folder, name, old_assignment, path.stat().st_mtime, {
                "projectHash": project_hash,
                "outputHash": self._hash_text(output),
                "cardPngPath": str(card_png or ""),
                "cardPngHash": self._hash_file(card_png) if card_png else "",
                "imagePath": str(image_path or ""),
                "imageHash": self._hash_file(image_path) if image_path else "",
                "thumbnail": self._image_data_url(thumb_source or image_path),
                "browserDescription": browser_description,
                "browserDescriptionSource": browser_description_source,
                "tags": tags,
                "outputPreview": output[:500],
                "hasEmotionImages": any((folder / f"{e}.png").exists() for e in EMOTION_OPTIONS),
                "extra": {"conceptHash": self._hash_text(concept)},
            })
        if virtual_folder_id != str(project.get("virtualFolderId") or ""):
            try:
                project["virtualFolderId"] = virtual_folder_id
                workspace["virtualFolderId"] = virtual_folder_id
                project["workspace"] = workspace
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                # Project changed because of portability mirror; refresh hash but keep same cached metadata.
                self._library_upsert_card(path, folder, name, virtual_folder_id, path.stat().st_mtime, {
                    "projectHash": self._hash_file(path),
                    "outputHash": self._hash_text(output),
                    "cardPngPath": str(card_png or ""),
                    "cardPngHash": self._hash_file(card_png) if card_png else "",
                    "imagePath": str(image_path or ""),
                    "imageHash": self._hash_file(image_path) if image_path else "",
                    "thumbnail": self._image_data_url(thumb_source or image_path),
                    "browserDescription": browser_description,
                    "browserDescriptionSource": browser_description_source,
                    "tags": tags,
                    "outputPreview": output[:500],
                    "hasEmotionImages": any((folder / f"{e}.png").exists() for e in EMOTION_OPTIONS),
                    "extra": {"conceptHash": self._hash_text(concept)},
                })
            except Exception:
                pass
        row = self._library_get_card_row(path)
        return self._browser_card_from_db_row(row) if row else None

    def _library_set_card_folder(self, project_path, folder_id):
        self._init_library_db()
        key = str(Path(project_path).resolve())
        folder_id = str(folder_id or "").strip()
        with self._library_connect() as conn:
            conn.execute(
                "UPDATE browser_cards SET virtual_folder_id=?, updated_ts=?, last_seen_ts=?, deleted=0 WHERE project_path=?",
                (folder_id, time.time(), time.time(), key),
            )
            # If the card was never scanned/upserted, create a minimal row so the assignment still survives.
            if conn.total_changes == 0:
                conn.execute(
                    "INSERT OR REPLACE INTO browser_cards(project_path, folder_path, name, virtual_folder_id, updated_ts, last_seen_ts, deleted) VALUES(?,?,?,?,?,?,0)",
                    (key, str(Path(project_path).parent.resolve()), Path(project_path).parent.name, folder_id, time.time(), time.time()),
                )
            conn.commit()

    def _library_delete_folders(self, folder_ids):
        ids = [str(x or "").strip() for x in (folder_ids or []) if str(x or "").strip()]
        if not ids:
            return
        self._init_library_db()
        with self._library_connect() as conn:
            conn.executemany("DELETE FROM browser_folders WHERE id=?", [(x,) for x in ids])
            conn.executemany("UPDATE browser_cards SET virtual_folder_id='', updated_ts=?, last_seen_ts=? WHERE virtual_folder_id=?", [(time.time(), time.time(), x) for x in ids])
            conn.commit()

    def _normalise_template(self, template):
        template = template or {}
        if "globalRules" not in template or not isinstance(template.get("globalRules"), list):
            template["globalRules"] = []
        if "sections" not in template or not isinstance(template.get("sections"), list):
            template["sections"] = []
        qa = template.get("qa")
        if not isinstance(qa, dict):
            qa = {}
        if "enabled" not in qa:
            qa["enabled"] = False

        def normalise_question(q):
            if isinstance(q, dict):
                value = str(q.get("text", q.get("question", ""))).strip()
                enabled = q.get("enabled", True) is not False
            else:
                value = str(q or "").strip()
                enabled = True
            return {"enabled": enabled, "text": value} if value else None

        sections = qa.get("sections")
        if not isinstance(sections, list):
            legacy_questions = qa.get("questions")
            if not isinstance(legacy_questions, list):
                legacy_questions = []
            converted = []
            for q in legacy_questions:
                nq = normalise_question(q)
                if nq:
                    converted.append(nq)
            sections = [{
                "id": "qa_general",
                "title": "General",
                "enabled": True,
                "collapsed": False,
                "questions": converted,
            }] if converted else []

        cleaned_sections = []
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or f"Q&A Section {idx + 1}").strip()
            questions = section.get("questions")
            if not isinstance(questions, list):
                questions = []
            cleaned_questions = []
            for q in questions:
                nq = normalise_question(q)
                if nq:
                    cleaned_questions.append(nq)
            cleaned_sections.append({
                "id": str(section.get("id") or f"qa_section_{idx + 1}"),
                "title": title,
                "enabled": section.get("enabled", True) is not False,
                "collapsed": section.get("collapsed", False) is True,
                "questions": cleaned_questions,
            })
        qa["sections"] = cleaned_sections
        qa["questions"] = [q["text"] for s in cleaned_sections if s.get("enabled", True) for q in s.get("questions", []) if q.get("enabled", True) and q.get("text")]
        template["qa"] = qa
        return template

    def _log_event(self, event, payload=None):
        try:
            entry = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": event,
                "payload": payload or {},
            }
            LOG_FILE.parent.mkdir(exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, indent=2) + "\n---\n")
            # Keep the debug log useful but bounded. This prevents giant repair logs
            # from making the UI sluggish after long sessions.
            max_bytes = 250_000
            try:
                if LOG_FILE.stat().st_size > max_bytes:
                    text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
                    LOG_FILE.write_text(text[-max_bytes:], encoding="utf-8")
            except Exception:
                pass
        except Exception:
            pass

    def get_debug_log(self):
        try:
            if not LOG_FILE.exists():
                return {"ok": True, "path": str(LOG_FILE), "text": "No debug log yet."}
            return {"ok": True, "path": str(LOG_FILE), "text": LOG_FILE.read_text(encoding="utf-8")[-60000:]}
        except Exception as e:
            return {"ok": False, "error": str(e)}


    def _extract_first_json_object(self, raw):
        """Return the first balanced JSON-looking object from a model response."""
        raw = str(raw or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
        start = raw.find("{")
        if start < 0:
            return raw
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(raw[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return raw[start:i+1]
        return raw[start:]

    def _repair_jsonish(self, raw):
        """Best-effort repair for small JSON objects returned by weaker models."""
        s = self._extract_first_json_object(raw)
        s = s.strip().replace("\ufeff", "")
        # Normalize curly quotes that sometimes sneak into compact models.
        s = s.translate(str.maketrans({
            "“": '"', "”": '"', "„": '"', "‟": '"',
            "‘": "'", "’": "'",
        }))
        # Remove JS-style comments.
        s = re.sub(r"//.*?(?=\n|$)", "", s)
        s = re.sub(r"/\*[\s\S]*?\*/", "", s)
        # Quote unquoted object keys.
        s = re.sub(r"([,{]\s*)([A-Za-z_][A-Za-z0-9_\-]*)(\s*:)", r'\1"\2"\3', s)
        # Add common missing commas between adjacent object members.
        s = re.sub(r'([}\]"0-9A-Za-z])\s+("[A-Za-z_][A-Za-z0-9_\-]*"\s*:)', r'\1, \2', s)
        # Remove trailing commas.
        s = re.sub(r",\s*([}\]])", r"\1", s)
        return s

    def _loads_model_json(self, raw):
        """Parse strict JSON first, then repaired JSON, then Python-literal-ish JSON."""
        candidates = [self._extract_first_json_object(raw), self._repair_jsonish(raw)]
        last_error = None
        for cand in candidates:
            try:
                return json.loads(cand)
            except Exception as e:
                last_error = e
        try:
            import ast
            return ast.literal_eval(candidates[-1])
        except Exception:
            pass
        raise last_error or ValueError("Could not parse model JSON")

    def _fallback_randomize_fields_from_text(self, raw, field_catalog):
        """Very small fallback when model returns malformed JSON: parse 'fieldId: value' lines."""
        valid = {str(f.get("id")): f for f in (field_catalog or []) if f.get("id")}
        fields = {}
        for line in str(raw or "").splitlines():
            line = line.strip().strip("-•, ")
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip().strip('"\'`')
            val = val.strip().strip(',').strip().strip('"\'`')
            if key in valid and val:
                fields[key] = val
        return fields

    def clear_debug_log(self):
        try:
            LOG_FILE.write_text("", encoding="utf-8")
            return {"ok": True, "path": str(LOG_FILE)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def cancel_current_task(self):
        self.cancel_event.set()
        self._log_event("cancel_requested", {"message": "User requested cancellation."})
        return {"ok": True, "message": "Cancellation requested. The current network call may finish before stopping."}

    def _reset_cancel(self):
        self.cancel_event.clear()

    def _raise_if_cancelled(self):
        if self.cancel_event.is_set():
            raise RuntimeError("Task cancelled by user.")

    def _clean_model_name(self, value):
        value = str(value or "").strip()
        if not value:
            return ""
        # Fix a common UI/editing accident where a newly pasted model gets appended
        # directly onto the old model with no separator, e.g.
        # old-model-name + mlabonne/NeuralDaredevil-8B-abliterated.
        known_provider_markers = [
            "mlabonne/", "openai/", "anthropic/", "google/", "meta-llama/",
            "mistralai/", "deepseek/", "qwen/", "moonshotai/", "huihui-ai/",
            "sao10k/", "nousresearch/", "cognitivecomputations/"
        ]
        lowered = value.lower()
        best = None
        for marker in known_provider_markers:
            start = 0
            marker_l = marker.lower()
            while True:
                idx = lowered.find(marker_l, start)
                if idx == -1:
                    break
                if idx > 0:
                    before = value[idx - 1]
                    # If this provider starts immediately after another model name rather
                    # than after a separator, treat it as the intended replacement.
                    if before not in " \t\n,;|":
                        best = idx
                start = idx + 1
        if best is not None:
            value = value[best:].strip()
        # If a user pasted several whitespace/comma-separated model names, use the last.
        parts = [x for x in re.split(r"[\s,;|]+", value) if x]
        if len(parts) > 1:
            value = parts[-1]
        return value

    def _normalise_settings(self, settings):
        settings = {**DEFAULT_SETTINGS, **(settings or {})}
        # Backwards compatibility with v0.1.0/v0.1.1, which had a single Max Tokens field.
        if "maxTokens" in settings:
            legacy_value = int(settings.get("maxTokens") or DEFAULT_SETTINGS["maxOutputTokens"])
            settings.setdefault("maxOutputTokens", legacy_value)
            settings.pop("maxTokens", None)
        settings["maxInputTokens"] = max(512, int(settings.get("maxInputTokens") or DEFAULT_SETTINGS["maxInputTokens"]))
        settings["maxOutputTokens"] = max(256, int(settings.get("maxOutputTokens") or DEFAULT_SETTINGS["maxOutputTokens"]))
        try:
            settings["apiTimeoutSeconds"] = max(30, min(1800, int(settings.get("apiTimeoutSeconds") or DEFAULT_SETTINGS["apiTimeoutSeconds"])))
        except Exception:
            settings["apiTimeoutSeconds"] = DEFAULT_SETTINGS["apiTimeoutSeconds"]
        try:
            settings["apiRetryCount"] = max(0, min(6, int(settings.get("apiRetryCount") or DEFAULT_SETTINGS["apiRetryCount"])))
        except Exception:
            settings["apiRetryCount"] = DEFAULT_SETTINGS["apiRetryCount"]
        settings["frontPorchDataFolder"] = str(settings.get("frontPorchDataFolder") or "").strip()
        settings["sdBaseUrl"] = str(settings.get("sdBaseUrl") or DEFAULT_SETTINGS["sdBaseUrl"]).strip() or DEFAULT_SETTINGS["sdBaseUrl"]
        settings["sdModel"] = str(settings.get("sdModel") or "").strip()
        merges = settings.get("browserTagMerges") if isinstance(settings.get("browserTagMerges"), dict) else {}
        clean_merges = {}
        for raw_from, raw_to in merges.items():
            from_key = str(raw_from or "").strip().lower()
            to_tag = str(raw_to or "").strip()
            if from_key and to_tag and from_key != to_tag.lower():
                clean_merges[from_key] = to_tag[:120]
        settings["browserTagMerges"] = clean_merges
        folders = settings.get("browserVirtualFolders") if isinstance(settings.get("browserVirtualFolders"), list) else []
        clean_folders = []
        seen_folders = set()
        for item in folders:
            if not isinstance(item, dict):
                continue
            fid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            parent = str(item.get("parentId") or "").strip()
            if fid and name and fid not in seen_folders:
                seen_folders.add(fid)
                clean_folders.append({"id": fid, "name": name[:120], "parentId": parent})
        settings["browserVirtualFolders"] = clean_folders
        settings["browserShowSubfolders"] = bool(settings.get("browserShowSubfolders", DEFAULT_SETTINGS.get("browserShowSubfolders", False)))
        emo = settings.get("emotionImageEmotions", DEFAULT_SETTINGS["emotionImageEmotions"])
        if not isinstance(emo, list):
            emo = DEFAULT_SETTINGS["emotionImageEmotions"]
        settings["emotionImageEmotions"] = [e for e in emo if e in EMOTION_OPTIONS]
        alt_styles = settings.get("alternateFirstMessageStyles", [])
        if not isinstance(alt_styles, list):
            alt_styles = []
        cleaned_styles = []
        for s in alt_styles:
            s = str(s or "").strip()
            cleaned_styles.append(s if s in FIRST_MESSAGE_STYLES else "")
        settings["alternateFirstMessageStyles"] = cleaned_styles
        mode = str(settings.get("cardMode") or "single").strip().lower()
        settings["cardMode"] = "multi" if mode in {"multi", "multi_character", "multi-character"} else "single"
        try:
            settings["multiCharacterCount"] = max(2, min(12, int(settings.get("multiCharacterCount") or 2)))
        except Exception:
            settings["multiCharacterCount"] = 2
        settings["visionApiBaseUrl"] = str(settings.get("visionApiBaseUrl") or "").strip()
        settings["visionApiKey"] = str(settings.get("visionApiKey") or "").strip()
        settings["model"] = self._clean_model_name(settings.get("model"))
        settings["visionModel"] = self._clean_model_name(settings.get("visionModel"))
        settings["aiSuggestionModel"] = self._clean_model_name(settings.get("aiSuggestionModel"))
        settings["backupTextModel"] = self._clean_model_name(settings.get("backupTextModel"))
        backup_mode = str(settings.get("backupTextMode") or "same").strip().lower()
        settings["backupTextMode"] = "lite" if backup_mode in {"lite", "lite_mode", "lite-mode"} else "same"
        settings["visionImagePath"] = str(settings.get("visionImagePath") or "").strip()
        settings["activeTemplateName"] = str(settings.get("activeTemplateName") or "Default").strip() or "Default"
        # Character Card Forge is now Front Porch-first and Character Card V2-first.
        # Older installs sometimes kept the previous JSON default in data/settings.json,
        # so migrate old/unversioned settings back to PNG once.
        valid_exports = {"chara_v2_png", "chara_v2_json", "markdown"}
        previous_version = str(settings.get("settingsSchemaVersion") or "").strip()
        export_format = str(settings.get("exportFormat") or "").strip()
        if export_format not in valid_exports:
            export_format = "chara_v2_png"
        if previous_version in {"", "0.5.9"} and export_format == "chara_v2_json":
            export_format = "chara_v2_png"
        settings["exportFormat"] = export_format
        settings["frontend"] = "front_porch"
        settings["settingsSchemaVersion"] = "0.6.0"
        return settings


    def _safe_template_slug(self, name):
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name or "").strip()).strip("_")
        return slug or "template"

    def _template_file_for_name(self, name):
        return TEMPLATES_DIR / f"{self._safe_template_slug(name)}.json"

    def _list_prompt_templates(self):
        names = ["Default"]
        seen = {"default"}
        for file in sorted(TEMPLATES_DIR.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                name = str(data.get("name") or file.stem).strip() or file.stem
            except Exception:
                name = file.stem
            key = name.casefold()
            if key not in seen:
                names.append(name)
                seen.add(key)
        active = self.settings.get("activeTemplateName", "Default")
        if active and active.casefold() not in seen:
            names.append(active)
        return names

    def _save_named_template(self, name, template):
        payload = {"name": name, "template": template, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        path = self._template_file_for_name(name)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def get_state(self):
        self.settings = self._normalise_settings(self.settings)
        try:
            self.settings["browserVirtualFolders"] = self._library_folders()
        except Exception:
            pass
        self._save_json(SETTINGS_FILE, self.settings)
        return {"settings": self.settings, "template": self.template, "styles": FIRST_MESSAGE_STYLES, "emotions": EMOTION_OPTIONS, "templates": self._list_prompt_templates(), "activeTemplateName": self.settings.get("activeTemplateName", "Default")}

    def _network_timeout(self, settings=None, fallback=300):
        settings = settings or self.settings or {}
        try:
            return max(30, min(1800, int(settings.get("apiTimeoutSeconds") or fallback or DEFAULT_SETTINGS["apiTimeoutSeconds"])))
        except Exception:
            return fallback or DEFAULT_SETTINGS["apiTimeoutSeconds"]

    def _network_retries(self, settings=None):
        settings = settings or self.settings or {}
        try:
            return max(0, min(6, int(settings.get("apiRetryCount") or DEFAULT_SETTINGS["apiRetryCount"])))
        except Exception:
            return DEFAULT_SETTINGS["apiRetryCount"]

    def _urlopen_with_retries(self, req, settings=None, timeout=None, label="API request"):
        timeout = self._network_timeout(settings, timeout or DEFAULT_SETTINGS["apiTimeoutSeconds"])
        retries = self._network_retries(settings)
        last_exc = None
        for attempt in range(retries + 1):
            self._raise_if_cancelled()
            try:
                return urllib.request.urlopen(req, timeout=timeout)
            except urllib.error.HTTPError:
                # HTTP errors mean the server answered; do not retry/fallback as a network timeout.
                raise
            except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as e:
                last_exc = e
                reason = getattr(e, "reason", None)
                reason_text = str(reason or e)
                self._log_event("network_retry", {
                    "label": label,
                    "attempt": attempt + 1,
                    "max_attempts": retries + 1,
                    "timeout_seconds": timeout,
                    "error": reason_text[:1000],
                })
                if attempt >= retries:
                    raise RuntimeError(
                        f"{label} timed out or could not connect after {retries + 1} attempt(s) "
                        f"with a {timeout}s timeout. Last error: {reason_text[:500]}. "
                        "VPNs can sometimes slow or interrupt OpenAI-compatible API calls; try increasing API Timeout/Retry Count in AI Settings, changing VPN location, split-tunneling this app/browser, or temporarily disconnecting the VPN."
                    ) from e
                time.sleep(min(8, 1.5 * (attempt + 1)))
        raise RuntimeError(f"{label} failed: {last_exc}")

    def ai_builder_suggest(self, field_meta, builder_state, settings=None):
        """Suggest one builder field value using only Builder state, never concept/output text."""
        try:
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            base = (merged.get("apiBaseUrl") or "").rstrip("/")
            key = merged.get("apiKey") or ""
            suggestion_model = (merged.get("aiSuggestionModel") or merged.get("model") or "").strip()
            missing = []
            if not base:
                missing.append("API Base URL")
            if not suggestion_model:
                missing.append("AI Suggestion Model or Text Model")
            if self._api_key_required_for_base(base) and not key:
                missing.append("API Key")
            if missing:
                return {"ok": False, "error": "AI suggestion settings are incomplete: " + ", ".join(missing) + ". Open AI Settings and enter an AI Suggestion Model, or fall back to a Text Model."}
            field_meta = field_meta or {}
            builder_state = builder_state or {}
            options = field_meta.get("options") or []
            label = str(field_meta.get("label") or field_meta.get("id") or "field").strip()
            field_id = str(field_meta.get("id") or "").strip()
            kind = str(field_meta.get("kind") or "text").strip()
            current_value = str(field_meta.get("currentValue") or "").strip()
            prompt = "\n".join([
                "You are helping fill a character-card builder form.",
                "Use ONLY the builder state supplied below. Do not invent facts from any main concept, output text, or hidden context.",
                "Return strict JSON only with keys: value, reason.",
                "The value must be concise and directly usable in the form field.",
                "For select/dropdown fields, choose exactly one of the available options unless Custom is available and clearly better.",
                "If you choose Custom, return the custom text as value and set custom: true.",
                "Do not include markdown.",
                f"Target field id: {field_id}",
                f"Target field label: {label}",
                f"Field kind: {kind}",
                f"Current value: {current_value}",
                "Available options: " + (", ".join([str(o) for o in options]) if options else "free-text field"),
                "Builder state JSON:",
                json.dumps(builder_state, ensure_ascii=False, indent=2),
                "Return example: {\"value\": \"confident\", \"reason\": \"Matches the existing gyaru/social traits.\"}"
            ])
            payload = {
                "model": suggestion_model,
                "messages": [
                    {"role": "system", "content": "You make concise form-field suggestions for fictional character builders and return strict JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.45,
                "max_tokens": 500,
            }
            req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode("utf-8"), method="POST")
            req.add_header("Content-Type", "application/json")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            self._log_event("ai_builder_suggest_request", {"field": field_meta, "model": suggestion_model, "builder_state_keys": list(builder_state.keys())})
            with self._urlopen_with_retries(req, merged, timeout=90, label="AI suggestion") as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            parsed = self._loads_model_json(raw)
            value = str(parsed.get("value") or "").strip()
            reason = str(parsed.get("reason") or "").strip()
            custom = bool(parsed.get("custom", False))
            if options:
                lower_map = {str(o).strip().lower(): str(o).strip() for o in options}
                if value.lower() in lower_map:
                    value = lower_map[value.lower()]
                    custom = False
                elif "custom" in lower_map:
                    custom = True
                else:
                    # Best-effort fuzzy containment match.
                    for opt in options:
                        opt_s = str(opt).strip()
                        if opt_s and opt_s.lower() in value.lower():
                            value = opt_s
                            custom = False
                            break
            self._log_event("ai_builder_suggest_response", {"field_id": field_id, "value": value, "custom": custom, "reason": reason})
            return {"ok": True, "value": value, "custom": custom, "reason": reason, "raw": raw}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._log_event("ai_builder_suggest_error", {"status": e.code, "body": body[:1000]})
            return {"ok": False, "error": f"AI suggestion HTTP {e.code}: {body[:500]}"}
        except Exception as e:
            self._log_event("ai_builder_suggest_error", {"error": str(e)})
            return {"ok": False, "error": f"AI suggestion failed: {e}"}


    def ai_builder_randomize_preset(self, preset, field_catalog, builder_state=None, settings=None):
        """Generate a coherent randomized builder setup from a preset using only builder/preset data."""
        try:
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            base = (merged.get("apiBaseUrl") or "").rstrip("/")
            key = merged.get("apiKey") or ""
            suggestion_model = (merged.get("aiSuggestionModel") or merged.get("model") or "").strip()
            missing = []
            if not base:
                missing.append("API Base URL")
            if not suggestion_model:
                missing.append("AI Suggestion Model or Text Model")
            if self._api_key_required_for_base(base) and not key:
                missing.append("API Key")
            if missing:
                return {"ok": False, "error": "AI preset settings are incomplete: " + ", ".join(missing) + ". Open AI Settings and enter an AI Suggestion Model, or fall back to a Text Model."}

            preset = preset or {}
            field_catalog = field_catalog or []
            builder_state = builder_state or {}

            # Keep AI randomize intentionally tiny so an 8k-context suggestion model can handle it.
            group_focus = str(preset.get("groupFocus") or "all").strip() or "all"
            group_label = str(preset.get("groupLabel") or group_focus).strip() or group_focus
            compact_fields = []
            for f in field_catalog[:45]:
                fid = str(f.get("id") or "").strip()
                if not fid:
                    continue
                item = {
                    "id": fid,
                    "group": str(f.get("group") or group_focus).strip()[:20],
                    "label": str(f.get("label") or fid).strip()[:42],
                    "kind": str(f.get("kind") or "text").strip(),
                }
                opts = [str(o).strip() for o in (f.get("options") or []) if str(o).strip()]
                if opts:
                    item["options"] = opts[:10]
                compact_fields.append(item)
            compact_state = {}
            for k, v in (builder_state or {}).items():
                sv = str(v or "").strip()
                if sv:
                    compact_state[str(k)] = sv[:80]
            min_count = 8 if group_focus == "character" else (10 if group_focus == "personality" else 6)
            prompt = "\n".join([
                f"Create coherent randomized {group_label} choices from THEME. Strict JSON only.",
                "8k-context task: be concise. No markdown. Avoid contradictions with CURRENT.",
                f"Focus ONLY on the listed {group_label} fields. Fill at least {min_count} useful fields when available.",
                "Select fields must use one exact option. Free text should be short, specific, and usable in a form.",
                'Return valid minified JSON only. No explanations, no trailing commas, no markdown.',
                'Schema: {"fields":{"fieldId":"value"},"cardMode":"single|multi","multiCharacterCount":"2","notes":"short"}',
                "THEME=" + json.dumps({"name": preset.get("name"), "theme": preset.get("prompt") or preset.get("theme") or preset.get("description") or preset.get("name"), "tags": preset.get("tags", []), "groupFocus": group_focus}, ensure_ascii=False, separators=(",", ":"))[:1000],
                "CURRENT=" + json.dumps(compact_state, ensure_ascii=False, separators=(",", ":"))[:1200],
                "FIELDS=" + json.dumps(compact_fields, ensure_ascii=False, separators=(",", ":"))[:4300]
            ])
            payload = {
                "model": suggestion_model,
                "messages": [
                    {"role": "system", "content": "You generate coherent randomized form presets for fictional character builders and return strict JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.9,
                "max_tokens": 900,
            }
            req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode("utf-8"), method="POST")
            req.add_header("Content-Type", "application/json")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            self._log_event("ai_builder_randomize_preset_request", {"preset": preset.get("name"), "groupFocus": group_focus, "model": suggestion_model, "field_count": len(field_catalog), "compact_field_count": len(compact_fields), "prompt_chars": len(prompt)})
            with self._urlopen_with_retries(req, merged, timeout=120, label="AI randomize theme") as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            try:
                parsed = self._loads_model_json(raw)
                parse_repaired = True
            except Exception as parse_error:
                self._log_event("ai_builder_randomize_preset_parse_error", {"groupFocus": group_focus, "error": str(parse_error), "raw": raw[:1500]})
                parsed = {"fields": self._fallback_randomize_fields_from_text(raw, field_catalog), "notes": "Recovered from malformed JSON."}
                parse_repaired = False
            fields = parsed.get("fields") or {}
            if not isinstance(fields, dict):
                fields = {}
            valid_ids = {str(f.get("id")) for f in field_catalog if f.get("id")}
            cleaned = {}
            catalog_by_id = {str(f.get("id")): f for f in field_catalog if f.get("id")}
            for fid, value in fields.items():
                fid = str(fid)
                if fid not in valid_ids or value is None:
                    continue
                text_value = str(value).strip()
                if not text_value:
                    continue
                field = catalog_by_id.get(fid, {})
                options = [str(o).strip() for o in (field.get("options") or []) if str(o).strip()]
                if options and not field.get("isCustomText"):
                    lower_map = {o.lower(): o for o in options}
                    if text_value.lower() in lower_map:
                        text_value = lower_map[text_value.lower()]
                    elif "custom" in lower_map:
                        # For select fields with custom available, set the select to custom and use paired custom field when known.
                        text_value = lower_map["custom"]
                    else:
                        # Keep only values that can actually be selected.
                        continue
                cleaned[fid] = text_value
            card_mode = str(parsed.get("cardMode") or preset.get("cardMode") or "").strip()
            if card_mode not in {"single", "multi"}:
                card_mode = ""
            multi_count = str(parsed.get("multiCharacterCount") or preset.get("multiCharacterCount") or "").strip()
            notes = str(parsed.get("notes") or "").strip()
            self._log_event("ai_builder_randomize_preset_response", {"groupFocus": group_focus, "fields": cleaned, "field_count": len(cleaned), "cardMode": card_mode, "multiCharacterCount": multi_count, "notes": notes, "json_parse_ok": parse_repaired})
            return {"ok": True, "fields": cleaned, "cardMode": card_mode, "multiCharacterCount": multi_count, "notes": notes, "raw": raw, "jsonParseOk": parse_repaired}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._log_event("ai_builder_randomize_preset_error", {"status": e.code, "body": body[:1000]})
            return {"ok": False, "error": f"AI preset HTTP {e.code}: {body[:500]}"}
        except Exception as e:
            self._log_event("ai_builder_randomize_preset_error", {"error": str(e)})
            return {"ok": False, "error": f"AI preset generation failed: {e}"}

    def ai_transfer_to_builders(self, main_concept, character_description, field_catalog, settings=None):
        """Use the full text model to convert Main Concept + Character Description into builder fields."""
        try:
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            validation = self._validate_text_api_settings(merged)
            if not validation.get("ok"):
                return {"ok": False, "error": validation.get("error") or "AI settings are incomplete."}
            field_catalog = field_catalog or []
            compact_fields = []
            valid = {}
            for f in field_catalog[:80]:
                fid = str(f.get("id") or "").strip()
                if not fid:
                    continue
                opts = [str(o).strip() for o in (f.get("options") or []) if str(o).strip()]
                item = {
                    "id": fid,
                    "group": str(f.get("group") or "").strip()[:24],
                    "label": str(f.get("label") or fid).strip()[:48],
                    "kind": str(f.get("kind") or "text").strip(),
                }
                if opts:
                    item["options"] = opts[:18]
                compact_fields.append(item)
                valid[fid] = item
            concept = str(main_concept or "").strip()[:12000]
            visual = str(character_description or "").strip()[:8000]
            prompt = "\n".join([
                "Convert the supplied character concept into Character Card Forge builder fields.",
                "Use the full concept and character description, but output ONLY builder field choices as JSON.",
                "Do not write the final character card. Do not include markdown.",
                "Fill Character Builder, Personality Builder, and Scene Builder fields where the concept implies them.",
                "Detect whether this is a true multi-main-character card. Only characters meant to be portrayed directly by {{char}} as main playable/chat characters should become builder characters.",
                "Side characters, exes, rivals, family, bosses, bulls, friends, or lore-only people should NOT become builder characters. Summarize them in sideCharacterNotes so they can become lorebook/context instead.",
                "If there are 2+ main characters, return cardMode=multi and put each main character in characters[]. Each character gets its own fields object using the same field ids.",
                "If the main characters come from different settings/scenes, keep those as per-character Scene Builder fields and add notes that they must be reconciled into one shared opening scenario during generation.",
                "Side characters and lore-only settings should not become builder characters; place those in sideCharacterNotes.",
                "If there is only one main character, use top-level fields and cardMode=single unless the source explicitly says multi-character single card.",
                "If a field is a dropdown/select, choose exactly one listed option unless custom is clearly better and the field has a Custom option.",
                "For text fields, write short direct values suitable for a form field.",
                "Do not invent wildly unrelated facts; infer sensible details only when helpful.",
                "Return strict JSON with this shape: {\"fields\": {\"fieldId\": \"value\"}, \"characters\": [{\"name\": \"\", \"role\": \"main\", \"fields\": {\"fieldId\": \"value\"}}], \"cardMode\": \"single|multi\", \"multiCharacterCount\": \"\", \"sideCharacterNotes\": \"\", \"notes\": \"\"}.",
                "Builder fields filled by this response will take priority over Main Concept / Character Description during generation.",
                "AVAILABLE BUILDER FIELDS JSON:",
                json.dumps(compact_fields, ensure_ascii=False, separators=(",", ":")),
                "MAIN CONCEPT:",
                concept or "(empty)",
                "CHARACTER DESCRIPTION / VISION DESCRIPTION:",
                visual or "(empty)",
            ])
            self._log_event("ai_transfer_to_builders_request", {"model": merged.get("model"), "field_count": len(compact_fields), "prompt_chars": len(prompt)})
            raw = self._chat(prompt, merged)
            parse_ok = True
            try:
                parsed = self._loads_model_json(raw)
            except Exception as parse_error:
                parse_ok = False
                self._log_event("ai_transfer_to_builders_parse_error", {"error": str(parse_error), "raw": raw[:1500]})
                parsed = {"fields": self._fallback_randomize_fields_from_text(raw, field_catalog)}
            def clean_field_map(raw_map):
                if not isinstance(raw_map, dict):
                    return {}
                cleaned_map = {}
                for fid, val in raw_map.items():
                    fid = str(fid or "").strip()
                    if fid not in valid:
                        continue
                    text_value = str(val or "").strip()
                    if not text_value:
                        continue
                    meta = valid[fid]
                    opts = [str(o).strip() for o in meta.get("options", []) if str(o).strip()]
                    if opts:
                        lower_map = {o.lower(): o for o in opts}
                        lower_val = text_value.lower()
                        if lower_val in lower_map:
                            text_value = lower_map[lower_val]
                        elif "custom" in lower_map or "custom…" in lower_map:
                            pass
                        else:
                            matched = ""
                            for opt in opts:
                                if opt.lower() in lower_val or lower_val in opt.lower():
                                    matched = opt
                                    break
                            if matched:
                                text_value = matched
                            else:
                                continue
                    cleaned_map[fid] = text_value[:500]
                return cleaned_map

            raw_fields = parsed.get("fields") if isinstance(parsed, dict) else {}
            cleaned = clean_field_map(raw_fields)
            characters = []
            raw_chars = parsed.get("characters") if isinstance(parsed, dict) else []
            if isinstance(raw_chars, list):
                for idx, ch in enumerate(raw_chars[:12]):
                    if not isinstance(ch, dict):
                        continue
                    role = str(ch.get("role") or ch.get("type") or "main").strip().lower()
                    if role and role not in {"main", "primary", "playable", "char"}:
                        continue
                    fields = clean_field_map(ch.get("fields") or {})
                    name = str(ch.get("name") or ch.get("character") or "").strip()[:80]
                    if name:
                        fields["multiCharacterName"] = name
                    if fields:
                        characters.append({"name": name or f"Character {idx + 1}", "fields": fields})
            card_mode = str(parsed.get("cardMode") or "").strip() if isinstance(parsed, dict) else ""
            if card_mode not in {"single", "multi"}:
                card_mode = ""
            if len(characters) >= 2:
                card_mode = "multi"
            elif len(characters) == 1 and not cleaned:
                cleaned = characters[0].get("fields") or {}
                card_mode = card_mode or "single"
                characters = []
            multi_count = str(parsed.get("multiCharacterCount") or "").strip() if isinstance(parsed, dict) else ""
            if len(characters) >= 2:
                multi_count = str(len(characters))
            notes = str(parsed.get("notes") or "").strip() if isinstance(parsed, dict) else ""
            side_notes = str(parsed.get("sideCharacterNotes") or "").strip() if isinstance(parsed, dict) else ""
            self._log_event("ai_transfer_to_builders_response", {"field_count": len(cleaned), "character_count": len(characters), "cardMode": card_mode, "multiCharacterCount": multi_count, "side_notes_chars": len(side_notes), "notes": notes, "json_parse_ok": parse_ok})
            return {"ok": True, "fields": cleaned, "characters": characters, "cardMode": card_mode, "multiCharacterCount": multi_count, "sideCharacterNotes": side_notes, "notes": notes, "raw": raw, "jsonParseOk": parse_ok}
        except Exception as e:
            self._log_event("ai_transfer_to_builders_error", {"error": str(e)})
            return {"ok": False, "error": f"Transfer to Builders failed: {e}"}

    def save_settings(self, settings):
        self.settings = self._normalise_settings({**self.settings, **(settings or {})})
        self._save_json(SETTINGS_FILE, self.settings)
        return {"ok": True, "settings": self.settings}

    def save_template(self, template):
        if not isinstance(template, dict) or "sections" not in template:
            return {"ok": False, "error": "Invalid template."}
        self.template = self._normalise_template(template)
        self._save_json(TEMPLATE_FILE, self.template)
        active = self.settings.get("activeTemplateName", "Default")
        if str(active).casefold() != "default":
            self._save_named_template(active, self.template)
        return {"ok": True}

    def reset_template(self):
        self.template = json.loads(json.dumps(DEFAULT_TEMPLATE))
        self.settings["activeTemplateName"] = "Default"
        self._save_json(TEMPLATE_FILE, self.template)
        self._save_json(SETTINGS_FILE, self.settings)
        return {"ok": True, "template": self.template, "templates": self._list_prompt_templates(), "activeTemplateName": "Default"}

    def list_prompt_templates(self):
        return {"ok": True, "templates": self._list_prompt_templates(), "activeTemplateName": self.settings.get("activeTemplateName", "Default")}

    def save_template_as(self, name, template):
        name = str(name or "").strip()
        if not name:
            return {"ok": False, "error": "Enter a template name first."}
        if name.casefold() == "default":
            return {"ok": False, "error": "Default is built in. Choose another name."}
        if not isinstance(template, dict) or "sections" not in template:
            return {"ok": False, "error": "Invalid template."}
        self.template = self._normalise_template(template)
        self.settings["activeTemplateName"] = name
        self._save_json(TEMPLATE_FILE, self.template)
        self._save_json(SETTINGS_FILE, self.settings)
        path = self._save_named_template(name, template)
        return {"ok": True, "template": self.template, "templates": self._list_prompt_templates(), "activeTemplateName": name, "path": str(path)}

    def load_prompt_template(self, name):
        name = str(name or "Default").strip() or "Default"
        if name.casefold() == "default":
            self.template = json.loads(json.dumps(DEFAULT_TEMPLATE))
            name = "Default"
        else:
            path = self._template_file_for_name(name)
            if not path.exists():
                return {"ok": False, "error": f"Template not found: {name}"}
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.template = payload.get("template", payload)
            except Exception as e:
                return {"ok": False, "error": f"Could not load template: {e}"}
            self.template = self._normalise_template(self.template)
            if not isinstance(self.template, dict) or "sections" not in self.template:
                return {"ok": False, "error": "Template file is invalid."}
        self.settings["activeTemplateName"] = name
        self._save_json(TEMPLATE_FILE, self.template)
        self._save_json(SETTINGS_FILE, self.settings)
        return {"ok": True, "template": self.template, "templates": self._list_prompt_templates(), "activeTemplateName": name}

    def delete_prompt_template(self, name):
        name = str(name or "").strip()
        if not name or name.casefold() == "default":
            return {"ok": False, "error": "Default template cannot be deleted."}
        path = self._template_file_for_name(name)
        if path.exists():
            path.unlink()
        if str(self.settings.get("activeTemplateName", "Default")).casefold() == name.casefold():
            self.template = json.loads(json.dumps(DEFAULT_TEMPLATE))
            self.settings["activeTemplateName"] = "Default"
            self._save_json(TEMPLATE_FILE, self.template)
            self._save_json(SETTINGS_FILE, self.settings)
        return {"ok": True, "template": self.template, "templates": self._list_prompt_templates(), "activeTemplateName": self.settings.get("activeTemplateName", "Default")}

    def _estimate_tokens(self, text):
        """Fast, offline approximation for preflight checks.

        Most roleplay/card prompts are English-heavy, where chars / 4 is a
        practical conservative estimate. Add a small fixed overhead for chat
        message wrappers so the warning triggers before the API rejects it.
        """
        if not text:
            return 0
        return max(1, int(len(text) / 4) + 128)

    def _context_check(self, prompt, settings, mode_label="Full Prompt"):
        estimated = self._estimate_tokens(prompt)
        limit = int(settings.get("maxInputTokens") or DEFAULT_SETTINGS["maxInputTokens"])
        if estimated > limit:
            return {
                "ok": False,
                "error": (
                    f"{mode_label} stopped before sending: estimated input is {estimated:,} tokens, "
                    f"but Max Input Tokens is {limit:,}. Switch to Lite Mode, raise Max Input Tokens "
                    "if your model really supports it, or shorten the concept/template."
                ),
                "estimatedInputTokens": estimated,
                "maxInputTokens": limit,
            }
        return {"ok": True, "estimatedInputTokens": estimated, "maxInputTokens": limit}

    def build_prompt(self, concept, template=None, settings=None, chunk=None):
        template = template or self.template
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        alt_count = int(settings.get("alternateFirstMessages") or 0)
        alt_section_enabled = any(
            sec.get("id") == "alternate_first_messages" and sec.get("enabled", True)
            for sec in template.get("sections", [])
        )
        style_key = settings.get("firstMessageStyle", "cinematic")
        style_text = FIRST_MESSAGE_STYLES.get(style_key, FIRST_MESSAGE_STYLES["cinematic"])
        alt_styles = settings.get("alternateFirstMessageStyles", []) or []
        lines = []
        lines.append("You are a fictional character generator and formatter.")
        lines.append("Follow the user-configured template exactly. Do not invent disabled sections.")
        lines.append("All primary characters and romantic/sexual participants must be 18+.")
        lines.append("If a source concept conflicts with the age rule, age characters up and adjust the setting.")
        if settings.get("cardMode") == "multi":
            count = int(settings.get("multiCharacterCount") or 2)
            lines.append("CARD MODE: MULTI-CHARACTER SINGLE CARD.")
            lines.append(f"Create one importable character card that contains approximately {count} primary characters in the same card.")
            lines.append("Do NOT create separate cards and do NOT assume multi-chat. The exported card must work as one {{char}} that can portray every listed character in a normal single-character frontend chat.")
            lines.append("The Name section should be a group/scenario title or combined character names, not only one person's name.")
            lines.append("For Description, Personality, Sexual Traits, Background, and any custom character-detail sections, use clear subsections for each character, such as: Character 1 — Name, Character 2 — Name.")
            lines.append("Each primary character needs their own visible age, appearance/body/outfit details, personality, motivations, relationship toward {{user}}, speech style, and role in the scenario.")
            lines.append("Include group dynamics: how the characters interact with each other, how they divide attention, conflict, jealousy, teamwork, secrets, and how they speak in scenes.")
            lines.append("Scenario and First Message must be written so the assistant can naturally play all characters in one conversation. Use character names before speech/actions when more than one character is active.")
            scene_policy = settings.get("sharedScenePolicy", "ai_reconcile")
            if scene_policy == "shared_opening":
                lines.append("MULTI-CHARACTER SETTING LOGIC: Treat each character's builder Scene details as their personal starting context/backstory, but create ONE shared opening Scenario where all primary characters can plausibly interact. If their original settings differ, reconcile them through a meeting point, shared event, visit, transfer, online arrangement, party, school/work overlap, or other natural convergence. Do not make separate incompatible scenarios.")
            elif scene_policy == "character_backgrounds":
                lines.append("MULTI-CHARACTER SETTING LOGIC: Preserve each character's different setting as background/lore, but the Scenario and First Message must choose one current shared location/time. Explain briefly why the characters are together now. Do not split the card into parallel scenes.")
            elif scene_policy == "user_defined":
                lines.append("MULTI-CHARACTER SETTING LOGIC: Use any explicit shared scenario notes from Main Concept / Scene Builder as the authority. If character scene details conflict, keep them only as background unless they fit the shared scenario.")
            else:
                lines.append("MULTI-CHARACTER SETTING LOGIC: If multiple primary characters have different settings or opening situations, automatically reconcile them into one coherent shared card scenario. Prefer a single current scene, with individual settings preserved as personal background. Resolve conflicts instead of copying incompatible separate scenes.")
            lines.append("Example Dialogues should demonstrate multi-character replies in one {{char}} response, with character names clearly attributed.")
            lines.append("Tags should include multi-character unless the Tags section is disabled.")
        else:
            lines.append("CARD MODE: SINGLE CHARACTER CARD.")
        lines.append(f"Token budget settings: maximum input context is {settings.get('maxInputTokens')} tokens; maximum generated output is {settings.get('maxOutputTokens')} tokens.")
        lines.append("Use the available input budget efficiently. Do not exceed the requested output structure.")
        lines.append(f"FIRST MESSAGE STYLE REQUIREMENT: use this style for the main First Message: {style_text}")
        if alt_count > 0:
            for idx in range(alt_count):
                alt_key = alt_styles[idx] if idx < len(alt_styles) else ""
                alt_text = FIRST_MESSAGE_STYLES.get(alt_key, style_text)
                lines.append(f"ALTERNATIVE FIRST MESSAGE {idx + 1} STYLE: {alt_text}")
        if alt_count > 0 and alt_section_enabled:
            lines.append(f"ALTERNATIVE FIRST MESSAGE REQUIREMENT: generate exactly {alt_count} additional/alternative first messages in their own clearly labelled section. Do not skip them.")
        elif alt_count > 0 and not alt_section_enabled:
            lines.append("ALTERNATIVE FIRST MESSAGE REQUIREMENT: the Alternative First Messages section is disabled, so do not generate alternatives.")
        else:
            lines.append("ALTERNATIVE FIRST MESSAGE REQUIREMENT: do not generate alternative first messages unless the template explicitly asks for them.")
        lines.append("")
        lines.append("GLOBAL RULES")
        for rule in template.get("globalRules", []):
            if str(rule).strip():
                lines.append(f"- {rule}")
        lines.append("")
        if chunk:
            lines.append(f"LITE MODE PASS: {chunk}")
            lines.append("Generate only the sections requested by this pass, but preserve consistency with the concept and any prior context supplied.")
            lines.append("")
        lines.append("OUTPUT TEMPLATE")
        for section in template.get("sections", []):
            if not section.get("enabled", True):
                continue
            title = section.get("title", "Untitled Section")
            if chunk and not self._section_in_chunk(section.get("id", ""), chunk):
                continue
            lines.append("------------------------------------------------")
            lines.append(title)
            desc = section.get("description", "")
            if desc:
                lines.append(desc)
            if section.get("id") == "first_message":
                lines.append(f"First message style: {style_text}")
            if section.get("id") == "example_dialogues":
                lines.append("IMPORTANT: Use exactly ONE <START> marker total, placed at the very beginning of this section.")
                lines.append("After that single <START>, write one continuous example conversation with each speaker on a separate line, such as {{user}}: ... and {{char}}: ...")
                lines.append("Do not start each exchange with another <START>; multiple <START> markers break Front Porch AI import formatting.")
            if section.get("id") == "alternate_first_messages":
                if alt_count > 0:
                    lines.append(f"Generate exactly {alt_count} alternative first messages in addition to the main First Message.")
                    lines.append("Inside this section, label each item exactly as: Alternative First Message 1, Alternative First Message 2, etc.")
                    for idx in range(alt_count):
                        alt_key = alt_styles[idx] if idx < len(alt_styles) else ""
                        alt_text = FIRST_MESSAGE_STYLES.get(alt_key, style_text)
                        lines.append(f"Alternative First Message {idx + 1} style/tone: {alt_text}")
                    lines.append("Each alternative must be a complete opening message, not a short summary.")
                    lines.append("Do not repeat the main First Message inside this section, and do not put alternatives inside the main First Message section.")
                else:
                    lines.append("No alternative first messages requested. Leave this section blank or write: None.")
                lines.append(f"Alternative style: {style_text}")
            fields = [f for f in section.get("fields", []) if f.get("enabled", True)]
            for field in fields:
                label = field.get("label", "Field")
                hint = field.get("hint", "")
                lines.append(f"- {label}:" + (f" {hint}" if hint else ""))
            lines.append("")
        lines.append("------------------------------------------------")
        lines.append("CHARACTER CONCEPT")
        lines.append(concept.strip())
        return "\n".join(lines).strip()

    def _section_in_chunk(self, section_id, chunk):
        mapping = {
            "core": {"name", "description", "personality", "sexual_traits", "background"},
            "scene": {"scenario", "first_message", "alternate_first_messages", "example_dialogues"},
            "extras": {"lorebook", "tags", "system_prompt", "state_tracking", "stable_diffusion"},
        }
        return section_id in mapping.get(chunk, set())

    def _template_section_category(self, section):
        category = (section.get("category") or "").strip().lower()
        if category in {"description", "personality"}:
            return category
        sid = section.get("id", "")
        if sid == "description":
            return "description"
        if sid in {"personality", "sexual_traits", "background"}:
            return "personality"
        fixed = {"name", "scenario", "first_message", "alternate_first_messages", "example_dialogues", "lorebook", "tags", "system_prompt", "state_tracking", "stable_diffusion"}
        if sid in fixed:
            return "fixed"
        # Old custom sections created before tab categories existed were almost
        # always meant as character-detail/personality sections. Keep them visible
        # in the Personality tab and export them into data.personality.
        return "personality"

    def _api_key_required_for_base(self, base):
        base = (base or "").strip().lower()
        if not base:
            return False
        local_markers = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal")
        return not any(marker in base for marker in local_markers)

    def _validate_text_api_settings(self, settings):
        base = (settings.get("apiBaseUrl") or "").strip()
        model = (settings.get("model") or "").strip()
        key = (settings.get("apiKey") or "").strip()
        missing = []
        if not base:
            missing.append("API Base URL")
        if not model:
            missing.append("Text Model")
        if self._api_key_required_for_base(base) and not key:
            missing.append("API Key")
        if missing:
            return {
                "ok": False,
                "error": "AI settings are incomplete: " + ", ".join(missing) + ". Open AI Settings and re-enter your endpoint/model/key before generating or revising.",
                "missingSettings": missing,
            }
        return {"ok": True}

    def _validate_vision_api_settings(self, settings):
        base = (settings.get("visionApiBaseUrl") or settings.get("apiBaseUrl") or "").strip()
        model = (settings.get("visionModel") or "").strip()
        key = (settings.get("visionApiKey") or settings.get("apiKey") or "").strip()
        missing = []
        if not base:
            missing.append("Vision API Base URL or Text API Base URL")
        if not model:
            missing.append("Vision Model")
        if self._api_key_required_for_base(base) and not key:
            missing.append("Vision API Key or Text API Key")
        if missing:
            return {
                "ok": False,
                "error": "Vision settings are incomplete: " + ", ".join(missing) + ". Open AI Settings and re-enter your vision model/key before analyzing an image.",
                "missingSettings": missing,
            }
        return {"ok": True}

    def _looks_like_text_refusal(self, text):
        sample = (text or "").strip()
        if not sample:
            return False
        lowered = sample.lower()
        compact = re.sub(r"\s+", " ", lowered[:1800]).strip()
        starts = (
            "i can't", "i can’t", "i cannot", "i won't", "i won’t", "i am unable", "i'm unable",
            "sorry, but i can't", "sorry, i can't", "i’m sorry", "i'm sorry", "i apologize",
            "as an ai", "i can not", "cannot comply", "can't comply", "can’t comply",
        )
        refusal_phrases = (
            "i can't help", "i can’t help", "i cannot help", "i can't provide", "i can’t provide",
            "i cannot provide", "i can't create", "i can’t create", "i cannot create",
            "i can't assist", "i can’t assist", "i cannot assist", "i'm not able to", "i am not able to",
            "i must refuse", "i have to refuse", "against policy", "safety guidelines", "not appropriate to generate",
            "not able to comply", "unable to comply", "i can't continue", "i can’t continue",
        )
        if compact.startswith(starts):
            return True
        if len(sample) < 1800 and any(phrase in compact for phrase in refusal_phrases):
            return True
        if "as an ai" in compact and any(x in compact for x in ("can't", "can’t", "cannot", "unable", "won't", "won’t")):
            return True
        return False

    def _reset_backup_info(self):
        self._last_backup_info = None

    def _note_backup_info(self, phase, primary_model, backup_model, backup_mode="same", lite=False):
        self._last_backup_info = {
            "used": True,
            "phase": phase,
            "primaryModel": primary_model,
            "backupModel": backup_model,
            "backupMode": backup_mode or "same",
            "lite": bool(lite),
        }

    def _get_backup_info(self):
        return self._last_backup_info or {"used": False}

    def _chat_once(self, prompt, settings, model, attempt_label="primary"):
        self._raise_if_cancelled()
        base = (settings.get("apiBaseUrl") or "").rstrip("/")
        key = settings.get("apiKey") or ""
        url = base + "/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You create structured fictional character cards and obey the requested output template exactly."},
                {"role": "user", "content": prompt}
            ],
            "temperature": float(settings.get("temperature", 0.75)),
            "max_tokens": int(settings.get("maxOutputTokens", DEFAULT_SETTINGS["maxOutputTokens"])),
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        self._log_event("text_generation_request", {"attempt": attempt_label, "model": model})
        try:
            with self._urlopen_with_retries(req, settings, timeout=180, label="Text generation") as resp:
                self._raise_if_cancelled()
                data = json.loads(resp.read().decode("utf-8"))
                self._raise_if_cancelled()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body[:1000]}")
        except Exception as e:
            raise RuntimeError(str(e))
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except Exception:
            content = json.dumps(data, indent=2, ensure_ascii=False)
        self._log_event("text_generation_response", {"attempt": attempt_label, "model": model, "looks_like_refusal": self._looks_like_text_refusal(content), "preview": content[:800]})
        return content

    def _chat(self, prompt, settings, signal_lite_backup=False):
        self._raise_if_cancelled()
        model = (settings.get("model") or "").strip()
        validation = self._validate_text_api_settings(settings)
        if not validation.get("ok"):
            raise ValueError(validation.get("error") or "AI settings are incomplete.")
        primary = self._chat_once(prompt, settings, model, "primary")
        backup = (settings.get("backupTextModel") or "").strip()
        backup_mode = (settings.get("backupTextMode") or "same").strip().lower()
        if self._looks_like_text_refusal(primary) and backup and backup != model:
            if backup_mode == "lite" and signal_lite_backup:
                self._log_event("text_generation_refusal_lite_fallback_needed", {"primary_model": model, "backup_model": backup, "primary_preview": primary[:1200]})
                raise TextRefusalForLiteFallback(primary)
            self._log_event("text_generation_refusal_fallback", {"primary_model": model, "backup_model": backup, "backup_mode": backup_mode, "primary_preview": primary[:1200]})
            self._note_backup_info("text_generation", model, backup, backup_mode, lite=False)
            return self._chat_once(prompt, settings, backup, "backup_after_refusal")
        return primary

    def _generate_lite_output(self, generation_concept, template, settings, model_override=None, label_prefix="lite"):
        parts = []
        prior = ""
        for chunk in ["core", "scene", "extras"]:
            self._raise_if_cancelled()
            chunk_prompt = self.build_prompt(generation_concept + ("\n\nPRIOR GENERATED CONTEXT:\n" + prior if prior else ""), template, settings, chunk=chunk)
            check = self._context_check(chunk_prompt, settings, mode_label=f"Lite Mode {chunk} pass")
            if not check["ok"]:
                raise RuntimeError(check.get("error", f"Lite Mode {chunk} pass exceeds context window."))
            if model_override:
                text = self._chat_once(chunk_prompt, settings, model_override, f"{label_prefix}_{chunk}")
            else:
                text = self._chat(chunk_prompt, settings)
            self._raise_if_cancelled()
            parts.append(text)
            prior += "\n\n" + text
        return "\n\n".join(parts).strip()

    def build_compact_prompt(self, concept, template=None, settings=None, chunk="core"):
        template = template or self.template
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        alt_count = int(settings.get("alternateFirstMessages") or 0)
        style_text = FIRST_MESSAGE_STYLES.get(settings.get("firstMessageStyle", "cinematic"), FIRST_MESSAGE_STYLES["cinematic"])
        chunk_sections = {
            "core": "Name, Description, Personality, Sexual Traits, Background",
            "scene": "Scenario, First Message, Alternative First Messages, Example Dialogues",
            "extras": "Lorebook Entries, Tags, Custom System Prompt, State Tracking, Stable Diffusion Prompt",
        }
        lines = [
            "Compact Lite generation for an 8k-context model. Return only the requested card sections.",
            "Use separator line ------------------------------------------------ before every section.",
            "All characters and sexual/romantic participants are 18+ fictional adults.",
            "Card mode: " + ("MULTI-CHARACTER SINGLE CARD" if settings.get("cardMode") == "multi" else "SINGLE CHARACTER CARD"),
            "Requested sections this pass: " + chunk_sections.get(chunk, chunk_sections["core"]),
            "First Message style: " + style_text,
            f"Alternative First Messages requested: {alt_count}",
            "Keep concise but complete. Do not add unrelated commentary.",
            "CONCEPT:",
            (concept or "").strip(),
        ]
        return "\n".join(lines).strip()

    def _generate_compact_lite_output(self, generation_concept, template, settings, model_override=None, label_prefix="compact_lite"):
        parts = []
        prior_brief = ""
        for chunk in ["core", "scene", "extras"]:
            self._raise_if_cancelled()
            source = generation_concept
            if prior_brief and chunk != "core":
                source = source + "\n\nBRIEF PRIOR CONTEXT FROM EARLIER PASSES:\n" + prior_brief[:2500]
            chunk_prompt = self.build_compact_prompt(source, template, settings, chunk=chunk)
            check = self._context_check(chunk_prompt, settings, mode_label=f"Compact Lite {chunk} pass")
            if not check["ok"]:
                raise RuntimeError(check.get("error", f"Compact Lite {chunk} pass exceeds context window."))
            if model_override:
                text = self._chat_once(chunk_prompt, settings, model_override, f"{label_prefix}_{chunk}")
            else:
                text = self._chat(chunk_prompt, settings)
            self._raise_if_cancelled()
            parts.append(text)
            prior_brief += "\n\n" + text[:2500]
        return "\n\n".join(parts).strip()

    def _generate_full_or_lite_output(self, generation_concept, template, settings):
        if settings.get("mode") == "compact_lite":
            return self._generate_compact_lite_output(generation_concept, template, settings)
        if settings.get("mode") == "lite":
            return self._generate_lite_output(generation_concept, template, settings)
        prompt = self.build_prompt(generation_concept, template, settings)
        check = self._context_check(prompt, settings, mode_label="Full Prompt")
        if not check["ok"]:
            raise RuntimeError(check.get("error", "Full Prompt exceeds context window."))
        try:
            return self._chat(prompt, settings, signal_lite_backup=True)
        except TextRefusalForLiteFallback:
            backup = (settings.get("backupTextModel") or "").strip()
            if not backup:
                raise
            self._log_event("text_generation_backup_lite_start", {"backup_model": backup, "main_mode": settings.get("mode"), "backup_mode": settings.get("backupTextMode")})
            self._note_backup_info("text_generation", settings.get("model"), backup, settings.get("backupTextMode"), lite=True)
            if settings.get("mode") == "compact_lite":
                return self._generate_compact_lite_output(generation_concept, template, settings, model_override=backup, label_prefix="backup_compact_lite_after_refusal")
            return self._generate_lite_output(generation_concept, template, settings, model_override=backup, label_prefix="backup_lite_after_refusal")

    def _norm_heading_key(self, value):
        value = (value or "").strip()
        value = re.sub(r"^#{1,6}\s*", "", value)
        value = value.strip(" *`_")
        value = re.sub(r"\s*[:：]\s*$", "", value).strip()
        return re.sub(r"\s+", " ", value).lower().strip("- ")

    def _canonical_heading_with_template(self, line, template=None):
        canonical = self._canonical_heading(line)
        if canonical:
            return canonical
        raw_key = self._norm_heading_key(line)
        if not raw_key or re.fullmatch(r"[-—_]{3,}", raw_key):
            return None
        for section in (template or {}).get("sections", []) if template else []:
            if not section.get("enabled", True):
                continue
            title = section.get("title", "")
            sid = section.get("id", "")
            if title and raw_key == self._norm_heading_key(title):
                return sid
        return None

    def _field_present(self, section_text, label):
        if not section_text or not label:
            return False
        label_re = re.escape(label.strip())
        return bool(re.search(rf"(?im)^\s*(?:[-*]\s*)?{label_re}\s*[:：]", section_text))

    def _enabled_section_ids(self, template):
        return [s.get("id", "") for s in (template or {}).get("sections", []) if s.get("enabled", True)]

    def validate_output_against_template(self, output, template=None, settings=None):
        """Check generated text for missing enabled sections/fields.

        This is intentionally lightweight and offline. It does not judge quality;
        it only catches structural gaps before the user exports/imports the card.
        """
        template = template or self.template
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        sections = self._parse_sections(output or "", template)
        missing = []
        optional = {"lorebook", "system_prompt"}
        alt_count = int(settings.get("alternateFirstMessages") or 0)
        for section in template.get("sections", []):
            if not section.get("enabled", True):
                continue
            sid = section.get("id", "")
            title = section.get("title", sid or "Untitled Section")
            if sid in optional:
                continue
            if sid == "alternate_first_messages" and alt_count <= 0:
                continue
            body = sections.get(sid, "").strip()
            if sid == "alternate_first_messages":
                actual = len(self._extract_alternates(output or ""))
                if actual < alt_count:
                    missing.append({"section_id": sid, "section": title, "field": None, "reason": f"Expected {alt_count} alternatives but found {actual}."})
                continue
            if sid == "example_dialogues":
                start_count = len(re.findall(r"(?i)<START>", body))
                if start_count == 0:
                    missing.append({"section_id": sid, "section": title, "field": None, "reason": "No <START> example dialogue marker found. Use exactly one <START> at the beginning."})
                elif start_count > 1:
                    missing.append({"section_id": sid, "section": title, "field": None, "reason": f"Found {start_count} <START> markers. Front Porch AI expects exactly one <START> followed by one continuous conversation."})
                continue
            if sid == "tags":
                tags = [t.strip() for t in body.replace("\n", ",").split(",") if t.strip()]
                if not tags:
                    missing.append({"section_id": sid, "section": title, "field": None, "reason": "No tags found."})
                continue
            if not body:
                missing.append({"section_id": sid, "section": title, "field": None, "reason": "Section is blank or missing."})
                continue
            for field in section.get("fields", []) or []:
                if not field.get("enabled", True):
                    continue
                label = field.get("label", "").strip()
                if label and not self._field_present(body, label):
                    missing.append({"section_id": sid, "section": title, "field": label, "reason": "Field label missing."})
        return {"ok": len(missing) == 0, "missing": missing}

    def _repair_missing_output(self, output, concept, template, settings, missing):
        if not missing:
            return output, {"repaired": False, "missing": []}
        affected_section_ids = []
        section_titles = {}
        for section in (template or {}).get("sections", []):
            if section.get("enabled", True):
                section_titles[section.get("id", "")] = section.get("title", section.get("id", ""))
        for item in missing:
            sid = item.get("section_id")
            if sid and sid not in affected_section_ids:
                affected_section_ids.append(sid)

        missing_lines = []
        for item in missing:
            if item.get("field"):
                missing_lines.append(f"- Section `{item.get('section')}` / field `{item.get('field')}`: {item.get('reason')}")
            else:
                missing_lines.append(f"- Section `{item.get('section')}`: {item.get('reason')}")

        requested_sections = []
        for sid in affected_section_ids:
            requested_sections.append(f"- {section_titles.get(sid, sid)}")

        prompt = "\n".join([
            "The generated fictional character card is missing required template content.",
            "Return ONLY complete replacement content for the missing affected section(s).",
            "Use the exact top-level section heading(s) listed under SECTIONS TO RETURN.",
            "Do NOT return loose bullet points outside a section heading.",
            "Do NOT rewrite sections that are not listed under SECTIONS TO RETURN.",
            "Do NOT include commentary, explanations, markdown fences, or a full card.",
            "For a missing field, return the whole affected section including the existing useful content plus the missing field filled in.",
            "Keep all details consistent with the existing card and original concept.",
            ("Card mode is MULTI-CHARACTER SINGLE CARD. Preserve all primary characters inside one {{char}} card and keep per-character subsections." if (settings or {}).get("cardMode") == "multi" else "Card mode is SINGLE CHARACTER CARD."),
            "If adding Alternative First Messages, label each item exactly as Alternative First Message 1, Alternative First Message 2, etc.",
            "",
            "SECTIONS TO RETURN",
            "\n".join(requested_sections),
            "",
            "MISSING CONTENT",
            "\n".join(missing_lines),
            "",
            "ORIGINAL CHARACTER CONCEPT",
            (concept or "").strip() or "(No original concept supplied.)",
            "",
            "CURRENT GENERATED CARD",
            (output or "").strip(),
        ]).strip()
        self._log_event("repair_prompt", {"missing": missing, "affected_section_ids": affected_section_ids, "prompt": prompt})
        check = self._context_check(prompt, settings, mode_label="Missing-section repair")
        if not check.get("ok"):
            self._log_event("repair_skipped_context", check)
            return output, {"repaired": False, "missing": missing, "repair_error": check.get("error")}
        repair = self._chat(prompt, settings)
        self._log_event("repair_response", {"repairText": repair})
        merged = self._merge_repair_sections(output, repair, template=template, missing=missing)
        self._log_event("repair_merged", {"merged_tail": merged[-2000:]})
        return merged, {"repaired": True, "missing": missing, "repairText": repair}

    def _merge_repair_sections(self, output, repair, template=None, missing=None):
        """Merge a missing-only repair response into the original card safely.

        The old merge path appended unparseable repair text at the end of the
        card, which could shove content after Stable Diffusion Prompt. This
        version understands custom template headings and refuses to append loose
        repair text to the card tail.
        """
        output = (output or "").strip()
        repair = (repair or "").strip()
        if not repair:
            return output
        repair_sections = self._parse_sections(repair, template)
        original_sections = self._parse_sections(output, template)

        if not repair_sections:
            affected = []
            for item in missing or []:
                sid = item.get("section_id")
                if sid and sid not in affected:
                    affected.append(sid)
            if len(affected) == 1:
                repair_sections[affected[0]] = self._clean_section_text(repair)
                self._log_event("repair_unheaded_assigned", {"section_id": affected[0], "repairText": repair})
            else:
                self._log_event("repair_unparseable_not_merged", {"repairText": repair, "affected": affected})
                return output

        known_order = [s.get("id", "") for s in (template or {}).get("sections", []) if s.get("enabled", True)]
        if not known_order:
            known_order = ["name", "description", "personality", "sexual_traits", "background", "scenario", "first_message", "alternate_first_messages", "example_dialogues", "lorebook", "tags", "system_prompt", "state_tracking", "stable_diffusion"]
        default_titles = {
            "name": "Name", "description": "Description", "personality": "Personality", "sexual_traits": "Sexual Traits",
            "background": "Background", "scenario": "Scenario", "first_message": "First Message",
            "alternate_first_messages": "Alternative First Messages", "example_dialogues": "Example Dialogues",
            "lorebook": "Lorebook Entries", "tags": "Tags", "system_prompt": "Custom System Prompt",
            "state_tracking": "State Tracking", "stable_diffusion": "Stable Diffusion Prompt",
        }
        titles = dict(default_titles)
        for s in (template or {}).get("sections", []):
            if s.get("id") and s.get("title"):
                titles[s.get("id")] = s.get("title")

        # Replacement section strategy: a repair response for a section should be
        # the complete corrected body for that section, so replace rather than
        # blindly append. This prevents repair-only bullets from drifting into
        # the wrong card area.
        for sid, repair_body in repair_sections.items():
            repair_body = self._clean_section_text(repair_body)
            if repair_body:
                original_sections[sid] = repair_body

        blocks = []
        for sid in known_order:
            body = original_sections.get(sid, "").strip()
            if body:
                blocks.append("------------------------------------------------\n" + titles.get(sid, sid.replace("_", " ").title()) + "\n\n" + body)
        for sid, body in original_sections.items():
            if sid not in known_order and body.strip():
                blocks.append("------------------------------------------------\n" + titles.get(sid, sid.replace("_", " ").title()) + "\n\n" + body.strip())
        return "\n\n".join(blocks).strip()

    def _generate_template_qa(self, concept, template, settings):
        template = self._normalise_template(template or self.template)
        qa = template.get("qa", {}) or {}
        if not qa.get("enabled"):
            return ""
        questions = [str(q).strip() for q in qa.get("questions", []) if str(q).strip()]
        if not questions:
            return ""
        lines = [
            "Before writing the final character card, interview the fictional character(s) to uncover deeper internal logic.",
            "Answer as the character(s), not as an assistant.",
            "These answers are private planning notes for generation only. They must not be copied into the final character card unless naturally reflected in characterization.",
            "If this is a multi-character card, answer each question for the relevant primary characters or as a grouped dynamic when appropriate.",
            "Keep answers concise but specific, emotionally useful, and character-consistent.",
            "Do not add sections from the final character-card template. Return only Q&A pairs.",
            "",
            "CHARACTER CONCEPT",
            concept.strip(),
            "",
            "QUESTIONS",
        ]
        for idx, q in enumerate(questions, start=1):
            lines.append(f"{idx}. {q}")
        lines.extend([
            "",
            "OUTPUT FORMAT",
            "Q1: <question>",
            "A1: <answer in character voice or clearly attributed character answers>",
            "Q2: <question>",
            "A2: <answer>",
        ])
        prompt = "\n".join(lines).strip()
        check = self._context_check(prompt, settings, mode_label="Q&A pre-generation pass")
        if not check.get("ok"):
            raise RuntimeError(check.get("error", "Q&A pre-generation pass exceeds context window."))
        self._log_event("qa_generation_request", {"questions": questions, "prompt": prompt})
        answers = self._chat(prompt, settings)
        self._log_event("qa_generation_response", {"answers": answers})
        return answers.strip()

    def generate_qa_context(self, concept, template, settings):
        self._reset_cancel()
        if not concept or not concept.strip():
            return {"ok": False, "error": "Enter a character concept first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        template = self._normalise_template(template)
        self.save_template(template)
        settings_check = self._validate_text_api_settings(merged_settings)
        if not settings_check.get("ok"):
            return settings_check
        try:
            self._reset_backup_info()
            self._raise_if_cancelled()
            answers = self._generate_template_qa(concept, template, merged_settings)
            self._raise_if_cancelled()
            info = self._get_backup_info()
            if info.get("used"):
                info["phase"] = "qa_interview"
            return {"ok": True, "qaAnswers": answers, "backupInfo": info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def generate_with_qa_answers(self, concept, template, settings, qa_answers=""):
        self._reset_cancel()
        if not concept or not concept.strip():
            return {"ok": False, "error": "Enter a character concept first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        template = self._normalise_template(template)
        self.save_template(template)
        settings_check = self._validate_text_api_settings(merged_settings)
        if not settings_check.get("ok"):
            return settings_check
        try:
            self._raise_if_cancelled()
            generation_concept = concept
            qa_answers = (qa_answers or "").strip()
            if qa_answers:
                generation_concept = concept.rstrip() + "\n\nPRE-GENERATION CHARACTER Q&A NOTES (private planning context, do not reproduce as a section):\n" + qa_answers
            self._reset_backup_info()
            output = self._generate_full_or_lite_output(generation_concept, template, merged_settings)
            backup_info = self._get_backup_info()
            if backup_info.get("used"):
                backup_info["phase"] = "character_generation"
            self._raise_if_cancelled()
            validation = self.validate_output_against_template(output, template, merged_settings)
            self._log_event("generation_validation", {"validation": validation})
            repair_info = {"repaired": False, "missing": []}
            if not validation.get("ok"):
                self._raise_if_cancelled()
                output, repair_info = self._repair_missing_output(output, generation_concept, template, merged_settings, validation.get("missing", []))
                self._raise_if_cancelled()
                validation = self.validate_output_against_template(output, template, merged_settings)
                self._log_event("generation_validation_after_repair", {"validation": validation})
            return {"ok": True, "output": output, "validation": validation, "repair": repair_info, "qaAnswers": qa_answers, "backupInfo": backup_info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def generate(self, concept, template, settings):
        self._reset_cancel()
        if not concept or not concept.strip():
            return {"ok": False, "error": "Enter a character concept first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        template = self._normalise_template(template)
        self.save_template(template)
        settings_check = self._validate_text_api_settings(merged_settings)
        if not settings_check.get("ok"):
            return settings_check
        try:
            self._raise_if_cancelled()
            qa_answers = self._generate_template_qa(concept, template, merged_settings)
            self._raise_if_cancelled()
            generation_concept = concept
            if qa_answers:
                generation_concept = concept.rstrip() + "\n\nPRE-GENERATION CHARACTER Q&A NOTES (private planning context, do not reproduce as a section):\n" + qa_answers
            self._reset_backup_info()
            output = self._generate_full_or_lite_output(generation_concept, template, merged_settings)
            backup_info = self._get_backup_info()
            if backup_info.get("used"):
                backup_info["phase"] = "character_generation"
            self._raise_if_cancelled()
            validation = self.validate_output_against_template(output, template, merged_settings)
            self._log_event("generation_validation", {"validation": validation})
            repair_info = {"repaired": False, "missing": []}
            if not validation.get("ok"):
                self._raise_if_cancelled()
                output, repair_info = self._repair_missing_output(output, generation_concept, template, merged_settings, validation.get("missing", []))
                self._raise_if_cancelled()
                validation = self.validate_output_against_template(output, template, merged_settings)
                self._log_event("generation_validation_after_repair", {"validation": validation})
            return {"ok": True, "output": output, "validation": validation, "repair": repair_info, "qaAnswers": qa_answers, "backupInfo": backup_info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def revise_card(self, current_output, followup, concept, template, settings):
        self._reset_cancel()
        if not current_output or not current_output.strip():
            return {"ok": False, "error": "Generate or paste an output first."}
        if not followup or not followup.strip():
            return {"ok": False, "error": "Enter the change you want made."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        self.save_template(template)
        settings_check = self._validate_text_api_settings(merged_settings)
        if not settings_check.get("ok"):
            return settings_check
        enabled_sections = [s.get("title", "Untitled Section") for s in template.get("sections", []) if s.get("enabled", True)]
        style_key = merged_settings.get("firstMessageStyle", "cinematic")
        style_text = FIRST_MESSAGE_STYLES.get(style_key, FIRST_MESSAGE_STYLES["cinematic"])
        alt_styles = merged_settings.get("alternateFirstMessageStyles", []) or []
        alt_style_lines = []
        for idx in range(int(merged_settings.get("alternateFirstMessages") or 0)):
            alt_key = alt_styles[idx] if idx < len(alt_styles) else ""
            alt_style_lines.append(f"Alternative First Message {idx + 1} style/tone: {FIRST_MESSAGE_STYLES.get(alt_key, style_text)}")
        prompt = "\n".join([
            "Revise the existing fictional character card according to the user's follow-up request.",
            "Return the complete revised card, not a diff or commentary.",
            "Keep the same section order and do not add disabled sections.",
            ("Card mode: MULTI-CHARACTER SINGLE CARD. Preserve all primary characters inside one {{char}} card; do not split into multiple cards or multi-chat." if merged_settings.get("cardMode") == "multi" else "Card mode: SINGLE CHARACTER CARD."),
            "Preserve good content unless the follow-up request changes it.",
            f"Enabled section order: {', '.join(enabled_sections)}",
            f"First Message style currently selected: {style_text}",
            f"Alternative First Messages requested by settings: {int(merged_settings.get('alternateFirstMessages') or 0)}",
            "\n".join(alt_style_lines),
            "If the follow-up explicitly asks for a different number of additional/alternative greetings, obey that explicit request. Otherwise preserve the configured count.",
            "Keep Alternative First Messages in their own top-level section. Each one must be labelled exactly: Alternative First Message 1, Alternative First Message 2, etc.",
            "Do not place Alternative First Messages inside the main First Message section.",
            "",
            "ORIGINAL CHARACTER CONCEPT",
            concept.strip() if concept else "(No original concept supplied.)",
            "",
            "CURRENT GENERATED CARD",
            current_output.strip(),
            "",
            "USER FOLLOW-UP REQUEST",
            followup.strip(),
        ]).strip()
        try:
            if merged_settings.get("mode") == "full":
                check = self._context_check(prompt, merged_settings, mode_label="Full Prompt follow-up")
                if not check["ok"]:
                    return check
            elif merged_settings.get("mode") == "compact_lite":
                check = self._context_check(prompt, merged_settings, mode_label="Compact Lite follow-up")
                if not check["ok"]:
                    return check
            else:
                check = self._context_check(prompt, merged_settings, mode_label="Lite Mode follow-up")
                if not check["ok"]:
                    return check
            self._reset_backup_info()
            output = self._chat(prompt, merged_settings)
            info = self._get_backup_info()
            if info.get("used"):
                info["phase"] = "followup_revision"
            return {"ok": True, "output": output, "backupInfo": info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _safe_upload_name(self, filename, fallback="upload"):
        """Return a filesystem-safe name while preserving the original extension.

        This matters for files such as Japanese PDFs. The old sanitizer could turn
        注意書き.pdf into just "pdf", which made the app think the file had no
        .pdf extension when dragged in through the browser upload path.
        """
        raw_name = Path(str(filename or fallback)).name
        fallback_path = Path(str(fallback or "upload"))
        original = Path(raw_name)
        suffix = original.suffix.lower() or fallback_path.suffix.lower()
        raw_stem = original.stem if original.suffix else original.name
        safe_stem = re.sub(r"[^a-zA-Z0-9._ -]+", "_", raw_stem).strip(" ._")
        if not safe_stem:
            fallback_stem = fallback_path.stem if fallback_path.suffix else fallback_path.name
            safe_stem = re.sub(r"[^a-zA-Z0-9._ -]+", "_", fallback_stem).strip(" ._") or "upload"
        return safe_stem + suffix

    def _decode_data_payload(self, data):
        if data is None:
            return b""
        if isinstance(data, str):
            value = data.strip()
            if "," in value and value.lower().startswith("data:"):
                value = value.split(",", 1)[1]
            return base64.b64decode(value)
        return bytes(data)

    def _data_url_mime(self, data):
        if isinstance(data, str):
            value = data.strip()
            if value.lower().startswith("data:") and ";" in value:
                return value[5:value.find(";")].strip().lower()
        return ""

    def _extension_from_mime(self, mime, kind="attachment"):
        mime = (mime or "").lower().split(";", 1)[0].strip()
        mapping = {
            "application/pdf": ".pdf",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/vtt": ".vtt",
            "application/json": ".json",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
        }
        if mime in mapping:
            return mapping[mime]
        if kind == "image" and mime.startswith("image/"):
            ext = "." + mime.split("/", 1)[1].replace("jpeg", "jpg")
            return ext if ext in {".png", ".jpg", ".jpeg", ".webp"} else ""
        return ""

    def _safe_name_with_extension(self, filename, fallback, data_url=None, kind="attachment"):
        explicit_suffix = Path(str(filename or "")).suffix.lower()
        inferred_suffix = explicit_suffix or self._extension_from_mime(self._data_url_mime(data_url), kind)
        fallback_name = fallback
        if inferred_suffix and not Path(str(fallback_name)).suffix:
            fallback_name = str(fallback_name) + inferred_suffix
        safe = self._safe_upload_name(filename, fallback_name)
        if inferred_suffix and not Path(safe).suffix:
            safe += inferred_suffix
        return safe

    def _run_modern_file_dialog(self, title="Open", kind="any", multiple=False):
        """Prefer KDE/portal-style native dialogs over PyWebView's old Qt dialog."""
        filters = {
            "image": "Images (*.png *.jpg *.jpeg *.webp)",
            "saved": "Character Cards / Projects (*.json *.png *.md *.txt)",
            "attachment": "Documents (*.txt *.srt *.vtt *.md *.pdf)",
            "any": "All Files (*)",
        }
        start_dir = str(Path.home())
        # KDE Plasma: this gives the modern KDE file picker instead of the embedded Qt/WebView one.
        if shutil.which("kdialog"):
            cmd = ["kdialog", "--title", title]
            if multiple:
                cmd += ["--multiple", "--separate-output"]
            cmd += ["--getopenfilename", start_dir, filters.get(kind, filters["any"])]
            try:
                proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    return []
                return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            except Exception as e:
                self._log_event("modern_file_dialog_kdialog_error", {"error": str(e), "cmd": cmd})
        # GNOME/GTK fallback.
        if shutil.which("zenity"):
            zfilters = {
                "image": "Images | *.png *.jpg *.jpeg *.webp",
                "saved": "Character Cards / Projects | *.json *.png *.md *.txt",
                "attachment": "Documents | *.txt *.srt *.vtt *.md *.pdf",
                "any": "All Files | *",
            }
            cmd = ["zenity", "--file-selection", "--title", title]
            if multiple:
                cmd += ["--multiple", "--separator=\n"]
            cmd += [f"--file-filter={zfilters.get(kind, zfilters['any'])}"]
            try:
                proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    return []
                return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            except Exception as e:
                self._log_event("modern_file_dialog_zenity_error", {"error": str(e), "cmd": cmd})
        # Last resort. This is the old-looking dialog, but only used if kdialog/zenity are unavailable.
        window = webview.windows[0] if webview.windows else None
        if not window:
            return []
        result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=multiple)
        if not result:
            return []
        if isinstance(result, (list, tuple)):
            return [str(x) for x in result]
        return [str(result)]

    def _copy_image_from_path(self, src_path, kind="card"):
        src = Path(str(src_path or ""))
        if not src.exists():
            return {"ok": False, "error": f"Image not found: {src}"}
        suffix = src.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            return {"ok": False, "error": "Please select a PNG, JPG, JPEG, or WebP image."}
        try:
            with Image.open(src) as img:
                img.verify()
        except Exception as e:
            return {"ok": False, "error": f"Selected file is not a valid image: {e}"}
        folder = VISION_IMAGES_DIR if kind == "vision" else CARD_IMAGES_DIR
        dest = folder / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{self._safe_upload_name(src.name, 'image' + suffix)}"
        shutil.copy2(src, dest)
        return {"ok": True, "path": str(dest), "filename": src.name, "sourcePath": str(src)}

    def pick_image_file(self, kind="card"):
        try:
            paths = self._run_modern_file_dialog("Select Vision Image" if kind == "vision" else "Select Card Image", "image", False)
            if not paths:
                return {"ok": False, "cancelled": True}
            return self._copy_image_from_path(paths[0], kind)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pick_saved_file(self):
        try:
            paths = self._run_modern_file_dialog("Load Saved Character Card / Project", "saved", False)
            if not paths:
                return {"ok": False, "cancelled": True}
            path = Path(paths[0])
            if path.suffix.lower() not in {".json", ".png", ".md", ".txt"}:
                return {"ok": False, "error": "Please select a JSON, PNG, MD, or TXT character card/project file."}
            return self._load_import_path(path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _concept_attachment_from_path(self, src_path):
        src = Path(str(src_path or ""))
        if not src.exists():
            return {"ok": False, "error": f"Attachment not found: {src}"}
        suffix = src.suffix.lower()
        if suffix not in {".txt", ".srt", ".vtt", ".md", ".pdf"}:
            return {"ok": False, "error": "Concept attachments support TXT, SRT, VTT, MD, and PDF files."}
        raw = src.read_bytes()
        if not raw:
            return {"ok": False, "error": "Attachment was empty."}
        filename = self._safe_upload_name(src.name, "attachment")
        path = CONCEPT_ATTACHMENTS_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}"
        shutil.copy2(src, path)
        if suffix == ".pdf":
            extracted = self._extract_pdf_text(path)
        else:
            extracted = None
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    extracted = raw.decode(enc)
                    break
                except Exception:
                    pass
            if extracted is None:
                extracted = "[Could not decode text attachment.]"
        max_chars = 90000
        truncated = False
        if len(extracted) > max_chars:
            extracted = extracted[:max_chars] + "\n\n[Attachment truncated to 90000 characters for prompt safety.]"
            truncated = True
        return {
            "ok": True,
            "id": uuid.uuid4().hex,
            "filename": filename,
            "path": str(path),
            "sourcePath": str(src),
            "text": extracted,
            "chars": len(extracted),
            "bytes": len(raw),
            "truncated": truncated,
        }

    def pick_concept_attachments(self):
        try:
            paths = self._run_modern_file_dialog("Attach Concept Files", "attachment", True)
            if not paths:
                return {"ok": False, "cancelled": True}
            attachments = []
            for path in paths:
                res = self._concept_attachment_from_path(path)
                if not res.get("ok"):
                    return res
                attachments.append(res)
            return {"ok": True, "attachments": attachments}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_uploaded_image(self, filename, data_url, kind="card"):
        try:
            filename = self._safe_name_with_extension(filename, "image.png", data_url, "image")
            suffix = Path(filename).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                return {"ok": False, "error": "Please select a PNG, JPG, JPEG, or WebP image."}
            raw = self._decode_data_payload(data_url)
            if not raw:
                return {"ok": False, "error": "Image upload was empty."}
            folder = VISION_IMAGES_DIR if str(kind).lower() == "vision" else CARD_IMAGES_DIR
            path = folder / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}"
            path.write_bytes(raw)
            # Verify Pillow can identify it, but do not rewrite the file.
            try:
                with Image.open(path) as img:
                    img.verify()
            except Exception as e:
                path.unlink(missing_ok=True)
                return {"ok": False, "error": f"Selected file is not a valid image: {e}"}
            return {"ok": True, "path": str(path), "filename": filename}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_import_upload(self, filename, data_url):
        try:
            filename = self._safe_upload_name(filename, "character_card")
            suffix = Path(filename).suffix.lower()
            if suffix not in {".json", ".png", ".md", ".txt"}:
                return {"ok": False, "error": "Please select a JSON, PNG, MD, or TXT character card/project file. Character Card V2/V3 PNG/JSON are supported."}
            raw = self._decode_data_payload(data_url)
            if not raw:
                return {"ok": False, "error": "Selected file was empty."}
            path = IMPORT_UPLOADS_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}"
            path.write_bytes(raw)
            result = self._load_import_path(path)
            if result.get("ok"):
                result["uploadedPath"] = str(path)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def card_upload_to_builders(self, filename, data_url, field_catalog, settings=None):
        """Load an existing character card/project upload and convert it into Builder fields."""
        try:
            filename = self._safe_upload_name(filename, "character_card")
            suffix = Path(filename).suffix.lower()
            if suffix not in {".json", ".png", ".md", ".txt"}:
                return {"ok": False, "error": "Please select a JSON, PNG, MD, or TXT character card/project file. Character Card V2/V3 PNG/JSON are supported."}
            raw = self._decode_data_payload(data_url)
            if not raw:
                return {"ok": False, "error": "Selected file was empty."}
            path = IMPORT_UPLOADS_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_builder_{filename}"
            path.write_bytes(raw)
            loaded = self._load_import_path(path)
            if not loaded.get("ok"):
                return loaded
            output = str(loaded.get("output") or "").strip()
            concept = str(loaded.get("concept") or "").strip()
            if not output and not concept:
                return {"ok": False, "error": "The selected card loaded, but it did not contain readable card text to transfer into builders."}
            source_text = output or concept
            self._log_event("card_upload_to_builders_loaded", {
                "filename": filename,
                "loadedType": loaded.get("loadedType"),
                "output_chars": len(output),
                "concept_chars": len(concept),
                "field_count": len(field_catalog or []),
            })
            transfer = self.ai_transfer_to_builders(source_text[:30000], "", field_catalog or [], settings or self.settings)
            if transfer.get("ok"):
                transfer["loadedType"] = loaded.get("loadedType", "card")
                transfer["sourcePath"] = loaded.get("sourcePath") or str(path)
                transfer["uploadedPath"] = str(path)
                transfer["sourceOutput"] = output
                main_concept = self._unmatched_card_context_for_main_concept(source_text)
                if transfer.get("sideCharacterNotes"):
                    side_block = "SIDE CHARACTERS / LOREBOOK-ONLY CHARACTERS:\n" + str(transfer.get("sideCharacterNotes") or "").strip()
                    main_concept = (main_concept + "\n\n" + side_block).strip() if main_concept else side_block
                transfer["mainConcept"] = main_concept
                transfer["imagePath"] = loaded.get("imagePath", "")
                transfer["embeddedImagePaths"] = loaded.get("embeddedImagePaths", [])
                transfer["message"] = "Loaded existing card into builders."
            return transfer
        except Exception as e:
            self._log_event("card_upload_to_builders_error", {"error": str(e)})
            return {"ok": False, "error": f"Load card to builders failed: {e}"}

    def pick_card_to_builders(self, field_catalog, settings=None):
        """Native file-picker variant of Load Card to Builders.

        This avoids pushing very large V3 JSON/PNG files through the JS bridge as
        base64 data URLs, which can fail or hang with embedded image-heavy cards.
        """
        try:
            paths = self._run_modern_file_dialog("Load Card to Builders", "card", False)
            if not paths:
                return {"ok": False, "cancelled": True}
            path = Path(paths[0])
            loaded = self._load_import_path(path)
            if not loaded.get("ok"):
                return loaded
            output = str(loaded.get("output") or "").strip()
            concept = str(loaded.get("concept") or "").strip()
            if not output and not concept:
                return {"ok": False, "error": "The selected card loaded, but it did not contain readable card text to transfer into builders."}
            source_text = output or concept
            self._log_event("card_pick_to_builders_loaded", {
                "path": str(path),
                "loadedType": loaded.get("loadedType"),
                "output_chars": len(output),
                "concept_chars": len(concept),
                "field_count": len(field_catalog or []),
            })
            transfer = self.ai_transfer_to_builders(source_text[:30000], "", field_catalog or [], settings or self.settings)
            if transfer.get("ok"):
                transfer["loadedType"] = loaded.get("loadedType", "card")
                transfer["sourcePath"] = loaded.get("sourcePath") or str(path)
                transfer["sourceOutput"] = output
                main_concept = self._unmatched_card_context_for_main_concept(source_text)
                if transfer.get("sideCharacterNotes"):
                    side_block = "SIDE CHARACTERS / LOREBOOK-ONLY CHARACTERS:\n" + str(transfer.get("sideCharacterNotes") or "").strip()
                    main_concept = (main_concept + "\n\n" + side_block).strip() if main_concept else side_block
                transfer["mainConcept"] = main_concept
                transfer["imagePath"] = loaded.get("imagePath", "")
                transfer["embeddedImagePaths"] = loaded.get("embeddedImagePaths", [])
                transfer["message"] = "Loaded existing card into builders."
            return transfer
        except Exception as e:
            self._log_event("card_pick_to_builders_error", {"error": str(e)})
            return {"ok": False, "error": f"Load card to builders failed: {e}"}

    def _loaded_card_to_main_concept_result(self, loaded, source_path):
        """Convert a loaded V2/V3/project/text card into Main Concept text without AI."""
        output = str(loaded.get("output") or "").strip()
        concept = str(loaded.get("concept") or "").strip()
        if output and concept and output != concept:
            main_concept = (concept + "\n\n--- Imported Card Text ---\n" + output).strip()
        else:
            main_concept = (output or concept).strip()
        if not main_concept:
            return {"ok": False, "error": "The selected card loaded, but it did not contain readable text for Main Concept."}
        return {
            "ok": True,
            "loadedType": loaded.get("loadedType", "card"),
            "sourcePath": loaded.get("sourcePath") or str(source_path),
            "mainConcept": main_concept,
            "sourceOutput": output,
            "imagePath": loaded.get("imagePath", ""),
            "embeddedImagePaths": loaded.get("embeddedImagePaths", []),
            "message": "Loaded existing card directly into Main Concept without AI.",
        }

    def card_upload_to_main_concept(self, filename, data_url, settings=None):
        """Load an existing card/project upload directly into Main Concept without AI."""
        try:
            filename = self._safe_upload_name(filename, "character_card")
            suffix = Path(filename).suffix.lower()
            if suffix not in {".json", ".png", ".md", ".txt"}:
                return {"ok": False, "error": "Please select a JSON, PNG, MD, or TXT character card/project file. Character Card V2/V3 PNG/JSON are supported."}
            raw = self._decode_data_payload(data_url)
            if not raw:
                return {"ok": False, "error": "Selected file was empty."}
            path = IMPORT_UPLOADS_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_concept_{filename}"
            path.write_bytes(raw)
            loaded = self._load_import_path(path)
            if not loaded.get("ok"):
                return loaded
            result = self._loaded_card_to_main_concept_result(loaded, path)
            self._log_event("card_upload_to_main_concept_loaded", {
                "filename": filename,
                "loadedType": loaded.get("loadedType"),
                "main_concept_chars": len(result.get("mainConcept") or "") if result.get("ok") else 0,
                "embedded_images": len(loaded.get("embeddedImagePaths", []) or []),
            })
            return result
        except Exception as e:
            self._log_event("card_upload_to_main_concept_error", {"error": str(e)})
            return {"ok": False, "error": f"Load card to Main Concept failed: {e}"}

    def pick_card_to_main_concept(self, settings=None):
        """Native file-picker card load directly to Main Concept, avoiding AI entirely."""
        try:
            paths = self._run_modern_file_dialog("Load Card to Main Concept", "card", False)
            if not paths:
                return {"ok": False, "cancelled": True}
            path = Path(paths[0])
            loaded = self._load_import_path(path)
            if not loaded.get("ok"):
                return loaded
            result = self._loaded_card_to_main_concept_result(loaded, path)
            self._log_event("card_pick_to_main_concept_loaded", {
                "path": str(path),
                "loadedType": loaded.get("loadedType"),
                "main_concept_chars": len(result.get("mainConcept") or "") if result.get("ok") else 0,
                "embedded_images": len(loaded.get("embeddedImagePaths", []) or []),
            })
            return result
        except Exception as e:
            self._log_event("card_pick_to_main_concept_error", {"error": str(e)})
            return {"ok": False, "error": f"Load card to Main Concept failed: {e}"}

    def _pdf_text_score(self, text):
        text = text or ""
        cjk = sum(1 for ch in text if "\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff")
        replacement = text.count("�") + text.count("□")
        return len(text.strip()) + (cjk * 3) - (replacement * 20)

    def _extract_pdf_text_with_pypdf(self, path):
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as e:
                page_text = f"[Could not extract page {i}: {e}]"
            page_text = page_text.strip()
            if page_text:
                pages.append(f"--- Page {i} ---\n{page_text}")
        return "\n\n".join(pages).strip()

    def _extract_pdf_text_with_pymupdf(self, path):
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        pages = []
        try:
            for i, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text") or ""
                except Exception as e:
                    page_text = f"[Could not extract page {i}: {e}]"
                page_text = page_text.strip()
                if page_text:
                    pages.append(f"--- Page {i} ---\n{page_text}")
        finally:
            doc.close()
        return "\n\n".join(pages).strip()

    def _extract_pdf_text_with_pdftotext(self, path):
        if not shutil.which("pdftotext"):
            return ""
        proc = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout.decode("utf-8", errors="replace").strip()

    def _extract_pdf_text(self, path):
        candidates = []
        errors = []
        for label, fn in (
            ("pypdf", self._extract_pdf_text_with_pypdf),
            ("pymupdf", self._extract_pdf_text_with_pymupdf),
            ("pdftotext", self._extract_pdf_text_with_pdftotext),
        ):
            try:
                extracted = fn(path)
                if extracted and extracted.strip():
                    candidates.append((self._pdf_text_score(extracted), label, extracted.strip()))
            except Exception as e:
                errors.append(f"{label}: {e}")
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            score, label, extracted = candidates[0]
            self._log_event("pdf_text_extracted", {
                "path": str(path),
                "method": label,
                "score": score,
                "chars": len(extracted),
                "alternatives": [{"method": m, "score": s, "chars": len(t)} for s, m, t in candidates[1:]],
            })
            return extracted
        error_msg = "; ".join(errors) if errors else "No extractor returned text."
        self._log_event("pdf_text_extract_failed", {"path": str(path), "errors": error_msg})
        return f"[Could not extract readable text from PDF. It may be image-only/scanned, encrypted, or use unsupported embedded fonts. Errors: {error_msg}]"

    def save_concept_attachment(self, filename, data_url):
        try:
            original_filename = filename
            mime = self._data_url_mime(data_url)
            raw = self._decode_data_payload(data_url)
            if not raw:
                return {"ok": False, "error": "Attachment was empty."}
            filename = self._safe_name_with_extension(filename, "attachment", data_url, "attachment")
            suffix = Path(filename).suffix.lower()
            # Some browser/drag-and-drop paths lose non-ASCII extensions or report application/octet-stream.
            # Sniff PDF bytes so 注意書き.pdf and similar CJK filenames still attach correctly.
            if not suffix and raw[:5] == b"%PDF-":
                filename = filename + ".pdf"
                suffix = ".pdf"
            if suffix not in {".txt", ".srt", ".vtt", ".md", ".pdf"}:
                # Last-chance PDF sniff even if filename sanitized weirdly.
                if raw[:5] == b"%PDF-":
                    filename = (Path(filename).stem or "attachment") + ".pdf"
                    suffix = ".pdf"
                else:
                    self._log_event("concept_attachment_import_rejected", {"original_filename": original_filename, "safe_filename": filename, "suffix": suffix, "mime": mime, "head": raw[:12].hex()})
                    return {"ok": False, "error": "Concept attachments support TXT, SRT, VTT, MD, and PDF files."}
            self._log_event("concept_attachment_import_start", {"original_filename": original_filename, "safe_filename": filename, "suffix": suffix, "mime": mime, "head": raw[:12].hex()})
            path = CONCEPT_ATTACHMENTS_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}"
            path.write_bytes(raw)
            if suffix == ".pdf":
                extracted = self._extract_pdf_text(path)
            else:
                extracted = None
                for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                    try:
                        extracted = raw.decode(enc)
                        break
                    except Exception:
                        pass
                if extracted is None:
                    extracted = "[Could not decode text attachment.]"
            # Keep prompts sane. User can attach more files, but each preview is capped.
            max_chars = 90000
            truncated = False
            if len(extracted) > max_chars:
                extracted = extracted[:max_chars] + "\n\n[Attachment truncated to 90000 characters for prompt safety.]"
                truncated = True
            return {
                "ok": True,
                "id": uuid.uuid4().hex,
                "filename": filename,
                "path": str(path),
                "text": extracted,
                "chars": len(extracted),
                "bytes": len(raw),
                "truncated": truncated,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def select_import_file(self):
        try:
            window = webview.windows[0] if webview.windows else None
            if not window:
                return {"ok": False, "error": "No active window."}
            # PyWebView/Qt file filter parsing is fragile across versions,
            # so we open a plain file picker and validate extensions after selection.
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False
            )
            if not result:
                return {"ok": False, "cancelled": True}
            path = Path(str(result[0] if isinstance(result, (list, tuple)) else result))
            if path.suffix.lower() not in {".json", ".png", ".md", ".txt"}:
                return {"ok": False, "error": "Please select a JSON, PNG, MD, or TXT character card/project file."}
            return self._load_import_path(path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _build_raw_card_from_chara_v2(self, payload):
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        lines = []
        def add(title, value):
            value = (value or "").strip()
            if not value:
                return
            lines.append("------------------------------------------------")
            lines.append(title)
            lines.append("")
            lines.append(value)
            lines.append("")
        name = data.get("name", "")
        if name:
            lines.append("------------------------------------------------")
            lines.append("Name")
            lines.append("")
            lines.append(name)
            lines.append("")
        add("Description", data.get("description", ""))
        add("Personality", data.get("personality", ""))
        add("Scenario", data.get("scenario", ""))
        add("First Message", data.get("first_mes", ""))
        alts = data.get("alternate_greetings", []) or []
        if alts:
            lines.append("------------------------------------------------")
            lines.append("Alternative First Messages")
            lines.append("")
            for idx, item in enumerate(alts, start=1):
                lines.append(f"Alternative First Message {idx}")
                lines.append(str(item).strip())
                lines.append("")
        add("Example Dialogues", data.get("mes_example", ""))
        tags = data.get("tags", []) or []
        if tags:
            add("Tags", ", ".join([str(t) for t in tags if str(t).strip()]))
        sys_prompt = data.get("system_prompt", "")
        if sys_prompt:
            add("Custom System Prompt", sys_prompt)
        ext = data.get("extensions", {}) if isinstance(data.get("extensions", {}), dict) else {}
        if ext.get("state_tracking"):
            add("State Tracking", ext.get("state_tracking", ""))
        if ext.get("stable_diffusion_prompt"):
            add("Stable Diffusion Prompt", ext.get("stable_diffusion_prompt", ""))

        # Chara Card V3 and some frontend extensions often store extra useful
        # text outside the classic V2 fields. Preserve those details when
        # importing into builders so things like first-message instructions,
        # creator notes, post-history instructions, and embedded extension notes
        # are not silently lost.
        if data.get("creator_notes"):
            add("Creator Notes", data.get("creator_notes", ""))
        if data.get("post_history_instructions"):
            add("Post History Instructions", data.get("post_history_instructions", ""))
        book = data.get("character_book") or data.get("characterBook") or {}
        entries = book.get("entries") if isinstance(book, dict) else []
        if isinstance(entries, list) and entries:
            lore_lines = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("comment") or entry.get("key") or ", ".join(entry.get("keys") or []) or "Entry"
                content = entry.get("content") or entry.get("value") or ""
                if str(content).strip():
                    lore_lines.append(f"Key: {name}\nValue: {content}")
            if lore_lines:
                add("Lorebook Entries", "\n\n".join(lore_lines))
        return "\n".join(lines).strip()

    def _embedded_image_suffix_from_mime(self, mime):
        mime = (mime or "").lower()
        if "jpeg" in mime or "jpg" in mime:
            return ".jpg"
        if "webp" in mime:
            return ".webp"
        if "gif" in mime:
            return ".gif"
        return ".png"

    def _save_embedded_card_image(self, raw, mime, label="embedded"):
        if not raw:
            return ""
        try:
            suffix = self._embedded_image_suffix_from_mime(mime)
            safe_label = self._safe_slug(label or "embedded")[:40] or "embedded"
            path = CARD_IMAGES_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_label}{suffix}"
            path.write_bytes(raw)
            try:
                with Image.open(path) as img:
                    img.verify()
            except Exception:
                # If the bytes are not a normal standalone image, keep the import
                # from failing but do not return a broken image path.
                path.unlink(missing_ok=True)
                return ""
            return str(path)
        except Exception:
            return ""

    def _extract_embedded_card_images(self, payload):
        """Extract embedded Chara Card V3/images assets and return saved paths.

        Chara Card V3 variants in the wild differ a little. This accepts common
        data URL, uri, url, data/base64, and image fields recursively without
        requiring one exact schema.
        """
        paths = []
        seen = set()
        def maybe_data_url(value, label="embedded"):
            if not isinstance(value, str):
                return
            s = value.strip()
            if not s.startswith("data:image/") or ";base64," not in s:
                return
            if s in seen:
                return
            seen.add(s)
            header, b64 = s.split(",", 1)
            mime = header.split(";", 1)[0].replace("data:", "")
            try:
                raw = base64.b64decode(b64)
            except Exception:
                return
            saved = self._save_embedded_card_image(raw, mime, label)
            if saved:
                paths.append(saved)

        def walk(obj, label="embedded"):
            if isinstance(obj, dict):
                local_label = str(obj.get("name") or obj.get("label") or obj.get("type") or obj.get("id") or label or "embedded")
                for key in ("uri", "url", "src", "image", "data", "dataUrl", "data_url"):
                    maybe_data_url(obj.get(key), local_label)
                # Some schemas split mime + base64 payload.
                b64 = obj.get("base64") or obj.get("bytes")
                mime = obj.get("mime") or obj.get("mime_type") or obj.get("content_type") or obj.get("type")
                if isinstance(b64, str) and isinstance(mime, str) and "image" in mime.lower():
                    try:
                        saved = self._save_embedded_card_image(base64.b64decode(b64), mime, local_label)
                        if saved:
                            paths.append(saved)
                    except Exception:
                        pass
                for v in obj.values():
                    walk(v, local_label)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, label)
            elif isinstance(obj, str):
                maybe_data_url(obj, label)
        walk(payload)
        # Deduplicate paths while preserving order.
        out = []
        for item in paths:
            if item not in out:
                out.append(item)
        return out

    def _unmatched_card_context_for_main_concept(self, output):
        """Keep card info that has no direct Builder field in Main Concept."""
        sections = self._parse_sections(output or "", self.template)
        wanted = [
            ("name", "Name"),
            ("first_message", "First Message"),
            ("alternate_first_messages", "Alternative First Messages"),
            ("example_dialogues", "Example Dialogues"),
            ("lorebook", "Lorebook Entries"),
            ("tags", "Tags"),
            ("system_prompt", "Custom System Prompt"),
            ("state_tracking", "State Tracking"),
            ("stable_diffusion", "Stable Diffusion Prompt"),
            ("creator_notes", "Creator Notes"),
            ("post_history_instructions", "Post History Instructions"),
        ]
        parts = []
        for sid, title in wanted:
            body = sections.get(sid, "")
            if body.strip():
                parts.append(f"{title}:\n{body.strip()}")
        # Also preserve V3/extra headings that are not core builder sources.
        for sid, body in sections.items():
            if sid in {"description", "personality", "sexual_traits", "background", "scenario"} or sid in {x[0] for x in wanted}:
                continue
            if body.strip():
                title = sid.replace("_", " ").title()
                parts.append(f"{title}:\n{body.strip()}")
        return "\n\n".join(parts).strip()

    def _load_project_payload(self, payload):
        project = payload.get("project", payload) if isinstance(payload, dict) else {}
        output = project.get("output") or project.get("raw_card") or ""
        workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
        return {
            "ok": True,
            "loadedType": "project",
            "concept": project.get("concept", ""),
            "output": output,
            "settings": self._normalise_settings(project.get("settings") or {}),
            "template": project.get("template") or self.template,
            "imagePath": (project.get("imagePath") or workspace.get("cardImagePath") or ""),
            "sourcePath": project.get("sourcePath") or "",
            "projectPath": project.get("projectPath") or "",
            "builderState": project.get("builderState") or workspace.get("builderState") or {},
            "qnaAnswers": project.get("qnaAnswers") or workspace.get("qnaAnswers") or "",
            "browserDescription": project.get("browserDescription") or workspace.get("browserDescription") or "",
            "browserDescriptionSourceHash": project.get("browserDescriptionSourceHash") or workspace.get("browserDescriptionSourceHash") or "",
            "tags": project.get("tags") or workspace.get("tags") or self._extract_tags_from_output(output, project.get("template") or self.template),
            "virtualFolderId": str(project.get("virtualFolderId") or workspace.get("virtualFolderId") or ""),
            "emotionImages": project.get("emotionImages") or workspace.get("emotionImages") or [],
            "emotionManifest": project.get("emotionManifest") or workspace.get("emotionManifest") or "",
            "visionDescription": project.get("visionDescription") or workspace.get("visionDescription") or "",
            "conceptAttachments": project.get("conceptAttachments") or workspace.get("conceptAttachments") or [],
            "message": "Loaded full Character Card Forge project with concept, template, settings, builders, Q&A, emotion images, and output.",
        }

    def _maybe_load_companion_project(self, path):
        folder = path.parent
        stem = path.stem
        candidates = []
        preferred_prefixes = [stem]
        for suffix in ["_cardv2", "_front_porch", "_hammer", "_sillytavern", "_generic"]:
            if stem.endswith(suffix):
                preferred_prefixes.append(stem[:-len(suffix)])
        for f in folder.glob("*_ccf_project.json"):
            name = f.stem
            if any(name.startswith(pref) for pref in preferred_prefixes if pref):
                candidates.append(f)
        if not candidates:
            return None
        candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        try:
            payload = json.loads(candidates[0].read_text(encoding="utf-8"))
            if isinstance(payload, dict) and (payload.get("format") == "character-card-forge-project" or payload.get("project")):
                return self._load_project_payload(payload)
        except Exception:
            return None
        return None

    def _decode_card_metadata_value(self, value):
        """Decode PNG card metadata values used by V2/V3 cards.

        Character card PNGs in the wild are annoyingly inconsistent:
        - V2 usually stores base64 JSON in a `chara` text chunk.
        - Some tools store plain JSON.
        - Some use URL-safe base64, missing padding, or insert whitespace.
        - Some compressed text chunks come through as compressed JSON bytes.
        This decoder accepts all of those before giving up.
        """
        if value is None:
            return None
        candidates = []
        if isinstance(value, bytes):
            candidates.append(value)
            for enc in ("utf-8", "utf-16", "latin-1"):
                try:
                    candidates.append(value.decode(enc))
                except Exception:
                    pass
        elif isinstance(value, str):
            candidates.append(value)
            try:
                candidates.append(value.encode("latin-1"))
            except Exception:
                pass
        else:
            return None

        def try_json_text(text):
            if not isinstance(text, str):
                return None
            text = text.strip().strip("\ufeff")
            if not text:
                return None
            if text.startswith("{") or text.startswith("["):
                try:
                    return json.loads(text)
                except Exception:
                    return None
            return None

        def try_json_bytes(raw):
            if not isinstance(raw, (bytes, bytearray)):
                return None
            byte_candidates = [bytes(raw)]
            for decomp in (zlib.decompress, gzip.decompress):
                if decomp is None:
                    continue
                try:
                    byte_candidates.append(decomp(bytes(raw)))
                except Exception:
                    pass
            for b in byte_candidates:
                for enc in ("utf-8", "utf-16", "latin-1"):
                    try:
                        parsed = try_json_text(b.decode(enc))
                        if parsed is not None:
                            return parsed
                    except Exception:
                        pass
            return None

        # Direct JSON / decoded byte JSON.
        for candidate in candidates:
            if isinstance(candidate, str):
                parsed = try_json_text(candidate)
                if parsed is not None:
                    return parsed
            else:
                parsed = try_json_bytes(candidate)
                if parsed is not None:
                    return parsed

        # URL-encoded JSON.
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            try:
                from urllib.parse import unquote
                u = unquote(candidate.strip())
                if u != candidate:
                    parsed = try_json_text(u)
                    if parsed is not None:
                        return parsed
            except Exception:
                pass

        # Base64 JSON metadata, with or without data: prefix. Try normal and URL-safe alphabets.
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            text = candidate.strip().strip("\ufeff")
            if not text:
                continue
            if "," in text and text.lower().startswith("data:"):
                text = text.split(",", 1)[1]
            # Some encoders wrap base64 or accidentally include whitespace.
            compact = re.sub(r"\s+", "", text)
            # Strip common JS/Python repr wrappers if a tool saved the string oddly.
            compact = compact.strip('"\'')
            variants = [compact, compact.replace("-", "+").replace("_", "/")]
            for item in variants:
                if not item:
                    continue
                padded = item + ("=" * (-len(item) % 4))
                for decoder in (base64.b64decode, base64.urlsafe_b64decode):
                    try:
                        raw = decoder(padded)
                    except Exception:
                        continue
                    parsed = try_json_bytes(raw)
                    if parsed is not None:
                        return parsed
        return None

    def _extract_png_text_chunks_raw(self, path):
        """Read PNG tEXt/zTXt/iTXt chunks manually.

        Pillow usually exposes these as Image.info, but some character cards use
        compressed or unusual text chunks that are safer to scan directly.
        """
        chunks = {}
        try:
            raw = Path(path).read_bytes()
        except Exception:
            return chunks
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            return chunks
        pos = 8
        while pos + 12 <= len(raw):
            try:
                length = int.from_bytes(raw[pos:pos+4], "big")
                ctype = raw[pos+4:pos+8]
                data = raw[pos+8:pos+8+length]
                pos = pos + 12 + length
            except Exception:
                break
            if ctype == b"IEND":
                break
            try:
                if ctype == b"tEXt" and b"\x00" in data:
                    key, text = data.split(b"\x00", 1)
                    chunks[key.decode("latin-1", errors="replace")] = text.decode("latin-1", errors="replace")
                elif ctype == b"zTXt" and b"\x00" in data:
                    key, rest = data.split(b"\x00", 1)
                    if rest:
                        method = rest[0]
                        compressed = rest[1:]
                        if method == 0:
                            text = zlib.decompress(compressed).decode("utf-8", errors="replace")
                            chunks[key.decode("latin-1", errors="replace")] = text
                elif ctype == b"iTXt" and b"\x00" in data:
                    # keyword\0 compression_flag compression_method language\0 translated_keyword\0 text
                    key, rest = data.split(b"\x00", 1)
                    if len(rest) >= 2:
                        comp_flag = rest[0]
                        comp_method = rest[1]
                        rest = rest[2:]
                        parts = rest.split(b"\x00", 2)
                        if len(parts) == 3:
                            _language, _translated, text_bytes = parts
                            if comp_flag == 1 and comp_method == 0:
                                text_bytes = zlib.decompress(text_bytes)
                            chunks[key.decode("latin-1", errors="replace")] = text_bytes.decode("utf-8", errors="replace")
            except Exception:
                continue
        return chunks

    def _extract_card_payload_from_png(self, path):
        """Return decoded Character Card V2/V3 payload from a PNG."""
        info = {}
        try:
            img = Image.open(path)
            info.update(dict(getattr(img, "info", {}) or {}))
        except Exception:
            pass
        raw_chunks = self._extract_png_text_chunks_raw(path)
        # Raw chunk scan wins only for missing keys so Pillow-decoded Unicode is kept when available.
        for key, value in raw_chunks.items():
            info.setdefault(key, value)

        preferred_keys = [
            "chara", "ccv2", "cc_v2", "chara_card_v2", "character_card_v2",
            "ccv3", "cc_v3", "chara_card_v3", "character-card-v3",
            "character_card", "character-card", "card", "metadata",
            "tavern_card", "sillytavern", "sillytavern_card", "sillytavern_chara_card_v2"
        ]
        lower_map = {str(k).lower(): k for k in info.keys()}
        # Prefer known card metadata chunks first, case-insensitively.
        for wanted in preferred_keys:
            actual = lower_map.get(wanted.lower())
            if actual is not None:
                payload = self._decode_card_metadata_value(info.get(actual))
                if isinstance(payload, dict):
                    return payload, str(actual)

        # Then scan all text chunks for a recognizable card payload.
        for key, value in info.items():
            payload = self._decode_card_metadata_value(value)
            if isinstance(payload, dict):
                spec = str(payload.get("spec") or payload.get("spec_version") or "").lower()
                if payload.get("data") or "chara_card" in spec or payload.get("name"):
                    return payload, str(key)

        # Final fallback: some bad encoders put raw JSON/base64 into an arbitrary chunk.
        # Avoid scanning huge image data; only look at ASCII-ish windows around known tokens.
        try:
            raw = Path(path).read_bytes()
            for token in (b'chara_card_v2', b'chara_card_v3', b'"first_mes"', b'"mes_example"'):
                idx = raw.find(token)
                if idx == -1:
                    continue
                start = max(0, raw.rfind(b'{', 0, idx))
                end = raw.find(b'}', idx)
                if start != -1 and end != -1:
                    snippet = raw[start:end+1]
                    payload = self._decode_card_metadata_value(snippet)
                    if isinstance(payload, dict):
                        return payload, "raw_png_scan"
        except Exception:
            pass
        return None, ""

    def _normalise_loaded_card_payload(self, payload):
        """Accept V2/V3 full payloads and data-only extracted JSON."""
        if not isinstance(payload, dict):
            return None
        if payload.get("spec") in {"chara_card_v2", "chara_card_v3"}:
            return payload
        # Some extractors save only the data object from a V3 card.
        cardish_keys = {"name", "description", "personality", "scenario", "first_mes", "mes_example", "alternate_greetings", "assets"}
        if cardish_keys.intersection(payload.keys()):
            guessed_spec = "chara_card_v3" if payload.get("assets") or payload.get("group_only_greetings") is not None else "chara_card_v2"
            return {"spec": guessed_spec, "spec_version": "3.0" if guessed_spec.endswith("v3") else "2.0", "data": payload}
        if isinstance(payload.get("data"), dict):
            data = payload.get("data")
            if cardish_keys.intersection(data.keys()):
                spec = payload.get("spec") or ("chara_card_v3" if data.get("assets") else "chara_card_v2")
                payload = dict(payload)
                payload["spec"] = spec
                return payload
        return None

    def _load_import_path(self, path):
        suffix = path.suffix.lower()
        if not path.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        if suffix == ".png":
            try:
                payload, meta_key = self._extract_card_payload_from_png(path)
                payload = self._normalise_loaded_card_payload(payload)
                if not isinstance(payload, dict):
                    # Sidecar fallback for tools that can extract the metadata even when
                    # the source PNG used a non-standard chunk encoding.
                    for candidate in [path.with_suffix(".extracted.json"), path.with_suffix(".json"), path.parent / f"{path.stem}.metadata.json"]:
                        try:
                            if candidate.exists():
                                sidecar_payload = json.loads(candidate.read_text(encoding="utf-8"))
                                payload = self._normalise_loaded_card_payload(sidecar_payload)
                                if isinstance(payload, dict):
                                    meta_key = f"sidecar:{candidate.name}"
                                    break
                        except Exception:
                            pass
                if not isinstance(payload, dict):
                    return {"ok": False, "error": "This PNG does not contain readable Character Card V2/V3 metadata. Checked common PNG text chunks including chara/ccv2/ccv3, compressed text chunks, and sidecar extracted JSON."}
                spec = str(payload.get("spec") or "")
                raw = payload.get("data", {}).get("extensions", {}).get("raw_card", "") if isinstance(payload, dict) else ""
                output = raw or self._build_raw_card_from_chara_v2(payload)
                embedded_images = self._extract_embedded_card_images(payload) if isinstance(payload, dict) else []
                companion = self._maybe_load_companion_project(path)
                self._log_event("png_card_metadata_loaded", {"path": str(path), "metadata_key": meta_key, "spec": spec, "output_chars": len(output or ""), "embedded_images": len(embedded_images)})
                if companion and companion.get("ok"):
                    companion["output"] = output or companion.get("output", "")
                    companion["imagePath"] = embedded_images[0] if embedded_images else str(path)
                    companion["embeddedImagePaths"] = embedded_images
                    companion["message"] = "Loaded character card PNG and restored the matching Character Card Forge project settings."
                    companion["loadedType"] = ("png_v3+project" if spec == "chara_card_v3" else "png+project")
                    return companion
                return {
                    "ok": True,
                    "loadedType": "png_v3" if spec == "chara_card_v3" else "png",
                    "concept": "",
                    "output": output,
                    "settings": self.settings,
                    "template": self.template,
                    "imagePath": embedded_images[0] if embedded_images else str(path),
                    "embeddedImagePaths": embedded_images,
                    "sourcePath": str(path),
                    "message": ("Loaded Character Card V3 PNG" if spec == "chara_card_v3" else "Loaded character card PNG") + (f" and extracted {len(embedded_images)} embedded image(s)." if embedded_images else ".") + " No saved project bundle was found, so current settings/template were kept.",
                }
            except Exception as e:
                return {"ok": False, "error": f"Could not load PNG card: {e}"}
        if suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                return {"ok": False, "error": f"Could not parse JSON: {e}"}
            if isinstance(payload, dict) and payload.get("format") == "character-card-forge-project":
                res = self._load_project_payload(payload)
                res["sourcePath"] = str(path)
                return res
            if isinstance(payload, dict) and payload.get("project") and isinstance(payload.get("project"), dict):
                res = self._load_project_payload(payload)
                res["sourcePath"] = str(path)
                return res
            if isinstance(payload, dict) and payload.get("format") == "character-card-forge-frontend-json":
                output = payload.get("raw_card") or self._build_raw_card_from_chara_v2(payload.get("sillytavern_chara_card_v2") or {})
                companion = self._maybe_load_companion_project(path)
                if companion and companion.get("ok"):
                    companion["output"] = output or companion.get("output", "")
                    companion["message"] = "Loaded frontend JSON and restored the matching Character Card Forge project settings."
                    companion["loadedType"] = "frontend_json+project"
                    return companion
                return {"ok": True, "loadedType": "frontend_json", "concept": "", "output": output, "settings": self.settings, "template": self.template, "imagePath": "", "sourcePath": str(path), "message": "Loaded frontend JSON. No saved project bundle was found, so current settings/template were kept."}
            card_payload = self._normalise_loaded_card_payload(payload)
            if isinstance(card_payload, dict):
                payload = card_payload
                spec = str(payload.get("spec") or "chara_card_v2")
                output = payload.get("data", {}).get("extensions", {}).get("raw_card", "") or self._build_raw_card_from_chara_v2(payload)
                embedded_images = self._extract_embedded_card_images(payload)
                self._log_event("json_card_metadata_loaded", {"path": str(path), "spec": spec, "output_chars": len(output or ""), "embedded_images": len(embedded_images)})
                companion = self._maybe_load_companion_project(path)
                if companion and companion.get("ok"):
                    companion["output"] = output or companion.get("output", "")
                    companion["message"] = ("Loaded Character Card V3 JSON" if spec == "chara_card_v3" else "Loaded Character Card V2 JSON") + " and restored the matching Character Card Forge project settings."
                    companion["loadedType"] = "card_json_v3+project" if spec == "chara_card_v3" else "card_json+project"
                    companion["embeddedImagePaths"] = embedded_images
                    if embedded_images:
                        companion["imagePath"] = embedded_images[0]
                    return companion
                return {"ok": True, "loadedType": "card_json_v3" if spec == "chara_card_v3" else "card_json", "concept": "", "output": output, "settings": self.settings, "template": self.template, "imagePath": embedded_images[0] if embedded_images else "", "embeddedImagePaths": embedded_images, "sourcePath": str(path), "message": ("Loaded Character Card V3 JSON" if spec == "chara_card_v3" else "Loaded Character Card V2 JSON") + (f" and extracted {len(embedded_images)} embedded image(s)." if embedded_images else ".") + " No saved project bundle was found, so current settings/template were kept."}
            return {"ok": False, "error": "JSON file was not recognized as a Character Card Forge project, frontend JSON, or Character Card V2/V3 file."}
        if suffix in {".md", ".txt"}:
            try:
                output = path.read_text(encoding="utf-8")
            except Exception as e:
                return {"ok": False, "error": f"Could not read text file: {e}"}
            companion = self._maybe_load_companion_project(path)
            if companion and companion.get("ok"):
                companion["output"] = output or companion.get("output", "")
                companion["message"] = "Loaded text card and restored the matching Character Card Forge project settings."
                companion["loadedType"] = "text+project"
                return companion
            return {"ok": True, "loadedType": "text", "concept": "", "output": output, "settings": self.settings, "template": self.template, "imagePath": "", "sourcePath": str(path), "message": "Loaded text card. No saved project bundle was found, so current settings/template were kept."}
        return {"ok": False, "error": f"Unsupported file type: {suffix}"}

    def _write_project_bundle(self, export_folder, safe_name, stamp, output, concept, template, settings, image_path, exported_path, frontend, export_format):
        payload = {
            "format": "character-card-forge-project",
            "version": (APP_DIR / "VERSION").read_text(encoding="utf-8").strip() if (APP_DIR / "VERSION").exists() else "unknown",
            "saved_at": stamp,
            "project": {
                "name": safe_name,
                "concept": concept or "",
                "output": output or "",
                "template": template or self.template,
                "settings": self._normalise_settings(settings or self.settings),
                "imagePath": image_path or "",
                "exportedPath": str(exported_path),
                "frontend": frontend or "front_porch",
                "exportFormat": export_format or "chara_v2_png",
            }
        }
        project_path = export_folder / f"{self._safe_slug(safe_name)}_{stamp}_ccf_project.json"
        payload["project"]["projectPath"] = str(project_path)
        project_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        latest_path = export_folder / "latest_ccf_project.json"
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return project_path

    def _image_data_url(self, path, max_size=(360, 480)):
        try:
            p = Path(str(path or ""))
            if not p.exists() or p.is_dir():
                return ""
            with Image.open(p) as img:
                img.thumbnail(max_size, Image.LANCZOS)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return ""

    def _read_emotion_manifest_for_folder(self, folder):
        try:
            folder = Path(folder)
            manifests = sorted(folder.glob("emotion_prompts_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not manifests:
                return {}
            return json.loads(manifests[0].read_text(encoding="utf-8"))
        except Exception:
            return {}


    def _browser_description_source_hash(self, output, concept=''):
        source = ((concept or '') + '\n\n' + (output or '')).strip()
        return hashlib.sha256(source.encode('utf-8', errors='ignore')).hexdigest()[:16]

    def _fallback_browser_description(self, output, concept=''):
        sections = self._parse_sections(output or '')
        name = self._extract_name(output or '') or 'This character'
        scenario = self._clean_section_text(sections.get('scenario', ''))
        personality = self._clean_section_text(sections.get('personality', ''))
        first = self._clean_section_text(sections.get('first_message', ''))
        concept = self._clean_section_text(concept or '')
        pieces = []
        if scenario:
            pieces.append(scenario)
        elif concept:
            pieces.append(concept)
        if personality:
            pieces.append(personality)
        if first and len(' '.join(pieces)) < 300:
            pieces.append(first)
        text = re.sub(r'\s+', ' ', ' '.join(pieces)).strip()
        if not text:
            text = f'{name} is a saved character card with a ready-to-load roleplay setup.'
        # Keep the browser description short and useful.
        if len(text) > 420:
            cut = text[:420].rsplit(' ', 1)[0].rstrip('.,;:')
            text = cut + '…'
        if name and not text.lower().startswith(name.lower()):
            text = f'{name}: {text}'
        return text

    def _generate_browser_description(self, output, concept='', settings=None):
        """Create a short Character Browser blurb about the route, not just appearance."""
        self._last_browser_description_source = "extracted"
        self._init_library_db()
        output = output or ''
        concept = concept or ''
        merged = self._normalise_settings({**self.settings, **(settings or {})})
        fallback = self._fallback_browser_description(output, concept)
        if not output.strip():
            return fallback
        # If the text API is not configured, still provide a useful non-AI fallback
        # instead of blocking autosave/export.
        if not self._validate_text_api_settings(merged).get('ok'):
            return fallback
        try:
            sections = self._parse_sections(output)
            compact = {
                'name': self._extract_name(output),
                'scenario': sections.get('scenario', '')[:2500],
                'personality': sections.get('personality', '')[:2200],
                'first_message': sections.get('first_message', '')[:1600],
                'tags': sections.get('tags', '')[:600],
                'concept': concept[:1800],
            }
            prompt = '\n'.join([
                'Create a short library/browser description for this fictional AI character card.',
                'This is NOT the physical Description field. Summarize what the scenario is about and give a brief overview of the character/dynamic involved.',
                'Return 2-4 sentences, maximum 90 words.',
                'Mention the main setup, relationship/tension, and roleplay hook. Avoid markdown, headings, lists, and quoted dialogue.',
                'Do not focus on clothing/body details unless they are central to the premise.',
                '',
                'CARD DATA JSON:',
                json.dumps(compact, ensure_ascii=False, indent=2),
            ]).strip()
            check = self._context_check(prompt, merged, mode_label='Browser description')
            if not check.get('ok'):
                return fallback
            local_settings = dict(merged)
            local_settings['maxOutputTokens'] = min(350, int(local_settings.get('maxOutputTokens') or 350))
            local_settings['temperature'] = min(0.55, float(local_settings.get('temperature', 0.45) or 0.45))
            text = self._chat_once(prompt, local_settings, (local_settings.get('aiSuggestionModel') or local_settings.get('model') or '').strip(), 'browser_description')
            text = re.sub(r'(?is)^```(?:\w+)?\s*|\s*```$', '', text or '').strip()
            text = re.sub(r'\s+', ' ', text).strip()
            if not text or self._looks_like_text_refusal(text):
                return fallback
            if len(text) > 620:
                text = text[:620].rsplit(' ', 1)[0].rstrip('.,;:') + '…'
            self._last_browser_description_source = "ai"
            return text
        except Exception as e:
            self._log_event('browser_description_generation_failed', {'error': str(e)})
            return fallback

    def _extract_tags_from_output(self, output, template=None):
        try:
            parsed_tags = self._parse_sections(output or "", template or self.template).get("tags", "")
            if not parsed_tags:
                parsed_tags = self._section(output or "", "Tags")
            seen = set()
            tags = []
            for raw in re.split(r"[,\n]+", str(parsed_tags or "")):
                tag = raw.strip().lstrip("-•*").strip()
                if not tag:
                    continue
                key = tag.lower()
                if key not in seen:
                    seen.add(key)
                    tags.append(tag)
            return tags
        except Exception:
            return []

    def _replace_tags_section(self, output, tags, template=None):
        output = output or ""
        tag_text = ", ".join([str(t).strip() for t in (tags or []) if str(t).strip()])
        lines = output.splitlines()
        start = None
        end = None
        for i, line in enumerate(lines):
            try:
                heading = self._canonical_heading_with_template(line, template or self.template)
            except Exception:
                heading = None
            if heading == "tags":
                start = i
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    try:
                        next_heading = self._canonical_heading_with_template(lines[j], template or self.template)
                    except Exception:
                        next_heading = None
                    if next_heading:
                        end = j
                        break
                break
        if start is None:
            suffix = f"Tags:\n{tag_text}" if tag_text else "Tags:\n"
            return (output.rstrip() + "\n\n" + suffix).strip()
        heading_line = lines[start]
        replacement = [heading_line]
        if tag_text:
            replacement.append(tag_text)
        new_lines = lines[:start] + replacement + lines[end:]
        return "\n".join(new_lines).strip()


    def _all_character_projects(self):
        projects = []
        if not EXPORT_DIR.exists():
            return projects
        for folder in sorted([p for p in EXPORT_DIR.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
            project_path = folder / "latest_ccf_project.json"
            if not project_path.exists():
                candidates = sorted(folder.glob("*_ccf_project.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                project_path = candidates[0] if candidates else None
            if project_path and Path(project_path).exists():
                projects.append(Path(project_path))
        return projects

    def _normalise_tag_key(self, tag):
        return re.sub(r"\s+", " ", str(tag or "").strip()).lower()

    def _collect_library_tag_stats(self):
        stats = {}
        projects = []
        for project_path in self._all_character_projects():
            try:
                payload = json.loads(project_path.read_text(encoding="utf-8"))
                project = payload.get("project", payload) if isinstance(payload, dict) else {}
                if not isinstance(project, dict):
                    continue
                tags = project.get("tags") if isinstance(project.get("tags"), list) else []
                if not tags:
                    tags = self._extract_tags_from_output(project.get("output") or "", project.get("template") or self.template)
                clean_tags = []
                seen_for_card = set()
                for raw in tags:
                    tag = str(raw or "").strip().strip(",")
                    key = self._normalise_tag_key(tag)
                    if not key or key in seen_for_card:
                        continue
                    seen_for_card.add(key)
                    clean_tags.append(tag)
                    entry = stats.setdefault(key, {"tag": tag, "count": 0})
                    entry["count"] += 1
                    # Keep the nicest-looking capitalization from the first occurrence.
                    if not entry.get("tag") or entry.get("tag") == key:
                        entry["tag"] = tag
                projects.append({"path": str(project_path), "name": project.get("name") or project_path.parent.name, "tags": clean_tags})
            except Exception as e:
                self._log_event("collect_library_tag_stats_error", {"project": str(project_path), "error": str(e)})
        return stats, projects

    def ai_suggest_tag_cleanup(self, settings=None):
        """Ask the configured text model for near-duplicate tag merge suggestions."""
        try:
            local_settings = self._normalise_settings({**self.settings, **(settings or {})})
            validation = self._validate_text_api_settings(local_settings)
            if not validation.get("ok"):
                return {"ok": False, "error": validation.get("error") or "AI settings are incomplete."}
            stats, projects = self._collect_library_tag_stats()
            tags = sorted(stats.values(), key=lambda x: (-int(x.get("count") or 0), str(x.get("tag") or "").lower()))
            if len(tags) < 2:
                return {"ok": True, "suggestions": [], "message": "Not enough tags to compare."}
            tag_lines = [f"- {item['tag']} ({item['count']} cards)" for item in tags[:700]]
            prompt = "\n".join([
                "You are helping clean tags for a fictional character card library.",
                "Find tags that are very close in meaning and could be merged or renamed.",
                "Only suggest true duplicates, spelling/capitalization variants, plural/singular variants, hyphen/space variants, or very close synonyms.",
                "Do not merge opposite meanings or broad/narrow tags unless they are genuinely redundant.",
                "For each suggestion, choose the cleanest canonical tag as merge_to.",
                "Return strict JSON only with this shape:",
                '{"suggestions":[{"from":"tag to merge/rename","to":"canonical tag","reason":"short reason"}]}',
                "Existing tags with card counts:",
                "\n".join(tag_lines),
            ])
            model = (local_settings.get("aiSuggestionModel") or local_settings.get("model") or "").strip()
            raw = self._chat_once(prompt, local_settings, model, "ai_tag_cleanup")
            parsed = self._loads_model_json(raw)
            raw_suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else []
            if not isinstance(raw_suggestions, list):
                raw_suggestions = []
            known = {self._normalise_tag_key(v.get("tag")): v.get("tag") for v in tags}
            suggestions = []
            seen = set()
            for item in raw_suggestions[:200]:
                if not isinstance(item, dict):
                    continue
                from_tag = str(item.get("from") or item.get("old") or item.get("source") or "").strip()
                to_tag = str(item.get("to") or item.get("merge_to") or item.get("target") or "").strip()
                reason = str(item.get("reason") or "").strip()
                from_key = self._normalise_tag_key(from_tag)
                to_key = self._normalise_tag_key(to_tag)
                if not from_key or not to_key or from_key == to_key:
                    continue
                if from_key not in known:
                    continue
                canonical_to = known.get(to_key, to_tag)
                pair = (from_key, self._normalise_tag_key(canonical_to))
                if pair in seen:
                    continue
                seen.add(pair)
                suggestions.append({
                    "from": known.get(from_key, from_tag),
                    "to": canonical_to,
                    "fromCount": int(stats.get(from_key, {}).get("count") or 0),
                    "toCount": int(stats.get(self._normalise_tag_key(canonical_to), {}).get("count") or 0),
                    "reason": reason[:240],
                })
            return {"ok": True, "suggestions": suggestions, "tagCount": len(tags), "cardCount": len(projects), "raw": raw[:2000]}
        except Exception as e:
            self._log_event("ai_tag_cleanup_failed", {"error": str(e)})
            return {"ok": False, "error": f"AI tag cleanup failed: {e}"}

    def rename_tags_across_library(self, rename_map):
        """Destructively rename real tags across saved character projects/cards."""
        try:
            if not isinstance(rename_map, dict) or not rename_map:
                return {"ok": False, "error": "No tag rename map was provided."}
            clean_map = {}
            for old, new in rename_map.items():
                old_key = self._normalise_tag_key(old)
                new_tag = str(new or "").strip().strip(",")
                if old_key and new_tag and old_key != self._normalise_tag_key(new_tag):
                    clean_map[old_key] = new_tag[:120]
            if not clean_map:
                return {"ok": False, "error": "No valid tag renames were provided."}
            updated = 0
            touched = []
            for project_path in self._all_character_projects():
                try:
                    payload = json.loads(project_path.read_text(encoding="utf-8"))
                    project = payload.get("project", payload) if isinstance(payload, dict) else {}
                    if not isinstance(project, dict):
                        continue
                    tags = project.get("tags") if isinstance(project.get("tags"), list) else []
                    if not tags:
                        tags = self._extract_tags_from_output(project.get("output") or "", project.get("template") or self.template)
                    new_tags = []
                    seen = set()
                    changed = False
                    for tag in tags:
                        original = str(tag or "").strip().strip(",")
                        if not original:
                            continue
                        replacement = clean_map.get(self._normalise_tag_key(original), original)
                        if replacement != original:
                            changed = True
                        key = self._normalise_tag_key(replacement)
                        if key and key not in seen:
                            seen.add(key)
                            new_tags.append(replacement)
                    if changed:
                        res = self.update_character_project_tags(str(project_path), new_tags)
                        if res.get("ok"):
                            updated += 1
                            touched.append(str(project_path))
                except Exception as e:
                    self._log_event("rename_tags_project_failed", {"project": str(project_path), "error": str(e)})
            return {"ok": True, "updated": updated, "projects": touched, "renameMap": clean_map}
        except Exception as e:
            return {"ok": False, "error": f"Could not rename tags: {e}"}

    def regenerate_browser_description_for_project(self, project_path, settings=None):
        """Use AI to refresh the Character Browser scenario/character overview for one saved project."""
        try:
            path = Path(project_path)
            if not path.exists():
                return {"ok": False, "error": "Character project not found."}
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid character project."}
            output = project.get("output") or ""
            concept = project.get("concept") or ""
            if not output.strip() and not concept.strip():
                return {"ok": False, "error": "This project has no card text to summarize."}
            desc = self._generate_browser_description(output, concept, settings or project.get("settings") or self.settings)
            source = "ai" if self._last_browser_description_source == "ai" else "extracted"
            project["browserDescription"] = desc
            project["browserDescriptionSourceHash"] = self._browser_description_source_hash(output, concept)
            project["browserDescriptionSource"] = source
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            workspace["browserDescription"] = desc
            workspace["browserDescriptionSource"] = source
            project["workspace"] = workspace
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                self._refresh_library_cache_for_project(path, force=True)
            except Exception:
                pass
            return {"ok": True, "browserDescription": desc, "browserDescriptionSource": source, "projectPath": str(path)}
        except Exception as e:
            self._log_event("regenerate_browser_description_failed", {"project": str(project_path), "error": str(e)})
            return {"ok": False, "error": f"Could not regenerate browser description: {e}"}

    def update_character_project_tags(self, project_path, tags):
        try:
            path = Path(project_path)
            if not path.exists():
                return {"ok": False, "error": "Character project not found."}
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid character project."}
            clean_tags = []
            seen = set()
            for raw in tags or []:
                tag = str(raw or "").strip().strip(",")
                if not tag:
                    continue
                key = tag.lower()
                if key in seen:
                    continue
                seen.add(key)
                clean_tags.append(tag)
            template = project.get("template") or self.template
            output = self._replace_tags_section(project.get("output") or "", clean_tags, template)
            project["output"] = output
            project["tags"] = clean_tags
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            workspace["output"] = output
            workspace["tags"] = clean_tags
            project["workspace"] = workspace
            project["saved_at"] = time.strftime("%Y%m%d-%H%M%S")
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            folder = path.parent
            name = project.get("name") or self._extract_name(output) or folder.name
            image_path = project.get("imagePath") or project.get("cardImagePath") or workspace.get("cardImagePath") or ""
            (folder / "latest_output.md").write_text(output, encoding="utf-8")
            latest_card = folder / f"{self._safe_slug(name)}_latest_cardv2.png"
            try:
                card_payload = self._to_chara_card_v2(output, name)
                self._write_chara_png(latest_card, card_payload, image_path)
                project["exportedPath"] = str(latest_card)
            except Exception as e:
                self._log_event("update_project_tags_card_refresh_failed", {"error": str(e), "project": str(path)})
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                self._refresh_library_cache_for_project(path, force=True)
            except Exception:
                pass
            self._log_event("character_project_tags_updated", {"project": str(path), "tags": clean_tags})
            return {"ok": True, "tags": clean_tags, "output": output, "projectPath": str(path)}
        except Exception as e:
            return {"ok": False, "error": f"Could not update tags: {e}"}

    def save_character_workspace(self, workspace):
        """Autosave the complete editable workspace into exports/<Character Name>/.

        This is the project's new source-of-truth save. It keeps the generated card,
        concept, builders, Q&A answers, settings/template, selected card image, and
        emotion prompt/image references together so the Character Browser can restore
        the whole route later.
        """
        workspace = workspace or {}
        output = workspace.get("output") or ""
        if not output.strip():
            return {"ok": False, "error": "Nothing to save yet. Generate or load a card first."}
        safe_name = workspace.get("name") or self._extract_name(output) or "Character Card"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        folder = self._character_export_dir(safe_name)
        settings = self._normalise_settings(workspace.get("settings") or self.settings)
        image_path = workspace.get("cardImagePath") or workspace.get("imagePath") or settings.get("cardImagePath") or ""
        template = workspace.get("template") or self.template
        concept = workspace.get("concept") or ""
        latest_project = folder / "latest_ccf_project.json"
        previous_project = {}
        if latest_project.exists():
            try:
                previous_payload = json.loads(latest_project.read_text(encoding="utf-8"))
                previous_project = previous_payload.get("project", previous_payload) or {}
            except Exception:
                previous_project = {}
        browser_source_hash = self._browser_description_source_hash(output, concept)
        browser_description = str(
            workspace.get("browserDescription")
            or workspace.get("libraryDescription")
            or workspace.get("scenarioDescription")
            or ""
        ).strip()
        previous_hash = str(previous_project.get("browserDescriptionSourceHash") or "").strip()
        if not browser_description and previous_hash == browser_source_hash:
            browser_description = str(previous_project.get("browserDescription") or "").strip()
        browser_description_source = str(workspace.get("browserDescriptionSource") or previous_project.get("browserDescriptionSource") or "").strip()
        if browser_description:
            browser_description_source = browser_description_source or ("ai" if previous_project.get("browserDescription") else "extracted")
        if not browser_description:
            browser_description = self._generate_browser_description(output, concept, settings)
            browser_description_source = "ai" if self._last_browser_description_source == "ai" else "extracted"
        # Keep latest text files simple and inspectable.
        (folder / "latest_output.md").write_text(output, encoding="utf-8")
        if workspace.get("qnaAnswers"):
            (folder / "qna_answers.md").write_text(str(workspace.get("qnaAnswers") or ""), encoding="utf-8")
        if workspace.get("builderState"):
            (folder / "builder_state.json").write_text(json.dumps(workspace.get("builderState"), indent=2, ensure_ascii=False), encoding="utf-8")
        if workspace.get("emotionImages"):
            (folder / "emotion_images_state.json").write_text(json.dumps(workspace.get("emotionImages"), indent=2, ensure_ascii=False), encoding="utf-8")

        # Automatically maintain a latest card PNG so the browser always has a usable card file.
        latest_card = folder / f"{self._safe_slug(safe_name)}_latest_cardv2.png"
        try:
            payload = self._to_chara_card_v2(output, safe_name)
            self._write_chara_png(latest_card, payload, image_path)
        except Exception as e:
            self._log_event("autosave_latest_card_failed", {"error": str(e)})
            latest_card = Path("")

        tags = self._extract_tags_from_output(output, template)
        virtual_folder_id = str(workspace.get("virtualFolderId") or previous_project.get("virtualFolderId") or "").strip()
        project = {
            "format": "character-card-forge-project",
            "version": (APP_DIR / "VERSION").read_text(encoding="utf-8").strip() if (APP_DIR / "VERSION").exists() else "unknown",
            "saved_at": stamp,
            "project": {
                "name": safe_name,
                "concept": concept,
                "output": output,
                "template": template,
                "settings": settings,
                "imagePath": image_path,
                "cardImagePath": image_path,
                "browserDescription": browser_description,
                "browserDescriptionSourceHash": browser_source_hash,
                "browserDescriptionSource": browser_description_source,
                "tags": tags,
                "virtualFolderId": virtual_folder_id,
                "projectPath": str(latest_project),
                "exportedPath": str(latest_card) if str(latest_card) else "",
                "frontend": "front_porch",
                "exportFormat": "chara_v2_png",
                "builderState": workspace.get("builderState") or {},
                "qnaAnswers": workspace.get("qnaAnswers") or "",
                "emotionImages": workspace.get("emotionImages") or [],
                "emotionManifest": workspace.get("emotionManifest") or "",
                "visionDescription": workspace.get("visionDescription") or "",
                "conceptAttachments": workspace.get("conceptAttachments") or [],
                "workspace": workspace,
            }
        }
        latest_project.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        # Also keep a timestamped project snapshot on first generation/export moments.
        snapshot = folder / f"{self._safe_slug(safe_name)}_{stamp}_ccf_project.json"
        if not snapshot.exists():
            snapshot.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            vf = str(project.get("virtualFolderId") or (project.get("workspace") or {}).get("virtualFolderId") or "").strip()
            # Refresh SQLite cache immediately after editor/output changes. This stores
            # metadata, tags, thumbnail image data, and hash checks for fast browsing.
            self._refresh_library_cache_for_project(latest_project, force=True)
            if vf:
                self._library_set_card_folder(latest_project, vf)
        except Exception as e:
            self._log_event("library_db_workspace_upsert_failed", {"name": safe_name, "error": str(e)})
        self._log_event("character_workspace_saved", {"name": safe_name, "folder": str(folder), "project": str(latest_project)})
        return {"ok": True, "name": safe_name, "folder": str(folder), "projectPath": str(latest_project), "cardPath": str(latest_card) if str(latest_card) else ""}

    def _virtual_folder_assignment_keys(self, project_path, folder, name=""):
        keys = []
        try:
            keys.append(str(Path(project_path).resolve()))
        except Exception:
            if project_path:
                keys.append(str(project_path))
        try:
            keys.append(str(Path(folder).resolve()))
        except Exception:
            if folder:
                keys.append(str(folder))
        safe_name = self._safe_slug(name or "") if name else ""
        if safe_name:
            keys.append(f"name:{safe_name}")
        # Preserve insertion order while removing duplicates.
        out = []
        seen = set()
        for key in keys:
            key = str(key or "").strip()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
        return out

    def _get_virtual_folder_assignment(self, project_path, folder, name="", fallback=""):
        assignments = self.settings.get("browserVirtualFolderAssignments") if isinstance(self.settings.get("browserVirtualFolderAssignments"), dict) else {}
        for key in self._virtual_folder_assignment_keys(project_path, folder, name):
            if key in assignments:
                return str(assignments.get(key) or "").strip()
        return str(fallback or "").strip()

    def _set_virtual_folder_assignment(self, project_path, folder, name, folder_id):
        assignments = self.settings.get("browserVirtualFolderAssignments") if isinstance(self.settings.get("browserVirtualFolderAssignments"), dict) else {}
        folder_id = str(folder_id or "").strip()
        for key in self._virtual_folder_assignment_keys(project_path, folder, name):
            assignments[key] = folder_id
        self.settings["browserVirtualFolderAssignments"] = assignments
        self.save_settings(self.settings)

    def list_character_library(self):
        """Return Character Browser cards from the SQLite cache.

        Disk scan only discovers project files and checks hashes. Full JSON/image parsing
        happens only when hashes changed or a card is new.
        """
        cards = []
        if not EXPORT_DIR.exists():
            return {"ok": True, "cards": [], "folders": self._library_folders()}
        seen_paths = set()
        project_files = []
        for folder in sorted([p for p in EXPORT_DIR.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
            project_path = folder / "latest_ccf_project.json"
            if not project_path.exists():
                projects = sorted(folder.glob("*_ccf_project.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                project_path = projects[0] if projects else None
            if project_path and Path(project_path).exists():
                project_files.append(Path(project_path))

        for project_path in project_files:
            try:
                seen_paths.add(str(project_path.resolve()))
                card = self._refresh_library_cache_for_project(project_path, force=False)
                if card:
                    cards.append(card)
            except Exception as e:
                self._log_event("character_library_card_error", {"project": str(project_path), "error": str(e)})

        # Mark DB rows whose physical project vanished as deleted, rather than
        # showing stale cards from the cache.
        try:
            with self._library_connect() as conn:
                rows = conn.execute("SELECT project_path FROM browser_cards WHERE deleted=0").fetchall()
                missing = [(time.time(), str(r["project_path"])) for r in rows if str(r["project_path"] or "") not in seen_paths and not Path(str(r["project_path"] or "")).exists()]
                if missing:
                    conn.executemany("UPDATE browser_cards SET deleted=1, last_seen_ts=? WHERE project_path=?", missing)
                    conn.commit()
        except Exception:
            pass

        folders = self._library_folders()
        self.settings["browserVirtualFolders"] = folders
        self.save_settings(self.settings)
        return {"ok": True, "cards": cards, "folders": folders, "dbPath": str(LIBRARY_DB_FILE)}

    def load_character_project(self, project_path):
        try:
            # Quick real-file check before opening. If the project/card/image changed
            # outside the app, refresh the SQLite cache first.
            self._refresh_library_cache_for_project(project_path, force=False)
            payload = json.loads(Path(project_path).read_text(encoding="utf-8"))
            res = self._load_project_payload(payload)
            res["projectPath"] = str(project_path)
            return res
        except Exception as e:
            return {"ok": False, "error": f"Could not load character project: {e}"}

    def export_character_from_project(self, project_path, export_format="chara_v2_png"):
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            return loaded
        return self.export_card(
            loaded.get("output") or "",
            "front_porch",
            export_format or "chara_v2_png",
            loaded.get("imagePath") or "",
            loaded.get("concept") or "",
            loaded.get("template") or self.template,
            loaded.get("settings") or self.settings,
        )

    def create_emotion_zip_for_project(self, project_path):
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            return loaded
        return self.create_emotion_zip(loaded.get("output") or "")


    def save_browser_virtual_folders(self, folders):
        """Persist virtual folder definitions in SQLite. They are browser-only and never move files."""
        try:
            self._init_library_db()
            clean = []
            seen = set()
            for item in folders or []:
                if not isinstance(item, dict):
                    continue
                fid = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
                parent = str(item.get("parentId") or "").strip()
                if not fid or not name or fid in seen:
                    continue
                seen.add(fid)
                clean.append({"id": fid, "name": name[:120], "parentId": parent})

            new_ids = {f["id"] for f in clean}
            with self._library_connect() as conn:
                old_ids = {r["id"] for r in conn.execute("SELECT id FROM browser_folders").fetchall()}
                deleted_ids = old_ids - new_ids
                for item in clean:
                    conn.execute(
                        "INSERT INTO browser_folders(id, name, parent_id) VALUES(?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, parent_id=excluded.parent_id, updated_at=CURRENT_TIMESTAMP",
                        (item["id"], item["name"], item["parentId"]),
                    )
                for fid in deleted_ids:
                    conn.execute("DELETE FROM browser_folders WHERE id=?", (fid,))
                    conn.execute("UPDATE browser_cards SET virtual_folder_id='', updated_ts=?, last_seen_ts=? WHERE virtual_folder_id=?", (time.time(), time.time(), fid))
                conn.commit()

            self.settings["browserVirtualFolders"] = clean
            self.save_settings(self.settings)
            return {"ok": True, "folders": clean}
        except Exception as e:
            return {"ok": False, "error": f"Could not save virtual folders: {e}"}

    def _project_path_inside_exports(self, project_path):
        path = Path(project_path).resolve()
        export_root = EXPORT_DIR.resolve()
        try:
            path.relative_to(export_root)
        except Exception:
            raise ValueError("Project path is outside the exports folder.")
        if not path.exists() or not path.is_file():
            raise ValueError("Character project not found.")
        return path

    def move_character_projects_to_folder(self, project_paths, folder_id=""):
        """Assign projects to a virtual folder. Does not move files on disk."""
        updated = 0
        touched = []
        try:
            folder_id = str(folder_id or "").strip()
            for raw in project_paths or []:
                try:
                    path = self._project_path_inside_exports(raw)
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    project = payload.get("project", payload) if isinstance(payload, dict) else {}
                    if not isinstance(project, dict):
                        continue
                    project["virtualFolderId"] = folder_id
                    workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
                    workspace["virtualFolderId"] = folder_id
                    project["workspace"] = workspace
                    project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                    self._library_upsert_card(path, path.parent, project.get("name") or path.parent.name, folder_id, path.stat().st_mtime)
                    self._set_virtual_folder_assignment(path, path.parent, project.get("name") or path.parent.name, folder_id)
                    updated += 1
                    touched.append(str(path))
                except Exception as e:
                    self._log_event("move_character_project_folder_failed", {"project": str(raw), "error": str(e)})
            return {"ok": True, "updated": updated, "projects": touched, "folderId": folder_id}
        except Exception as e:
            return {"ok": False, "error": f"Could not move selected characters: {e}"}

    def delete_character_project_directories(self, project_paths):
        """Delete local Character Card Forge export directories only. Front Porch DB entries are intentionally untouched."""
        deleted = 0
        failed = []
        try:
            folders = []
            for raw in project_paths or []:
                try:
                    path = self._project_path_inside_exports(raw)
                    folder = path.parent.resolve()
                    folder.relative_to(EXPORT_DIR.resolve())
                    if folder == EXPORT_DIR.resolve():
                        raise ValueError("Refusing to delete exports root.")
                    if folder not in folders:
                        folders.append(folder)
                except Exception as e:
                    failed.append({"project": str(raw), "error": str(e)})
            for folder in folders:
                try:
                    shutil.rmtree(folder)
                    deleted += 1
                except Exception as e:
                    failed.append({"folder": str(folder), "error": str(e)})
            return {"ok": True, "deleted": deleted, "failed": failed}
        except Exception as e:
            return {"ok": False, "error": f"Could not delete character directories: {e}"}

    def copy_to_clipboard(self, text):
        try:
            text = text or ""
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app is not None:
                    app.clipboard().setText(text)
                    return {"ok": True}
            except Exception:
                pass
            try:
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update()
                root.destroy()
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": f"Clipboard copy failed: {e}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def select_vision_image(self):
        try:
            window = webview.windows[0] if webview.windows else None
            if not window:
                return {"ok": False, "error": "No active window."}
            # Avoid Qt file filter errors by using an unfiltered picker.
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False
            )
            if not result:
                return {"ok": False, "cancelled": True}
            path = str(result[0] if isinstance(result, (list, tuple)) else result)
            if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                return {"ok": False, "error": "Please select a PNG, JPG, JPEG, or WebP image."}
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def analyze_vision_image(self, image_path, settings=None):
        self._reset_cancel()
        self._raise_if_cancelled()
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        image_path = (image_path or merged_settings.get("visionImagePath") or "").strip()
        if not image_path:
            return {"ok": False, "error": "Select an image first."}
        path = Path(image_path)
        if not path.exists():
            return {"ok": False, "error": f"Image not found: {image_path}"}
        vision_check = self._validate_vision_api_settings(merged_settings)
        if not vision_check.get("ok"):
            return vision_check
        base = (merged_settings.get("visionApiBaseUrl") or merged_settings.get("apiBaseUrl") or "").rstrip("/")
        key = merged_settings.get("visionApiKey") or merged_settings.get("apiKey") or ""
        model = merged_settings.get("visionModel") or ""
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        try:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            base_image_payload = {"mime": mime, "b64": b64, "bytes": len(raw), "label": "original", "optimized": False}
        except Exception as e:
            return {"ok": False, "error": f"Could not read image: {e}"}
        prompt = (
            "Describe the visible fictional character for an AI roleplay character card. "
            "Focus ONLY on character visual design: physical appearance, body shape, approximate breast/chest size if visible, face, hair, eyes, skin tone, visible distinguishing features, clothing, accessories, and fashion style. "
            "Do NOT include age/age appearance, expression, emotion, pose, posture, camera angle, setting, scene context, background, lighting, story context, pose symbolism, personality, or identity speculation. "
            "Do not identify the character or speculate about identity. "
            "Do not describe minors as sexualized; if age is unclear, avoid age entirely and describe only neutral visible adult-coded traits. "
            "If multiple characters are visible, give a separate concise subsection for each visible character. "
            "Output clean bullet points under the heading 'Visual Description'."
        )

        sfw_retry_prompt = (
            "The previous attempt may have refused because the reference image contained nudity or sexual context. "
            "For this retry, create a SAFE-FOR-WORK character visual-design description only. "
            "Describe ONLY the character's safe visual design: face, hair, eyes, skin tone, body type/silhouette, approximate bust/chest size in neutral non-explicit wording, distinguishing features, clothing, accessories, and fashion style. "
            "Do NOT include age/age appearance, expression, emotion, pose, posture, camera angle, setting, scene context, background, lighting, story context, personality, intimate context, or what the character is doing. "
            "Do not describe explicit sexual activity, nudity, genitals, nipples, intimate contact, arousal, or sexual positioning. "
            "Convert exposed or explicit elements into neutral SFW character-design wording. If clothing is minimal or absent, infer a modest non-explicit outfit/fashion style that fits the character design. "
            "Ignore the scene and any sexual context completely. "
            "If multiple characters are visible, give a separate concise SFW subsection for each visible character. "
            "Output clean bullet points under the heading 'Visual Description'."
        )

        def is_vision_refusal(text):
            lowered = (text or "").lower()
            refusal_bits = [
                "can't provide", "cannot provide", "i can’t provide", "i can't provide",
                "i need to decline", "must decline", "i can't help", "i cannot help",
                "sexual content", "explicit sexual", "intimate positioning", "nude/nearly-nude",
                "exposed breasts", "i'm happy to help describe appropriate", "sfw roleplay cards"
            ]
            return any(bit in lowered for bit in refusal_bits)

        def is_empty_vision_result(text):
            return not (text or "").strip()

        empty_retry_prompt = (
            prompt
            + "\n\nIMPORTANT: The previous vision response was empty. Do not return an empty response. "
            + "Return a concise safe visual character-design description only, with 5-12 bullet points under 'Visual Description'. "
            + "If any detail is uncertain, omit it rather than refusing or outputting blank text."
        )

        def clean_vision_description(text):
            banned_labels = (
                "age", "age appearance", "expression", "emotion", "pose", "posture",
                "setting", "setting context", "scene", "scene context", "background",
                "camera", "camera angle", "lighting", "story context", "context",
                "what she is doing", "what he is doing", "activity"
            )
            cleaned = []
            for line in (text or "").splitlines():
                raw = line.strip()
                if not raw:
                    cleaned.append(line)
                    continue
                normalized = raw.lstrip("-*•0123456789. )\t").strip()
                normalized = re.sub(r"^\*\*(.*?)\*\*\s*:?", r"\1:", normalized).strip()
                label = normalized.split(":", 1)[0].strip().lower() if ":" in normalized else ""
                if label and any(label == b or label.startswith(b + " ") for b in banned_labels):
                    continue
                lower = normalized.lower()
                if lower.startswith(("modern residential", "standing in", "sitting in", "natural daylight", "urban background", "doorway", "threshold")):
                    continue
                cleaned.append(line)
            result = "\n".join(cleaned).strip()
            result = re.sub(r"\n{3,}", "\n\n", result)
            return result or (text or "").strip()

        def build_smaller_vision_payload():
            max_dim = 1536
            target_max_bytes = 1800000
            with Image.open(path) as img:
                had_alpha = (img.mode in ("RGBA", "LA")) or (img.mode == "P" and "transparency" in getattr(img, "info", {}))
                if had_alpha:
                    rgba = img.convert("RGBA")
                    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    img = Image.alpha_composite(bg, rgba).convert("RGB")
                else:
                    img = img.convert("RGB")
                if max(img.size) > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
                chosen = None
                chosen_quality = None
                for quality in (88, 82, 76, 70, 62, 55):
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality, optimize=True)
                    data = buf.getvalue()
                    chosen = data
                    chosen_quality = quality
                    if len(data) <= target_max_bytes:
                        break
                if not chosen:
                    raise RuntimeError("Could not create a downsized vision image.")
                return {
                    "mime": "image/jpeg",
                    "b64": base64.b64encode(chosen).decode("ascii"),
                    "bytes": len(chosen),
                    "label": "downsized_jpeg",
                    "optimized": True,
                    "width": img.width,
                    "height": img.height,
                    "quality": chosen_quality,
                    "sourceHadAlpha": had_alpha,
                }

        def call_vision(prompt_text, attempt_label, image_payload=None):
            image_payload = image_payload or base_image_payload
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a precise visual description assistant for fictional AI character card creation. When asked for SFW output, safely transform visual references into neutral, non-explicit character-design descriptions."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:{image_payload['mime']};base64,{image_payload['b64']}"}}
                    ]}
                ],
                "temperature": 0.2,
                "max_tokens": 1800,
            }
            url = base + "/chat/completions"
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
            req.add_header("Content-Type", "application/json")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            self._log_event("vision_analyze_request", {
                "attempt": attempt_label,
                "image_path": str(path),
                "vision_base": base,
                "vision_model": model,
                "prompt": prompt_text,
                "image_payload": {
                    "label": image_payload.get("label", "original"),
                    "mime": image_payload.get("mime"),
                    "bytes": image_payload.get("bytes"),
                    "optimized": image_payload.get("optimized", False),
                    "width": image_payload.get("width"),
                    "height": image_payload.get("height"),
                    "quality": image_payload.get("quality"),
                }
            })
            try:
                with self._urlopen_with_retries(req, merged_settings, timeout=240, label="Vision analysis") as resp:
                    self._raise_if_cancelled()
                    data = json.loads(resp.read().decode("utf-8"))
                    self._raise_if_cancelled()
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code == 413 and not image_payload.get("optimized"):
                    resized_payload = build_smaller_vision_payload()
                    self._log_event("vision_analyze_payload_too_large", {
                        "status": e.code,
                        "body": body[:1000],
                        "original_bytes": image_payload.get("bytes"),
                        "retry_payload": {
                            "label": resized_payload.get("label"),
                            "mime": resized_payload.get("mime"),
                            "bytes": resized_payload.get("bytes"),
                            "width": resized_payload.get("width"),
                            "height": resized_payload.get("height"),
                            "quality": resized_payload.get("quality"),
                        }
                    })
                    return call_vision(prompt_text, attempt_label + "_downsized", resized_payload)
                raise RuntimeError(f"VISION_HTTP_{e.code}::{body[:4000]}")
            try:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                content = (content or "").strip()
                if not content:
                    fallback_content = (
                        message.get("text")
                        or message.get("response")
                        or data["choices"][0].get("text")
                        or ""
                    )
                    content = str(fallback_content or "").strip()
                if not content:
                    self._log_event("vision_analyze_empty_model_response", {
                        "attempt": attempt_label,
                        "finish_reason": data["choices"][0].get("finish_reason"),
                        "message_keys": list(message.keys()) if isinstance(message, dict) else [],
                    })
                return content
            except Exception:
                return json.dumps(data, indent=2, ensure_ascii=False)

        retry_used = False
        try:
            description = call_vision(prompt, "normal")
            if is_empty_vision_result(description):
                self._log_event("vision_analyze_empty_detected", {"attempt": "normal", "action": "retry_empty_safe_prompt"})
                self._raise_if_cancelled()
                retry_used = True
                description = call_vision(empty_retry_prompt, "empty_retry")
            if is_empty_vision_result(description):
                self._log_event("vision_analyze_empty_after_retry", {"action": "fail_with_clear_error"})
                return {"ok": False, "error": "Vision model returned an empty response twice. Try a different vision model, or enter the visual description manually."}
            if is_vision_refusal(description):
                self._log_event("vision_analyze_refusal_detected", {"description": description[:4000], "action": "retry_sfw"})
                self._raise_if_cancelled()
                retry_used = True
                description = call_vision(sfw_retry_prompt, "sfw_retry")
            if is_empty_vision_result(description):
                self._log_event("vision_analyze_empty_after_sfw_retry", {"action": "fail_with_clear_error"})
                return {"ok": False, "error": "Vision model returned an empty response after the SFW retry. Try a different vision model, less explicit crop, or enter the visual description manually."}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._log_event("vision_analyze_error", {"status": e.code, "body": body[:4000]})
            return {"ok": False, "error": f"Vision HTTP {e.code}: {body[:1000]}"}
        except Exception as e:
            msg = str(e)
            if msg.startswith("VISION_HTTP_"):
                try:
                    status, body = msg.split("::", 1)
                    code = status.replace("VISION_HTTP_", "")
                    self._log_event("vision_analyze_error", {"status": int(code), "body": body[:4000]})
                    return {"ok": False, "error": f"Vision HTTP {code}: {body[:1000]}"}
                except Exception:
                    pass
            self._log_event("vision_analyze_error", {"error": msg})
            return {"ok": False, "error": f"Vision analysis failed: {msg}"}

        if is_vision_refusal(description):
            self._log_event("vision_analyze_refusal_after_retry", {"description": description[:4000]})
            return {"ok": False, "error": "The vision model still refused after the SFW retry. Try a less explicit crop/reference image or enter a manual visual description."}

        raw_description = description
        description = clean_vision_description(description)
        if description != raw_description:
            self._log_event("vision_analyze_cleaned", {"removed_disallowed_context": True, "before": raw_description[:4000], "after": description[:4000]})
        if is_empty_vision_result(description):
            self._log_event("vision_analyze_empty_after_cleanup", {"raw_description": raw_description[:4000]})
            return {"ok": False, "error": "Vision analysis produced no usable description after cleanup. Try a different vision model or enter the visual description manually."}

        self._log_event("vision_analyze_response", {"retry_used": retry_used, "description": description})
        return {"ok": True, "description": description, "imagePath": str(path), "retryUsed": retry_used}

    def select_card_image(self):
        try:
            window = webview.windows[0] if webview.windows else None
            if not window:
                return {"ok": False, "error": "No active window."}
            # Avoid Qt file filter errors by using an unfiltered picker.
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False
            )
            if not result:
                return {"ok": False, "cancelled": True}
            path = str(result[0] if isinstance(result, (list, tuple)) else result)
            if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                return {"ok": False, "error": "Please select a PNG, JPG, JPEG, or WebP image."}
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def fetch_sd_models(self, settings=None):
        """Fetch available Stable Diffusion checkpoints from SD Forge / Automatic1111."""
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        base = (merged_settings.get("sdBaseUrl") or DEFAULT_SETTINGS["sdBaseUrl"]).rstrip("/")
        models_url = base + "/sdapi/v1/sd-models"
        options_url = base + "/sdapi/v1/options"
        try:
            req = urllib.request.Request(models_url, method="GET")
            with self._urlopen_with_retries(req, merged_settings, timeout=120, label="Stable Diffusion model list") as resp:
                models_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"Stable Diffusion HTTP {e.code}: {body[:1000]}"}
        except Exception as e:
            return {"ok": False, "error": f"Could not fetch Stable Diffusion models: {e}"}

        current_model = ""
        try:
            req = urllib.request.Request(options_url, method="GET")
            with self._urlopen_with_retries(req, merged_settings, timeout=120, label="Stable Diffusion options") as resp:
                options_data = json.loads(resp.read().decode("utf-8"))
            current_model = str(options_data.get("sd_model_checkpoint") or "").strip()
        except Exception:
            current_model = ""

        models = []
        seen = set()
        if isinstance(models_data, list):
            for item in models_data:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                model_name = str(item.get("model_name") or "").strip()
                sha = str(item.get("sha256") or item.get("hash") or "").strip()
                value = title or model_name
                if not value:
                    continue
                key = value.lower()
                if key in seen:
                    continue
                seen.add(key)
                display_name = title or model_name
                if model_name and title and model_name.lower() != title.lower():
                    display_name = f"{title} ({model_name})"
                models.append({
                    "value": value,
                    "title": title,
                    "modelName": model_name,
                    "sha": sha,
                    "displayName": display_name,
                    "current": bool(current_model and value == current_model),
                })

        selected = str(merged_settings.get("sdModel") or "").strip()
        return {"ok": True, "models": models, "currentModel": current_model, "selectedModel": selected}

    def _apply_sd_model_to_payload(self, payload, merged_settings):
        selected_model = str(merged_settings.get("sdModel") or "").strip()
        if selected_model:
            payload["override_settings"] = {"sd_model_checkpoint": selected_model}
            payload["override_settings_restore_afterwards"] = True
        return payload

    def generate_sd_images(self, output, settings=None):
        """Generate four 1024x1024 candidate card images from Stable Diffusion Prompt.

        Supports Automatic1111 / SD Forge compatible endpoints at /sdapi/v1/txt2img.
        The generated images are NOT embedded automatically. The user selects one,
        then Character Card V2 PNG export uses that selected image.
        """
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or paste a card first so I can read the Stable Diffusion Prompt section."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        prompts = self._extract_sd_prompts(output)
        if not prompts.get("positive"):
            return {"ok": False, "error": "No Positive Prompt found in the Stable Diffusion Prompt section."}
        base = (merged_settings.get("sdBaseUrl") or "http://127.0.0.1:7860").rstrip("/")
        url = base + "/sdapi/v1/txt2img"
        payload = {
            "prompt": prompts.get("positive", ""),
            "negative_prompt": prompts.get("negative", "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text"),
            "width": 1024,
            "height": 1024,
            "batch_size": 4,
            "n_iter": 1,
            "steps": int(float(merged_settings.get("sdSteps", 28) or 28)),
            "cfg_scale": float(merged_settings.get("sdCfgScale", 7.0) or 7.0),
        }
        sampler = (merged_settings.get("sdSampler") or "").strip()
        if sampler:
            payload["sampler_name"] = sampler
        payload = self._apply_sd_model_to_payload(payload, merged_settings)
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with self._urlopen_with_retries(req, merged_settings, timeout=600, label="Stable Diffusion generation") as resp:
                self._raise_if_cancelled()
                data = json.loads(resp.read().decode("utf-8"))
                self._raise_if_cancelled()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"Stable Diffusion HTTP {e.code}: {body[:1000]}"}
        except Exception as e:
            return {"ok": False, "error": f"Stable Diffusion generation failed: {e}"}
        images = data.get("images") or []
        if not images:
            return {"ok": False, "error": "Stable Diffusion returned no images."}
        safe_name = self._extract_name(output) or "character_card"
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", safe_name).strip("_") or "character_card"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        results = []
        for idx, b64 in enumerate(images[:4], start=1):
            if "," in b64 and b64.strip().lower().startswith("data:image"):
                b64 = b64.split(",", 1)[1]
            try:
                raw = base64.b64decode(b64)
                path = GENERATED_IMAGES_DIR / f"{safe}_{stamp}_{idx}.png"
                path.write_bytes(raw)
                results.append({
                    "path": str(path),
                    "dataUrl": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                })
            except Exception as e:
                return {"ok": False, "error": f"Could not save generated image {idx}: {e}"}
        return {"ok": True, "images": results, "prompt": prompts.get("positive", ""), "negativePrompt": prompts.get("negative", "")}

    def delete_generated_image(self, path):
        try:
            if not path:
                return {"ok": False, "error": "No image path supplied."}
            target = Path(path).resolve()
            allowed = GENERATED_IMAGES_DIR.resolve()
            if allowed not in target.parents and target != allowed:
                return {"ok": False, "error": "Refusing to delete an image outside the generated images folder."}
            if target.exists():
                target.unlink()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _extract_sd_prompts(self, output):
        section = self._clean_section_text(self._section(output, "Stable Diffusion Prompt"))
        positive = ""
        negative = ""
        if not section:
            return {"positive": "", "negative": ""}
        lines = section.splitlines()
        current = None
        bucket = {"positive": [], "negative": []}
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            m_pos = re.match(r"(?i)^[-*\s]*(?:positive\s+prompt|positive)\s*[:：]\s*(.*)$", line)
            m_neg = re.match(r"(?i)^[-*\s]*(?:negative\s+prompt|negative)\s*[:：]\s*(.*)$", line)
            if m_pos:
                current = "positive"
                if m_pos.group(1).strip():
                    bucket[current].append(m_pos.group(1).strip())
                continue
            if m_neg:
                current = "negative"
                if m_neg.group(1).strip():
                    bucket[current].append(m_neg.group(1).strip())
                continue
            if current:
                bucket[current].append(line)
        positive = " ".join(bucket["positive"]).strip()
        negative = " ".join(bucket["negative"]).strip()
        # Fallback: if the model put only raw comma tags in the section, treat all
        # non-negative-looking text as the positive prompt.
        if not positive:
            positive = re.sub(r"(?is)negative\s+prompt\s*:.*$", "", section).strip()
        if not negative:
            m = re.search(r"(?is)negative\s+prompt\s*[:：]\s*(.+)$", section)
            if m:
                negative = m.group(1).strip()
        return {"positive": positive, "negative": negative}

    def _strip_stable_diffusion_for_card(self, output):
        """Keep raw card useful but do not embed SD prompt text in card PNG/JSON."""
        lines = []
        current = None
        for line in (output or "").splitlines():
            heading = self._canonical_heading(line)
            if heading:
                current = heading
            if current == "stable_diffusion":
                continue
            lines.append(line)
        return self._clean_section_text("\n".join(lines))

    def _safe_slug(self, value):
        value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "character_card")).strip("_")
        return value or "character_card"

    def _character_export_dir(self, name):
        safe = self._safe_slug(name)
        folder = EXPORT_DIR / safe
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _extract_emotion_images_dir(self, name):
        return self._character_export_dir(name)

    def _extract_character_visual_baseline(self, output):
        prompts = self._extract_sd_prompts(output)
        positive = prompts.get("positive", "").strip()
        negative = prompts.get("negative", "").strip()
        if positive:
            return {"positive": positive, "negative": negative}
        description = self._clean_section_text(self._section(output, "Description"))
        scenario = self._clean_section_text(self._section(output, "Scenario"))
        name = self._extract_name(output)
        base = f"1girl, solo, anime style, portrait, {name}, {description}".strip()
        if scenario:
            base += ", inspired by: " + scenario[:300]
        return {"positive": base, "negative": "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text"}

    def _emotion_positive_fallback(self, base_positive, emotion):
        emotion_phrases = {
            "admiration": "admiring expression, soft smile, bright attentive eyes",
            "affection": "affectionate expression, gentle smile, tender eyes",
            "amusement": "amused smile, playful eyes, light laughter",
            "anger": "angry expression, furrowed brows, tense posture",
            "annoyance": "annoyed expression, narrowed eyes, slight frown",
            "anticipation": "anticipatory expression, expectant gaze, poised posture",
            "approval": "approving expression, satisfied smile, warm eyes",
            "caring": "caring expression, gentle smile, compassionate eyes",
            "confusion": "confused expression, tilted head, uncertain eyes",
            "curiosity": "curious expression, inquisitive eyes, slight head tilt",
            "desire": "desiring expression, half-lidded eyes, flushed cheeks",
            "disappointment": "disappointed expression, downcast eyes, subdued posture",
            "disapproval": "disapproving expression, stern eyes, restrained frown",
            "disgust": "disgusted expression, wrinkled nose, recoiling posture",
            "embarrassment": "embarrassed expression, blushing cheeks, shy eyes",
            "excitement": "excited expression, wide sparkling eyes, energetic pose",
            "fear": "fearful expression, wide eyes, tense posture",
            "gratitude": "grateful expression, soft smile, relieved eyes",
            "grief": "grieving expression, tearful eyes, sorrowful posture",
            "joy": "joyful expression, bright smile, sparkling eyes",
            "love": "loving expression, warm smile, affectionate eyes",
            "nervousness": "nervous expression, hesitant smile, tense shoulders",
            "optimism": "optimistic expression, hopeful smile, confident eyes",
            "pride": "proud expression, confident smile, lifted chin",
            "realization": "realization expression, widened eyes, thoughtful look",
            "relief": "relieved expression, softened smile, relaxed shoulders",
            "remorse": "remorseful expression, apologetic eyes, lowered gaze",
            "sadness": "sad expression, tearful eyes, downcast gaze",
            "surprise": "surprised expression, widened eyes, parted lips",
            "neutral": "neutral expression, calm eyes, relaxed posture",
        }
        extra = emotion_phrases.get(emotion, f"{emotion} expression")
        return f"{base_positive}, {extra}, same character design, same outfit, same hairstyle, same overall visual style, solo portrait".strip(', ')

    def _generate_emotion_prompts_via_llm(self, output, emotions, settings):
        base = self._extract_character_visual_baseline(output)
        prompt = "\n".join([
            "You generate Stable Diffusion prompts for character emotion portraits.",
            "Return strict JSON only. No markdown. No commentary.",
            "For each requested emotion, return an object with keys positive and negative.",
            "Preserve the exact same character identity, hairstyle, clothing, body type, age, and visual style across every prompt.",
            "Only vary facial expression, body language, and subtle pose cues to match the emotion.",
            "Each positive prompt must be suitable for anime-style txt2img portrait generation at 1024x1024.",
            f"Character name: {self._extract_name(output)}",
            f"Base positive prompt: {base.get('positive','')}",
            f"Base negative prompt: {base.get('negative','')}",
            f"Requested emotions: {', '.join(emotions)}",
            "Return format example:",
            '{"joy": {"positive": "...", "negative": "..."}, "sadness": {"positive": "...", "negative": "..."}}'
        ])
        check = self._context_check(prompt, settings, mode_label="Emotion prompt generation")
        if not check.get("ok"):
            raise RuntimeError(check.get("error", "Emotion prompt generation exceeds context window."))
        raw = self._chat(prompt, settings)
        raw = raw.strip()
        m = re.search(r"\{[\s\S]*\}$", raw)
        if m:
            raw = m.group(0)
        data = json.loads(raw)
        out = {}
        for emo in emotions:
            item = data.get(emo, {}) if isinstance(data, dict) else {}
            pos = str(item.get("positive", "")).strip()
            neg = str(item.get("negative", "")).strip()
            if not pos:
                pos = self._emotion_positive_fallback(base.get("positive", ""), emo)
            if not neg:
                neg = base.get("negative", "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text")
            out[emo] = {"positive": pos, "negative": neg}
        return out

    def _build_emotion_prompts(self, output, emotions, settings):
        base = self._extract_character_visual_baseline(output)
        try:
            return self._generate_emotion_prompts_via_llm(output, emotions, settings)
        except Exception:
            prompts = {}
            for emo in emotions:
                prompts[emo] = {
                    "positive": self._emotion_positive_fallback(base.get("positive", ""), emo),
                    "negative": base.get("negative", "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text"),
                }
            return prompts

    def _generate_sd_single_image(self, prompt, negative_prompt, settings, emotion_label="image"):
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        base = (merged_settings.get("sdBaseUrl") or "http://127.0.0.1:7860").rstrip("/")
        url = base + "/sdapi/v1/txt2img"
        payload = {
            "prompt": prompt or "",
            "negative_prompt": negative_prompt or "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text",
            "width": 1024,
            "height": 1024,
            "batch_size": 1,
            "n_iter": 1,
            "steps": int(float(merged_settings.get("sdSteps", 28) or 28)),
            "cfg_scale": float(merged_settings.get("sdCfgScale", 7.0) or 7.0),
        }
        sampler = (merged_settings.get("sdSampler") or "").strip()
        if sampler:
            payload["sampler_name"] = sampler
        payload = self._apply_sd_model_to_payload(payload, merged_settings)
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with self._urlopen_with_retries(req, merged_settings, timeout=600, label="Stable Diffusion generation") as resp:
                self._raise_if_cancelled()
                data = json.loads(resp.read().decode("utf-8"))
                self._raise_if_cancelled()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Stable Diffusion HTTP {e.code} while generating {emotion_label}: {body[:1000]}")
        except Exception as e:
            raise RuntimeError(f"Stable Diffusion generation failed for {emotion_label}: {e}")
        images = data.get("images") or []
        if not images:
            raise RuntimeError(f"Stable Diffusion returned no image for '{emotion_label}'.")
        b64 = images[0]
        if "," in b64 and b64.strip().lower().startswith("data:image"):
            b64 = b64.split(",", 1)[1]
        return base64.b64decode(b64)

    def generate_emotion_images(self, output, emotions=None, settings=None):
        self._reset_cancel()
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or paste a card first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        emotions = emotions or merged_settings.get("emotionImageEmotions") or []
        emotions = [e for e in emotions if e in EMOTION_OPTIONS]
        if not emotions:
            return {"ok": False, "error": "Select at least one emotion first."}
        prompts = self._build_emotion_prompts(output, emotions, merged_settings)
        base = (merged_settings.get("sdBaseUrl") or "http://127.0.0.1:7860").rstrip("/")
        url = base + "/sdapi/v1/txt2img"
        name = self._extract_name(output) or "character_card"
        folder = self._extract_emotion_images_dir(name)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        results = []
        prompt_manifest = {}
        for emo in emotions:
            self._raise_if_cancelled()
            emo_prompts = prompts.get(emo, {})
            prompt_manifest[emo] = emo_prompts
            try:
                raw = self._generate_sd_single_image(
                    emo_prompts.get("positive", ""),
                    emo_prompts.get("negative", "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text"),
                    merged_settings,
                    emo,
                )
            except Exception as e:
                return {"ok": False, "error": str(e)}
            file_path = folder / f"{emo}.png"
            file_path.write_bytes(raw)
            results.append({
                "emotion": emo,
                "path": str(file_path),
                "dataUrl": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                "prompt": emo_prompts.get("positive", ""),
                "negativePrompt": emo_prompts.get("negative", ""),
            })
        manifest_path = folder / f"emotion_prompts_{stamp}.json"
        manifest_path.write_text(json.dumps(prompt_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "images": results, "folder": str(folder), "manifest": str(manifest_path)}

    def regenerate_emotion_image(self, output, emotion, prompt, negative_prompt="", settings=None):
        self._reset_cancel()
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or paste a card first."}
        emotion = (emotion or "").strip().lower()
        if emotion not in EMOTION_OPTIONS:
            return {"ok": False, "error": f"Unsupported emotion: {emotion}"}
        if not (prompt or "").strip():
            return {"ok": False, "error": "Prompt is empty."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        name = self._extract_name(output) or "character_card"
        folder = self._extract_emotion_images_dir(name)
        try:
            raw = self._generate_sd_single_image(prompt, negative_prompt, merged_settings, emotion)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        path = folder / f"{emotion}.png"
        path.write_bytes(raw)
        return {
            "ok": True,
            "image": {
                "emotion": emotion,
                "path": str(path),
                "dataUrl": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                "prompt": prompt,
                "negativePrompt": negative_prompt or "",
            },
            "folder": str(folder),
        }

    def create_emotion_zip(self, output):
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or load a card first."}
        name = self._extract_name(output) or "character_card"
        folder = self._extract_emotion_images_dir(name)
        files = []
        for emo in EMOTION_OPTIONS:
            path = folder / f"{emo}.png"
            if path.exists():
                files.append((emo, path))
        if not files:
            return {"ok": False, "error": "No emotion images found to zip."}
        zip_path = folder / "front_porch_emotion_images.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for emo, path in files:
                    zf.write(path, arcname=f"{emo}.png")
            return {"ok": True, "path": str(zip_path), "folder": str(folder), "count": len(files)}
        except Exception as e:
            return {"ok": False, "error": f"Could not create emotion image zip: {e}"}


    def _front_porch_paths(self, settings=None):
        # Current UI settings should win over old saved workspace settings.
        settings = self._normalise_settings({**(settings or {}), **self.settings})
        raw_root = str(settings.get("frontPorchDataFolder") or "").strip().strip('"').strip("'")
        if not raw_root:
            return None, None, "Front Porch Data Folder is not set. Set it in AI Settings first."
        root = Path(raw_root).expanduser()
        candidates = []

        def add_candidate(path):
            path = Path(path).expanduser()
            if path not in candidates:
                candidates.append(path)

        # Accept selecting the database file itself.
        if root.suffix.lower() == ".db":
            db = root
            if db.exists() and db.name in {"front_porch_beta.db", "front_porch.db"}:
                return db.parent, db, ""
            add_candidate(root.parent)

        # User normally selects the Front Porch data folder, which contains KoboldManager.
        add_candidate(root / "KoboldManager")
        # Also support selecting KoboldManager directly.
        add_candidate(root)
        # A few systems may expose the data root one level up/down or via a symlink.
        add_candidate(root.resolve() / "KoboldManager" if root.exists() else root / "KoboldManager")
        add_candidate(root.resolve() if root.exists() else root)

        checked = []
        for km in candidates:
            if not km.exists() or not km.is_dir():
                checked.append(str(km))
                continue
            dbs = [km / "front_porch_beta.db", km / "front_porch.db"]
            checked.extend(str(p) for p in dbs)
            db = next((p for p in dbs if p.exists()), None)
            if db:
                return km, db, ""
        self._log_event("front_porch_scan_not_found", {"raw_root": raw_root, "checked": checked[:20]})
        return None, None, "Could not find front_porch_beta.db or front_porch.db. Set Front Porch Data Folder to the folder shown in Front Porch → Settings, or select the KoboldManager folder/database directly. Checked: " + "; ".join(checked[:6])

    def scan_front_porch_folder(self, settings=None):
        km, db, err = self._front_porch_paths(settings)
        if err:
            return {"ok": False, "error": err}
        try:
            con = sqlite3.connect(str(db))
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            con.close()
            needed = {"characters", "avatar_images"}
            missing = sorted(needed - tables)
            if missing:
                return {"ok": False, "error": f"Front Porch database found, but required table(s) are missing: {', '.join(missing)}"}
            return {"ok": True, "koboldManager": str(km), "database": str(db), "charactersDir": str(km / "Characters"), "databaseName": db.name}
        except Exception as e:
            return {"ok": False, "error": f"Could not inspect Front Porch database: {e}"}

    def _safe_front_porch_character_folder(self, name):
        """Match Front Porch AI's character/avatar directory slug.

        Front Porch stores a character card PNG directly under Characters/, but
        extra/avatar emotion images live under Characters/<safe name>/avatars/.
        Its own add-avatar path sanitizes the character name by removing
        everything except word chars, whitespace, and hyphens, then replacing
        spaces with underscores. Keeping this identical is important because the
        avatar_images table stores only the image filename, not a full path.
        """
        safe = re.sub(r"[^\w\s-]+", "", str(name or "Character"), flags=re.UNICODE)
        safe = safe.replace(" ", "_").strip("_")
        return safe or "Character"

    def _front_porch_avatar_dir(self, chars_dir, name):
        return Path(chars_dir) / self._safe_front_porch_character_folder(name) / "avatars"

    def _json_for_db(self, value, default):
        if value is None:
            return json.dumps(default, ensure_ascii=False)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return json.dumps(default, ensure_ascii=False)
            try:
                json.loads(s)
                return s
            except Exception:
                return json.dumps(value, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)

    def export_to_front_porch(self, output, image_path=None, settings=None, project_path=None):
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or load a character first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        km, db, err = self._front_porch_paths(merged_settings)
        if err:
            return {"ok": False, "error": err}
        chars_dir = km / "Characters"
        chars_dir.mkdir(parents=True, exist_ok=True)
        name = self._extract_name(output) or "Character Card"
        safe = self._safe_front_porch_character_folder(name)
        now = int(time.time())
        ms = int(time.time() * 1000)
        char_id = f"{safe}_{ms}"
        card_v2 = self._to_chara_card_v2(output, name)
        data = card_v2.get("data", {})
        image_filename = f"{safe}_{ms}.png"
        image_dest = chars_dir / image_filename
        try:
            self._write_chara_png(image_dest, card_v2, image_path)
        except Exception as e:
            return {"ok": False, "error": f"Could not write Front Porch character card PNG: {e}"}

        # Backup DB before direct write. SQLite writes are small, but this makes the feature less scary.
        try:
            backup_path = db.with_suffix(db.suffix + f".ccf_backup_{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(db, backup_path)
        except Exception as e:
            return {"ok": False, "error": f"Could not create database backup before export: {e}"}

        lorebook = data.get("character_book") or {"entries": []}
        tags = data.get("tags") or []
        alt = data.get("alternate_greetings") or []
        fp = (((data.get("extensions") or {}).get("front_porch") or {}).get("realism_engine") or {})
        desc = data.get("description", "") or ""
        personality = data.get("personality", "") or ""
        scenario = data.get("scenario", "") or ""
        first_mes = data.get("first_mes", "") or ""
        mes_example = data.get("mes_example", "") or ""
        system_prompt = data.get("system_prompt", "") or ""
        post = data.get("post_history_instructions", "") or ""
        try:
            con = sqlite3.connect(str(db))
            cur = con.cursor()
            cur.execute("""
                INSERT INTO characters (
                    id, name, description, personality, scenario, first_message, mes_example,
                    system_prompt, post_history_instructions, alternate_greetings, tags, image_path,
                    tts_voice, folder_id, lorebook, world_names, memory_sources, evolved_personality,
                    evolved_scenario, evolution_count, created_at, updated_at, deleted_at, prime_avatar_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, '[]', '[]', '', '', 0, ?, ?, NULL, 1)
            """, (
                char_id, name, desc, personality, scenario, first_mes, mes_example,
                system_prompt, post, json.dumps(alt, ensure_ascii=False), json.dumps(tags, ensure_ascii=False), image_filename,
                json.dumps(lorebook, ensure_ascii=False), now, now
            ))
            session_id = str(ms + 1)
            cur.execute("""
                INSERT INTO sessions (
                    id, character_id, group_id, name, description, author_note, author_note_depth,
                    summary, summary_last_index, parent_session, fork_index, affection_score, relationship_tier,
                    long_term_score, long_term_tier, turns_since_long_term_check, short_term_deltas_summary,
                    realism_enabled, short_term_mood, mood_decay_counter, character_emotion, emotion_intensity,
                    time_of_day, day_count, nsfw_cooldown_enabled, passage_of_time_enabled, arousal_level,
                    cooldown_turns_remaining, trust_level, active_fixation, fixation_lifespan, spatial_stance,
                    trust_repair_pending, chaos_mode_enabled, chaos_pressure, evolved_personality, evolved_scenario,
                    evolution_count, group_evolved_personalities, group_evolved_scenarios, generation_settings,
                    created_at, updated_at, deleted_at, user_persona_id
                ) VALUES (?, ?, NULL, NULL, NULL, '', 4, NULL, NULL, NULL, NULL, ?, 0, ?, 0, 0, 0, ?, 0, 0, ?, ?, ?, ?, ?, ?, 0, 0, ?, '', 0, '', 0, ?, 0, '', '', 0, '{}', '{}', NULL, ?, ?, NULL, NULL)
            """, (
                session_id, char_id,
                int(fp.get("short_term_bond") or 0), int(fp.get("long_term_bond") or 0),
                1 if fp.get("enabled", True) else 0,
                str(fp.get("character_emotion") or ""), str(fp.get("emotion_intensity") or ""),
                str(fp.get("time_of_day") or "morning"), int(fp.get("day_count") or 1),
                1 if fp.get("nsfw_cooldown_enabled", True) else 0,
                1 if fp.get("passage_of_time_enabled", True) else 0,
                int(fp.get("trust_level") or 0),
                1 if fp.get("chaos_mode_enabled", True) else 0,
                now, now
            ))
            if first_mes:
                cur.execute("""
                    INSERT INTO messages (id, session_id, position, sender, is_user, character_id, swipes, swipe_index, swipe_durations, metadata, swipe_metadata, updated_at, deleted_at)
                    VALUES (?, ?, 0, ?, 0, NULL, ?, 0, '[0]', NULL, NULL, ?, NULL)
                """, (str(uuid.uuid4()), session_id, name, json.dumps([first_mes], ensure_ascii=False), now))

            # Copy emotion/avatar images from the project/export folder and register them.
            # Front Porch resolves avatar_images.filename relative to:
            #   Characters/<safe character name>/avatars/<filename>
            # The DB row must therefore contain only the basename, while the
            # physical file must be in the avatars subfolder.
            emotion_count = 0
            source_folders = []
            if project_path:
                source_folders.append(Path(project_path).parent)
            # Usual CCF location is exports/<name>/<emotion>.png.
            source_folders.append(self._character_export_dir(name))
            char_emotion_dir = self._front_porch_avatar_dir(chars_dir, name)
            char_emotion_dir.mkdir(parents=True, exist_ok=True)
            for emo_i, emo in enumerate(EMOTION_OPTIONS):
                src = next((folder / f"{emo}.png" for folder in source_folders if folder and (folder / f"{emo}.png").exists()), None)
                if not src:
                    continue
                avatar_file = f"avatar_{ms + emotion_count}.png"
                shutil.copy2(src, char_emotion_dir / avatar_file)
                cur.execute("INSERT INTO avatar_images (id, character_id, filename, label, display_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), char_id, avatar_file, emo, emotion_count, now))
                emotion_count += 1
            cur.execute("UPDATE sync_meta SET version = version + 1, last_modified_at = ? WHERE id = 1", (now,))
            con.commit()
            con.close()
            self._log_event("front_porch_export", {"name": name, "id": char_id, "db": str(db), "image": image_filename, "emotions": emotion_count, "avatarDir": str(char_emotion_dir), "backup": str(backup_path)})
            return {"ok": True, "name": name, "characterId": char_id, "database": str(db), "cardImage": str(image_dest), "emotionImages": emotion_count, "avatarDir": str(char_emotion_dir), "backup": str(backup_path)}
        except Exception as e:
            try:
                con.rollback(); con.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Front Porch export failed: {e}. Database backup was created at: {backup_path}"}

    def export_front_porch_from_project(self, project_path):
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            return loaded
        # Current app settings win over the older settings saved inside the character workspace,
        # otherwise a saved project with a blank Front Porch folder can mask the value the user just entered.
        settings = {**(loaded.get("settings") or {}), **self.settings}
        return self.export_to_front_porch(loaded.get("output") or "", loaded.get("imagePath") or loaded.get("settings", {}).get("cardImagePath") or "", settings, project_path)

    def export_card(self, output, frontend=None, export_format=None, image_path=None, concept="", template=None, settings=None):
        if not output or not output.strip():
            return {"ok": False, "error": "Nothing to export."}
        frontend = "front_porch"
        export_format = export_format or "chara_v2_png"
        if export_format == "frontend_json":
            export_format = "chara_v2_json"
        safe_name = self._extract_name(output) or "character_card"
        safe = self._safe_slug(safe_name)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        export_folder = self._character_export_dir(safe_name)
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        template = template or self.template

        if export_format == "chara_v2_png":
            payload = self._to_chara_card_v2(output, safe_name)
            path = export_folder / f"{safe}_{stamp}_cardv2.png"
            self._write_chara_png(path, payload, image_path)
        elif export_format == "chara_v2_json":
            payload = self._to_chara_card_v2(output, safe_name)
            path = export_folder / f"{safe}_{stamp}_cardv2.json"
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        elif export_format == "frontend_json":
            payload = self._to_frontend_json(output, safe_name, frontend)
            path = export_folder / f"{safe}_{stamp}_{frontend}.json"
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            path = export_folder / f"{safe}_{stamp}.md"
            path.write_text(output, encoding="utf-8")

        project_path = self._write_project_bundle(export_folder, safe_name, stamp, output, concept, template, merged_settings, image_path, path, frontend, export_format)
        return {"ok": True, "path": str(path), "folder": str(export_folder), "projectPath": str(project_path)}

    def _extract_name(self, text):
        m = re.search(r"(?im)^Name\s*\n+([^\n#]+)", text)
        if m:
            return m.group(1).strip()[:80]
        m = re.search(r"(?im)^Name\s*[:\-]\s*(.+)$", text)
        if m:
            return m.group(1).strip()[:80]
        return "Character Card"

    def _canonical_heading(self, line):
        """Return a canonical section id if a line is a top-level card heading.

        The model may omit divider lines or put blank sections directly next to
        the next heading. Regex-only extraction was too greedy in those cases,
        especially for First Message, Custom System Prompt, and State Tracking.
        This scanner treats headings as hard boundaries before export.
        """
        raw = (line or "").strip()
        if not raw:
            return None
        if re.fullmatch(r"[-—_]{3,}", raw):
            return None

        cleaned = raw.strip()
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
        cleaned = cleaned.strip(" *`_")
        cleaned = re.sub(r"\s*[:：]\s*$", "", cleaned).strip()
        cleaned_key = re.sub(r"\s+", " ", cleaned).lower()
        cleaned_key = cleaned_key.strip("- ")

        aliases = {
            "name": "name",
            "description": "description",
            "personality": "personality",
            "sexual traits": "sexual_traits",
            "background": "background",
            "scenario": "scenario",
            "first message": "first_message",
            "alternative first messages": "alternate_first_messages",
            "alternate first messages": "alternate_first_messages",
            "additional first messages": "alternate_first_messages",
            "alternative first greetings": "alternate_first_messages",
            "alternate first greetings": "alternate_first_messages",
            "additional first greetings": "alternate_first_messages",
            "example dialogues": "example_dialogues",
            "example dialogue": "example_dialogues",
            "lorebook entries": "lorebook",
            "lorebook": "lorebook",
            "tags": "tags",
            "custom system prompt": "system_prompt",
            "system prompt": "system_prompt",
            "state tracking": "state_tracking",
            "stable diffusion prompt": "stable_diffusion",
            "stable diffusion": "stable_diffusion",
            "creator notes": "creator_notes",
            "creator note": "creator_notes",
            "post history instructions": "post_history_instructions",
            "post-history instructions": "post_history_instructions",
        }
        if cleaned_key in aliases:
            return aliases[cleaned_key]
        if re.fullmatch(r"-+\s*state tracking\s*-+", cleaned_key):
            return "state_tracking"
        return None

    def _is_divider_line(self, line):
        return bool(re.fullmatch(r"\s*[-—_]{3,}\s*", line or ""))

    def _clean_section_text(self, value):
        """Remove prompt divider lines and tidy section bodies for export."""
        cleaned = []
        for line in (value or "").splitlines():
            if self._is_divider_line(line):
                continue
            cleaned.append(line.rstrip())
        return "\n".join(cleaned).strip()

    def _parse_sections(self, text, template=None):
        sections = {}
        current = None
        for line in (text or "").splitlines():
            if self._is_divider_line(line):
                continue
            heading = self._canonical_heading_with_template(line, template)
            if heading:
                current = heading
                sections.setdefault(current, [])
                continue
            if current:
                sections[current].append(line)
        return {k: self._clean_section_text("\n".join(v)) for k, v in sections.items()}

    def _section(self, text, title):
        title_key = self._canonical_heading(title) or re.sub(r"\s+", "_", title.strip().lower())
        return self._parse_sections(text).get(title_key, "").strip()

    def _clean_blank_system_prompt(self, value):
        value = (value or "").strip()
        if not value:
            return ""
        if re.fullmatch(r"(?is)(?:leave blank|blank|none|n/a|not required|no special behavioral rules required|no special rules required)[.\s]*", value):
            return ""
        # Safety: if a model accidentally put later sections here, trim them.
        for marker in ["State Tracking", "--- STATE TRACKING ---", "Stable Diffusion Prompt"]:
            idx = value.lower().find(marker.lower())
            if idx > 0:
                value = value[:idx].strip()
        return value

    def _split_keys(self, key_text):
        raw = (key_text or "").strip()
        if not raw:
            return []
        parts = []
        for piece in re.split(r"[,;|/]+", raw):
            piece = piece.strip()
            if piece:
                parts.append(piece)
        return parts or [raw]

    def _parse_lorebook_entries(self, value):
        """Parse the generated Lorebook Entries section into Character Card book entries.

        Supported model output styles:
        - Key: keyword1, keyword2 / Value: content
        - Name: Entry Name / Key: keyword1, keyword2 / Content: content
        - Entry Name\nKey: ...\nValue: ...
        """
        value = self._clean_section_text(value)
        if not value:
            return []

        entries = []
        current = None
        pending_label = None

        def flush():
            nonlocal current
            if not current:
                return
            key_text = (current.get("key") or current.get("name") or "").strip()
            content = (current.get("content") or "").strip()
            if not key_text or not content:
                current = None
                return
            keys = self._split_keys(key_text)
            name = (current.get("name") or "").strip()
            if not name:
                # Use the first keyword as a human-readable entry name. This matches
                # how Front Porch/SillyTavern cards commonly display lorebook entries.
                name = keys[0].strip() if keys else key_text
            entries.append({
                "name": name,
                "key": key_text,
                "keys": keys,
                "content": content,
                "enabled": True,
                "constant": False,
                "sticky_depth": 1,
            })
            current = None

        lines = value.splitlines()
        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            m = re.match(r"^(Name|Entry|Title)\s*:\s*(.+)$", stripped, flags=re.I)
            if m:
                if current and current.get("content"):
                    flush()
                current = current or {}
                current["name"] = m.group(2).strip()
                pending_label = "name"
                continue
            m = re.match(r"^(Key|Keys|Keywords)\s*:\s*(.+)$", stripped, flags=re.I)
            if m:
                if current and current.get("content"):
                    flush()
                current = current or {}
                current["key"] = m.group(2).strip()
                pending_label = "key"
                continue
            m = re.match(r"^(Value|Content|Description)\s*:\s*(.+)$", stripped, flags=re.I)
            if m:
                current = current or {}
                current["content"] = (current.get("content", "") + ("\n" if current.get("content") else "") + m.group(2).strip()).strip()
                pending_label = "content"
                continue

            # A standalone title immediately before Key/Value blocks.
            if current is None:
                current = {"name": stripped}
                pending_label = "name"
            elif pending_label == "content":
                current["content"] = (current.get("content", "") + "\n" + stripped).strip()
            elif current.get("key") and not current.get("content"):
                current["content"] = stripped
                pending_label = "content"
            else:
                # Prefer preserving text rather than dropping it; append to content
                # if we already have a key, otherwise treat it as the entry name.
                if current.get("key"):
                    current["content"] = (current.get("content", "") + "\n" + stripped).strip()
                    pending_label = "content"
                else:
                    current["name"] = (current.get("name", "") + " " + stripped).strip()
                    pending_label = "name"

        flush()
        return entries

    def _parse_int_value(self, value, default=0):
        if value is None:
            return default
        m = re.search(r"-?\d+", str(value))
        if not m:
            return default
        try:
            return int(m.group(0))
        except Exception:
            return default

    def _parse_state_tracking_map(self, value):
        state = {}
        for raw_line in self._clean_section_text(value).splitlines():
            line = raw_line.strip().lstrip("-•*").strip()
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = re.sub(r"\s+", "_", key.strip().lower())
            key = key.replace("starting_emotion", "character_emotion")
            key = key.replace("current_objective", "current_task")
            state[key] = val.strip()
        return state

    def _front_porch_realism_engine(self, state_tracking):
        state = self._parse_state_tracking_map(state_tracking)
        time_of_day = (state.get("time_of_day") or "afternoon").strip().lower()
        emotion_intensity = (state.get("emotion_intensity") or "moderate").strip().lower()
        return {
            "enabled": True,
            "short_term_bond": self._parse_int_value(state.get("short_term_bond"), 0),
            "long_term_bond": self._parse_int_value(state.get("long_term_bond"), 0),
            "trust_level": self._parse_int_value(state.get("trust_level"), 0),
            "day_count": self._parse_int_value(state.get("day_number"), 1),
            "time_of_day": time_of_day,
            "character_emotion": state.get("character_emotion") or "Neutral",
            "emotion_intensity": emotion_intensity,
            "nsfw_cooldown_enabled": True,
            "passage_of_time_enabled": True,
            "chaos_mode_enabled": True,
            "current_task": state.get("current_task") or "Interact with {{user}} in character.",
        }

    def _normalize_example_dialogues_for_front_porch(self, value):
        """Front Porch AI expects one <START> marker for the mes_example field.

        Some models naturally emit one <START> per mini-example. That imports
        badly, so collapse any extra markers into a single continuous sample
        conversation while preserving the speaker lines.
        """
        text = self._clean_section_text(value or "")
        if not text:
            return ""
        parts = re.split(r"(?i)<START>", text)
        # Text before the first marker can contain accidental headings/notes.
        leading = parts[0].strip()
        examples = [p.strip() for p in parts[1:] if p.strip()]
        if not examples:
            body = leading
        else:
            body_parts = []
            if leading and not re.fullmatch(r"[-—_\s]+", leading):
                body_parts.append(leading)
            body_parts.extend(examples)
            body = "\n\n".join(body_parts).strip()
        if not body:
            return "<START>"
        # Remove any nested accidental markers that survived parsing.
        body = re.sub(r"(?i)<START>", "", body).strip()
        return "<START>\n" + body

    def _to_chara_card_v2(self, output, name):
        template = self.template or DEFAULT_TEMPLATE
        parsed = self._parse_sections(output or "", template)

        def sec_by_id(sid, title):
            return self._clean_section_text(parsed.get(sid, "") or self._section(output, title))

        description_base = sec_by_id("description", "Description")
        personality_core = sec_by_id("personality", "Personality")
        sexual_traits = sec_by_id("sexual_traits", "Sexual Traits")
        background = sec_by_id("background", "Background")
        scenario = sec_by_id("scenario", "Scenario")
        first_mes = self._strip_embedded_sections(sec_by_id("first_message", "First Message"))
        mes_example = self._normalize_example_dialogues_for_front_porch(sec_by_id("example_dialogues", "Example Dialogues"))
        system_prompt = self._clean_blank_system_prompt(sec_by_id("system_prompt", "Custom System Prompt"))
        state_tracking = sec_by_id("state_tracking", "State Tracking")
        stable_diffusion = sec_by_id("stable_diffusion", "Stable Diffusion Prompt")
        lorebook_entries = self._parse_lorebook_entries(sec_by_id("lorebook", "Lorebook Entries"))
        front_porch_realism_engine = self._front_porch_realism_engine(state_tracking)
        tags = [t.strip() for t in sec_by_id("tags", "Tags").replace("\n", ",").split(",") if t.strip()]

        # New tabbed template model: every enabled section assigned to the
        # Description tab is folded into the Chara V2 data.description field;
        # every enabled section assigned to the Personality tab is folded into
        # data.personality. This keeps custom Description/Personality sections
        # visible in normal card imports instead of hiding them in extensions.
        description_parts = []
        if description_base:
            description_parts.append(description_base)
        personality_parts = []
        if personality_core:
            personality_parts.append(personality_core)

        extension_sections = {}
        core_ids = {"name", "description", "personality", "scenario", "first_message", "alternate_first_messages", "example_dialogues", "lorebook", "tags", "system_prompt", "state_tracking", "stable_diffusion"}
        for section in template.get("sections", []):
            if not section.get("enabled", True):
                continue
            sid = section.get("id", "")
            title = section.get("title", sid.replace("_", " ").title())
            body = self._clean_section_text(parsed.get(sid, ""))
            if not body:
                continue
            category = self._template_section_category(section)
            if category == "description" and sid != "description":
                description_parts.append(f"{title}\n{body}")
                extension_sections[sid] = {"title": title, "category": category, "content": body}
            elif category == "personality" and sid != "personality":
                personality_parts.append(f"{title}\n{body}")
                extension_sections[sid] = {"title": title, "category": category, "content": body}
            elif sid not in core_ids:
                extension_sections[sid] = {"title": title, "category": category, "content": body}

        # Backward-compatible fallback for old templates that lacked categories.
        if sexual_traits and "sexual_traits" not in {s.get("id") for s in template.get("sections", []) if self._template_section_category(s) == "personality"}:
            personality_parts.append("Sexual Traits\n" + sexual_traits)
        if background and "background" not in {s.get("id") for s in template.get("sections", []) if self._template_section_category(s) == "personality"}:
            personality_parts.append("Background\n" + background)

        description = "\n\n".join([p for p in description_parts if p.strip()]).strip()
        personality = "\n\n".join([p for p in personality_parts if p.strip()]).strip()
        return {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {
                "name": name,
                "description": description,
                "personality": personality,
                "scenario": scenario,
                "first_mes": first_mes,
                "mes_example": mes_example,
                "creator_notes": "Generated with Character Card Forge.",
                "system_prompt": system_prompt,
                "post_history_instructions": "",
                "alternate_greetings": self._extract_alternates(output),
                "tags": tags,
                "creator": "Character Card Forge",
                "character_version": "1.0",
                "character_book": {"entries": lorebook_entries},
                "world_names": [],
                "extensions": {
                    "raw_card": self._strip_stable_diffusion_for_card(output),
                    "background": background,
                    "sexual_traits": sexual_traits,
                    "description_tab_sections": {k: v for k, v in extension_sections.items() if v.get("category") == "description"},
                    "personality_tab_sections": {k: v for k, v in extension_sections.items() if v.get("category") == "personality"},
                    "custom_sections": extension_sections,
                    "state_tracking_raw": state_tracking,
                    "front_porch": {
                        "version": "2.5",
                        "realism_engine": front_porch_realism_engine
                    },
                    "character_card_forge": {
                        "lorebook_location": "data.character_book.entries",
                        "state_tracking_location": "data.extensions.front_porch.realism_engine",
                        "stable_diffusion_note": "Stable Diffusion prompts are not embedded into Character Card V2 exports. Use the Export page image generator instead.",
                        "note": "Description/Personality tab sections are folded into the visible Chara V2 fields for frontend imports."
                    }
                }
            }
        }

    # Backwards compatible alias for older frontend calls.
    def _to_sillytavern(self, output, name):
        return self._to_chara_card_v2(output, name)

    def _to_frontend_json(self, output, name, frontend):
        card_v2 = self._to_chara_card_v2(output, name)
        data = card_v2["data"]
        return {
            "format": "character-card-forge-frontend-json",
            "target_frontend": frontend or "generic",
            "name": name,
            "description": data.get("description", ""),
            "personality": data.get("personality", ""),
            "scenario": data.get("scenario", ""),
            "first_message": data.get("first_mes", ""),
            "example_dialogues": data.get("mes_example", ""),
            "alternate_first_messages": data.get("alternate_greetings", []),
            "system_prompt": data.get("system_prompt", ""),
            "lorebook_entries": data.get("character_book", {}).get("entries", []),
            "character_book": data.get("character_book", {"entries": []}),
            "front_porch_realism_engine": data.get("extensions", {}).get("front_porch", {}).get("realism_engine", {}),
            "state_tracking": data.get("extensions", {}).get("state_tracking_raw", ""),
            "stable_diffusion_prompt": self._clean_section_text(self._section(output, "Stable Diffusion Prompt")),
            "tags": data.get("tags", []),
            "raw_card": output,
            "sillytavern_chara_card_v2": card_v2,
        }

    def _write_chara_png(self, path, payload, image_path=None):
        source = (image_path or "").strip()
        if source and Path(source).exists():
            img = Image.open(source).convert("RGBA")
        else:
            img = Image.new("RGBA", (512, 768), (24, 24, 32, 255))

        # Character Card V2 PNG convention: write base64-encoded JSON into the
        # PNG tEXt chunk named "chara". SillyTavern and compatible frontends can
        # import this directly as a card image.
        metadata = PngInfo()
        json_text = json.dumps(payload, ensure_ascii=False)
        metadata.add_text("chara", base64.b64encode(json_text.encode("utf-8")).decode("ascii"))
        metadata.add_text("ccf_raw", payload.get("data", {}).get("extensions", {}).get("raw_card", ""))
        img.save(path, "PNG", pnginfo=metadata)

    def _extract_alternates(self, text):
        """Return clean individual alternate greetings for Chara Card V2.

        The exporter must emit only true alternate greetings. It must not let
        Example Dialogues, Lorebook, Tags, State Tracking, or Stable Diffusion
        leak into a greeting if the model forgets a blank line or divider.
        """
        sections = self._parse_sections(text)
        alt = sections.get("alternate_first_messages", "")

        if not alt:
            # Fallback for rare cards where the model omitted the plural section
            # heading and wrote numbered alternative headings directly. Capture
            # only from the first alt heading until the next real top-level heading.
            lines = (text or "").splitlines()
            capture = []
            active = False
            alt_heading_re = re.compile(r"^\s*(?:#{1,6}\s*)?(?:Alternative|Alternate|Additional)\s+(?:First\s+)?(?:Message|Greeting)s?\s*#?\s*\d+\s*[:.\-]?\s*$", re.I)
            for line in lines:
                if alt_heading_re.match(line):
                    active = True
                    capture.append(line)
                    continue
                if active and self._canonical_heading(line):
                    break
                if active:
                    capture.append(line)
            alt = "\n".join(capture).strip()
        if not alt:
            return []

        # Explicit alternative headings.
        heading_pattern = re.compile(
            r"(?ims)^\s*(?:#{1,6}\s*)?(?:Alternative|Alternate|Additional)\s+(?:First\s+)?(?:Message|Greeting)s?\s*#?\s*(\d+)\s*[:.\-]?\s*$"
        )
        matches = list(heading_pattern.finditer(alt))
        if matches:
            greetings = []
            for i, match in enumerate(matches):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(alt)
                body = alt[start:end].strip()
                body = re.sub(r"(?ims)^[-]{5,}\s*", "", body).strip()
                body = self._strip_embedded_sections(body)
                if len(body) > 20:
                    greetings.append(body)
            return greetings

        # Numbered or bulleted list inside the Alternative First Messages section.
        chunks = re.split(r"(?m)^\s*(?:\d+[.)]|[-*])\s+", alt)
        greetings = []
        for chunk in chunks:
            body = self._strip_embedded_sections(chunk.strip())
            if len(body) > 20 and not re.fullmatch(r"(?i)none|n/a", body):
                greetings.append(body)
        return greetings

    def _strip_embedded_sections(self, text):
        """Trim any accidental following card sections from a message body."""
        lines = []
        for line in (text or "").splitlines():
            if self._is_divider_line(line):
                continue
            if self._canonical_heading(line):
                break
            lines.append(line)
        return self._clean_section_text("\n".join(lines))


def main():
    api = Api()
    window = webview.create_window(
        "Character Card Forge",
        str(APP_DIR / "frontend" / "index.html"),
        js_api=api,
        width=1320,
        height=880,
        min_size=(980, 700),
    )
    webview.start(gui="qt", debug=False)

if __name__ == "__main__":
    main()
