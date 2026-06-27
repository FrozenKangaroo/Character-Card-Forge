import json
import os
import sys
import platform
import re
import time
import uuid
import urllib.request
import urllib.error
import urllib.parse
import base64
import copy
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
import ssl
import struct
import hashlib
import traceback
import webbrowser
import http.server
import socketserver
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.dont_write_bytecode = True

# Use a bundled CA bundle when available.
# GitHub-built AppImages can inherit Ubuntu/PyInstaller OpenSSL default CA paths
# that do not exist on Fedora/Nobara systems, causing HTTPS API calls to fail with
# CERTIFICATE_VERIFY_FAILED. certifi gives the frozen app a portable trust store.
try:
    import certifi
except Exception:  # pragma: no cover - source installs can still use system CAs
    certifi = None


def _portable_ssl_context():
    if certifi is None:
        return None
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


_PORTABLE_SSL_CONTEXT = _portable_ssl_context()


def _safe_urlopen(req, *args, **kwargs):
    if _PORTABLE_SSL_CONTEXT is not None and "context" not in kwargs:
        kwargs["context"] = _PORTABLE_SSL_CONTEXT
    return urllib.request.urlopen(req, *args, **kwargs)

import webview
from PIL import Image
from PIL.PngImagePlugin import PngInfo

APP_NAME = "Character Card Forge"

# -----------------------------------------------------------------------------
# Path handling
# -----------------------------------------------------------------------------
# AppImage/PyInstaller bundles are mounted read-only. Treat BUNDLE_ROOT/APP_DIR
# as resource roots only, and put every user-created file in a per-user writable
# data folder.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_ROOT = Path(sys._MEIPASS).resolve()
else:
    BUNDLE_ROOT = Path(__file__).resolve().parent

# APP_DIR remains available for bundled read-only assets. In PyInstaller/AppImage
# builds, resources may live either inside sys._MEIPASS/_internal or beside the
# executable/AppDir root, so version lookup checks several safe read-only roots.
APP_DIR = BUNDLE_ROOT
BUNDLED_DATA_DIR = BUNDLE_ROOT / "data"


def _candidate_version_files():
    candidates = []

    def add(path):
        try:
            p = Path(path).expanduser().resolve()
        except Exception:
            return
        if p not in candidates:
            candidates.append(p)

    # Source checkout / bundled resource root.
    add(APP_DIR / "VERSION")
    add(BUNDLE_ROOT / "VERSION")

    # AppImage/PyInstaller builders sometimes copy the frontend assets but not
    # loose root files. Keep a duplicate VERSION beside index.html and prefer it
    # before any executable/AppDir-level file that may be stale from an older
    # AppImage build.
    add(APP_DIR / "frontend" / "VERSION")
    add(BUNDLE_ROOT / "frontend" / "VERSION")

    # PyInstaller one-dir commonly has resources either in _internal or beside
    # the executable. AppImage builders often copy VERSION to the AppDir root.
    try:
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir / "VERSION")
        add(exe_dir / "_internal" / "VERSION")
        add(exe_dir.parent / "VERSION")
    except Exception:
        pass

    # AppImage runtime root, when present.
    appdir = os.environ.get("APPDIR")
    if appdir:
        add(Path(appdir) / "VERSION")
        add(Path(appdir) / "usr" / "bin" / "VERSION")

    # Working directory fallback for direct terminal runs and dev launchers.
    try:
        add(Path.cwd() / "VERSION")
    except Exception:
        pass

    return candidates


def _read_app_version():
    for version_file in _candidate_version_files():
        try:
            if version_file.exists() and version_file.is_file():
                value = version_file.read_text(encoding="utf-8", errors="replace").strip()
                if value:
                    return value
        except Exception:
            continue
    return "unknown"


def _app_version_file_path():
    for version_file in _candidate_version_files():
        try:
            if version_file.exists() and version_file.is_file():
                return str(version_file)
        except Exception:
            continue
    return ""


def _safe_mkdir(path):
    """Create a directory only when it is safe/writable.

    Never raise during startup for AppImage/PyInstaller read-only mounts. This
    prevents a bad path from crashing before the app can fall back to user data.
    """
    path = Path(path).expanduser().resolve()
    path_str = str(path)
    if ".mount_" in path_str or "squashfs-root" in path_str or "_internal" in path.parts:
        return path
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return path


def _path_is_writable_dir(path):
    try:
        path = _safe_mkdir(path)
        path_str = str(path)
        if ".mount_" in path_str or "squashfs-root" in path_str or "_internal" in path.parts:
            return False
        probe = path / f".ccf_write_test_{os.getpid()}_{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _real_home_dir():
    try:
        return Path.home().expanduser().resolve()
    except Exception:
        return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or "/tmp").expanduser().resolve()


def _data_dir_config_file():
    home = _real_home_dir()
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    elif system == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))
    return base / APP_NAME / "data_dir.txt"


def _path_is_safe_user_data_root(candidate):
    try:
        candidate = Path(candidate).expanduser().resolve()
        candidate_str = str(candidate)
        if ".mount_" in candidate_str or "squashfs-root" in candidate_str or "_internal" in candidate.parts:
            return False
        return True
    except Exception:
        return False


def _read_user_data_root_override():
    try:
        cfg = _data_dir_config_file()
        if cfg.exists():
            value = cfg.read_text(encoding="utf-8").strip()
            if value:
                candidate = Path(value).expanduser().resolve()
                if _path_is_safe_user_data_root(candidate):
                    return candidate
    except Exception:
        pass
    return None


def _write_user_data_root_override(path):
    cfg = _data_dir_config_file()
    _safe_mkdir(cfg.parent)
    cfg.write_text(str(Path(path).expanduser().resolve()), encoding="utf-8")
    return cfg


def _get_writable_user_root():
    """Return a user-writable data root outside the application bundle."""
    configured = _read_user_data_root_override()
    if configured is not None and _path_is_writable_dir(configured):
        return configured

    # Explicit override, but ignore unsafe AppImage/internal mount overrides.
    for env_name in ("CCF_DATA_DIR", "CHARACTER_CARD_FORGE_DATA_DIR"):
        value = os.environ.get(env_name)
        if value:
            candidate = Path(value).expanduser().resolve()
            candidate_str = str(candidate)
            if ".mount_" not in candidate_str and "squashfs-root" not in candidate_str and "_internal" not in candidate.parts:
                if _path_is_writable_dir(candidate):
                    return candidate

    system = platform.system().lower()
    home = _real_home_dir()
    candidates = []

    if system == "windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / APP_NAME)
        candidates.extend([
            home / "AppData" / "Roaming" / APP_NAME,
            home / "Documents" / APP_NAME,
        ])
    elif system == "darwin":
        candidates.extend([
            home / "Library" / "Application Support" / APP_NAME,
            home / "Documents" / APP_NAME,
        ])
    else:
        docs = home / "Documents"
        if docs.exists():
            candidates.append(docs / APP_NAME)
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            candidates.append(Path(xdg).expanduser() / APP_NAME)
        candidates.extend([
            home / ".local" / "share" / APP_NAME,
            Path("/tmp") / APP_NAME,
        ])

    for candidate in candidates:
        candidate = Path(candidate).expanduser().resolve()
        candidate_str = str(candidate)
        if ".mount_" in candidate_str or "squashfs-root" in candidate_str or "_internal" in candidate.parts:
            continue
        if _path_is_writable_dir(candidate):
            return candidate

    return _safe_mkdir(Path("/tmp") / APP_NAME)


USER_DATA_ROOT = _get_writable_user_root()
DATA_DIR = USER_DATA_ROOT / "data"
EXPORT_DIR = USER_DATA_ROOT / "exports"

SETTINGS_FILE = DATA_DIR / "settings.json"
TEMPLATE_FILE = DATA_DIR / "template.json"
TEMPLATES_DIR = DATA_DIR / "templates"
LOG_FILE = DATA_DIR / "debug.log"
LIBRARY_DB_FILE = DATA_DIR / "character_library.sqlite3"

CARD_IMAGES_DIR = DATA_DIR / "card_images"
GENERATED_IMAGES_DIR = CARD_IMAGES_DIR / "generated"
VISION_IMAGES_DIR = DATA_DIR / "vision_images"
CONCEPT_ATTACHMENTS_DIR = DATA_DIR / "concept_attachments"
IMPORT_UPLOADS_DIR = DATA_DIR / "import_uploads"
CHARACTER_LIBRARY_DIR = EXPORT_DIR

for _dir in (
    USER_DATA_ROOT,
    DATA_DIR,
    TEMPLATES_DIR,
    EXPORT_DIR,
    CARD_IMAGES_DIR,
    GENERATED_IMAGES_DIR,
    VISION_IMAGES_DIR,
    CONCEPT_ATTACHMENTS_DIR,
    IMPORT_UPLOADS_DIR,
):
    _safe_mkdir(_dir)


def _seed_user_data_from_bundle():
    """Copy bundled defaults/templates into writable user data once."""
    try:
        if BUNDLED_DATA_DIR.exists():
            _safe_mkdir(DATA_DIR)
            for name in ("settings.json", "template.json"):
                src = BUNDLED_DATA_DIR / name
                dst = DATA_DIR / name
                if src.exists() and not dst.exists():
                    shutil.copy2(src, dst)

            src_templates = BUNDLED_DATA_DIR / "templates"
            if src_templates.exists():
                _safe_mkdir(TEMPLATES_DIR)
                for src in src_templates.glob("*.json"):
                    dst = TEMPLATES_DIR / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
    except Exception:
        # Bundled defaults are convenience only. DEFAULT_SETTINGS and
        # DEFAULT_TEMPLATE still let the app start if seeding fails.
        pass


_seed_user_data_from_bundle()


def _upgrade_front_porch_prompt_text(text):
    text = str(text or "")
    if not text:
        return text
    replacements = [
        (r"(?i)bond\s+ranges\s*:\s*short\s*/\s*long\s*-?200\s*\.\.\s*200\s*;\s*trust\s*-?50\s*\.\.\s*50", "Bond ranges: short/long -300..300; trust -100..100"),
        (r"(?i)bond\s+ranges\s*:\s*short\s*/\s*long\s*-?200\s*to\s*200\s*;\s*trust\s*-?50\s*to\s*50", "Bond ranges: short/long -300..300; trust -100..100"),
        (r"(?i)short[- ]term\s+bond\s+range\s*:\s*-?200\s*(?:to|\.\.)\s*200", "Short-Term Bond range: -300 to 300"),
        (r"(?i)long[- ]term\s+bond\s+range\s*:\s*-?200\s*(?:to|\.\.)\s*200", "Long-Term Bond range: -300 to 300"),
        (r"(?i)trust\s+level\s+range\s*:\s*-?50\s*(?:to|\.\.)\s*50", "Trust Level range: -100 to 100"),
        (r"(?i)front\s+porch\s+range\s*:\s*-?200\s*to\s*200", "Front Porch range: -300 to 300"),
        (r"(?i)front\s+porch\s+range\s*:\s*-?50\s*to\s*50", "Front Porch range: -100 to 100"),
        (r"(?i)late\s+afternoon", "Afternoon"),
    ]
    out = text
    for pat, rep in replacements:
        out = re.sub(pat, rep, out)
    return out


def _merge_front_porch_state_tracking_section(template):
    if not isinstance(template, dict):
        return template, False
    sections = template.get("sections")
    if not isinstance(sections, list):
        return template, False
    changed = False
    for section in sections:
        if not isinstance(section, dict) or str(section.get("id") or "").strip() != "state_tracking":
            continue
        desired_description = "Optional Front Porch realism/state values. Bond ranges: short/long -300..300; trust -100..100. Valid time_of_day: morning, noon, afternoon, evening, night. Optional day_of_week/start_day_of_week: 0 legacy/unset, or 1 Monday through 7 Sunday. Late Afternoon is normalized to Afternoon."
        if str(section.get("description") or "") != desired_description:
            old = str(section.get("description") or "")
            section["description"] = _upgrade_front_porch_prompt_text(old)
            if not section["description"] or section["description"] == old:
                section["description"] = desired_description
            changed = True
        fields = section.get("fields")
        if not isinstance(fields, list):
            fields = []
            section["fields"] = fields
            changed = True
        field_map = {}
        for item in fields:
            if isinstance(item, dict) and item.get("id"):
                field_map[str(item.get("id"))] = item
        desired_fields = [
            ("emotion", "Starting Emotion", "Primary emotional state."),
            ("objective", "Current Objective", "Immediate goal."),
            ("short_term_bond", "Short-Term Bond", "Front Porch range: -300 to 300."),
            ("long_term_bond", "Long-Term Bond", "Front Porch range: -300 to 300."),
            ("trust_level", "Trust Level", "Front Porch range: -100 to 100."),
            ("time_of_day", "Time of Day", "Use morning, noon, afternoon, evening, or night. Late Afternoon is exported as afternoon."),
            ("day_of_week", "Day of Week", "Optional Front Porch schema v28 weekday anchor: 0 legacy/unset, 1 Monday, 2 Tuesday, 3 Wednesday, 4 Thursday, 5 Friday, 6 Saturday, 7 Sunday."),
        ]
        desired_ids = {fid for fid, _, _ in desired_fields}
        new_fields = []
        for fid, label, hint in desired_fields:
            existing = field_map.get(fid)
            if isinstance(existing, dict):
                item = dict(existing)
                if str(item.get("label") or "") != label:
                    item["label"] = label
                    changed = True
                new_hint = _upgrade_front_porch_prompt_text(str(item.get("hint") or ""))
                if not new_hint or fid in {"short_term_bond", "long_term_bond", "trust_level", "time_of_day", "day_of_week"}:
                    new_hint = hint
                if str(item.get("hint") or "") != new_hint:
                    item["hint"] = new_hint
                    changed = True
                if "enabled" not in item:
                    item["enabled"] = True
                    changed = True
                new_fields.append(item)
            else:
                new_fields.append({"id": fid, "label": label, "enabled": True, "hint": hint})
                changed = True
        # Preserve any custom fields the user added after the required Front Porch fields.
        for item in fields:
            if isinstance(item, dict) and str(item.get("id") or "") not in desired_ids:
                upgraded = dict(item)
                if "hint" in upgraded:
                    new_hint = _upgrade_front_porch_prompt_text(str(upgraded.get("hint") or ""))
                    if new_hint != upgraded.get("hint"):
                        upgraded["hint"] = new_hint
                        changed = True
                new_fields.append(upgraded)
        if section.get("fields") != new_fields:
            section["fields"] = new_fields
            changed = True
        break
    return template, changed


def _migrate_front_porch_templates_and_prompts():
    migrated = []
    try:
        # Main active template
        if TEMPLATE_FILE.exists():
            try:
                data = json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))
                data, changed = _merge_front_porch_state_tracking_section(data)
                if changed:
                    TEMPLATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    migrated.append(str(TEMPLATE_FILE))
            except Exception:
                pass

        # Saved custom templates
        if TEMPLATES_DIR.exists():
            for path in TEMPLATES_DIR.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                changed = False
                if isinstance(payload, dict) and isinstance(payload.get("template"), dict):
                    new_tpl, inner_changed = _merge_front_porch_state_tracking_section(payload.get("template"))
                    if inner_changed:
                        payload["template"] = new_tpl
                        changed = True
                elif isinstance(payload, dict) and isinstance(payload.get("sections"), list):
                    payload, changed = _merge_front_porch_state_tracking_section(payload)
                if changed:
                    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                    migrated.append(str(path))

        # Prompt text files in user data root (current and future-proof)
        for base in [DATA_DIR, TEMPLATES_DIR]:
            if not Path(base).exists():
                continue
            for path in Path(base).glob("*.txt"):
                try:
                    original = path.read_text(encoding="utf-8")
                    updated = _upgrade_front_porch_prompt_text(original)
                    if updated != original:
                        path.write_text(updated, encoding="utf-8")
                        migrated.append(str(path))
                except Exception:
                    pass
        return migrated
    except Exception:
        return migrated


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
    "firstMessageCustomStyle": "",
    "firstMessageCustomInstructions": "",
    "alternateFirstMessages": 2,
    "exportFormat": "chara_v2_png",
    "cardImagePath": "",
    "imageGenerationProvider": "sd",
    "sdBaseUrl": "http://127.0.0.1:7860",
    "sdModel": "",
    "imageApiBaseUrl": "",
    "imageApiKey": "",
    "imageModel": "",
    "imageResolution": "1024x1024",
    "imagePromptMode": "auto",
    "imageVisualStyle": "anime",
    "streamAi": False,
    "sdSteps": 28,
    "sdCfgScale": 7.0,
    "sdSampler": "Euler a",
    "emotionImageEmotions": ["neutral"],
    "alternateFirstMessageStyles": [],
    "alternateFirstMessageCustomStyles": [],
    "alternateFirstMessageInstructions": [],
    "cardMode": "single",
    "multiCharacterCount": 2,
    "sharedScenePolicy": "ai_reconcile",
    "visionApiBaseUrl": "",
    "visionApiKey": "",
    "visionModel": "",
    "visionImagePath": "",
    "activeTemplateName": "Default",
    "frontPorchDataFolder": "",  # Legacy/current active Front Porch folder.
    "frontPorchExportTarget": "stable",
    "frontPorchStableDataFolder": "",
    "frontPorchBetaDataFolder": "",
    "dataFilesFolder": "",
    "restrictTags": False,
    "allowedTags": "",
    "nsfwBrowserMode": "show",
    "nsfwTags": "NSFW",
    "recentModels": [],
    "ideaGeneratorOptions": {},
    "ideaGeneratorMultiFields": ["personality", "subjectOf", "engagesIn", "sexualEngagesIn"],
    "ideaGeneratorRandomMaxChoices": 3,
    "browserTagMerges": {},
    "browserVirtualFolders": [],
    "browserVirtualFolderAssignments": {},
    "browserShowSubfolders": False,
    "mobileServerEnabled": False,
    "mobileServerHost": "0.0.0.0",
    "mobileServerPort": 8787,
    "mobileServerAccessCode": "",
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
               'description': 'Optional Front Porch realism/state values. Bond ranges: short/long -300..300; trust -100..100. Valid time_of_day: morning, noon, afternoon, evening, night. Optional day_of_week/start_day_of_week: 0 legacy/unset, or 1 Monday through 7 Sunday. Late Afternoon is normalized to Afternoon.',
               'fields': [{'id': 'emotion',
                           'label': 'Starting Emotion',
                           'enabled': True,
                           'hint': 'Primary emotional state.'},
                          {'id': 'objective',
                           'label': 'Current Objective',
                           'enabled': True,
                           'hint': 'Immediate goal.'},
                          {'id': 'short_term_bond',
                           'label': 'Short-Term Bond',
                           'enabled': True,
                           'hint': 'Front Porch range: -300 to 300.'},
                          {'id': 'long_term_bond',
                           'label': 'Long-Term Bond',
                           'enabled': True,
                           'hint': 'Front Porch range: -300 to 300.'},
                          {'id': 'trust_level',
                           'label': 'Trust Level',
                           'enabled': True,
                           'hint': 'Front Porch range: -100 to 100.'},
                          {'id': 'time_of_day',
                           'label': 'Time of Day',
                           'enabled': True,
                           'hint': 'Use morning, noon, afternoon, evening, or night. Late Afternoon is exported as afternoon.'},
                          {'id': 'day_of_week',
                           'label': 'Day of Week',
                           'enabled': True,
                           'hint': 'Optional Front Porch schema v28 weekday anchor: 0 legacy/unset, 1 Monday, 2 Tuesday, 3 Wednesday, 4 Thursday, 5 Friday, 6 Saturday, 7 Sunday.'}]},
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
                           'hint': 'low quality, bad anatomy, blurry, watermark, text'}]},
              {'id': 'natural_image_prompt',
               'title': 'Natural English Image Prompt',
               'enabled': False,
               'category': 'image',
               'description': 'Optional natural-language prompt for API image models that respond better to normal English instructions.',
               'fields': [{'id': 'prompt',
                           'label': 'Prompt',
                           'enabled': True,
                           'hint': 'A clear natural-language prompt for portrait generation.'}]}],
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
        self.settings = self._normalise_settings(self._load_json(SETTINGS_FILE, DEFAULT_SETTINGS))
        migrated = _migrate_front_porch_templates_and_prompts()
        self.template = self._normalise_template(self._load_json(TEMPLATE_FILE, DEFAULT_TEMPLATE))
        self._save_json(TEMPLATE_FILE, self.template)
        self.cancel_event = threading.Event()
        self.window = None
        self._last_browser_description_source = "extracted"
        self._mobile_server = None
        self._mobile_server_thread = None
        self._mobile_server_port = None
        self._mobile_generation_lock = threading.Lock()
        self._init_library_db()
        if migrated:
            self._log_event("front_porch_template_prompt_migration", {"files": migrated})
        if self.settings.get("mobileServerEnabled"):
            self._apply_mobile_server_settings(self.settings, save=False)

    def _load_json(self, path, default):
        path = Path(path)
        _safe_mkdir(path.parent)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        path.write_text(json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.loads(json.dumps(default))

    def _save_json(self, path, data):
        path = Path(path)
        _safe_mkdir(path.parent)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _library_connect(self):
        conn = sqlite3.connect(str(LIBRARY_DB_FILE), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        return conn

    def _init_library_db(self):
        """Create the browser library database and migrate old settings-based folders/assignments."""
        _safe_mkdir(DATA_DIR)
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_assets (
                    project_path TEXT NOT NULL,
                    asset_key TEXT NOT NULL,
                    asset_type TEXT NOT NULL DEFAULT '',
                    filename TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    data_text TEXT NOT NULL DEFAULT '',
                    data_blob BLOB,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(project_path, asset_key)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_assets_project ON workspace_assets(project_path)")

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
                try:
                    existing_extra = json.loads(existing_d.get("metadata_json") or "{}")
                    if not isinstance(existing_extra, dict):
                        existing_extra = {}
                except Exception:
                    existing_extra = {}
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
                    "extra": existing_extra,
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

    def _asset_data_url_to_blob(self, data_url):
        try:
            text = str(data_url or "")
            m = re.match(r"^data:([^;,]+)?(?:;charset=[^;,]+)?;base64,(.*)$", text, re.I | re.S)
            if not m:
                return "", None
            mime = (m.group(1) or "application/octet-stream").strip()
            blob = base64.b64decode(re.sub(r"\s+", "", m.group(2) or ""), validate=False)
            return mime, blob
        except Exception:
            return "", None

    def _blob_to_data_url(self, mime, blob):
        try:
            if blob is None:
                return ""
            return f"data:{mime or 'application/octet-stream'};base64," + base64.b64encode(blob).decode("ascii")
        except Exception:
            return ""

    def _store_workspace_asset(self, conn, project_path, asset_key, asset_type, *, filename='', mime_type='', source_path='', data_text='', data_blob=None, metadata=None):
        conn.execute(
            """
            INSERT INTO workspace_assets(project_path, asset_key, asset_type, filename, mime_type, source_path, data_text, data_blob, metadata_json, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(project_path, asset_key) DO UPDATE SET
                asset_type=excluded.asset_type,
                filename=excluded.filename,
                mime_type=excluded.mime_type,
                source_path=excluded.source_path,
                data_text=excluded.data_text,
                data_blob=excluded.data_blob,
                metadata_json=excluded.metadata_json,
                created_at=CURRENT_TIMESTAMP
            """,
            (str(project_path), str(asset_key), str(asset_type), str(filename or ''), str(mime_type or ''), str(source_path or ''), str(data_text or ''), data_blob, json.dumps(metadata or {}, ensure_ascii=False)),
        )

    def _read_file_asset_blob(self, path):
        try:
            p = Path(str(path or ""))
            if not p.exists() or not p.is_file():
                return "", None, ""
            mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            return mime, p.read_bytes(), p.name
        except Exception:
            return "", None, ""

    def _save_workspace_assets_to_db(self, project_path, workspace, image_path=''):
        """Persist restore-critical workspace assets into SQLite and replace old asset rows.

        Project JSON remains a lightweight fallback/manifest; binary image previews,
        emotion/generated image data, and attachment extracted text live in SQLite so
        temp folders can be safely cleaned.
        """
        self._init_library_db()
        project_key = str(Path(project_path).resolve())
        workspace = workspace or {}
        with self._library_connect() as conn:
            conn.execute("DELETE FROM workspace_assets WHERE project_path=?", (project_key,))
            self._store_workspace_asset(conn, project_key, "workspace_payload", "json", data_text=json.dumps(workspace, ensure_ascii=False), metadata={"kind":"workspace"})
            selected_image_source = str(image_path or workspace.get("cardImagePath") or workspace.get("imagePath") or "").strip()
            if selected_image_source or workspace.get("imageDataUrl") or workspace.get("cardImageDataUrl") or workspace.get("generatedImages"):
                mime, blob, filename = self._read_file_asset_blob(selected_image_source) if selected_image_source else ("", None, "")
                if not blob:
                    # Selected/generated image paths can be cleaned after save, while
                    # the workspace still has the generated image as base64 dataUrl.
                    # Store that base64 as the selected card image so saved-card and
                    # group-card exports can restore the real avatar instead of a
                    # flat placeholder.
                    for candidate in self._workspace_card_image_candidates(workspace, selected_image_source):
                        data_url = self._candidate_image_data_url_from_value(candidate)
                        if not data_url:
                            continue
                        cmime, cblob = self._asset_data_url_to_blob(data_url)
                        if cblob:
                            mime, blob, filename = cmime or "image/png", cblob, "selected_card_image" + (self._extension_from_mime(cmime or "image/png", "image") or ".png")
                            break
                if blob:
                    self._store_workspace_asset(conn, project_key, "selected_card_image", "image", filename=filename, mime_type=mime, source_path=selected_image_source, data_blob=blob, metadata={"role":"selected_card_image"})
            def store_image_list(prefix, images):
                if not isinstance(images, list):
                    return
                for idx, item in enumerate(images):
                    if not isinstance(item, dict):
                        continue
                    key = f"{prefix}_{idx:04d}"
                    meta = {k:v for k,v in item.items() if k not in {"dataUrl"}}
                    data_url = item.get("dataUrl") or ""
                    mime, blob = self._asset_data_url_to_blob(data_url)
                    filename = Path(str(item.get("path") or item.get("filename") or key)).name
                    if not blob and item.get("path"):
                        mime, blob, filename = self._read_file_asset_blob(item.get("path"))
                    if blob:
                        self._store_workspace_asset(conn, project_key, key, prefix, filename=filename, mime_type=mime, source_path=item.get("path") or "", data_blob=blob, metadata=meta)
            store_image_list("generated_image", workspace.get("generatedImages") or [])
            store_image_list("emotion_image", workspace.get("emotionImages") or [])
            tabs = workspace.get("characterTabs") if isinstance(workspace.get("characterTabs"), list) else []
            for t_idx, tab in enumerate(tabs):
                if not isinstance(tab, dict):
                    continue
                for idx, item in enumerate(tab.get("generatedImages") or []):
                    if isinstance(item, dict):
                        mime, blob = self._asset_data_url_to_blob(item.get("dataUrl") or "")
                        filename = Path(str(item.get("path") or f"tab{t_idx}_generated_{idx}.png")).name
                        if not blob and item.get("path"):
                            mime, blob, filename = self._read_file_asset_blob(item.get("path"))
                        if blob:
                            meta = {k:v for k,v in item.items() if k != "dataUrl"}
                            meta["tabIndex"] = t_idx
                            self._store_workspace_asset(conn, project_key, f"tab_{t_idx:03d}_generated_{idx:04d}", "tab_generated_image", filename=filename, mime_type=mime, source_path=item.get("path") or "", data_blob=blob, metadata=meta)
                for idx, item in enumerate(tab.get("emotionImages") or []):
                    if isinstance(item, dict):
                        mime, blob = self._asset_data_url_to_blob(item.get("dataUrl") or "")
                        filename = Path(str(item.get("path") or f"tab{t_idx}_emotion_{idx}.png")).name
                        if not blob and item.get("path"):
                            mime, blob, filename = self._read_file_asset_blob(item.get("path"))
                        if blob:
                            meta = {k:v for k,v in item.items() if k != "dataUrl"}
                            meta["tabIndex"] = t_idx
                            self._store_workspace_asset(conn, project_key, f"tab_{t_idx:03d}_emotion_{idx:04d}", "tab_emotion_image", filename=filename, mime_type=mime, source_path=item.get("path") or "", data_blob=blob, metadata=meta)
            attachments = workspace.get("conceptAttachments") if isinstance(workspace.get("conceptAttachments"), list) else []
            for idx, att in enumerate(attachments):
                if not isinstance(att, dict):
                    continue
                text = att.get("text") or att.get("extractedText") or att.get("content") or att.get("preview") or ""
                self._store_workspace_asset(conn, project_key, f"attachment_{idx:04d}", "attachment_text", filename=att.get("name") or att.get("filename") or "", source_path=att.get("path") or att.get("source") or "", data_text=text, metadata=att)
            conn.commit()

    def _load_workspace_assets_from_db(self, project_path):
        self._init_library_db()
        key = str(Path(project_path).resolve())
        with self._library_connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM workspace_assets WHERE project_path=? ORDER BY asset_key", (key,)).fetchall()]
            if not rows:
                # Older snapshots and browser actions can point at a timestamped
                # project while the asset DB is keyed by latest_ccf_project.json
                # in the same folder.  Look inside the project folder before
                # giving up, preferring selected-card and generated-image rows.
                try:
                    folder = str(Path(project_path).resolve().parent)
                    prefix = folder.rstrip('/\\') + os.sep + "%"
                    rows = [dict(r) for r in conn.execute(
                        "SELECT * FROM workspace_assets WHERE project_path LIKE ? ORDER BY CASE asset_key WHEN 'selected_card_image' THEN 0 ELSE 1 END, asset_key",
                        (prefix,),
                    ).fetchall()]
                except Exception:
                    rows = []
        return rows

    def _workspace_asset_file_path_from_row(self, row, kind="generated", reason="workspace_asset_restore"):
        """Return a readable file path for an image asset row without base64 serialising it.

        Loading a character workspace used to convert every generated/emotion image
        BLOB in the SQLite asset cache into a data: URL and send all of that through
        pywebview. A few cards with image candidates could turn a simple Browser
        open into a multi-minute UI lock. Restore blobs to cached files instead and
        let the frontend lazy-load small previews only when it needs to draw them.
        """
        try:
            source_path = str((row or {}).get("source_path") or "").strip()
            if source_path:
                local = self._ensure_local_card_image_path(source_path, kind if kind in {"card", "generated", "emotion"} else "generated", f"{reason}_source")
                if local:
                    return local
            blob = (row or {}).get("data_blob")
            if not blob:
                return ""
            mime = str((row or {}).get("mime_type") or "image/png").strip() or "image/png"
            filename = Path(str((row or {}).get("filename") or (row or {}).get("asset_key") or kind or "image")).name
            stem = self._safe_slug(Path(filename).stem or str((row or {}).get("asset_key") or kind or "image")) or "image"
            ext = Path(filename).suffix.lower()
            if not ext or len(ext) > 8:
                ext = self._extension_from_mime(mime, "image") or ".png"
            root = CARD_IMAGES_DIR / "restored" if kind == "card" else GENERATED_IMAGES_DIR / "restored"
            _safe_mkdir(root)
            digest = hashlib.sha256(blob).hexdigest()[:20]
            path = root / f"{stem}_{digest}{ext}"
            if not path.exists() or path.stat().st_size != len(blob):
                path.write_bytes(blob)
            return str(path)
        except Exception as e:
            try:
                self._log_event("workspace_asset_file_restore_failed", {"kind": kind, "reason": reason, "error": str(e)})
            except Exception:
                pass
            return ""

    def _hydrate_workspace_from_db_assets(self, project_path, loaded):
        """Merge SQLite workspace assets into a loaded project, with old file JSON as fallback.

        This deliberately returns file paths, not large data URLs, for generated and
        emotion images. The frontend lazy-loads preview thumbnails from those paths.
        """
        try:
            rows = self._load_workspace_assets_from_db(project_path)
        except Exception:
            rows = []
        if not rows:
            return loaded
        generated = []
        emotions = []
        attachments_by_idx = {}
        tabs = loaded.get("characterTabs") if isinstance(loaded.get("characterTabs"), list) else []
        restored_files = 0
        for r in rows:
            key = r.get("asset_key") or ""
            atype = r.get("asset_type") or ""
            try:
                meta = json.loads(r.get("metadata_json") or "{}")
            except Exception:
                meta = {}
            if atype == "image" and key == "selected_card_image" and r.get("data_blob"):
                # One selected card image is enough for preview/export. Do not also
                # send imageDataUrl through pywebview during workspace load.
                source_path = str(r.get("source_path") or "").strip()
                local_image = self._ensure_local_card_image_path(source_path, "card", "hydrate_selected_card_source") if source_path else ""
                if not local_image:
                    local_image = self._workspace_asset_file_path_from_row(r, "card", "hydrate_selected_card_asset")
                if local_image:
                    loaded["imagePath"] = local_image
                    loaded["cardImagePath"] = local_image
                    restored_files += 1
                    if isinstance(loaded.get("settings"), dict):
                        loaded["settings"]["cardImagePath"] = local_image
                else:
                    loaded["imagePath"] = loaded.get("imagePath") or source_path or ""
            elif atype == "generated_image" and r.get("data_blob"):
                item = dict(meta or {})
                local = self._workspace_asset_file_path_from_row(r, "generated", "hydrate_generated_asset")
                item.pop("dataUrl", None)
                item["path"] = local or item.get("path") or r.get("source_path") or r.get("filename") or ""
                if local:
                    restored_files += 1
                generated.append(item)
            elif atype == "emotion_image" and r.get("data_blob"):
                item = dict(meta or {})
                local = self._workspace_asset_file_path_from_row(r, "emotion", "hydrate_emotion_asset")
                item.pop("dataUrl", None)
                item["path"] = local or item.get("path") or r.get("source_path") or r.get("filename") or ""
                if local:
                    restored_files += 1
                emotions.append(item)
            elif atype == "attachment_text":
                try:
                    idx = int(key.split("_")[-1])
                except Exception:
                    idx = len(attachments_by_idx)
                item = dict(meta or {})
                text = r.get("data_text") or item.get("text") or item.get("extractedText") or ""
                item["text"] = text
                item["extractedText"] = text
                item["preview"] = item.get("preview") or text[:1000]
                attachments_by_idx[idx] = item
            elif atype in {"tab_generated_image", "tab_emotion_image"} and r.get("data_blob"):
                t_idx = int(meta.get("tabIndex") or 0)
                while len(tabs) <= t_idx:
                    tabs.append({"name": f"Character {len(tabs)+1}", "output":"", "qaAnswers":"", "emotionImages":[], "generatedImages":[], "cardImagePath":""})
                item = dict(meta or {})
                local = self._workspace_asset_file_path_from_row(r, "emotion" if atype == "tab_emotion_image" else "generated", "hydrate_tab_image_asset")
                item.pop("dataUrl", None)
                item["path"] = local or item.get("path") or r.get("source_path") or r.get("filename") or ""
                if local:
                    restored_files += 1
                if atype == "tab_generated_image":
                    tabs[t_idx].setdefault("generatedImages", []).append(item)
                else:
                    tabs[t_idx].setdefault("emotionImages", []).append(item)
        if generated:
            loaded["generatedImages"] = generated
        if emotions:
            loaded["emotionImages"] = emotions
        if attachments_by_idx:
            loaded["conceptAttachments"] = [attachments_by_idx[i] for i in sorted(attachments_by_idx)]
        if tabs:
            loaded["characterTabs"] = tabs
        try:
            self._log_event("workspace_assets_hydrated_lightweight", {"project": str(project_path), "rows": len(rows), "generated": len(generated), "emotions": len(emotions), "tabs": len(tabs), "restoredFiles": restored_files})
        except Exception:
            pass
        return loaded

    def _lighten_loaded_workspace_image_payloads(self, loaded, reason="load_character_project"):
        """Replace embedded generated/emotion image data URLs with local file paths.

        Saved projects from older builds can contain base64 image previews inside
        generatedImages/emotionImages. Returning those through pywebview makes
        Browser -> Load Workspace painfully slow. Keep the image recoverable as a
        local cached path and let the UI lazy-load thumbnails on demand.
        """
        if not isinstance(loaded, dict):
            return loaded
        changed = 0
        def lighten_list(images, kind, label):
            nonlocal changed
            if not isinstance(images, list):
                return images
            out = []
            for idx, item in enumerate(images):
                if not isinstance(item, dict):
                    out.append(item)
                    continue
                next_item = dict(item)
                data_url = next_item.get("dataUrl") or next_item.get("data_url") or ""
                if data_url:
                    local = self._ensure_local_card_image_path(data_url, kind, f"{reason}_{label}_{idx}")
                    if local:
                        next_item["path"] = local
                    next_item.pop("dataUrl", None)
                    next_item.pop("data_url", None)
                    changed += 1
                out.append(next_item)
            return out
        for key, kind in (("generatedImages", "generated"), ("emotionImages", "emotion")):
            if isinstance(loaded.get(key), list):
                loaded[key] = lighten_list(loaded.get(key), kind, key)
        workspace = loaded.get("workspace") if isinstance(loaded.get("workspace"), dict) else None
        if workspace is not None:
            for key, kind in (("generatedImages", "generated"), ("emotionImages", "emotion")):
                if isinstance(workspace.get(key), list):
                    workspace[key] = lighten_list(workspace.get(key), kind, "workspace_" + key)
            loaded["workspace"] = workspace
        tabs = loaded.get("characterTabs") if isinstance(loaded.get("characterTabs"), list) else []
        for t_idx, tab in enumerate(tabs):
            if not isinstance(tab, dict):
                continue
            if isinstance(tab.get("generatedImages"), list):
                tab["generatedImages"] = lighten_list(tab.get("generatedImages"), "generated", f"tab_{t_idx}_generated")
            if isinstance(tab.get("emotionImages"), list):
                tab["emotionImages"] = lighten_list(tab.get("emotionImages"), "emotion", f"tab_{t_idx}_emotion")
        if tabs:
            loaded["characterTabs"] = tabs
        if changed:
            try:
                self._log_event("loaded_workspace_image_payloads_lightened", {"project": str(loaded.get("projectPath") or loaded.get("sourcePath") or ""), "count": changed, "reason": reason})
            except Exception:
                pass
        return loaded

    def _materialize_loaded_project_card_image(self, loaded, project_path="", reason="load_project"):
        """Ensure a loaded project points at a real local image file.

        A saved project can contain a stale generated-image path while the real
        selected image bytes live in workspace_assets. The UI preview and exporters
        both need an actual file path, so recover from selected-card assets,
        imageDataUrl, or saved project image candidates and mirror the resolved path
        through settings/workspace/tabs.
        """
        if not isinstance(loaded, dict):
            return loaded
        selected = str(loaded.get("imagePath") or loaded.get("cardImagePath") or "").strip()
        local_image = self._ensure_local_card_image_path(selected, "card", f"{reason}_selected_path") if selected else ""
        if not local_image and loaded.get("imageDataUrl"):
            local_image = self._ensure_local_card_image_path(loaded.get("imageDataUrl"), "card", f"{reason}_image_data_url")
        if not local_image and project_path:
            local_image = self._front_porch_project_image_from_assets(project_path, selected, f"{reason}_workspace_assets")
        if not local_image and project_path:
            local_image = self._front_porch_project_image_from_json(project_path, selected, f"{reason}_project_json")
        if local_image:
            loaded["imagePath"] = local_image
            loaded["cardImagePath"] = local_image
            settings_obj = loaded.get("settings") if isinstance(loaded.get("settings"), dict) else {}
            settings_obj["cardImagePath"] = local_image
            loaded["settings"] = settings_obj
            workspace = loaded.get("workspace") if isinstance(loaded.get("workspace"), dict) else {}
            workspace["imagePath"] = local_image
            workspace["cardImagePath"] = local_image
            loaded["workspace"] = workspace
            selected_name = Path(selected).name if selected and not selected.lower().startswith(("data:", "http://", "https://")) else ""
            tabs = loaded.get("characterTabs") if isinstance(loaded.get("characterTabs"), list) else []
            for tab in tabs:
                if not isinstance(tab, dict):
                    continue
                tab_path = str(tab.get("cardImagePath") or tab.get("imagePath") or "").strip()
                tab_name = Path(tab_path).name if tab_path and not tab_path.lower().startswith(("data:", "http://", "https://")) else ""
                if not tab_path or tab_path == selected or (selected_name and tab_name == selected_name):
                    tab["cardImagePath"] = local_image
                    tab["imagePath"] = local_image
            if tabs:
                loaded["characterTabs"] = tabs
            self._log_event("loaded_project_card_image_materialized", {"reason": reason, "project": str(project_path or ""), "selected": selected[:240], "path": local_image})
        elif selected:
            self._log_event("loaded_project_card_image_unresolved", {"reason": reason, "project": str(project_path or ""), "selected": selected[:240], "hasImageDataUrl": bool(loaded.get("imageDataUrl"))})
        return loaded

    def _cleanup_temp_workspace_dirs(self, keep_paths=None):
        """Delete temp/cache files after SQLite persistence. Old project files remain fallback."""
        keep = {str(Path(p).resolve()) for p in (keep_paths or []) if p}
        roots = [GENERATED_IMAGES_DIR, VISION_IMAGES_DIR, CONCEPT_ATTACHMENTS_DIR, IMPORT_UPLOADS_DIR]
        for root in roots:
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in list(root.iterdir()):
                    try:
                        cpath = str(child.resolve())
                        if cpath in keep:
                            continue
                        if child.is_dir():
                            shutil.rmtree(child, ignore_errors=True)
                        else:
                            child.unlink(missing_ok=True)
                    except Exception:
                        pass
                _safe_mkdir(root)
            except Exception:
                pass

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
        try:
            extra = json.loads(row.get("metadata_json") or "{}")
            if not isinstance(extra, dict):
                extra = {}
        except Exception:
            extra = {}
        token_counts = extra.get("tokenCounts") if isinstance(extra.get("tokenCounts"), dict) else {}
        try:
            token_total = int(extra.get("tokenTotal") or token_counts.get("total") or 0)
        except Exception:
            token_total = 0
        try:
            token_breakdown_version = int(extra.get("tokenBreakdownVersion") or 0)
        except Exception:
            token_breakdown_version = 0
        updated_ts = float(row.get("updated_ts") or 0)
        return {
            "name": row.get("name") or Path(row.get("folder_path") or "").name,
            "folder": row.get("folder_path") or "",
            "projectPath": row.get("project_path") or "",
            "updated": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated_ts or time.time())),
            "thumbnail": row.get("thumbnail_data_url") or "",
            "browserDescription": row.get("browser_description") or "",
            "browserDescriptionSource": row.get("browser_description_source") or "extracted",
            "cardRating": extra.get("cardRating") or "",
            "cardRatingReasoning": extra.get("cardRatingReasoning") or "",
            "cardRatingDetails": extra.get("cardRatingDetails") if isinstance(extra.get("cardRatingDetails"), list) else [],
            "cardRatingSourceHash": extra.get("cardRatingSourceHash") or "",
            "tokenTotal": token_total,
            "tokenCounts": token_counts,
            "tokenBreakdownVersion": token_breakdown_version,
            "tags": tags,
            "virtualFolderId": str(row.get("virtual_folder_id") or ""),
            "outputPreview": row.get("output_preview") or "",
            "hasEmotionImages": bool(row.get("has_emotion_images")),
            "cached": True,
            "projectHash": row.get("project_hash") or "",
            "cardPngHash": row.get("card_png_hash") or "",
            "imageHash": row.get("image_hash") or "",
            "isGroupCard": bool(extra.get("isGroupCard")),
            "exportFormat": extra.get("exportFormat") or "",
            "groupCardPath": extra.get("groupCardPath") or "",
        }

    def _refresh_library_cache_for_project(self, project_path, force=False):
        """Refresh one project cache if its project/card/image hashes changed."""
        path = Path(project_path)
        if not path.exists():
            return None
        folder = path.parent
        row = self._library_get_card_row(path)
        if row and not force:
            # Very fast cache path for normal Browser opens: avoid hashing/parsing JSON
            # and thumbnails when the project/card/image stat metadata is unchanged.
            try:
                extra_fast = json.loads(row.get("metadata_json") or "{}")
                path_stat = path.stat()
                project_stat_ok = (
                    int(extra_fast.get("projectMtimeNs") or 0) == int(getattr(path_stat, "st_mtime_ns", int(path_stat.st_mtime * 1_000_000_000)))
                    and int(extra_fast.get("projectSize") or -1) == int(path_stat.st_size)
                )
                card_png_path = str(row.get("card_png_path") or "")
                image_fast_path = str(row.get("image_path") or "")
                def stat_matches_fast(file_path, mtime_key, size_key):
                    value = str(file_path or "").strip()
                    if not value:
                        return True
                    fp = Path(value)
                    if not fp.exists():
                        return False
                    st = fp.stat()
                    return (
                        int(extra_fast.get(mtime_key) or 0) == int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
                        and int(extra_fast.get(size_key) or -1) == int(st.st_size)
                    )
                card_stat_ok = stat_matches_fast(card_png_path, "cardPngMtimeNs", "cardPngSize")
                image_stat_ok = stat_matches_fast(image_fast_path, "imageMtimeNs", "imageSize")
                token_ok = (
                    isinstance(extra_fast.get("tokenCounts"), dict)
                    and int(extra_fast.get("tokenTotal") or 0) > 0
                    and int(extra_fast.get("tokenBreakdownVersion") or 0) >= 3
                )
                thumb_ok = self._thumbnail_reference_exists(row.get("thumbnail_data_url") or "")
                index_ok = int(extra_fast.get("browserIndexVersion") or 0) >= 7
                if project_stat_ok and card_stat_ok and image_stat_ok and token_ok and index_ok and thumb_ok:
                    return self._browser_card_from_db_row(row)
            except Exception:
                pass
        project_hash = self._hash_file(path)
        if row and not force and str(row.get("project_hash") or "") == project_hash:
            # Older cache rows may not have stat metadata. Fall back to file hashes once,
            # then refresh/upsert with browserIndexVersion 7 for future instant loads.
            card_png_path = str(row.get("card_png_path") or "")
            image_path = str(row.get("image_path") or "")
            card_hash_ok = (not card_png_path) or self._hash_file(card_png_path) == str(row.get("card_png_hash") or "")
            image_hash_ok = (not image_path) or self._hash_file(image_path) == str(row.get("image_hash") or "")
            needs_token_counts = True
            try:
                extra_for_tokens = json.loads(row.get("metadata_json") or "{}")
                needs_token_counts = not (
                    isinstance(extra_for_tokens, dict)
                    and isinstance(extra_for_tokens.get("tokenCounts"), dict)
                    and int(extra_for_tokens.get("tokenTotal") or 0) > 0
                    and int(extra_for_tokens.get("tokenBreakdownVersion") or 0) >= 3
                )
            except Exception:
                needs_token_counts = True
            needs_browser_index_refresh = True
            try:
                extra_for_index = json.loads(row.get("metadata_json") or "{}")
                needs_browser_index_refresh = int(extra_for_index.get("browserIndexVersion") or 0) < 7
            except Exception:
                needs_browser_index_refresh = True
            thumb_ok = self._thumbnail_reference_exists(row.get("thumbnail_data_url") or "")
            if card_hash_ok and image_hash_ok and not needs_token_counts and not needs_browser_index_refresh and thumb_ok:
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
        resolved_image_path = self._ensure_local_card_image_path(image_path, "card", "browser_cache_project_image") if image_path else ""
        if not resolved_image_path:
            try:
                resolved_image_path = self._front_porch_project_image_from_assets(path, image_path, "browser_cache_asset_image")
            except Exception:
                resolved_image_path = ""
        if resolved_image_path:
            image_path = resolved_image_path
        card_png = self._latest_card_png_for_folder(folder, name)
        # Prefer the selected card image for the Browser thumbnail. If an older
        # autosaved card PNG was created with a blank fallback, the selected image
        # from the workspace asset DB is still the source of truth.
        thumb_source = image_path or (str(card_png) if card_png else "")
        browser_description = str(project.get("browserDescription") or "").strip()
        browser_description_source = str(project.get("browserDescriptionSource") or "").strip().lower()
        if browser_description:
            browser_description_source = browser_description_source or "ai"
        if not browser_description:
            browser_description = self._fallback_browser_description(output, concept)
            browser_description_source = "extracted"
        card_rating = str(project.get("cardRating") or workspace.get("cardRating") or "").strip()
        card_rating_reasoning = str(project.get("cardRatingReasoning") or workspace.get("cardRatingReasoning") or "").strip()
        card_rating_source_hash = str(project.get("cardRatingSourceHash") or workspace.get("cardRatingSourceHash") or "").strip()
        card_rating_details = project.get("cardRatingDetails") if isinstance(project.get("cardRatingDetails"), list) else (workspace.get("cardRatingDetails") if isinstance(workspace.get("cardRatingDetails"), list) else [])
        tags = project.get("tags") if isinstance(project.get("tags"), list) else []
        if not tags:
            tags = self._extract_tags_from_output(output, project.get("template") or self.template)
        token_counts = self._card_browser_token_counts(output)
        browser_thumb = self._browser_preview_reference(thumb_source or image_path, folder)
        old_assignment = self._get_virtual_folder_assignment(path, folder, name, project.get("virtualFolderId") or "")
        if row:
            virtual_folder_id = self._library_upsert_card(path, folder, name, None, path.stat().st_mtime, {
                "projectHash": project_hash,
                "outputHash": self._hash_text(output),
                "cardPngPath": str(card_png or ""),
                "cardPngHash": self._hash_file(card_png) if card_png else "",
                "imagePath": str(image_path or ""),
                "imageHash": self._hash_file(image_path) if image_path else "",
                "thumbnail": browser_thumb or self._image_data_url(thumb_source or image_path),
                "browserDescription": browser_description,
                "browserDescriptionSource": browser_description_source,
                "tags": tags,
                "outputPreview": output[:500],
                "hasEmotionImages": any((folder / f"{e}.png").exists() for e in EMOTION_OPTIONS),
                "extra": {
                    "conceptHash": self._hash_text(concept),
                    "cardRating": card_rating,
                    "cardRatingReasoning": card_rating_reasoning,
                    "cardRatingDetails": card_rating_details,
                    "cardRatingSourceHash": card_rating_source_hash,
                    "tokenTotal": int(token_counts.get("total") or 0),
                    "tokenCounts": token_counts.get("sections") if isinstance(token_counts.get("sections"), dict) else {},
                    "tokenBreakdownVersion": int(token_counts.get("version") or 3),
                    "browserIndexVersion": 7,
                    "projectMtimeNs": int(getattr(path.stat(), "st_mtime_ns", int(path.stat().st_mtime * 1_000_000_000))) if path.exists() else 0,
                    "projectSize": int(path.stat().st_size) if path.exists() else 0,
                    "cardPngMtimeNs": int(getattr(Path(card_png).stat(), "st_mtime_ns", int(Path(card_png).stat().st_mtime * 1_000_000_000))) if card_png and Path(card_png).exists() else 0,
                    "cardPngSize": int(Path(card_png).stat().st_size) if card_png and Path(card_png).exists() else 0,
                    "imageMtimeNs": int(getattr(Path(image_path).stat(), "st_mtime_ns", int(Path(image_path).stat().st_mtime * 1_000_000_000))) if image_path and Path(image_path).exists() else 0,
                    "imageSize": int(Path(image_path).stat().st_size) if image_path and Path(image_path).exists() else 0,
                    "isGroupCard": bool(project.get("isGroupCard") or workspace.get("isGroupCard")),
                    "exportFormat": project.get("exportFormat") or workspace.get("exportFormat") or "",
                    "groupCardPath": project.get("groupCardPath") or workspace.get("groupCardPath") or project.get("exportedPath") or "",
                },
            })
        else:
            virtual_folder_id = self._library_upsert_card(path, folder, name, old_assignment, path.stat().st_mtime, {
                "projectHash": project_hash,
                "outputHash": self._hash_text(output),
                "cardPngPath": str(card_png or ""),
                "cardPngHash": self._hash_file(card_png) if card_png else "",
                "imagePath": str(image_path or ""),
                "imageHash": self._hash_file(image_path) if image_path else "",
                "thumbnail": browser_thumb or self._image_data_url(thumb_source or image_path),
                "browserDescription": browser_description,
                "browserDescriptionSource": browser_description_source,
                "tags": tags,
                "outputPreview": output[:500],
                "hasEmotionImages": any((folder / f"{e}.png").exists() for e in EMOTION_OPTIONS),
                "extra": {
                    "conceptHash": self._hash_text(concept),
                    "cardRating": card_rating,
                    "cardRatingReasoning": card_rating_reasoning,
                    "cardRatingDetails": card_rating_details,
                    "cardRatingSourceHash": card_rating_source_hash,
                    "tokenTotal": int(token_counts.get("total") or 0),
                    "tokenCounts": token_counts.get("sections") if isinstance(token_counts.get("sections"), dict) else {},
                    "tokenBreakdownVersion": int(token_counts.get("version") or 3),
                    "browserIndexVersion": 7,
                    "projectMtimeNs": int(getattr(path.stat(), "st_mtime_ns", int(path.stat().st_mtime * 1_000_000_000))) if path.exists() else 0,
                    "projectSize": int(path.stat().st_size) if path.exists() else 0,
                    "cardPngMtimeNs": int(getattr(Path(card_png).stat(), "st_mtime_ns", int(Path(card_png).stat().st_mtime * 1_000_000_000))) if card_png and Path(card_png).exists() else 0,
                    "cardPngSize": int(Path(card_png).stat().st_size) if card_png and Path(card_png).exists() else 0,
                    "imageMtimeNs": int(getattr(Path(image_path).stat(), "st_mtime_ns", int(Path(image_path).stat().st_mtime * 1_000_000_000))) if image_path and Path(image_path).exists() else 0,
                    "imageSize": int(Path(image_path).stat().st_size) if image_path and Path(image_path).exists() else 0,
                    "isGroupCard": bool(project.get("isGroupCard") or workspace.get("isGroupCard")),
                    "exportFormat": project.get("exportFormat") or workspace.get("exportFormat") or "",
                    "groupCardPath": project.get("groupCardPath") or workspace.get("groupCardPath") or project.get("exportedPath") or "",
                },
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
                    "thumbnail": browser_thumb or self._image_data_url(thumb_source or image_path),
                    "browserDescription": browser_description,
                    "browserDescriptionSource": browser_description_source,
                    "tags": tags,
                    "outputPreview": output[:500],
                    "hasEmotionImages": any((folder / f"{e}.png").exists() for e in EMOTION_OPTIONS),
                    "extra": {
                    "conceptHash": self._hash_text(concept),
                    "cardRating": card_rating,
                    "cardRatingReasoning": card_rating_reasoning,
                    "cardRatingDetails": card_rating_details,
                    "cardRatingSourceHash": card_rating_source_hash,
                    "tokenTotal": int(token_counts.get("total") or 0),
                    "tokenCounts": token_counts.get("sections") if isinstance(token_counts.get("sections"), dict) else {},
                    "tokenBreakdownVersion": int(token_counts.get("version") or 3),
                    "browserIndexVersion": 7,
                    "projectMtimeNs": int(getattr(path.stat(), "st_mtime_ns", int(path.stat().st_mtime * 1_000_000_000))) if path.exists() else 0,
                    "projectSize": int(path.stat().st_size) if path.exists() else 0,
                    "cardPngMtimeNs": int(getattr(Path(card_png).stat(), "st_mtime_ns", int(Path(card_png).stat().st_mtime * 1_000_000_000))) if card_png and Path(card_png).exists() else 0,
                    "cardPngSize": int(Path(card_png).stat().st_size) if card_png and Path(card_png).exists() else 0,
                    "imageMtimeNs": int(getattr(Path(image_path).stat(), "st_mtime_ns", int(Path(image_path).stat().st_mtime * 1_000_000_000))) if image_path and Path(image_path).exists() else 0,
                    "imageSize": int(Path(image_path).stat().st_size) if image_path and Path(image_path).exists() else 0,
                    "isGroupCard": bool(project.get("isGroupCard") or workspace.get("isGroupCard")),
                    "exportFormat": project.get("exportFormat") or workspace.get("exportFormat") or "",
                    "groupCardPath": project.get("groupCardPath") or workspace.get("groupCardPath") or project.get("exportedPath") or "",
                },
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
        # Force Front Porch template migrations whenever a template is loaded/saved.
        # This catches existing active/custom templates that were created before
        # start_day_of_week/day_of_week support and preserves any custom fields.
        try:
            template, _ = _merge_front_porch_state_tracking_section(template)
        except Exception:
            pass
        try:
            sections = template.get("sections") if isinstance(template.get("sections"), list) else []
            ids = {str(s.get("id") or "") for s in sections if isinstance(s, dict)}
            if "natural_image_prompt" not in ids:
                insert_at = len(sections)
                for idx, section in enumerate(sections):
                    if str(section.get("id") or "") == "stable_diffusion":
                        insert_at = idx + 1
                        break
                sections.insert(insert_at, {
                    "id": "natural_image_prompt",
                    "title": "Natural English Image Prompt",
                    "enabled": False,
                    "category": "image",
                    "description": "Optional natural-language prompt for API image models that respond better to normal English instructions.",
                    "fields": [{"id": "prompt", "label": "Prompt", "enabled": True, "hint": "A clear natural-language prompt for portrait generation."}],
                })
                template["sections"] = sections
        except Exception:
            pass
        return template

    def _log_event(self, event, payload=None):
        try:
            entry = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": event,
                "payload": payload or {},
            }
            _safe_mkdir(LOG_FILE.parent)
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
            return {"ok": True, "path": str(LOG_FILE), "text": LOG_FILE.read_text(encoding="utf-8", errors="replace")[-60000:]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def append_debug_event(self, event, payload=None):
        """Frontend-safe debug bridge.

        Some token-fetch failures can happen before the backend fetch method is
        reached (missing fields, pywebview binding mismatch, frontend exception).
        This lets the visible Debug Log record those client-side checkpoints too.
        """
        try:
            clean_event = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(event or "client_event"))[:160] or "client_event"
            clean_payload = payload if isinstance(payload, dict) else {"value": payload}
            self._log_event(clean_event, clean_payload)
            return {"ok": True, "path": str(LOG_FILE)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # camelCase alias for pywebview builds that expose JavaScript methods this way.
    def appendDebugEvent(self, event, payload=None):
        return self.append_debug_event(event, payload)


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

    def reset_cancel_request(self):
        self._reset_cancel()
        return {"ok": True}

    def resetCancelRequest(self):
        return self.reset_cancel_request()

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
        legacy_front_porch = str(settings.get("frontPorchDataFolder") or "").strip()
        target = str(settings.get("frontPorchExportTarget") or "stable").strip().lower()
        if target not in {"stable", "beta"}:
            target = "stable"
        stable_front_porch = str(settings.get("frontPorchStableDataFolder") or "").strip()
        beta_front_porch = str(settings.get("frontPorchBetaDataFolder") or "").strip()

        # v1.0.2 migration: older builds had only one Front Porch Data Folder.
        # If the user already had a single folder configured, place it into the most
        # likely stable/beta slot by looking for the database name. If the path cannot
        # be inspected, treat it as the stable path to preserve older behaviour.
        if legacy_front_porch and not stable_front_porch and not beta_front_porch:
            try:
                legacy_path = Path(legacy_front_porch.strip('"').strip("'")).expanduser()
                probe_paths = []
                if legacy_path.suffix.lower() == ".db":
                    probe_paths.append(legacy_path)
                else:
                    probe_paths.extend([
                        legacy_path / "KoboldManager" / "front_porch_beta.db",
                        legacy_path / "front_porch_beta.db",
                        legacy_path / "KoboldManager" / "front_porch.db",
                        legacy_path / "front_porch.db",
                    ])
                has_beta = any(p.name == "front_porch_beta.db" and p.exists() for p in probe_paths)
                has_stable = any(p.name == "front_porch.db" and p.exists() for p in probe_paths)
                if has_beta and not has_stable:
                    beta_front_porch = legacy_front_porch
                    target = "beta"
                else:
                    stable_front_porch = legacy_front_porch
            except Exception:
                stable_front_porch = legacy_front_porch

        active_front_porch = beta_front_porch if target == "beta" else stable_front_porch
        if not active_front_porch and legacy_front_porch:
            active_front_porch = legacy_front_porch
        settings["frontPorchExportTarget"] = target
        settings["frontPorchStableDataFolder"] = stable_front_porch
        settings["frontPorchBetaDataFolder"] = beta_front_porch
        settings["frontPorchDataFolder"] = active_front_porch
        settings["dataFilesFolder"] = str(settings.get("dataFilesFolder") or str(USER_DATA_ROOT)).strip() or str(USER_DATA_ROOT)
        settings["restrictTags"] = bool(settings.get("restrictTags"))
        allowed_tags_value = settings.get("allowedTags")
        if isinstance(allowed_tags_value, list):
            allowed_tags_value = ", ".join(str(x).strip() for x in allowed_tags_value if str(x).strip())
        settings["allowedTags"] = str(allowed_tags_value or "").strip()
        nsfw_mode = str(settings.get("nsfwBrowserMode") or "show").strip().lower()
        settings["nsfwBrowserMode"] = nsfw_mode if nsfw_mode in {"show", "blur", "hide"} else "show"
        nsfw_tags_value = settings.get("nsfwTags", DEFAULT_SETTINGS.get("nsfwTags", "NSFW"))
        if isinstance(nsfw_tags_value, list):
            nsfw_tags_value = ", ".join(str(x).strip() for x in nsfw_tags_value if str(x).strip())
        nsfw_tags_value = str(nsfw_tags_value or DEFAULT_SETTINGS.get("nsfwTags", "NSFW")).strip()
        settings["nsfwTags"] = nsfw_tags_value or "NSFW"
        provider = str(settings.get("imageGenerationProvider") or DEFAULT_SETTINGS.get("imageGenerationProvider", "sd")).strip().lower()
        settings["imageGenerationProvider"] = provider if provider in {"sd", "api"} else "sd"
        settings["sdBaseUrl"] = str(settings.get("sdBaseUrl") or DEFAULT_SETTINGS["sdBaseUrl"]).strip() or DEFAULT_SETTINGS["sdBaseUrl"]
        settings["sdModel"] = str(settings.get("sdModel") or "").strip()
        settings["imageApiBaseUrl"] = str(settings.get("imageApiBaseUrl") or "").strip()
        settings["imageApiKey"] = str(settings.get("imageApiKey") or "").strip()
        settings["imageModel"] = str(settings.get("imageModel") or "").strip()
        settings["imageResolution"] = str(settings.get("imageResolution") or DEFAULT_SETTINGS.get("imageResolution", "1024x1024")).strip() or "1024x1024"
        prompt_mode = str(settings.get("imagePromptMode") or DEFAULT_SETTINGS.get("imagePromptMode", "auto")).strip().lower()
        settings["imagePromptMode"] = prompt_mode if prompt_mode in {"auto", "sd", "natural"} else "auto"
        visual_style = str(settings.get("imageVisualStyle") or DEFAULT_SETTINGS.get("imageVisualStyle", "anime")).strip().lower()
        settings["imageVisualStyle"] = visual_style if visual_style in {"anime", "realistic"} else "anime"
        settings["streamAi"] = bool(settings.get("streamAi"))

        idea_fields = {"archetype", "conflict", "setting", "tone", "occupation", "relationship", "status", "personality", "subjectOf", "engagesIn", "sexualEngagesIn"}
        raw_idea_options = settings.get("ideaGeneratorOptions") if isinstance(settings.get("ideaGeneratorOptions"), dict) else {}
        clean_idea_options = {}
        for field, values in raw_idea_options.items():
            if field not in idea_fields or not isinstance(values, list):
                continue
            cleaned_values = []
            seen_values = set()
            for value in values:
                text = re.sub(r"\s+", " ", str(value or "").strip())[:120]
                key = text.casefold()
                if text and key not in seen_values:
                    seen_values.add(key)
                    cleaned_values.append(text)
            if cleaned_values:
                clean_idea_options[field] = cleaned_values[:500]
        settings["ideaGeneratorOptions"] = clean_idea_options
        raw_multi = settings.get("ideaGeneratorMultiFields") if isinstance(settings.get("ideaGeneratorMultiFields"), list) else DEFAULT_SETTINGS.get("ideaGeneratorMultiFields", [])
        clean_multi = []
        for field in raw_multi:
            field = str(field or "").strip()
            if field in idea_fields and field not in clean_multi:
                clean_multi.append(field)
        settings["ideaGeneratorMultiFields"] = clean_multi or list(DEFAULT_SETTINGS.get("ideaGeneratorMultiFields", []))
        try:
            settings["ideaGeneratorRandomMaxChoices"] = max(1, min(20, int(float(settings.get("ideaGeneratorRandomMaxChoices", DEFAULT_SETTINGS.get("ideaGeneratorRandomMaxChoices", 3))))))
        except Exception:
            settings["ideaGeneratorRandomMaxChoices"] = int(DEFAULT_SETTINGS.get("ideaGeneratorRandomMaxChoices", 3))

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
        settings["mobileServerEnabled"] = bool(settings.get("mobileServerEnabled", DEFAULT_SETTINGS.get("mobileServerEnabled", False)))
        host = str(settings.get("mobileServerHost") or DEFAULT_SETTINGS.get("mobileServerHost", "0.0.0.0")).strip() or "0.0.0.0"
        if host in {"*", "all"}:
            host = "0.0.0.0"
        settings["mobileServerHost"] = host[:80]
        try:
            settings["mobileServerPort"] = max(1024, min(65535, int(settings.get("mobileServerPort") or DEFAULT_SETTINGS.get("mobileServerPort", 8787))))
        except Exception:
            settings["mobileServerPort"] = int(DEFAULT_SETTINGS.get("mobileServerPort", 8787))
        settings["mobileServerAccessCode"] = str(settings.get("mobileServerAccessCode") or "").strip()[:128]
        emo = settings.get("emotionImageEmotions", DEFAULT_SETTINGS["emotionImageEmotions"])
        if not isinstance(emo, list):
            emo = DEFAULT_SETTINGS["emotionImageEmotions"]
        settings["emotionImageEmotions"] = [e for e in emo if e in EMOTION_OPTIONS]
        style_key = str(settings.get("firstMessageStyle") or "cinematic").strip()
        if style_key not in FIRST_MESSAGE_STYLES and style_key != "custom":
            style_key = "cinematic"
        settings["firstMessageStyle"] = style_key
        settings["firstMessageCustomStyle"] = str(settings.get("firstMessageCustomStyle") or "").strip()[:120]
        settings["firstMessageCustomInstructions"] = str(settings.get("firstMessageCustomInstructions") or "").strip()[:2000]
        alt_styles = settings.get("alternateFirstMessageStyles", [])
        if not isinstance(alt_styles, list):
            alt_styles = []
        cleaned_styles = []
        for s in alt_styles:
            s = str(s or "").strip()
            cleaned_styles.append(s if (s in FIRST_MESSAGE_STYLES or s == "custom") else "")
        settings["alternateFirstMessageStyles"] = cleaned_styles
        def _clean_text_list(value, max_len):
            if not isinstance(value, list):
                value = []
            return [str(x or "").strip()[:max_len] for x in value]
        settings["alternateFirstMessageCustomStyles"] = _clean_text_list(settings.get("alternateFirstMessageCustomStyles", []), 120)
        settings["alternateFirstMessageInstructions"] = _clean_text_list(settings.get("alternateFirstMessageInstructions", []), 2000)
        mode = str(settings.get("cardMode") or "single").strip().lower()
        settings["cardMode"] = "group_cards" if mode in {"group_cards", "group-cards", "group", "multi_card", "multi-card", "multi_cards", "multi-cards"} else ("split_cards" if mode in {"split_cards", "split-cards", "multi_split", "split"} else ("multi" if mode in {"multi", "multi_character", "multi-character"} else "single"))
        try:
            settings["multiCharacterCount"] = max(2, min(4 if settings.get("cardMode") == "group_cards" else 12, int(settings.get("multiCharacterCount") or 2)))
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
        # Remember recently used text models for quick switching. Keep compact and sorted newest first.
        raw_recent = settings.get("recentModels") if isinstance(settings.get("recentModels"), list) else []
        recent = []
        seen_recent = set()
        now_ts = time.time()
        for item in raw_recent:
            if isinstance(item, dict):
                name = self._clean_model_name(item.get("name") or item.get("model") or item.get("id"))
                try:
                    last_used = float(item.get("lastUsed") or item.get("last_used") or 0)
                except Exception:
                    last_used = 0
                input_tokens = item.get("maxInputTokens") or item.get("max_input_tokens") or ""
                output_tokens = item.get("maxOutputTokens") or item.get("max_output_tokens") or ""
            else:
                name = self._clean_model_name(item)
                last_used = 0
                input_tokens = ""
                output_tokens = ""
            if not name:
                continue
            key = name.casefold()
            if key in seen_recent:
                continue
            seen_recent.add(key)
            entry = {"name": name, "lastUsed": last_used or 0}
            try:
                if input_tokens not in (None, ""):
                    entry["maxInputTokens"] = int(input_tokens)
            except Exception:
                pass
            try:
                if output_tokens not in (None, ""):
                    entry["maxOutputTokens"] = int(output_tokens)
            except Exception:
                pass
            recent.append(entry)
        current_model = self._clean_model_name(settings.get("model"))
        if current_model and current_model.casefold() not in seen_recent:
            recent.insert(0, {"name": current_model, "lastUsed": now_ts})
        recent.sort(key=lambda x: float(x.get("lastUsed") or 0), reverse=True)
        settings["recentModels"] = recent[:30]
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
        return {"settings": self.settings, "template": self.template, "styles": FIRST_MESSAGE_STYLES, "emotions": EMOTION_OPTIONS, "templates": self._list_prompt_templates(), "activeTemplateName": self.settings.get("activeTemplateName", "Default"), "paths": self.get_data_locations(), "version": self.get_app_version()}

    def get_app_version(self):
        return _read_app_version()

    def _normalise_version_string(self, value):
        """Return a clean semantic version from release/tag text.

        GitHub tags are normally like v1.0.9-beta35, but Actions/manual
        releases can accidentally produce names such as
        character-card-forge-v1.0.9-beta35 or release-1.0.9_beta35.  The
        update checker should still understand those instead of treating them
        as version 0.0.0.
        """
        raw = str(value or "").strip()
        if not raw:
            return ""
        raw = raw.split("+", 1)[0].strip()
        raw = raw.replace("_", "-")
        raw = re.sub(r"^[vV](?=\d)", "", raw)

        # Prefer the first SemVer-looking substring anywhere in the text.
        # This catches tags/release names with prefixes like
        # character-card-forge-v1.0.9-beta35.
        match = re.search(
            r"(?i)(\d+(?:\.\d+){0,3})(?:[-\s.]*(alpha|beta|rc|preview|pre|nightly)[-\s.]*(\d+)?)?",
            raw,
        )
        if match:
            main = match.group(1) or ""
            label = (match.group(2) or "").lower()
            number = match.group(3) or ""
            if label:
                if label == "preview":
                    label = "pre"
                return f"{main}-{label}{number}"
            return main
        return raw

    def _parse_version_for_compare(self, value):
        """Parse v1.2.3-beta4 style tags into a comparable tuple.

        Stable releases sort above pre-releases with the same numeric version.
        Unknown/malformed values sort very low instead of crashing update checks.
        """
        raw = self._normalise_version_string(value)
        if not raw:
            return ((0, 0, 0), -1, 0, "")
        main, sep, pre = raw.partition("-")
        nums = []
        for part in main.split("."):
            m = re.match(r"^(\d+)", part.strip())
            nums.append(int(m.group(1)) if m else 0)
        while len(nums) < 3:
            nums.append(0)
        nums = tuple(nums[:4])
        if not sep:
            return (nums, 3, 0, "")
        pre_l = pre.lower()
        rank = 0
        if pre_l.startswith(("alpha", "nightly", "pre")):
            rank = 0
        elif pre_l.startswith("beta"):
            rank = 1
        elif pre_l.startswith(("rc", "release-candidate")):
            rank = 2
        m = re.search(r"(\d+)", pre_l)
        pre_num = int(m.group(1)) if m else 0
        return (nums, rank, pre_num, pre_l)

    def _version_core_tuple(self, value):
        try:
            return self._parse_version_for_compare(value)[0]
        except Exception:
            return (0, 0, 0)

    def _is_prerelease_version(self, value):
        raw = self._normalise_version_string(value)
        return "-" in raw

    def _is_newer_version(self, latest, current):
        return self._parse_version_for_compare(latest) > self._parse_version_for_compare(current)

    def _github_api_get_json(self, url, headers, timeout=15):
        req = urllib.request.Request(url, headers=headers)
        started = time.time()
        try:
            with _safe_urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", None) or getattr(resp, "code", None)
                raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            self._log_event("update_check_fetch_success", {
                "url": url,
                "status": status,
                "bytes": len(raw.encode("utf-8", errors="replace")),
                "elapsedMs": int((time.time() - started) * 1000),
                "kind": type(parsed).__name__,
                "count": len(parsed) if isinstance(parsed, list) else (len(parsed.keys()) if isinstance(parsed, dict) else 0),
            })
            return parsed
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:800]
            except Exception:
                body = ""
            self._log_event("update_check_fetch_http_error", {
                "url": url,
                "status": getattr(e, "code", None),
                "reason": str(getattr(e, "reason", "") or e),
                "bodyPreview": body,
                "elapsedMs": int((time.time() - started) * 1000),
            })
            raise
        except Exception as e:
            self._log_event("update_check_fetch_failed", {
                "url": url,
                "error": str(e),
                "errorType": type(e).__name__,
                "portableCaBundle": bool(_PORTABLE_SSL_CONTEXT),
                "certifiBundle": (certifi.where() if certifi else ""),
                "elapsedMs": int((time.time() - started) * 1000),
            })
            raise

    def _release_info_from_github_html_tag(self, tag, owner, repo):
        tag = str(tag or "").strip()
        version = self._normalise_version_string(tag)
        return {
            "tag": tag,
            "version": version,
            "name": tag or version or "Latest tag",
            "url": f"https://github.com/{owner}/{repo}/releases/tag/{urllib.parse.quote(tag)}" if tag else f"https://github.com/{owner}/{repo}/releases",
            "body": "",
            "publishedAt": "",
            "prerelease": self._is_prerelease_version(version),
            "draft": False,
        }

    def _release_info_from_github_release(self, data, owner, repo):
        data = data or {}
        tag = str(data.get("tag_name") or "").strip()
        version = self._normalise_version_string(tag)
        if not version:
            version = self._normalise_version_string(data.get("name") or "")
        return {
            "tag": tag or (f"v{version}" if version else ""),
            "version": version,
            "name": str(data.get("name") or tag or version or "Latest release"),
            "url": str(data.get("html_url") or (f"https://github.com/{owner}/{repo}/releases/tag/{tag}" if tag else f"https://github.com/{owner}/{repo}/releases/latest")),
            "body": str(data.get("body") or "").strip(),
            "publishedAt": str(data.get("published_at") or data.get("created_at") or ""),
            "prerelease": bool(data.get("prerelease")) or self._is_prerelease_version(version),
            "draft": bool(data.get("draft")),
        }

    def _release_info_from_github_tag(self, data, owner, repo):
        data = data or {}
        tag = str(data.get("name") or data.get("ref") or "").strip()
        if tag.startswith("refs/tags/"):
            tag = tag.split("refs/tags/", 1)[1]
        version = self._normalise_version_string(tag)
        return {
            "tag": tag,
            "version": version,
            "name": tag or version or "Latest tag",
            "url": f"https://github.com/{owner}/{repo}/releases/tag/{tag}" if tag else f"https://github.com/{owner}/{repo}/releases",
            "body": "",
            "publishedAt": "",
            "prerelease": self._is_prerelease_version(version),
            "draft": False,
        }

    def _select_best_update_release(self, current, releases):
        """Choose the best available update, preferring stable releases.

        This deliberately treats a stable release as newer than a beta with the same
        numeric version. Example: current 1.0.6-beta9 should notify for 1.0.6.
        """
        clean = [r for r in (releases or []) if r.get("version") and not r.get("draft")]
        if not clean:
            return None, "none"

        stable = [r for r in clean if not r.get("prerelease") and "-" not in str(r.get("version") or "")]
        stable.sort(key=lambda r: self._parse_version_for_compare(r.get("version")), reverse=True)
        clean.sort(key=lambda r: self._parse_version_for_compare(r.get("version")), reverse=True)

        current_is_beta = self._is_prerelease_version(current)
        current_core = self._version_core_tuple(current)

        if current_is_beta:
            for rel in stable:
                if self._version_core_tuple(rel.get("version")) >= current_core and self._is_newer_version(rel.get("version"), current):
                    return rel, "stable_for_beta"

        for rel in stable:
            if self._is_newer_version(rel.get("version"), current):
                return rel, "stable_newer"

        # Only offer pre-release updates when the current app is already a pre-release.
        # Stable users should not get nagged about beta/nightly builds unless they opt in
        # later via a dedicated setting.
        if current_is_beta:
            for rel in clean:
                if self._is_newer_version(rel.get("version"), current):
                    return rel, "prerelease_newer"

        return (stable[0] if stable else clean[0]), "latest_not_newer"

    def check_for_updates(self):
        """Check GitHub for a newer public Character Card Forge build."""
        current = self.get_app_version()
        owner = "FrozenKangaroo"
        repo = "Character-Card-Forge"
        repo_url = f"https://github.com/{owner}/{repo}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"CharacterCardForge/{current or 'unknown'}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            releases = []
            source_parts = []
            release_versions = set()
            endpoint_errors = []

            def remember_rows(rows, source_name):
                added = 0
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    version_key = str(row.get("version") or "").casefold()
                    tag_key = str(row.get("tag") or "").casefold()
                    dedupe_key = version_key or tag_key
                    if not dedupe_key or dedupe_key in release_versions:
                        continue
                    releases.append(row)
                    release_versions.add(dedupe_key)
                    added += 1
                if added:
                    source_parts.append(source_name)
                return added

            try:
                rel_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=50"
                data = self._github_api_get_json(rel_url, headers, timeout=15)
                if isinstance(data, list):
                    remember_rows([self._release_info_from_github_release(x, owner, repo) for x in data], "releases")
            except Exception as releases_error:
                err = str(releases_error)
                endpoint_errors.append({"source": "releases", "error": err[:500]})
                self._log_event("update_check_releases_api_failed", {"currentVersion": current, "error": err})

            # Always merge tags as well as releases. Some builds can be published
            # as tags/assets without GitHub Release objects, and relying on
            # /releases alone makes the in-app update checker look dead.
            try:
                tag_url = f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=50"
                data = self._github_api_get_json(tag_url, headers, timeout=15)
                if isinstance(data, list):
                    remember_rows([self._release_info_from_github_tag(x, owner, repo) for x in data], "tags")
            except Exception as tags_error:
                err = str(tags_error)
                endpoint_errors.append({"source": "tags", "error": err[:500]})
                self._log_event("update_check_tags_api_failed", {"currentVersion": current, "error": err})

            # Last-resort fallback: scrape public tag/release pages for tag links.
            # This gives the debug log another signal if the GitHub JSON API is
            # blocked/rate-limited but normal github.com pages still load.
            if not releases:
                html_headers = {
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": f"Mozilla/5.0 CharacterCardForge/{current or 'unknown'}",
                }
                for page_name, page_url in (
                    ("tags_html", f"https://github.com/{owner}/{repo}/tags"),
                    ("releases_html", f"https://github.com/{owner}/{repo}/releases"),
                ):
                    try:
                        req = urllib.request.Request(page_url, headers=html_headers)
                        started = time.time()
                        with _safe_urlopen(req, timeout=15) as resp:
                            status = getattr(resp, "status", None) or getattr(resp, "code", None)
                            html = resp.read().decode("utf-8", errors="replace")
                        tags = []
                        for m in re.finditer(rf"/{re.escape(owner)}/{re.escape(repo)}/(?:releases/tag|tree)/([^\"'<>?#]+)", html):
                            try:
                                tag = urllib.parse.unquote(m.group(1))
                            except Exception:
                                tag = m.group(1)
                            if tag and tag not in tags:
                                tags.append(tag)
                        added = remember_rows([self._release_info_from_github_html_tag(t, owner, repo) for t in tags], page_name)
                        self._log_event("update_check_html_fallback", {
                            "source": page_name,
                            "url": page_url,
                            "status": status,
                            "bytes": len(html.encode("utf-8", errors="replace")),
                            "elapsedMs": int((time.time() - started) * 1000),
                            "tagsFound": len(tags),
                            "added": added,
                        })
                        if releases:
                            break
                    except Exception as html_error:
                        err = str(html_error)
                        endpoint_errors.append({"source": page_name, "error": err[:500]})
                        self._log_event("update_check_html_fallback_failed", {"source": page_name, "url": page_url, "error": err})

            source = "+".join(source_parts) if source_parts else "none"
            chosen, update_kind = self._select_best_update_release(current, releases)
            chosen = chosen or {}
            latest_version = str(chosen.get("version") or "").strip()
            latest_tag = str(chosen.get("tag") or (f"v{latest_version}" if latest_version else "")).strip()
            release_url = str(chosen.get("url") or f"{repo_url}/releases/latest")
            body = str(chosen.get("body") or "").strip()
            published_at = str(chosen.get("publishedAt") or "")
            name = str(chosen.get("name") or latest_tag or latest_version or "Latest release")
            newer = bool(latest_version and current and current != "unknown" and self._is_newer_version(latest_version, current))

            stable_releases = [r for r in releases if r.get("version") and not r.get("prerelease") and "-" not in str(r.get("version") or "")]
            stable_releases.sort(key=lambda r: self._parse_version_for_compare(r.get("version")), reverse=True)
            latest_stable = stable_releases[0] if stable_releases else {}
            candidates_sorted = sorted(
                [r for r in releases if r.get("version")],
                key=lambda r: self._parse_version_for_compare(r.get("version")),
                reverse=True,
            )
            candidate_versions = []
            for row in candidates_sorted[:12]:
                candidate_versions.append({
                    "version": row.get("version") or "",
                    "tag": row.get("tag") or "",
                    "prerelease": bool(row.get("prerelease")),
                    "draft": bool(row.get("draft")),
                })

            result = {
                "ok": True,
                "currentVersion": current,
                "currentIsPrerelease": self._is_prerelease_version(current),
                "latestVersion": latest_version,
                "latestTag": latest_tag,
                "latestName": name,
                "latestStableVersion": latest_stable.get("version") or "",
                "latestStableTag": latest_stable.get("tag") or "",
                "releaseUrl": release_url,
                "repositoryUrl": repo_url,
                "publishedAt": published_at,
                "isNewer": newer,
                "updateKind": update_kind,
                "source": source,
                "candidateCount": len(releases),
                "candidateVersions": candidate_versions,
                "endpointErrors": endpoint_errors,
                "versionFile": _app_version_file_path(),
                "bodyPreview": body[:1200],
            }
            self._log_event("update_check_complete", {
                k: result.get(k)
                for k in (
                    "currentVersion", "currentIsPrerelease", "latestVersion", "latestStableVersion",
                    "latestTag", "isNewer", "updateKind", "source", "candidateCount", "candidateVersions",
                    "endpointErrors", "versionFile", "releaseUrl"
                )
            })
            return result
        except Exception as e:
            self._log_event("update_check_failed", {"currentVersion": current, "versionFile": _app_version_file_path(), "error": str(e)})
            return {"ok": False, "currentVersion": current, "repositoryUrl": repo_url, "versionFile": _app_version_file_path(), "error": str(e)}

    def open_external_url(self, url):
        try:
            target = str(url or "").strip()
            if not re.match(r"^https://github\.com/FrozenKangaroo/Character-Card-Forge(?:/|$)", target):
                return {"ok": False, "error": "Only Character Card Forge GitHub links can be opened from this action."}
            webbrowser.open(target)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_data_locations(self):
        return {
            "appDir": str(APP_DIR),
            "userDataRoot": str(USER_DATA_ROOT),
            "dataDir": str(DATA_DIR),
            "exportsDir": str(EXPORT_DIR),
            "settingsFile": str(SETTINGS_FILE),
            "libraryDbFile": str(LIBRARY_DB_FILE),
            "dataDirConfigFile": str(_data_dir_config_file()),
            "versionFile": _app_version_file_path(),
        }

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
                return _safe_urlopen(req, timeout=timeout)
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
                    "portableCaBundle": bool(_PORTABLE_SSL_CONTEXT),
                    "certifiBundle": (certifi.where() if certifi else ""),
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
        """Use the full text model to convert Main Concept + Vision into builder fields."""
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
                "Builder fields filled by this response will take priority over Main Concept / Vision during generation.",
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

    def _copy_user_data_to(self, target_root):
        target_root = Path(target_root).expanduser().resolve()
        if not _path_is_safe_user_data_root(target_root):
            return {"ok": False, "error": "That folder is inside a read-only app/bundle mount. Choose a normal user folder."}
        try:
            _safe_mkdir(target_root)
            if not _path_is_writable_dir(target_root):
                return {"ok": False, "error": "The selected data folder is not writable."}
            if USER_DATA_ROOT.exists() and USER_DATA_ROOT.resolve() != target_root.resolve():
                shutil.copytree(USER_DATA_ROOT, target_root, dirs_exist_ok=True)
            _write_user_data_root_override(target_root)
            return {"ok": True, "path": str(target_root), "restartRequired": True}
        except Exception as e:
            return {"ok": False, "error": f"Could not set data folder: {e}"}

    def select_data_folder(self):
        try:
            paths = []
            if shutil.which("kdialog") and not self._is_packaged_appimage():
                paths = self._run_dialog_command(["kdialog", "--title", "Select Character Card Forge Data Folder", "--getexistingdirectory", str(USER_DATA_ROOT)], "kdialog_folder") or []
            if not paths and shutil.which("zenity") and not self._is_packaged_appimage():
                paths = self._run_dialog_command(["zenity", "--file-selection", "--directory", "--title", "Select Character Card Forge Data Folder"], "zenity_folder") or []
            if not paths:
                window = webview.windows[0] if webview.windows else None
                if window and hasattr(webview, "FOLDER_DIALOG"):
                    result = window.create_file_dialog(webview.FOLDER_DIALOG)
                    if isinstance(result, (list, tuple)):
                        paths = [str(x) for x in result if str(x).strip()]
                    elif result:
                        paths = [str(result)]
            if not paths:
                return {"ok": False, "cancelled": True}
            return {"ok": True, "path": str(Path(paths[0]).expanduser().resolve())}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def select_export_folder(self):
        try:
            start = EXPORT_DIR if EXPORT_DIR.exists() else USER_DATA_ROOT
            paths = []
            if shutil.which("kdialog") and not self._is_packaged_appimage():
                paths = self._run_dialog_command(["kdialog", "--title", "Select Character Card Export Folder", "--getexistingdirectory", str(start)], "kdialog_export_folder") or []
            if not paths and shutil.which("zenity") and not self._is_packaged_appimage():
                paths = self._run_dialog_command(["zenity", "--file-selection", "--directory", "--title", "Select Character Card Export Folder"], "zenity_export_folder") or []
            if not paths:
                window = webview.windows[0] if webview.windows else None
                if window and hasattr(webview, "FOLDER_DIALOG"):
                    result = window.create_file_dialog(webview.FOLDER_DIALOG)
                    if isinstance(result, (list, tuple)):
                        paths = [str(x) for x in result if str(x).strip()]
                    elif result:
                        paths = [str(result)]
            if not paths:
                return {"ok": False, "cancelled": True}
            path = Path(paths[0]).expanduser().resolve()
            _safe_mkdir(path)
            if not _path_is_writable_dir(path):
                return {"ok": False, "error": "The selected export folder is not writable."}
            return {"ok": True, "path": str(path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def generate_idea(self, idea_options, settings=None):
        """Generate a compact Main Concept seed from Idea Generator controls."""
        try:
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            validation = self._validate_text_api_settings(merged)
            if not validation.get("ok"):
                return {"ok": False, "error": validation.get("error") or "AI settings are incomplete."}
            idea_options = idea_options or {}
            labels = {
                "gender": "Gender",
                "archetype": "Archetype",
                "coreConflict": "Core Conflict",
                "setting": "Setting",
                "tone": "Tone",
                "occupation": "Occupation / Role",
                "relationship": "Relationship to {{user}}",
                "status": "Status / Social Position",
                "personality": "Personality",
                "subjectOf": "Subject Of",
                "engagesIn": "Engages In",
                "sexualEngagesIn": "Engages In (Sexual)",
                "customInstructions": "Custom Instructions",
            }
            def _format_idea_value(value):
                if isinstance(value, (list, tuple, set)):
                    items = []
                    seen_items = set()
                    for item in value:
                        text = re.sub(r"\s+", " ", str(item or "").strip())
                        key = text.casefold()
                        if text and key not in seen_items:
                            seen_items.add(key)
                            items.append(text)
                    return ", ".join(items)
                return re.sub(r"\s+", " ", str(value or "").strip())

            chosen = []
            for key, label in labels.items():
                value = _format_idea_value(idea_options.get(key))
                if value:
                    chosen.append(f"- {label}: {value}")
            if not chosen:
                return {"ok": False, "error": "Choose at least one idea option or enter custom instructions first."}
            prompt = "\n".join([
                "You are an idea generator for fictional AI roleplay character cards.",
                "Create ONLY a compact Main Concept seed, not a full character card.",
                "The output will be pasted into the Main Concept box before the user generates the real card later.",
                "Use the selected ingredients below as inspiration, but make them coherent and playable.",
                "All main/romantic/sexual participants must be adults 18+ even if the setting is school-like; use university/adult academy framing when needed.",
                "Avoid explicit sexual prose. You may include romance, drama, secrecy, temptation, or tension as scenario ingredients, but keep this as high-level concept notes.",
                "Include these concise headings only: Core Idea, Main Character, Relationship to {{user}}, Conflict, Setting, Tone, First Scene Hook, Tags.",
                "Keep it short enough to edit easily: around 250-500 words.",
                "Do not write Name/Description/Personality/Scenario/First Message sections as a finished card.",
                "",
                "SELECTED IDEA INGREDIENTS",
                "\n".join(chosen),
            ])
            raw = self._chat(prompt, merged).strip()
            raw = self._clean_section_text(raw)
            raw = re.sub(r"^```(?:markdown|text)?\s*", "", raw, flags=re.I).strip()
            raw = re.sub(r"\s*```$", "", raw).strip()
            if not raw:
                return {"ok": False, "error": "The AI returned an empty idea."}
            self._log_event("idea_generator_response", {"options": idea_options, "preview": raw[:1000]})
            return {"ok": True, "idea": raw}
        except Exception as e:
            self._log_event("idea_generator_error", {"error": str(e)})
            return {"ok": False, "error": f"Idea generation failed: {e}"}

    # CamelCase aliases for PyWebView builds that do not expose/refresh the snake_case
    # method table reliably after packaging. The frontend tries both names.
    def generateIdea(self, idea_options, settings=None):
        return self.generate_idea(idea_options, settings)

    def generateIdeaFromOptions(self, idea_options, settings=None):
        return self.generate_idea(idea_options, settings)

    def _model_metadata_value(self, obj, keys):
        if not isinstance(obj, dict):
            return None
        for key in keys:
            if key in obj and obj.get(key) not in (None, ""):
                return obj.get(key)
        # Try nested common metadata dictionaries.
        for nested_key in ("metadata", "details", "limits", "capabilities", "config", "info", "provider", "settings", "parameters"):
            nested = obj.get(nested_key)
            if isinstance(nested, dict):
                value = self._model_metadata_value(nested, keys)
                if value not in (None, ""):
                    return value
        return None

    def _coerce_token_limit(self, value):
        """Safely coerce a token limit value to int.

        Some model catalogs include nested dict/list objects in metadata blocks.
        Those must never be passed into int()/float() as usable limits.
        """
        if value is None or isinstance(value, (dict, list, tuple, set)):
            return 0
        try:
            if isinstance(value, str):
                value = value.strip().replace(",", "")
                if not value:
                    return 0
            parsed = int(float(value))
            return parsed if parsed > 0 else 0
        except Exception:
            return 0

    def fetch_model_token_limits(self, settings=None):
        """Fetch model token metadata with direct visible diagnostics.

        This method is intentionally self-contained and writes directly to LOG_FILE
        before doing anything else, so Debug Log can prove whether the pywebview
        bridge actually reached Python.
        """
        import json as _json
        import os as _os
        import re as _re
        import subprocess as _subprocess
        import time as _time
        import traceback as _traceback
        import urllib.parse as _urlparse
        import urllib.request as _urlrequest
        from pathlib import Path as _Path

        def _fallback_log_file():
            try:
                return LOG_FILE
            except Exception:
                home = _Path(_os.environ.get("HOME") or _os.environ.get("USERPROFILE") or "/tmp").expanduser()
                return home / ".local" / "share" / "Character Card Forge" / "data" / "debug.log"

        def log_debug(event, payload=None):
            """Write JSON event directly to the same file read by Debug Log."""
            payload = payload or {}
            try:
                path = _fallback_log_file()
                path.parent.mkdir(parents=True, exist_ok=True)
                entry = {
                    "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
                    "event": event,
                    "payload": payload,
                }
                with path.open("a", encoding="utf-8") as f:
                    f.write(_json.dumps(entry, ensure_ascii=False, indent=2, default=str) + "\n---\n")
                    f.flush()
                try:
                    print(f"[TOKEN_FETCH] {event}: {_json.dumps(payload, ensure_ascii=False, default=str)[:1200]}", flush=True)
                except Exception:
                    pass
            except Exception:
                # Token logging must never stop the actual fetch.
                pass

        def setting_value(merged, *keys):
            for key in keys:
                try:
                    value = merged.get(key)
                    if value not in (None, ""):
                        return value
                except Exception:
                    pass
            return ""

        def normalize_settings(local_settings):
            merged = {}
            try:
                merged.update(DEFAULT_SETTINGS)
            except Exception:
                pass
            try:
                if isinstance(getattr(self, "settings", None), dict):
                    merged.update(self.settings)
            except Exception:
                pass
            try:
                if isinstance(local_settings, dict):
                    merged.update(local_settings)
            except Exception:
                pass
            return merged

        def ensure_scheme(url):
            url = str(url or "").strip()
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url
            return url

        def strip_completion_suffix(url):
            url = ensure_scheme(url).rstrip("/")
            lowered = url.casefold()
            for suffix in ("/chat/completions", "/completions", "/responses"):
                if lowered.endswith(suffix):
                    return url[: -len(suffix)]
            return url

        def tokenise(value):
            return [p for p in _re.split(r"[:\-_/.\s]+", str(value or "").casefold()) if p]

        def compact(value):
            return _re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

        def safe_int(value):
            if value is None or isinstance(value, (dict, list, tuple, set)):
                return 0
            try:
                if isinstance(value, str):
                    value = value.strip().replace(",", "")
                    if not value:
                        return 0
                parsed = int(float(value))
                return parsed if parsed > 0 else 0
            except Exception:
                return 0

        def nested_limit(obj, keys):
            if not isinstance(obj, dict):
                return 0
            for key in keys:
                if key in obj:
                    val = safe_int(obj.get(key))
                    if val > 0:
                        return val
            for nested_key in (
                "metadata", "details", "limits", "capabilities", "config", "info",
                "provider", "settings", "parameters", "architecture", "model", "generation_config"
            ):
                nested = obj.get(nested_key)
                if isinstance(nested, dict):
                    val = nested_limit(nested, keys)
                    if val > 0:
                        return val
                elif isinstance(nested, list):
                    for sub in nested:
                        val = nested_limit(sub, keys)
                        if val > 0:
                            return val
            return 0

        input_keys = [
            "context_length", "contextLength", "context_window", "contextWindow", "context_size", "contextSize",
            "max_context", "maxContext", "max_context_length", "maxContextLength", "max_input_tokens", "maxInputTokens",
            "input_token_limit", "inputTokenLimit", "prompt_token_limit", "promptTokenLimit", "max_prompt_tokens", "maxPromptTokens",
            "max_position_embeddings",
        ]
        output_keys = [
            "max_output_tokens", "maxOutputTokens", "max_completion_tokens", "maxCompletionTokens", "completion_token_limit",
            "completionTokenLimit", "output_token_limit", "outputTokenLimit", "generation_token_limit", "generationTokenLimit",
            "max_generation", "maxGeneration", "max_completion", "maxCompletion", "max_gen_tokens", "maxGenTokens",
        ]

        def extract_limits(row):
            if not isinstance(row, dict):
                return 0, 0
            in_val = nested_limit(row, input_keys)
            out_val = nested_limit(row, output_keys)
            return in_val, out_val

        def extract_model_list(data):
            if isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    return data.get("data") or []
                for key in ("models", "items", "result"):
                    if isinstance(data.get(key), list):
                        return data.get(key) or []
            if isinstance(data, list):
                return data
            return []

        def identity_values(row):
            if not isinstance(row, dict):
                return []
            keys = ["id", "name", "model", "canonicalId", "canonical_id", "slug", "label"]
            vals = []
            for key in keys:
                val = row.get(key)
                if val not in (None, ""):
                    vals.append(str(val))
            for nested_key in ("metadata", "details", "info"):
                nested = row.get(nested_key)
                if isinstance(nested, dict):
                    for key in keys:
                        val = nested.get(key)
                        if val not in (None, ""):
                            vals.append(str(val))
            deduped = []
            seen = set()
            for val in vals:
                key = val.casefold()
                if key not in seen:
                    seen.add(key)
                    deduped.append(val)
            return deduped

        def display_id(row):
            vals = identity_values(row)
            return vals[0] if vals else ""

        def score_candidate(candidate, target_model):
            cand = str(candidate or "")
            target = str(target_model or "")
            if not cand or not target:
                return 0
            cand_cf = cand.casefold()
            target_cf = target.casefold()
            cand_compact = compact(cand)
            target_compact = compact(target)
            target_tail = target.split("/")[-1]
            target_tail_compact = compact(target_tail)
            score = 0
            if cand_cf == target_cf:
                score = max(score, 1_000_000)
            if cand_compact == target_compact:
                score = max(score, 950_000)
            if cand_cf.endswith("/" + target_cf) or cand_cf.endswith(":" + target_cf):
                score = max(score, 850_000)
            if target_tail_compact and (cand_compact == target_tail_compact or cand_compact.endswith(target_tail_compact)):
                score = max(score, 800_000)
            if target_cf in cand_cf or cand_cf in target_cf:
                score = max(score, 650_000 + min(len(cand_cf), len(target_cf)))
            ignored = {"org", "ai", "the", "model"}
            target_tokens = [t for t in tokenise(target) if t not in ignored]
            cand_tokens = {t for t in tokenise(cand) if t not in ignored}
            if target_tokens:
                matched = sum(1 for t in target_tokens if t in cand_tokens)
                ratio = matched / max(1, len(target_tokens))
                if matched == len(target_tokens):
                    score = max(score, 500_000 + matched)
                elif matched >= 3 and ratio >= 0.70:
                    score = max(score, int(300_000 + ratio * 100_000))
            return score

        def read_urllib(url, headers):
            req = _urlrequest.Request(url, headers=headers, method="GET")
            with _safe_urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = getattr(response, "status", getattr(response, "code", ""))
            return _json.loads(raw), raw, status

        def read_curl(url, headers):
            curl = _shutil_which("curl")
            if not curl:
                raise RuntimeError("curl is not available")
            cmd = [curl, "-sS", "--compressed", "--max-time", "30", url]
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])
            proc = _subprocess.run(cmd, stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, text=True, timeout=40)
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or "curl failed").strip()[:1000])
            raw = proc.stdout or ""
            return _json.loads(raw), raw, "curl"

        def _shutil_which(name):
            try:
                import shutil as _shutil
                return _shutil.which(name)
            except Exception:
                return None

        def raw_find_limit_near_id(body, ids):
            body = str(body or "")
            if not body:
                return 0, 0
            patterns_in = [
                r'"context_length"\s*:\s*"?([0-9][0-9,]*)"?',
                r'"contextLength"\s*:\s*"?([0-9][0-9,]*)"?',
                r'"max_input_tokens"\s*:\s*"?([0-9][0-9,]*)"?',
                r'"maxInputTokens"\s*:\s*"?([0-9][0-9,]*)"?',
            ]
            patterns_out = [
                r'"max_output_tokens"\s*:\s*"?([0-9][0-9,]*)"?',
                r'"maxOutputTokens"\s*:\s*"?([0-9][0-9,]*)"?',
                r'"max_completion_tokens"\s*:\s*"?([0-9][0-9,]*)"?',
                r'"maxCompletionTokens"\s*:\s*"?([0-9][0-9,]*)"?',
            ]
            def json_escaped(value):
                try:
                    return _json.dumps(str(value), ensure_ascii=False)[1:-1]
                except Exception:
                    return str(value)
            def window_at(index):
                start = body.rfind("{", 0, index)
                if start < 0:
                    start = max(0, index - 2500)
                depth = 0
                in_str = False
                esc = False
                for pos in range(start, min(len(body), index + 24000)):
                    ch = body[pos]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth <= 0 and pos > index:
                            return body[start:pos + 1]
                return body[max(0, index - 2500):min(len(body), index + 24000)]
            def extract(window):
                iv = ov = 0
                for pat in patterns_in:
                    m = _re.search(pat, window, flags=_re.I)
                    if m:
                        iv = safe_int(m.group(1))
                        if iv > 0:
                            break
                for pat in patterns_out:
                    m = _re.search(pat, window, flags=_re.I)
                    if m:
                        ov = safe_int(m.group(1))
                        if ov > 0:
                            break
                return iv, ov
            needles = []
            for val in ids:
                val = str(val or "").strip()
                if not val:
                    continue
                for candidate in (val, val.replace("/", r"\/"), json_escaped(val), val.split("/")[-1]):
                    if candidate and candidate not in needles:
                        needles.append(candidate)
            for needle in sorted(needles, key=len, reverse=True):
                for match in _re.finditer(_re.escape(needle), body, flags=_re.I):
                    iv, ov = extract(window_at(match.start()))
                    if iv > 0 or ov > 0:
                        return iv, ov
            return 0, 0

        log_debug("model_token_fetch_python_entry", {"settingsType": type(settings).__name__, "debugLogPath": str(_fallback_log_file())})

        try:
            merged = normalize_settings(settings)
            raw_base = str(setting_value(merged, "apiBaseUrl", "baseUrl", "api_base_url") or "").strip()
            model = str(setting_value(merged, "model", "textModel", "modelName") or "").strip()
            api_key = str(setting_value(merged, "apiKey", "api_key", "key") or "").strip()

            if not raw_base or not model:
                log_debug("model_token_fetch_skipped_missing_fields", {"hasApiBaseUrl": bool(raw_base), "hasModel": bool(model)})
                return {"ok": False, "error": "Enter API Base URL and Model first.", "debugLogPath": str(_fallback_log_file())}

            base = strip_completion_suffix(raw_base)
            is_nanogpt = any(marker in base.casefold() for marker in ("nano-gpt", "nanogpt"))
            endpoints = []
            if is_nanogpt:
                parsed = _urlparse.urlparse(base)
                root_base = f"{parsed.scheme or 'https'}://{parsed.netloc or 'nano-gpt.com'}".rstrip("/")
                endpoints = [
                    root_base + "/api/v1/models?detailed=true",
                    root_base + "/api/subscription/v1/models?detailed=true",
                    root_base + "/api/paid/v1/models?detailed=true",
                ]
            else:
                b = base.rstrip("/")
                if b.endswith("/models"):
                    endpoints = [b + "?detailed=true", b]
                else:
                    endpoints = [b + "/models?detailed=true", b + "/models"]
            seen = set()
            endpoints = [u for u in endpoints if not (u in seen or seen.add(u))]
            headers = {"Accept": "application/json", "User-Agent": f"Mozilla/5.0 CharacterCardForge/{self.get_app_version()}"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                headers["x-api-key"] = api_key

            log_debug("model_token_fetch_start", {
                "rawBase": raw_base,
                "normalisedBase": base,
                "model": model,
                "isNanoGpt": is_nanogpt,
                "endpoints": endpoints,
                "hasApiKey": bool(api_key),
                "headerKeys": sorted(headers.keys()),
            })

            readers = [("urllib", read_urllib)]
            if is_nanogpt:
                readers.append(("curl", read_curl))

            all_rows = []
            raw_responses = []
            endpoint_errors = []
            fetch_attempts = []
            sampled_ids = []

            for url in endpoints:
                for method, reader in readers:
                    try:
                        data, raw, status = reader(url, headers)
                        rows = extract_model_list(data)
                        fetch_attempts.append({"url": url, "method": method, "status": status, "count": len(rows)})
                        raw_responses.append({"url": url, "method": method, "body": raw})
                        possible = []
                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            rid = display_id(row)
                            if rid and rid not in sampled_ids and len(sampled_ids) < 40:
                                sampled_ids.append(rid)
                            score = max([score_candidate(v, model) for v in identity_values(row)] or [0])
                            if score > 0 and len(possible) < 20:
                                iv, ov = extract_limits(row)
                                possible.append({
                                    "id": rid,
                                    "score": score,
                                    "input": iv,
                                    "output": ov,
                                    "keys": sorted([str(k) for k in row.keys()])[:80],
                                    "context_length": row.get("context_length"),
                                    "max_output_tokens": row.get("max_output_tokens"),
                                })
                            row = dict(row)
                            row["_ccf_source_endpoint"] = url
                            row["_ccf_fetch_method"] = method
                            all_rows.append(row)
                        log_debug("model_token_fetch_response", {
                            "url": url,
                            "method": method,
                            "status": status,
                            "modelRows": len(rows),
                            "topLevelKeys": sorted(list(data.keys()))[:50] if isinstance(data, dict) else [],
                            "rawBodyPrefix": str(raw or "")[:2500],
                            "possibleMatches": possible,
                        })
                    except Exception as e:
                        err = f"{method} {url}: {e}"
                        endpoint_errors.append(err)
                        log_debug("model_token_fetch_endpoint_error", {"url": url, "method": method, "error": str(e), "traceback": _traceback.format_exc()[-2500:]})

            if not all_rows:
                log_debug("model_token_fetch_no_rows", {"endpointErrors": endpoint_errors[:12], "fetchAttempts": fetch_attempts})
                return {
                    "ok": False,
                    "error": "Could not fetch any model metadata. " + ("; ".join(endpoint_errors[:4]) or "No endpoints returned model rows."),
                    "searchedEndpoints": endpoints,
                    "endpointErrors": endpoint_errors[:12],
                    "fetchAttempts": fetch_attempts,
                    "debugLogPath": str(_fallback_log_file()),
                }

            matches = []
            for row in all_rows:
                best_score = 0
                best_id = display_id(row)
                for ident in identity_values(row):
                    sc = score_candidate(ident, model)
                    if sc > best_score:
                        best_score = sc
                        best_id = ident
                if best_score >= 300_000:
                    iv, ov = extract_limits(row)
                    matches.append({"row": row, "score": best_score, "id": best_id, "input": iv, "output": ov})

            log_debug("model_token_fetch_matched_rows", {
                "matchedCount": len(matches),
                "rows": [{
                    "id": display_id(m["row"]) or m.get("id", ""),
                    "matchedIdentity": m.get("id", ""),
                    "score": m.get("score", 0),
                    "input": m.get("input", 0),
                    "output": m.get("output", 0),
                    "keys": sorted([str(k) for k in m["row"].keys() if not str(k).startswith("_ccf_")])[:80],
                } for m in matches[:25]],
                "sampleModels": sampled_ids[:25],
            })

            if not matches:
                return {
                    "ok": False,
                    "error": f"Could not find model configuration matching '{model}'. Seen examples:\n" + "\n".join(f" - {x}" for x in sampled_ids[:12]),
                    "sampleModels": sampled_ids[:40],
                    "searchedEndpoints": endpoints,
                    "endpointErrors": endpoint_errors[:12],
                    "fetchAttempts": fetch_attempts,
                    "debugLogPath": str(_fallback_log_file()),
                }

            matches.sort(key=lambda m: ((m["input"] > 0 or m["output"] > 0), m["score"], m["input"], m["output"]), reverse=True)
            best = matches[0]
            row = best["row"]
            input_tokens = best["input"]
            output_tokens = best["output"]

            log_debug("model_token_fetch_best_match", {
                "requestedModel": model,
                "chosenId": display_id(row) or best.get("id", ""),
                "matchedIdentity": best.get("id", ""),
                "score": best.get("score", 0),
                "inputTokensBeforeRawFallback": input_tokens,
                "outputTokensBeforeRawFallback": output_tokens,
                "matchedRowKeys": sorted([str(k) for k in row.keys() if not str(k).startswith("_ccf_")])[:100],
                "matchedRowJsonPrefix": _json.dumps({k: v for k, v in row.items() if not str(k).startswith("_ccf_")}, ensure_ascii=False, default=str)[:8000],
            })

            if input_tokens <= 0 and output_tokens <= 0:
                ids = [model, best.get("id", ""), display_id(row)] + identity_values(row)
                for raw in raw_responses:
                    iv, ov = raw_find_limit_near_id(raw.get("body", ""), ids)
                    log_debug("model_token_fetch_raw_fallback_attempt", {
                        "url": raw.get("url", ""),
                        "method": raw.get("method", ""),
                        "input": iv,
                        "output": ov,
                        "ids": ids[:12],
                    })
                    if iv > 0 or ov > 0:
                        input_tokens, output_tokens = iv, ov
                        row["_ccf_raw_limit_endpoint"] = raw.get("url", "")
                        row["_ccf_raw_limit_method"] = raw.get("method", "")
                        break

            if input_tokens <= 0 and output_tokens <= 0:
                log_debug("model_token_fetch_found_but_no_limits", {
                    "requestedModel": model,
                    "chosenId": display_id(row) or best.get("id", ""),
                    "matchedRowKeys": sorted([str(k) for k in row.keys() if not str(k).startswith("_ccf_")])[:100],
                    "fetchAttempts": fetch_attempts,
                    "endpointErrors": endpoint_errors[:12],
                })
                return {
                    "ok": False,
                    "error": f"Found {display_id(row) or best.get('id') or model}, but no token limit fields were read. Open Debug Log and copy the latest model_token_fetch_* entries.",
                    "modelInfo": row,
                    "sourceEndpoint": row.get("_ccf_source_endpoint", ""),
                    "searchedEndpoints": endpoints,
                    "endpointErrors": endpoint_errors[:12],
                    "fetchAttempts": fetch_attempts,
                    "debugLogPath": str(_fallback_log_file()),
                }

            if input_tokens <= 0:
                input_tokens = safe_int(merged.get("maxInputTokens")) or 32768
            if output_tokens <= 0:
                output_tokens = min(384000, max(4096, input_tokens // 4)) if input_tokens > 0 else 4096

            result = {
                "ok": True,
                "model": display_id(row) or best.get("id") or model,
                "matchedRequestedModel": model,
                "matchScore": best.get("score", 0),
                "maxInputTokens": input_tokens,
                "maxOutputTokens": output_tokens,
                "modelInfo": row,
                "sourceEndpoint": row.get("_ccf_raw_limit_endpoint") or row.get("_ccf_source_endpoint", ""),
                "fetchMethod": row.get("_ccf_raw_limit_method") or row.get("_ccf_fetch_method", ""),
                "searchedEndpoints": endpoints,
                "endpointErrors": endpoint_errors[:12],
                "fetchAttempts": fetch_attempts,
                "debugLogPath": str(_fallback_log_file()),
            }

            log_debug("model_token_fetch_success", {
                "requestedModel": model,
                "matchedModel": result.get("model"),
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "sourceEndpoint": result.get("sourceEndpoint"),
                "fetchMethod": result.get("fetchMethod"),
                "fetchAttempts": fetch_attempts,
            })

            try:
                if hasattr(self, "_remember_recent_model_in_settings"):
                    self.settings = self._remember_recent_model_in_settings(merged, model, result)
                else:
                    self.settings = merged
                if hasattr(self, "_save_json"):
                    self._save_json(SETTINGS_FILE, self.settings)
                result["recentModels"] = self.settings.get("recentModels", []) if isinstance(self.settings, dict) else []
            except Exception as save_err:
                log_debug("model_token_fetch_save_recent_warning", {"error": str(save_err)})
            return result
        except Exception as global_err:
            log_debug("model_token_fetch_global_exception", {"error": str(global_err), "traceback": _traceback.format_exc()[-8000:]})
            return {"ok": False, "error": f"Token limit fetch crashed before completing: {global_err}. Open Debug Log and copy the latest model_token_fetch_* entries.", "debugLogPath": str(_fallback_log_file())}


    # camelCase aliases for PyWebView builds that expose names differently
    def fetchModelTokenLimits(self, settings=None):
        return self.fetch_model_token_limits(settings)

    def _remember_recent_model_in_settings(self, settings=None, model_name=None, token_info=None):
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        name = self._clean_model_name(model_name or settings.get("model"))
        if not name:
            return settings
        token_info = token_info or {}
        existing = settings.get("recentModels") if isinstance(settings.get("recentModels"), list) else []
        now_ts = time.time()
        merged = []
        seen = {name.casefold()}
        entry = {"name": name, "lastUsed": now_ts}
        for src_key, dst_key in (("maxInputTokens", "maxInputTokens"), ("max_input_tokens", "maxInputTokens"), ("maxOutputTokens", "maxOutputTokens"), ("max_output_tokens", "maxOutputTokens")):
            try:
                val = token_info.get(src_key)
                if val not in (None, ""):
                    entry[dst_key] = int(val)
            except Exception:
                pass
        if "maxInputTokens" not in entry:
            try:
                entry["maxInputTokens"] = int(settings.get("maxInputTokens") or 0)
            except Exception:
                pass
        if "maxOutputTokens" not in entry:
            try:
                entry["maxOutputTokens"] = int(settings.get("maxOutputTokens") or 0)
            except Exception:
                pass
        merged.append(entry)
        for item in existing:
            if isinstance(item, dict):
                old_name = self._clean_model_name(item.get("name") or item.get("model") or item.get("id"))
            else:
                old_name = self._clean_model_name(item)
            if not old_name or old_name.casefold() in seen:
                continue
            seen.add(old_name.casefold())
            if isinstance(item, dict):
                old = dict(item)
                old["name"] = old_name
                merged.append(old)
            else:
                merged.append({"name": old_name, "lastUsed": 0})
        settings["recentModels"] = merged[:30]
        return self._normalise_settings(settings)

    def remember_recent_model(self, settings=None, model_name=None, token_info=None):
        self.settings = self._remember_recent_model_in_settings(settings, model_name, token_info)
        self._save_json(SETTINGS_FILE, self.settings)
        return {"ok": True, "settings": self.settings, "recentModels": self.settings.get("recentModels", [])}

    def rememberRecentModel(self, settings=None, model_name=None, token_info=None):
        return self.remember_recent_model(settings, model_name, token_info)

    def save_settings(self, settings):
        incoming = dict(settings or {})
        requested_data_root = str(incoming.get("dataFilesFolder") or "").strip()
        data_root_result = None
        if requested_data_root:
            try:
                requested_path = Path(requested_data_root).expanduser().resolve()
                if requested_path != USER_DATA_ROOT.resolve():
                    data_root_result = self._copy_user_data_to(requested_path)
            except Exception as e:
                data_root_result = {"ok": False, "error": f"Could not process data folder: {e}"}
        self.settings = self._normalise_settings({**self.settings, **incoming})
        self.settings = self._remember_recent_model_in_settings(self.settings, self.settings.get("model"), {
            "maxInputTokens": self.settings.get("maxInputTokens"),
            "maxOutputTokens": self.settings.get("maxOutputTokens"),
        })
        self.settings["dataFilesFolder"] = str(USER_DATA_ROOT if not data_root_result or not data_root_result.get("ok") else Path(requested_data_root).expanduser().resolve())
        self._save_json(SETTINGS_FILE, self.settings)
        mobile_result = self._apply_mobile_server_settings(self.settings, save=False)
        result = {"ok": True, "settings": self.settings, "mobileServer": mobile_result}
        if data_root_result:
            result["dataFolder"] = data_root_result
            result["restartRequired"] = bool(data_root_result.get("restartRequired"))
        return result

    def _mobile_public_host_urls(self, host, port):
        urls = []
        shown_host = "127.0.0.1" if str(host or "") in {"0.0.0.0", "", "::"} else str(host)
        urls.append(f"http://{shown_host}:{port}/mobile.html")
        if shown_host in {"127.0.0.1", "localhost"}:
            try:
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                probe.settimeout(0.2)
                probe.connect(("8.8.8.8", 80))
                lan_ip = probe.getsockname()[0]
                probe.close()
                if lan_ip and lan_ip not in {"127.0.0.1", shown_host}:
                    urls.append(f"http://{lan_ip}:{port}/mobile.html")
            except Exception:
                pass
        return urls

    def _mobile_server_auth_ok(self, handler):
        code = str((self.settings or {}).get("mobileServerAccessCode") or "").strip()
        if not code:
            return True
        try:
            parsed = urllib.parse.urlparse(handler.path)
            query = urllib.parse.parse_qs(parsed.query)
            supplied = ""
            if query.get("token"):
                supplied = str(query.get("token", [""])[0] or "")
            if not supplied:
                supplied = str(handler.headers.get("X-CCF-Mobile-Token") or "")
            return supplied == code
        except Exception:
            return False

    def _mobile_send_json(self, handler, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-CCF-Mobile-Token")
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def _mobile_send_file(self, handler, path, content_type):
        try:
            raw = Path(path).read_bytes()
        except Exception:
            self._mobile_send_json(handler, {"ok": False, "error": "mobile.html could not be found in the bundled frontend folder."}, 404)
            return
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def _mobile_read_json(self, handler):
        try:
            length = int(handler.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = handler.rfile.read(min(length, 1_000_000)).decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
        except Exception as e:
            raise ValueError(f"Invalid JSON request: {e}")

    def _mobile_generate_character(self, concept, client_note=""):
        concept = str(concept or "").strip()
        if not concept:
            return {"ok": False, "error": "Enter a Main Concept first."}
        if not self._mobile_generation_lock.acquire(blocking=False):
            return {"ok": False, "error": "A mobile generation is already running. Wait for it to finish before starting another."}
        old_settings = dict(self.settings or {})
        try:
            local_settings = self._normalise_settings({**old_settings, "cardMode": "single", "sharedScenePolicy": "ai_reconcile"})
            local_template = json.loads(json.dumps(self.template or DEFAULT_TEMPLATE))
            generate_res = self.generate(concept, local_template, local_settings)
            if not generate_res.get("ok"):
                return generate_res
            output = str(generate_res.get("output") or "").strip()
            name = self._extract_name(output) or self._extract_output_name(output, "Mobile Card") or "Mobile Card"
            workspace = {
                "name": name,
                "concept": concept,
                "output": output,
                "template": local_template,
                "settings": local_settings,
                "qnaAnswers": generate_res.get("qaAnswers") or "",
                "builderState": {},
                "generatedImages": [],
                "emotionImages": [],
                "mobileGenerationNote": str(client_note or "")[:1000],
                "characterTabs": [{"title": name, "output": output, "qnaAnswers": generate_res.get("qaAnswers") or ""}],
                "conceptTabs": [{"title": name, "concept": concept, "visionDescription": "", "visionImagePath": "", "conceptAttachments": [], "builderState": {}}],
                "manualTabs": [],
                "activeConceptTabIndex": 0,
                "activeManualGuideTabIndex": 0,
            }
            save_res = self.save_character_workspace(workspace)
            if not save_res.get("ok"):
                return save_res
            self._log_event("mobile_generation_saved", {"name": save_res.get("name"), "project": save_res.get("projectPath")})
            return {
                "ok": True,
                "name": save_res.get("name") or name,
                "projectPath": save_res.get("projectPath") or "",
                "cardPath": save_res.get("cardPath") or "",
                "outputPreview": output[:1800],
                "qaPreview": str(generate_res.get("qaAnswers") or "")[:1800],
                "validation": generate_res.get("validation") or {},
            }
        finally:
            # Mobile generation forces a one-card route internally, but it should not
            # overwrite the user's desktop Card Mode or other current settings.
            self.settings = self._normalise_settings(old_settings)
            self._save_json(SETTINGS_FILE, self.settings)
            try:
                self._mobile_generation_lock.release()
            except Exception:
                pass

    def _mobile_make_handler(self):
        api = self

        class MobileHandler(http.server.BaseHTTPRequestHandler):
            server_version = "CharacterCardForgeMobile/1.0"

            def log_message(self, fmt, *args):
                try:
                    api._log_event("mobile_server_request", {"client": self.client_address[0] if self.client_address else "", "message": fmt % args})
                except Exception:
                    pass

            def do_OPTIONS(self):
                api._mobile_send_json(self, {"ok": True})

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path or "/"
                if path in {"/", "/mobile.html"}:
                    api._mobile_send_file(self, APP_DIR / "frontend" / "mobile.html", "text/html; charset=utf-8")
                    return
                if path == "/api/status":
                    status = api.mobile_server_status()
                    status["authRequired"] = bool(str((api.settings or {}).get("mobileServerAccessCode") or "").strip())
                    status["authenticated"] = api._mobile_server_auth_ok(self)
                    api._mobile_send_json(self, status)
                    return
                api._mobile_send_json(self, {"ok": False, "error": "Not found."}, 404)

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/api/generate":
                    api._mobile_send_json(self, {"ok": False, "error": "Not found."}, 404)
                    return
                if not api._mobile_server_auth_ok(self):
                    api._mobile_send_json(self, {"ok": False, "error": "Invalid or missing mobile access code."}, 401)
                    return
                try:
                    payload = api._mobile_read_json(self)
                    res = api._mobile_generate_character(payload.get("concept") or "", payload.get("note") or "")
                    api._mobile_send_json(self, res, 200 if res.get("ok") else 400)
                except Exception as e:
                    api._mobile_send_json(self, {"ok": False, "error": str(e)}, 500)

        return MobileHandler

    def _start_mobile_server_locked(self, settings):
        host = str(settings.get("mobileServerHost") or "0.0.0.0").strip() or "0.0.0.0"
        port = int(settings.get("mobileServerPort") or 8787)
        if self._mobile_server is not None:
            if self._mobile_server.server_address[0] == host and int(self._mobile_server.server_address[1]) == port:
                return self.mobile_server_status()
            self._stop_mobile_server_locked()
        handler = self._mobile_make_handler()
        class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True
        server = ThreadingServer((host, port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="CCFMobileServer")
        thread.start()
        self._mobile_server = server
        self._mobile_server_thread = thread
        self._mobile_server_port = port
        self._log_event("mobile_server_started", {"host": host, "port": port, "urls": self._mobile_public_host_urls(host, port)})
        return self.mobile_server_status()

    def _stop_mobile_server_locked(self):
        server = self._mobile_server
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        self._mobile_server = None
        self._mobile_server_thread = None
        self._mobile_server_port = None
        self._log_event("mobile_server_stopped", {})
        return self.mobile_server_status()

    def _apply_mobile_server_settings(self, settings=None, save=False):
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        if save:
            self.settings = settings
            self._save_json(SETTINGS_FILE, self.settings)
        try:
            if settings.get("mobileServerEnabled"):
                return self._start_mobile_server_locked(settings)
            return self._stop_mobile_server_locked()
        except Exception as e:
            self._log_event("mobile_server_error", {"error": str(e), "host": settings.get("mobileServerHost"), "port": settings.get("mobileServerPort")})
            return {"ok": False, "running": False, "error": str(e)}

    def start_mobile_server(self, settings=None):
        merged = self._normalise_settings({**self.settings, **(settings or {}), "mobileServerEnabled": True})
        self.settings = merged
        self._save_json(SETTINGS_FILE, self.settings)
        return self._apply_mobile_server_settings(merged, save=False)

    def stop_mobile_server(self):
        self.settings["mobileServerEnabled"] = False
        self._save_json(SETTINGS_FILE, self.settings)
        return self._apply_mobile_server_settings(self.settings, save=False)

    def mobile_server_status(self):
        running = self._mobile_server is not None
        host = str((self.settings or {}).get("mobileServerHost") or "0.0.0.0")
        port = int((self.settings or {}).get("mobileServerPort") or (self._mobile_server_port or 8787))
        return {
            "ok": True,
            "running": running,
            "host": host,
            "port": port,
            "urls": self._mobile_public_host_urls(host, port) if running else [],
            "authRequired": bool(str((self.settings or {}).get("mobileServerAccessCode") or "").strip()),
        }

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

    def _estimate_card_browser_tokens(self, text):
        """Fast browser-card token estimate without chat-wrapper overhead."""
        text = str(text or "")
        if not text.strip():
            return 0
        return max(1, int(len(text) / 4))

    def _split_card_output_sections_for_tokens(self, output):
        """Split a generated card into rough titled sections for browser token stats.

        Cards commonly start with a separator line. The beta11 splitter only
        matched separators that had a newline before them, so a leading
        separator could become a fake "Other" section. This splitter treats
        separator lines at the beginning, middle, or end the same way.
        """
        text = str(output or "")
        if not text.strip():
            return []
        chunks = re.split(r"(?:^|\n)\s*-{3,}\s*(?:\n|$)", text)
        sections = []
        for chunk in chunks:
            chunk = str(chunk or "").strip()
            if not chunk:
                continue
            lines = [line.rstrip() for line in chunk.splitlines()]
            while lines and not lines[0].strip():
                lines.pop(0)
            if not lines:
                continue
            embedded_heading_re = re.compile(
                r"^(?:Name|Description|Personality|Sexual Traits|Sexual Profile|Background|Backstory|Scenario|"
                r"First Message|Alternative First Messages|Alternate First Messages|Example Dialogues?|Example Messages?|"
                r"Lorebook Entries?|Lore Book Entries?|Tags|State Tracking|Stable Diffusion Prompt|SD Prompt|Natural English Image Prompt|Natural Image Prompt|Image Prompt)\s*:?\s*$",
                re.IGNORECASE,
            )
            starts = [0]
            for idx in range(1, len(lines)):
                if embedded_heading_re.match(lines[idx].strip()):
                    starts.append(idx)
            starts.append(len(lines))
            for pos in range(len(starts) - 1):
                start = starts[pos]
                end = starts[pos + 1]
                if start >= end:
                    continue
                title = lines[start].strip().strip(":") or "Other"
                body = "\n".join(lines[start + 1:end]).strip()
                section_text = (title + ("\n" + body if body else "")).strip()
                if section_text:
                    sections.append((title, section_text))
        return sections

    def _card_browser_token_counts(self, output):
        """Return total and section-level token estimates for Character Browser cards."""
        text = str(output or "")
        counts = {
            "description": 0,
            "personality": 0,
            "sexualTraits": 0,
            "background": 0,
            "scenario": 0,
            "greetings": 0,
            "exampleMessages": 0,
            "lorebook": 0,
            "tags": 0,
            "stateTracking": 0,
            "stableDiffusion": 0,
            "other": 0,
        }
        for title, section_text in self._split_card_output_sections_for_tokens(text):
            key = "other"
            norm = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
            if norm in {"name", "description"} or norm.startswith("description"):
                key = "description"
            elif norm.startswith("personality"):
                key = "personality"
            elif norm.startswith("sexual trait") or norm.startswith("sexuality") or norm in {"sexual traits", "sexual profile"}:
                key = "sexualTraits"
            elif norm.startswith("background") or norm.startswith("backstory"):
                key = "background"
            elif norm.startswith("scenario"):
                key = "scenario"
            elif norm.startswith("first message") or norm.startswith("alternative first messages") or norm.startswith("alternate first messages") or norm in {"greeting", "greetings"}:
                key = "greetings"
            elif norm.startswith("example dialogue") or norm.startswith("example message") or norm.startswith("example dialogues") or norm.startswith("example messages"):
                key = "exampleMessages"
            elif norm.startswith("lorebook") or norm.startswith("lore book"):
                key = "lorebook"
            elif norm == "tags" or norm.startswith("tag"):
                key = "tags"
            elif norm.startswith("state tracking") or norm in {"state", "stats", "tracking"}:
                key = "stateTracking"
            elif norm.startswith("stable diffusion") or norm.startswith("sd prompt") or norm.startswith("image prompt") or norm.startswith("natural english image prompt") or norm.startswith("natural image prompt") or norm.startswith("natural prompt"):
                key = "stableDiffusion"
            counts[key] += self._estimate_card_browser_tokens(section_text)
        # Keep the headline total mathematically consistent with the rows
        # displayed in the Character Browser token details panel. Earlier builds
        # estimated the full raw card text separately, so separators/blank lines
        # could make the headline total look larger than the visible section
        # rows. For the browser UI, a sum-of-sections total is clearer and
        # debuggable: every token shown belongs to a displayed bucket.
        total = sum(int(v or 0) for v in counts.values())
        return {"total": total, "sections": counts, "version": 3}

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

    def _allowed_tags_from_settings(self, settings=None):
        settings = settings or self.settings or {}
        raw = settings.get("allowedTags") or ""
        if isinstance(raw, list):
            parts = raw
        else:
            parts = re.split(r"[,\n]+", str(raw or ""))
        out = []
        seen = set()
        for item in parts:
            tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(item or "").strip().lower()).strip("-")
            if tag and tag not in seen:
                seen.add(tag)
                out.append(tag)
        return out

    def _apply_restricted_tags_to_output(self, output, template=None, settings=None):
        settings = settings or self.settings or {}
        if not settings.get("restrictTags"):
            return output
        allowed = self._allowed_tags_from_settings(settings)
        if not allowed:
            return output
        current = self._extract_tags_from_output(output, template or self.template)
        allowed_set = {t.lower() for t in allowed}
        filtered = []
        seen = set()
        for tag in current:
            key = str(tag or "").strip().lower()
            if key in allowed_set and key not in seen:
                seen.add(key)
                filtered.append(key)
        return self._replace_tags_section(output, filtered, template or self.template)

    def _first_message_style_text(self, settings):
        style_key = str((settings or {}).get("firstMessageStyle") or "cinematic").strip()
        if style_key == "custom":
            name = str((settings or {}).get("firstMessageCustomStyle") or "Custom").strip() or "Custom"
            base = f"Custom style: {name}"
        else:
            base = FIRST_MESSAGE_STYLES.get(style_key, FIRST_MESSAGE_STYLES["cinematic"])
        instructions = str((settings or {}).get("firstMessageCustomInstructions") or "").strip()
        if instructions:
            base += f"\nCustom first-message instructions: {instructions}"
        return base

    def _alt_first_message_style_text(self, settings, idx, fallback_style_text):
        settings = settings or {}
        alt_styles = settings.get("alternateFirstMessageStyles") or []
        alt_custom_styles = settings.get("alternateFirstMessageCustomStyles") or []
        alt_instructions = settings.get("alternateFirstMessageInstructions") or []
        alt_key = alt_styles[idx] if idx < len(alt_styles) else ""
        if alt_key == "custom":
            name = str(alt_custom_styles[idx] if idx < len(alt_custom_styles) else "").strip() or "Custom"
            text = f"Custom style: {name}"
        elif alt_key:
            text = FIRST_MESSAGE_STYLES.get(alt_key, fallback_style_text)
        else:
            text = fallback_style_text
        instructions = str(alt_instructions[idx] if idx < len(alt_instructions) else "").strip()
        if instructions:
            text += f"\nCustom instructions for this alternative greeting: {instructions}"
        return text

    def build_prompt(self, concept, template=None, settings=None, chunk=None):
        template = template or self.template
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        alt_count = int(settings.get("alternateFirstMessages") or 0)
        alt_section_enabled = any(
            sec.get("id") == "alternate_first_messages" and sec.get("enabled", True)
            for sec in template.get("sections", [])
        )
        style_text = self._first_message_style_text(settings)
        lines = []
        lines.append("You are a fictional character generator and formatter.")
        lines.append("Follow the user-configured template exactly. Do not invent disabled sections.")
        lines.append("All primary characters and romantic/sexual participants must be 18+.")
        lines.append("If a source concept conflicts with the age rule, age characters up and adjust the setting.")
        if settings.get("cardMode") == "group_cards":
            lines.append("CARD MODE: MULTI-CARD GROUP CARD — CURRENT PASS IS ONE MEMBER CARD ONLY.")
            lines.append("Generate exactly one importable character card for the focused group member named in the concept instructions for this pass.")
            lines.append("The focused character is the card's {{char}}. Do not make this member card a group/multi-character card; the group card will be assembled after member cards are generated.")
            lines.append("Other important members from the original concept must be kept as Lorebook Entries, relationship context, background/supporting cast references, or scenario hooks so the focused member can still remember and refer to them.")
            lines.append("Name, Description, Personality, Scenario, First Message, Example Dialogues, State Tracking, Stable Diffusion Prompt, and Natural English Image Prompt must all focus on the focused member only.")
            lines.append("Tags should describe the focused member/card, not the whole group, unless the Tags section is disabled.")
        elif settings.get("cardMode") == "split_cards":
            lines.append("CARD MODE: SPLIT INTO MULTIPLE CARDS — CURRENT PASS IS ONE CHARACTER ONLY.")
            lines.append("Generate exactly one importable character card for the focused main character named in the concept instructions for this pass.")
            lines.append("The focused character is the card's {{char}}. Do not make the card a group/multi-character card.")
            lines.append("Other important characters from the original concept must be kept as Lorebook Entries or background/supporting cast references so {{char}} can still remember and refer to them.")
            lines.append("Name, Description, Personality, Scenario, First Message, Example Dialogues, State Tracking, Stable Diffusion Prompt, and Natural English Image Prompt must all focus on the focused character only.")
            lines.append("Tags should describe the focused character/card, not the whole group, unless the Tags section is disabled.")
        elif settings.get("cardMode") == "multi":
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
        lines.append("SOURCE CONCEPT FIDELITY RULES — the CHARACTER CONCEPT is authoritative. Preserve the user's named characters, relationships, premise, setting, scenario hook, visual details, clothing, props, captions/messages, and requested emotional/sexual dynamics unless they conflict with the 18+ rule.")
        lines.append("Do not replace the user's scenario with a different backstory, different character name, different relationship, different outfit, or unrelated opening. Clean up and expand what the user provided; do not reinvent it.")
        lines.append("If CHARACTER CONCEPT contains a heading such as First Message, Greeting, Opening, or Scenario, use those beats as the mandatory source for the generated Scenario and First Message. You may polish grammar, pacing, and prose, but must keep the same situation, named characters, power dynamic, message/caption if present, and opening confrontation.")
        lines.append("If temporary generation notes are present, treat them as mandatory one-off direction. They clarify the current card and override generic style assumptions.")
        lines.append(f"Token budget settings: maximum input context is {settings.get('maxInputTokens')} tokens; maximum generated output is {settings.get('maxOutputTokens')} tokens.")
        lines.append("Use the available input budget efficiently. Do not exceed the requested output structure.")
        lines.append(f"FIRST MESSAGE STYLE REQUIREMENT: use this style for the main First Message: {style_text}")
        if alt_count > 0:
            for idx in range(alt_count):
                alt_text = self._alt_first_message_style_text(settings, idx, style_text)
                lines.append(f"ALTERNATIVE FIRST MESSAGE {idx + 1} STYLE / INSTRUCTIONS: {alt_text}")
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
            if section.get("id") == "tags" and settings.get("restrictTags"):
                allowed_tags = self._allowed_tags_from_settings(settings)
                if allowed_tags:
                    lines.append("RESTRICTED TAG MODE: choose tags ONLY from this allowed list. Do not invent new tags.")
                    lines.append("Allowed tags: " + ", ".join(allowed_tags))
            if section.get("id") == "stable_diffusion":
                lines.append("Return only these labels and their comma-separated prompt text: Positive Prompt: ... and Negative Prompt: ...")
                lines.append("Do not echo helper text, ordering guidance, field descriptions, or explanations inside the Stable Diffusion Prompt or Natural English Image Prompt sections.")
            if section.get("id") == "first_message":
                lines.append(f"First message style/instructions: {style_text}")
            if section.get("id") == "example_dialogues":
                lines.append("IMPORTANT: Use exactly ONE <START> marker total, placed at the very beginning of this section.")
                lines.append("After that single <START>, write one continuous example conversation with each speaker on a separate line, such as {{user}}: ... and {{char}}: ...")
                lines.append("Do not start each exchange with another <START>; multiple <START> markers break Front Porch AI import formatting.")
            if section.get("id") == "alternate_first_messages":
                if alt_count > 0:
                    lines.append(f"Generate exactly {alt_count} alternative first messages in addition to the main First Message.")
                    lines.append("Inside this section, label each item exactly as: Alternative First Message 1, Alternative First Message 2, etc.")
                    for idx in range(alt_count):
                        alt_text = self._alt_first_message_style_text(settings, idx, style_text)
                        lines.append(f"Alternative First Message {idx + 1} style/instructions: {alt_text}")
                    lines.append("Each alternative must be a complete opening message, not a short summary.")
                    lines.append("Do not repeat the main First Message inside this section, and do not put alternatives inside the main First Message section.")
                else:
                    lines.append("No alternative first messages requested. Leave this section blank or write: None.")
                lines.append(f"Alternative style: {style_text}")
            fields = [f for f in section.get("fields", []) if f.get("enabled", True)]
            for field in fields:
                label = field.get("label", "Field")
                hint = field.get("hint", "")
                if section.get("id") == "stable_diffusion":
                    lines.append(f"- {label}:")
                else:
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

    def _emit_frontend_event(self, event_name, payload=None):
        """Best-effort UI callback used for streaming/progress updates."""
        try:
            if not getattr(self, "window", None):
                return
            js = f"window.{event_name} && window.{event_name}({json.dumps(payload or {}, ensure_ascii=False)});"
            self.window.evaluate_js(js)
        except Exception:
            # UI updates must never break generation.
            pass

    def _stream_target_for_attempt(self, settings, attempt_label):
        # Only stream into visible UI text boxes when the caller explicitly asks for it.
        # Several internal AI jobs also use the generic "primary" attempt label
        # (emotion prompt generation, JSON cleanup, tag suggestions, browser summaries).
        # The old inference treated any "primary" response as final card output,
        # which could overwrite the Full Text Output with internal JSON prompts.
        explicit = str((settings or {}).get("_streamTarget") or "").strip().lower()
        if explicit in {"qa", "output"}:
            return explicit
        return ""

    def _emit_stream_chunk(self, settings, attempt_label, chunk, full_text=None):
        if not chunk:
            return
        target = self._stream_target_for_attempt(settings, attempt_label)
        if not target:
            return
        self._emit_frontend_event("ccfStreamUpdate", {
            "target": target,
            "chunk": chunk,
            "text": full_text or "",
            "attempt": attempt_label,
        })

    def _read_streaming_chat_response(self, resp, settings, attempt_label):
        content_parts = []
        for raw_line in resp:
            self._raise_if_cancelled()
            try:
                line = raw_line.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            delta = choice.get("delta") or {}
            chunk = delta.get("content")
            if chunk is None:
                msg = choice.get("message") or {}
                chunk = msg.get("content")
            if chunk:
                content_parts.append(str(chunk))
                self._emit_stream_chunk(settings, attempt_label, str(chunk), "".join(content_parts))
        return "".join(content_parts).strip()

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
        if settings.get("streamAi"):
            payload["stream"] = True
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        self._log_event("text_generation_request", {"attempt": attempt_label, "model": model})
        try:
            with self._urlopen_with_retries(req, settings, timeout=180, label="Text generation") as resp:
                self._raise_if_cancelled()
                if settings.get("streamAi"):
                    content = self._read_streaming_chat_response(resp, settings, attempt_label)
                    self._raise_if_cancelled()
                    self._log_event("text_generation_response", {"attempt": attempt_label, "model": model, "streamed": True, "looks_like_refusal": self._looks_like_text_refusal(content), "preview": content[:800]})
                    return content
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
        style_text = self._first_message_style_text(settings)
        chunk_sections = {
            "core": "Name, Description, Personality, Sexual Traits, Background",
            "scene": "Scenario, First Message, Alternative First Messages, Example Dialogues",
            "extras": "Lorebook Entries, Tags, Custom System Prompt, State Tracking, Stable Diffusion Prompt, Natural English Image Prompt",
        }
        lines = [
            "Compact Lite generation for an 8k-context model. Return only the requested card sections.",
            "Use separator line ------------------------------------------------ before every section.",
            "All characters and sexual/romantic participants are 18+ fictional adults.",
            "Card mode: " + ("SPLIT INTO MULTIPLE CARDS — ONE FOCUSED CHARACTER FOR THIS PASS" if settings.get("cardMode") == "split_cards" else ("MULTI-CHARACTER SINGLE CARD" if settings.get("cardMode") == "multi" else "SINGLE CHARACTER CARD")),
            "Requested sections this pass: " + chunk_sections.get(chunk, chunk_sections["core"]),
            "First Message style: " + style_text,
            f"Alternative First Messages requested: {alt_count}",
            "Keep concise but complete. Do not add unrelated commentary.",
            "SOURCE CONCEPT FIDELITY: preserve the user's named characters, relationships, scenario hook, visual details, clothing, captions/messages, and explicit First Message beats. Clean up and expand; do not replace them with unrelated names, backstory, outfit, or opening.",
            "If temporary generation notes are present, treat them as mandatory direction for this card.",
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
            "state_tracking": "State Tracking", "stable_diffusion": "Stable Diffusion Prompt", "natural_image_prompt": "Natural English Image Prompt",
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

    def _qa_enabled_questions(self, template):
        template = self._normalise_template(template or self.template)
        qa = template.get("qa", {}) or {}
        if not qa.get("enabled"):
            return []
        return [str(q).strip() for q in qa.get("questions", []) if str(q).strip()]

    def _qa_answered_indexes(self, answers, question_count):
        text = str(answers or "")
        answered = set()
        for match in re.finditer(r"(?im)^\s*A\s*(\d{1,3})\s*[:：\-]\s*(.+)$", text):
            try:
                idx = int(match.group(1))
            except Exception:
                continue
            body = (match.group(2) or "").strip()
            if 1 <= idx <= question_count and body and not re.fullmatch(r"(?is)(?:n/?a|none|skip(?:ped)?|unknown|no answer)[.\s]*", body):
                answered.add(idx)
        if not answered:
            for i in range(1, question_count + 1):
                if re.search(rf"(?is)(?:^|\n)\s*(?:Q\s*)?{i}\s*[:.)\-].{{0,700}}?(?:A\s*{i}\s*[:：\-]|Answer\s*[:：\-])\s*\S", text):
                    answered.add(i)
        return answered

    def _qa_missing_indexes(self, answers, questions):
        answered = self._qa_answered_indexes(answers, len(questions))
        return [i for i in range(1, len(questions) + 1) if i not in answered]

    def _qa_normalise_for_compare(self, text):
        return re.sub(r"[^a-z0-9]+", "", str(text or "").casefold())

    def _qa_deduplicate_question_list(self, questions):
        """Return questions once, preserving order, with exact-normalized duplicates removed.

        One-off custom questions can enter through both frontend temporary templates
        and backend compatibility arguments. Keeping duplicated question text causes
        later repair passes to renumber and pair answers against the wrong slot,
        especially for card-specific custom Q&A at the end of a long interview.
        """
        cleaned = []
        seen = set()
        duplicates = []
        for idx, q in enumerate(questions or [], start=1):
            value = str(q or "").strip()
            if not value:
                continue
            key = self._qa_normalise_for_compare(value)
            if key and key in seen:
                duplicates.append({"sourceIndex": idx, "question": value[:240]})
                continue
            if key:
                seen.add(key)
            cleaned.append(value)
        return cleaned, {"deduplicated": bool(duplicates), "removed": len(duplicates), "duplicates": duplicates[:20]}

    def _qa_clean_extra_questions_for_template(self, template, extra_questions):
        """Normalize per-generation custom Q&A and remove questions already in template.

        This keeps custom questions from being appended twice when a newer frontend
        sends a temporary template while an older/newer backend compatibility path
        also receives extra_questions positionally.
        """
        if isinstance(extra_questions, str):
            raw = [q.strip() for q in re.split(r"\r?\n", extra_questions) if q.strip()]
        elif isinstance(extra_questions, (list, tuple)):
            raw = [str(q or "").strip() for q in extra_questions if str(q or "").strip()]
        else:
            raw = []
        if not raw:
            return []
        existing, _ = self._qa_deduplicate_question_list(self._qa_enabled_questions(template))
        seen = {self._qa_normalise_for_compare(q) for q in existing if self._qa_normalise_for_compare(q)}
        cleaned = []
        for q in raw:
            key = self._qa_normalise_for_compare(q)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            cleaned.append(q)
        return cleaned

    def _qa_find_matching_question_index(self, text, questions):
        """Find the 1-based template question index matching a model-emitted Q body."""
        body = str(text or "").strip()
        if not body or not questions:
            return None
        first = body.splitlines()[0].strip()
        first = re.sub(r"^\s*Q\s*\d{1,4}\s*[:：\-]\s*", "", first).strip()
        body_cmp = self._qa_normalise_for_compare(first)
        if not body_cmp:
            return None
        best_idx = None
        best_ratio = 0.0
        try:
            from difflib import SequenceMatcher
        except Exception:
            SequenceMatcher = None
        for idx, q in enumerate(questions or [], start=1):
            expected = str(q or "").strip()
            expected_cmp = self._qa_normalise_for_compare(expected)
            if not expected_cmp:
                continue
            if body_cmp == expected_cmp:
                return idx
            min_prefix = max(18, min(80, int(len(expected_cmp) * 0.55)))
            if len(body_cmp) >= min_prefix and (body_cmp.startswith(expected_cmp[:min_prefix]) or expected_cmp.startswith(body_cmp[:min_prefix])):
                return idx
            if SequenceMatcher and len(body_cmp) >= 12:
                ratio = SequenceMatcher(None, body_cmp, expected_cmp).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = idx
        return best_idx if best_ratio >= 0.86 else None

    def _qa_reinsert_questions_if_model_used_q_as_answer(self, answers, questions):
        """Repair a common model failure where it outputs Q101: <answer> instead
        of Q101: <question> / A101: <answer>.

        Some models follow the numbering but stop echoing the original question
        after a long Q&A run. The app expects Q/A pairs, so this converts those
        malformed Q-only answer lines back into canonical pairs using the saved
        template questions as the source of truth.
        """
        raw = str(answers or "").strip()
        if not raw or not questions:
            return raw, {"repaired": False, "qOnlyAnswers": 0, "answerCount": 0}

        matches = list(re.finditer(r"(?im)^\s*([QA])\s*(\d{1,3})\s*[:：\-]\s*(.*)$", raw))
        if not matches:
            return raw, {"repaired": False, "qOnlyAnswers": 0, "answerCount": 0}

        parsed = {}
        q_only_answers = 0
        max_q = len(questions)
        for pos, match in enumerate(matches):
            label = (match.group(1) or "").upper()
            try:
                idx = int(match.group(2))
            except Exception:
                continue
            if idx < 1 or idx > max_q:
                continue
            body_start = match.start(3)
            body_end = matches[pos + 1].start() if pos + 1 < len(matches) else len(raw)
            body = raw[body_start:body_end].strip()
            if not body:
                continue
            item = parsed.setdefault(idx, {"questionSeen": "", "answer": "", "malformedQAnswer": False})
            if label == "A":
                if item["answer"]:
                    item["answer"] = (item["answer"].rstrip() + "\n" + body).strip()
                else:
                    item["answer"] = body
            else:
                expected_question = questions[idx - 1] if 0 <= idx - 1 < len(questions) else ""
                looks_like_question = self._qa_text_looks_like_question(body, expected_question)
                if looks_like_question:
                    item["questionSeen"] = body
                else:
                    # The model put the answer after a Q label. Keep it as the answer,
                    # then rebuild the real Q label from the template question list.
                    if not item["answer"]:
                        item["answer"] = body
                        item["malformedQAnswer"] = True
                        q_only_answers += 1
                    else:
                        item["questionSeen"] = body

        if not q_only_answers:
            return raw, {"repaired": False, "qOnlyAnswers": 0, "answerCount": len([v for v in parsed.values() if v.get("answer")])}

        blocks = []
        for idx in range(1, max_q + 1):
            item = parsed.get(idx, {})
            answer = str(item.get("answer") or "").strip()
            if not answer:
                continue
            answer = self._qa_strip_leading_duplicate_question(answer, questions[idx - 1])
            blocks.append(f"Q{idx}: {questions[idx - 1]}\nA{idx}: {answer}")

        repaired = "\n\n".join(blocks).strip()
        return repaired or raw, {"repaired": True, "qOnlyAnswers": q_only_answers, "answerCount": len(blocks)}

    def _qa_text_looks_like_question(self, text, expected_question):
        """Return true when a model-emitted Q body is really the template question.

        Models sometimes rewrite typos while echoing the question, so this uses a
        forgiving normalized comparison rather than exact text only.
        """
        body = str(text or "").strip()
        expected = str(expected_question or "").strip()
        if not body or not expected:
            return False
        body_first = body.splitlines()[0].strip()
        body_cmp = self._qa_normalise_for_compare(body_first)
        expected_cmp = self._qa_normalise_for_compare(expected)
        if not body_cmp or not expected_cmp:
            return False
        if body_cmp == expected_cmp:
            return True
        # Prefix matching must not treat very short answers like "No" or "b" as
        # a duplicated question just because they share the first character.
        min_prefix = max(18, min(80, int(len(expected_cmp) * 0.55)))
        if len(body_cmp) >= min_prefix and body_cmp.startswith(expected_cmp[:min_prefix]):
            return True
        if len(body_cmp) >= min_prefix and expected_cmp.startswith(body_cmp[:min_prefix]):
            return True
        try:
            from difflib import SequenceMatcher
            return len(body_cmp) >= 12 and SequenceMatcher(None, body_cmp, expected_cmp).ratio() >= 0.82
        except Exception:
            return False

    def _qa_strip_leading_duplicate_question(self, answer, expected_question):
        """Remove duplicated question text that some models paste at the top of A lines."""
        text = str(answer or "").strip()
        if not text:
            return text
        lines = text.splitlines()
        changed = False
        while lines:
            first = lines[0].strip()
            first = re.sub(r"^\s*Q\s*\d{1,3}\s*[:：\-]\s*", "", first).strip()
            # Do not require a literal question mark here. Some templates use
            # prompts/instructions rather than grammatical questions, and models
            # often echo typo-corrected custom questions at the top of A lines.
            if self._qa_text_looks_like_question(first, expected_question):
                lines = lines[1:]
                changed = True
                while lines and not lines[0].strip():
                    lines = lines[1:]
                continue
            break
        return "\n".join(lines).strip() if changed else text

    def _qa_canonicalise_order_and_questions(self, answers, questions):
        """Canonicalise Q&A output into template question order.

        This pass is deliberately stricter than the raw model output. It fixes:
        - retry answers appended out of order,
        - Q<number>: <answer> malformed rows,
        - duplicated custom questions emitted with extra numbering,
        - answers whose A-number follows a duplicated/reworded Q body and would
          otherwise slide under the wrong question.
        """
        raw = str(answers or "").strip()
        if not raw or not questions:
            return raw, {"repaired": False, "reason": "empty", "answerCount": 0}

        questions, dedupe_info = self._qa_deduplicate_question_list(questions)
        if not questions:
            return raw, {"repaired": False, "reason": "no_questions", "answerCount": 0}

        matches = list(re.finditer(r"(?im)^\s*([QA])\s*(\d{1,4})\s*[:：\-]\s*(.*)$", raw))
        if not matches:
            return raw, {"repaired": False, "reason": "no_labels", "answerCount": 0}

        max_q = len(questions)
        parsed = {}
        original_answer_order = []
        duplicate_question_answers = 0
        remapped_by_question_text = 0
        malformed_q_answers = 0
        duplicate_answers_removed = 0
        last_q_label = None
        last_q_mapped_idx = None

        def add_answer(mapped_idx, body):
            nonlocal duplicate_question_answers, duplicate_answers_removed
            if not mapped_idx or mapped_idx < 1 or mapped_idx > max_q:
                return
            cleaned = self._qa_strip_leading_duplicate_question(body, questions[mapped_idx - 1]).strip()
            if cleaned != str(body or "").strip():
                duplicate_question_answers += 1
            if not cleaned:
                return
            item = parsed.setdefault(mapped_idx, {"answers": [], "normAnswers": set(), "questionSeen": ""})
            norm = self._qa_normalise_for_compare(cleaned)
            no_answer_re = r"(?is)^(?:n/?a|none|skip(?:ped)?|unknown|no answer)[.\s]*$"
            existing_answers = [str(a or "").strip() for a in item.get("answers", []) if str(a or "").strip()]
            if existing_answers:
                # If a question appears twice because a custom one-off question was
                # duplicated, keep the first real answer instead of doubling text or
                # sliding a later answer under the same Q. Replace only placeholder
                # no-answer values with a real retry answer.
                if all(re.fullmatch(no_answer_re, a) for a in existing_answers) and not re.fullmatch(no_answer_re, cleaned):
                    item["answers"] = []
                    item["normAnswers"] = set()
                else:
                    duplicate_answers_removed += 1
                    return
            if norm and norm in item["normAnswers"]:
                duplicate_answers_removed += 1
                return
            if norm:
                item["normAnswers"].add(norm)
            item["answers"].append(cleaned)
            original_answer_order.append(mapped_idx)

        for pos, match in enumerate(matches):
            label = (match.group(1) or "").upper()
            try:
                raw_idx = int(match.group(2))
            except Exception:
                continue
            body_start = match.start(3)
            body_end = matches[pos + 1].start() if pos + 1 < len(matches) else len(raw)
            body = raw[body_start:body_end].strip()
            if not body:
                continue

            if label == "Q":
                # Trust a valid numeric Q label first when its body matches that
                # exact template slot. Many Q&A sets have very similar questions
                # ("What kind of person..."), so fuzzy search before label trust
                # can remap Q19 to Q18 and slide answers out of alignment.
                if 1 <= raw_idx <= max_q and self._qa_text_looks_like_question(body, questions[raw_idx - 1]):
                    matched_idx = raw_idx
                else:
                    matched_idx = self._qa_find_matching_question_index(body, questions)
                mapped_idx = matched_idx or (raw_idx if 1 <= raw_idx <= max_q else None)
                if matched_idx and matched_idx != raw_idx:
                    remapped_by_question_text += 1
                last_q_label = raw_idx
                last_q_mapped_idx = mapped_idx

                if mapped_idx and self._qa_text_looks_like_question(body, questions[mapped_idx - 1]):
                    parsed.setdefault(mapped_idx, {"answers": [], "normAnswers": set(), "questionSeen": ""})["questionSeen"] = body
                elif mapped_idx and 1 <= mapped_idx <= max_q:
                    # The model used Q<number> as the answer label.
                    malformed_q_answers += 1
                    add_answer(mapped_idx, body)
                continue

            # A label. Prefer the immediately preceding Q body mapping when the
            # A label corresponds to that Q label. This is what fixes duplicated
            # custom questions where the model emits extra/reworded Q numbers.
            mapped_idx = None
            if last_q_label == raw_idx and last_q_mapped_idx:
                mapped_idx = last_q_mapped_idx
            elif 1 <= raw_idx <= max_q:
                mapped_idx = raw_idx
            elif last_q_mapped_idx:
                mapped_idx = last_q_mapped_idx
            add_answer(mapped_idx, body)

        blocks = []
        seen_answer_indexes = []
        for idx in range(1, max_q + 1):
            item = parsed.get(idx) or {}
            answers_for_idx = [str(a or "").strip() for a in item.get("answers", []) if str(a or "").strip()]
            if not answers_for_idx:
                continue
            answer = "\n".join(answers_for_idx).strip()
            blocks.append(f"Q{idx}: {questions[idx - 1]}\nA{idx}: {answer}")
            seen_answer_indexes.append(idx)

        if not blocks:
            return raw, {"repaired": False, "reason": "no_answers", "answerCount": 0}

        canonical = "\n\n".join(blocks).strip()
        order_was_wrong = bool(original_answer_order and original_answer_order != sorted(original_answer_order))
        repaired = (
            canonical != raw
            or order_was_wrong
            or duplicate_question_answers > 0
            or malformed_q_answers > 0
            or remapped_by_question_text > 0
            or duplicate_answers_removed > 0
            or bool(dedupe_info.get("deduplicated"))
        )
        return canonical if repaired else raw, {
            "repaired": repaired,
            "answerCount": len(blocks),
            "firstAnswer": seen_answer_indexes[0] if seen_answer_indexes else None,
            "lastAnswer": seen_answer_indexes[-1] if seen_answer_indexes else None,
            "orderRepaired": order_was_wrong,
            "duplicateQuestionAnswersRemoved": duplicate_question_answers,
            "malformedQAnswersRepaired": malformed_q_answers,
            "remappedByQuestionText": remapped_by_question_text,
            "duplicateAnswersRemoved": duplicate_answers_removed,
            "questionDuplicatesRemoved": dedupe_info.get("removed", 0),
        }

    def _retry_missing_qa_answers(self, concept, questions, previous_answers, missing_indexes, settings):
        missing_lines = []
        for idx in missing_indexes:
            if 1 <= idx <= len(questions):
                missing_lines.append(f"{idx}. {questions[idx - 1]}")
        prompt = "\n".join([
            "The previous Q&A answer set skipped one or more required questions.",
            "Answer ONLY the missing questions below. Use the exact labels Q<number>: and A<number>:. Do not answer any other questions.",
            "Return only Q&A pairs. No markdown, no commentary.",
            "",
            "CHARACTER CONCEPT",
            concept.strip(),
            "",
            "PREVIOUS Q&A ANSWERS",
            str(previous_answers or "").strip() or "(none)",
            "",
            "MISSING QUESTIONS",
            "\n".join(missing_lines),
        ]).strip()
        check = self._context_check(prompt, settings, mode_label="Q&A missing-answer retry")
        if not check.get("ok"):
            raise RuntimeError(check.get("error", "Q&A missing-answer retry exceeds context window."))
        self._log_event("qa_generation_retry_request", {"missing": missing_indexes, "prompt": prompt})
        qa_settings = {**settings, "_streamTarget": "qa"}
        extra = self._chat(prompt, qa_settings).strip()
        self._log_event("qa_generation_retry_response", {"missing": missing_indexes, "answers": extra})
        return extra

    def _generate_template_qa(self, concept, template, settings):
        template = self._normalise_template(template or self.template)
        questions = self._qa_enabled_questions(template)
        questions, question_dedupe_info = self._qa_deduplicate_question_list(questions)
        if question_dedupe_info.get("deduplicated"):
            self._log_event("qa_generation_questions_deduplicated", question_dedupe_info)
        if not questions:
            return ""
        split_focus = bool(re.search(r"(?is)^\s*SPLIT-CARD GENERATION PASS\b.*?Focused main character for this card\s*:", concept or ""))
        lines = [
            "Before writing the final character card, interview the fictional character(s) to uncover deeper internal logic.",
            "Answer as the character(s), not as an assistant.",
            "These answers are private planning notes for generation only. They must not be copied into the final character card unless naturally reflected in characterization.",
        ]
        if split_focus:
            lines.extend([
                "This is a split-card focused Q&A pass. Answer ONLY for the focused main character named in the concept header.",
                "Do not answer as every character. Do not include side-by-side answers for the other split characters.",
                "Other characters may be mentioned only as relationship/lore context when that helps explain the focused character.",
            ])
        else:
            lines.append("If this is a multi-character card, answer each question for the relevant primary characters or as a grouped dynamic when appropriate.")
        lines.extend([
            "Keep answers concise but specific, emotionally useful, and character-consistent.",
            "Do not add sections from the final character-card template. Return only Q&A pairs.",
            "Every question is mandatory. Do not skip any question.",
            "Use the exact labels Q1/A1, Q2/A2, and so on, so the app can verify completion.",
            "",
            "CHARACTER CONCEPT",
            concept.strip(),
            "",
            "QUESTIONS",
        ])
        for idx, q in enumerate(questions, start=1):
            lines.append(f"{idx}. {q}")
        if split_focus:
            lines.extend([
                "",
                "OUTPUT FORMAT",
                "Q1: <question>",
                "A1: <answer for the focused character only>",
                "Q2: <question>",
                "A2: <answer for the focused character only>",
            ])
        else:
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
        qa_settings = {**settings, "_streamTarget": "qa"}
        answers = self._chat(prompt, qa_settings).strip()
        self._log_event("qa_generation_response", {"answers": answers})
        answers, qa_format_info = self._qa_reinsert_questions_if_model_used_q_as_answer(answers, questions)
        if qa_format_info.get("repaired"):
            self._log_event("qa_generation_format_repaired", qa_format_info)
        answers, qa_order_info = self._qa_canonicalise_order_and_questions(answers, questions)
        if qa_order_info.get("repaired"):
            self._log_event("qa_generation_order_repaired", qa_order_info)
        missing = self._qa_missing_indexes(answers, questions)
        retries = 0
        while missing and retries < 2:
            retries += 1
            extra = self._retry_missing_qa_answers(concept, questions, answers, missing, settings)
            if extra:
                extra, extra_format_info = self._qa_reinsert_questions_if_model_used_q_as_answer(extra, questions)
                if extra_format_info.get("repaired"):
                    self._log_event("qa_generation_retry_format_repaired", {**extra_format_info, "retry": retries})
                extra, extra_order_info = self._qa_canonicalise_order_and_questions(extra, questions)
                if extra_order_info.get("repaired"):
                    self._log_event("qa_generation_retry_order_repaired", {**extra_order_info, "retry": retries})
                answers = (answers.rstrip() + "\n\n" + extra.strip()).strip()
                answers, combined_format_info = self._qa_reinsert_questions_if_model_used_q_as_answer(answers, questions)
                if combined_format_info.get("repaired"):
                    self._log_event("qa_generation_combined_format_repaired", {**combined_format_info, "retry": retries})
                answers, combined_order_info = self._qa_canonicalise_order_and_questions(answers, questions)
                if combined_order_info.get("repaired"):
                    self._log_event("qa_generation_combined_order_repaired", {**combined_order_info, "retry": retries})
            missing = self._qa_missing_indexes(answers, questions)
        if missing:
            missing_labels = ", ".join([f"Q{i}" for i in missing])
            raise RuntimeError(f"Q&A is enabled but the AI skipped required question(s): {missing_labels}. Try again or simplify the Q&A list.")
        return answers.strip()

    def generate_qa_context(self, concept, template, settings, *extra_args, extra_questions=None, force_enabled=None):
        # Keep this bridge method tolerant of older/newer frontend calls.
        # PyWebView passes JS arguments positionally, so adding modal-specific
        # options directly to the method signature can break if a stale frontend
        # or backend is mixed during packaging.
        if extra_args:
            if len(extra_args) >= 1:
                extra_questions = extra_args[0]
            if len(extra_args) >= 2:
                force_enabled = extra_args[1]
        self._reset_cancel()
        if not concept or not concept.strip():
            return {"ok": False, "error": "Enter a character concept first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        template = self._normalise_template(template)
        # Save the real template only. Per-card custom Q&A questions are added to
        # a temporary copy below so the Generate Card modal cannot accidentally
        # pollute the saved Prompt Template Q&A list.
        self.save_template(template)
        qa_template = json.loads(json.dumps(template))
        cleaned_extra = self._qa_clean_extra_questions_for_template(qa_template, extra_questions)
        if cleaned_extra:
            qa = qa_template.setdefault("qa", {})
            qa["enabled"] = True
            sections = qa.setdefault("sections", [])
            sections.append({
                "id": "temporary_card_qa",
                "title": "Card-specific Q&A",
                "enabled": True,
                "collapsed": False,
                "questions": [{"enabled": True, "text": q} for q in cleaned_extra],
            })
            qa_template = self._normalise_template(qa_template)
        elif force_enabled is not None:
            qa_template.setdefault("qa", {})["enabled"] = bool(force_enabled)
            qa_template = self._normalise_template(qa_template)
        settings_check = self._validate_text_api_settings(merged_settings)
        if not settings_check.get("ok"):
            return settings_check
        try:
            self._reset_backup_info()
            self._raise_if_cancelled()
            answers = self._generate_template_qa(concept, qa_template, merged_settings)
            self._raise_if_cancelled()
            info = self._get_backup_info()
            if info.get("used"):
                info["phase"] = "qa_interview"
            return {"ok": True, "qaAnswers": answers, "backupInfo": info, "temporaryQuestionCount": len(cleaned_extra)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _fallback_split_character_names(self, concept, settings):
        names = []
        pattern = re.compile(r"(?im)^\s*(?:character\s*\d+|char\s*\d+|name)\s*[:\-]\s*([^\n,;]{2,80})")
        for m in pattern.finditer(concept or ""):
            name = re.sub(r"[^A-Za-z0-9_ '\-]", "", m.group(1)).strip()
            if name and name.lower() not in {n.lower() for n in names}:
                names.append(name)
        count = max(2, min(12, int(settings.get("multiCharacterCount") or 2)))
        while len(names) < count:
            names.append(f"Character {len(names) + 1}")
        return names[:count]

    def identify_split_characters(self, concept, settings=None):
        merged = self._normalise_settings({**self.settings, **(settings or {})})
        fallback = self._fallback_split_character_names(concept, merged)
        validation = self._validate_text_api_settings(merged)
        if not validation.get("ok"):
            return {"ok": True, "characters": fallback, "fallback": True, "notes": validation.get("error", "")}
        prompt = "\n".join([
            "Identify the main characters that should each receive their own separate character card.",
            "Return strict JSON only: {\"characters\":[\"Name 1\",\"Name 2\"]}.",
            "Include only primary/main roleplay characters, not background-only side characters.",
            "If names are unknown, use short labels like Character 1, Character 2.",
            f"Maximum characters: {max(2, min(4 if merged.get('cardMode') == 'group_cards' else 12, int(merged.get('multiCharacterCount') or 2)))}",
            "CONCEPT:",
            (concept or "").strip(),
        ])
        try:
            model = (merged.get("aiSuggestionModel") or merged.get("model") or "").strip()
            raw = self._chat_once(prompt, {**merged, "streamAi": False, "_streamTarget": ""}, model, "split_character_identification")
            parsed = self._loads_model_json(raw)
            chars = parsed.get("characters") if isinstance(parsed, dict) else []
            out = []
            for item in chars or []:
                name = str(item or "").strip()[:80]
                if name and name.casefold() not in {n.casefold() for n in out}:
                    out.append(name)
            if len(out) < 2 and str(merged.get("sharedScenePolicy") or "") == "split_cards":
                # Split mode should not silently collapse back to one card. If the
                # identifier under-detects, use the fallback labels so the user can
                # still get separate passes instead of one combined card.
                out = fallback
            if not out:
                out = fallback
            max_chars = max(2, min(4 if merged.get("cardMode") == "group_cards" else 12, int(merged.get("multiCharacterCount") or 2)))
            return {"ok": True, "characters": out[:max_chars], "fallback": False, "notes": str(parsed.get("notes") or "") if isinstance(parsed, dict) else ""}
        except Exception as e:
            return {"ok": True, "characters": fallback, "fallback": True, "notes": str(e)}

    def _split_card_focus_concept(self, original_concept, focus_name, all_names, qa_answers=""):
        other_names = [n for n in all_names if n != focus_name]
        instructions = [
            "SPLIT-CARD GENERATION PASS",
            f"Focused main character for this card: {focus_name}",
            f"This pass must generate one single-character card for {focus_name} only.",
            "The focused character is {{char}} and must be treated as the main playable character.",
            "Do not create a group card and do not include other primary characters as co-protagonists in the main Description/Personality sections.",
            "Other named characters from the original concept should appear as lorebook entries, relationship context, background references, or supporting cast so the focused character can still reference them.",
        ]
        if other_names:
            instructions.append("Other characters to preserve as lorebook/supporting references: " + ", ".join(other_names))
        if qa_answers:
            instructions.append("Shared Q&A context may contain information about all characters. FILTER it for the focused character only. Do not copy or preserve full multi-character Q&A answers as this card's Q&A.")
        return "\n".join(instructions) + "\n\nORIGINAL MULTI-CHARACTER CONCEPT:\n" + (original_concept or "").strip() + (("\n\nSHARED Q&A NOTES TO FILTER FOR THIS FOCUSED CARD ONLY:\n" + qa_answers.strip()) if qa_answers else "")

    def _extract_output_name(self, output, fallback="Character"):
        try:
            name = self._extract_name(output)
            if name:
                return name
        except Exception:
            pass
        return fallback or "Character"


    def _concept_primary_name(self, concept):
        """Best-effort main-name extraction for concept fidelity checks.

        This is intentionally conservative. It only blocks obvious drift such as
        the model replacing Alison with an unrelated prior character name, while
        still allowing nameless concepts to generate a fresh name.
        """
        text = str(concept or "")
        if not text.strip():
            return ""
        # Remove common field labels/headings that are capitalised but not names.
        cleaned = re.sub(r"(?im)^\s*(Visual Description|Generation Notes?|Hair|Eyes|Skin|Body|Clothing|Accessories|Details|Scenario|First Message|Greeting|Opening)\s*:", " ", text)
        cleaned = re.sub(r"\{\{user\}\}", " ", cleaned, flags=re.I)
        stop = {
            "The", "This", "That", "These", "Those", "One", "Day", "Evening", "Inside", "First", "Message",
            "Visual", "Description", "Hair", "Eyes", "Skin", "Body", "Clothing", "Accessories", "Details",
            "Long", "Bright", "Fair", "Curvy", "Tight", "Holding", "Visible", "Black", "White", "Your",
            "Alex" if False else "",  # keeps the set literal stable below after comprehension filtering
        }
        names = []
        for match in re.finditer(r"\b([A-Z][a-z]{2,24})\b", cleaned):
            name = match.group(1).strip()
            if name in stop:
                continue
            if name.lower() in {"user", "char", "black", "blacked"}:
                continue
            if name not in names:
                names.append(name)
        return names[0] if names else ""

    def _concept_required_markers(self, concept):
        text = str(concept or "")
        markers = []
        # Preserve loud/unique tokens that often carry scenario meaning: shirt
        # slogans, captions, proper nouns in all caps, etc.
        for token in re.findall(r"\b[A-Z][A-Z0-9_'-]{3,}\b", text):
            if token in {"FIRST", "MESSAGE"}:
                continue
            if token not in markers:
                markers.append(token)
        # Keep short quoted/caption-like phrases that are highly distinctive.
        for quoted in re.findall(r"[\"“”']([^\"“”']{8,80})[\"“”']", text):
            q = quoted.strip()
            if any(ch.isalpha() for ch in q) and q not in markers:
                markers.append(q)
        return markers[:8]

    def _concept_fidelity_report(self, concept, output):
        concept = str(concept or "")
        output = str(output or "")
        if not concept.strip() or not output.strip():
            return {"drifted": False, "missing": []}
        lower_out = output.lower()
        missing = []
        primary_name = self._concept_primary_name(concept)
        if primary_name and not re.search(rf"\b{re.escape(primary_name)}\b", output, flags=re.I):
            missing.append(f"primary name `{primary_name}`")
        for marker in self._concept_required_markers(concept):
            if len(marker) >= 4 and marker.lower() not in lower_out:
                missing.append(f"required marker `{marker[:80]}`")
        # If the user supplied an explicit First Message, the output should at
        # least preserve the identified primary name/markers. Avoid over-policing
        # when no concrete markers were found.
        explicit_first = bool(re.search(r"(?im)^\s*(First Message|Greeting|Opening)\s*:", concept))
        drifted = bool(missing and (explicit_first or len(missing) >= 2))
        return {"drifted": drifted, "missing": missing, "primaryName": primary_name, "explicitFirstMessage": explicit_first}

    def _retry_generation_for_concept_fidelity(self, generation_concept, template, settings, previous_output, report):
        missing = report.get("missing") or []
        retry_concept = "\n\n".join([
            "STRICT CONCEPT-FIDELITY RETRY",
            "The previous output drifted away from the user's source concept. Regenerate the full character card from scratch.",
            "Do NOT use the previous output as source material. It is only a bad example of what drifted.",
            "The user's CHARACTER CONCEPT below is authoritative. Preserve its named characters, relationships, scenario hook, visual details, clothing, captions/messages, explicit First Message beats, and temporary generation notes.",
            "Missing/changed facts detected: " + (", ".join(missing) if missing else "unknown concept details"),
            "If the source concept names a character, that character must remain the card's main character unless split-card focus instructions explicitly say otherwise.",
            "If the source concept contains First Message/Greeting/Opening text, keep the same situation and confrontation while only polishing/expanding the prose.",
            "ORIGINAL SOURCE CONCEPT",
            str(generation_concept or "").strip(),
            "BAD PREVIOUS OUTPUT TO AVOID COPYING",
            str(previous_output or "").strip()[:6000],
        ]).strip()
        self._log_event("concept_fidelity_retry_request", {"missing": missing, "primaryName": report.get("primaryName", "")})
        retry_settings = {**settings, "_streamTarget": ""}
        retry = self._apply_restricted_tags_to_output(
            self._ensure_image_prompt_sections(self._clean_generated_output(self._generate_full_or_lite_output(retry_concept, template, retry_settings)), retry_settings),
            template,
            settings,
        )
        retry_report = self._concept_fidelity_report(generation_concept, retry)
        self._log_event("concept_fidelity_retry_response", {"drifted": retry_report.get("drifted"), "missing": retry_report.get("missing", []), "preview": retry[:1000]})
        if retry and not retry_report.get("drifted"):
            return retry, {"repaired": True, "reason": "concept_fidelity_retry", "initialReport": report, "retryReport": retry_report}
        return previous_output, {"repaired": False, "reason": "retry_still_drifted", "initialReport": report, "retryReport": retry_report}

    def generate_split_cards(self, concept, template, settings, qa_answers="", disable_template_qa=False, *extra_args, extra_questions=None):
        # v1.0.6-beta1: split-card generation must never reuse one shared
        # multi-character Q&A blob as every character tab's Q&A. Each focused
        # card gets a focused Q&A pass instead; older frontends that still pass
        # shared qa_answers are treated as reference notes only.
        if extra_args and extra_questions is None:
            extra_questions = extra_args[0]
        self._reset_cancel()
        if not concept or not concept.strip():
            return {"ok": False, "error": "Enter a character concept first."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        merged_settings["cardMode"] = "split_cards"
        merged_settings["sharedScenePolicy"] = "split_cards"
        self.save_settings(merged_settings)
        template = self._normalise_template(template)
        self.save_template(template)
        qa_template = json.loads(json.dumps(template))
        cleaned_extra = self._qa_clean_extra_questions_for_template(qa_template, extra_questions)
        if cleaned_extra:
            qa = qa_template.setdefault("qa", {})
            qa["enabled"] = True
            sections = qa.setdefault("sections", [])
            sections.append({
                "id": "temporary_card_qa",
                "title": "Card-specific Q&A",
                "enabled": True,
                "collapsed": False,
                "questions": [{"enabled": True, "text": q} for q in cleaned_extra],
            })
            qa_template = self._normalise_template(qa_template)
        settings_check = self._validate_text_api_settings(merged_settings)
        if not settings_check.get("ok"):
            return settings_check
        ident = self.identify_split_characters(concept, merged_settings)
        names = ident.get("characters") or self._fallback_split_character_names(concept, merged_settings)
        cards = []
        try:
            shared_qa = (qa_answers or "").strip()
            qa_enabled = bool((qa_template.get("qa", {}) or {}).get("enabled"))
            for idx, focus in enumerate(names):
                self._raise_if_cancelled()
                per_settings = {**merged_settings, "cardMode": "split_cards", "_streamTarget": ""}
                per_qa = ""
                if qa_enabled and not disable_template_qa:
                    # Generate a focused Q&A for this split card. Do not reuse a
                    # previously generated shared multi-character Q&A blob, because
                    # that causes every output tab to show the same Q&A answers.
                    q_concept = self._split_card_focus_concept(concept, focus, names, shared_qa)
                    self._log_event("split_card_focused_qa_request", {"focus": focus, "hasSharedReferenceQa": bool(shared_qa), "extraQuestionCount": len(cleaned_extra)})
                    per_qa = self._generate_template_qa(q_concept, qa_template, per_settings)
                    self._log_event("split_card_focused_qa_response", {"focus": focus, "length": len(per_qa or "")})
                elif shared_qa:
                    self._log_event("split_card_shared_qa_ignored", {"focus": focus, "reason": "split cards require per-character Q&A; shared Q&A was not copied into this tab"})
                focus_concept = self._split_card_focus_concept(concept, focus, names, per_qa)
                self._reset_backup_info()
                output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(self._generate_full_or_lite_output(focus_concept, template, per_settings)), template, per_settings), per_settings)
                fidelity_info = {"repaired": False}
                fidelity_report = self._concept_fidelity_report(focus_concept, output)
                if fidelity_report.get("drifted"):
                    self._log_event("concept_fidelity_drift_detected", {"mode": "split", "focus": focus, "missing": fidelity_report.get("missing", []), "primaryName": fidelity_report.get("primaryName", "")})
                    output, fidelity_info = self._retry_generation_for_concept_fidelity(focus_concept, template, per_settings, output, fidelity_report)
                validation = self.validate_output_against_template(output, template, per_settings)
                repair_info = {"repaired": False, "missing": []}
                if not validation.get("ok"):
                    output, repair_info = self._repair_missing_output(output, focus_concept, template, per_settings, validation.get("missing", []))
                    output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(output), template, per_settings), per_settings)
                    validation = self.validate_output_against_template(output, template, per_settings)
                cards.append({
                    "name": self._extract_output_name(output, focus),
                    "focusName": focus,
                    "output": output,
                    "qaAnswers": per_qa,
                    "emotionImages": [],
                    "generatedImages": [],
                    "cardImagePath": "",
                    "validation": validation,
                    "repair": repair_info,
                    "fidelity": fidelity_info,
                })
            return {"ok": True, "cards": cards, "characters": names, "identification": ident}
        except Exception as e:
            return {"ok": False, "error": str(e), "cards": cards}

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
            output_settings = {**merged_settings, "_streamTarget": "output"}
            output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(self._generate_full_or_lite_output(generation_concept, template, output_settings)), template, merged_settings), merged_settings)
            fidelity_info = {"repaired": False}
            fidelity_report = self._concept_fidelity_report(generation_concept, output)
            if fidelity_report.get("drifted"):
                self._log_event("concept_fidelity_drift_detected", {"mode": "single", "missing": fidelity_report.get("missing", []), "primaryName": fidelity_report.get("primaryName", "")})
                output, fidelity_info = self._retry_generation_for_concept_fidelity(generation_concept, template, output_settings, output, fidelity_report)
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
                output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(output), template, merged_settings), merged_settings)
                self._raise_if_cancelled()
                validation = self.validate_output_against_template(output, template, merged_settings)
                self._log_event("generation_validation_after_repair", {"validation": validation})
            return {"ok": True, "output": output, "validation": validation, "repair": repair_info, "qaAnswers": qa_answers, "backupInfo": backup_info, "fidelity": fidelity_info}
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
            output_settings = {**merged_settings, "_streamTarget": "output"}
            output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(self._generate_full_or_lite_output(generation_concept, template, output_settings)), template, merged_settings), merged_settings)
            fidelity_info = {"repaired": False}
            fidelity_report = self._concept_fidelity_report(generation_concept, output)
            if fidelity_report.get("drifted"):
                self._log_event("concept_fidelity_drift_detected", {"mode": "legacy_generate", "missing": fidelity_report.get("missing", []), "primaryName": fidelity_report.get("primaryName", "")})
                output, fidelity_info = self._retry_generation_for_concept_fidelity(generation_concept, template, output_settings, output, fidelity_report)
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
                output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(output), template, merged_settings), merged_settings)
                self._raise_if_cancelled()
                validation = self.validate_output_against_template(output, template, merged_settings)
                self._log_event("generation_validation_after_repair", {"validation": validation})
            return {"ok": True, "output": output, "validation": validation, "repair": repair_info, "qaAnswers": qa_answers, "backupInfo": backup_info, "fidelity": fidelity_info}
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
        style_text = self._first_message_style_text(merged_settings)
        alt_style_lines = []
        for idx in range(int(merged_settings.get("alternateFirstMessages") or 0)):
            alt_style_lines.append(f"Alternative First Message {idx + 1} style/instructions: {self._alt_first_message_style_text(merged_settings, idx, style_text)}")
        prompt = "\n".join([
            "Revise the existing fictional character card according to the user's follow-up request.",
            "Return the complete revised card, not a diff or commentary.",
            "Do not add a wrapper title such as '# Revised Character Card'.",
            "Use the existing/plain section headings only. Do not convert the card to Markdown # or ## headings.",
            "Keep the same section order and do not add disabled sections.",
            ("Card mode: SPLIT CARDS. Revise only the currently focused character card. Keep other original characters as lorebook/background references, not co-protagonists." if merged_settings.get("cardMode") == "split_cards" else ("Card mode: MULTI-CHARACTER SINGLE CARD. Preserve all primary characters inside one {{char}} card; do not split into multiple cards or multi-chat." if merged_settings.get("cardMode") == "multi" else "Card mode: SINGLE CHARACTER CARD.")),
            "Preserve good content unless the follow-up request changes it.",
            f"Enabled section order: {', '.join(enabled_sections)}",
            f"First Message style/instructions currently selected: {style_text}",
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
            output_settings = {**merged_settings, "_streamTarget": "output"}
            output = self._ensure_image_prompt_sections(self._apply_restricted_tags_to_output(self._clean_generated_output(self._chat(prompt, output_settings)), template, merged_settings), merged_settings)
            info = self._get_backup_info()
            if info.get("used"):
                info["phase"] = "followup_revision"
            return {"ok": True, "output": output, "backupInfo": info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def revise_card_from_rating_project(self, project_path, settings=None):
        """Compatibility bridge for PyWebView builds: improve a saved project from its AI rating."""
        return self.generate_card_improvement_from_rating(project_path, settings)

    def reviseCardFromRatingProject(self, project_path, settings=None):
        return self.generate_card_improvement_from_rating(project_path, settings)

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

    def _dialog_subprocess_env(self):
        """Return a host-ish environment for external file pickers.

        AppImages set APPDIR/APPIMAGE and sometimes LD_LIBRARY_PATH values that
        can confuse host desktop tools.  The picker itself is outside the app, so
        run it with those bundle-specific variables stripped.
        """
        env = dict(os.environ)
        for key in ("APPDIR", "APPIMAGE", "ARGV0", "PYINSTALLER_RESET_ENVIRONMENT"):
            env.pop(key, None)
        # LD_LIBRARY_PATH from AppImage/PyInstaller can make kdialog/zenity load
        # bundled libraries instead of system ones. Restore the original value if
        # AppImage preserved it, otherwise remove it for external GUI tools.
        orig_ld = env.get("LD_LIBRARY_PATH_ORIG")
        if orig_ld is not None:
            env["LD_LIBRARY_PATH"] = orig_ld
        elif "APPIMAGE" in os.environ or getattr(sys, "frozen", False):
            env.pop("LD_LIBRARY_PATH", None)
        return env

    def _run_dialog_command(self, cmd, label):
        try:
            self._log_event("modern_file_dialog_try", {"label": label, "cmd": cmd})
            proc = subprocess.run(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._dialog_subprocess_env(),
                timeout=120,
                check=False,
            )
            if proc.returncode != 0:
                # Return code 1 is usually user cancel.  Anything else is still
                # non-fatal; continue to the next picker/fallback instead of
                # silently making the button look broken.
                self._log_event("modern_file_dialog_nonzero", {
                    "label": label,
                    "returncode": proc.returncode,
                    "stderr": (proc.stderr or "")[:1000],
                })
                return None
            paths = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
            return paths
        except subprocess.TimeoutExpired:
            self._log_event("modern_file_dialog_timeout", {"label": label, "cmd": cmd})
            return None
        except Exception as e:
            self._log_event("modern_file_dialog_error", {"label": label, "error": str(e), "cmd": cmd})
            return None

    def _is_packaged_appimage(self):
        return bool(getattr(sys, "frozen", False) or os.environ.get("APPIMAGE") or os.environ.get("APPDIR"))

    def _run_pywebview_file_dialog(self, title="Open", kind="any", multiple=False):
        """Use PyWebView's built-in/classic picker.

        Inside AppImage/PyInstaller builds, external host pickers such as kdialog
        and zenity can fail invisibly or never attach to the app window. The
        classic PyWebView picker is less pretty, but it is the reliable one in
        packaged builds, so every packaged file button/drop-zone uses it.
        """
        self._log_event("file_dialog_pywebview", {"title": title, "kind": kind, "multiple": bool(multiple)})
        window = webview.windows[0] if webview.windows else None
        if not window:
            return []
        result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=multiple)
        if not result:
            return []
        if isinstance(result, (list, tuple)):
            return [str(x) for x in result if str(x).strip()]
        return [str(result)] if str(result).strip() else []

    def _run_modern_file_dialog(self, title="Open", kind="any", multiple=False):
        """Prefer host native dialogs in source runs, but force PyWebView in AppImage.

        The normal source app can keep using kdialog/zenity. Packaged AppImage
        builds go straight to PyWebView because that is the picker path known to
        appear reliably on the user's machine.
        """
        if self._is_packaged_appimage():
            return self._run_pywebview_file_dialog(title, kind, multiple)

        filters = {
            "image": "Images (*.png *.jpg *.jpeg *.webp)",
            "saved": "Character Cards / Projects (*.json *.png *.md *.txt)",
            "card": "Character Cards / Projects (*.json *.png *.md *.txt)",
            "attachment": "Documents (*.txt *.srt *.vtt *.md *.pdf)",
            "any": "All Files (*)",
        }
        start_dir = str(Path.home())
        if shutil.which("kdialog"):
            cmd = ["kdialog", "--title", title]
            if multiple:
                cmd += ["--multiple", "--separate-output"]
            cmd += ["--getopenfilename", start_dir, filters.get(kind, filters["any"])]
            paths = self._run_dialog_command(cmd, "kdialog")
            if paths:
                return paths
        if shutil.which("zenity"):
            zfilters = {
                "image": "Images | *.png *.jpg *.jpeg *.webp",
                "saved": "Character Cards / Projects | *.json *.png *.md *.txt",
                "card": "Character Cards / Projects | *.json *.png *.md *.txt",
                "attachment": "Documents | *.txt *.srt *.vtt *.md *.pdf",
                "any": "All Files | *",
            }
            cmd = ["zenity", "--file-selection", "--title", title]
            if multiple:
                cmd += ["--multiple", "--separator=\n"]
            cmd += [f"--file-filter={zfilters.get(kind, zfilters['any'])}"]
            paths = self._run_dialog_command(cmd, "zenity")
            if paths:
                expanded = []
                for item in paths:
                    expanded.extend([x.strip() for x in str(item).split("|") if x.strip()])
                return expanded or paths
        return self._run_pywebview_file_dialog(title, kind, multiple)

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

    def import_image_path(self, path, kind="card"):
        try:
            return self._copy_image_from_path(path, kind)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_project_card_image(self, project_path, image_source):
        """Force-update the selected card image for an existing saved project.

        This is intentionally separate from the normal workspace autosave path.
        Older projects can carry stale/blank exportedPath/latest_cardv2 image
        state even after the editor's Card Image field changes.  This method
        treats the supplied image as authoritative, rewrites the project JSON,
        rewrites the latest Chara V2 PNG with that image, stores the image in
        workspace_assets, and refreshes the Character Browser cache.
        """
        try:
            path = Path(str(project_path or "")).expanduser()
            if not path.exists() or not path.is_file():
                return {"ok": False, "error": "Character project not found."}
            source = str(image_source or "").strip()
            if not source:
                return {"ok": False, "error": "No card image was supplied."}

            local_image_path = self._ensure_local_card_image_path(source, "card", "update_project_card_image")
            if not local_image_path:
                return {"ok": False, "error": f"Could not resolve the selected card image: {source[:200]}"}

            # Make the selected image durable.  Even if the source currently exists
            # in generated_images or elsewhere, old-card updates should not depend
            # on a temp/generated path remaining alive after cleanup/reload.
            try:
                resolved = Path(local_image_path).expanduser().resolve()
                card_root = CARD_IMAGES_DIR.resolve()
                if not (resolved == card_root or card_root in resolved.parents):
                    promoted = self._copy_image_from_path(resolved, "card")
                    if promoted.get("ok") and promoted.get("path"):
                        self._log_event("project_card_image_promoted", {"project": str(path), "from": str(resolved), "to": promoted.get("path")})
                        local_image_path = str(promoted.get("path"))
            except Exception as e:
                self._log_event("project_card_image_promote_failed", {"project": str(path), "image": str(local_image_path), "error": str(e)})

            payload = json.loads(path.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid character project."}
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            settings = self._normalise_settings(project.get("settings") if isinstance(project.get("settings"), dict) else {})

            output = str(project.get("output") or workspace.get("output") or "").strip()
            if not output:
                # Try the sidecar used by older saved workspaces.
                try:
                    sidecar = path.parent / "latest_output.md"
                    if sidecar.exists():
                        output = sidecar.read_text(encoding="utf-8").strip()
                except Exception:
                    output = ""
            name = self._clean_character_name_value(project.get("name") or self._extract_name(output) or path.parent.name) or "Character Card"
            template = project.get("template") or workspace.get("template") or self.template

            settings["cardImagePath"] = local_image_path
            for target in (project, workspace):
                target["imagePath"] = local_image_path
                target["cardImagePath"] = local_image_path
            project["settings"] = settings

            def update_tabs(tabs):
                if not isinstance(tabs, list):
                    return
                for tab in tabs:
                    if isinstance(tab, dict):
                        tab["imagePath"] = local_image_path
                        tab["cardImagePath"] = local_image_path
            update_tabs(project.get("characterTabs"))
            update_tabs(workspace.get("characterTabs"))

            stamp = time.strftime("%Y%m%d-%H%M%S")
            project["saved_at"] = stamp
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            workspace["settings"] = settings
            workspace["saved_at"] = stamp
            workspace["updated_at"] = project["updated_at"]
            project["workspace"] = workspace

            latest_card = Path("")
            if output:
                try:
                    latest_card = path.parent / f"{self._safe_slug(name)}_latest_cardv2.png"
                    card_payload = self._to_chara_card_v2(output, name)
                    self._write_chara_png(latest_card, card_payload, local_image_path, require_image=True)
                    project["exportedPath"] = str(latest_card)
                    try:
                        (path.parent / "latest_output.md").write_text(output, encoding="utf-8")
                    except Exception:
                        pass
                except Exception as e:
                    self._log_event("update_project_card_image_latest_png_failed", {"project": str(path), "error": str(e), "image": str(local_image_path)})
                    return {"ok": False, "error": f"Could not rewrite latest card PNG with selected image: {e}"}

            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                asset_workspace = dict(workspace)
                asset_workspace["output"] = output or asset_workspace.get("output") or project.get("output") or ""
                asset_workspace["settings"] = settings
                asset_workspace["cardImagePath"] = local_image_path
                asset_workspace["imagePath"] = local_image_path
                self._save_workspace_assets_to_db(path, asset_workspace, image_path=local_image_path)
            except Exception as e:
                self._log_event("update_project_card_image_asset_save_failed", {"project": str(path), "error": str(e)})
            try:
                self._refresh_library_cache_for_project(path, force=True)
            except Exception as e:
                self._log_event("update_project_card_image_cache_refresh_failed", {"project": str(path), "error": str(e)})
            self._log_event("project_card_image_updated", {"project": str(path), "image": str(local_image_path), "latestCard": str(latest_card or "")})
            return {
                "ok": True,
                "projectPath": str(path),
                "imagePath": local_image_path,
                "cardImagePath": local_image_path,
                "cardPath": str(latest_card) if str(latest_card) else "",
                "name": name,
            }
        except Exception as e:
            return {"ok": False, "error": f"Could not update saved card image: {e}"}

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

    def import_concept_attachment_paths(self, paths):
        try:
            if isinstance(paths, str):
                paths = [paths]
            paths = [str(p).strip() for p in (paths or []) if str(p).strip()]
            if not paths:
                return {"ok": False, "error": "No dropped concept attachment path was received."}
            attachments = []
            for path in paths:
                res = self._concept_attachment_from_path(path)
                if not res.get("ok"):
                    return res
                attachments.append(res)
            return {"ok": True, "attachments": attachments}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _looks_like_url(self, value):
        try:
            parsed = urllib.parse.urlparse(str(value or "").strip())
            return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False

    def _filename_from_url_response(self, url, headers=None, fallback="download"):
        headers = headers or {}
        cd = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd, re.I)
        if m:
            name = urllib.parse.unquote(m.group(1).strip().strip('"'))
        else:
            parsed = urllib.parse.urlparse(url)
            name = urllib.parse.unquote(Path(parsed.path or "").name or fallback)
        name = name.split("?")[0].split("#")[0].strip() or fallback
        return self._safe_upload_name(name, fallback)

    def _extension_from_content_type(self, content_type, fallback=""):
        ct = str(content_type or "").split(";", 1)[0].strip().lower()
        return {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
            "application/json": ".json",
            "text/json": ".json",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "application/x-markdown": ".md",
        }.get(ct, fallback or "")

    def _download_url_to_file(self, url, *, folder=None, allowed_suffixes=None, fallback_name="download", max_bytes=80 * 1024 * 1024, prefix="url"):
        url = str(url or "").strip()
        if not self._looks_like_url(url):
            return {"ok": False, "error": "Enter a valid http:// or https:// URL."}
        folder = Path(folder or IMPORT_UPLOADS_DIR)
        _safe_mkdir(folder)
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", f"{APP_NAME}/1.0")
        try:
            with _safe_urlopen(req, timeout=60) as resp:
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > max_bytes:
                            return {"ok": False, "error": f"URL file is too large ({int(content_length)} bytes)."}
                    except Exception:
                        pass
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    return {"ok": False, "error": f"URL file is too large. Limit is {max_bytes // (1024 * 1024)} MB."}
                final_url = resp.geturl() or url
                filename = self._filename_from_url_response(final_url, resp.headers, fallback_name)
        except Exception as e:
            return {"ok": False, "error": f"Could not download URL: {e}"}
        if not raw:
            return {"ok": False, "error": "Downloaded file was empty."}
        suffix = Path(filename).suffix.lower()
        if not suffix:
            suffix = self._extension_from_content_type(content_type, "")
            filename = filename + suffix if suffix else filename
        if allowed_suffixes and suffix not in set(allowed_suffixes):
            guessed = self._extension_from_content_type(content_type, suffix)
            if guessed and guessed in set(allowed_suffixes):
                suffix = guessed
                filename = str(Path(filename).with_suffix(guessed))
            else:
                allowed = ", ".join(sorted(allowed_suffixes))
                return {"ok": False, "error": f"URL file type is not supported ({suffix or content_type or 'unknown'}). Allowed: {allowed}."}
        safe = self._safe_upload_name(filename, fallback_name + (suffix or ""))
        path = folder / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{prefix}_{safe}"
        path.write_bytes(raw)
        return {"ok": True, "path": str(path), "filename": safe, "url": url, "contentType": content_type, "bytes": len(raw)}

    def save_image_from_url(self, url, kind="card"):
        folder = VISION_IMAGES_DIR if str(kind).lower() == "vision" else CARD_IMAGES_DIR
        res = self._download_url_to_file(url, folder=folder, allowed_suffixes={".png", ".jpg", ".jpeg", ".webp"}, fallback_name="image", max_bytes=40 * 1024 * 1024, prefix="url_image")
        if not res.get("ok"):
            return res
        path = Path(res["path"])
        try:
            with Image.open(path) as img:
                img.verify()
        except Exception as e:
            path.unlink(missing_ok=True)
            return {"ok": False, "error": f"Downloaded URL is not a valid image: {e}"}
        return {"ok": True, "path": str(path), "filename": res.get("filename"), "sourceUrl": url, "contentType": res.get("contentType", "")}

    def load_import_url(self, url):
        res = self._download_url_to_file(url, folder=IMPORT_UPLOADS_DIR, allowed_suffixes={".json", ".png", ".md", ".txt"}, fallback_name="character_card", max_bytes=90 * 1024 * 1024, prefix="url_card")
        if not res.get("ok"):
            return res
        loaded = self._load_import_path(Path(res["path"]))
        if loaded.get("ok"):
            loaded["uploadedPath"] = res["path"]
            loaded["sourceUrl"] = url
            loaded["message"] = loaded.get("message") or "Loaded character card/project from URL."
        return loaded

    def load_import_path(self, path):
        try:
            p = Path(str(path or "")).expanduser()
            if not p.exists():
                return {"ok": False, "error": f"Import file was not found: {p}"}
            if p.suffix.lower() not in {".json", ".png", ".jpg", ".jpeg", ".webp", ".md", ".txt"}:
                return {"ok": False, "error": "Import supports JSON, PNG, JPG, WebP, MD, and TXT files."}
            loaded = self._load_import_path(p)
            if loaded.get("ok"):
                loaded["sourcePath"] = str(p)
                loaded["message"] = loaded.get("message") or "Loaded character card/project from path."
            return loaded
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

    def card_url_to_builders(self, url, field_catalog, settings=None):
        """Load an existing character card/project from URL and convert it into Builder fields."""
        try:
            loaded = self.load_import_url(url)
            if not loaded.get("ok"):
                return loaded
            output = str(loaded.get("output") or "").strip()
            concept = str(loaded.get("concept") or "").strip()
            if not output and not concept:
                return {"ok": False, "error": "The URL card loaded, but it did not contain readable card text to transfer into builders."}
            source_text = output or concept
            self._log_event("card_url_to_builders_loaded", {
                "url": url,
                "loadedType": loaded.get("loadedType"),
                "output_chars": len(output),
                "concept_chars": len(concept),
                "field_count": len(field_catalog or []),
            })
            transfer = self.ai_transfer_to_builders(source_text[:30000], "", field_catalog or [], settings or self.settings)
            if transfer.get("ok"):
                transfer["loadedType"] = loaded.get("loadedType", "card")
                transfer["sourcePath"] = loaded.get("sourcePath") or loaded.get("uploadedPath") or url
                transfer["uploadedPath"] = loaded.get("uploadedPath", "")
                transfer["sourceUrl"] = url
                transfer["sourceOutput"] = output
                main_concept = self._unmatched_card_context_for_main_concept(source_text)
                if transfer.get("sideCharacterNotes"):
                    side_block = "SIDE CHARACTERS / LOREBOOK-ONLY CHARACTERS:\n" + str(transfer.get("sideCharacterNotes") or "").strip()
                    main_concept = (main_concept + "\n\n" + side_block).strip() if main_concept else side_block
                transfer["mainConcept"] = main_concept
                transfer["imagePath"] = loaded.get("imagePath", "")
                transfer["embeddedImagePaths"] = loaded.get("embeddedImagePaths", [])
                transfer["message"] = "Loaded existing card URL into builders."
            return transfer
        except Exception as e:
            self._log_event("card_url_to_builders_error", {"url": url, "error": str(e)})
            return {"ok": False, "error": f"Load card URL to builders failed: {e}"}

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

    def card_url_to_main_concept(self, url, settings=None):
        """Load an existing card/project URL directly into Main Concept without AI."""
        try:
            loaded = self.load_import_url(url)
            if not loaded.get("ok"):
                return loaded
            result = self._loaded_card_to_main_concept_result(loaded, loaded.get("uploadedPath") or url)
            if result.get("ok"):
                result["sourceUrl"] = url
            self._log_event("card_url_to_main_concept_loaded", {
                "url": url,
                "loadedType": loaded.get("loadedType"),
                "main_concept_chars": len(result.get("mainConcept") or "") if result.get("ok") else 0,
                "embedded_images": len(loaded.get("embeddedImagePaths", []) or []),
            })
            return result
        except Exception as e:
            self._log_event("card_url_to_main_concept_error", {"url": url, "error": str(e)})
            return {"ok": False, "error": f"Load card URL to Main Concept failed: {e}"}

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

    def save_concept_attachment_url(self, url):
        try:
            res = self._download_url_to_file(url, folder=CONCEPT_ATTACHMENTS_DIR, allowed_suffixes={".txt", ".srt", ".vtt", ".md", ".pdf"}, fallback_name="attachment", max_bytes=40 * 1024 * 1024, prefix="url_attachment")
            if not res.get("ok"):
                return res
            path = Path(res["path"])
            # Reuse the same extraction logic by converting the downloaded file path result.
            result = self._concept_attachment_from_path(path)
            if result.get("ok"):
                result["sourceUrl"] = url
                # _concept_attachment_from_path copies the file again; remove first downloaded temp to avoid duplicate clutter.
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            return result
        except Exception as e:
            return {"ok": False, "error": f"Could not attach URL: {e}"}

    def select_import_file(self):
        """Legacy import entry point kept for older UI paths.

        Use the same modern OS picker as Load Saved / Load Card to Main Concept
        instead of PyWebView's basic fallback picker.
        """
        return self.pick_saved_file()

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
            add("Natural English Image Prompt", ext.get("natural_image_prompt", ""))

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
            ("natural_image_prompt", "Natural English Image Prompt"),
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
        workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
        project_tabs = project.get("characterTabs") if isinstance(project.get("characterTabs"), list) else []
        workspace_tabs = workspace.get("characterTabs") if isinstance(workspace.get("characterTabs"), list) else []
        character_tabs = project_tabs or workspace_tabs or []

        def tab_output_value(tab):
            if not isinstance(tab, dict):
                return ""
            for key in ("output", "fullTextOutput", "fullText", "fullTextOutputText", "outputText", "cardText", "cardOutput", "raw_card", "rawCard", "text", "content"):
                value = str(tab.get(key) or "").strip()
                if value:
                    return value
            return ""

        primary_tab = next((tab for tab in character_tabs if tab_output_value(tab)), {})
        output = (
            str(project.get("output") or "").strip()
            or str(workspace.get("output") or "").strip()
            or str(project.get("fullTextOutput") or "").strip()
            or str(workspace.get("fullTextOutput") or "").strip()
            or str(project.get("fullText") or "").strip()
            or str(workspace.get("fullText") or "").strip()
            or str(project.get("outputText") or "").strip()
            or str(workspace.get("outputText") or "").strip()
            or str(project.get("raw_card") or "").strip()
            or str(workspace.get("raw_card") or "").strip()
            or str(project.get("rawCard") or "").strip()
            or str(workspace.get("rawCard") or "").strip()
            or tab_output_value(primary_tab)
            or ""
        )
        loaded = {
            "ok": True,
            "loadedType": "project",
            "concept": project.get("concept", ""),
            "output": output,
            "settings": self._normalise_settings(project.get("settings") or {}),
            "template": project.get("template") or self.template,
            "imagePath": (project.get("imagePath") or project.get("cardImagePath") or workspace.get("cardImagePath") or workspace.get("imagePath") or (primary_tab.get("cardImagePath") if isinstance(primary_tab, dict) else "") or (primary_tab.get("imagePath") if isinstance(primary_tab, dict) else "") or ""),
            "cardImagePath": (project.get("cardImagePath") or project.get("imagePath") or workspace.get("cardImagePath") or workspace.get("imagePath") or (primary_tab.get("cardImagePath") if isinstance(primary_tab, dict) else "") or (primary_tab.get("imagePath") if isinstance(primary_tab, dict) else "") or ""),
            "imageDataUrl": project.get("imageDataUrl") or workspace.get("imageDataUrl") or project.get("cardImageDataUrl") or workspace.get("cardImageDataUrl") or (primary_tab.get("imageDataUrl") if isinstance(primary_tab, dict) else "") or (primary_tab.get("cardImageDataUrl") if isinstance(primary_tab, dict) else "") or "",
            "sourcePath": project.get("sourcePath") or "",
            "projectPath": project.get("projectPath") or "",
            "builderState": project.get("builderState") or workspace.get("builderState") or {},
            "qnaAnswers": project.get("qnaAnswers") or project.get("qaAnswers") or project.get("qna") or project.get("qa") or workspace.get("qnaAnswers") or workspace.get("qaAnswers") or workspace.get("qna") or workspace.get("qa") or (primary_tab.get("qnaAnswers") if isinstance(primary_tab, dict) else "") or (primary_tab.get("qaAnswers") if isinstance(primary_tab, dict) else "") or (primary_tab.get("qna") if isinstance(primary_tab, dict) else "") or (primary_tab.get("qa") if isinstance(primary_tab, dict) else "") or "",
            "qaAnswers": project.get("qaAnswers") or project.get("qnaAnswers") or project.get("qa") or project.get("qna") or workspace.get("qaAnswers") or workspace.get("qnaAnswers") or workspace.get("qa") or workspace.get("qna") or (primary_tab.get("qaAnswers") if isinstance(primary_tab, dict) else "") or (primary_tab.get("qnaAnswers") if isinstance(primary_tab, dict) else "") or (primary_tab.get("qa") if isinstance(primary_tab, dict) else "") or (primary_tab.get("qna") if isinstance(primary_tab, dict) else "") or "",
            "browserDescription": project.get("browserDescription") or workspace.get("browserDescription") or "",
            "browserDescriptionSourceHash": project.get("browserDescriptionSourceHash") or workspace.get("browserDescriptionSourceHash") or "",
            "cardRating": project.get("cardRating") or workspace.get("cardRating") or "",
            "cardRatingReasoning": project.get("cardRatingReasoning") or workspace.get("cardRatingReasoning") or "",
            "cardRatingDetails": project.get("cardRatingDetails") if isinstance(project.get("cardRatingDetails"), list) else (workspace.get("cardRatingDetails") if isinstance(workspace.get("cardRatingDetails"), list) else []),
            "cardRatingSourceHash": project.get("cardRatingSourceHash") or workspace.get("cardRatingSourceHash") or "",
            "tags": project.get("tags") or workspace.get("tags") or self._extract_tags_from_output(output, project.get("template") or self.template),
            "virtualFolderId": str(project.get("virtualFolderId") or workspace.get("virtualFolderId") or ""),
            "emotionImages": project.get("emotionImages") or workspace.get("emotionImages") or (primary_tab.get("emotionImages") if isinstance(primary_tab, dict) else []) or [],
            "generatedImages": project.get("generatedImages") or workspace.get("generatedImages") or (primary_tab.get("generatedImages") if isinstance(primary_tab, dict) else []) or [],
            "characterTabs": character_tabs,
            "conceptTabs": project.get("conceptTabs") or workspace.get("conceptTabs") or [],
            "manualTabs": project.get("manualTabs") or workspace.get("manualTabs") or [],
            "activeConceptTabIndex": project.get("activeConceptTabIndex", workspace.get("activeConceptTabIndex", 0)),
            "activeManualGuideTabIndex": project.get("activeManualGuideTabIndex", workspace.get("activeManualGuideTabIndex", 0)),
            "emotionManifest": project.get("emotionManifest") or workspace.get("emotionManifest") or "",
            "visionDescription": project.get("visionDescription") or workspace.get("visionDescription") or "",
            "conceptAttachments": project.get("conceptAttachments") or workspace.get("conceptAttachments") or [],
            "workspace": workspace,
            # Front Porch Group Card projects keep the browser-readable summary
            # in output, while the actual portable card lives in groupPayload /
            # .group.png. Preserve those fields through load/export paths so a
            # Browser Export JSON/PNG action does not accidentally convert the
            # summary text into a normal Chara V2 card.
            "isGroupCard": bool(project.get("isGroupCard") or workspace.get("isGroupCard")),
            "groupCardMode": project.get("groupCardMode") or workspace.get("groupCardMode") or "",
            "groupCardPath": project.get("groupCardPath") or workspace.get("groupCardPath") or project.get("exportedPath") or "",
            "groupJsonPath": project.get("groupJsonPath") or workspace.get("groupJsonPath") or "",
            "groupPayload": project.get("groupPayload") if isinstance(project.get("groupPayload"), dict) else (workspace.get("groupPayload") if isinstance(workspace.get("groupPayload"), dict) else {}),
            "memberProjectPaths": project.get("memberProjectPaths") if isinstance(project.get("memberProjectPaths"), list) else (workspace.get("memberProjectPaths") if isinstance(workspace.get("memberProjectPaths"), list) else []),
            "exportFormat": project.get("exportFormat") or workspace.get("exportFormat") or "",
            "frontend": project.get("frontend") or workspace.get("frontend") or "",
            "message": "Loaded full Character Card Forge project content. Global Settings were kept unchanged.",
        }
        # If an older saved project kept a generated-image URL as cardImagePath,
        # materialize it on load so the editor/exporter shows and uses a stable
        # local PNG/JPG/WebP path instead of a remote URL.
        raw_image_path = str(loaded.get("imagePath") or "").strip()
        if raw_image_path:
            local_image_path = self._ensure_local_card_image_path(raw_image_path, "card", "load_project_payload")
            if local_image_path:
                loaded["imagePath"] = local_image_path
                loaded["cardImagePath"] = local_image_path
                if isinstance(loaded.get("settings"), dict):
                    loaded["settings"]["cardImagePath"] = local_image_path
        # Prefer the actual file path used for this load. Older project JSON can
        # contain a stale embedded projectPath, while workspace_assets are keyed
        # by the real saved latest_ccf_project.json path.
        project_path = str(path) if 'path' in locals() else ""
        embedded_project_path = project.get("projectPath") or ""
        if project_path:
            loaded = self._hydrate_workspace_from_db_assets(project_path, loaded)
            loaded = self._materialize_loaded_project_card_image(loaded, project_path, "load_project_payload")
        if embedded_project_path and embedded_project_path != project_path:
            loaded = self._hydrate_workspace_from_db_assets(embedded_project_path, loaded)
            loaded = self._materialize_loaded_project_card_image(loaded, embedded_project_path, "load_project_embedded_payload")
        return loaded

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
            "version": self.get_app_version(),
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

    def _image_file_data_url(self, path, mime=None):
        try:
            p = Path(str(path or ""))
            if not p.exists() or p.is_dir():
                return ""
            suffix = p.suffix.lower()
            detected = mime or {
                ".webp": "image/webp",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }.get(suffix, "image/png")
            return "data:" + detected + ";base64," + base64.b64encode(p.read_bytes()).decode("ascii")
        except Exception:
            return ""

    def _thumbnail_reference_exists(self, value):
        try:
            text = str(value or "").strip()
            if not text:
                return False
            # The Browser UI can always render data URLs. file:// thumbnails from
            # beta6 were fast but unreliable in pywebview, so treat them as stale.
            if text.startswith("data:"):
                return True
            if text.startswith("file://"):
                return False
            return Path(text).exists()
        except Exception:
            return False

    def _browser_preview_reference(self, source_path, project_folder, max_size=(320, 420), quality=48):
        """Return a browser-safe lightweight thumbnail data URL.

        The WebP file is cached beside the project for speed, but the value sent to
        the frontend is a data URL. That avoids broken file:// images in pywebview
        while still keeping Browser payloads far smaller than full PNG thumbnails.
        """
        preview_path = None
        try:
            folder = Path(str(project_folder or "")).resolve()
            if folder.exists():
                cache_dir = folder / ".ccf_browser_cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                preview_path = cache_dir / "browser_thumb.webp"
        except Exception:
            preview_path = None

        try:
            src = Path(str(source_path or "")).resolve()
            if src.exists() and not src.is_dir() and preview_path is not None:
                src_stat = src.stat()
                needs_refresh = True
                if preview_path.exists():
                    try:
                        prev_stat = preview_path.stat()
                        needs_refresh = not (
                            prev_stat.st_size > 0
                            and int(getattr(prev_stat, "st_mtime_ns", int(prev_stat.st_mtime * 1_000_000_000))) >= int(getattr(src_stat, "st_mtime_ns", int(src_stat.st_mtime * 1_000_000_000)))
                        )
                    except Exception:
                        needs_refresh = True
                if needs_refresh:
                    with Image.open(src) as img:
                        if img.mode not in ("RGB", "RGBA"):
                            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                        img.thumbnail(max_size, Image.LANCZOS)
                        if img.mode == "RGBA":
                            img.save(preview_path, format="WEBP", quality=int(quality), method=6, lossless=False)
                        else:
                            img.convert("RGB").save(preview_path, format="WEBP", quality=int(quality), method=6)
                if preview_path.exists() and preview_path.stat().st_size > 0:
                    data_url = self._image_file_data_url(preview_path, "image/webp")
                    if data_url:
                        return data_url
                # If WebP support is missing in the runtime Pillow build, still return
                # a small preview instead of a broken Browser image.
                fallback = self._image_data_url(src, max_size=max_size)
                if fallback:
                    return fallback
        except Exception:
            pass

        # If the original image cannot be found but an earlier cached WebP exists,
        # keep using it instead of breaking existing Browser tiles.
        try:
            if preview_path is not None and preview_path.exists() and preview_path.stat().st_size > 0:
                data_url = self._image_file_data_url(preview_path, "image/webp")
                if data_url:
                    return data_url
        except Exception:
            pass
        try:
            return self._image_data_url(source_path, max_size=max_size)
        except Exception:
            return ""

    def image_preview_data_url(self, path):
        try:
            # Resolve the same sources export uses: file:// URLs, managed card-image
            # paths, generated-image filenames, data URLs, and raw/base64 image blobs.
            # This keeps the Quick Save / Image preview from breaking after reload
            # when the saved project only has a generated image in the asset DB or
            # stores the generated image by filename.
            local_path = self._ensure_local_card_image_path(path, "card", "image_preview_data_url") if path else ""
            data_url = self._image_data_url(local_path or path, max_size=(420, 560))
            if not data_url:
                return {"ok": False, "error": "Image preview could not be loaded."}
            return {"ok": True, "dataUrl": data_url, "path": local_path or str(path or "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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

    def _card_rating_source_hash(self, output, concept='', browser_description=''):
        return self._hash_text("\n---CARD-RATING---\n" + str(output or '') + "\n---CONCEPT---\n" + str(concept or '') + "\n---BROWSER-DESCRIPTION---\n" + str(browser_description or ''))

    def _normalise_card_rating_value(self, value):
        try:
            if value is None or value == "":
                return ""
            m = re.search(r"\d+(?:\.\d+)?", str(value))
            if not m:
                return ""
            num = float(m.group(0))
            if num < 0:
                num = 0
            if num > 10:
                num = 10
            if abs(num - round(num)) < 0.05:
                return str(int(round(num)))
            return f"{num:.1f}".rstrip("0").rstrip(".")
        except Exception:
            return ""

    def _first_non_empty_value(self, obj, keys, default=""):
        """Return the first present/non-empty value from a dict without treating 0 as missing."""
        if not isinstance(obj, dict):
            return default
        for key in keys:
            if key in obj:
                value = obj.get(key)
                if value is not None and value != "":
                    return value
        return default

    def _card_rating_detail_key_candidates(self):
        return [
            "details", "detailRatings", "detail_ratings", "detailedRatings", "detailed_ratings",
            "elementRatings", "element_ratings", "elements", "elementScores", "element_scores",
            "criteria", "criteriaRatings", "criteria_ratings", "criteriaScores", "criteria_scores",
            "breakdown", "breakdownByElement", "breakdown_by_element", "categoryBreakdown", "category_breakdown",
            "categories", "categoryRatings", "category_ratings", "scores", "ratings", "ratingDetails", "rating_details",
            "perElementRatings", "per_element_ratings", "aspectRatings", "aspect_ratings", "sectionRatings", "section_ratings",
        ]

    def _normalise_card_rating_details(self, value):
        """Return a compact list of per-category rating objects for UI display.

        The rating provider can be annoyingly creative. Accept normal JSON arrays,
        dict maps, nested aliases, JSON strings, and common ``score_out_of_10``-style
        keys, while still refusing arbitrary project metadata as rows.
        """
        details = []
        try:
            if isinstance(value, str):
                raw_text = value.strip()
                if not raw_text:
                    return []
                try:
                    return self._normalise_card_rating_details(json.loads(raw_text))
                except Exception:
                    # Last-resort text parser for lines like:
                    # Concept Clarity: 9/10 - Clear hook and premise.
                    rows = []
                    for line in raw_text.splitlines():
                        m = re.match(r"^\s*(?:[-*•]\s*)?(?P<name>[A-Za-z][A-Za-z0-9 /{}()&+._\-]{2,80})\s*[:=\-–—]\s*(?P<score>\d+(?:\.\d+)?)\s*(?:/\s*10)?(?:\s*[-–—:]\s*(?P<reason>.*))?$", line.strip())
                        if m:
                            rows.append({"name": m.group('name').strip(), "rating": m.group('score'), "reason": (m.group('reason') or '').strip()})
                    value = rows
            iterable = []
            name_keys = ["name", "category", "element", "criteria", "criterion", "field", "section", "title", "aspect", "label"]
            score_keys = ["rating", "score", "value", "points", "grade", "ratingOutOf10", "rating_out_of_10", "scoreOutOf10", "score_out_of_10", "pointsOutOf10", "points_out_of_10"]
            reason_keys = ["reason", "reasoning", "comment", "comments", "note", "notes", "feedback", "explanation", "rationale", "why", "justification", "shortReason", "short_reason"]
            if isinstance(value, dict):
                # A single row object: {"name": "Concept", "score": 8, "comment": "..."}
                single_name = self._first_non_empty_value(value, name_keys)
                single_score = self._first_non_empty_value(value, score_keys)
                if single_name and single_score != "":
                    iterable = [value]
                else:
                    # A container object: {"elementRatings": [...]} or {"scores": {"Concept": 8}}
                    for key in self._card_rating_detail_key_candidates():
                        if key in value:
                            nested = self._normalise_card_rating_details(value.get(key))
                            if nested:
                                return nested
                    skip_keys = {
                        "ok", "success", "error", "errors", "projectPath", "project_path", "path",
                        "rating", "score", "overall", "overallRating", "overall_rating", "cardRating", "card_rating",
                        "reasoning", "reason", "summary", "strengths", "improvements", "areas_to_improve", "areasToImprove",
                        "browser_description", "browserDescription", "browserDescriptionSource", "browserDescriptionSourceHash",
                        "name", "title", "source", "sourceHash", "source_hash", "cardRatingReasoning", "cardRatingSourceHash",
                        "result", "evaluation", "analysis", "rating_result", "ratingResult", "workspace", "settings", "output", "concept",
                    }
                    for k, v in value.items():
                        if str(k) in skip_keys:
                            continue
                        if isinstance(v, dict):
                            item = dict(v)
                            item.setdefault("name", k)
                        else:
                            item = {"name": k, "rating": v, "reason": ""}
                        iterable.append(item)
            elif isinstance(value, list):
                iterable = value
            else:
                iterable = []
            seen = set()
            for item in iterable:
                if isinstance(item, str):
                    parsed = self._normalise_card_rating_details(item)
                    for row in parsed:
                        if row:
                            details.append(row)
                    continue
                if not isinstance(item, dict):
                    continue
                name = str(self._first_non_empty_value(item, name_keys) or "").strip()
                if not name:
                    continue
                key = re.sub(r"\s+", " ", name.lower()).strip()
                if key in seen:
                    continue
                seen.add(key)
                raw_rating = self._first_non_empty_value(item, score_keys)
                if isinstance(raw_rating, dict):
                    raw_rating = self._first_non_empty_value(raw_rating, ["rating", "score", "value", "points", "grade", "outOf10", "out_of_10"])
                rating = self._normalise_card_rating_value(raw_rating)
                reason = str(self._first_non_empty_value(item, reason_keys) or "").strip()
                if not reason:
                    reason = str(self._first_non_empty_value(item, ["status", "state"]) or "").strip()
                if len(reason) > 260:
                    reason = reason[:260].rsplit(" ", 1)[0].rstrip() + "…"
                # Keep rows that have a usable score or a reason; this lets a
                # provider omit one score while still showing its comment.
                if not rating and not reason:
                    continue
                details.append({"name": name[:80], "rating": rating, "reason": reason})
                if len(details) >= 12:
                    break
        except Exception:
            return []
        return details

    def _parse_card_rating_response(self, text):
        raw = re.sub(r'(?is)^```(?:json)?\s*|\s*```$', '', str(text or '')).strip()
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = None
            if data is None:
                m = re.search(r"\[.*\]", raw, re.S)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except Exception:
                        data = None
        rating = ""
        reasoning = ""
        details = []
        if isinstance(data, list):
            details = self._normalise_card_rating_details(data)
        if isinstance(data, dict):
            # Some providers wrap the useful JSON one level down.
            payloads = [data]
            for key in ("result", "evaluation", "cardRating", "card_rating", "rating_result", "ratingResult", "analysis"):
                nested = data.get(key)
                if isinstance(nested, dict):
                    payloads.append(nested)
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                if not rating:
                    rating = self._normalise_card_rating_value(self._first_non_empty_value(payload, [
                        "rating", "score", "overall", "overallRating", "overall_rating", "cardRating", "card_rating", "quality", "qualityScore", "quality_score", "ratingOutOf10", "rating_out_of_10", "scoreOutOf10", "score_out_of_10"
                    ]))
                if not details:
                    for key in self._card_rating_detail_key_candidates():
                        if key in payload:
                            details = self._normalise_card_rating_details(payload.get(key))
                            if details:
                                break
                if not details:
                    details = self._normalise_card_rating_details(payload)
                if not reasoning:
                    reasoning_parts = []
                    for key in ("reasoning", "reason", "summary", "overallReasoning", "overall_reasoning", "commentary", "comments", "feedback"):
                        value = payload.get(key)
                        if value:
                            reasoning_parts.append(str(value).strip())
                    for key, label in (("strengths", "Strengths"), ("improvements", "Areas to improve"), ("areas_to_improve", "Areas to improve"), ("areasToImprove", "Areas to improve"), ("suggestions", "Suggestions")):
                        value = payload.get(key)
                        if isinstance(value, list):
                            lines = [str(v).strip() for v in value if str(v).strip()]
                            if lines:
                                reasoning_parts.append(label + ":\n" + "\n".join(f"- {x}" for x in lines[:6]))
                        elif value:
                            reasoning_parts.append(f"{label}: {str(value).strip()}")
                    reasoning = "\n\n".join(x for x in reasoning_parts if x).strip()
                if rating and reasoning and details:
                    break
        if not details:
            details = self._normalise_card_rating_details(raw)
        if not rating:
            m = re.search(r"(?:rating|score)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*/\s*10", raw, re.I)
            if not m:
                m = re.search(r"\b(\d+(?:\.\d+)?)\s*/\s*10\b", raw, re.I)
            if m:
                rating = self._normalise_card_rating_value(m.group(1))
        if not reasoning:
            reasoning = raw.strip()
            reasoning = re.sub(r"(?i)^\s*(?:rating|score)\s*[:=]?\s*\d+(?:\.\d+)?\s*/?\s*10\s*[-–—:]*\s*", "", reasoning).strip()
        if len(reasoning) > 1800:
            reasoning = reasoning[:1800].rsplit(" ", 1)[0].rstrip() + "…"
        return rating, reasoning, details

    def _card_rating_expected_detail_names(self):
        return [
            "Concept Clarity", "Character Identity", "Personality Depth", "Scenario Hook",
            "Relationship to {{user}}", "First Message", "Formatting", "Specificity",
            "Roleplay Usability", "Continuity/Lore",
        ]

    def _generate_required_card_rating_details(self, output, concept, browser_description, rating, reasoning, settings=None, reason_label='missing_details'):
        """Force a dedicated AI request for true per-element rating details.

        The normal card-rating prompt can be ignored by some models, which may return only
        {"rating": ..., "reasoning": ...}.  This helper is intentionally separate and logs
        as text_generation_request attempt=card_rating_details_required so the debug log proves
        whether the second request happened.
        """
        try:
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            validation = self._validate_text_api_settings(merged)
            if not validation.get('ok'):
                self._log_event('card_rating_details_required_skipped_settings', {
                    'reason': reason_label,
                    'error': validation.get('error'),
                    'hasRating': bool(self._normalise_card_rating_value(rating)),
                })
                return []
            if not self._normalise_card_rating_value(rating):
                self._log_event('card_rating_details_required_skipped_no_rating', {'reason': reason_label})
                return []

            sections = self._parse_sections(output or '')
            compact = {
                "overall_rating": self._normalise_card_rating_value(rating),
                "overall_reasoning": str(reasoning or '')[:1400],
                "name": self._extract_name(output or ''),
                "description": sections.get("description", "")[:1600],
                "personality": sections.get("personality", "")[:2000],
                "scenario": sections.get("scenario", "")[:2000],
                "first_message": sections.get("first_message", "")[:1400],
                "example_dialogues": sections.get("example_dialogues", "")[:1000],
                "tags": sections.get("tags", "")[:500],
                "concept": str(concept or '')[:1400],
                "browser_description": str(browser_description or '')[:900],
            }
            expected = self._card_rating_expected_detail_names()
            expected_text = ", ".join(expected)
            local_settings = dict(merged)
            local_settings['maxOutputTokens'] = min(2400, int(local_settings.get('maxOutputTokens') or 2400))
            local_settings['temperature'] = min(0.2, float(local_settings.get('temperature', 0.2) or 0.2))
            model_name = (local_settings.get('aiSuggestionModel') or local_settings.get('model') or '').strip()
            self._log_event('card_rating_details_required_start', {
                'reason': reason_label,
                'rating': self._normalise_card_rating_value(rating),
                'model': model_name,
            })

            prompt = "\n".join([
                "You previously rated this fictional AI character card overall, but the saved project has no per-element breakdown.",
                "Your task is ONLY to generate the missing Card Rating Details rows.",
                "Do NOT repeat only the overall rating. Do NOT return only reasoning.",
                "Return ONLY valid JSON with this exact top-level key: details.",
                "Schema: {\"details\":[{\"name\":\"Concept Clarity\",\"rating\":8,\"reason\":\"one short sentence\"}]}",
                "Include exactly 10 detail objects, in this exact order: " + expected_text + ".",
                "Each rating must be numeric 0-10. Use varied scores where some elements are stronger or weaker.",
                "Each reason must be specific to the card, not generic fallback wording.",
                "No markdown. No prose outside JSON. No extra top-level keys.",
                "",
                "CARD DATA JSON:",
                json.dumps(compact, ensure_ascii=False, indent=2),
            ]).strip()

            check = self._context_check(prompt, merged, mode_label='Card rating details required')
            if not check.get('ok'):
                self._log_event('card_rating_details_required_skipped_context', {'reason': reason_label, 'error': check.get('error')})
                return []
            text = self._chat_once(prompt, local_settings, model_name, 'card_rating_details_required')
            self._log_event('card_rating_details_required_raw', {'reason': reason_label, 'preview': str(text or '')[:1200]})
            if self._looks_like_text_refusal(text):
                self._log_event('card_rating_details_required_refusal', {'reason': reason_label})
                return []
            _rating, _reasoning, details = self._parse_card_rating_response(text)
            details = self._normalise_card_rating_details(details)
            if not details:
                raw = re.sub(r'(?is)^```(?:json)?\s*|\s*```$', '', str(text or '')).strip()
                try:
                    data = json.loads(raw)
                except Exception:
                    m_obj = re.search(r"\{.*\}", raw, re.S)
                    m_arr = re.search(r"\[.*\]", raw, re.S)
                    data = None
                    if m_obj:
                        try:
                            data = json.loads(m_obj.group(0))
                        except Exception:
                            data = None
                    if data is None and m_arr:
                        try:
                            data = json.loads(m_arr.group(0))
                        except Exception:
                            data = None
                details = self._normalise_card_rating_details(data if data is not None else raw)
            if details:
                self._log_event('card_rating_details_required_parsed', {'reason': reason_label, 'count': len(details)})
                return details

            # Some models behave better with plain text than JSON after ignoring a JSON-only request.
            plain_prompt = "\n".join([
                "Generate the missing Card Rating Details for this fictional AI character card.",
                "Return exactly 10 lines and nothing else.",
                "Line format: Element Name: score/10 - one specific reason",
                "Elements, in order: " + expected_text + ".",
                "Use varied numeric scores where appropriate.",
                "",
                "CARD DATA JSON:",
                json.dumps(compact, ensure_ascii=False, indent=2),
            ]).strip()
            check = self._context_check(plain_prompt, merged, mode_label='Card rating details required plain')
            if not check.get('ok'):
                self._log_event('card_rating_details_required_plain_skipped_context', {'reason': reason_label, 'error': check.get('error')})
                return []
            text2 = self._chat_once(plain_prompt, local_settings, model_name, 'card_rating_details_required_plain')
            self._log_event('card_rating_details_required_plain_raw', {'reason': reason_label, 'preview': str(text2 or '')[:1200]})
            if self._looks_like_text_refusal(text2):
                return []
            _rating2, _reasoning2, details2 = self._parse_card_rating_response(text2)
            details2 = self._normalise_card_rating_details(details2 or text2)
            if details2:
                self._log_event('card_rating_details_required_plain_parsed', {'reason': reason_label, 'count': len(details2)})
                return details2
            self._log_event('card_rating_details_required_empty', {'reason': reason_label})
            return []
        except Exception as e:
            self._log_event('card_rating_details_required_failed', {'reason': reason_label, 'error': str(e)})
            return []

    def _repair_missing_card_rating_details(self, output, concept, browser_description, rating, reasoning, settings):
        """Ask for only the missing per-element breakdown when the first rating call omitted it."""
        forced = self._generate_required_card_rating_details(
            output, concept, browser_description, rating, reasoning, settings,
            reason_label='ensure_repair_missing_details'
        )
        if forced:
            return forced
        try:
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            if not self._validate_text_api_settings(merged).get('ok'):
                return []
            sections = self._parse_sections(output or '')
            compact = {
                "overall_rating": rating,
                "overall_reasoning": str(reasoning or '')[:1200],
                "name": self._extract_name(output or ''),
                "description": sections.get("description", "")[:1400],
                "personality": sections.get("personality", "")[:1800],
                "scenario": sections.get("scenario", "")[:1800],
                "first_message": sections.get("first_message", "")[:1200],
                "example_dialogues": sections.get("example_dialogues", "")[:900],
                "tags": sections.get("tags", "")[:400],
                "concept": str(concept or '')[:1200],
                "browser_description": str(browser_description or '')[:700],
            }
            expected = ", ".join(self._card_rating_expected_detail_names())
            prompts = [
                "\n".join([
                    "The previous card-quality rating response did not include the required per-element breakdown.",
                    "Create ONLY the missing breakdown for this fictional AI character card.",
                    "Return ONLY valid JSON in exactly this shape:",
                    "{\"details\":[{\"name\":\"Concept Clarity\",\"rating\":0-10,\"reason\":\"one short sentence\"}]}",
                    "Include exactly these elements, in this order: " + expected + ".",
                    "Use 0-10 numeric ratings. Vary the scores where the card has stronger/weaker areas.",
                    "No markdown. No prose outside JSON. No extra top-level keys.",
                    "",
                    "CARD DATA JSON:",
                    json.dumps(compact, ensure_ascii=False, indent=2),
                ]).strip(),
                "\n".join([
                    "Return ONLY a JSON array of 10 rating objects for this fictional AI character card.",
                    "Every object must have name, rating, and reason.",
                    "Names, in order: " + expected + ".",
                    "rating must be a number from 0 to 10. reason must be one concise sentence.",
                    "Do not include the overall rating. Do not use markdown.",
                    "CARD DATA JSON:",
                    json.dumps(compact, ensure_ascii=False, indent=2),
                ]).strip(),
            ]
            local_settings = dict(merged)
            local_settings['maxOutputTokens'] = min(2000, int(local_settings.get('maxOutputTokens') or 2000))
            local_settings['temperature'] = min(0.25, float(local_settings.get('temperature', 0.25) or 0.25))
            model_name = (local_settings.get('aiSuggestionModel') or local_settings.get('model') or '').strip()
            for idx, prompt in enumerate(prompts, start=1):
                check = self._context_check(prompt, merged, mode_label='Card rating details repair')
                if not check.get('ok'):
                    self._log_event('card_rating_details_repair_skipped_context', {"error": check.get('error'), "attempt": idx})
                    continue
                text = self._chat_once(prompt, local_settings, model_name, 'card_rating_details')
                self._log_event('card_rating_details_repair_raw', {'attempt': idx, 'preview': str(text or '')[:1200]})
                if self._looks_like_text_refusal(text):
                    continue
                parsed_rating, parsed_reasoning, parsed_details = self._parse_card_rating_response(text)
                if parsed_details:
                    return parsed_details
                raw = re.sub(r'(?is)^```(?:json)?\s*|\s*```$', '', str(text or '')).strip()
                try:
                    data = json.loads(raw)
                except Exception:
                    m_obj = re.search(r"\{.*\}", raw, re.S)
                    m_arr = re.search(r"\[.*\]", raw, re.S)
                    data = None
                    if m_obj:
                        try:
                            data = json.loads(m_obj.group(0))
                        except Exception:
                            data = None
                    if data is None and m_arr:
                        try:
                            data = json.loads(m_arr.group(0))
                        except Exception:
                            data = None
                parsed = self._normalise_card_rating_details(data if data is not None else raw)
                if parsed:
                    return parsed
        except Exception as e:
            self._log_event('card_rating_details_repair_failed', {'error': str(e)})
        return []

    def _fallback_card_rating_details(self, output, concept='', browser_description='', rating='', reasoning=''):
        """Create a conservative per-element breakdown when the model gives an overall score but omits details.

        This prevents the UI from having a 9/10 card with an empty Details modal.  The rows are
        intentionally labelled in their wording as a fallback-style breakdown: useful enough for the
        user to inspect, but not pretending the model supplied bespoke per-element comments.
        """
        try:
            base_text = self._normalise_card_rating_value(rating)
            if not base_text:
                return []
            base = float(base_text)
            sections = self._parse_sections(output or '')
            output_text = str(output or '')
            concept_text = str(concept or '')
            desc_text = str(browser_description or '')

            def has_section(name, min_len=80):
                return len(str(sections.get(name, '') or '').strip()) >= min_len

            def clamp_score(delta=0.0):
                score = max(0.0, min(10.0, base + float(delta)))
                if abs(score - round(score)) < 0.05:
                    return str(int(round(score)))
                return f"{score:.1f}".rstrip('0').rstrip('.')

            def row(name, delta, good, weak):
                present_reason = good if delta >= -0.2 else weak
                return {"name": name, "rating": clamp_score(delta), "reason": present_reason[:220]}

            has_name = bool(self._extract_name(output_text))
            has_desc = has_section('description', 100) or len(desc_text) >= 80
            has_personality = has_section('personality', 160)
            has_scenario = has_section('scenario', 120)
            has_first = has_section('first_message', 80) or has_section('first message', 80)
            user_anchor = '{{user}}' in output_text or '{{ user }}' in output_text or '{{char}}' in output_text
            dialogue_present = has_section('example_dialogues', 120) or has_section('example dialogue', 120)
            headings = len(re.findall(r'(?m)^\s*(?:#{1,3}\s*)?[A-Za-z][A-Za-z /{}()\-]{2,40}\s*[:：]\s*$', output_text))
            output_len = len(output_text.strip())
            has_lore = bool(re.search(r'(?i)\b(backstory|history|lore|family|past|secret|work|job|school|relationship|friend|rival)\b', output_text))

            details = [
                row('Concept Clarity', 0 if (concept_text.strip() or has_desc or has_scenario) else -0.8,
                    'The core premise is readable enough to support the overall rating.',
                    'The premise could use clearer framing so the roleplay starts with less guesswork.'),
                row('Character Identity', 0.2 if (has_name and has_desc) else -0.5,
                    'Name/identity and descriptive cues are present enough for the character to feel defined.',
                    'The card would benefit from stronger identity and visual/role definition.'),
                row('Personality Depth', 0.2 if has_personality else -0.6,
                    'The personality section gives the model useful behavioral direction.',
                    'More concrete traits, contradictions, and speech behavior would strengthen the personality.'),
                row('Scenario Hook', 0.1 if has_scenario else -0.7,
                    'The scenario gives the chat a playable starting situation.',
                    'The scenario hook needs more setup, stakes, or immediate direction.'),
                row('Relationship to {{user}}', 0.1 if user_anchor else -0.6,
                    'The card anchors the dynamic around {{user}} well enough for interaction.',
                    'The relationship with {{user}} should be stated more directly.'),
                row('First Message', 0.1 if has_first else -0.7,
                    'The opening message appears usable as a roleplay launch point.',
                    'A stronger first message would make the card easier to start from.'),
                row('Formatting', 0 if (headings >= 2 or output_len < 5000) else -0.4,
                    'The card is structured well enough for the frontend/model to read.',
                    'Formatting could be cleaner or more concise to reduce bloat.'),
                row('Specificity', 0.1 if output_len >= 1200 else -0.5,
                    'There is enough specific information to guide the character beyond a generic archetype.',
                    'More specific hooks, habits, boundaries, and details would improve consistency.'),
                row('Roleplay Usability', 0.2 if (has_scenario and has_first and has_personality) else -0.4,
                    'The card gives enough direction to support an ongoing chat.',
                    'Usability would improve with clearer behavior rules, scene setup, and opening momentum.'),
                row('Continuity/Lore', 0.1 if (has_lore or dialogue_present) else -0.3,
                    'The card includes enough supporting context to maintain continuity.',
                    'More lore, relationship context, or example dialogue would help long chats stay consistent.'),
            ]
            return self._normalise_card_rating_details(details)
        except Exception as e:
            self._log_event('card_rating_details_fallback_failed', {'error': str(e)})
            return []


    def _guaranteed_card_rating_details(self, output, concept='', browser_description='', rating='', reasoning=''):
        """Last-ditch deterministic breakdown so rated cards never save with an empty details array.

        The AI repair pass should normally create the real per-element comments. This method is
        deliberately simple, local, and non-AI: it only runs if every AI/detail parser path failed.
        """
        try:
            base_text = self._normalise_card_rating_value(rating) or "5"
            base = float(base_text)
        except Exception:
            base = 5.0
        text = "\n".join([str(output or ''), str(concept or ''), str(browser_description or ''), str(reasoning or '')])
        lower = text.lower()

        def present(pattern):
            return bool(re.search(pattern, lower, re.I | re.S))

        def score(delta):
            value = max(0.0, min(10.0, base + float(delta)))
            if abs(value - round(value)) < 0.05:
                return str(int(round(value)))
            return f"{value:.1f}".rstrip('0').rstrip('.')

        row_specs = [
            ("Concept Clarity", 0.2 if (concept or browser_description or present(r"\b(scenario|premise|hook|setup)\b")) else -0.5,
             "Core premise is present, but this is a deterministic safety breakdown because no AI element details were saved."),
            ("Character Identity", 0.1 if present(r"\b(name|description|appearance|age|occupation|role)\b") else -0.4,
             "Identity cues appear present enough for the model to track the character."),
            ("Personality Depth", 0.2 if present(r"\b(personality|trait|flaw|motivation|fear|habit|speech)\b") else -0.5,
             "Personality direction appears present, though true AI per-element notes were not returned."),
            ("Scenario Hook", 0.1 if present(r"\b(scenario|scene|first meet|opening|hook|event)\b") else -0.6,
             "The setup appears playable enough to support the overall rating."),
            ("Relationship to {{user}}", 0.1 if ('{{user}}' in text or '{{ user }}' in text or present(r"\b(user|relationship|dynamic)\b")) else -0.6,
             "The card appears to include a usable relationship anchor for {{user}}."),
            ("First Message", 0.1 if present(r"\b(first message|greeting|opening message|\*.*{{user}})\b") else -0.5,
             "Opening-message support appears present, but regenerate can replace this with AI-specific feedback."),
            ("Formatting", -0.2 if len(text) > 6500 else 0.1,
             "Formatting appears readable enough for the app/model to consume."),
            ("Specificity", 0.2 if len(text) > 1800 else -0.3,
             "The card appears to include enough specific material to avoid feeling generic."),
            ("Roleplay Usability", 0.1 if present(r"\b(scenario|first message|personality|{{user}})\b") else -0.4,
             "The saved card appears usable for chat, but true per-element AI notes were missing."),
            ("Continuity/Lore", 0.1 if present(r"\b(backstory|history|lore|family|friend|secret|past|job|school)\b") else -0.3,
             "Supporting continuity/lore appears present enough for the overall score."),
        ]
        return [{"name": name, "rating": score(delta), "reason": reason[:240]} for name, delta, reason in row_specs]

    def _ensure_card_rating_details(self, output, concept, browser_description, rating, reasoning, settings=None, existing_details=None, existing_source=''):
        """Return non-empty normalized rating details whenever a rating exists.

        Order of preference:
        1. Already parsed/saved real details.
        2. Details-only AI repair prompt.
        3. Heuristic fallback based on card structure.
        4. Guaranteed deterministic rows, so the frontend/database never store [] beside a rating.
        """
        details = self._normalise_card_rating_details(existing_details or [])
        if details:
            return details, (existing_source or 'existing')
        if not self._normalise_card_rating_value(rating):
            return [], 'none'
        try:
            repaired = self._repair_missing_card_rating_details(output, concept, browser_description, rating, reasoning, settings or self.settings)
            repaired = self._normalise_card_rating_details(repaired)
            if repaired:
                self._log_event('card_rating_details_ensure_repaired', {'count': len(repaired)})
                return repaired, 'ai_repair'
        except Exception as e:
            self._log_event('card_rating_details_ensure_repair_failed', {'error': str(e)})
        try:
            fallback = self._fallback_card_rating_details(output, concept, browser_description, rating, reasoning)
            fallback = self._normalise_card_rating_details(fallback)
            if fallback:
                self._log_event('card_rating_details_ensure_fallback', {'count': len(fallback)})
                return fallback, 'fallback'
        except Exception as e:
            self._log_event('card_rating_details_ensure_fallback_failed', {'error': str(e)})
        guaranteed = self._normalise_card_rating_details(self._guaranteed_card_rating_details(output, concept, browser_description, rating, reasoning))
        if guaranteed:
            self._log_event('card_rating_details_ensure_guaranteed', {'count': len(guaranteed)})
            return guaranteed, 'guaranteed'
        return [], 'none'

    def _boolish_from_value(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value or "").strip().lower()
        if text in {"true", "yes", "y", "1", "nsfw", "adult", "explicit"}:
            return True
        if text in {"false", "no", "n", "0", "sfw", "safe", "clean"}:
            return False
        return None

    def _parse_nsfw_flag_from_rating_text(self, text):
        try:
            data = self._loads_model_json(text)
        except Exception:
            data = None
        keys = [
            "isNsfw", "is_nsfw", "nsfw", "adult", "adultContent", "adult_content",
            "containsAdultContent", "contains_adult_content", "explicit", "explicitContent",
            "explicit_content", "needsNsfwTag", "needs_nsfw_tag", "markNsfw", "mark_nsfw",
        ]
        def walk(obj):
            if isinstance(obj, dict):
                for key in keys:
                    if key in obj:
                        parsed = self._boolish_from_value(obj.get(key))
                        if parsed is not None:
                            return parsed
                for key in ("result", "evaluation", "analysis", "metadata", "safety", "classification"):
                    if key in obj:
                        found = walk(obj.get(key))
                        if found is not None:
                            return found
            return None
        found = walk(data)
        if found is not None:
            return found
        raw = str(text or "")
        m = re.search(r"(?i)\b(?:isNsfw|is_nsfw|nsfw|adultContent|explicitContent|markNsfw)\b\s*[:=]\s*(true|false|yes|no|1|0|sfw|nsfw|adult|explicit)", raw)
        if m:
            return self._boolish_from_value(m.group(1))
        return None

    def _generate_card_nsfw_detection(self, output, concept='', browser_description='', settings=None, reason_label='missing_nsfw_flag'):
        """Ask the text model whether this saved card should receive the editable NSFW marker tag."""
        output = output or ''
        if not output.strip() and not str(concept or '').strip():
            return None
        merged = self._normalise_settings({**self.settings, **(settings or {})})
        if not self._validate_text_api_settings(merged).get('ok'):
            return None
        try:
            sections = self._parse_sections(output)
            compact = {
                "name": self._extract_name(output),
                "description": sections.get("description", "")[:1600],
                "personality": sections.get("personality", "")[:1800],
                "scenario": sections.get("scenario", "")[:1800],
                "first_message": sections.get("first_message", "")[:1200],
                "example_dialogues": sections.get("example_dialogues", "")[:900],
                "tags": sections.get("tags", "")[:500],
                "concept": str(concept or '')[:1200],
                "browser_description": str(browser_description or '')[:700],
            }
            prompt = "\n".join([
                "Classify this fictional AI character card for library tagging only.",
                "Return ONLY valid JSON with exactly this shape: {\"isNsfw\": true/false, \"reason\": \"short reason\"}",
                "Set isNsfw true when the card contains explicit sexual content, porn/adult-industry content, fetish/kink roleplay, nudity/explicit sexual imagery, or is clearly intended for adult/NSFW roleplay.",
                "Set isNsfw false for non-explicit romance, flirting, swimsuits, violence, angst, or mature themes without explicit sexual/adult-roleplay intent.",
                "Do not judge whether the content is good or bad; this only decides whether the saved card should receive the user-configured NSFW marker tag.",
                "",
                "CARD DATA JSON:",
                json.dumps(compact, ensure_ascii=False, indent=2),
            ]).strip()
            check = self._context_check(prompt, merged, mode_label='Card NSFW detection')
            if not check.get('ok'):
                self._log_event('card_nsfw_detection_skipped_context', {'reason': reason_label, 'error': check.get('error')})
                return None
            local_settings = dict(merged)
            local_settings['maxOutputTokens'] = min(250, int(local_settings.get('maxOutputTokens') or 250))
            local_settings['temperature'] = min(0.15, float(local_settings.get('temperature', 0.15) or 0.15))
            model_name = (local_settings.get('aiSuggestionModel') or local_settings.get('model') or '').strip()
            text = self._chat_once(prompt, local_settings, model_name, 'card_nsfw_detection')
            flag = self._parse_nsfw_flag_from_rating_text(text)
            self._log_event('card_nsfw_detection_result', {'reason': reason_label, 'isNsfw': flag, 'preview': str(text or '')[:600]})
            return flag
        except Exception as e:
            self._log_event('card_nsfw_detection_failed', {'reason': reason_label, 'error': str(e)})
            return None

    def _generate_card_rating(self, output, concept='', browser_description='', settings=None):
        """Rate saved card quality for Character Browser. Returns rating/reasoning or blanks on failure."""
        output = output or ''
        concept = concept or ''
        browser_description = browser_description or ''
        if not output.strip():
            return {"rating": "", "reasoning": "", "details": [], "isNsfw": None, "sourceHash": self._card_rating_source_hash(output, concept, browser_description), "source": "none"}
        merged = self._normalise_settings({**self.settings, **(settings or {})})
        source_hash = self._card_rating_source_hash(output, concept, browser_description)
        if not self._validate_text_api_settings(merged).get('ok'):
            return {"rating": "", "reasoning": "", "details": [], "isNsfw": None, "sourceHash": source_hash, "source": "none"}
        try:
            sections = self._parse_sections(output)
            compact = {
                "name": self._extract_name(output),
                "description": sections.get("description", "")[:2200],
                "personality": sections.get("personality", "")[:2600],
                "scenario": sections.get("scenario", "")[:2600],
                "first_message": sections.get("first_message", "")[:1800],
                "example_dialogues": sections.get("example_dialogues", "")[:1400],
                "tags": sections.get("tags", "")[:600],
                "concept": concept[:1800],
                "browser_description": browser_description[:900],
            }
            prompt = "\n".join([
                "Evaluate the craft quality of this fictional AI character card for roleplay use.",
                "Rate the CARD QUALITY out of 10. Do not rate morality, taste, genre, or whether the premise is wholesome; rate how usable and well-built the card is.",
                "Criteria: clear concept, consistent personality, playable scenario hook, relationship/dynamic with {{user}}, useful first message, formatting, specificity, and whether the card gives enough direction without being bloated.",
                "Return ONLY compact JSON with exactly these top-level keys: rating, reasoning, details, isNsfw.",
                "The details key is REQUIRED and must be a non-empty array. Do not rename it to scores, ratings, categories, breakdown, or elementRatings.",
                "Set isNsfw true if the card contains explicit sexual content, porn/adult-industry content, fetish/kink roleplay, nudity/explicit sexual imagery, or is clearly intended for adult/NSFW roleplay; otherwise false. Do not let NSFW status lower or raise the quality rating by itself.",
                "{\"rating\": number from 0 to 10, \"reasoning\": \"2-5 concise sentences explaining the overall score, strengths, and areas to improve.\", \"details\": [{\"name\": \"Concept Clarity\", \"rating\": number from 0 to 10, \"reason\": \"one short sentence\"}], \"isNsfw\": true/false}",
                "Include exactly these detail elements, in this order: " + ", ".join(self._card_rating_expected_detail_names()) + ".",
                "Do not use markdown. Do not include extra keys except optional strengths/improvements arrays.",
                "",
                "CARD DATA JSON:",
                json.dumps(compact, ensure_ascii=False, indent=2),
            ]).strip()
            check = self._context_check(prompt, merged, mode_label='Card rating')
            if not check.get('ok'):
                self._log_event('card_rating_skipped_context', {"error": check.get('error')})
                return {"rating": "", "reasoning": "", "details": [], "isNsfw": None, "sourceHash": source_hash, "source": "none"}
            local_settings = dict(merged)
            local_settings['maxOutputTokens'] = min(1400, int(local_settings.get('maxOutputTokens') or 1400))
            local_settings['temperature'] = min(0.35, float(local_settings.get('temperature', 0.35) or 0.35))
            text = self._chat_once(prompt, local_settings, (local_settings.get('aiSuggestionModel') or local_settings.get('model') or '').strip(), 'card_rating')
            if self._looks_like_text_refusal(text):
                return {"rating": "", "reasoning": "", "details": [], "isNsfw": None, "sourceHash": source_hash, "source": "none"}
            rating, reasoning, details = self._parse_card_rating_response(text)
            is_nsfw = self._parse_nsfw_flag_from_rating_text(text)
            if is_nsfw is None:
                is_nsfw = self._generate_card_nsfw_detection(output, concept, browser_description, merged, reason_label='primary_rating_missing_nsfw_flag')
            if not rating:
                self._log_event('card_rating_parse_failed', {"preview": str(text or '')[:1200]})
                return {"rating": "", "reasoning": "", "details": [], "isNsfw": None, "sourceHash": source_hash, "source": "none"}
            detail_source = "ai" if details else ""
            if not details:
                self._log_event('card_rating_details_missing', {"rating": rating, "preview": str(text or '')[:1200]})
                forced_details = self._generate_required_card_rating_details(
                    output, concept, browser_description, rating, reasoning, merged,
                    reason_label='primary_rating_response_missing_details'
                )
                forced_details = self._normalise_card_rating_details(forced_details)
                if forced_details:
                    details = forced_details
                    detail_source = "ai_required"
            details, ensured_source = self._ensure_card_rating_details(
                output, concept, browser_description, rating, reasoning, merged,
                existing_details=details, existing_source=detail_source
            )
            detail_source = ensured_source or detail_source or "none"
            self._log_event('card_rating_details_final', {"count": len(details or []), "rating": rating, "detailSource": detail_source, "isNsfw": is_nsfw})
            return {"rating": rating, "reasoning": reasoning, "details": details, "isNsfw": is_nsfw, "sourceHash": source_hash, "source": "ai", "detailSource": detail_source}
        except Exception as e:
            self._log_event('card_rating_generation_failed', {'error': str(e)})
            return {"rating": "", "reasoning": "", "details": [], "isNsfw": None, "sourceHash": source_hash, "source": "none"}



    def _section_display_name_for_diff(self, section_key, template=None):
        """Return a human-readable section title for rating-improvement diffs."""
        key = str(section_key or '').strip()
        if not key:
            return 'Unknown Section'
        tmpl = template if isinstance(template, dict) else (self.template or DEFAULT_TEMPLATE)
        try:
            for sec in tmpl.get('sections', []):
                if not isinstance(sec, dict):
                    continue
                title = str(sec.get('title') or '').strip()
                if not title:
                    continue
                canon = self._canonical_heading_with_template(title, tmpl) or self._canonical_heading(title)
                if canon == key:
                    return title
        except Exception:
            pass
        return key.replace('_', ' ').strip().title()

    def _card_improvement_field_diffs(self, original, revised, template=None):
        """Summarise which card sections changed between old and revised output."""
        try:
            tmpl = template if isinstance(template, dict) else (self.template or DEFAULT_TEMPLATE)
            old_sections = self._parse_sections(original or '', tmpl)
            new_sections = self._parse_sections(revised or '', tmpl)
            ordered_keys = []
            for sec in tmpl.get('sections', []):
                if not isinstance(sec, dict):
                    continue
                title = str(sec.get('title') or '').strip()
                if not title:
                    continue
                key = self._canonical_heading_with_template(title, tmpl) or self._canonical_heading(title)
                if key and key not in ordered_keys:
                    ordered_keys.append(key)
            for key in list(old_sections.keys()) + list(new_sections.keys()):
                if key and key not in ordered_keys:
                    ordered_keys.append(key)
            if not ordered_keys:
                ordered_keys = ['full_card']
                old_sections = {'full_card': str(original or '').strip()}
                new_sections = {'full_card': str(revised or '').strip()}
            diffs = []
            for key in ordered_keys:
                old = str(old_sections.get(key, '') or '').strip()
                new = str(new_sections.get(key, '') or '').strip()
                if not old and not new:
                    continue
                if old and new:
                    status = 'unchanged' if old == new else 'changed'
                elif old and not new:
                    status = 'removed'
                else:
                    status = 'added'
                diffs.append({
                    'name': self._section_display_name_for_diff(key, tmpl),
                    'key': key,
                    'status': status,
                    'oldLength': len(old),
                    'newLength': len(new),
                    'delta': len(new) - len(old),
                    'oldPreview': (old[:220].rsplit(' ', 1)[0].rstrip() + '…') if len(old) > 240 else old,
                    'newPreview': (new[:220].rsplit(' ', 1)[0].rstrip() + '…') if len(new) > 240 else new,
                })
            return diffs[:40]
        except Exception as e:
            self._log_event('card_rating_improvement_field_diff_failed', {'error': str(e)})
            return []

    def _parse_lost_detail_response(self, text):
        """Parse AI lost-detail audit into a compact list plus summary."""
        raw = re.sub(r'(?is)^```(?:json)?\s*|\s*```$', '', str(text or '')).strip()
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = None
        summary = ''
        items = []
        if isinstance(data, dict):
            summary = str(data.get('summary') or data.get('note') or '').strip()
            for key in ('possiblyRemovedDetails', 'possibleRemovedDetails', 'lostDetails', 'removedDetails', 'possibly_removed_details', 'details'):
                value = data.get(key)
                if isinstance(value, list):
                    items = [str(v).strip() for v in value if str(v).strip()]
                    break
                if isinstance(value, str) and value.strip():
                    items = [line.strip(' -•\t') for line in value.splitlines() if line.strip(' -•\t')]
                    break
        elif isinstance(data, list):
            items = [str(v).strip() for v in data if str(v).strip()]
        if not items:
            for line in raw.splitlines():
                cleaned = line.strip()
                cleaned = re.sub(r'^[-*•\d.)\s]+', '', cleaned).strip()
                if cleaned and not re.match(r'(?i)^(possibly removed details|lost details|summary)\s*[:：]?$', cleaned):
                    items.append(cleaned)
        clean_items = []
        seen = set()
        for item in items:
            item = re.sub(r'\s+', ' ', item).strip(' -•\t')
            if not item or item.lower() in {'none', 'nothing', 'no details removed', 'no obvious details removed'}:
                continue
            if len(item) > 220:
                item = item[:220].rsplit(' ', 1)[0].rstrip() + '…'
            key = item.lower()
            if key not in seen:
                seen.add(key)
                clean_items.append(item)
            if len(clean_items) >= 12:
                break
        if len(summary) > 420:
            summary = summary[:420].rsplit(' ', 1)[0].rstrip() + '…'
        return {'summary': summary, 'items': clean_items}

    def _generate_lost_detail_check(self, original, revised, concept='', settings=None):
        """Ask the AI to audit whether the improvement accidentally removed important facts."""
        try:
            original = str(original or '').strip()
            revised = str(revised or '').strip()
            if not original or not revised:
                return {'items': [], 'summary': '', 'source': 'none'}
            merged = self._normalise_settings({**self.settings, **(settings or {})})
            prompt = "\n".join([
                "Compare the ORIGINAL and REVISED fictional AI character cards.",
                "Your job is NOT to judge writing quality. Only identify important facts, constraints, or roleplay hooks that may have been removed, weakened, contradicted, or changed in the revised card.",
                "Be conservative: list only details a human reviewer should double-check.",
                "Return JSON only in this shape:",
                "{\"summary\": \"one short sentence\", \"possiblyRemovedDetails\": [\"detail 1\", \"detail 2\"]}",
                "If nothing obvious was lost, return an empty array.",
                "Important facts include names, ages, relationships, setting, backstory, jobs, kinks, boundaries, roleplay premise, first-meeting setup, and recurring character-specific details.",
                "",
                "ORIGINAL MAIN CONCEPT",
                str(concept or '').strip() or "(No concept supplied.)",
                "",
                "ORIGINAL CARD",
                original,
                "",
                "REVISED CARD",
                revised,
            ]).strip()
            check = self._context_check(prompt, merged, mode_label='Card improvement lost-detail check')
            if not check.get('ok'):
                return {'items': [], 'summary': 'Lost-detail check skipped: ' + str(check.get('error') or 'context too large'), 'source': 'skipped'}
            local_settings = dict(merged)
            local_settings['streamAi'] = False
            local_settings['_streamTarget'] = ''
            model = (local_settings.get('aiSuggestionModel') or local_settings.get('model') or '').strip()
            text = self._chat_once(prompt, local_settings, model, 'card_improvement_lost_detail_check')
            parsed = self._parse_lost_detail_response(text)
            parsed['source'] = 'ai'
            return parsed
        except Exception as e:
            self._log_event('card_rating_improvement_lost_detail_failed', {'error': str(e)})
            return {'items': [], 'summary': f'Lost-detail check failed: {e}', 'source': 'error'}

    def generate_card_improvement_from_rating(self, project_path, settings=None):
        """Generate a preview revision that applies the saved AI rating suggestions."""
        try:
            path = Path(project_path)
            if not path.exists():
                return {"ok": False, "error": "Character project not found."}
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid character project."}
            output = str(project.get("output") or "").strip()
            concept = str(project.get("concept") or "").strip()
            rating = str(project.get("cardRating") or "").strip()
            reasoning = str(project.get("cardRatingReasoning") or "").strip()
            if not output:
                return {"ok": False, "error": "This project has no generated card text to improve."}
            if not reasoning:
                return {"ok": False, "error": "Generate an AI Card Rating first so the model has improvement notes to apply."}

            active_settings = self._normalise_settings({**self.settings, **(settings or project.get("settings") or {})})
            settings_check = self._validate_text_api_settings(active_settings)
            if not settings_check.get("ok"):
                return settings_check
            template = project.get("template") or self.template
            if not isinstance(template, dict):
                template = self.template
            sections = [str(sec.get("title") or "").strip() for sec in template.get("sections", []) if isinstance(sec, dict) and sec.get("enabled", True) and str(sec.get("title") or "").strip()]
            name = self._extract_name(output) or project.get("name") or "the character"
            prompt = "\n".join([
                "Revise this fictional AI character card by applying the improvement suggestions from its AI Card Rating.",
                "Return the COMPLETE revised character card only, not a diff, not commentary, and not markdown fences.",
                "Do not add a wrapper title such as '# Revised Character Card'.",
                "Use the existing/plain section headings only. Do not convert the card to Markdown # or ## headings.",
                "SAFETY / PRESERVATION RULES:",
                "- Do not remove or contradict existing facts.",
                "- Do not change names, ages, relationships, setting, backstory, kinks, boundaries, or roleplay premise unless the rating notes explicitly demand it.",
                "- Do not simplify the card by deleting specific details. Preserve unique hooks, jobs, locations, history, and first-meeting setup.",
                "- Improve wording, clarity, specificity, and roleplay usefulness while preserving the card's intent.",
                "Keep the same character name unless the current card is obviously missing/invalid.",
                "Preserve the premise, genre, relationship dynamic, and tone. Improve craft/usability; do not sanitize, moralize, or replace the user's chosen scenario.",
                "Focus on the rating feedback: make the concept clearer, deepen personality consistency, sharpen the scenario hook, improve {{user}} involvement, strengthen the first message, and clean formatting where needed.",
                "Keep the same section order and headings when possible.",
                f"Expected section order: {', '.join(sections) if sections else 'preserve the current card headings'}",
                f"Current character name: {name}",
                f"Current rating: {rating + '/10' if rating else 'not scored'}",
                "",
                "AI CARD RATING REASONING / IMPROVEMENT NOTES",
                reasoning,
                "",
                "ORIGINAL MAIN CONCEPT",
                concept or "(No original concept supplied.)",
                "",
                "CURRENT CHARACTER CARD",
                output,
            ]).strip()
            check = self._context_check(prompt, active_settings, mode_label="Card rating improvement")
            if not check.get("ok"):
                return check
            local_settings = dict(active_settings)
            # Preview generation should not stream into the main Output box.
            local_settings["streamAi"] = False
            local_settings["_streamTarget"] = ""
            revised = self._ensure_image_prompt_sections(self._clean_generated_output(self._chat(prompt, local_settings)), local_settings)
            if not revised or self._looks_like_text_refusal(revised):
                return {"ok": False, "error": "The model did not return a usable revised card."}
            validation = self.validate_output_against_template(revised, template, active_settings)
            field_diffs = self._card_improvement_field_diffs(output, revised, template)
            lost_check = self._generate_lost_detail_check(output, revised, concept, active_settings)
            self._log_event("card_rating_improvement_preview", {
                "project": str(path),
                "rating": rating,
                "validation": validation,
                "changedFields": len([d for d in field_diffs if d.get('status') != 'unchanged']),
                "lostDetailCount": len(lost_check.get('items') or [])
            })
            return {
                "ok": True,
                "projectPath": str(path),
                "name": str(project.get("name") or name),
                "rating": rating,
                "reasoning": reasoning,
                "output": revised,
                "validation": validation,
                "fieldDiffs": field_diffs,
                "lostDetails": lost_check.get('items') or [],
                "lostDetailSummary": lost_check.get('summary') or '',
                "lostDetailSource": lost_check.get('source') or '',
            }
        except Exception as e:
            self._log_event("card_rating_improvement_failed", {"project": str(canonical_project_path), "error": str(e)})
            return {"ok": False, "error": f"Could not generate card improvement preview: {e}"}

    # CamelCase aliases for PyWebView/AppImage builds that sometimes expose or
    # cache method tables differently from the browser JavaScript context.
    def generateCardImprovementFromRating(self, project_path, settings=None):
        return self.generate_card_improvement_from_rating(project_path, settings)

    def improveCardFromRating(self, project_path, settings=None):
        return self.generate_card_improvement_from_rating(project_path, settings)

    def applyCardImprovementPreview(self, project_path, revised_output, settings=None):
        return self.apply_card_improvement_preview(project_path, revised_output, settings)

    def commitCardImprovementPreview(self, project_path, revised_output, settings=None):
        return self.apply_card_improvement_preview(project_path, revised_output, settings)

    def _strip_volatile_image_settings(self, settings_obj):
        """Remove current-editor image fields from settings before saving a different saved card.

        The global Settings object often contains the most recently generated/selected
        image.  When committing an AI Rating improvement for an older saved card,
        those volatile fields must not override the card's own saved image.
        """
        out = dict(settings_obj or {}) if isinstance(settings_obj, dict) else {}
        for key in ("cardImagePath", "imagePath", "imageDataUrl", "cardImageDataUrl"):
            out.pop(key, None)
        return out

    def _project_saved_card_image_source(self, project, project_path=None, reason="project_saved_card_image"):
        """Resolve the original image belonging to a saved project, not the current editor image."""
        project = project if isinstance(project, dict) else {}
        workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
        settings_obj = project.get("settings") if isinstance(project.get("settings"), dict) else {}
        workspace_settings = workspace.get("settings") if isinstance(workspace.get("settings"), dict) else {}
        candidates = []

        def add(value):
            if value is None:
                return
            value = str(value or "").strip()
            if value and value not in candidates:
                candidates.append(value)

        for obj in (project, workspace, settings_obj, workspace_settings):
            if not isinstance(obj, dict):
                continue
            for key in ("cardImagePath", "imagePath", "imageDataUrl", "cardImageDataUrl"):
                add(obj.get(key))

        # First preserve an explicit image field if it still exists or can be materialized.
        for candidate in candidates:
            local = self._ensure_local_card_image_path(candidate, "card", reason)
            if local:
                self._log_event("card_rating_improvement_image_preserved", {"method": "explicit_project_image", "path": local, "project": str(project_path or "")})
                return local

        # Then use the saved project's own asset DB / JSON / legacy card PNG fallbacks.
        if project_path:
            selected = candidates[0] if candidates else ""
            local = self._resolve_front_porch_export_image(selected, project_path=project_path, loaded_project=project, reason=reason)
            if local:
                self._log_event("card_rating_improvement_image_preserved", {"method": "project_asset_or_legacy", "path": local, "project": str(project_path)})
                return local

        self._log_event("card_rating_improvement_image_missing", {"project": str(project_path or ""), "candidateCount": len(candidates)})
        return candidates[0] if candidates else ""

    def apply_card_improvement_preview(self, project_path, revised_output, settings=None):
        """Commit a previewed AI rating improvement back into the saved character project."""
        try:
            path = Path(project_path)
            if not path.exists():
                return {"ok": False, "error": "Character project not found."}
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid character project."}
            revised_output = str(revised_output or "").strip()
            if not revised_output:
                return {"ok": False, "error": "The preview is empty. Nothing was committed."}
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            workspace = dict(workspace)

            # Preserve the saved card's own image before merging any live editor settings.
            # Otherwise the current Settings cardImagePath can overwrite an older card with
            # the last generated image from another workspace.
            image_path = self._project_saved_card_image_source(project, path, "card_rating_improvement_commit")

            project_settings = project.get("settings") if isinstance(project.get("settings"), dict) else {}
            incoming_settings = self._strip_volatile_image_settings(settings or {})
            merged_settings = {**project_settings, **incoming_settings}
            if image_path:
                merged_settings["cardImagePath"] = image_path

            workspace["output"] = revised_output
            workspace["concept"] = project.get("concept") or workspace.get("concept") or ""
            workspace["template"] = project.get("template") or workspace.get("template") or self.template
            workspace["settings"] = merged_settings
            workspace["builderState"] = project.get("builderState") or workspace.get("builderState") or {}
            workspace["qnaAnswers"] = project.get("qnaAnswers") or workspace.get("qnaAnswers") or ""
            workspace["emotionImages"] = project.get("emotionImages") or workspace.get("emotionImages") or []
            workspace["generatedImages"] = project.get("generatedImages") or workspace.get("generatedImages") or []
            workspace["characterTabs"] = project.get("characterTabs") or workspace.get("characterTabs") or []
            workspace["emotionManifest"] = project.get("emotionManifest") or workspace.get("emotionManifest") or ""
            workspace["visionDescription"] = project.get("visionDescription") or workspace.get("visionDescription") or ""
            workspace["conceptAttachments"] = project.get("conceptAttachments") or workspace.get("conceptAttachments") or []
            workspace["virtualFolderId"] = str(project.get("virtualFolderId") or workspace.get("virtualFolderId") or "")
            workspace["cardImagePath"] = image_path
            workspace["imagePath"] = image_path
            workspace["_disableSettingsCardImageFallback"] = True
            # Force fresh description/rating for the revised card instead of carrying stale scores forward.
            workspace["browserDescription"] = ""
            workspace["browserDescriptionSource"] = ""
            workspace["cardRating"] = ""
            workspace["cardRatingReasoning"] = ""
            workspace["cardRatingDetails"] = []
            workspace["cardRatingSourceHash"] = ""
            result = self.save_character_workspace(workspace)
            if result.get("ok"):
                self._log_event("card_rating_improvement_committed", {"oldProject": str(path), "newProject": result.get("projectPath"), "preservedImage": image_path})
            return result
        except Exception as e:
            self._log_event("card_rating_improvement_commit_failed", {"project": str(canonical_project_path), "error": str(e)})
            return {"ok": False, "error": f"Could not commit improved card: {e}"}

    def _clean_character_tag(self, value):
        tag = str(value or "").strip().strip(",;|/\\").strip().strip('"\'`“”‘’')
        tag = re.sub(r"^[-•*]+\s*", "", tag).strip()
        tag = re.sub(r"\s+", " ", tag)
        if not tag:
            return ""
        low = tag.lower()
        instruction_bits = [
            "lowercase", "hyphen-separated", "hyphen seperated", "hyphen-seperated", "maximum", "naximum",
            "max ", "minimum", "tags only", "comma-separated", "comma separated", "8-12", "8 to 12",
            "include ", "do not ", "return ", "format", "tag list", "number of tags",
        ]
        if any(bit in low for bit in instruction_bits):
            return ""
        if re.search(r"\b(?:tags?|maximum|max|minimum|min)\b", low) and re.search(r"\d", low):
            return ""
        if len(tag) > 48 or tag.count(" ") >= 5 or any(ch in tag for ch in "{}[]<>#"):
            return ""
        tag = tag.replace("_", "-")
        tag = re.sub(r"\s+", "-", tag.strip().lower())
        tag = re.sub(r"[^a-z0-9+.-]+", "-", tag)
        tag = re.sub(r"-{2,}", "-", tag).strip("-.")
        if not tag or len(tag) > 48:
            return ""
        if tag in {"tag", "tags", "none", "n-a", "na", "naximum-15", "maximum-15"}:
            return ""
        return tag

    def _clean_character_tags(self, tags):
        cleaned = []
        seen = set()
        for raw in tags or []:
            tag = self._clean_character_tag(raw)
            key = self._normalise_tag_key(tag)
            if tag and key not in seen:
                seen.add(key)
                cleaned.append(tag)
        return cleaned[:30]

    def _nsfw_tags_from_settings(self, settings=None):
        """Return the editable list of tags that should mark a card as NSFW.

        The visible default is "NSFW", but stored card tags are normalized by
        _clean_character_tag, so matching is case-insensitive and normally becomes
        the lower-case tag "nsfw" in card data.
        """
        try:
            merged = settings if isinstance(settings, dict) else self.settings
            raw = (merged or {}).get("nsfwTags", DEFAULT_SETTINGS.get("nsfwTags", "NSFW"))
            if isinstance(raw, list):
                pieces = raw
            else:
                pieces = re.split(r"[,\n]+", str(raw or ""))
            tags = self._clean_character_tags(pieces)
            return tags or [self._clean_character_tag("NSFW") or "nsfw"]
        except Exception:
            return ["nsfw"]

    def _primary_nsfw_tag(self, settings=None):
        tags = self._nsfw_tags_from_settings(settings)
        return tags[0] if tags else "nsfw"

    def _tag_list_has_nsfw_marker(self, tags, settings=None):
        nsfw_keys = {self._normalise_tag_key(t) for t in self._nsfw_tags_from_settings(settings)}
        return any(self._normalise_tag_key(self._clean_character_tag(t)) in nsfw_keys for t in (tags or []))

    def _add_nsfw_tag_to_list(self, tags, settings=None):
        clean_tags = self._clean_character_tags(tags or [])
        if self._tag_list_has_nsfw_marker(clean_tags, settings):
            return clean_tags, False
        tag = self._primary_nsfw_tag(settings)
        if tag:
            clean_tags.append(tag)
            self._log_event("nsfw_tag_added", {"tag": tag})
            return self._clean_character_tags(clean_tags), True
        return clean_tags, False

    def _extract_tags_from_output(self, output, template=None):
        try:
            parsed_tags = self._parse_sections(output or "", template or self.template).get("tags", "")
            if not parsed_tags:
                parsed_tags = self._section(output or "", "Tags")
            return self._clean_character_tags(re.split(r"[,\n]+", str(parsed_tags or "")))
        except Exception:
            return []

    def _replace_section_body(self, output, section_id, body_text, template=None, title_fallback=None):
        output = output or ""
        body_text = (body_text or "").strip()
        lines = output.splitlines()
        start = None
        end = None
        heading_line = None
        tmpl = template or self.template
        for i, line in enumerate(lines):
            try:
                heading = self._canonical_heading_with_template(line, tmpl)
            except Exception:
                heading = None
            if heading == section_id:
                start = i
                heading_line = lines[i]
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    try:
                        next_heading = self._canonical_heading_with_template(lines[j], tmpl)
                    except Exception:
                        next_heading = None
                    if next_heading:
                        end = j
                        break
                break
        if start is None:
            section_title = title_fallback or None
            if not section_title:
                for sec in (tmpl or {}).get("sections", []):
                    if str(sec.get("id") or "").strip() == str(section_id):
                        section_title = str(sec.get("title") or "").strip()
                        break
            section_title = section_title or str(section_id).replace("_", " ").title()
            suffix = f"{section_title}:\n{body_text}" if body_text else f"{section_title}:\n"
            return (output.rstrip() + "\n\n" + suffix).strip()
        replacement = [heading_line]
        if body_text:
            replacement.append(body_text)
        new_lines = lines[:start] + replacement + lines[end:]
        return "\n".join(new_lines).strip()

    def _replace_tags_section(self, output, tags, template=None):
        tag_text = ", ".join([str(t).strip() for t in (tags or []) if str(t).strip()])
        return self._replace_section_body(output, "tags", tag_text, template=template, title_fallback="Tags")

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
                    tag = self._clean_character_tag(raw)
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
                self._log_event("collect_library_tag_stats_error", {"project": str(canonical_project_path), "error": str(e)})
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
                new_tag = self._clean_character_tag(new)
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
                    self._log_event("rename_tags_project_failed", {"project": str(canonical_project_path), "error": str(e)})
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
            active_settings = settings or project.get("settings") or self.settings
            desc = self._generate_browser_description(output, concept, active_settings)
            source = "ai" if self._last_browser_description_source == "ai" else "extracted"
            # Always try to refresh the rating/details when the user explicitly presses
            # Regenerate AI Description. Older builds only rated when the description
            # source was AI; if the description fell back to extracted text, the response
            # could keep a stale overall score in the frontend while returning no details.
            existing_rating = str(project.get("cardRating") or "").strip()
            existing_reasoning = str(project.get("cardRatingReasoning") or "").strip()
            existing_details = project.get("cardRatingDetails") if isinstance(project.get("cardRatingDetails"), list) else []
            rating_info = self._generate_card_rating(output, concept, desc, active_settings)
            rating = str(rating_info.get("rating") or existing_rating or "").strip()
            reasoning = str(rating_info.get("reasoning") or existing_reasoning or "").strip()
            details = rating_info.get("details") if isinstance(rating_info.get("details"), list) else []
            detail_source = str(rating_info.get("detailSource") or "").strip()
            if rating and not details:
                self._log_event("browser_description_rating_details_missing_post_rating", {"project": str(path), "rating": rating})
                forced_details = self._generate_required_card_rating_details(
                    output, concept, desc, rating, reasoning, active_settings,
                    reason_label='regenerate_browser_description_post_rating'
                )
                forced_details = self._normalise_card_rating_details(forced_details)
                if forced_details:
                    details = forced_details
                    detail_source = "ai_required_post_rating"
            if not details and existing_details:
                details = existing_details
                detail_source = detail_source or "existing"
            if rating:
                details, ensured_source = self._ensure_card_rating_details(
                    output, concept, desc, rating, reasoning, active_settings,
                    existing_details=details, existing_source=detail_source
                )
                detail_source = ensured_source or detail_source or "none"
            source_hash = rating_info.get("sourceHash") or self._card_rating_source_hash(output, concept, desc)
            nsfw_flag = rating_info.get("isNsfw", None)
            if nsfw_flag is None:
                nsfw_flag = self._generate_card_nsfw_detection(output, concept, desc, active_settings, reason_label='regenerate_browser_description_missing_nsfw_flag')
            nsfw_tag_added = False
            if nsfw_flag is True:
                current_tags = project.get("tags") if isinstance(project.get("tags"), list) else self._extract_tags_from_output(output, project.get("template") or self.template)
                new_tags, nsfw_tag_added = self._add_nsfw_tag_to_list(current_tags, active_settings)
                if nsfw_tag_added:
                    output = self._replace_tags_section(output, new_tags, project.get("template") or self.template)
                    project["output"] = output
                    project["tags"] = new_tags
                    source_hash = self._card_rating_source_hash(output, concept, desc)
                    try:
                        (path.parent / "latest_output.md").write_text(output, encoding="utf-8")
                    except Exception:
                        pass
            self._log_event("browser_description_rating_regenerated", {
                "project": str(path),
                "source": source,
                "rating": rating,
                "detailCount": len(details or []) if isinstance(details, list) else 0,
                "detailSource": detail_source,
                "hadExistingRating": bool(existing_rating),
                "isNsfw": nsfw_flag,
                "nsfwTagAdded": nsfw_tag_added,
            })
            project["browserDescription"] = desc
            project["browserDescriptionSourceHash"] = self._browser_description_source_hash(output, concept)
            project["browserDescriptionSource"] = source
            project["cardRating"] = rating
            project["cardRatingReasoning"] = reasoning
            project["cardRatingDetails"] = details if isinstance(details, list) else []
            project["cardRatingSourceHash"] = source_hash
            project["cardRatingDetailSource"] = detail_source
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            workspace["output"] = project.get("output") or output
            if isinstance(project.get("tags"), list):
                workspace["tags"] = project.get("tags")
            workspace["browserDescription"] = desc
            workspace["browserDescriptionSource"] = source
            workspace["cardRating"] = project["cardRating"]
            workspace["cardRatingReasoning"] = project["cardRatingReasoning"]
            workspace["cardRatingDetails"] = project["cardRatingDetails"]
            workspace["cardRatingSourceHash"] = project["cardRatingSourceHash"]
            workspace["cardRatingDetailSource"] = detail_source
            project["workspace"] = workspace
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                self._refresh_library_cache_for_project(path, force=True)
            except Exception:
                pass
            details = project.get("cardRatingDetails") if isinstance(project.get("cardRatingDetails"), list) else []
            rating = project.get("cardRating") or ""
            reasoning = project.get("cardRatingReasoning") or ""
            source_hash = project.get("cardRatingSourceHash") or ""
            return {
                "ok": True,
                "success": True,
                "browserDescription": desc,
                "browserDescriptionSource": source,
                "cardRating": rating,
                "cardRatingReasoning": reasoning,
                "cardRatingDetails": details,
                "cardRatingSourceHash": source_hash,
                "cardRatingDetailSource": detail_source,
                # Alias keys keep older/newer frontend handlers from silently dropping the breakdown.
                "rating": rating,
                "reasoning": reasoning,
                "details": details,
                "detailSource": detail_source,
                "sourceHash": source_hash,
                "source_hash": source_hash,
                "projectPath": str(path),
                "isNsfw": nsfw_flag,
                "nsfwTagAdded": nsfw_tag_added,
                "tags": project.get("tags") if isinstance(project.get("tags"), list) else [],
            }
        except Exception as e:
            self._log_event("regenerate_browser_description_failed", {"project": str(canonical_project_path), "error": str(e)})
            return {"ok": False, "error": f"Could not regenerate browser description: {e}"}

    def ensure_card_rating_details_for_project(self, project_path, settings=None):
        """Generate/save missing per-element rating details for an already-rated project.

        This is used as a repair path from the Details modal and after regenerating the
        browser description. It reads the saved project from disk, repairs missing details,
        writes them back to both project and workspace, and refreshes the browser cache.
        """
        try:
            path = Path(project_path)
            if not path.exists():
                return {"ok": False, "error": "Character project not found."}
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid character project."}
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            output = project.get("output") or workspace.get("output") or ""
            concept = project.get("concept") or workspace.get("concept") or ""
            browser_description = project.get("browserDescription") or workspace.get("browserDescription") or self._fallback_browser_description(output, concept)
            rating = str(project.get("cardRating") or workspace.get("cardRating") or "").strip()
            reasoning = str(project.get("cardRatingReasoning") or workspace.get("cardRatingReasoning") or "").strip()
            existing_details = project.get("cardRatingDetails") if isinstance(project.get("cardRatingDetails"), list) else (workspace.get("cardRatingDetails") if isinstance(workspace.get("cardRatingDetails"), list) else [])
            active_settings = settings or project.get("settings") or self.settings

            # If the project somehow has reasoning but no score, try a full rating pass first.
            detail_source = "existing" if existing_details else ""
            if not rating and output.strip():
                rating_info = self._generate_card_rating(output, concept, browser_description, active_settings)
                rating = str(rating_info.get("rating") or "").strip()
                reasoning = str(rating_info.get("reasoning") or reasoning or "").strip()
                existing_details = rating_info.get("details") if isinstance(rating_info.get("details"), list) else existing_details
                detail_source = str(rating_info.get("detailSource") or detail_source or "").strip()

            if rating and not existing_details:
                forced_details = self._generate_required_card_rating_details(
                    output, concept, browser_description, rating, reasoning, active_settings,
                    reason_label='details_modal_or_project_repair'
                )
                forced_details = self._normalise_card_rating_details(forced_details)
                if forced_details:
                    existing_details = forced_details
                    detail_source = "ai_required_project_repair"
            details, ensured_source = self._ensure_card_rating_details(
                output, concept, browser_description, rating, reasoning, active_settings,
                existing_details=existing_details, existing_source=detail_source
            )
            detail_source = ensured_source or detail_source or "none"

            source_hash = project.get("cardRatingSourceHash") or workspace.get("cardRatingSourceHash") or self._card_rating_source_hash(output, concept, browser_description)
            project["cardRating"] = rating
            project["cardRatingReasoning"] = reasoning
            project["cardRatingDetails"] = details
            project["cardRatingSourceHash"] = source_hash
            project["cardRatingDetailSource"] = detail_source
            workspace["cardRating"] = rating
            workspace["cardRatingReasoning"] = reasoning
            workspace["cardRatingDetails"] = details
            workspace["cardRatingSourceHash"] = source_hash
            workspace["cardRatingDetailSource"] = detail_source
            project["workspace"] = workspace
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                self._refresh_library_cache_for_project(path, force=True)
            except Exception:
                pass
            self._log_event("card_rating_details_project_ensured", {"project": str(path), "rating": rating, "detailCount": len(details or []), "detailSource": detail_source})
            return {
                "ok": True,
                "success": True,
                "cardRating": rating,
                "cardRatingReasoning": reasoning,
                "cardRatingDetails": details,
                "cardRatingSourceHash": source_hash,
                "cardRatingDetailSource": detail_source,
                "rating": rating,
                "reasoning": reasoning,
                "details": details,
                "detailSource": detail_source,
                "sourceHash": source_hash,
                "source_hash": source_hash,
                "projectPath": str(path),
            }
        except Exception as e:
            self._log_event("ensure_card_rating_details_failed", {"project": str(canonical_project_path), "error": str(e)})
            return {"ok": False, "error": f"Could not ensure card rating details: {e}"}

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

    def _unique_character_variant_name(self, base_name, suffix="Copy"):
        base = self._clean_character_name_value(base_name or "Character") or "Character"
        suffix = self._clean_character_name_value(suffix or "Copy") or "Copy"
        first = f"{base} {suffix}" if suffix.lower() not in base.lower() else base
        candidate = first.strip()
        n = 2
        while (EXPORT_DIR / self._safe_slug(candidate)).exists():
            candidate = f"{first} {n}".strip()
            n += 1
        return candidate

    def _variation_requested_name(self, instructions):
        try:
            text = str(instructions or "")
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key in {"variation name", "name", "new name", "card name"} and value:
                    cleaned = re.sub(r"\s+", " ", value).strip(" -")
                    if cleaned:
                        return cleaned[:120]
        except Exception:
            pass
        return ""

    def _variation_suffix_from_instructions(self, instructions):
        text = re.sub(r"\{\{user\}\}", "user", str(instructions or ""), flags=re.I)
        lower = text.lower()
        parts = []
        m = re.search(r"\b(\d+)\s+(year|years|month|months)\s+later\b", lower)
        if m:
            unit = "Year" if m.group(2).startswith("year") else "Month"
            parts.append(f"{m.group(1)} {unit}{'' if m.group(1) == '1' else 's'} Later")
        if "married" in lower or "wife" in lower or "husband" in lower:
            parts.append("Married Life")
        if "university" in lower or "college" in lower:
            parts.append("University")
        if "high school" in lower:
            parts.append("High School")
        if "future" in lower and not parts:
            parts.append("Future")
        if "corrupt" in lower:
            parts.append("Corrupted Route")
        if "after" in lower and not parts:
            parts.append("After Story")
        if parts:
            # Preserve order while deduping.
            seen = set()
            clean = []
            for part in parts:
                key = part.lower()
                if key not in seen:
                    seen.add(key)
                    clean.append(part)
            return " / ".join(clean)[:80]
        words = re.findall(r"[A-Za-z0-9]+", text)
        stop = {"make", "this", "card", "character", "variation", "set", "where", "when", "with", "from", "into", "using", "the", "and", "for", "new", "based", "years", "year", "later"}
        useful = [w.capitalize() for w in words if w.lower() not in stop][:4]
        return " ".join(useful)[:80] if useful else "Variation"

    def _replace_name_section_for_variant(self, output, new_name):
        text = str(output or "")
        name = self._clean_character_name_value(new_name or "")
        if not text.strip() or not name:
            return text
        try:
            return self._replace_section_body(text, "name", name, self.template, "Name")
        except Exception:
            pass
        # Fallback for cards with simple heading formatting.
        pattern = re.compile(r"(?is)(^|\n)(\s*Name\s*\n+)(.*?)(?=\n\s*-{3,}\s*\n|\n\s*(?:Description|Personality|Scenario|First Message)\s*\n|$)")
        if pattern.search(text):
            return pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{name}\n", text, count=1)
        return f"Name\n\n{name}\n\n------------------------------------------------\n" + text.lstrip()

    def _replace_path_strings_recursive(self, value, old_root, new_root):
        old = str(old_root or "")
        new = str(new_root or "")
        if isinstance(value, dict):
            return {k: self._replace_path_strings_recursive(v, old, new) for k, v in value.items()}
        if isinstance(value, list):
            return [self._replace_path_strings_recursive(v, old, new) for v in value]
        if isinstance(value, str) and old and old in value:
            return value.replace(old, new)
        return value

    def _clear_project_identity_recursive(self, value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k in {"projectPath", "workspaceProjectPath"}:
                    out[k] = ""
                else:
                    out[k] = self._clear_project_identity_recursive(v)
            return out
        if isinstance(value, list):
            return [self._clear_project_identity_recursive(v) for v in value]
        return value

    def duplicate_character_project(self, project_path):
        """Create an editable duplicate project and make the browser able to group it.

        The content is copied from the original, with only the card/project identity
        made unique so later saves do not overwrite the source card.
        """
        try:
            src_project = self._project_path_inside_exports(project_path)
            src_folder = src_project.parent
            payload = json.loads(src_project.read_text(encoding="utf-8"))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            if not isinstance(project, dict):
                return {"ok": False, "error": "Invalid source character project."}
            original_name = project.get("name") or self._extract_name(project.get("output") or "") or src_folder.name
            duplicate_name = self._unique_character_variant_name(original_name, "Copy")
            dest_folder = EXPORT_DIR / self._safe_slug(duplicate_name)
            shutil.copytree(src_folder, dest_folder)
            dest_project = dest_folder / "latest_ccf_project.json"
            # Work from the copied latest file when available so sidecars and snapshots stay together.
            if dest_project.exists():
                payload = json.loads(dest_project.read_text(encoding="utf-8"))
            payload = self._replace_path_strings_recursive(payload, str(src_folder), str(dest_folder))
            project = payload.get("project", payload) if isinstance(payload, dict) else {}
            workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
            output = str(project.get("output") or workspace.get("output") or "")
            output = self._replace_name_section_for_variant(output, duplicate_name)
            project["name"] = duplicate_name
            project["output"] = output
            project["projectPath"] = str(dest_project)
            project["saved_at"] = time.strftime("%Y%m%d-%H%M%S")
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            workspace["name"] = duplicate_name
            workspace["output"] = output
            workspace["projectPath"] = str(dest_project)
            workspace["workspaceProjectPath"] = str(dest_project)
            for tab in workspace.get("characterTabs") if isinstance(workspace.get("characterTabs"), list) else []:
                if isinstance(tab, dict):
                    tab["name"] = duplicate_name
                    tab["focusName"] = duplicate_name
                    tab["output"] = output
                    tab["fullTextOutput"] = output
                    tab["projectPath"] = str(dest_project)
                    tab["workspaceProjectPath"] = str(dest_project)
            project["workspace"] = workspace
            if isinstance(payload, dict) and payload.get("project") is not None:
                payload["project"] = project
                payload["version"] = self.get_app_version()
                payload["saved_at"] = time.strftime("%Y%m%d-%H%M%S")
            else:
                payload = project
            image_path = project.get("imagePath") or project.get("cardImagePath") or workspace.get("cardImagePath") or workspace.get("imagePath") or ""
            latest_card = dest_folder / f"{self._safe_slug(duplicate_name)}_latest_cardv2.png"
            try:
                card_payload = self._to_chara_card_v2(output, duplicate_name)
                self._write_chara_png(latest_card, card_payload, image_path)
                project["exportedPath"] = str(latest_card)
                if isinstance(payload, dict) and payload.get("project") is not None:
                    payload["project"] = project
            except Exception as e:
                self._log_event("duplicate_project_card_refresh_failed", {"source": str(src_project), "dest": str(dest_project), "error": str(e)})
            try:
                (dest_folder / "latest_output.md").write_text(output, encoding="utf-8")
            except Exception:
                pass
            dest_project.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                self._refresh_library_cache_for_project(dest_project, force=True)
                vf = str(project.get("virtualFolderId") or workspace.get("virtualFolderId") or "").strip()
                if vf:
                    self._library_set_card_folder(dest_project, vf)
            except Exception as e:
                self._log_event("duplicate_project_library_refresh_failed", {"dest": str(dest_project), "error": str(e)})
            self._log_event("character_project_duplicated", {"source": str(src_project), "dest": str(dest_project), "name": duplicate_name})
            return {"ok": True, "name": duplicate_name, "projectPath": str(dest_project), "folder": str(dest_folder), "originalProjectPath": str(src_project)}
        except Exception as e:
            return {"ok": False, "error": f"Could not duplicate character project: {e}"}

    def _variation_followup_prompt(self, original_name, suggested_name, instructions):
        return "\n".join([
            "Create a NEW alternate/future variation of this fictional character card from the current card.",
            "Return the COMPLETE new card only, not a diff and not commentary.",
            "This must be a separate route/version of the same character, suitable to save as its own card.",
            "Preserve the character's core identity, voice, formatting, section order, and useful details unless the instructions require changing them.",
            "Update timeline, relationship status, scenario, first message, background, sexual traits, tags, and state tracking as needed for the requested variation.",
            f"Original card name: {original_name}",
            f"Use this concise variation name in the Name section unless the user explicitly requested a better one: {suggested_name}",
            "Do not mention that this is AI-generated.",
            "",
            "USER VARIATION INSTRUCTIONS",
            str(instructions or "").strip(),
        ]).strip()

    def create_card_variation_from_workspace(self, workspace, instructions, settings=None):
        try:
            workspace = workspace or {}
            instructions = str(instructions or "").strip()
            if not instructions:
                return {"ok": False, "error": "Enter variation instructions first."}
            output = str(workspace.get("output") or "").strip()
            if not output:
                return {"ok": False, "error": "No card output was supplied for the variation."}
            template = workspace.get("template") or self.template
            concept = workspace.get("concept") or ""
            merged_settings = self._normalise_settings({**self.settings, **(settings or workspace.get("settings") or {})})
            original_name = self._extract_name(output) or workspace.get("name") or "Character"
            explicit_name = self._variation_requested_name(instructions)
            if explicit_name:
                suggested_name = explicit_name
            else:
                suffix = self._variation_suffix_from_instructions(instructions)
                suggested_name = self._unique_character_variant_name(original_name, suffix)
            prompt = self._variation_followup_prompt(original_name, suggested_name, instructions)
            revised = self.revise_card(output, prompt, concept, template, merged_settings)
            if not revised.get("ok"):
                return revised
            new_output = str(revised.get("output") or "").strip()
            new_name = self._extract_name(new_output) or suggested_name
            if self._safe_slug(new_name).lower() == self._safe_slug(original_name).lower() or self._is_generic_character_name(new_name):
                new_name = suggested_name
                new_output = self._replace_name_section_for_variant(new_output, new_name)
            elif (EXPORT_DIR / self._safe_slug(new_name)).exists():
                unique_name = self._unique_character_variant_name(new_name, "Variation")
                new_name = unique_name
                new_output = self._replace_name_section_for_variant(new_output, new_name)
            variation_workspace = self._clear_project_identity_recursive(json.loads(json.dumps(workspace, ensure_ascii=False)))
            variation_workspace["name"] = new_name
            variation_workspace["output"] = new_output
            variation_workspace["browserDescription"] = ""
            variation_workspace["browserDescriptionSource"] = ""
            variation_workspace["cardRating"] = ""
            variation_workspace["cardRatingReasoning"] = ""
            variation_workspace["cardRatingDetails"] = []
            variation_workspace["cardRatingSourceHash"] = ""
            variation_workspace["template"] = template
            variation_workspace["settings"] = merged_settings
            tabs = variation_workspace.get("characterTabs") if isinstance(variation_workspace.get("characterTabs"), list) else []
            if tabs:
                for tab in tabs:
                    if isinstance(tab, dict):
                        tab["name"] = new_name
                        tab["focusName"] = new_name
                        tab["output"] = new_output
                        tab["fullTextOutput"] = new_output
            else:
                variation_workspace["characterTabs"] = [{"name": new_name, "focusName": new_name, "output": new_output, "fullTextOutput": new_output, "cardImagePath": variation_workspace.get("cardImagePath") or variation_workspace.get("imagePath") or ""}]
            saved = self.save_character_workspace(variation_workspace)
            if not saved.get("ok"):
                return saved
            saved["output"] = new_output
            saved["backupInfo"] = revised.get("backupInfo") or {}
            saved["originalName"] = original_name
            return saved
        except Exception as e:
            return {"ok": False, "error": f"Could not create card variation: {e}"}

    def create_card_variation_from_project(self, project_path, instructions, settings=None):
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            return loaded
        workspace = loaded.get("workspace") if isinstance(loaded.get("workspace"), dict) else {}
        merged = {**workspace, **loaded}
        # Do not let the new variation save back over the source project.
        merged = self._clear_project_identity_recursive(merged)
        return self.create_card_variation_from_workspace(merged, instructions, settings)

    def _workspace_group_payload(self, workspace):
        """Return a valid Front Porch Group Card payload from a workspace-like dict.

        Group Card browser projects have a human-readable preview in ``output``.
        That preview must never be treated as a normal Chara V2 card on autosave
        or export. The real portable data is the fpa_group payload.
        """
        if not isinstance(workspace, dict):
            return {}
        payload = workspace.get("groupPayload")
        if isinstance(payload, dict) and payload.get("spec") == "front_porch_group_card":
            return payload
        nested = workspace.get("workspace") if isinstance(workspace.get("workspace"), dict) else {}
        payload = nested.get("groupPayload") if isinstance(nested, dict) else None
        if isinstance(payload, dict) and payload.get("spec") == "front_porch_group_card":
            return payload
        json_path = str(workspace.get("groupJsonPath") or nested.get("groupJsonPath") or "").strip()
        if json_path and Path(json_path).exists():
            try:
                data = json.loads(Path(json_path).read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("spec") == "front_porch_group_card":
                    return data
            except Exception:
                pass
        return {}

    def _save_front_porch_group_workspace(self, workspace):
        """Autosave an opened Front Porch Group Card project without flattening it.

        Normal workspace autosave writes a latest *_cardv2.png from output text.
        For group cards, output is only a Forge preview, so this path preserves
        groupPayload and rewrites latest .group.png/.group.json instead.
        """
        workspace = workspace or {}
        payload = self._workspace_group_payload(workspace)
        if not payload or payload.get("spec") != "front_porch_group_card":
            return {"ok": False, "error": "This workspace is marked as a Group Card but is missing its Front Porch fpa_group payload."}
        name = str(payload.get("name") or workspace.get("name") or self._extract_name(workspace.get("output") or "") or "Group Card").strip() or "Group Card"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        project_path_raw = str(workspace.get("projectPath") or workspace.get("workspaceProjectPath") or "").strip()
        folder = None
        if project_path_raw:
            try:
                candidate = self._project_path_inside_exports(project_path_raw)
                if candidate and Path(candidate).exists():
                    folder = Path(candidate).parent
            except Exception:
                folder = None
        if folder is None:
            folder = self._character_export_dir(name)
        _safe_mkdir(folder)
        safe = self._safe_slug(name or "group_card") or "group_card"

        # Prefer the existing group image as cover, otherwise fall back to the
        # first raw member avatar. The embedded fpa_group payload is what matters.
        cover = str(workspace.get("groupCardPath") or workspace.get("cardImagePath") or workspace.get("imagePath") or "").strip()
        if not cover:
            raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else []
            if raw_members:
                try:
                    avatar_b64 = str((raw_members[0] or {}).get("avatar_base64") or "")
                    if avatar_b64:
                        tmp = Path(TEMP_DIR) / f"ccf_group_autosave_cover_{uuid.uuid4().hex}.png"
                        tmp.write_bytes(base64.b64decode(avatar_b64))
                        cover = str(tmp)
                except Exception:
                    cover = ""

        group_png = folder / f"{safe}_latest.group.png"
        group_json = folder / f"{safe}_latest.group.json"
        self._write_front_porch_group_png(group_png, payload, cover)
        group_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        output = str(workspace.get("output") or self._group_card_browser_output(payload, payload.get("raw_member_data") or [], workspace)).strip()
        (folder / "latest_output.md").write_text(output + "\n", encoding="utf-8")

        settings = self._normalise_settings(workspace.get("settings") or self.settings)
        member_paths = workspace.get("memberProjectPaths") if isinstance(workspace.get("memberProjectPaths"), list) else []
        group_profile = workspace.get("groupProfile") if isinstance(workspace.get("groupProfile"), dict) else {}
        virtual_folder_id = str(workspace.get("virtualFolderId") or "").strip()
        latest_project = folder / "latest_ccf_project.json"
        workspace_copy = dict(workspace)
        workspace_copy.update({
            "name": name,
            "output": output,
            "settings": settings,
            "cardImagePath": str(group_png),
            "imagePath": str(group_png),
            "groupCardPath": str(group_png),
            "groupJsonPath": str(group_json),
            "groupPayload": payload,
            "groupProfile": group_profile,
            "memberProjectPaths": member_paths,
            "isGroupCard": True,
            "groupCardMode": workspace.get("groupCardMode") or "insert",
            "projectPath": str(latest_project),
            "workspaceProjectPath": str(latest_project),
        })
        project = {
            "format": "character-card-forge-project",
            "version": self.get_app_version(),
            "saved_at": stamp,
            "project": {
                "name": name,
                "concept": str(workspace.get("concept") or ""),
                "output": output,
                "template": workspace.get("template") or self.template,
                "settings": settings,
                "imagePath": str(group_png),
                "cardImagePath": str(group_png),
                "exportedPath": str(group_png),
                "groupCardPath": str(group_png),
                "groupJsonPath": str(group_json),
                "groupPayload": payload,
                "groupProfile": group_profile,
                "memberProjectPaths": member_paths,
                "isGroupCard": True,
                "groupCardMode": workspace.get("groupCardMode") or "insert",
                "frontend": "front_porch_group",
                "exportFormat": "fpa_group_png",
                "browserDescription": str(workspace.get("browserDescription") or f"Front Porch group card with {len(payload.get('raw_member_data') or payload.get('members') or [])} members."),
                "browserDescriptionSource": str(workspace.get("browserDescriptionSource") or "generated"),
                "tags": ["group-card", "front-porch", "group-chat"],
                "virtualFolderId": virtual_folder_id,
                "characterTabs": workspace.get("characterTabs") if isinstance(workspace.get("characterTabs"), list) else [],
                "conceptTabs": workspace.get("conceptTabs") if isinstance(workspace.get("conceptTabs"), list) else [],
                "manualTabs": workspace.get("manualTabs") if isinstance(workspace.get("manualTabs"), list) else [],
                "activeConceptTabIndex": workspace.get("activeConceptTabIndex", 0),
                "activeManualGuideTabIndex": workspace.get("activeManualGuideTabIndex", 0),
                "workspace": workspace_copy,
            },
        }
        latest_project.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        snapshot = folder / f"{safe}_{stamp}_ccf_project.json"
        if not snapshot.exists():
            snapshot.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self._refresh_library_cache_for_project(latest_project, force=True)
            if virtual_folder_id:
                self._library_set_card_folder(latest_project, virtual_folder_id)
        except Exception as e:
            self._log_event("group_workspace_cache_refresh_failed", {"project": str(latest_project), "error": str(e)})
        self._log_event("front_porch_group_workspace_saved", {"name": name, "folder": str(folder), "project": str(latest_project)})
        return {"ok": True, "name": name, "folder": str(folder), "projectPath": str(latest_project), "cardPath": str(group_png), "groupCard": True}

    def save_character_workspace(self, workspace):
        """Autosave the complete editable workspace into exports/<Character Name>/.

        This is the project's new source-of-truth save. It keeps the generated card,
        concept, builders, Q&A answers, settings/template, selected card image, and
        emotion prompt/image references together so the Character Browser can restore
        the whole route later.
        """
        workspace = workspace or {}
        group_payload = self._workspace_group_payload(workspace)
        if group_payload:
            return self._save_front_porch_group_workspace(workspace)
        # v1.0.10-beta8 migration guard: some pre-Group-Card single-card workspaces
        # can carry stale isGroupCard/frontend/exportFormat fields after being loaded
        # through newer builds.  Do not let those stale flags hijack normal autosave
        # unless a real fpa_group payload exists.
        if workspace.get("isGroupCard"):
            self._log_event("stale_group_flag_ignored_on_workspace_save", {
                "name": str(workspace.get("name") or "")[:120],
                "projectPath": str(workspace.get("projectPath") or workspace.get("workspaceProjectPath") or "")[:500],
                "frontend": str(workspace.get("frontend") or "")[:80],
                "exportFormat": str(workspace.get("exportFormat") or "")[:80],
            })
            for stale_key in ("isGroupCard", "groupCardMode", "groupCardPath", "groupJsonPath", "groupPayload", "memberProjectPaths"):
                workspace.pop(stale_key, None)
            if str(workspace.get("frontend") or "").strip().lower() == "front_porch_group":
                workspace.pop("frontend", None)
            if str(workspace.get("exportFormat") or "").strip().lower() in {"fpa_group_png", "fpa_group_json", "group_png", "group_json"}:
                workspace.pop("exportFormat", None)
        output = workspace.get("output") or ""
        if not output.strip():
            return {"ok": False, "error": "Nothing to save yet. Generate or load a card first."}
        output_template = workspace.get("template") or self.template
        normalised_output = self._normalise_card_output_for_save(output, output_template)
        if normalised_output and normalised_output != output:
            self._log_event("workspace_output_normalised_on_save", {"changed": True, "name": str(workspace.get("name") or "")[:120]})
            output = normalised_output
            workspace["output"] = output
        extracted_name = self._extract_name(output) or "Character Card"
        workspace_name = workspace.get("name") or ""
        safe_name = extracted_name if self._is_generic_character_name(workspace_name) else self._clean_character_name_value(workspace_name)
        if self._is_generic_character_name(safe_name):
            safe_name = extracted_name
        stamp = time.strftime("%Y%m%d-%H%M%S")
        folder = self._character_export_dir(safe_name)
        settings = self._normalise_settings(workspace.get("settings") or self.settings)
        disable_settings_image_fallback = bool(workspace.get("_disableSettingsCardImageFallback") or workspace.get("_preserveExistingCardImage"))
        image_path = workspace.get("cardImagePath") or workspace.get("imagePath") or ("" if disable_settings_image_fallback else (settings.get("cardImagePath") or ""))
        original_image_path = str(image_path or "").strip()
        local_image_path = self._ensure_local_card_image_path(original_image_path, "card", "save_character_workspace") if original_image_path else ""
        if not local_image_path and not disable_settings_image_fallback:
            local_image_path = self._resolve_workspace_card_image_path(workspace, original_image_path, "save_character_workspace_generated_base64")
        elif not local_image_path and disable_settings_image_fallback and original_image_path:
            # Only try candidates that are directly tied to this saved workspace; do not
            # allow the live Settings cardImagePath to supply a different character image.
            stripped_workspace = dict(workspace)
            stripped_settings = self._strip_volatile_image_settings(stripped_workspace.get("settings") or {})
            stripped_workspace["settings"] = stripped_settings
            local_image_path = self._resolve_workspace_card_image_path(stripped_workspace, original_image_path, "save_character_workspace_preserve_image")
        if local_image_path:
            # Generated-image candidates are temporary. Once the user chooses one
            # as the card image, promote it into the durable card_images folder so
            # reload, browser thumbnail refresh, and export never depend on a stale
            # generated_images path.
            try:
                resolved_local = Path(local_image_path).expanduser().resolve()
                generated_root = GENERATED_IMAGES_DIR.resolve()
                if resolved_local == generated_root or generated_root in resolved_local.parents:
                    promoted = self._copy_image_from_path(resolved_local, "card")
                    if promoted.get("ok") and promoted.get("path"):
                        self._log_event("selected_generated_image_promoted_on_save", {"from": str(resolved_local), "to": promoted.get("path")})
                        local_image_path = str(promoted.get("path"))
            except Exception as e:
                self._log_event("selected_generated_image_promote_failed", {"path": str(local_image_path), "error": str(e)})
            image_path = local_image_path
            settings["cardImagePath"] = local_image_path
            workspace["cardImagePath"] = local_image_path
            workspace["imagePath"] = local_image_path
            tabs = workspace.get("characterTabs")
            if isinstance(tabs, list):
                for tab in tabs:
                    if isinstance(tab, dict) and (not tab.get("cardImagePath") or str(tab.get("cardImagePath") or "").strip() == original_image_path):
                        tab["cardImagePath"] = local_image_path
                        tab["imagePath"] = local_image_path
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
        card_rating_source_hash = self._card_rating_source_hash(output, concept, browser_description)
        previous_rating_hash = str(previous_project.get("cardRatingSourceHash") or "").strip()
        card_rating = str(workspace.get("cardRating") or "").strip()
        card_rating_reasoning = str(workspace.get("cardRatingReasoning") or "").strip()
        card_rating_details = workspace.get("cardRatingDetails") if isinstance(workspace.get("cardRatingDetails"), list) else []
        if (not card_rating) and previous_rating_hash == card_rating_source_hash:
            card_rating = str(previous_project.get("cardRating") or "").strip()
            card_rating_reasoning = str(previous_project.get("cardRatingReasoning") or "").strip()
            card_rating_details = previous_project.get("cardRatingDetails") if isinstance(previous_project.get("cardRatingDetails"), list) else []
        if card_rating and (not card_rating_details) and previous_rating_hash == card_rating_source_hash:
            previous_details = previous_project.get("cardRatingDetails") if isinstance(previous_project.get("cardRatingDetails"), list) else []
            if previous_details:
                card_rating_details = previous_details
        rating_info = {}
        if (not card_rating) and str(browser_description_source or "").lower() == "ai":
            rating_info = self._generate_card_rating(output, concept, browser_description, settings)
            card_rating = str(rating_info.get("rating") or "").strip()
            card_rating_reasoning = str(rating_info.get("reasoning") or "").strip()
            card_rating_details = rating_info.get("details") if isinstance(rating_info.get("details"), list) else []
            card_rating_source_hash = str(rating_info.get("sourceHash") or card_rating_source_hash).strip()
        card_rating_detail_source = str(workspace.get("cardRatingDetailSource") or previous_project.get("cardRatingDetailSource") or "").strip()
        if card_rating and not card_rating_details:
            forced_details = self._generate_required_card_rating_details(
                output, concept, browser_description, card_rating, card_rating_reasoning, settings,
                reason_label='save_workspace_missing_details'
            )
            forced_details = self._normalise_card_rating_details(forced_details)
            if forced_details:
                card_rating_details = forced_details
                card_rating_detail_source = "ai_required_save_workspace"
            card_rating_details, _detail_source = self._ensure_card_rating_details(
                output, concept, browser_description, card_rating, card_rating_reasoning, settings,
                existing_details=card_rating_details, existing_source=card_rating_detail_source
            )
            card_rating_detail_source = _detail_source or card_rating_detail_source or "none"
        ai_rating_nsfw_flag = rating_info.get("isNsfw", None) if isinstance(rating_info, dict) else None
        if ai_rating_nsfw_flag is True:
            current_tags = self._extract_tags_from_output(output, template)
            new_tags, added_nsfw = self._add_nsfw_tag_to_list(current_tags, settings)
            if added_nsfw:
                output = self._replace_tags_section(output, new_tags, template)
                workspace["output"] = output
                workspace["tags"] = new_tags
                card_rating_source_hash = self._card_rating_source_hash(output, concept, browser_description)
                self._log_event("save_workspace_nsfw_tag_added_from_ai_rating", {"tag": self._primary_nsfw_tag(settings), "name": safe_name})
        if card_rating or card_rating_reasoning or card_rating_details:
            workspace["cardRating"] = card_rating
            workspace["cardRatingReasoning"] = card_rating_reasoning
            workspace["cardRatingDetails"] = card_rating_details
            workspace["cardRatingSourceHash"] = card_rating_source_hash
            workspace["cardRatingDetailSource"] = card_rating_detail_source
        # Keep latest text files simple and inspectable.
        (folder / "latest_output.md").write_text(output, encoding="utf-8")
        if workspace.get("qnaAnswers"):
            (folder / "qna_answers.md").write_text(str(workspace.get("qnaAnswers") or ""), encoding="utf-8")
        if workspace.get("builderState"):
            (folder / "builder_state.json").write_text(json.dumps(workspace.get("builderState"), indent=2, ensure_ascii=False), encoding="utf-8")
        if workspace.get("emotionImages"):
            (folder / "emotion_images_state.json").write_text(json.dumps(workspace.get("emotionImages"), indent=2, ensure_ascii=False), encoding="utf-8")
        if workspace.get("generatedImages"):
            (folder / "generated_images_state.json").write_text(json.dumps(workspace.get("generatedImages"), indent=2, ensure_ascii=False), encoding="utf-8")

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
            "version": self.get_app_version(),
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
                "cardRating": card_rating,
                "cardRatingReasoning": card_rating_reasoning,
                "cardRatingDetails": card_rating_details,
                "cardRatingSourceHash": card_rating_source_hash,
                "cardRatingDetailSource": card_rating_detail_source,
                "tags": tags,
                "virtualFolderId": virtual_folder_id,
                "projectPath": str(latest_project),
                "exportedPath": str(latest_card) if str(latest_card) else "",
                "frontend": "front_porch",
                "exportFormat": "chara_v2_png",
                "builderState": workspace.get("builderState") or {},
                "qnaAnswers": workspace.get("qnaAnswers") or "",
                "emotionImages": workspace.get("emotionImages") or [],
                "generatedImages": workspace.get("generatedImages") or [],
                "characterTabs": workspace.get("characterTabs") or [],
                "conceptTabs": workspace.get("conceptTabs") or [],
                "manualTabs": workspace.get("manualTabs") or [],
                "activeConceptTabIndex": workspace.get("activeConceptTabIndex", 0),
                "activeManualGuideTabIndex": workspace.get("activeManualGuideTabIndex", 0),
                "emotionManifest": workspace.get("emotionManifest") or "",
                "visionDescription": workspace.get("visionDescription") or "",
                "conceptAttachments": workspace.get("conceptAttachments") or [],
                "workspace": workspace,
            }
        }
        latest_project.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self._save_workspace_assets_to_db(latest_project, workspace, image_path=image_path)
            # Once SQLite has the restore-critical assets, temp/cache folders can be cleaned.
            # Keep the selected card image path if it lives in one of these folders so immediate
            # export after save still works; older project files remain the fallback for old entries.
            self._cleanup_temp_workspace_dirs(keep_paths=[image_path])
        except Exception as e:
            self._log_event("workspace_asset_db_save_failed", {"project": str(latest_project), "error": str(e)})
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
        browser_card = None
        try:
            row = self._library_get_card_row(latest_project)
            if row:
                browser_card = self._browser_card_from_db_row(row)
        except Exception:
            browser_card = None
        self._log_event("character_workspace_saved", {"name": safe_name, "folder": str(folder), "project": str(latest_project)})
        return {"ok": True, "name": safe_name, "folder": str(folder), "projectPath": str(latest_project), "cardPath": str(latest_card) if str(latest_card) else "", "browserCard": browser_card}

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
        happens only when hashes changed or a card is new. Projects are refreshed in
        parallel so large libraries open faster.
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

        seen_paths = {str(p.resolve()) for p in project_files}
        max_workers = max(2, min(8, (os.cpu_count() or 4), len(project_files) or 1))
        future_map = {}
        if project_files:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ccf-browser") as executor:
                for index, project_path in enumerate(project_files):
                    future = executor.submit(self._refresh_library_cache_for_project, project_path, False)
                    future_map[future] = (index, project_path)
                ordered_cards = {}
                for future in as_completed(future_map):
                    index, project_path = future_map[future]
                    try:
                        card = future.result()
                        if card:
                            ordered_cards[index] = card
                    except Exception as e:
                        self._log_event("character_library_card_error", {"project": str(project_path), "error": str(e)})
                cards = [ordered_cards[i] for i in sorted(ordered_cards.keys())]

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
        started_at = time.time()
        try:
            # Do not refresh/re-index the Character Browser cache here. The Browser
            # card was already produced by list_character_library(), and doing hash /
            # thumbnail / token work again during "Load Workspace" can make the UI
            # sit on LOADING CHARACTER WORKSPACE for minutes on image-heavy cards.
            path = Path(project_path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            res = self._load_project_payload(payload)
            res["projectPath"] = str(path)

            # Older 1.0.6/1.0.7 workspace-tab saves could leave the visible project JSON
            # with Concept data but without the editor-facing fields. The sidecar files are
            # still written beside latest_ccf_project.json, so load them as a rescue source
            # before hydrating images from SQLite.
            folder = path.parent
            restored_from_sidecar = []
            if not str(res.get("output") or "").strip():
                for candidate in (folder / "latest_output.md", folder / "output.md"):
                    try:
                        if candidate.exists():
                            text = candidate.read_text(encoding="utf-8").strip()
                            if text:
                                res["output"] = text
                                restored_from_sidecar.append(candidate.name)
                                break
                    except Exception:
                        pass
            if not str(res.get("qnaAnswers") or res.get("qaAnswers") or "").strip():
                for candidate in (folder / "qna_answers.md", folder / "qa_answers.md"):
                    try:
                        if candidate.exists():
                            text = candidate.read_text(encoding="utf-8").strip()
                            if text:
                                res["qnaAnswers"] = text
                                res["qaAnswers"] = text
                                restored_from_sidecar.append(candidate.name)
                                break
                    except Exception:
                        pass
            if not res.get("emotionImages"):
                candidate = folder / "emotion_images_state.json"
                try:
                    if candidate.exists():
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        if isinstance(data, list):
                            res["emotionImages"] = data
                            restored_from_sidecar.append(candidate.name)
                except Exception:
                    pass
            if not res.get("generatedImages"):
                candidate = folder / "generated_images_state.json"
                try:
                    if candidate.exists():
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        if isinstance(data, list):
                            res["generatedImages"] = data
                            restored_from_sidecar.append(candidate.name)
                except Exception:
                    pass

            # Use the actual file the user selected as the authoritative asset key.
            # Older projects can contain a stale embedded projectPath, which meant
            # text loaded but card image / generated images / emotion images stayed empty.
            res = self._hydrate_workspace_from_db_assets(path, res)
            # After hydration the selected image may exist only as imageDataUrl in
            # workspace_assets, while the old cardImagePath points at a cleaned temp
            # file or a generated-image basename. Materialize it now so preview,
            # browser thumbnail refresh, and exports all use the same real file.
            resolved_image_path = ""
            raw_image_path = str(res.get("cardImagePath") or res.get("imagePath") or "").strip()
            if raw_image_path:
                resolved_image_path = self._ensure_local_card_image_path(raw_image_path, "card", "load_character_project_selected_image")
            if not resolved_image_path and res.get("imageDataUrl"):
                resolved_image_path = self._ensure_local_card_image_path(res.get("imageDataUrl"), "card", "load_character_project_image_data_url")
            if resolved_image_path:
                res["imagePath"] = resolved_image_path
                res["cardImagePath"] = resolved_image_path
                if isinstance(res.get("settings"), dict):
                    res["settings"]["cardImagePath"] = resolved_image_path
                workspace = res.get("workspace") if isinstance(res.get("workspace", {}), dict) else {}
                workspace["imagePath"] = resolved_image_path
                workspace["cardImagePath"] = resolved_image_path
                res["workspace"] = workspace
            # Final repair pass for projects saved while the image workflow was
            # broken. It can recover from workspace_assets, image data URLs,
            # generated-image basenames, or non-blank saved card PNGs.
            res = self._materialize_loaded_project_card_image(res, str(path), "load_character_project")
            res["projectPath"] = str(path)
            # Keep workspace loads light: selected image remains a real file path,
            # generated/emotion previews are lazy-loaded by the frontend.
            res = self._lighten_loaded_workspace_image_payloads(res, "load_character_project")

            # Always provide a single, fully hydrated tab for Character Browser loading.
            # This prevents the frontend from opening a tab shell with only Concept data.
            output = str(res.get("output") or "").strip()
            if output:
                tabs = res.get("characterTabs") if isinstance(res.get("characterTabs"), list) else []
                primary = next((t for t in tabs if isinstance(t, dict) and str(t.get("output") or t.get("fullTextOutput") or "").strip() == output), None)
                if primary is None:
                    primary = next((t for t in tabs if isinstance(t, dict) and str(t.get("output") or t.get("fullTextOutput") or "").strip()), None)
                tab = dict(primary or {})
                tab["name"] = tab.get("name") or tab.get("focusName") or res.get("name") or self._extract_name(output) or "Loaded Character"
                tab["focusName"] = tab.get("focusName") or tab.get("name")
                tab["output"] = output
                tab["fullTextOutput"] = output
                qa = str(res.get("qnaAnswers") or res.get("qaAnswers") or tab.get("qnaAnswers") or tab.get("qaAnswers") or "")
                tab["qnaAnswers"] = qa
                tab["qaAnswers"] = qa
                tab["emotionImages"] = res.get("emotionImages") if isinstance(res.get("emotionImages"), list) else (tab.get("emotionImages") if isinstance(tab.get("emotionImages"), list) else [])
                tab["generatedImages"] = res.get("generatedImages") if isinstance(res.get("generatedImages"), list) else (tab.get("generatedImages") if isinstance(tab.get("generatedImages"), list) else [])
                tab["cardImagePath"] = res.get("cardImagePath") or res.get("imagePath") or tab.get("cardImagePath") or tab.get("imagePath") or ""
                tab["imagePath"] = tab["cardImagePath"]
                tab["projectPath"] = str(path)
                tab["workspaceProjectPath"] = str(path)
                if self._loaded_project_is_group_card(res):
                    tab["isGroupCard"] = True
                    tab["frontend"] = "front_porch_group"
                    tab["exportFormat"] = "fpa_group_png"
                    tab["groupCardMode"] = res.get("groupCardMode") or ""
                    tab["groupCardPath"] = res.get("groupCardPath") or res.get("imagePath") or res.get("cardImagePath") or ""
                    tab["groupJsonPath"] = res.get("groupJsonPath") or ""
                    tab["groupPayload"] = res.get("groupPayload") if isinstance(res.get("groupPayload"), dict) else {}
                    tab["memberProjectPaths"] = res.get("memberProjectPaths") if isinstance(res.get("memberProjectPaths"), list) else []
                res["characterTabs"] = [tab]

            try:
                self._log_event("character_project_load_restore_summary", {
                    "project": str(path),
                    "hasOutput": bool(str(res.get("output") or "").strip()),
                    "qaLength": len(str(res.get("qnaAnswers") or res.get("qaAnswers") or "")),
                    "emotionCount": len(res.get("emotionImages") or []) if isinstance(res.get("emotionImages"), list) else 0,
                    "generatedCount": len(res.get("generatedImages") or []) if isinstance(res.get("generatedImages"), list) else 0,
                    "tabCount": len(res.get("characterTabs") or []) if isinstance(res.get("characterTabs"), list) else 0,
                    "sidecars": restored_from_sidecar,
                    "durationMs": int((time.time() - started_at) * 1000),
                })
            except Exception:
                pass
            return res
        except Exception as e:
            return {"ok": False, "error": f"Could not load character project: {e}"}

    def _loaded_project_is_group_card(self, loaded):
        if not isinstance(loaded, dict):
            return False
        payload = loaded.get("groupPayload") if isinstance(loaded.get("groupPayload"), dict) else {}
        if payload.get("spec") == "front_porch_group_card":
            return True
        export_format = str(loaded.get("exportFormat") or "").strip().lower()
        frontend = str(loaded.get("frontend") or "").strip().lower()
        group_path = str(loaded.get("groupCardPath") or loaded.get("groupJsonPath") or "").strip()
        # Be deliberately conservative. Some normal projects can carry stale
        # browser metadata after a group-card tab was open, so don't treat a bare
        # isGroupCard/groupCardPath truthy value as authoritative unless it is
        # also a real fpa_group export marker.
        return bool(
            export_format in {"fpa_group_png", "fpa_group_json", "group_png", "group_json"}
            or frontend == "front_porch_group"
            or re.search(r"\.group\.(png|json)$", group_path, re.I)
        )

    def _load_group_payload_for_project(self, loaded):
        payload = loaded.get("groupPayload") if isinstance(loaded.get("groupPayload"), dict) else {}
        if payload.get("spec") == "front_porch_group_card":
            return payload
        json_path = str(loaded.get("groupJsonPath") or "").strip()
        if json_path and Path(json_path).exists():
            try:
                data = json.loads(Path(json_path).read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return payload if isinstance(payload, dict) else {}

    def _export_group_card_project(self, loaded, project_path, export_format="chara_v2_png"):
        """Export a saved Front Porch Group Card project as .group.png/.group.json.

        Group-card Browser projects store a readable summary in output so they can
        be shown in CCF. That summary must never be converted to a normal Chara
        V2 card during Browser Export PNG/JSON; the real artifact is the fpa_group
        payload and its .group.png/.group.json files.
        """
        payload = self._load_group_payload_for_project(loaded)
        if not isinstance(payload, dict) or payload.get("spec") != "front_porch_group_card":
            return {"ok": False, "error": "This Group Card project is missing its Front Porch fpa_group payload."}
        member_paths = loaded.get("memberProjectPaths") if isinstance(loaded.get("memberProjectPaths"), list) else []
        payload = self._refresh_group_payload_member_avatars_from_projects(payload, member_paths)
        name = str(payload.get("name") or loaded.get("name") or "Group Card").strip() or "Group Card"
        safe = self._safe_slug(name)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        settings = self._normalise_settings({**self.settings, **(loaded.get("settings") or {})})
        export_root = str(settings.get("exportDestinationFolder") or "").strip()
        if export_root:
            export_folder = Path(export_root).expanduser().resolve()
            _safe_mkdir(export_folder)
            if not _path_is_writable_dir(export_folder):
                return {"ok": False, "error": "The selected export folder is not writable."}
        else:
            export_folder = Path(project_path).parent if project_path else self._character_export_dir(name)

        fmt = str(export_format or "chara_v2_png").strip().lower()
        if fmt in {"chara_v2_png", "png", "group_png", "fpa_group_png"}:
            path = export_folder / f"{safe}_{stamp}.group.png"
            source = str(loaded.get("groupCardPath") or loaded.get("imagePath") or loaded.get("cardImagePath") or "").strip()
            try:
                first_image = ""
                raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else []
                if raw_members:
                    try:
                        avatar_b64 = str((raw_members[0] or {}).get("avatar_base64") or "")
                        if avatar_b64:
                            tmp = Path(TEMP_DIR) / f"ccf_group_export_cover_{uuid.uuid4().hex}.png"
                            tmp.write_bytes(base64.b64decode(avatar_b64))
                            first_image = str(tmp)
                    except Exception:
                        first_image = ""
                if not first_image and source and Path(source).exists():
                    first_image = source
                self._write_front_porch_group_png(path, payload, first_image)
            except Exception as e:
                return {"ok": False, "error": f"Could not export Group Card PNG: {e}"}
        elif fmt in {"chara_v2_json", "frontend_json", "json", "group_json", "fpa_group_json"}:
            path = export_folder / f"{safe}_{stamp}.group.json"
            try:
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                return {"ok": False, "error": f"Could not export Group Card JSON: {e}"}
        else:
            path = export_folder / f"{safe}_{stamp}_group_summary.md"
            try:
                path.write_text(str(loaded.get("output") or self._group_card_browser_output(payload, payload.get("raw_member_data") or [])), encoding="utf-8")
            except Exception as e:
                return {"ok": False, "error": f"Could not export Group Card summary: {e}"}

        return {
            "ok": True,
            "path": str(path),
            "folder": str(export_folder),
            "projectPath": str(project_path or loaded.get("projectPath") or ""),
            "name": name,
            "groupCard": True,
            "exportFormat": "fpa_group_png" if path.suffix.lower() == ".png" else ("fpa_group_json" if path.suffix.lower() == ".json" else "markdown"),
        }

    def export_character_from_project(self, project_path, export_format="chara_v2_png"):
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            self._log_event("front_porch_project_export_load_failed", {"project": str(project_path), "error": loaded.get("error")})
            return loaded
        is_group_project = self._loaded_project_is_group_card(loaded)
        self._log_event("front_porch_project_export_start", {
            "project": str(project_path),
            "target": None,
            "isGroupProject": bool(is_group_project),
            "frontend": loaded.get("frontend"),
            "exportFormat": loaded.get("exportFormat"),
            "groupCardPath": loaded.get("groupCardPath"),
            "hasGroupPayload": isinstance(loaded.get("groupPayload"), dict) and loaded.get("groupPayload", {}).get("spec") == "front_porch_group_card",
        })
        if is_group_project:
            return self._export_group_card_project(loaded, project_path, export_format or "chara_v2_png")
        return self.export_card(
            loaded.get("output") or "",
            "front_porch",
            export_format or "chara_v2_png",
            loaded.get("imagePath") or loaded.get("imageDataUrl") or "",
            loaded.get("concept") or "",
            loaded.get("template") or self.template,
            loaded.get("settings") or self.settings,
        )


    def _group_card_member_from_project(self, project_path):
        """Build one high-fidelity Front Porch group-card member from a saved CCF project.

        Front Porch's post-v30 group-card contract uses raw_member_data as the
        fidelity source of truth. Each member needs a stable ID for export-time
        remapping plus a complete avatar PNG that already contains a Chara V2
        `chara` chunk.
        """
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            raise ValueError(loaded.get("error") or "Could not load character project.")
        output = str(loaded.get("output") or "").strip()
        if not output:
            raise ValueError("Saved project has no card output.")
        name = self._extract_name(output) or loaded.get("name") or "Character"
        payload = self._to_chara_card_v2(output, name)
        data = dict(payload.get("data") or {})
        data["name"] = name
        data.setdefault("character_book", {"entries": []})
        data.setdefault("world_names", [])
        data.setdefault("alternate_greetings", [])
        data.setdefault("tags", [])
        data.setdefault("extensions", {})

        stable_id = str(uuid.uuid4())

        image_source = loaded.get("imagePath") or loaded.get("cardImagePath") or loaded.get("imageDataUrl") or loaded.get("cardImageDataUrl") or ""
        canonical_project_path = str(project_path)
        # Use the same robust image resolver as direct Front Porch export so
        # group members do not fall back to blank grey avatars when a saved
        # project only has the image in workspace_assets or an older card PNG.
        local_image = self._resolve_front_porch_export_image(
            image_source,
            project_path=canonical_project_path,
            loaded_project=loaded,
            reason="group_card_member_avatar",
        )
        if not local_image:
            # Some workspaces only surface the restored image after hydration on
            # nested workspace/tab fields.  Search the loaded object itself as a
            # final pre-placeholder pass.
            for data_url in self._iter_image_data_urls_deep(loaded, limit=128):
                candidate = self._ensure_local_card_image_path(data_url, "card", "group_card_member_avatar_loaded_deep")
                if candidate and self._png_file_has_nonblank_visible_pixels(candidate):
                    local_image = candidate
                    self._log_event("group_card_member_avatar_resolved_loaded_deep", {"project": str(canonical_project_path), "name": name, "path": candidate})
                    break
        avatar_base64 = ""
        try:
            if local_image and Path(local_image).exists() and self._png_file_has_nonblank_visible_pixels(local_image):
                img = Image.open(local_image).convert("RGBA")
            else:
                # Last-chance recoveries for source projects whose saved image path
                # points at an expired temp file or an old flat placeholder.
                recovered = self._front_porch_project_image_from_library_cache(canonical_project_path, "group_card_member_avatar_library_cache") or self._front_porch_existing_card_png_from_project(canonical_project_path, "group_card_member_avatar_existing_png")
                if recovered and Path(recovered).exists() and self._png_file_has_nonblank_visible_pixels(recovered):
                    img = Image.open(recovered).convert("RGBA")
                    local_image = recovered
                else:
                    self._log_event("group_card_member_avatar_placeholder_used", {"project": str(canonical_project_path), "name": name, "resolvedImage": str(local_image or "")})
                    img = Image.new("RGBA", (512, 768), (24, 24, 32, 255))

            avatar_payload = {
                "spec": payload.get("spec") or "chara_card_v2",
                "spec_version": payload.get("spec_version") or "2.0",
                "data": data,
            }
            avatar_meta = PngInfo()
            avatar_json = json.dumps(avatar_payload, ensure_ascii=False)
            avatar_chara = base64.b64encode(avatar_json.encode("utf-8")).decode("ascii")
            avatar_text_chunks = {"chara": avatar_chara, "ccf_group_member_id": stable_id}
            for k, v in avatar_text_chunks.items():
                avatar_meta.add_text(k, v)
            buf = io.BytesIO()
            img.save(buf, format="PNG", pnginfo=avatar_meta)
            avatar_bytes = self._png_bytes_with_text_chunks(buf.getvalue(), avatar_text_chunks)
            avatar_base64 = base64.b64encode(avatar_bytes).decode("ascii")
        except Exception as e:
            self._log_event("group_card_avatar_encode_failed", {"project": str(canonical_project_path), "error": str(e)})

        data["avatar_base64"] = avatar_base64
        data["_original_stable_id"] = stable_id
        return {"projectPath": str(project_path), "name": name, "output": output, "stableId": stable_id, "data": data}

    def _group_card_realism_payloads(self, members):
        """Build Front Porch-style group realism seed payloads.

        A Front Porch-exported group card (post-v30/v33) uses a slightly mixed
        compatibility shape:
        - baseline_realism_state: JSON string containing a flat stableId -> state map.
        - default_member_realism_state: JSON string containing {"perChar": {...}}.
        - realism_state / extensions.realism_state: flat stableId -> state map.
        - extensions.default_member_realism_state: object containing {"perChar": {...}}.

        Keep this aligned with actual Front Porch group exports rather than the
        earlier draft-only all-in-one perChar state object.
        """
        clean = []
        for member in members or []:
            if isinstance(member, dict):
                data = member.get("data") if isinstance(member.get("data"), dict) else {}
                sid = str(member.get("stableId") or data.get("_original_stable_id") or "").strip()
                name = str(member.get("name") or data.get("name") or "Character").strip() or "Character"
            else:
                sid = ""
                name = str(member or "Character").strip() or "Character"
            if sid:
                clean.append((sid, name))

        baseline = {}
        per_char = {}
        for sid, name in clean:
            baseline[sid] = {
                "affection": 35,
                "trust": 40,
                "emotion": "neutral",
                "emotionIntensity": "mild",
                "timeOfDay": "morning",
                "dayCount": 1,
            }
            per_char[sid] = {
                "affection": 35,
                "trust": 40,
                "emotion": "neutral",
                "emotionIntensity": "mild",
                "timeOfDay": "morning",
                "dayCount": 1,
                "needs": {
                    "hunger": 70,
                    "thirst": 75,
                    "rest": 65,
                    "social": 60,
                    "hygiene": 80,
                    "bladder": 85,
                },
                "enjoysLowHygiene": False,
                "relationships": {},
            }
        default_state = {"perChar": per_char}
        return {
            "baseline": baseline,
            "default": default_state,
            "realism": copy.deepcopy(baseline),
        }

    def _group_card_default_realism_state(self, members):
        """Backward-compatible helper: return the default_member_realism_state object."""
        return self._group_card_realism_payloads(members).get("default", {"perChar": {}})

    def _group_card_ai_prompt(self, members, options):
        summaries = []
        for member in members:
            data = member.get("data") or {}
            book = data.get("character_book") if isinstance(data.get("character_book"), dict) else {}
            lore_entries = []
            for entry in book.get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                lore_entries.append({
                    "name": entry.get("name") or entry.get("key") or "",
                    "keys": entry.get("keys") or entry.get("key") or [],
                    "content": str(entry.get("content") or "")[:1000],
                })
                if len(lore_entries) >= 4:
                    break
            summaries.append({
                "name": data.get("name") or member.get("name"),
                "description": str(data.get("description") or "")[:2200],
                "personality": str(data.get("personality") or "")[:3600],
                "scenario": str(data.get("scenario") or "")[:1600],
                "first_mes": str(data.get("first_mes") or "")[:1600],
                "alternate_greetings": [str(x)[:900] for x in (data.get("alternate_greetings") or [])[:2]],
                "example_dialogue": str(data.get("mes_example") or "")[:1600],
                "lorebook_entries": lore_entries,
                "tags": data.get("tags") or [],
            })
        return "\n".join([
            "Create high-quality shared Front Porch group setup fields for these existing character cards.",
            "Return STRICT JSON only. No markdown. No comments outside JSON.",
            "Required JSON keys: name, group_overview, group_dynamic, member_roles, scenario, first_message, system_prompt, tags.",
            "member_roles must be an object whose keys are character names and whose values are concise role/dynamic notes.",
            "tags must be an array of short lowercase tags for Forge's preview only.",
            "Do not rewrite, merge, or flatten the individual member cards. Each member card remains separate in members[] and raw_member_data[].",
            "Do not create a fake Chara V2 character description/personality for the group itself. Front Porch group cards store shared scene fields at the group root and character fields on each member.",
            "group_overview is only a Forge preview note for the group premise. It is not a character description and must not describe the group as if it were one character.",
            "Your job is to write polished shared group fields: scenario, first message, group system prompt, relationship/dynamic notes, and optional preview overview.",
            "Avoid generic filler such as 'created by Character Card Forge', 'each character keeps their own personality', or bland member lists.",
            "Scenario should be the shared starting situation, not a copy-paste list of each member's solo scenario.",
            "First_message should be a strong group opening scene with multiple members present, clear body language, and at least one character speaking.",
            "System_prompt should give Front Porch strong group-running instructions: voice separation, attribution, turn handling, relationship dynamics, and what not to collapse.",
            "Preserve canon facts from the member cards. If user instructions conflict with source cards, preserve source-card facts unless the instruction is clearly a route/timeline framing.",
            "Use {{user}} exactly, never {user}.",
            "",
            "USER GROUP INSTRUCTIONS",
            str(options.get("aiInstructions") or "").strip() or "Create a polished, emotionally specific shared group setup for these characters.",
            "",
            "REQUESTED GROUP NAME",
            str(options.get("name") or "").strip() or "(AI may choose)",
            "",
            "MEMBER CARD SUMMARIES",
            json.dumps(summaries, ensure_ascii=False, indent=2),
        ]).strip()

    def _build_group_card_fields_direct(self, members, options):
        names = [m.get("name") or (m.get("data") or {}).get("name") or "Character" for m in members]
        group_name = str(options.get("name") or "").strip() or " & ".join(names)
        scenario = str(options.get("scenario") or "").strip()
        if not scenario:
            group_subject = (', '.join(names[:-1]) + (' and ' if len(names) > 1 else '') + names[-1]) if names else 'the group'
            parts = [f"{{{{user}}}} is with {group_subject} in a shared group-card scene. Each character keeps their own personality, memory, and role while reacting naturally to both {{{{user}}}} and the other members."]
            for member in members:
                data = member.get("data") or {}
                member_scenario = str(data.get("scenario") or "").strip()
                if member_scenario:
                    parts.append(f"{data.get('name') or member.get('name')}: {member_scenario}")
            notes = str(options.get("aiInstructions") or "").strip()
            if notes:
                parts.append(f"Group notes: {notes}")
            scenario = "\n\n".join(parts).strip()
        first_message = str(options.get("firstMessage") or "").strip()
        if not first_message:
            first_message = f"*{group_name} begins with {', '.join(names)} together with {{{{user}}}}. Each character carries their own history, mood, and desires into the scene, waiting for {{{{user}}}} to speak first.*"
        system_prompt = str(options.get("systemPrompt") or "").strip()
        if not system_prompt:
            system_prompt = "This is a Front Porch group card. Keep each member distinct, preserve their original card traits, and make sure dialogue/action attribution remains clear."
        group_overview_lines = [
            f"Shared Front Porch group setup for {', '.join(names)}.",
            "This is a Forge preview note only; the actual character descriptions and personalities remain on each member card.",
        ]
        tags = sorted({"group-card", "front-porch", "group-chat", *[str(t).strip().lower() for member in members for t in ((member.get("data") or {}).get("tags") or []) if str(t).strip()]})[:24]
        return {
            "name": group_name,
            "group_overview": "\n".join(group_overview_lines).strip(),
            "group_dynamic": "",
            "member_roles": {},
            "scenario": scenario,
            "first_message": first_message,
            "system_prompt": system_prompt,
            "tags": tags or ["group-card", "front-porch", "group-chat"],
        }

    def _clean_group_card_ai_tags(self, value):
        tags = []
        if isinstance(value, list):
            source = value
        elif isinstance(value, str):
            source = re.split(r"[,\n]", value)
        else:
            source = []
        seen = set()
        for raw in source:
            tag = re.sub(r"\s+", "-", str(raw or "").strip().lower())
            tag = re.sub(r"[^a-z0-9_\-]+", "", tag)
            if not tag or tag in seen:
                continue
            seen.add(tag)
            tags.append(tag[:40])
            if len(tags) >= 24:
                break
        return tags

    def _build_group_card_fields_ai(self, members, options, settings):
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        check = self._validate_text_api_settings(merged_settings)
        if not check.get("ok"):
            raise ValueError(check.get("error") or "AI settings are incomplete.")
        prompt = self._group_card_ai_prompt(members, options)
        ctx = self._context_check(prompt, merged_settings, mode_label="Group Card AI combine")
        if not ctx.get("ok"):
            raise ValueError(ctx.get("error") or "Group Card AI prompt exceeds context window.")
        # This is an internal JSON-only combine pass.  Do not stream it into
        # the visible Full Text Output box: during Concept → Group Card
        # generation the active tab is usually member 1, so streaming here can
        # overwrite/corrupt that member card with the group wrapper JSON.
        raw = self._chat(prompt, {**merged_settings, "_streamTarget": ""})
        data = self._loads_model_json(raw)
        if not isinstance(data, dict):
            raise ValueError("AI did not return a JSON object.")
        direct = self._build_group_card_fields_direct(members, options)
        member_roles = data.get("member_roles") or data.get("memberRoles") or {}
        if not isinstance(member_roles, dict):
            member_roles = {}
        clean_roles = {}
        for key, value in member_roles.items():
            name = str(key or "").strip()
            note = str(value or "").strip()
            if name and note:
                clean_roles[name[:120]] = note
        tags = self._clean_group_card_ai_tags(data.get("tags"))
        if not tags:
            tags = direct.get("tags") or ["group-card", "front-porch", "group-chat"]
        return {
            "name": str(data.get("name") or direct["name"]).strip()[:180] or direct["name"],
            "group_overview": str(data.get("group_overview") or data.get("groupOverview") or data.get("description") or direct.get("group_overview") or "").strip() or direct.get("group_overview", ""),
            "group_dynamic": str(data.get("group_dynamic") or data.get("groupDynamic") or "").strip(),
            "member_roles": clean_roles,
            "scenario": str(data.get("scenario") or direct["scenario"]).strip() or direct["scenario"],
            "first_message": str(data.get("first_message") or data.get("firstMessage") or direct["first_message"]).strip() or direct["first_message"],
            "system_prompt": str(data.get("system_prompt") or data.get("systemPrompt") or direct["system_prompt"]).strip() or direct["system_prompt"],
            "tags": tags,
        }

    def _refresh_group_payload_member_avatars_from_projects(self, payload, member_project_paths=None):
        """Repair group-member avatar_base64 values using source member projects.

        Existing beta builds could preserve a flat placeholder avatar because the
        payload already had *some* PNG bytes.  For Front Porch import/export we
        need actual visible member art, so always try to refresh from source
        projects when available and only keep the current avatar if it is real.
        """
        if not isinstance(payload, dict):
            return payload
        raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else []
        if not raw_members:
            return payload
        paths = [str(p or "").strip() for p in (member_project_paths or []) if str(p or "").strip()]
        if not paths:
            # Last-resort recovery for older group projects that lost their
            # memberProjectPaths: find saved CCF cards by member name in exports.
            try:
                name_to_project = {}
                for proj in EXPORT_DIR.glob("*/latest_ccf_project.json"):
                    try:
                        data = json.loads(proj.read_text(encoding="utf-8"))
                        pr = data.get("project", data) if isinstance(data, dict) else {}
                        if not isinstance(pr, dict) or self._loaded_project_is_group_card(pr):
                            continue
                        n = str(pr.get("name") or self._extract_name(pr.get("output") or "") or "").strip().lower()
                        if n and n not in name_to_project:
                            name_to_project[n] = str(proj)
                    except Exception:
                        continue
                for raw in raw_members:
                    n = str((raw or {}).get("name") or "").strip().lower()
                    paths.append(name_to_project.get(n, ""))
                paths = [p for p in paths if p]
            except Exception:
                paths = []
        updated = copy.deepcopy(payload)
        updated_raw = []
        changed = False
        for idx, raw in enumerate(raw_members):
            item = copy.deepcopy(raw if isinstance(raw, dict) else {})
            current_avatar = str(item.get("avatar_base64") or "")
            current_real = self._avatar_base64_has_nonblank_visible_pixels(current_avatar)
            fresh_avatar = ""
            if idx < len(paths):
                try:
                    fresh = self._group_card_member_from_project(self._project_path_inside_exports(paths[idx]))
                    fresh_data = fresh.get("data") if isinstance(fresh, dict) else {}
                    fresh_avatar = str((fresh_data or {}).get("avatar_base64") or "")
                    self._log_event("group_payload_avatar_refresh_attempt", {
                        "index": idx,
                        "member": item.get("name"),
                        "project": paths[idx],
                        "currentBytes": len(current_avatar),
                        "currentReal": bool(current_real),
                        "freshBytes": len(fresh_avatar),
                        "freshReal": bool(self._avatar_base64_has_nonblank_visible_pixels(fresh_avatar)),
                    })
                except Exception as e:
                    self._log_event("group_payload_avatar_refresh_failed", {"index": idx, "project": paths[idx] if idx < len(paths) else "", "error": str(e)})
            if fresh_avatar and self._avatar_base64_has_nonblank_visible_pixels(fresh_avatar):
                if fresh_avatar != current_avatar:
                    item["avatar_base64"] = fresh_avatar
                    changed = True
            elif not current_real:
                self._log_event("group_payload_avatar_still_placeholder", {"index": idx, "member": item.get("name"), "project": paths[idx] if idx < len(paths) else "", "currentBytes": len(current_avatar), "freshBytes": len(fresh_avatar)})
            updated_raw.append(item)
        if changed:
            updated["raw_member_data"] = updated_raw
            if isinstance(updated.get("members"), list):
                display_keys = [
                    "name", "description", "personality", "scenario", "first_mes",
                    "mes_example", "creator_notes", "system_prompt",
                    "post_history_instructions", "alternate_greetings", "tags",
                    "creator", "character_version", "character_book", "world_names", "extensions",
                ]
                display = []
                for raw in updated_raw:
                    minimal = {k: copy.deepcopy(raw.get(k)) for k in display_keys if isinstance(raw, dict) and k in raw}
                    if isinstance(minimal.get("extensions"), dict):
                        ext = dict(minimal["extensions"])
                        ext.pop("raw_card", None)
                        minimal["extensions"] = ext
                    display.append(minimal)
                updated["members"] = display
        return updated

    def _ensure_group_payload_avatar_chunks(self, payload, reason="group_payload_avatar_chunks"):
        """Return a copy of a Front Porch Group Card payload whose raw member avatars
        are complete PNGs with embedded Chara V2 metadata.

        This is separate from the direct-DB avatar writer because .group.png export
        and browser-project sidecars must also carry full-fidelity avatars in
        raw_member_data[].avatar_base64. Front Porch's importer treats that field as
        the source of truth for materialising private group member avatar files.
        """
        if not isinstance(payload, dict):
            return payload
        raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else []
        if not raw_members:
            return payload
        updated = copy.deepcopy(payload)
        updated_raw = []
        changed = False
        for idx, raw in enumerate(raw_members):
            item = copy.deepcopy(raw if isinstance(raw, dict) else {})
            avatar_b64 = str(item.get("avatar_base64") or "").strip()
            stable_id = str(item.get("_original_stable_id") or item.get("id") or item.get("name") or f"member_{idx+1}").strip()
            before_len = len(avatar_b64)
            before_keys = []
            after_keys = []
            ok = False
            try:
                png_bytes = base64.b64decode(avatar_b64) if avatar_b64 else b""
                if png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    # Full Chara V2 payload for this member. Do not include the
                    # transport-only avatar_base64 field inside the embedded chara.
                    embedded_data = copy.deepcopy(item)
                    embedded_data.pop("avatar_base64", None)
                    embedded_data.pop("_original_stable_id", None)
                    chara_payload = {"spec": "chara_card_v2", "spec_version": "2.0", "data": embedded_data}
                    chara_text = base64.b64encode(json.dumps(chara_payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
                    before_keys = self._png_text_chunk_keys_from_bytes(png_bytes)
                    text_chunks = {"chara": chara_text, "ccf_group_member_id": stable_id}
                    new_bytes = self._png_bytes_with_text_chunks(png_bytes, text_chunks)
                    after_keys = self._png_text_chunk_keys_from_bytes(new_bytes)
                    if new_bytes != png_bytes:
                        item["avatar_base64"] = base64.b64encode(new_bytes).decode("ascii")
                        changed = True
                    ok = "chara" in after_keys
            except Exception as e:
                self._log_event("group_payload_avatar_chunk_ensure_failed", {"reason": reason, "index": idx, "member": item.get("name"), "error": str(e), "beforeBytes": before_len})
            self._log_event("group_payload_avatar_chunk_ensure", {
                "reason": reason,
                "index": idx,
                "member": item.get("name"),
                "stableId": stable_id,
                "beforeBytes": before_len,
                "afterBytes": len(str(item.get("avatar_base64") or "")),
                "beforeKeys": before_keys[:20],
                "afterKeys": after_keys[:20],
                "hasChara": bool(ok),
                "real": bool(self._avatar_base64_has_nonblank_visible_pixels(str(item.get("avatar_base64") or ""))),
            })
            updated_raw.append(item)
        updated["raw_member_data"] = updated_raw
        if changed and isinstance(updated.get("members"), list):
            display_keys = [
                "name", "description", "personality", "scenario", "first_mes",
                "mes_example", "creator_notes", "system_prompt",
                "post_history_instructions", "alternate_greetings", "tags",
                "creator", "character_version", "character_book", "world_names", "extensions",
            ]
            display = []
            for raw in updated_raw:
                minimal = {k: copy.deepcopy(raw.get(k)) for k in display_keys if isinstance(raw, dict) and k in raw}
                if isinstance(minimal.get("extensions"), dict):
                    ext = dict(minimal["extensions"])
                    ext.pop("raw_card", None)
                    minimal["extensions"] = ext
                display.append(minimal)
            updated["members"] = display
        return updated

    def _png_text_chunk_keys_from_bytes(self, data):
        try:
            data = bytes(data or b"")
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                return []
            pos = 8
            keys = []
            while pos + 8 <= len(data):
                length = struct.unpack(">I", data[pos:pos+4])[0]
                ctype = data[pos+4:pos+8]
                chunk = data[pos+8:pos+8+length]
                pos += 12 + length
                if ctype in (b"tEXt", b"zTXt", b"iTXt") and b"\x00" in chunk:
                    keys.append(chunk.split(b"\x00", 1)[0].decode("utf-8", "replace"))
                if ctype == b"IEND":
                    break
            return keys[:40]
        except Exception:
            return []

    def _write_front_porch_group_png(self, path, payload, cover_image_path=""):
        payload = self._ensure_group_payload_avatar_chunks(payload, reason="write_front_porch_group_png")
        source = str(cover_image_path or "").strip()
        local_source = self._ensure_local_card_image_path(source, "card", "write_group_card_png") if source else ""
        if local_source and Path(local_source).exists():
            img = Image.open(local_source).convert("RGBA")
        else:
            img = Image.new("RGBA", (512, 768), (24, 24, 32, 255))
        metadata = PngInfo()
        # Front Porch group-card convention: private fpa_group text chunk whose
        # value is base64(UTF-8 JSON). Normal character-card tools ignore it.
        json_text = json.dumps(payload, ensure_ascii=False)
        text_chunks = {
            "fpa_group": base64.b64encode(json_text.encode("utf-8")).decode("ascii"),
            "ccf_group_summary": json.dumps({
                "name": payload.get("name"),
                "memberCount": len(payload.get("raw_member_data") or payload.get("members") or []),
                "createdBy": "Character Card Forge",
            }, ensure_ascii=True),
        }
        for k, v in text_chunks.items():
            metadata.add_text(k, v)
        img.save(path, "PNG", pnginfo=metadata)
        self._ensure_png_text_chunks(path, text_chunks, log_reason="write_front_porch_group_png")

    def _group_card_browser_output(self, payload, members, options=None):
        """Build a readable CCF preview for a Front Porch Group Card project.

        The portable data lives in the embedded fpa_group payload. The preview is
        not a fake Chara V2 root card: shared group fields appear first, then each
        member card is shown with its own character fields. This makes Full Text
        Output useful for inspection while keeping export routed through fpa_group.
        """
        options = options if isinstance(options, dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        name = str(payload.get("name") or "Group Card").strip() or "Group Card"

        ext = payload.get("extensions") if isinstance(payload.get("extensions"), dict) else {}
        ccf_ext = ext.get("character_card_forge") if isinstance(ext.get("character_card_forge"), dict) else {}
        profile = ccf_ext.get("group_profile") if isinstance(ccf_ext.get("group_profile"), dict) else {}
        if not profile and isinstance(options.get("groupProfile"), dict):
            profile = options.get("groupProfile")

        # Prefer high-fidelity raw_member_data for preview. Fall back to the
        # caller's member wrappers or the lighter members[] array.
        raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else []
        if not raw_members:
            for member in members or []:
                if isinstance(member, dict):
                    data = member.get("data") if isinstance(member.get("data"), dict) else member
                    if isinstance(data, dict):
                        raw_members.append(data)
        if not raw_members and isinstance(payload.get("members"), list):
            raw_members = [m for m in payload.get("members") or [] if isinstance(m, dict)]

        member_names = [str((m or {}).get("name") or "Character").strip() or "Character" for m in raw_members]
        member_list = "\n".join(f"- Member {idx}: {member_name}" for idx, member_name in enumerate(member_names, start=1))
        group_overview = str(profile.get("group_overview") or profile.get("description") or payload.get("description") or "").strip()
        if not group_overview:
            group_overview = "Member cards are preserved separately. This Forge preview shows the shared group setup followed by each embedded member card."

        lines = [
            "Name",
            "",
            name,
            "",
            "------------------------------------------------",
            "Members",
            "",
            member_list or "- No members found in preview metadata.",
            "",
            "------------------------------------------------",
            "Group Overview",
            "",
            group_overview,
        ]

        group_dynamic = str(profile.get("group_dynamic") or payload.get("group_dynamic") or payload.get("groupDynamic") or "").strip()
        if group_dynamic:
            lines.extend(["", "------------------------------------------------", "Group Dynamic", "", group_dynamic])

        member_roles = profile.get("member_roles") or payload.get("member_roles") or payload.get("memberRoles") or {}
        if isinstance(member_roles, dict) and member_roles:
            lines.extend(["", "------------------------------------------------", "Member Roles", ""])
            for role_name, role_text in member_roles.items():
                role_name = str(role_name or "Character").strip() or "Character"
                role_text = str(role_text or "").strip()
                if role_text:
                    lines.append(f"- {role_name}: {role_text}")

        lines.extend([
            "",
            "------------------------------------------------",
            "Group Scenario",
            "",
            str(payload.get("scenario") or "").strip() or "Shared group scenario is stored in the embedded Front Porch fpa_group data.",
            "",
            "------------------------------------------------",
            "Group First Message",
            "",
            str(payload.get("first_message") or "").strip() or "Shared group opening is stored in the embedded Front Porch fpa_group data.",
            "",
            "------------------------------------------------",
            "Group Settings",
            "",
            f"- Turn Order: {payload.get('turn_order') or 'roundRobin'}",
            f"- Auto Advance: {'Yes' if payload.get('auto_advance') else 'No'}",
            f"- Director Mode: {'Yes' if payload.get('director_mode') else 'No'}",
            f"- Member Count: {len(member_names)}",
        ])
        notes = str(options.get("groupInstructions") or options.get("aiInstructions") or "").strip()
        if notes:
            lines.append("- Notes: " + notes)
        system_prompt = str(payload.get("system_prompt") or "").strip()
        if system_prompt:
            lines.extend(["", "------------------------------------------------", "Group System Prompt", "", system_prompt])
        tags = profile.get("tags") if isinstance(profile.get("tags"), list) else payload.get("tags")
        if isinstance(tags, list):
            tag_line = ", ".join(str(t).strip() for t in tags if str(t).strip())
        else:
            tag_line = str(tags or "").strip()
        if not tag_line:
            tag_line = "group-card, front-porch, group-chat"
        lines.extend(["", "------------------------------------------------", "Group Tags", tag_line])

        def add_member_section(title, value):
            text = str(value or "").strip()
            if text:
                lines.extend(["", title, "", text])

        def json_text(value):
            try:
                if value in (None, "", [], {}):
                    return ""
                return json.dumps(value, indent=2, ensure_ascii=False)
            except Exception:
                return str(value or "")

        if raw_members:
            lines.extend(["", "================================================", "Embedded Member Cards", "================================================"])
            for idx, member in enumerate(raw_members, start=1):
                if not isinstance(member, dict):
                    continue
                member_name = str(member.get("name") or f"Member {idx}").strip() or f"Member {idx}"
                lines.extend(["", "------------------------------------------------", f"Member {idx}: {member_name}", "------------------------------------------------"])
                add_member_section("Description", member.get("description"))
                add_member_section("Personality", member.get("personality"))
                add_member_section("Scenario", member.get("scenario"))
                add_member_section("First Message", member.get("first_mes") or member.get("first_message"))
                alts = member.get("alternate_greetings") or []
                if isinstance(alts, list) and alts:
                    alt_lines = []
                    for alt_i, alt in enumerate(alts, start=1):
                        alt_text = str(alt or "").strip()
                        if alt_text:
                            alt_lines.append(f"Alternative First Message {alt_i}\n{alt_text}")
                    add_member_section("Alternative First Messages", "\n\n".join(alt_lines))
                add_member_section("Example Dialogues", member.get("mes_example"))
                add_member_section("System Prompt", member.get("system_prompt"))
                add_member_section("Post-History Instructions", member.get("post_history_instructions"))
                book = member.get("character_book")
                entries = (book or {}).get("entries") if isinstance(book, dict) else []
                if entries:
                    lore_lines = []
                    for entry_i, entry in enumerate(entries, start=1):
                        if not isinstance(entry, dict):
                            continue
                        entry_name = str(entry.get("name") or entry.get("key") or f"Entry {entry_i}").strip()
                        keys = entry.get("keys") or entry.get("key") or []
                        keys_text = ", ".join(keys) if isinstance(keys, list) else str(keys or "")
                        content = str(entry.get("content") or "").strip()
                        lore_lines.append(f"Name: {entry_name}\nKey(s): {keys_text}\nContent: {content}".strip())
                    add_member_section("Lorebook Entries", "\n\n".join(lore_lines))
                member_tags = member.get("tags") or []
                if isinstance(member_tags, list):
                    add_member_section("Tags", ", ".join(str(t).strip() for t in member_tags if str(t).strip()))
                else:
                    add_member_section("Tags", member_tags)
                world_names = member.get("world_names") or []
                if world_names:
                    add_member_section("World Names", json_text(world_names))
                # Surface Forge/Front Porch text extras that are useful in the editor,
                # but intentionally omit avatar_base64 to avoid dumping megabytes of PNG.
                ext = member.get("extensions") if isinstance(member.get("extensions"), dict) else {}
                if isinstance(ext, dict):
                    add_member_section("Background", ext.get("background"))
                    add_member_section("Sexual Traits", ext.get("sexual_traits"))
                    add_member_section("State Tracking", ext.get("state_tracking_raw"))
                    fp = ext.get("front_porch")
                    if isinstance(fp, dict):
                        add_member_section("Front Porch Extensions", json_text(fp))

        return "\n".join(lines).strip() + "\n"

    def _save_group_card_browser_project(self, folder, payload, group_png_path, group_json_path, members, clean_paths, options=None, mode="insert"):
        """Create a Browser-visible CCF project for a generated Front Porch Group Card."""
        options = options if isinstance(options, dict) else {}
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = str(payload.get("name") or "Group Card").strip() or "Group Card"
        output = self._group_card_browser_output(payload, members, options)
        latest_project = Path(folder) / "latest_ccf_project.json"
        latest_output = Path(folder) / "latest_output.md"
        latest_output.write_text(output, encoding="utf-8")
        settings = self._normalise_settings(options.get("settings") or self.settings)
        member_paths = [str(p) for p in clean_paths or []]
        group_profile = options.get("groupProfile") if isinstance(options.get("groupProfile"), dict) else {}
        if not group_profile:
            ext = payload.get("extensions") if isinstance(payload.get("extensions"), dict) else {}
            ccf_ext = ext.get("character_card_forge") if isinstance(ext.get("character_card_forge"), dict) else {}
            group_profile = ccf_ext.get("group_profile") if isinstance(ccf_ext.get("group_profile"), dict) else {}
        workspace = {
            "name": name,
            "output": output,
            "settings": settings,
            "cardImagePath": str(group_png_path or ""),
            "imagePath": str(group_png_path or ""),
            "groupCardPath": str(group_png_path or ""),
            "groupJsonPath": str(group_json_path or ""),
            "groupPayload": payload,
            "groupProfile": group_profile,
            "memberProjectPaths": member_paths,
            "isGroupCard": True,
            "groupCardMode": mode,
        }
        project = {
            "format": "character-card-forge-project",
            "version": self.get_app_version(),
            "saved_at": stamp,
            "project": {
                "name": name,
                "concept": str(options.get("aiInstructions") or options.get("groupInstructions") or ""),
                "output": output,
                "template": self.template,
                "settings": settings,
                "imagePath": str(group_png_path or ""),
                "cardImagePath": str(group_png_path or ""),
                "exportedPath": str(group_png_path or ""),
                "groupCardPath": str(group_png_path or ""),
                "groupJsonPath": str(group_json_path or ""),
                "groupPayload": payload,
                "groupProfile": group_profile,
                "memberProjectPaths": member_paths,
                "isGroupCard": True,
                "frontend": "front_porch_group",
                "exportFormat": "fpa_group_png",
                "browserDescription": f"Front Porch group card with {len(member_paths)} member{'s' if len(member_paths) != 1 else ''}.",
                "browserDescriptionSource": "generated",
                "tags": ["group-card", "front-porch", "group-chat"],
                "workspace": workspace,
            },
        }
        latest_project.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        snapshot = Path(folder) / f"{self._safe_slug(name)}_{stamp}_ccf_project.json"
        snapshot.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self._refresh_library_cache_for_project(latest_project, force=True)
        except Exception as e:
            self._log_event("group_card_browser_project_cache_failed", {"project": str(latest_project), "error": str(e)})
        return str(latest_project)

    def export_group_card_from_projects(self, project_paths, options=None, settings=None):
        """Create a Front Porch .group.png from 2-4 saved CCF cards."""
        try:
            options = options if isinstance(options, dict) else {}
            clean_paths = []
            for raw in project_paths or []:
                path = str(raw or "").strip()
                if path and path not in clean_paths:
                    clean_paths.append(path)
            if len(clean_paths) < 2:
                return {"ok": False, "error": "Select at least two cards for a group card."}
            if len(clean_paths) > 4:
                return {"ok": False, "error": "Front Porch group cards currently support a maximum of 4 members."}

            members = [self._group_card_member_from_project(self._project_path_inside_exports(path)) for path in clean_paths]
            mode = str(options.get("mode") or "insert").strip().lower()
            if mode == "ai":
                fields = self._build_group_card_fields_ai(members, options, settings or {})
            else:
                fields = self._build_group_card_fields_direct(members, options)

            raw_member_data = [dict(m.get("data") or {}) for m in members]
            member_names = [m.get("name") or (m.get("data") or {}).get("name") or "Character" for m in members]
            stable_ids = [m.get("stableId") or (m.get("data") or {}).get("_original_stable_id") for m in members]

            # The display member list should remain a normal per-character
            # card-shaped object. Each member keeps its own description,
            # personality, scenario, etc. raw_member_data is the high-fidelity
            # source and additionally carries avatar_base64/_original_stable_id.
            display_member_keys = [
                "name", "description", "personality", "scenario", "first_mes",
                "mes_example", "creator_notes", "system_prompt",
                "post_history_instructions", "alternate_greetings", "tags",
                "creator", "character_version", "character_book", "world_names",
                "extensions",
            ]
            display_members = []
            for raw in raw_member_data:
                minimal = {k: copy.deepcopy(raw.get(k)) for k in display_member_keys if k in raw}
                if isinstance(minimal.get("extensions"), dict):
                    # Keep display members readable/light; raw_member_data keeps
                    # the complete original extensions payload.
                    ext = dict(minimal["extensions"])
                    ext.pop("raw_card", None)
                    minimal["extensions"] = ext
                display_members.append(minimal)

            include_realism = bool(options.get("includeRealismState"))
            realism_payloads = self._group_card_realism_payloads(members) if include_realism else {"baseline": {}, "default": {}, "realism": {}}
            baseline_realism = realism_payloads.get("baseline") if isinstance(realism_payloads.get("baseline"), dict) else {}
            default_member_realism = realism_payloads.get("default") if isinstance(realism_payloads.get("default"), dict) else {}
            realism_state = realism_payloads.get("realism") if isinstance(realism_payloads.get("realism"), dict) else {}
            baseline_json = json.dumps(baseline_realism, ensure_ascii=False) if baseline_realism else "{}"
            default_realism_json = json.dumps(default_member_realism, ensure_ascii=False) if default_member_realism else "{}"
            character_system_prompts = {}
            for member in raw_member_data:
                sid = str((member or {}).get("_original_stable_id") or "").strip()
                prompt_text = str((member or {}).get("system_prompt") or "").strip()
                if sid and prompt_text:
                    character_system_prompts[sid] = prompt_text

            group_profile = {
                "group_overview": fields.get("group_overview") or "",
                "group_dynamic": fields.get("group_dynamic") or "",
                "member_roles": fields.get("member_roles") if isinstance(fields.get("member_roles"), dict) else {},
                "tags": fields.get("tags") if isinstance(fields.get("tags"), list) else [],
                "mode": mode,
                "member_project_paths": clean_paths,
                "stable_ids": stable_ids,
            }

            # Match the real Front Porch Group Card shape: the root is a group
            # wrapper, members/raw_member_data contain the actual character cards,
            # and realism compatibility fields mirror Front Porch exports.
            payload = {
                "name": fields.get("name") or " & ".join(member_names),
                "members": display_members,
                "turn_order": str(options.get("turnOrder") or "roundRobin"),
                "auto_advance": bool(options.get("autoAdvance")),
                "director_mode": bool(options.get("directorMode")),
                "first_message": fields.get("first_message") or "",
                "scenario": fields.get("scenario") or "",
                "system_prompt": fields.get("system_prompt") or "",
                "character_system_prompts": character_system_prompts,
                "group_lorebook": json.dumps({"entries": []}, ensure_ascii=False, separators=(",", ":")),
                "inherit_character_lorebooks": True,
                "chaos_mode_enabled": False,
                "chaos_nsfw_enabled": False,
                "baseline_realism_state": baseline_json,
                "default_member_realism_state": default_realism_json,
                "extensions": {
                    "realism_state": copy.deepcopy(realism_state),
                    "default_member_realism_state": copy.deepcopy(default_member_realism),
                },
                "realism_state": copy.deepcopy(realism_state),
                "raw_member_data": raw_member_data,
                "spec": "front_porch_group_card",
                "spec_version": "1.0",
            }
            payload = self._ensure_group_payload_avatar_chunks(payload, reason="create_group_card_payload")
            raw_member_data = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else raw_member_data

            safe_name = self._safe_slug(payload["name"] or "group_card")
            stamp = time.strftime("%Y%m%d-%H%M%S")
            merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
            first_image = ""
            try:
                loaded0 = self.load_character_project(clean_paths[0])
                first_image = loaded0.get("imagePath") or loaded0.get("cardImagePath") or loaded0.get("imageDataUrl") or ""
            except Exception:
                first_image = ""

            # Always create a Browser-visible CCF project for the new group card.
            # Previous beta builds only wrote the .group.png export, so Insert mode
            # appeared to do nothing in the Character Browser.
            browser_folder = self._character_export_dir(f"{payload['name']} Group Card")
            browser_png = browser_folder / f"{safe_name}_{stamp}.group.png"
            browser_latest_png = browser_folder / f"{safe_name}_latest.group.png"
            self._write_front_porch_group_png(browser_png, payload, first_image)
            try:
                shutil.copy2(browser_png, browser_latest_png)
            except Exception:
                browser_latest_png = browser_png
            browser_sidecar = browser_folder / f"{safe_name}_{stamp}.group.json"
            browser_sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            browser_latest_sidecar = browser_folder / f"{safe_name}_latest.group.json"
            try:
                shutil.copy2(browser_sidecar, browser_latest_sidecar)
            except Exception:
                browser_latest_sidecar = browser_sidecar
            project_path = self._save_group_card_browser_project(
                browser_folder,
                payload,
                browser_latest_png,
                browser_latest_sidecar,
                members,
                clean_paths,
                {**options, "settings": merged_settings, "groupProfile": group_profile},
                mode,
            )

            export_path = browser_png
            export_sidecar = browser_sidecar
            export_folder = browser_folder
            export_root = str(merged_settings.get("exportDestinationFolder") or "").strip()
            if export_root:
                export_folder = Path(export_root).expanduser().resolve()
                _safe_mkdir(export_folder)
                if not _path_is_writable_dir(export_folder):
                    return {"ok": False, "error": "The selected export folder is not writable."}
                export_path = export_folder / f"{safe_name}_{stamp}.group.png"
                export_sidecar = export_folder / f"{safe_name}_{stamp}.group.json"
                try:
                    shutil.copy2(browser_png, export_path)
                    shutil.copy2(browser_sidecar, export_sidecar)
                except Exception:
                    self._write_front_porch_group_png(export_path, payload, first_image)
                    export_sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

            self._log_event("front_porch_group_card_exported", {
                "path": str(export_path),
                "browserPath": str(browser_latest_png),
                "projectPath": str(project_path),
                "memberCount": len(raw_member_data),
                "mode": mode,
                "realismState": bool(realism_state),
                "stableIds": stable_ids,
            })
            return {
                "ok": True,
                "path": str(export_path),
                "jsonPath": str(export_sidecar),
                "browserPath": str(browser_latest_png),
                "browserJsonPath": str(browser_latest_sidecar),
                "folder": str(export_folder),
                "browserFolder": str(browser_folder),
                "projectPath": str(project_path),
                "name": payload["name"],
                "memberCount": len(raw_member_data),
                "mode": mode,
            }
        except Exception as e:
            return {"ok": False, "error": f"Could not create Front Porch group card: {e}"}

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
                    project_paths_in_folder = [str(p.resolve()) for p in folder.glob("*_ccf_project.json")] + [str((folder / "latest_ccf_project.json").resolve())]
                    shutil.rmtree(folder)
                    deleted += 1
                    try:
                        with self._library_connect() as conn:
                            now = time.time()
                            for pp in project_paths_in_folder:
                                conn.execute("UPDATE browser_cards SET deleted=1, last_seen_ts=? WHERE project_path=?", (now, pp))
                            conn.commit()
                    except Exception:
                        pass
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
            paths = self._run_modern_file_dialog("Select Vision Image", "image", False)
            if not paths:
                return {"ok": False, "cancelled": True}
            path = str(paths[0])
            if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                return {"ok": False, "error": "Please select a PNG, JPG, JPEG, or WebP image."}
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def analyze_vision_image(self, image_path, settings=None, mode="character", custom_instructions=""):
        self._reset_cancel()
        self._raise_if_cancelled()
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        self.save_settings(merged_settings)
        mode = str(mode or "character").strip().lower().replace("-", "_")
        full_card_mode = mode in {"card", "full_card", "concept", "main_concept", "scene"}
        custom_instructions = str(custom_instructions or "").strip()
        image_path = (image_path or merged_settings.get("visionImagePath") or "").strip()
        if not image_path:
            return {"ok": False, "error": "Select an image first."}
        downloaded_from_url = ""
        if self._looks_like_url(image_path):
            dl = self.save_image_from_url(image_path, "vision")
            if not dl.get("ok"):
                return dl
            downloaded_from_url = image_path
            image_path = dl.get("path") or ""
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
        character_prompt = (
            "Describe the visible fictional character for an AI roleplay character card. "
            "Focus ONLY on character visual design: physical appearance, body shape, approximate breast/chest size if visible, face, hair, eyes, skin tone, visible distinguishing features, clothing, accessories, and fashion style. "
            "Do NOT include age/age appearance, expression, emotion, pose, posture, camera angle, setting, scene context, background, lighting, story context, pose symbolism, personality, or identity speculation. "
            "Do not identify the character or speculate about identity. "
            "Do not describe minors as sexualized; if age is unclear, avoid age entirely and describe only neutral visible adult-coded traits. "
            "If multiple characters are visible, give a separate concise subsection for each visible character. "
            "Output clean bullet points under the heading 'Visual Description'."
        )

        full_card_prompt = (
            "Analyze the entire fictional character card/reference image, not only the character. "
            "Use the whole image: character design, pose/action, expression, clothing, props, visible text if legible, background, location, mood, lighting, symbols, composition, and any implied story context. "
            "Turn that into a playable Main Concept for an AI roleplay character card. "
            "Infer useful creative details only when the image strongly suggests them; mark uncertain details as implied rather than factual. "
            "Do not identify copyrighted characters, real people, artists, or source titles. Do not claim identity from the image. "
            "Do not sexualize anyone who appears underage; if age is unclear, keep the concept adult-coded or non-explicit. "
            "Return a concise concept block ready to paste into the Main Concept window with these headings:\n"
            "Title Idea:\n"
            "Core Character:\n"
            "Visual Design:\n"
            "Personality / Vibe:\n"
            "Setting:\n"
            "What Is Happening In The Card:\n"
            "Relationship To {{user}}:\n"
            "Core Conflict / Hook:\n"
            "Scenario Starting Point:\n"
            "Important Details To Preserve:\n"
            "Keep it specific, vivid, and generator-friendly."
        )

        prompt = full_card_prompt if full_card_mode else character_prompt
        if custom_instructions:
            prompt += (
                "\n\nUSER CUSTOM INSTRUCTIONS FOR THIS ANALYSIS:\n"
                + custom_instructions
                + "\nUse these instructions when they are compatible with the visible image and safety rules. If the user asks you to be creative, add useful roleplay-ready implications without claiming uncertain image details as fact."
            )

        character_sfw_retry_prompt = (
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

        full_card_sfw_retry_prompt = (
            "The previous attempt may have refused because the reference image contained nudity or sexual context. "
            "For this retry, analyze the entire image as a SAFE-FOR-WORK fictional character-card concept only. "
            "Use neutral wording for body/clothing, omit explicit anatomy and sexual acts, and transform any explicit context into non-explicit story/relationship tension. "
            "Consider the character, background, setting, props, mood, visible text if legible, and implied scene. "
            "Do not identify copyrighted characters, real people, artists, or source titles. Do not sexualize anyone who appears underage; if age is unclear, keep the concept adult-coded or non-explicit. "
            "Return a concise Main Concept block with these headings: Title Idea, Core Character, Visual Design, Personality / Vibe, Setting, What Is Happening In The Card, Relationship To {{user}}, Core Conflict / Hook, Scenario Starting Point, Important Details To Preserve."
        )

        sfw_retry_prompt = full_card_sfw_retry_prompt if full_card_mode else character_sfw_retry_prompt
        if custom_instructions:
            sfw_retry_prompt += (
                "\n\nUSER CUSTOM INSTRUCTIONS TO PRESERVE SAFELY:\n"
                + custom_instructions
                + "\nPreserve only the safe, non-explicit parts of these instructions and ignore anything that conflicts with the SFW retry requirements."
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
            + ("Return a concise safe Main Concept block using the requested headings. " if full_card_mode else "Return a concise safe visual character-design description only, with 5-12 bullet points under 'Visual Description'. ")
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
                    {"role": "system", "content": "You are a precise visual analysis assistant for fictional AI character card creation. For character mode, describe only visual character design. For full-card mode, convert the whole image into a concise playable Main Concept. When asked for SFW output, safely transform visual references into neutral, non-explicit character-card descriptions."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:{image_payload['mime']};base64,{image_payload['b64']}"}}
                    ]}
                ],
                "temperature": 0.2,
                "max_tokens": 2600 if full_card_mode else 1800,
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
                "custom_instructions_present": bool(custom_instructions),
                "custom_instructions_preview": custom_instructions[:500],
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
        if not full_card_mode:
            description = clean_vision_description(description)
            if description != raw_description:
                self._log_event("vision_analyze_cleaned", {"removed_disallowed_context": True, "before": raw_description[:4000], "after": description[:4000]})
        if is_empty_vision_result(description):
            self._log_event("vision_analyze_empty_after_cleanup", {"raw_description": raw_description[:4000]})
            return {"ok": False, "error": "Vision analysis produced no usable description after cleanup. Try a different vision model or enter the visual description manually."}

        self._log_event("vision_analyze_response", {"retry_used": retry_used, "mode": "full_card" if full_card_mode else "character", "description": description})
        result = {"ok": True, "description": description, "imagePath": str(path), "sourceUrl": downloaded_from_url, "retryUsed": retry_used, "mode": "full_card" if full_card_mode else "character"}
        if full_card_mode:
            result["concept"] = description
        return result


    def _normalise_sd_prompt_items(self, text, *, max_items=90, max_chars=1200):
        """Normalize comma-separated SD prompt fragments and remove repeated loops."""
        text = str(text or "").strip()
        if not text:
            return ""
        text = re.sub(r"(?is)^\s*(?:positive|negative)\s+prompt\s*[:：]\s*", "", text).strip()
        parts = re.split(r",|\n", text)
        out = []
        seen = set()
        for raw in parts:
            item = re.sub(r"\s+", " ", str(raw or "").strip())
            item = item.strip(" ,;.")
            if not item:
                continue
            # Normalize wrapper parentheses only for duplicate comparison, but keep the user's weighting syntax in output.
            key = item.lower()
            key = re.sub(r"^[\(\[\{]+|[\)\]\}]+$", "", key).strip()
            key = re.sub(r"\s+", " ", key)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= max_items:
                break
        cleaned = ", ".join(out).strip()
        if len(cleaned) > max_chars:
            trimmed = []
            total = 0
            for item in out:
                add_len = len(item) + (2 if trimmed else 0)
                if total + add_len > max_chars:
                    break
                trimmed.append(item)
                total += add_len
            cleaned = ", ".join(trimmed).strip()
        return cleaned

    def _default_sd_negative_prompt(self):
        return "bad anatomy, extra fingers, missing fingers, extra limbs, missing limbs, poorly drawn hands, poorly drawn face, deformed, disfigured, mutation, ugly, blurry, cropped, out of frame, low quality, worst quality, normal quality, jpeg artifacts, watermark, signature, text, logo"

    def _extract_natural_image_prompt(self, output):
        section = self._clean_section_text(self._section(output, "Natural English Image Prompt"))
        return section.strip()

    def _build_natural_image_prompt_body(self, output, settings=None, model=None):
        prompts = self._extract_sd_prompts(output or "")
        existing = self._extract_natural_image_prompt(output or "")
        if existing:
            return existing
        body = self._build_natural_api_image_prompt(output or "", prompts, settings or self.settings, model or "")
        return self._clean_section_text(body)

    def generate_natural_prompt_from_output(self, output, settings=None):
        output = (output or "").strip()
        if not output:
            return {"ok": False, "error": "Generate or load a card first so I can read the character text."}
        natural_body = self._build_natural_image_prompt_body(output, settings=settings)
        if not natural_body:
            return {"ok": False, "error": "Could not build a Natural English Image Prompt from the current card."}
        updated_output = self._replace_section_body(output, "natural_image_prompt", natural_body, template=self.template, title_fallback="Natural English Image Prompt")
        updated_output = self._clean_generated_output(updated_output)
        return {"ok": True, "output": updated_output, "naturalImagePromptBody": natural_body, "method": "full_text_output"}

    def _ensure_image_prompt_sections(self, output, settings=None):
        text_out = str(output or "")
        if not text_out.strip():
            return text_out
        merged = self._normalise_settings({**self.settings, **(settings or {})})
        has_sd = bool(self._extract_sd_prompts(text_out).get("positive"))
        natural = self._extract_natural_image_prompt(text_out)
        provider = str(merged.get("imageGenerationProvider") or "sd").strip().lower()
        wants_natural = provider == "api" and self._api_image_prompt_style(merged, merged.get("imageModel") or "") == "natural"
        if (has_sd or wants_natural) and not natural:
            body = self._build_natural_image_prompt_body(text_out, settings=merged, model=merged.get("imageModel") or "")
            if body:
                text_out = self._replace_section_body(text_out, "natural_image_prompt", body, template=self.template, title_fallback="Natural English Image Prompt")
        return text_out

    def _build_sd_prompt_from_character_text(self, reference_text, settings=None, vision_summary=""):
        local_settings = self._normalise_settings({**self.settings, **(settings or {})})
        validation = self._validate_text_api_settings(local_settings)
        if not validation.get("ok"):
            return {"ok": False, "error": validation.get("error") or "AI settings are incomplete."}
        model = (local_settings.get("aiSuggestionModel") or local_settings.get("model") or "").strip()
        if not model:
            return {"ok": False, "error": "Set a Text Model or AI Suggestion Model first."}
        base_context = (reference_text or "").strip()
        if not base_context and not vision_summary:
            return {"ok": False, "error": "There is not enough character information to generate a Stable Diffusion Prompt."}
        visual_style = self._image_visual_style(local_settings)
        style_label = "anime-style illustrated" if visual_style == "anime" else "realistic cinematic"
        prompt_parts = [
            f"Create a Stable Diffusion Prompt section for a fictional {style_label} character card.",
            "Return ONLY the Stable Diffusion Prompt section body, not the whole card.",
            "Use exactly this format:",
            "Positive Prompt: <comma-separated prompt>",
            "Negative Prompt: <comma-separated negative prompt>",
            "The positive prompt should focus on a single polished portrait/card image of the character and include appearance, body type, hair, eyes, clothing, key accessories, expression, pose, environment/background, lighting, style, and quality tags.",
            f"The prompt style must lean {style_label}.",
            "The negative prompt must be concise: 15-30 UNIQUE comma-separated tags only. Do not repeat tags or phrases.",
            "Do not include explanations, bullet points, JSON, markdown fences, helper text, or headings other than Positive Prompt and Negative Prompt.",
        ]
        if vision_summary:
            prompt_parts.extend(["", "VISION / IMAGE NOTES", vision_summary.strip()])
        if base_context:
            prompt_parts.extend(["", "CHARACTER CARD TEXT", base_context])
        prompt = "\n".join(prompt_parts).strip()
        try:
            sd_body = self._chat_once(prompt, local_settings, model, "sd_prompt_generation")
        except Exception as e:
            return {"ok": False, "error": f"Stable Diffusion prompt generation failed: {e}"}
        sd_body = self._strip_sd_prompt_guidance(self._clean_section_text(sd_body))
        pos_match = re.search(r"(?is)positive\s+prompt\s*[:：]\s*(.+?)(?:\n+\s*negative\s+prompt\s*[:：]|\Z)", sd_body)
        neg_match = re.search(r"(?is)negative\s+prompt\s*[:：]\s*(.+)$", sd_body)
        positive = (pos_match.group(1).strip() if pos_match else "")
        negative = (neg_match.group(1).strip() if neg_match else "")
        if not positive:
            compact = re.sub(r"\s+", " ", sd_body).strip()
            if compact and "," in compact:
                positive = compact
        positive = self._normalise_sd_prompt_items(positive, max_items=120, max_chars=1800)
        negative = self._normalise_sd_prompt_items(negative, max_items=32, max_chars=700)
        if not positive:
            return {"ok": False, "error": "The AI did not return a usable Stable Diffusion positive prompt."}
        if not negative:
            negative = self._default_sd_negative_prompt()
        else:
            # Make sure common cleanup tags are present without creating the runaway repetition bug.
            negative = self._normalise_sd_prompt_items(negative + ", " + self._default_sd_negative_prompt(), max_items=36, max_chars=800)
        sd_body = f"Positive Prompt: {positive}\nNegative Prompt: {negative}"
        return {"ok": True, "stableDiffusionBody": sd_body.strip(), "positive": positive, "negative": negative}

    def generate_relationship_matrix(self, characters, settings=None):
        """Generate a relationship matrix for currently open workspace characters."""
        try:
            settings = self._normalise_settings(settings or self.settings)
            rows = []
            for idx, item in enumerate(characters or []):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("focusName") or f"Character {idx + 1}").strip() or f"Character {idx + 1}"
                output = str(item.get("output") or "").strip()
                if not output:
                    continue
                rows.append({"name": name[:120], "output": output[:18000]})
            if len(rows) < 2:
                return {"ok": False, "error": "Open at least two generated characters first."}
            character_blocks = []
            for i, row in enumerate(rows, start=1):
                character_blocks.append(f"CHARACTER {i}: {row['name']}\n{row['output']}")
            prompt = "\n\n".join([
                "Create a multi-character roleplay relationship matrix for these open character cards.",
                "Use the card text as canon. Do not invent major contradictions, but infer plausible connections, tensions, alliances, rivalries, attraction, jealousy, secrets, and roleplay hooks where useful.",
                "Return GitHub-flavored Markdown only.",
                "Format exactly like this:",
                "# Relationship Matrix",
                "## Overview\nShort paragraph on the group dynamic.",
                "## Matrix\nA table with rows = source character and columns = target character. Each non-self cell should be 1-2 concise sentences. Self cells should be —.",
                "## Pair Hooks\nBullets for each important pair: **A ↔ B:** hook/tension/conflict.",
                "## Group Roleplay Seeds\n5-8 bullets for scenes that use multiple characters together.",
                "Characters:",
                "\n\n---\n\n".join(character_blocks),
            ])
            self._log_event("relationship_matrix_request", {"characterCount": len(rows), "characters": [r["name"] for r in rows]})
            matrix = self._chat_once(prompt, settings, (settings.get("model") or "").strip(), "relationship_matrix")
            matrix = re.sub(r"^```(?:markdown|md)?\s*", "", str(matrix or "").strip(), flags=re.IGNORECASE)
            matrix = re.sub(r"\s*```$", "", matrix).strip()
            self._log_event("relationship_matrix_response", {"characterCount": len(rows), "preview": matrix[:1000]})
            return {"ok": True, "matrix": matrix, "characters": [r["name"] for r in rows]}
        except Exception as e:
            self._log_event("relationship_matrix_failed", {"error": str(e)})
            return {"ok": False, "error": str(e)}

    def generate_sd_prompt_from_output(self, output, settings=None):
        output = (output or "").strip()
        if not output:
            return {"ok": False, "error": "Generate or load a card first so I can read the character text."}
        res = self._build_sd_prompt_from_character_text(output, settings=settings)
        if not res.get("ok"):
            return res
        updated_output = self._replace_section_body(output, "stable_diffusion", res.get("stableDiffusionBody") or "", template=self.template, title_fallback="Stable Diffusion Prompt")
        updated_output = self._ensure_image_prompt_sections(self._clean_generated_output(updated_output), settings)
        return {"ok": True, "output": updated_output, "stableDiffusionBody": res.get("stableDiffusionBody"), "positive": res.get("positive"), "negative": res.get("negative"), "method": "full_text_output"}

    def generate_sd_prompt_from_vision(self, image_path, output='', settings=None):
        image_path = str(image_path or "").strip()
        if not image_path:
            return {"ok": False, "error": "Select a card image first so the vision model has something to read."}
        vision = self.analyze_vision_image(image_path, settings)
        if not vision.get("ok"):
            return vision
        vision_summary = str(vision.get("description") or "").strip()
        reference_text = (output or "").strip()
        if reference_text:
            reference_text = reference_text + "\n\nVisual reference summary:\n" + vision_summary
        else:
            reference_text = "Visual reference summary:\n" + vision_summary
        res = self._build_sd_prompt_from_character_text(reference_text, settings=settings, vision_summary=vision_summary)
        if not res.get("ok"):
            return res
        updated_output = self._replace_section_body(output or "", "stable_diffusion", res.get("stableDiffusionBody") or "", template=self.template, title_fallback="Stable Diffusion Prompt")
        updated_output = self._ensure_image_prompt_sections(self._clean_generated_output(updated_output), settings)
        return {"ok": True, "output": updated_output, "stableDiffusionBody": res.get("stableDiffusionBody"), "positive": res.get("positive"), "negative": res.get("negative"), "visionDescription": vision_summary, "method": "vision"}

    def select_card_image(self):
        try:
            paths = self._run_modern_file_dialog("Select Card Image", "image", False)
            if not paths:
                return {"ok": False, "cancelled": True}
            path = str(paths[0])
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


    def _image_api_base_url(self, settings):
        base = str(settings.get("imageApiBaseUrl") or settings.get("apiBaseUrl") or DEFAULT_SETTINGS.get("apiBaseUrl") or "").strip()
        if not base:
            return ""
        if not re.match(r"^https?://", base, re.I):
            base = "https://" + base
        base = base.rstrip("/")
        lowered = base.lower()
        for suffix in ("/images/generations", "/image/generations", "/images/generate", "/generate-image", "/image-models", "/models"):
            if lowered.endswith(suffix):
                base = base[: -len(suffix)]
                lowered = base.lower()
        return base.rstrip("/")

    def _image_api_key(self, settings):
        return str(settings.get("imageApiKey") or settings.get("apiKey") or "").strip()

    def _parse_api_image_price(self, item):
        try:
            pricing = item.get("pricing") if isinstance(item, dict) else {}
            per_image = pricing.get("per_image") if isinstance(pricing, dict) else {}
            if isinstance(per_image, dict) and per_image:
                first_key = next(iter(per_image.keys()))
                val = per_image.get(first_key)
                return f"${float(val):g}/{first_key}"
        except Exception:
            pass
        return ""

    def _api_image_model_entry(self, item):
        if not isinstance(item, dict):
            return None
        model_id = str(item.get("id") or item.get("model") or "").strip()
        if not model_id:
            return None
        category = str(item.get("category") or "").strip().lower()
        if category == "tools":
            return None
        arch = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
        modality = str(arch.get("modality") or item.get("modality") or "").strip()
        input_modalities = arch.get("input_modalities") if isinstance(arch.get("input_modalities"), list) else []
        output_modalities = arch.get("output_modalities") if isinstance(arch.get("output_modalities"), list) else []
        caps = item.get("capabilities") if isinstance(item.get("capabilities"), dict) else {}
        params = item.get("supported_parameters") if isinstance(item.get("supported_parameters"), dict) else {}
        tags = [str(t).lower() for t in (item.get("tags") if isinstance(item.get("tags"), list) else [])]
        if caps and caps.get("image_generation") is False:
            return None
        if output_modalities and "image" not in [str(x).lower() for x in output_modalities]:
            return None
        # For the first beta, CCF only generates card portraits from text.  Pure edit/upscale/crop tools need
        # reference-image upload workflows, so keep them out of the picker for now.
        modality_l = modality.lower()
        if modality_l == "image->image" or any(t in {"upscale", "crop", "background-remover", "text-removal", "virtual-try-on"} for t in tags):
            return None
        if input_modalities and "text" not in [str(x).lower() for x in input_modalities]:
            return None
        resolutions = params.get("resolutions") if isinstance(params.get("resolutions"), list) else []
        try:
            max_images = int(params.get("max_output_images") or params.get("max_images") or 1)
        except Exception:
            max_images = 1
        name = str(item.get("name") or model_id).strip()
        owner = str(item.get("owned_by") or "").strip()
        price = self._parse_api_image_price(item)
        bits = [name]
        if owner:
            bits.append(owner)
        if modality:
            bits.append(modality)
        if price:
            bits.append(price)
        if max_images:
            bits.append(f"max {max_images}")
        display = " • ".join(bits) + f" — {model_id}"
        return {
            "value": model_id,
            "id": model_id,
            "name": name,
            "ownedBy": owner,
            "displayName": display,
            "description": str(item.get("description") or ""),
            "modality": modality,
            "resolutions": [str(x) for x in resolutions],
            "defaultResolution": str(resolutions[0]) if resolutions else "1024x1024",
            "maxImages": max_images,
            "imageToImage": bool(caps.get("image_to_image")),
            "nsfw": bool(caps.get("nsfw")),
        }

    def fetch_api_image_models(self, settings=None):
        """Fetch OpenAI/NanoGPT-style image model metadata for the API image picker."""
        merged = self._normalise_settings({**self.settings, **(settings or {})})
        base = self._image_api_base_url(merged)
        key = self._image_api_key(merged)
        if not base:
            return {"ok": False, "error": "Enter an Image API Base URL or Text API Base URL first."}
        if self._api_key_required_for_base(base) and not key:
            return {"ok": False, "error": "Enter an Image API Key or Text API Key first."}
        endpoint_candidates = [
            base + "/image-models",
            base + "/image-models?detailed=true",
            base + "/models?detailed=true",
            base + "/models",
        ]
        endpoints = []
        seen_endpoints = set()
        for url in endpoint_candidates:
            if url not in seen_endpoints:
                seen_endpoints.add(url)
                endpoints.append(url)
        last_error = ""
        for url in endpoints:
            req = urllib.request.Request(url, method="GET")
            req.add_header("Accept", "application/json")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
                req.add_header("x-api-key", key)
            try:
                with self._urlopen_with_retries(req, merged, timeout=120, label="API image model list") as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
                items = data.get("data") if isinstance(data, dict) else data
                if not isinstance(items, list):
                    items = []
                models = []
                seen = set()
                for item in items:
                    entry = self._api_image_model_entry(item)
                    if not entry:
                        continue
                    key_id = entry["id"].lower()
                    if key_id in seen:
                        continue
                    seen.add(key_id)
                    models.append(entry)
                selected = str(merged.get("imageModel") or "").strip()
                default_resolution = "1024x1024"
                if selected:
                    for m in models:
                        if m.get("id") == selected and m.get("defaultResolution"):
                            default_resolution = m.get("defaultResolution")
                            break
                elif models:
                    default_resolution = models[0].get("defaultResolution") or default_resolution
                self._log_event("api_image_models_fetched", {"url": url, "count": len(models), "selected": selected})
                if models:
                    return {"ok": True, "models": models, "selectedModel": selected, "defaultResolution": default_resolution}
                # Keep trying fallback endpoints if this endpoint returns no usable image models.
                last_error = f"No usable image models found at {url}"
                continue
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {e.code}: {body[:800]}"
            except Exception as e:
                last_error = str(e)
        return {"ok": False, "error": f"Could not fetch API image models: {last_error}"}

    def _api_image_prompt_style(self, settings, model):
        mode = str(settings.get("imagePromptMode") or "auto").strip().lower()
        if mode in {"sd", "natural"}:
            return mode
        m = str(model or "").lower()
        natural_markers = [
            "gpt", "openai", "banana", "gemini", "imagen", "seedream", "qwen", "wan", "hidream",
            "ideogram", "recraft", "grok", "kling", "vidu", "runway", "midjourney", "minimax",
            "hunyuan", "ernie", "longcat", "reve", "lucid", "krea", "riverflow", "bagel"
        ]
        sd_markers = [
            "stable-diffusion", "sdxl", "sd3", "sd-", "pony", "animagine", "dreamshaper", "rev-animated",
            "illustrious", "hassaku", "realvis", "cyberrealistic", "chroma", "juggernaut", "proteus", "flux"
        ]
        if any(x in m for x in natural_markers):
            return "natural"
        if any(x in m for x in sd_markers):
            return "sd"
        return "natural"

    def _image_visual_style(self, settings=None):
        style = str((settings or {}).get("imageVisualStyle") or self.settings.get("imageVisualStyle") or "anime").strip().lower()
        return style if style in {"anime", "realistic"} else "anime"

    def _image_visual_style_phrase(self, settings=None):
        return "anime-style illustrated" if self._image_visual_style(settings) == "anime" else "realistic cinematic"

    def _natural_prompt_filter_safe_positive_close(self, settings=None):
        if self._image_visual_style(settings) == "anime":
            return "Use a clean anime illustration style, polished linework, appealing color design, balanced lighting, and a focused single-character portrait composition."
        return "Use a realistic cinematic portrait style, natural skin texture, believable lighting, detailed fabric and hair, and a focused single-character portrait composition."

    def _build_natural_api_image_prompt(self, output, prompts, settings, model):
        existing = self._extract_natural_image_prompt(output or "")
        if existing:
            return existing
        sections = self._parse_sections(output or {}) if isinstance(output, dict) else self._parse_sections(output or "")
        name = self._extract_name(output or "") or "the character"
        description = self._clean_section_text(sections.get("description") or self._section(output or "", "Description"))
        personality = self._clean_section_text(sections.get("personality") or self._section(output or "", "Personality"))
        scenario = self._clean_section_text(sections.get("scenario") or self._section(output or "", "Scenario"))
        positive = self._normalise_sd_prompt_items(prompts.get("positive") or "", max_items=90, max_chars=1400)
        visual_style = self._image_visual_style_phrase(settings)
        parts = [
            f"Create a polished {visual_style} character-card portrait of {name}.",
            "Single main character, centered composition, clean readable silhouette, strong face and outfit detail, high quality lighting, suitable as a roleplay character card portrait.",
            self._natural_prompt_filter_safe_positive_close(settings),
        ]
        if description:
            parts.append("Character appearance and identity: " + re.sub(r"\s+", " ", description)[:1600])
        if positive:
            parts.append("Visual prompt notes to follow: " + positive)
        if personality:
            parts.append("Mood/personality to express visually: " + re.sub(r"\s+", " ", personality)[:900])
        if scenario:
            parts.append("Optional setting/atmosphere: " + re.sub(r"\s+", " ", scenario)[:700])
        return "\n\n".join(p for p in parts if p).strip()

    def _build_api_image_prompt(self, output, prompts, settings, model):
        style = self._api_image_prompt_style(settings, model)
        positive = self._normalise_sd_prompt_items(prompts.get("positive") or "", max_items=120, max_chars=1800)
        negative = self._normalise_sd_prompt_items(prompts.get("negative") or "", max_items=36, max_chars=800)
        if style == "sd":
            style_prefix = "anime style" if self._image_visual_style(settings) == "anime" else "realistic, cinematic portrait, lifelike detail"
            positive = self._normalise_sd_prompt_items((style_prefix + ", " + positive).strip(", "), max_items=130, max_chars=1900)
            if negative:
                return f"{positive}\nNegative prompt: {negative}".strip(), style
            return positive, style
        return self._build_natural_api_image_prompt(output, prompts, settings, model), style

    def _collect_image_blobs_from_response_value(self, value, out):
        if value is None:
            return
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return
            if s.lower().startswith("data:image"):
                try:
                    b64 = s.split(",", 1)[1]
                    out.append(base64.b64decode(re.sub(r"\s+", "", b64), validate=False))
                except Exception:
                    pass
                return
            if re.match(r"^https?://", s, re.I):
                try:
                    req = urllib.request.Request(s, method="GET")
                    with self._urlopen_with_retries(req, self.settings, timeout=180, label="API image download") as resp:
                        out.append(resp.read())
                except Exception as e:
                    self._log_event("api_image_url_download_failed", {"url": s[:500], "error": str(e)})
                return
            # Plain base64 image body.
            compact = re.sub(r"\s+", "", s)
            if len(compact) > 100 and re.match(r"^[A-Za-z0-9+/=_-]+$", compact):
                try:
                    out.append(base64.b64decode(compact + ("=" * (-len(compact) % 4)), validate=False))
                except Exception:
                    pass
                return
        elif isinstance(value, dict):
            priority = ["b64_json", "image_base64", "base64", "b64", "data", "image", "url", "image_url", "output_image"]
            used = set()
            for key in priority:
                if key in value:
                    used.add(key)
                    self._collect_image_blobs_from_response_value(value.get(key), out)
            for key, child in value.items():
                if key not in used:
                    self._collect_image_blobs_from_response_value(child, out)
        elif isinstance(value, list):
            for child in value:
                self._collect_image_blobs_from_response_value(child, out)

    def _api_image_response_blobs(self, raw_bytes, content_type=""):
        blobs = []
        ct = str(content_type or "").lower()
        if raw_bytes and ct.startswith("image/"):
            return [raw_bytes]
        try:
            data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except Exception:
            # Some gateways return a raw image without a useful content type.
            if raw_bytes.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10])) or raw_bytes.startswith(bytes([255, 216, 255])) or raw_bytes[:4] == b"RIFF":
                return [raw_bytes]
            return []
        self._collect_image_blobs_from_response_value(data, blobs)
        return blobs

    def _save_api_generated_image_blob(self, raw, safe, stamp, idx):
        path = GENERATED_IMAGES_DIR / f"{safe}_{stamp}_api_{idx}.png"
        try:
            with Image.open(io.BytesIO(raw)) as img:
                img = img.convert("RGBA")
                img.save(path, "PNG")
            png_raw = path.read_bytes()
        except Exception:
            # Keep the raw bytes for debugging/export even if Pillow cannot decode it.
            path.write_bytes(raw)
            png_raw = raw
        return {
            "path": str(path),
            "dataUrl": "data:image/png;base64," + base64.b64encode(png_raw).decode("ascii"),
        }

    def _parse_image_resolution_dimensions(self, resolution):
        raw = str(resolution or "1024x1024").strip().lower()
        m = re.match(r"^(\d+)\s*[x×]\s*(\d+)$", raw)
        if not m:
            return 1024, 1024
        try:
            return max(64, min(4096, int(m.group(1)))), max(64, min(4096, int(m.group(2))))
        except Exception:
            return 1024, 1024

    def _api_image_generation_endpoints(self, base):
        base = str(base or "").rstrip("/")
        lowered = base.lower()
        is_nanogpt = "nano-gpt.com" in lowered
        if is_nanogpt:
            # NanoGPT uses /api/v1 for model discovery but the documented
            # OpenAI-compatible image generation path is /v1/images/generations.
            if lowered.endswith("/api/v1"):
                root = re.sub(r"/api/v1$", "/v1", base, flags=re.I)
            elif lowered.endswith("/api"):
                root = re.sub(r"/api$", "/v1", base, flags=re.I)
            elif lowered.endswith("/v1"):
                root = base
            else:
                root = base + "/v1"
            return [root.rstrip("/") + "/images/generations"]
        bases = [base] if base else []
        candidates = []
        for b in bases:
            candidates.extend([
                b + "/images/generations",
                b + "/image/generations",
                b + "/image/generate",
                b + "/generate-image",
                b + "/images/generate",
            ])
        out = []
        seen = set()
        for url in candidates:
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _api_image_generation_payloads(self, model, prompt, count, resolution, style="natural", base=""):
        width, height = self._parse_image_resolution_dimensions(resolution)
        prompt = str(prompt or "").strip()
        model = str(model or "").strip()
        count = self._clamp_int_value(count, default=1, minimum=1, maximum=20)
        resolution = str(resolution or f"{width}x{height}").strip() or f"{width}x{height}"
        aspect_ratio = f"{width}:{height}"
        is_nanogpt = "nano-gpt.com" in str(base or "").lower()
        if is_nanogpt:
            # Keep NanoGPT requests exactly OpenAI-compatible. Extra native-style
            # fields/routes can produce misleading 404/HTML errors and hide the
            # real API validation message. Try the requested count, then a safe
            # one-image fallback for models with fixed counts or max_images=1.
            payloads = [
                {"model": model, "prompt": prompt, "n": count, "size": resolution, "response_format": "b64_json"},
            ]
            if count != 1:
                payloads.append({"model": model, "prompt": prompt, "n": 1, "size": resolution, "response_format": "b64_json"})
        else:
            payloads = [
                {"model": model, "prompt": prompt, "n": count, "size": resolution, "response_format": "b64_json"},
                {"model": model, "prompt": prompt, "n": count, "size": resolution},
                {"model": model, "prompt": prompt, "num_images": count, "size": resolution},
                {"model": model, "prompt": prompt, "num_images": count, "width": width, "height": height},
                {"model": model, "prompt": prompt, "image_count": count, "resolution": resolution},
                {"model": model, "prompt": prompt, "image_count": count, "width": width, "height": height},
                {"model": model, "prompt": prompt, "num_outputs": count, "width": width, "height": height},
                {"model": model, "prompt": prompt, "count": count, "width": width, "height": height},
                {"model": model, "prompt": prompt, "aspect_ratio": aspect_ratio, "num_images": count},
            ]
        out = []
        seen = set()
        for payload in payloads:
            key = json.dumps(payload, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(payload)
        return out

    def _clean_api_image_http_error_body(self, body):
        body = str(body or "")
        compact = re.sub(r"\s+", " ", body).strip()
        if compact.lower().startswith("<!doctype html") or "<html" in compact.lower()[:200]:
            return "HTML 404/page response"
        return compact[:1000]

    def _generate_api_image_model_images(self, output, merged_settings, prompts):
        model = str(merged_settings.get("imageModel") or "").strip()
        if not model:
            return {"ok": False, "error": "Select an API Image Model in Image Generation settings first."}
        base = self._image_api_base_url(merged_settings)
        key = self._image_api_key(merged_settings)
        if not base:
            return {"ok": False, "error": "Enter an Image API Base URL or Text API Base URL first."}
        if self._api_key_required_for_base(base) and not key:
            return {"ok": False, "error": "Enter an Image API Key or Text API Key first."}
        image_count = self._clamp_int_value(merged_settings.get("sdImageCount") or 4, default=4, minimum=1, maximum=20)
        resolution = str(merged_settings.get("imageResolution") or "1024x1024").strip() or "1024x1024"
        prompt, style = self._build_api_image_prompt(output, prompts, merged_settings, model)
        if not prompt:
            return {"ok": False, "error": "Could not build an API image prompt from the card."}
        endpoints = self._api_image_generation_endpoints(base)
        payloads = self._api_image_generation_payloads(model, prompt, image_count, resolution, style, base)
        self._log_event("api_image_generation_start", {"model": model, "count": image_count, "resolution": resolution, "promptStyle": style, "base": base, "generationEndpointFirst": endpoints[0] if endpoints else ""})
        last_error = ""
        first_meaningful_error = ""
        errors = []
        blobs = []
        for endpoint in endpoints:
            for payload in payloads:
                req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST")
                req.add_header("Content-Type", "application/json")
                req.add_header("Accept", "application/json, image/png, image/jpeg, image/webp")
                if key:
                    req.add_header("Authorization", f"Bearer {key}")
                    req.add_header("x-api-key", key)
                try:
                    with self._urlopen_with_retries(req, merged_settings, timeout=900, label="API image generation") as resp:
                        raw = resp.read()
                        content_type = resp.headers.get("Content-Type", "") if getattr(resp, "headers", None) else ""
                    blobs = self._api_image_response_blobs(raw, content_type)
                    if blobs:
                        break
                    last_error = f"{endpoint}: API returned no parseable image data."
                    errors.append(last_error)
                    if not first_meaningful_error:
                        first_meaningful_error = last_error
                except urllib.error.HTTPError as e:
                    body = self._clean_api_image_http_error_body(e.read().decode("utf-8", errors="replace"))
                    last_error = f"{endpoint} HTTP {e.code}: {body}"
                    errors.append(last_error)
                    if e.code != 404 and body != "HTML 404/page response" and not first_meaningful_error:
                        first_meaningful_error = last_error
                    if e.code == 404:
                        break
                    continue
                except Exception as e:
                    last_error = str(e)
                    errors.append(last_error)
                    if not first_meaningful_error:
                        first_meaningful_error = last_error
                    continue
            if blobs:
                break
        if not blobs:
            shown_error = first_meaningful_error or last_error
            self._log_event("api_image_generation_failed", {"model": model, "endpointsTried": endpoints, "payloadsTried": payloads, "errors": errors[-12:], "lastError": last_error, "shownError": shown_error})
            return {"ok": False, "error": f"API image generation failed: {shown_error}. Tried: {', '.join(endpoints)}"}
        safe_name = self._extract_name(output) or "character_card"
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", safe_name).strip("_") or "character_card"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        results = []
        for idx, raw in enumerate(blobs[:image_count], start=1):
            try:
                results.append(self._save_api_generated_image_blob(raw, safe, stamp, idx))
            except Exception as e:
                return {"ok": False, "error": f"Could not save API image {idx}: {e}"}
        return {"ok": True, "images": results, "provider": "api", "model": model, "prompt": prompt, "promptStyle": style, "resolution": resolution}
    def generate_sd_images(self, output, settings=None):
        """Generate four 1024x1024 candidate card images from Stable Diffusion Prompt.

        Supports Automatic1111 / SD Forge compatible endpoints at /sdapi/v1/txt2img.
        The generated images are NOT embedded automatically. The user selects one,
        then Character Card V2 PNG export uses that selected image.
        """
        # Start every standard image batch with a fresh cancellation state.
        # Emotion-image generation shares the same backend cancel event, and a
        # user-cancelled emotion job can leave that event set after returning.
        # Without clearing it here, the next Quick Save / Image generation can
        # fail instantly with the stale "Task cancelled by user" error.
        self._reset_cancel()
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or paste a card first so I can read the Stable Diffusion Prompt section."}
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        image_count = self._clamp_int_value(merged_settings.get("sdImageCount") or 4, default=4, minimum=1, maximum=20)
        self._log_event("sd_image_generation_start", {"count": image_count, "cancelStateReset": True})
        self.save_settings(merged_settings)
        prompts = self._extract_sd_prompts(output)
        if str(merged_settings.get("imageGenerationProvider") or "sd").strip().lower() == "api":
            return self._generate_api_image_model_images(output, merged_settings, prompts)
        if not prompts.get("positive"):
            return {"ok": False, "error": "No Positive Prompt found in the Stable Diffusion Prompt section."}
        base = (merged_settings.get("sdBaseUrl") or "http://127.0.0.1:7860").rstrip("/")
        url = base + "/sdapi/v1/txt2img"
        payload = {
            "prompt": prompts.get("positive", ""),
            "negative_prompt": prompts.get("negative", "low quality, bad anatomy, extra fingers, extra limbs, blurry, watermark, text"),
            "width": 1024,
            "height": 1024,
            "batch_size": image_count,
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
        for idx, b64 in enumerate(images[:image_count], start=1):
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

    def _strip_sd_prompt_guidance(self, text):
        """Remove template/helper prose that some models echo before real SD prompts."""
        if not text:
            return ""
        lines = str(text).splitlines()
        cleaned = []
        guidance_patterns = [
            r"^\s*positive\s+and\s+negative\s+prompts\s+for\s+image\s+generation\b",
            r"^\s*positive\s+order\s*:",
            r"^\s*order\s*:\s*subject\s*[→>\-]",
            r"^\s*subject\s*[→>\-]\s*traits\s*[→>\-]",
            r"^\s*comma[-\s]*separated\s+visual\s+descriptors\b",
            r"^\s*optional\s+image\s+prompt\b",
            r"^\s*disabled\s+by\s+default\b",
            r"^\s*low\s+quality,\s*bad\s+anatomy,\s*blurry,\s*watermark,\s*text\s*$",
        ]
        for raw in lines:
            line = raw.strip()
            if not line:
                cleaned.append(raw)
                continue
            if any(re.search(pat, line, re.I) for pat in guidance_patterns):
                continue
            cleaned.append(raw)
        out = "\n".join(cleaned).strip()
        # If guidance prose appears inline before Positive Prompt, cut it away.
        m = re.search(r"(?is)(positive\s+prompt\s*[:：].*)$", out)
        if m:
            prefix = out[:m.start()].strip()
            if re.search(r"positive\s+and\s+negative\s+prompts|positive\s+order\s*:", prefix, re.I):
                out = m.group(1).strip()
        return out

    def _looks_like_divider_line(self, value):
        raw = str(value or "").strip()
        return bool(raw) and bool(re.fullmatch(r"[-_=*~]{3,}", raw))

    def _is_generic_character_name(self, value):
        cleaned = self._clean_character_name_value(value) if value else ""
        return cleaned.casefold() in {"", "character", "characters", "character card", "new character", "untitled", "unknown"}

    def _clean_character_name_value(self, value):
        """Keep the Name section/export/tab name to the actual display name only."""
        name = str(value or "").strip().strip('"“”')
        if not name:
            return ""
        name = re.sub(r"^[-*•\s]+", "", name).strip()
        before_paren = re.split(r"\s*\(", name, maxsplit=1)[0].strip()
        if before_paren and 1 <= len(before_paren) <= 80:
            name = before_paren
        name = re.split(r"\s+(?:often|usually|sometimes|also|aka|a\.k\.a\.|known as|who )\b", name, maxsplit=1, flags=re.I)[0].strip()
        name = re.split(r"\s*[,;]\s*", name, maxsplit=1)[0].strip()
        return name[:80] or str(value or "").strip()[:80]

    def _clean_name_section(self, output):
        output = output or ""
        lines = output.splitlines()
        for i, line in enumerate(lines):
            try:
                heading = self._canonical_heading_with_template(line, self.template)
            except Exception:
                heading = None
            if heading != "name":
                continue
            for j in range(i + 1, len(lines)):
                if not lines[j].strip() or self._looks_like_divider_line(lines[j]):
                    continue
                try:
                    next_heading = self._canonical_heading_with_template(lines[j], self.template)
                except Exception:
                    next_heading = None
                if next_heading:
                    return output
                cleaned = self._clean_character_name_value(lines[j])
                if cleaned and cleaned != lines[j].strip():
                    lines[j] = cleaned
                    return "\n".join(lines)
                return output
        def repl(m):
            cleaned = self._clean_character_name_value(m.group(2))
            return m.group(1) + cleaned
        new_output, count = re.subn(r"(?im)^(\s*Name\s*[:：-]\s*)(.+)$", repl, output, count=1)
        return new_output if count else output

    def _section_title_for_id(self, section_id, template=None):
        section_id = str(section_id or "").strip()
        for sec in (template or self.template or DEFAULT_TEMPLATE).get("sections", []):
            if str(sec.get("id") or "").strip() == section_id:
                title = str(sec.get("title") or "").strip()
                if title:
                    return title
        defaults = {
            "name": "Name", "description": "Description", "personality": "Personality",
            "sexual_traits": "Sexual Traits", "background": "Background", "scenario": "Scenario",
            "first_message": "First Message", "alternate_first_messages": "Alternative First Messages",
            "example_dialogues": "Example Dialogues", "lorebook": "Lorebook Entries",
            "tags": "Tags", "system_prompt": "Custom System Prompt", "state_tracking": "State Tracking",
            "stable_diffusion": "Stable Diffusion Prompt", "natural_image_prompt": "Natural English Image Prompt",
        }
        return defaults.get(section_id, section_id.replace("_", " ").title())

    def _normalise_generated_card_headings(self, output, template=None):
        """Convert model-added markdown section headers into CCF's plain section format.

        Some models return cards headed with '# Revised Character Card' and
        '## Name' / '## Stable Diffusion Prompt'. The backend can usually parse
        those, but the UI image-prompt checks historically expected plain section
        headings. Normalising here keeps revision output consistent and prevents
        image generation controls from being disabled by harmless markdown '#'.
        """
        text = str(output or "")
        if not text.strip():
            return text
        tmpl = template or self.template or DEFAULT_TEMPLATE
        wrapper_keys = {
            "revised character card", "revised card", "character card",
            "generated character card", "final character card", "updated character card",
        }
        out = []
        for raw_line in text.splitlines():
            raw = raw_line.rstrip()
            norm = self._norm_heading_key(raw)
            try:
                heading = self._canonical_heading_with_template(raw, tmpl)
            except Exception:
                heading = None
            if norm in wrapper_keys and not heading:
                continue
            if heading:
                # Avoid duplicate dividers when the model already used the CCF divider style.
                while out and not out[-1].strip():
                    out.pop()
                if out and self._looks_like_divider_line(out[-1]):
                    out.pop()
                if out:
                    out.append("")
                out.append("------------------------------------------------")
                out.append(self._section_title_for_id(heading, tmpl))
                out.append("")
                continue
            out.append(raw)
        cleaned = "\n".join(out).strip()
        # Collapse excessive blank lines introduced by normalisation without
        # touching intentional paragraph breaks too aggressively.
        cleaned = re.sub(r"(?im)^\s*#{2,6}\s*(Alternative First Message\s+\d+)\s*$", r"\1", cleaned)
        cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
        return cleaned

    def _normalise_state_tracking_body(self, value):
        """Store State Tracking in CCF's plain key/value format.

        Some models revise the whole card as Markdown and turn state fields into
        bullets ("- Starting Emotion: ...").  Parsing can tolerate that, but saved
        workspace text and Front Porch exports should stay in the app's canonical
        field format so later UI checks do not misread the section.
        """
        text = self._clean_section_text(value or "")
        if not text:
            return ""
        label_map = {
            "starting_emotion": "Starting Emotion",
            "emotion": "Starting Emotion",
            "character_emotion": "Starting Emotion",
            "current_objective": "Current Objective",
            "objective": "Current Objective",
            "current_task": "Current Objective",
            "short_term_bond": "Short-Term Bond",
            "short-term_bond": "Short-Term Bond",
            "short term bond": "Short-Term Bond",
            "long_term_bond": "Long-Term Bond",
            "long-term_bond": "Long-Term Bond",
            "long term bond": "Long-Term Bond",
            "trust_level": "Trust Level",
            "trust level": "Trust Level",
            "time_of_day": "Time of Day",
            "time of day": "Time of Day",
            "day_of_week": "Day of Week",
            "day of week": "Day of Week",
            "weekday": "Day of Week",
            "starting_weekday": "Day of Week",
            "starting_day_of_week": "Day of Week",
            "day_number": "Day Number",
            "day number": "Day Number",
            "day_count": "Day Number",
            "emotion_intensity": "Emotion Intensity",
            "emotion intensity": "Emotion Intensity",
        }
        order = [
            "Starting Emotion", "Current Objective", "Short-Term Bond", "Long-Term Bond",
            "Trust Level", "Time of Day", "Day of Week", "Day Number", "Emotion Intensity",
        ]
        values = {}
        extras = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            stripped = re.sub(r"^\s*[-*•]+\s*", "", stripped).strip()
            stripped = re.sub(r"^\s*\d+[.)]\s*", "", stripped).strip()
            if not stripped or ":" not in stripped:
                extras.append(stripped)
                continue
            key, val = stripped.split(":", 1)
            key_norm = re.sub(r"\s+", "_", key.strip().lower().replace("-", "_"))
            key_loose = re.sub(r"\s+", " ", key.strip().lower().replace("_", " ").replace("-", " ")).strip()
            label = label_map.get(key_norm) or label_map.get(key_loose)
            if label:
                values[label] = val.strip()
            else:
                # Unknown state fields are still valid user data; just remove the bullet.
                clean_key = key.strip().strip("-*• ")
                extras.append(f"{clean_key}: {val.strip()}".strip())
        lines = [f"{label}: {values[label]}" for label in order if values.get(label)]
        for extra in extras:
            if extra and extra not in lines:
                lines.append(extra)
        return "\n".join(lines).strip()

    def _normalise_tags_body(self, value):
        text = self._clean_section_text(value or "")
        if not text:
            return ""
        pieces = []
        for raw_line in text.splitlines():
            line = re.sub(r"^\s*[-*•]+\s*", "", raw_line.strip())
            if line:
                pieces.extend(re.split(r"[,;]+", line))
        tags = self._clean_character_tags(pieces)
        return ", ".join(tags) if tags else text.strip()

    def _normalise_structured_section_bodies(self, output, template=None):
        text = str(output or "")
        tmpl = template or self.template or DEFAULT_TEMPLATE
        parsed = self._parse_sections(text, tmpl)
        state = parsed.get("state_tracking") or self._section(text, "State Tracking")
        if state:
            cleaned_state = self._normalise_state_tracking_body(state)
            if cleaned_state and cleaned_state.strip() != state.strip():
                text = self._replace_section_body(text, "state_tracking", cleaned_state, template=tmpl, title_fallback="State Tracking")
        tags = parsed.get("tags") or self._section(text, "Tags")
        if tags:
            cleaned_tags = self._normalise_tags_body(tags)
            if cleaned_tags and cleaned_tags.strip() != tags.strip():
                text = self._replace_section_body(text, "tags", cleaned_tags, template=tmpl, title_fallback="Tags")
        return text.strip()

    def _normalise_card_output_for_save(self, output, template=None):
        """Canonicalise card text before saving/exporting.

        The editor should never persist model-added Markdown wrappers or '#'
        section headings as the project source of truth.  Keep the content, but
        store sections using CCF divider headings and clean key/value sections.
        """
        text = self._clean_generated_output(output or "")
        text = self._normalise_structured_section_bodies(text, template or self.template)
        return text.strip()

    def _clean_generated_output(self, output):
        """Final output cleanup for known prompt/template leakage without removing features."""
        if not output:
            return output
        template = self.template or DEFAULT_TEMPLATE
        text = self._normalise_generated_card_headings(self._clean_name_section(str(output)), template)
        text = self._normalise_structured_section_bodies(text, template)
        parsed = self._parse_sections(text, template)
        sd_body = parsed.get("stable_diffusion") or self._section(text, "Stable Diffusion Prompt")
        if not sd_body:
            return text
        cleaned_sd = self._strip_sd_prompt_guidance(sd_body)
        if cleaned_sd.strip() == sd_body.strip():
            return text
        new_text = self._replace_section_body(text, "stable_diffusion", cleaned_sd.strip(), template=template, title_fallback="Stable Diffusion Prompt")
        return new_text if new_text else text

    def _extract_sd_prompts(self, output):
        section = self._clean_section_text(self._section(output, "Stable Diffusion Prompt"))
        section = self._strip_sd_prompt_guidance(section)
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
        positive = self._normalise_sd_prompt_items(positive, max_items=140, max_chars=2200)
        negative = self._normalise_sd_prompt_items(negative, max_items=40, max_chars=900)
        if not negative and positive:
            negative = self._default_sd_negative_prompt()
        return {"positive": positive, "negative": negative}

    def _strip_stable_diffusion_for_card(self, output):
        """Keep raw card useful but do not embed SD prompt text in card PNG/JSON."""
        lines = []
        current = None
        for line in (output or "").splitlines():
            heading = self._canonical_heading(line)
            if heading:
                current = heading
            if current in {"stable_diffusion", "natural_image_prompt"}:
                continue
            lines.append(line)
        return self._clean_section_text("\n".join(lines))

    def _safe_slug(self, value):
        value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "character_card")).strip("_")
        return value or "character_card"

    def _character_export_dir(self, name):
        safe = self._safe_slug(name)
        folder = EXPORT_DIR / safe
        _safe_mkdir(folder)
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
        # This is an internal helper request. Never stream its JSON into the
        # Q&A or Full Text Output boxes.
        prompt_settings = {**settings, "_streamTarget": "", "streamAi": False}
        raw = self._chat(prompt, prompt_settings)
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

    def _build_emotion_prompts(self, output, emotions, settings, style="sd"):
        base = self._extract_character_visual_baseline(output)
        if style == "natural":
            natural_base = self._build_natural_image_prompt_body(output, settings=settings, model=(settings or {}).get("imageModel") or "")
            prompts = {}
            for emo in emotions:
                prompts[emo] = {
                    "prompt": (natural_base + f"\n\nKeep the same character identity, hairstyle, outfit, body type, age, and overall {self._image_visual_style_phrase(settings)} style. Express {emo} clearly through facial expression, body language, and subtle posing. Use a focused single-character portrait composition.").strip(),
                    "negative": "",
                }
            return prompts
        try:
            return self._generate_emotion_prompts_via_llm(output, emotions, settings)
        except Exception:
            prompts = {}
            for emo in emotions:
                prompts[emo] = {
                    "positive": self._emotion_positive_fallback(base.get("positive", ""), emo),
                    "negative": base.get("negative", self._default_sd_negative_prompt()),
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

    def _generate_api_single_image(self, prompt, merged_settings, model, resolution, style, negative_prompt="", emotion_label="image"):
        prompt_text = str(prompt or "").strip()
        negative_text = str(negative_prompt or "").strip()
        if style == "sd" and negative_text:
            prompt_text = f"{prompt_text}\nNegative prompt: {negative_text}".strip()
        # Natural-English image models are sensitive to filter-triggering negative lists.
        # Keep natural prompts positive-only; do not append SD-style negative prompt words.
        base = self._image_api_base_url(merged_settings)
        endpoints = self._api_image_generation_endpoints(base)
        payloads = self._api_image_generation_payloads(model, prompt_text, 1, resolution, style, base)
        key = self._image_api_key(merged_settings)
        last_error = ""
        first_meaningful_error = ""
        errors = []
        for endpoint in endpoints:
            for payload in payloads:
                req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST")
                req.add_header("Content-Type", "application/json")
                req.add_header("Accept", "application/json, image/png, image/jpeg, image/webp")
                if key:
                    req.add_header("Authorization", f"Bearer {key}")
                    req.add_header("x-api-key", key)
                try:
                    with self._urlopen_with_retries(req, merged_settings, timeout=900, label="API image generation") as resp:
                        raw = resp.read()
                        content_type = resp.headers.get("Content-Type", "") if getattr(resp, "headers", None) else ""
                    blobs = self._api_image_response_blobs(raw, content_type)
                    if blobs:
                        return blobs[0]
                    last_error = f"{endpoint}: API returned no parseable image data."
                    errors.append(last_error)
                    if not first_meaningful_error:
                        first_meaningful_error = last_error
                except urllib.error.HTTPError as e:
                    body = self._clean_api_image_http_error_body(e.read().decode("utf-8", errors="replace"))
                    last_error = f"{endpoint} HTTP {e.code}: {body}"
                    errors.append(last_error)
                    if e.code != 404 and body != "HTML 404/page response" and not first_meaningful_error:
                        first_meaningful_error = last_error
                    if e.code == 404:
                        break
                    continue
                except Exception as e:
                    last_error = str(e)
                    errors.append(last_error)
                    if not first_meaningful_error:
                        first_meaningful_error = last_error
                    continue
        shown_error = first_meaningful_error or last_error
        self._log_event("api_single_image_generation_failed", {"model": model, "emotion": emotion_label, "endpointsTried": endpoints, "payloadsTried": payloads, "errors": errors[-12:], "lastError": last_error, "shownError": shown_error})
        raise RuntimeError(f"API image generation failed for {emotion_label}: {shown_error}. Tried: {', '.join(endpoints)}")

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
        provider = str(merged_settings.get("imageGenerationProvider") or "sd").strip().lower()
        model = str(merged_settings.get("imageModel") or "").strip()
        style = self._api_image_prompt_style(merged_settings, model) if provider == "api" else "sd"
        self._emit_frontend_event("ccfEmotionProgress", {"phase": "prompts", "message": "Generating emotion prompts…"})
        prompts = self._build_emotion_prompts(output, emotions, merged_settings, style=style)
        image_backend_label = "API image model…" if provider == "api" else "SD Forge / Automatic1111…"
        self._emit_frontend_event("ccfEmotionProgress", {"phase": "images", "message": f"Generating emotion images with {image_backend_label}"})
        resolution = str(merged_settings.get("imageResolution") or "1024x1024").strip() or "1024x1024"
        name = self._extract_name(output) or "character_card"
        folder = self._extract_emotion_images_dir(name)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        results = []
        prompt_manifest = {}
        for emo in emotions:
            try:
                self._raise_if_cancelled()
                self._emit_frontend_event("ccfEmotionProgress", {"phase": "images", "emotion": emo, "message": f"Generating {emo}.png…"})
                emo_prompts = prompts.get(emo, {})
                prompt_manifest[emo] = emo_prompts
                if provider == "api":
                    prompt_value = emo_prompts.get("prompt", "") if style == "natural" else emo_prompts.get("positive", "")
                    negative_value = emo_prompts.get("negative", self._default_sd_negative_prompt())
                    raw = self._generate_api_single_image(prompt_value, merged_settings, model, resolution, style, negative_value, emo)
                else:
                    prompt_value = emo_prompts.get("positive", "")
                    negative_value = emo_prompts.get("negative", self._default_sd_negative_prompt())
                    raw = self._generate_sd_single_image(prompt_value, negative_value, merged_settings, emo)
                file_path = folder / f"{emo}.png"
                file_path.write_bytes(raw)
                image_item = {
                    "emotion": emo,
                    "path": str(file_path),
                    "dataUrl": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                    "prompt": prompt_value,
                    "negativePrompt": negative_value,
                }
                results.append(image_item)
                self._emit_frontend_event("ccfEmotionImageGenerated", image_item)
            except Exception as e:
                if "cancelled" in str(e).lower():
                    return {"ok": False, "cancelled": True, "error": str(e), "images": results, "folder": str(folder)}
                return {"ok": False, "error": str(e), "images": results, "folder": str(folder)}
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
        provider = str(merged_settings.get("imageGenerationProvider") or "sd").strip().lower()
        model = str(merged_settings.get("imageModel") or "").strip()
        style = self._api_image_prompt_style(merged_settings, model) if provider == "api" else "sd"
        resolution = str(merged_settings.get("imageResolution") or "1024x1024").strip() or "1024x1024"
        try:
            if provider == "api":
                raw = self._generate_api_single_image(prompt, merged_settings, model, resolution, style, negative_prompt, emotion)
            else:
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


    def _front_porch_paths(self, settings=None, target=None):
        # Current UI settings should win over older saved workspace settings.
        settings = self._normalise_settings({**self.settings, **(settings or {})})
        selected_target = str(target or settings.get("frontPorchExportTarget") or "stable").strip().lower()
        if selected_target not in {"stable", "beta"}:
            selected_target = "stable"

        folder_key = "frontPorchBetaDataFolder" if selected_target == "beta" else "frontPorchStableDataFolder"
        raw_root = str(settings.get(folder_key) or "").strip().strip('"').strip("'")
        if not raw_root:
            # Legacy fallback for settings created before stable/beta folders existed.
            raw_root = str(settings.get("frontPorchDataFolder") or "").strip().strip('"').strip("'")
        if not raw_root:
            label = "Beta" if selected_target == "beta" else "Stable"
            return None, None, f"{label} Front Porch Data Folder is not set. Set it in Settings first.", selected_target

        expected_db_name = "front_porch_beta.db" if selected_target == "beta" else "front_porch.db"
        label = "Beta" if selected_target == "beta" else "Stable"
        root = Path(raw_root).expanduser()
        candidates = []

        def add_candidate(path):
            path = Path(path).expanduser()
            if path not in candidates:
                candidates.append(path)

        # Accept selecting the database file itself, but make the stable/beta target explicit
        # so the exporter cannot quietly write to the wrong Front Porch install.
        if root.suffix.lower() == ".db":
            db = root
            if db.exists() and db.name == expected_db_name:
                return db.parent, db, "", selected_target
            if db.exists() and db.name in {"front_porch_beta.db", "front_porch.db"}:
                return None, None, f"Selected {label} target expects {expected_db_name}, but the selected database is {db.name}. Change the export target or choose the matching database.", selected_target
            add_candidate(root.parent)

        # User normally selects the Front Porch data folder, which contains KoboldManager.
        add_candidate(root / "KoboldManager")
        # Also support selecting KoboldManager directly.
        add_candidate(root)
        # A few systems may expose the data root one level up/down or via a symlink.
        add_candidate(root.resolve() / "KoboldManager" if root.exists() else root / "KoboldManager")
        add_candidate(root.resolve() if root.exists() else root)

        checked = []
        found_other = []
        for km in candidates:
            if not km.exists() or not km.is_dir():
                checked.append(str(km))
                continue
            expected = km / expected_db_name
            checked.append(str(expected))
            if expected.exists():
                return km, expected, "", selected_target
            other_name = "front_porch.db" if selected_target == "beta" else "front_porch_beta.db"
            other = km / other_name
            checked.append(str(other))
            if other.exists():
                found_other.append(str(other))

        payload = {"target": selected_target, "raw_root": raw_root, "expectedDb": expected_db_name, "foundOther": found_other[:10], "checked": checked[:20]}
        self._log_event("front_porch_scan_not_found", payload)
        if found_other:
            return None, None, f"{label} export target expects {expected_db_name}, but only found the other Front Porch database: {found_other[0]}. Switch the export target or set the matching {label} data folder.", selected_target
        return None, None, f"Could not find {expected_db_name}. Set the {label} Front Porch Data Folder to the folder shown in that Front Porch version's Settings, or select its KoboldManager folder/database directly. Checked: " + "; ".join(checked[:6]), selected_target

    def scan_front_porch_folder(self, settings=None, *args, target=None):
        """Locate the selected Front Porch database quickly.

        Keep this bridge method tolerant of older/newer frontend calls.  PyWebView
        reports confusing positional-argument errors when the JS side calls an
        exposed method with an extra argument, so beta29 accepts optional *args
        and also reads the target from the settings payload.  The actual scan is
        intentionally shallow: it only checks the expected db path candidates.
        Export still performs any deeper database work.
        """
        if target is None and args:
            target = args[0]
        if isinstance(settings, dict) and not target:
            target = settings.get("frontPorchExportTarget")
        km, db, err, selected_target = self._front_porch_paths(settings, target=target)
        if err:
            return {"ok": False, "error": err, "target": selected_target}
        try:
            chars_dir = km / "Characters"
            payload = {
                "ok": True,
                "koboldManager": str(km),
                "database": str(db),
                "charactersDir": str(chars_dir),
                "databaseName": db.name,
                "target": selected_target,
                "targetLabel": ("Beta" if selected_target == "beta" else "Stable"),
                "charactersDirExists": chars_dir.exists(),
            }
            payload.update(self._front_porch_database_schema_summary(db))
            self._log_event("front_porch_scan_success", payload)
            return payload
        except Exception as e:
            return {"ok": False, "error": f"Could not inspect Front Porch folder: {e}", "target": selected_target}


    def _front_porch_json_value(self, value, default=None):
        if default is None:
            default = []
        if value is None:
            return copy.deepcopy(default)
        if isinstance(value, (list, dict)):
            return value
        s = str(value or "").strip()
        if not s:
            return copy.deepcopy(default)
        try:
            parsed = json.loads(s)
            return parsed
        except Exception:
            if isinstance(default, list):
                return [item.strip() for item in re.split(r"[,\n]", s) if item.strip()]
            return copy.deepcopy(default)

    def _front_porch_character_image_path(self, km, image_path):
        raw = str(image_path or "").strip()
        if not raw:
            return ""
        p = Path(raw).expanduser()
        if p.is_absolute() and p.exists():
            return str(p)
        chars_dir = Path(km) / "Characters"
        candidates = [chars_dir / raw, Path(km) / raw]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return str(candidate)
            except Exception:
                pass
        return str(candidates[0])

    def _front_porch_session_state_tracking_text(self, cursor, character_id):
        try:
            columns = self._sqlite_table_columns(cursor, "sessions")
            if not columns or "character_id" not in columns:
                return ""
            select_cols = [c for c in [
                "character_emotion", "emotion_intensity", "affection_score", "long_term_score",
                "trust_level", "time_of_day", "day_count", "start_day_of_week", "realism_enabled",
                "nsfw_cooldown_enabled", "passage_of_time_enabled", "chaos_mode_enabled"
            ] if c in columns]
            if not select_cols:
                return ""
            order_col = "updated_at" if "updated_at" in columns else ("created_at" if "created_at" in columns else "id")
            q = ", ".join(select_cols)
            row = cursor.execute(f"SELECT {q} FROM sessions WHERE character_id = ? AND (deleted_at IS NULL OR deleted_at = 0 OR deleted_at = '') ORDER BY {order_col} DESC LIMIT 1", (character_id,)).fetchone() if "deleted_at" in columns else cursor.execute(f"SELECT {q} FROM sessions WHERE character_id = ? ORDER BY {order_col} DESC LIMIT 1", (character_id,)).fetchone()
            if not row:
                return ""
            data = {select_cols[i]: row[i] for i in range(len(select_cols))}
            lines = []
            if data.get("character_emotion") not in (None, ""):
                lines.append(f"Starting Emotion: {data.get('character_emotion')}")
            if data.get("affection_score") not in (None, ""):
                lines.append(f"Short-Term Bond: {data.get('affection_score')}")
            if data.get("long_term_score") not in (None, ""):
                lines.append(f"Long-Term Bond: {data.get('long_term_score')}")
            if data.get("trust_level") not in (None, ""):
                lines.append(f"Trust Level: {data.get('trust_level')}")
            if data.get("time_of_day") not in (None, ""):
                lines.append(f"Time of Day: {data.get('time_of_day')}")
            if data.get("start_day_of_week") not in (None, ""):
                lines.append(f"Day of Week: {data.get('start_day_of_week')}")
            if data.get("day_count") not in (None, ""):
                lines.append(f"Day Number: {data.get('day_count')}")
            if data.get("emotion_intensity") not in (None, ""):
                lines.append(f"Emotion Intensity: {data.get('emotion_intensity')}")
            return "\n".join(lines).strip()
        except Exception as e:
            self._log_event("front_porch_session_state_read_failed", {"characterId": character_id, "error": str(e)})
            return ""

    def _front_porch_character_payload_from_row(self, cursor, row, km):
        data = dict(row or {})
        character_id = str(data.get("id") or "")
        alt = self._front_porch_json_value(data.get("alternate_greetings"), [])
        if not isinstance(alt, list):
            alt = []
        tags = self._front_porch_json_value(data.get("tags"), [])
        if not isinstance(tags, list):
            tags = []
        lorebook = self._front_porch_json_value(data.get("lorebook"), {"entries": []})
        if not isinstance(lorebook, dict):
            lorebook = {"entries": []}
        extensions = {}
        state_text = self._front_porch_session_state_tracking_text(cursor, character_id)
        if state_text:
            extensions["state_tracking"] = state_text
        card_data = {
            "name": str(data.get("name") or "Character"),
            "description": str(data.get("description") or ""),
            "personality": str(data.get("personality") or ""),
            "scenario": str(data.get("scenario") or ""),
            "first_mes": str(data.get("first_message") or data.get("first_mes") or ""),
            "mes_example": str(data.get("mes_example") or ""),
            "system_prompt": str(data.get("system_prompt") or ""),
            "post_history_instructions": str(data.get("post_history_instructions") or ""),
            "alternate_greetings": [str(x) for x in alt if str(x).strip()],
            "tags": [str(x) for x in tags if str(x).strip()],
            "character_book": lorebook,
            "extensions": extensions,
        }
        return {"spec": "chara_card_v2", "spec_version": "2.0", "data": card_data}

    def list_front_porch_characters(self, settings=None, target=None, *args):
        if target is None and args:
            target = args[0]
        if isinstance(settings, dict) and not target:
            target = settings.get("frontPorchExportTarget")
        km, db, err, selected_target = self._front_porch_paths(settings, target=target)
        if err:
            return {"ok": False, "error": err, "target": selected_target, "characters": []}
        con = None
        try:
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            tables = {str(r[0]) for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "characters" not in tables:
                return {"ok": False, "error": f"{db.name} does not contain a characters table.", "target": selected_target, "characters": []}
            cols = self._sqlite_table_columns(cur, "characters")
            wanted = [c for c in ["id", "name", "image_path", "tags", "created_at", "updated_at", "deleted_at", "folder_id"] if c in cols]
            if not wanted:
                return {"ok": False, "error": "Characters table exists but has no readable columns.", "target": selected_target, "characters": []}
            where = ""
            if "deleted_at" in cols:
                where = " WHERE deleted_at IS NULL OR deleted_at = 0 OR deleted_at = ''"
            order = "updated_at" if "updated_at" in cols else ("created_at" if "created_at" in cols else "name")
            rows = cur.execute(f"SELECT {', '.join(wanted)} FROM characters{where} ORDER BY {order} DESC").fetchall()
            sessions_cols = self._sqlite_table_columns(cur, "sessions") if "sessions" in tables else set()
            avatar_cols = self._sqlite_table_columns(cur, "avatar_images") if "avatar_images" in tables else set()
            group_refs = {}
            gm_cols = self._sqlite_table_columns(cur, "group_members") if "group_members" in tables else set()
            for ref_col in ["character_id", "source_character_id", "original_character_id"]:
                if ref_col in gm_cols:
                    try:
                        for cid, count in cur.execute(f"SELECT {ref_col}, COUNT(*) FROM group_members WHERE {ref_col} IS NOT NULL AND {ref_col} != '' GROUP BY {ref_col}").fetchall():
                            group_refs[str(cid)] = group_refs.get(str(cid), 0) + int(count or 0)
                    except Exception:
                        pass
            out = []
            for row in rows:
                item = {k: row[k] for k in row.keys()}
                cid = str(item.get("id") or "")
                item["target"] = selected_target
                item["targetLabel"] = "Beta" if selected_target == "beta" else "Stable"
                item["imageFile"] = self._front_porch_character_image_path(km, item.get("image_path"))
                item["tagsList"] = self._front_porch_json_value(item.get("tags"), []) if "tags" in item else []
                item["sessionCount"] = 0
                item["avatarCount"] = 0
                item["groupReferenceCount"] = group_refs.get(cid, 0)
                if "sessions" in tables and "character_id" in sessions_cols:
                    try:
                        item["sessionCount"] = int(cur.execute("SELECT COUNT(*) FROM sessions WHERE character_id = ?", (cid,)).fetchone()[0] or 0)
                    except Exception:
                        pass
                if "avatar_images" in tables and "character_id" in avatar_cols:
                    try:
                        item["avatarCount"] = int(cur.execute("SELECT COUNT(*) FROM avatar_images WHERE character_id = ?", (cid,)).fetchone()[0] or 0)
                    except Exception:
                        pass
                out.append(item)
            con.close()
            self._log_event("front_porch_characters_listed", {"target": selected_target, "db": str(db), "count": len(out)})
            return {"ok": True, "target": selected_target, "targetLabel": ("Beta" if selected_target == "beta" else "Stable"), "database": str(db), "koboldManager": str(km), "count": len(out), "characters": out}
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Could not list Front Porch characters: {e}", "target": selected_target, "characters": []}

    def load_front_porch_character(self, character_id, settings=None, target=None, *args):
        if target is None and args:
            target = args[0]
        character_id = str(character_id or "").strip()
        if not character_id:
            return {"ok": False, "error": "Select a Front Porch character to import."}
        km, db, err, selected_target = self._front_porch_paths(settings, target=target)
        if err:
            return {"ok": False, "error": err, "target": selected_target}
        con = None
        try:
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cols = self._sqlite_table_columns(cur, "characters")
            if not cols:
                return {"ok": False, "error": f"{db.name} does not contain a readable characters table."}
            wanted = [c for c in ["id", "name", "description", "personality", "scenario", "first_message", "first_mes", "mes_example", "system_prompt", "post_history_instructions", "alternate_greetings", "tags", "image_path", "lorebook", "created_at", "updated_at", "deleted_at"] if c in cols]
            row = cur.execute(f"SELECT {', '.join(wanted)} FROM characters WHERE id = ? LIMIT 1", (character_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "Front Porch character was not found. Refresh the list and try again."}
            row_dict = {k: row[k] for k in row.keys()}
            payload = self._front_porch_character_payload_from_row(cur, row_dict, km)
            output = self._build_raw_card_from_chara_v2(payload)
            image_path = self._front_porch_character_image_path(km, row_dict.get("image_path"))
            con.close()
            name = (payload.get("data") or {}).get("name") or "Character"
            self._log_event("front_porch_character_loaded", {"target": selected_target, "db": str(db), "id": character_id, "name": name, "image": image_path})
            return {"ok": True, "loadedType": f"front_porch_{selected_target}", "concept": "", "output": output, "settings": self.settings, "template": self.template, "imagePath": image_path, "sourcePath": str(db), "frontPorchCharacterId": character_id, "name": name, "message": f"Loaded {name} from {('Beta' if selected_target == 'beta' else 'Stable')} Front Porch."}
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Could not import Front Porch character: {e}", "target": selected_target}

    def delete_front_porch_characters(self, character_ids, settings=None, target=None, *args):
        if target is None and args:
            target = args[0]
        if isinstance(character_ids, str):
            character_ids = [character_ids]
        ids = [str(x or "").strip() for x in (character_ids or []) if str(x or "").strip()]
        ids = list(dict.fromkeys(ids))
        if not ids:
            return {"ok": False, "error": "Select at least one Front Porch character to delete."}
        km, db, err, selected_target = self._front_porch_paths(settings, target=target)
        if err:
            return {"ok": False, "error": err, "target": selected_target}
        con = None
        try:
            backup_path = self._create_front_porch_db_backup(db, km, reason="character_delete", keep=10)
        except Exception as e:
            return {"ok": False, "error": f"Could not create capped database backup before delete: {e}"}
        try:
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            tables = {str(r[0]) for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "characters" not in tables:
                return {"ok": False, "error": f"{db.name} does not contain a characters table."}
            char_cols = self._sqlite_table_columns(cur, "characters")
            sel_cols = [c for c in ["id", "name", "image_path"] if c in char_cols]
            qmarks = ",".join(["?"] * len(ids))
            rows = cur.execute(f"SELECT {', '.join(sel_cols)} FROM characters WHERE id IN ({qmarks})", ids).fetchall()
            found = [{k: r[k] for k in r.keys()} for r in rows]
            found_ids = [str(r.get("id") or "") for r in found]
            if not found_ids:
                return {"ok": False, "error": "None of the selected characters were found. Refresh the list and try again."}
            qmarks_found = ",".join(["?"] * len(found_ids))
            session_ids = []
            if "sessions" in tables:
                session_cols = self._sqlite_table_columns(cur, "sessions")
                if "character_id" in session_cols:
                    try:
                        session_ids = [str(r[0]) for r in cur.execute(f"SELECT id FROM sessions WHERE character_id IN ({qmarks_found})", found_ids).fetchall() if str(r[0]).strip()]
                    except Exception:
                        session_ids = []
            deleted_messages = 0
            if session_ids and "messages" in tables:
                qm = ",".join(["?"] * len(session_ids))
                try:
                    deleted_messages = cur.execute(f"DELETE FROM messages WHERE session_id IN ({qm})", session_ids).rowcount or 0
                except Exception:
                    deleted_messages = 0
            deleted_sessions = 0
            if session_ids and "sessions" in tables:
                qm = ",".join(["?"] * len(session_ids))
                try:
                    deleted_sessions = cur.execute(f"DELETE FROM sessions WHERE id IN ({qm})", session_ids).rowcount or 0
                except Exception:
                    deleted_sessions = 0
            deleted_avatars = 0
            if "avatar_images" in tables:
                av_cols = self._sqlite_table_columns(cur, "avatar_images")
                if "character_id" in av_cols:
                    try:
                        deleted_avatars = cur.execute(f"DELETE FROM avatar_images WHERE character_id IN ({qmarks_found})", found_ids).rowcount or 0
                    except Exception:
                        deleted_avatars = 0
            deleted_group_members = 0
            if "group_members" in tables:
                gm_cols = self._sqlite_table_columns(cur, "group_members")
                for ref_col in ["character_id", "source_character_id", "original_character_id"]:
                    if ref_col in gm_cols:
                        try:
                            deleted_group_members += cur.execute(f"DELETE FROM group_members WHERE {ref_col} IN ({qmarks_found})", found_ids).rowcount or 0
                        except Exception:
                            pass
            deleted_characters = cur.execute(f"DELETE FROM characters WHERE id IN ({qmarks_found})", found_ids).rowcount or 0
            now = int(time.time())
            if "sync_meta" in tables:
                try:
                    cur.execute("UPDATE sync_meta SET version = version + 1, last_modified_at = ? WHERE id = 1", (now,))
                except Exception:
                    pass
            con.commit()
            con.close()
            chars_dir = Path(km) / "Characters"
            deleted_files = 0
            deleted_dirs = 0
            file_errors = []
            for row in found:
                try:
                    img = self._front_porch_character_image_path(km, row.get("image_path"))
                    if img:
                        ip = Path(img)
                        if ip.exists() and ip.is_file() and chars_dir in [ip.parent, *ip.parents]:
                            ip.unlink()
                            deleted_files += 1
                except Exception as e:
                    file_errors.append(str(e))
                try:
                    avatar_dir = self._front_porch_avatar_dir(chars_dir, row.get("name") or "")
                    if avatar_dir.exists() and avatar_dir.is_dir():
                        shutil.rmtree(avatar_dir)
                        deleted_dirs += 1
                except Exception as e:
                    file_errors.append(str(e))
            payload = {"ok": True, "target": selected_target, "targetLabel": ("Beta" if selected_target == "beta" else "Stable"), "database": str(db), "backup": str(backup_path), "requested": len(ids), "deletedCharacters": deleted_characters, "deletedSessions": deleted_sessions, "deletedMessages": deleted_messages, "deletedAvatarRows": deleted_avatars, "deletedGroupMemberRows": deleted_group_members, "deletedImageFiles": deleted_files, "deletedAvatarFolders": deleted_dirs, "fileErrors": file_errors[:10]}
            self._log_event("front_porch_characters_deleted", payload)
            return payload
        except Exception as e:
            try:
                con.rollback(); con.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Could not delete Front Porch character(s): {e}. Database backup was created at: {backup_path}", "target": selected_target}

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

    def _front_porch_asset_root_from_kobold_manager(self, km):
        """Return the Front Porch install/data root used for non-DB assets.

        The database lives in <FrontPorchRoot>/KoboldManager, but current
        Front Porch stores group-private avatar folders at
        <FrontPorchRoot>/groups/<group_id>/avatars, not under KoboldManager.
        Older CCF betas incorrectly wrote KoboldManager/groups, which left the
        DB rows valid-looking but gave Front Porch no member folders to load.
        """
        root = Path(km).expanduser()
        try:
            if root.name == "KoboldManager":
                return root.parent
        except Exception:
            pass
        return root


    def _sqlite_backup_database_file(self, db, backup_path):
        """Create a consistent SQLite backup, falling back to a file copy.

        Front Porch may be open while CCF exports.  SQLite's backup API is safer
        than a raw shutil.copy2 for WAL/active databases, but the fallback keeps
        older Python/SQLite builds working.
        """
        db = Path(db)
        backup_path = Path(backup_path)
        try:
            src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                dst = sqlite3.connect(str(backup_path), timeout=5)
                try:
                    src.backup(dst)
                    dst.commit()
                finally:
                    dst.close()
            finally:
                src.close()
            try:
                shutil.copystat(db, backup_path)
            except Exception:
                pass
        except Exception:
            try:
                if backup_path.exists():
                    backup_path.unlink()
            except Exception:
                pass
            shutil.copy2(db, backup_path)

    def _prune_front_porch_ccf_backups(self, backup_dir, db, keep=10, protect_path=None):
        """Keep CCF-created Front Porch DB backups capped so exports do not spam files.

        Only files with CCF backup markers are touched.  Front Porch's own backup
        files are deliberately left alone.
        """
        backup_dir = Path(backup_dir)
        db = Path(db)
        keep = max(1, int(keep or 10))
        patterns = [
            f"{db.stem}.ccf_*{db.suffix}",
            f"{db.name}.ccf_backup_*",
        ]
        protected = None
        if protect_path:
            try:
                protected = str(Path(protect_path).resolve())
            except Exception:
                protected = str(protect_path)
        found = []
        seen = set()
        for pattern in patterns:
            for path in backup_dir.glob(pattern):
                try:
                    key = str(path.resolve())
                except Exception:
                    key = str(path)
                if key in seen or not path.is_file():
                    continue
                seen.add(key)
                found.append(path)
        found.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        pruned = []
        kept = []
        for path in found:
            try:
                key = str(path.resolve())
            except Exception:
                key = str(path)
            if protected and key == protected:
                kept.append(path)
            elif len(kept) < keep:
                kept.append(path)
            else:
                try:
                    path.unlink()
                    pruned.append(str(path))
                except Exception as e:
                    self._log_event("front_porch_backup_prune_failed", {"path": str(path), "error": str(e)})
        return {"kept": len(kept), "pruned": pruned, "totalBefore": len(found)}

    def _create_front_porch_db_backup(self, db, km=None, reason="export", keep=10):
        """Create a capped CCF backup inside Front Porch's own backups folder.

        Previous CCF builds wrote unlimited *.ccf_backup_* files beside the live
        database.  Front Porch already has a KoboldManager/backups folder, so CCF
        now writes there and keeps only the latest CCF-created backups.
        """
        db = Path(db)
        km = Path(km) if km else db.parent
        backup_dir = km / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(reason or "export")).strip("_") or "export"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        millis = int(time.time() * 1000) % 1000
        backup_path = backup_dir / f"{db.stem}.ccf_{safe_reason}_{stamp}-{millis:03d}{db.suffix}"
        counter = 1
        while backup_path.exists():
            backup_path = backup_dir / f"{db.stem}.ccf_{safe_reason}_{stamp}-{millis:03d}_{counter}{db.suffix}"
            counter += 1
        self._sqlite_backup_database_file(db, backup_path)
        # The SQLite copy helper may preserve the source DB mtime.  Refresh the
        # new backup timestamp so pruning never treats the just-created backup
        # as an old sidecar.
        try:
            os.utime(backup_path, None)
        except Exception:
            pass
        main_prune = self._prune_front_porch_ccf_backups(backup_dir, db, keep=keep, protect_path=backup_path)
        legacy_prune = self._prune_front_porch_ccf_backups(db.parent, db, keep=keep)
        self._log_event("front_porch_db_backup", {
            "database": str(db),
            "backup": str(backup_path),
            "backupDir": str(backup_dir),
            "reason": safe_reason,
            "keep": keep,
            "pruned": main_prune.get("pruned", []) + legacy_prune.get("pruned", []),
        })
        return backup_path

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

    def _sqlite_table_columns(self, cursor, table_name):
        try:
            return {str(row[1]) for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
        except Exception:
            return set()

    def _sqlite_table_info(self, cursor, table_name):
        try:
            rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        except Exception:
            return {}
        info = {}
        for row in rows:
            # cid, name, type, notnull, dflt_value, pk
            info[str(row[1])] = {
                "type": str(row[2] or ""),
                "notnull": bool(row[3]),
                "default": row[4],
                "pk": bool(row[5]),
            }
        return info

    def _front_porch_empty_group_realism_state(self):
        """Default JSON payload for Front Porch v30 group realism fields.

        v30 stores group/member realism in sessions.group_realism_state and
        groups.default_member_realism_state. Character Card Forge does not yet
        author full Group Cards, but returning an explicit empty v30 payload keeps
        direct SQL writes self-documenting when the column exists.
        """
        return "{}"

    def _front_porch_v30_schema_summary(self, cursor):
        """Return non-fatal Front Porch v30 group realism schema details."""
        summary = {
            "groupsTable": False,
            "sessionsTable": False,
            "groupsDefaultMemberRealismState": False,
            "sessionsGroupRealismState": False,
            "compatible": False,
            "partial": False,
        }
        try:
            table_rows = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = {str(row[0]) for row in table_rows}
            summary["groupsTable"] = "groups" in tables
            summary["sessionsTable"] = "sessions" in tables
            if "groups" in tables:
                groups_info = self._sqlite_table_info(cursor, "groups")
                summary["groupsDefaultMemberRealismState"] = "default_member_realism_state" in groups_info
            if "sessions" in tables:
                sessions_info = self._sqlite_table_info(cursor, "sessions")
                summary["sessionsGroupRealismState"] = "group_realism_state" in sessions_info
            summary["compatible"] = bool(summary["groupsDefaultMemberRealismState"] and summary["sessionsGroupRealismState"])
            summary["partial"] = bool(summary["groupsDefaultMemberRealismState"] or summary["sessionsGroupRealismState"]) and not summary["compatible"]
        except Exception:
            pass
        return summary

    def _front_porch_database_schema_summary(self, db):
        """Open a Front Porch DB briefly and summarize optional schema features."""
        summary = {
            "frontPorchV30": {
                "groupsTable": False,
                "sessionsTable": False,
                "groupsDefaultMemberRealismState": False,
                "sessionsGroupRealismState": False,
                "compatible": False,
                "partial": False,
            },
            "schemaReadError": "",
        }
        try:
            con = sqlite3.connect(str(db))
            cur = con.cursor()
            summary["frontPorchV30"] = self._front_porch_v30_schema_summary(cur)
            con.close()
        except Exception as e:
            summary["schemaReadError"] = str(e)
            try:
                con.close()
            except Exception:
                pass
        return summary

    def _audit_front_porch_insert_plan(self, table_info, table_name, provided_values):
        messages = []
        columns = set(table_info.keys())
        provided = set(provided_values.keys())
        missing_expected = sorted(provided - columns)
        for col in missing_expected:
            messages.append({
                "level": "error",
                "table": table_name,
                "message": f"Missing expected column '{col}'. Character Card Forge writes this column during Front Porch export.",
            })

        for col, meta in table_info.items():
            if meta.get("pk"):
                continue
            has_default = meta.get("default") is not None
            if meta.get("notnull") and col not in provided and not has_default:
                messages.append({
                    "level": "error",
                    "table": table_name,
                    "message": f"Column '{col}' is NOT NULL with no default, but Character Card Forge does not currently provide it.",
                })

        for col, value in provided_values.items():
            meta = table_info.get(col)
            if not meta:
                continue
            if meta.get("notnull") and value is None:
                messages.append({
                    "level": "error",
                    "table": table_name,
                    "message": f"Column '{col}' is NOT NULL, but Character Card Forge currently inserts NULL for it.",
                })
        return messages

    def _audit_front_porch_insert_rollback(self, cur, tables):
        """Exercise the real Front Porch insert path inside a rollback-only transaction.

        The audit intentionally proves that the rows Character Card Forge would
        insert can be accepted by the current schema, then proves the temporary
        character/session/message/avatar rows were removed again. This is safer
        than a permanent probe insert and catches constraint issues that PRAGMA
        inspection alone cannot see.
        """
        result = {"ok": True, "inserted": False, "rolledBack": False, "cleaned": False, "details": []}
        required = {"characters", "sessions", "messages"}
        if not required.issubset(set(tables or [])):
            result["ok"] = False
            result["details"].append("Skipped rollback insert test because one or more required tables are missing.")
            return result
        stamp = int(time.time() * 1000)
        token = f"ccf_audit_{uuid.uuid4().hex}"
        char_id = token + "_character"
        session_id = token + "_session"
        message_id = token + "_message"
        avatar_id = token + "_avatar"
        now = int(time.time())
        try:
            cur.execute("SAVEPOINT ccf_audit_insert")
            cur.execute("""
                INSERT INTO characters (
                    id, name, description, personality, scenario, first_message, mes_example,
                    system_prompt, post_history_instructions, alternate_greetings, tags, image_path,
                    tts_voice, folder_id, lorebook, world_names, memory_sources, evolved_personality,
                    evolved_scenario, evolution_count, created_at, updated_at, deleted_at, prime_avatar_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, '[]', '[]', '', '', 0, ?, ?, NULL, 1)
            """, (
                char_id, "CCF Audit Temporary Character", "Temporary audit description", "Temporary audit personality",
                "Temporary audit scenario", "Temporary audit first message", "<START>\n{{char}}: Temporary audit example.",
                "", "", "[]", "[\"ccf-audit\"]", f"{token}.png", "{\"entries\":[]}", now, now,
            ))
            session_columns = [
                "id", "character_id", "group_id", "name", "description", "author_note", "author_note_depth",
                "summary", "summary_last_index", "parent_session", "fork_index", "affection_score", "relationship_tier",
                "long_term_score", "long_term_tier", "turns_since_long_term_check", "short_term_deltas_summary",
                "realism_enabled", "short_term_mood", "mood_decay_counter", "character_emotion", "emotion_intensity",
                "time_of_day", "day_count", "nsfw_cooldown_enabled", "passage_of_time_enabled", "arousal_level",
                "cooldown_turns_remaining", "trust_level", "active_fixation", "fixation_lifespan", "spatial_stance",
                "trust_repair_pending", "chaos_mode_enabled", "chaos_pressure", "evolved_personality", "evolved_scenario",
                "evolution_count", "group_evolved_personalities", "group_evolved_scenarios", "generation_settings",
                "created_at", "updated_at", "deleted_at", "user_persona_id"
            ]
            session_values = [
                session_id, char_id, None, None, None, "", 4,
                None, None, None, None, 0, 0,
                0, 0, 0, 0,
                1, 0, 0, "neutral", "low",
                "afternoon", 1, 1, 1, 0,
                0, 0, "", 0, "",
                0, 1, 0, "", "",
                0, "{}", "{}", None,
                now, now, None, None,
            ]
            sessions_columns_available = self._sqlite_table_columns(cur, "sessions")
            if "start_day_of_week" in sessions_columns_available:
                session_columns.append("start_day_of_week")
                session_values.append(0)
            if "group_realism_state" in sessions_columns_available:
                session_columns.append("group_realism_state")
                session_values.append(self._front_porch_empty_group_realism_state())
            placeholders = ", ".join(["?"] * len(session_columns))
            cur.execute(f"INSERT INTO sessions ({', '.join(session_columns)}) VALUES ({placeholders})", session_values)
            cur.execute("""
                INSERT INTO messages (id, session_id, position, sender, is_user, character_id, swipes, swipe_index, swipe_durations, metadata, swipe_metadata, updated_at, deleted_at)
                VALUES (?, ?, 0, ?, 0, NULL, ?, 0, '[0]', NULL, NULL, ?, NULL)
            """, (message_id, session_id, "CCF Audit Temporary Character", "[\"Temporary audit first message\"]", now))
            if "avatar_images" in tables:
                cur.execute("INSERT INTO avatar_images (id, character_id, filename, label, display_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (avatar_id, char_id, f"{token}.png", "neutral", 0, now))
            if "sync_meta" in tables:
                try:
                    cur.execute("UPDATE sync_meta SET version = version + 1, last_modified_at = ? WHERE id = 1", (now,))
                except Exception:
                    pass
            result["inserted"] = True
            cur.execute("ROLLBACK TO ccf_audit_insert")
            cur.execute("RELEASE ccf_audit_insert")
            result["rolledBack"] = True
            leftovers = []
            checks = [
                ("characters", "id", char_id),
                ("sessions", "id", session_id),
                ("messages", "id", message_id),
            ]
            if "avatar_images" in tables:
                checks.append(("avatar_images", "id", avatar_id))
            for table, col, value in checks:
                try:
                    count = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (value,)).fetchone()[0]
                    if count:
                        leftovers.append((table, col, value, int(count)))
                except Exception as e:
                    result["details"].append(f"Could not verify rollback cleanup for {table}: {e}")
            if leftovers:
                result["ok"] = False
                for table, col, value, count in leftovers:
                    result["details"].append(f"Rollback left {count} temporary row(s) in {table}; attempting explicit cleanup.")
                    cur.execute(f"DELETE FROM {table} WHERE {col} = ?", (value,))
                result["cleaned"] = True
            else:
                result["cleaned"] = True
                result["details"].append("Temporary character/session/message/avatar rows were rolled back and verified absent.")
            return result
        except Exception as e:
            result["ok"] = False
            result["details"].append(str(e))
            try:
                cur.execute("ROLLBACK TO ccf_audit_insert")
                cur.execute("RELEASE ccf_audit_insert")
                result["rolledBack"] = True
            except Exception:
                pass
            try:
                cur.execute("DELETE FROM avatar_images WHERE id = ? OR character_id = ?", (avatar_id, char_id))
                cur.execute("DELETE FROM messages WHERE id = ? OR session_id = ?", (message_id, session_id))
                cur.execute("DELETE FROM sessions WHERE id = ? OR character_id = ?", (session_id, char_id))
                cur.execute("DELETE FROM characters WHERE id = ?", (char_id,))
                result["cleaned"] = True
            except Exception as cleanup_error:
                result["details"].append(f"Explicit cleanup failed: {cleanup_error}")
            return result

    def audit_front_porch_database(self, settings=None, target=None, *args):
        """Read-only compatibility audit for the Front Porch SQLite schema.

        This checks the live Front Porch database against the exact tables and
        columns Character Card Forge writes during direct export. It does not
        modify the database. The goal is to catch Front Porch schema changes
        before an export creates a broken or half-imported character.
        """
        if target is None and args:
            target = args[0]
        if isinstance(settings, dict) and not target:
            target = settings.get("frontPorchExportTarget")
        km, db, err, selected_target = self._front_porch_paths(settings, target=target)
        if err:
            return {"ok": False, "error": err, "target": selected_target}

        chars_dir = km / "Characters"
        report = {
            "ok": True,
            "target": selected_target,
            "targetLabel": "Beta" if selected_target == "beta" else "Stable",
            "koboldManager": str(km),
            "database": str(db),
            "charactersDir": str(chars_dir),
            "errors": [],
            "warnings": [],
            "info": [],
            "tables": {},
        }

        def add(level, message, table=None):
            item = {"level": level, "message": message}
            if table:
                item["table"] = table
            if level == "error":
                report["errors"].append(item)
            elif level == "warning":
                report["warnings"].append(item)
            else:
                report["info"].append(item)

        try:
            con = sqlite3.connect(str(db))
            cur = con.cursor()
            table_rows = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = {str(row[0]) for row in table_rows}
            required_tables = ["characters", "sessions", "messages", "avatar_images", "sync_meta"]
            for table in required_tables:
                if table not in tables:
                    add("error", f"Required table '{table}' is missing. Front Porch export cannot safely write to this database.", table)
                    continue
                info = self._sqlite_table_info(cur, table)
                report["tables"][table] = {
                    "columns": sorted(info.keys()),
                    "columnCount": len(info),
                }
            if "groups" in tables:
                groups_info = self._sqlite_table_info(cur, "groups")
                report["tables"]["groups"] = {
                    "columns": sorted(groups_info.keys()),
                    "columnCount": len(groups_info),
                }

            v30_summary = self._front_porch_v30_schema_summary(cur)
            report["frontPorchV30"] = v30_summary
            if v30_summary.get("compatible"):
                add("info", "Front Porch v30 group realism columns detected: groups.default_member_realism_state and sessions.group_realism_state.", "groups")
            elif v30_summary.get("partial"):
                add("warning", "Partial Front Porch v30 group realism schema detected. Group realism round-tripping may be incomplete until both v30 columns exist.", "groups")
            else:
                add("info", "Front Porch v30 group realism columns were not detected. This is fine for older Front Porch versions and normal 1:1 character exports.", "groups")

            if "characters" in tables:
                character_values = {
                    "id": "", "name": "", "description": "", "personality": "", "scenario": "",
                    "first_message": "", "mes_example": "", "system_prompt": "", "post_history_instructions": "",
                    "alternate_greetings": "[]", "tags": "[]", "image_path": "", "tts_voice": None,
                    "folder_id": None, "lorebook": "{}", "world_names": "[]", "memory_sources": "[]",
                    "evolved_personality": "", "evolved_scenario": "", "evolution_count": 0,
                    "created_at": 0, "updated_at": 0, "deleted_at": None, "prime_avatar_index": 1,
                }
                for item in self._audit_front_porch_insert_plan(self._sqlite_table_info(cur, "characters"), "characters", character_values):
                    add(item["level"], item["message"], item.get("table"))

            if "sessions" in tables:
                session_values = {
                    "id": "", "character_id": "", "group_id": None, "name": None, "description": None,
                    "author_note": "", "author_note_depth": 4, "summary": None, "summary_last_index": None,
                    "parent_session": None, "fork_index": None, "affection_score": 0, "relationship_tier": 0,
                    "long_term_score": 0, "long_term_tier": 0, "turns_since_long_term_check": 0,
                    "short_term_deltas_summary": 0, "realism_enabled": 1, "short_term_mood": 0,
                    "mood_decay_counter": 0, "character_emotion": "", "emotion_intensity": "",
                    "time_of_day": "afternoon", "day_count": 1, "nsfw_cooldown_enabled": 1,
                    "passage_of_time_enabled": 1, "arousal_level": 0, "cooldown_turns_remaining": 0,
                    "trust_level": 0, "active_fixation": "", "fixation_lifespan": 0, "spatial_stance": "",
                    "trust_repair_pending": 0, "chaos_mode_enabled": 1, "chaos_pressure": 0,
                    "evolved_personality": "", "evolved_scenario": "", "evolution_count": 0,
                    "group_evolved_personalities": "{}", "group_evolved_scenarios": "{}",
                    "generation_settings": None, "created_at": 0, "updated_at": 0, "deleted_at": None,
                    "user_persona_id": None,
                }
                session_info = self._sqlite_table_info(cur, "sessions")
                if "start_day_of_week" in session_info:
                    session_values["start_day_of_week"] = 0
                    add("info", "sessions.start_day_of_week detected and will be written by Character Card Forge.", "sessions")
                else:
                    add("info", "sessions.start_day_of_week not present; export will use Front Porch legacy weekday behavior.", "sessions")
                if "group_realism_state" in session_info:
                    session_values["group_realism_state"] = self._front_porch_empty_group_realism_state()
                    add("info", "sessions.group_realism_state detected. Normal 1:1 exports write '{}' explicitly; future Group Card support can populate evolved per-member realism here.", "sessions")
                for item in self._audit_front_porch_insert_plan(session_info, "sessions", session_values):
                    add(item["level"], item["message"], item.get("table"))

            if "messages" in tables:
                message_values = {
                    "id": "", "session_id": "", "position": 0, "sender": "", "is_user": 0,
                    "character_id": None, "swipes": "[]", "swipe_index": 0, "swipe_durations": "[0]",
                    "metadata": None, "swipe_metadata": None, "updated_at": 0, "deleted_at": None,
                }
                for item in self._audit_front_porch_insert_plan(self._sqlite_table_info(cur, "messages"), "messages", message_values):
                    add(item["level"], item["message"], item.get("table"))

            if "avatar_images" in tables:
                avatar_values = {
                    "id": "", "character_id": "", "filename": "avatar.png",
                    "label": "neutral", "display_order": 0, "created_at": 0,
                }
                for item in self._audit_front_porch_insert_plan(self._sqlite_table_info(cur, "avatar_images"), "avatar_images", avatar_values):
                    add(item["level"], item["message"], item.get("table"))

            if "sync_meta" in tables:
                sync_info = self._sqlite_table_info(cur, "sync_meta")
                for col in ["id", "version", "last_modified_at"]:
                    if col not in sync_info:
                        add("error", f"sync_meta.{col} is missing. Character Card Forge cannot bump Front Porch sync metadata correctly.", "sync_meta")
                try:
                    row = cur.execute("SELECT id, version, last_modified_at FROM sync_meta WHERE id = 1").fetchone()
                    if not row:
                        add("warning", "sync_meta has no id=1 row. Export can still insert the character, but Front Porch/cloud sync may not notice the database change immediately.", "sync_meta")
                except Exception as e:
                    add("warning", f"Could not verify sync_meta id=1 row: {e}", "sync_meta")

            try:
                insert_test = self._audit_front_porch_insert_rollback(cur, tables)
                report["insertRollbackTest"] = insert_test
                if insert_test.get("cleaned"):
                    try:
                        con.commit()
                    except Exception:
                        pass
                if insert_test.get("ok"):
                    add("info", "Rollback insert test passed: temporary character/session/message/avatar rows were inserted inside a transaction, rolled back, and verified absent.", "characters")
                else:
                    add("error", "Rollback insert test failed: " + "; ".join(insert_test.get("details") or ["unknown error"]), "characters")
            except Exception as e:
                add("error", f"Rollback insert test could not run: {e}", "characters")

            try:
                char_count = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0] if "characters" in tables else 0
                report["characterCount"] = int(char_count)
            except Exception:
                report["characterCount"] = None

            con.close()
        except Exception as e:
            return {"ok": False, "error": f"Could not audit Front Porch database: {e}", "target": selected_target, "database": str(db)}

        if not chars_dir.exists():
            add("warning", f"Characters folder does not exist yet: {chars_dir}. Export will try to create it.")
        else:
            if not os.access(str(chars_dir), os.W_OK):
                add("warning", f"Characters folder may not be writable: {chars_dir}")

        report["errorCount"] = len(report["errors"])
        report["warningCount"] = len(report["warnings"])
        report["ok"] = report["errorCount"] == 0
        self._log_event("front_porch_database_audit", {
            "target": selected_target,
            "db": str(db),
            "errors": report["errorCount"],
            "warnings": report["warningCount"],
            "tables": {k: v.get("columnCount") for k, v in report["tables"].items()},
        })
        return report

    def _normalize_front_porch_start_day_of_week(self, value):
        # Front Porch schema v28: 0 = legacy/unset, 1 = Monday ... 7 = Sunday.
        raw = str(value or "").strip().lower()
        if not raw:
            return 0
        raw = re.sub(r"[^a-z0-9]+", " ", raw).strip()
        aliases = {
            "legacy": 0, "unset": 0, "unknown": 0, "none": 0,
            "monday": 1, "mon": 1,
            "tuesday": 2, "tue": 2, "tues": 2,
            "wednesday": 3, "wed": 3,
            "thursday": 4, "thu": 4, "thur": 4, "thurs": 4,
            "friday": 5, "fri": 5,
            "saturday": 6, "sat": 6,
            "sunday": 7, "sun": 7,
        }
        if raw in aliases:
            return aliases[raw]
        try:
            ivalue = int(raw)
        except Exception:
            ivalue = 0
        return max(0, min(7, ivalue))

    def export_to_front_porch(self, output, image_path=None, settings=None, project_path=None):
        if not output or not output.strip():
            return {"ok": False, "error": "Generate or load a character first."}
        output = self._normalise_card_output_for_save(output, self.template)
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        km, db, err, selected_target = self._front_porch_paths(merged_settings)
        if err:
            return {"ok": False, "error": err, "target": selected_target}
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
        original_image_path = str(image_path or "").strip()
        local_image_path = self._resolve_front_porch_export_image(original_image_path, project_path=project_path, reason="front_porch_export")
        if not local_image_path:
            self._log_event("front_porch_export_image_missing_placeholder_allowed", {"name": name, "project": str(project_path or ""), "target": selected_target})
        try:
            self._write_chara_png(image_dest, card_v2, local_image_path, require_image=False)
        except Exception as e:
            return {"ok": False, "error": f"Could not write Front Porch character card PNG: {e}"}

        # Backup DB before direct write. Store it in Front Porch's own backups folder
        # and prune old CCF backups instead of endlessly creating sidecar files.
        try:
            backup_path = self._create_front_porch_db_backup(db, km, reason="character_export", keep=10)
        except Exception as e:
            return {"ok": False, "error": f"Could not create capped database backup before export: {e}"}

        lorebook = data.get("character_book") or {"entries": []}
        tags = data.get("tags") or []
        alt = data.get("alternate_greetings") or []
        fp = self._normalise_front_porch_realism_engine((((data.get("extensions") or {}).get("front_porch") or {}).get("realism_engine") or {}))
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
            self._sqlite_insert_dynamic(cur, "characters", {
                "id": char_id,
                "name": name,
                "description": desc,
                "personality": personality,
                "scenario": scenario,
                "first_message": first_mes,
                "mes_example": mes_example,
                "system_prompt": system_prompt,
                "post_history_instructions": post,
                "alternate_greetings": json.dumps(alt, ensure_ascii=False),
                "tags": json.dumps(tags, ensure_ascii=False),
                "image_path": image_filename,
                "tts_voice": None,
                "folder_id": None,
                "lorebook": json.dumps(lorebook, ensure_ascii=False),
                "world_names": "[]",
                "memory_sources": "[]",
                "evolved_personality": "",
                "evolved_scenario": "",
                "evolution_count": 0,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
                "prime_avatar_index": 1,
            })
            session_id = str(ms + 1)
            session_values = {
                "id": session_id,
                "character_id": char_id,
                "group_id": None,
                "name": None,
                "description": None,
                "author_note": "",
                "author_note_depth": 4,
                "summary": None,
                "summary_last_index": None,
                "parent_session": None,
                "fork_index": None,
                "affection_score": int(fp.get("short_term_bond") or 0),
                "relationship_tier": 0,
                "long_term_score": int(fp.get("long_term_bond") or 0),
                "long_term_tier": 0,
                "turns_since_long_term_check": 0,
                "short_term_deltas_summary": 0,
                "realism_enabled": 1 if fp.get("enabled", True) else 0,
                "short_term_mood": 0,
                "mood_decay_counter": 0,
                "character_emotion": str(fp.get("character_emotion") or ""),
                "emotion_intensity": str(fp.get("emotion_intensity") or ""),
                "time_of_day": self._normalize_front_porch_time_of_day(fp.get("time_of_day") or "afternoon"),
                "day_count": int(fp.get("day_count") or 1),
                "nsfw_cooldown_enabled": 1 if fp.get("nsfw_cooldown_enabled", True) else 0,
                "passage_of_time_enabled": 1 if fp.get("passage_of_time_enabled", True) else 0,
                "arousal_level": 0,
                "cooldown_turns_remaining": 0,
                "trust_level": int(fp.get("trust_level") or 0),
                "active_fixation": "",
                "fixation_lifespan": 0,
                "spatial_stance": "",
                "trust_repair_pending": 0,
                "chaos_mode_enabled": 1 if fp.get("chaos_mode_enabled", True) else 0,
                "chaos_pressure": 0,
                "evolved_personality": "",
                "evolved_scenario": "",
                "evolution_count": 0,
                "group_evolved_personalities": "{}",
                "group_evolved_scenarios": "{}",
                "generation_settings": None,
                "start_day_of_week": self._normalize_front_porch_start_day_of_week(fp.get("start_day_of_week") or 0),
                "group_realism_state": self._front_porch_empty_group_realism_state(),
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
                "user_persona_id": None,
            }
            self._sqlite_insert_dynamic(cur, "sessions", session_values)
            if first_mes:
                self._sqlite_insert_dynamic(cur, "messages", {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "position": 0,
                    "sender": name,
                    "is_user": 0,
                    "character_id": None,
                    "swipes": json.dumps([first_mes], ensure_ascii=False),
                    "swipe_index": 0,
                    "swipe_durations": "[0]",
                    "metadata": None,
                    "swipe_metadata": None,
                    "updated_at": now,
                    "deleted_at": None,
                })

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
                self._sqlite_insert_dynamic(cur, "avatar_images", {
                    "id": str(uuid.uuid4()),
                    "character_id": char_id,
                    "filename": avatar_file,
                    "label": emo,
                    "display_order": emotion_count,
                    "created_at": now,
                })
                emotion_count += 1
            if "sync_meta" in {str(row[0]) for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
                try:
                    cur.execute("UPDATE sync_meta SET version = version + 1, last_modified_at = ? WHERE id = 1", (now,))
                except Exception:
                    pass
            con.commit()
            con.close()
            self._log_event("front_porch_export", {"name": name, "id": char_id, "target": selected_target, "db": str(db), "image": image_filename, "sourceImage": str(local_image_path or original_image_path or ""), "emotions": emotion_count, "avatarDir": str(char_emotion_dir), "backup": str(backup_path)})
            return {"ok": True, "name": name, "characterId": char_id, "target": selected_target, "targetLabel": ("Beta" if selected_target == "beta" else "Stable"), "database": str(db), "cardImage": str(image_dest), "emotionImages": emotion_count, "avatarDir": str(char_emotion_dir), "backup": str(backup_path)}
        except Exception as e:
            try:
                con.rollback(); con.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Front Porch export failed: {e}. Database backup was created at: {backup_path}"}

    def _sqlite_insert_dynamic(self, cursor, table_name, values):
        """Insert a row using only columns present in the target DB.

        Front Porch Group Card schemas can change, so Group Card direct export must be
        tolerant: write known columns when present and supply generic values for
        NOT NULL/no-default columns so additive schema changes do not hard-crash.
        """
        info = self._sqlite_table_info(cursor, table_name)
        if not info:
            raise ValueError(f"Required table '{table_name}' is missing or unreadable.")
        row = {}
        def fallback_value(meta):
            typ = str(meta.get("type") or "").upper()
            if "INT" in typ:
                return 0
            if "REAL" in typ or "FLOA" in typ or "DOUB" in typ:
                return 0.0
            if "BLOB" in typ:
                return b""
            return ""

        for key, value in (values or {}).items():
            if key in info:
                meta = info.get(key) or {}
                if value is None and meta.get("notnull"):
                    # Let SQLite apply a declared default when available; otherwise
                    # provide a safe generic value. This keeps direct export stable
                    # across Front Porch schema churn.
                    if meta.get("default") is not None:
                        continue
                    row[key] = fallback_value(meta)
                elif isinstance(value, (dict, list)):
                    row[key] = json.dumps(value, ensure_ascii=False)
                else:
                    row[key] = value
        for col, meta in info.items():
            if meta.get("pk") or col in row:
                continue
            if meta.get("notnull") and meta.get("default") is None:
                row[col] = fallback_value(meta)
        if not row:
            raise ValueError(f"No writable columns resolved for table '{table_name}'.")
        cols = list(row.keys())
        placeholders = ", ".join(["?"] * len(cols))
        cursor.execute(f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})", [row[c] for c in cols])

    def _json_loads_or_default(self, value, default=None):
        default = {} if default is None else default
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return copy.deepcopy(default)
            try:
                return json.loads(s)
            except Exception:
                return copy.deepcopy(default)
        if value is None:
            return copy.deepcopy(default)
        return copy.deepcopy(value)

    def _remap_json_keys(self, value, id_map):
        """Recursively remap stable-ID dictionary keys inside group state blobs."""
        if not isinstance(id_map, dict) or not id_map:
            return value
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                skey = str(key)
                new_key = id_map.get(skey, key)
                out[new_key] = self._remap_json_keys(child, id_map)
            return out
        if isinstance(value, list):
            return [self._remap_json_keys(item, id_map) for item in value]
        if isinstance(value, str):
            return id_map.get(value, value)
        return value

    def _json_string_or_default(self, value, default=None):
        default = {} if default is None else default
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return json.dumps(default, ensure_ascii=False)
            try:
                json.loads(s)
                return s
            except Exception:
                return json.dumps(default, ensure_ascii=False)
        if value is None:
            return json.dumps(default, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)

    def _uuid_like_or_new(self, value, used=None):
        used = used if isinstance(used, set) else set()
        raw = str(value or "").strip().lower()
        try:
            parsed = str(uuid.UUID(raw))
            if parsed not in used:
                used.add(parsed)
                return parsed
        except Exception:
            pass
        while True:
            candidate = str(uuid.uuid4())
            if candidate not in used:
                used.add(candidate)
                return candidate

    def _png_text_chunk(self, key, value):
        """Build a raw PNG tEXt chunk for a UTF-8/ascii text value."""
        key_b = str(key or "").encode("latin-1", "replace")
        if not key_b:
            raise ValueError("PNG text chunk key cannot be empty.")
        if b"\x00" in key_b:
            key_b = key_b.split(b"\x00", 1)[0]
        value_b = str(value or "").encode("latin-1", "replace")
        chunk_type = b"tEXt"
        chunk_data = key_b + b"\x00" + value_b
        crc = zlib.crc32(chunk_type)
        crc = zlib.crc32(chunk_data, crc) & 0xffffffff
        return struct.pack(">I", len(chunk_data)) + chunk_type + chunk_data + struct.pack(">I", crc)

    def _png_bytes_with_text_chunks(self, png_bytes, text_map):
        """Return PNG bytes guaranteed to contain the requested text chunks.

        Pillow normally writes PngInfo correctly, but this manual pass makes the
        Front Porch group-member avatar contract deterministic. If a requested
        key is missing, insert it immediately after IHDR so downstream loaders
        see the metadata before IDAT regardless of how the image was produced.
        """
        data = bytes(png_bytes or b"")
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return data
        wanted = {str(k): str(v or "") for k, v in (text_map or {}).items() if str(k or "").strip()}
        if not wanted:
            return data
        pos = 8
        existing = set()
        ihdr_end = None
        try:
            while pos + 8 <= len(data):
                length = struct.unpack(">I", data[pos:pos+4])[0]
                ctype = data[pos+4:pos+8]
                chunk_start = pos
                chunk_end = pos + 12 + length
                if chunk_end > len(data):
                    break
                chunk = data[pos+8:pos+8+length]
                if ctype == b"IHDR" and ihdr_end is None:
                    ihdr_end = chunk_end
                if ctype in (b"tEXt", b"zTXt", b"iTXt") and b"\x00" in chunk:
                    existing.add(chunk.split(b"\x00", 1)[0].decode("utf-8", "replace"))
                pos = chunk_end
                if ctype == b"IEND":
                    break
        except Exception:
            return data
        missing = [(k, v) for k, v in wanted.items() if k not in existing]
        if not missing:
            return data
        insert_at = ihdr_end if ihdr_end is not None else 8
        chunks = b"".join(self._png_text_chunk(k, v) for k, v in missing)
        return data[:insert_at] + chunks + data[insert_at:]

    def _ensure_png_text_chunks(self, path, text_map, log_reason="png_text_chunks"):
        """Mutate an existing PNG so the requested text chunks are present."""
        try:
            p = Path(path)
            before = p.read_bytes()
            after = self._png_bytes_with_text_chunks(before, text_map)
            changed = after != before
            if changed:
                p.write_bytes(after)
            try:
                keys = self._png_text_chunk_keys(p)
            except Exception:
                keys = []
            self._log_event("png_text_chunk_ensure", {
                "reason": log_reason,
                "path": str(p),
                "changed": bool(changed),
                "requestedKeys": list((text_map or {}).keys()),
                "textKeys": keys[:40],
                "sizeBefore": len(before),
                "sizeAfter": len(after),
            })
            return {"changed": changed, "textKeys": keys, "sizeBefore": len(before), "sizeAfter": len(after)}
        except Exception as e:
            self._log_event("png_text_chunk_ensure_failed", {"reason": log_reason, "path": str(path or ""), "error": str(e)})
            return {"changed": False, "error": str(e)}

    def _png_text_chunk_keys(self, path):
        """Return PNG text chunk keywords for diagnostics without dumping payloads."""
        try:
            data = Path(path).read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                return []
            pos = 8
            keys = []
            while pos + 8 <= len(data):
                length = struct.unpack(">I", data[pos:pos+4])[0]
                ctype = data[pos+4:pos+8]
                chunk = data[pos+8:pos+8+length]
                pos += 12 + length
                if ctype in (b"tEXt", b"zTXt", b"iTXt") and b"\x00" in chunk:
                    key = chunk.split(b"\x00", 1)[0].decode("utf-8", "replace")
                    keys.append(key)
                if ctype == b"IEND":
                    break
            return keys[:40]
        except Exception:
            return []

    def _png_file_diagnostics(self, path):
        """Small image diagnostics for Front Porch export logs."""
        out = {"path": str(path or ""), "exists": False}
        try:
            p = Path(path)
            out["exists"] = p.exists() and p.is_file()
            if not out["exists"]:
                return out
            out["sizeBytes"] = p.stat().st_size
            with Image.open(p) as img:
                out["width"] = img.width
                out["height"] = img.height
                out["mode"] = img.mode
            out["visibleReal"] = bool(self._png_file_has_nonblank_visible_pixels(p))
            keys = self._png_text_chunk_keys(p)
            out["textKeys"] = keys
            out["hasChara"] = "chara" in keys
            out["hasFpaGroup"] = "fpa_group" in keys
        except Exception as e:
            out["error"] = str(e)
        return out

    def _write_group_member_avatar_file(self, dest, member_data, member_id):
        """Write a group member avatar PNG with embedded Chara V2 metadata."""
        dest = Path(dest)
        _safe_mkdir(dest.parent)
        data = copy.deepcopy(member_data if isinstance(member_data, dict) else {})
        avatar_b64 = str(data.pop("avatar_base64", "") or "").strip()
        data.pop("_original_stable_id", None)
        img = None
        input_bytes = 0
        input_real = False
        input_dims = None
        if avatar_b64:
            try:
                raw = base64.b64decode(avatar_b64)
                input_bytes = len(raw)
                if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                    # Preserve visible pixels but always rewrite metadata so the
                    # private group avatar matches the group_members row.
                    img = Image.open(io.BytesIO(raw)).convert("RGBA")
                    input_dims = [img.width, img.height]
                    input_real = self._avatar_base64_has_nonblank_visible_pixels(avatar_b64)
                    if not input_real:
                        self._log_event("front_porch_group_member_avatar_is_placeholder", {"member": data.get("name"), "memberId": member_id, "inputBytes": input_bytes, "inputDims": input_dims})
            except Exception as e:
                self._log_event("front_porch_group_member_avatar_decode_failed", {"member": data.get("name"), "memberId": member_id, "error": str(e), "inputBytes": input_bytes})
                img = None
        payload = {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}
        chara_text = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
        text_chunks = {"chara": chara_text, "ccf_group_member_id": member_id}
        meta = PngInfo()
        for k, v in text_chunks.items():
            meta.add_text(k, v)
        if img is None:
            img = Image.new("RGBA", (512, 768), (24, 24, 32, 255))
        img.save(dest, "PNG", pnginfo=meta)
        # Manual safety pass: Front Porch expects private member avatars to be
        # real Chara V2 PNGs, not just ordinary image files. Guarantee the tEXt
        # chunks even if Pillow/image transformations dropped metadata.
        self._ensure_png_text_chunks(dest, text_chunks, log_reason="group_member_avatar")
        diag = self._png_file_diagnostics(dest)
        diag.update({"member": data.get("name"), "memberId": member_id, "inputBytes": input_bytes, "inputReal": bool(input_real), "inputDims": input_dims})
        self._log_event("front_porch_group_member_avatar_written", diag)
        return diag

    def export_group_card_to_front_porch_beta(self, loaded, settings=None, target=None):
        """Directly export a Front Porch Group Card project into Stable or Beta.

        Group chat support is now available in Stable Front Porch as well as Beta,
        so the selected Front Porch target controls which database/folders receive
        the group rows and avatar assets.
        """
        selected_target = str(target or (settings or {}).get("frontPorchExportTarget") or self.settings.get("frontPorchExportTarget") or "stable").strip().lower()
        if selected_target not in {"stable", "beta"}:
            selected_target = "stable"
        target_label = "Beta" if selected_target == "beta" else "Stable"
        merged_settings = {**self.settings, **(settings or {}), "frontPorchExportTarget": selected_target}
        km, db, err, selected_target = self._front_porch_paths(merged_settings, target=selected_target)
        target_label = "Beta" if selected_target == "beta" else "Stable"
        if err:
            return {"ok": False, "error": err, "target": selected_target}
        payload = self._load_group_payload_for_project(loaded)
        if not isinstance(payload, dict) or payload.get("spec") != "front_porch_group_card":
            return {"ok": False, "error": "This Group Card project is missing its fpa_group payload."}
        raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else []
        if not (2 <= len(raw_members) <= 4):
            return {"ok": False, "error": "Front Porch group cards require 2–4 embedded members."}
        member_project_paths = loaded.get("memberProjectPaths") if isinstance(loaded.get("memberProjectPaths"), list) else []
        if member_project_paths:
            payload = self._refresh_group_payload_member_avatars_from_projects(payload, member_project_paths)
            raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else raw_members
        payload = self._ensure_group_payload_avatar_chunks(payload, reason="front_porch_direct_export_payload")
        raw_members = payload.get("raw_member_data") if isinstance(payload.get("raw_member_data"), list) else raw_members
        # Keep the saved .group.png/.group.json in sync with the refreshed avatar payload.
        # Earlier builds repaired images for direct DB export only, leaving the local
        # group PNG sidecar with placeholder avatar_base64 values.
        try:
            group_card_path = str(loaded.get("groupCardPath") or "").strip()
            if group_card_path:
                cover = ""
                if raw_members:
                    cover_member = raw_members[0] if isinstance(raw_members[0], dict) else {}
                    cover_b64 = str(cover_member.get("avatar_base64") or "")
                    cover = self._ensure_local_card_image_path("data:image/png;base64," + cover_b64, "card", "front_porch_group_payload_cover") if cover_b64 else ""
                self._write_front_porch_group_png(group_card_path, payload, cover)
                sidecar = Path(group_card_path).with_suffix(".json")
                sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                self._log_event("front_porch_group_payload_persisted", {"path": group_card_path, "jsonPath": str(sidecar), "members": len(raw_members)})
        except Exception as e:
            self._log_event("front_porch_group_payload_persist_failed", {"error": str(e), "path": str(loaded.get("groupCardPath") or "")})
        try:
            backup_path = self._create_front_porch_db_backup(db, km, reason="group_export", keep=10)
        except Exception as e:
            return {"ok": False, "error": f"Could not create capped database backup before group export: {e}"}

        con = None
        try:
            con = sqlite3.connect(str(db))
            cur = con.cursor()
            tables = {str(row[0]) for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "groups" not in tables or "group_members" not in tables:
                raise ValueError(f"This {target_label} database does not expose the required groups/group_members tables yet. Update Front Porch or choose a database with group chat support.")
            try:
                groups_info = self._sqlite_table_info(cur, "groups")
                self._log_event("front_porch_groups_schema", {
                    "db": str(db),
                    "columns": list(groups_info.keys()),
                    "legacyCharacterColumns": [c for c in groups_info.keys() if c.lower() in ("character_ids", "characterids")],
                    "avatarColumns": [c for c in groups_info.keys() if any(tok in c.lower() for tok in ("avatar", "image", "cover", "thumbnail", "file"))],
                })
            except Exception as e:
                self._log_event("front_porch_groups_schema_error", {"db": str(db), "error": str(e)})
            try:
                gm_info = self._sqlite_table_info(cur, "group_members")
                self._log_event("front_porch_group_members_schema", {
                    "db": str(db),
                    "columns": list(gm_info.keys()),
                    "avatarColumns": [c for c in gm_info.keys() if any(tok in c.lower() for tok in ("avatar", "image", "file"))],
                })
            except Exception as e:
                self._log_event("front_porch_group_members_schema_error", {"db": str(db), "error": str(e)})
            now_ms = int(time.time() * 1000)
            now_sec = int(time.time())
            # Front Porch-created groups in current Front Porch use a plain
            # group_<milliseconds> id.  The extra random suffix used in beta30
            # made valid group_members rows harder for some UI paths to resolve.
            group_id = f"group_{now_ms}"
            while cur.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
                now_ms += 1
                group_id = f"group_{now_ms}"
            # group_members rows created by Front Porch's own importer currently
            # use 0 for member created/updated timestamps, while groups/sync_meta
            # use seconds.  Match that shape instead of writing millisecond values.
            now = now_sec
            member_ts = 0
            used_ids = set()
            member_rows = []
            member_ids = []
            source_character_ids = []
            source_character_rows = []
            source_session_rows = []
            source_message_rows = []
            stable_id_map = {}
            asset_root = self._front_porch_asset_root_from_kobold_manager(km)
            chars_dir = km / "Characters"
            chars_dir.mkdir(parents=True, exist_ok=True)
            # Important: Front Porch keeps group avatar folders beside
            # KoboldManager, e.g. FrontPorchAI/groups/<group_id>/avatars.
            # They are not stored in KoboldManager/groups.
            avatar_dir = asset_root / "groups" / group_id / "avatars"
            avatar_dir.mkdir(parents=True, exist_ok=True)
            if not avatar_dir.exists() or not avatar_dir.is_dir():
                raise ValueError(f"Could not create Front Porch group avatar folder: {avatar_dir}")
            if not chars_dir.exists() or not chars_dir.is_dir():
                raise ValueError(f"Could not create Front Porch Characters folder: {chars_dir}")
            existing_character_ids = {str(r[0]) for r in cur.execute("SELECT id FROM characters").fetchall()} if "characters" in tables else set()
            for idx, member in enumerate(raw_members, start=1):
                data = copy.deepcopy(member if isinstance(member, dict) else {})
                original_stable_id = str(data.get("_original_stable_id") or "").strip()
                member_name = str(data.get("name") or f"Member {idx}").strip() or f"Member {idx}"
                safe_member = self._safe_front_porch_character_folder(member_name)
                source_ms = now_ms + idx
                source_character_id = f"{safe_member}_{source_ms}"
                while source_character_id in existing_character_ids:
                    source_ms += 1000
                    source_character_id = f"{safe_member}_{source_ms}"
                existing_character_ids.add(source_character_id)
                source_character_ids.append(source_character_id)
                if original_stable_id:
                    stable_id_map[original_stable_id] = source_character_id
                stable_id_map[member_name] = source_character_id
                # Direct DB export must create the same normal character records
                # that Front Porch has available when its own group creator asks
                # you to select characters.  The private group_members rows below
                # are still the scene snapshot, but these source rows give older
                # edit/extract paths real characters to resolve instead of empty
                # or private UUID-only references.
                source_image_name = f"{source_character_id}.png"
                source_image_path = chars_dir / source_image_name
                source_card_data = copy.deepcopy(data)
                source_card_data.pop("avatar_base64", None)
                source_card_data.pop("_original_stable_id", None)
                source_card_data["name"] = member_name
                source_payload = {"spec": "chara_card_v2", "spec_version": "2.0", "data": source_card_data}
                avatar_b64 = str(data.get("avatar_base64") or "").strip()
                avatar_source = "data:image/png;base64," + avatar_b64 if avatar_b64 else ""
                self._write_chara_png(source_image_path, source_payload, avatar_source, require_image=False)
                source_ext = source_card_data.get("extensions") if isinstance(source_card_data.get("extensions"), dict) else {}
                source_fp = self._normalise_front_porch_realism_engine(((source_ext.get("front_porch") or {}).get("realism_engine") or {}) if isinstance(source_ext.get("front_porch"), dict) else {})
                source_character_rows.append({
                    "id": source_character_id,
                    "name": member_name,
                    "description": str(source_card_data.get("description") or ""),
                    "personality": str(source_card_data.get("personality") or ""),
                    "scenario": str(source_card_data.get("scenario") or ""),
                    "first_message": str(source_card_data.get("first_mes") or source_card_data.get("first_message") or ""),
                    "mes_example": str(source_card_data.get("mes_example") or ""),
                    "system_prompt": str(source_card_data.get("system_prompt") or ""),
                    "post_history_instructions": str(source_card_data.get("post_history_instructions") or ""),
                    "alternate_greetings": json.dumps(source_card_data.get("alternate_greetings") if isinstance(source_card_data.get("alternate_greetings"), list) else [], ensure_ascii=False),
                    "tags": json.dumps(source_card_data.get("tags") if isinstance(source_card_data.get("tags"), list) else [], ensure_ascii=False),
                    "image_path": source_image_name,
                    "tts_voice": source_card_data.get("tts_voice"),
                    "folder_id": None,
                    "lorebook": json.dumps(source_card_data.get("character_book") if isinstance(source_card_data.get("character_book"), dict) else {"entries": []}, ensure_ascii=False),
                    "world_names": json.dumps(source_card_data.get("world_names") if isinstance(source_card_data.get("world_names"), list) else [], ensure_ascii=False),
                    "memory_sources": "[]",
                    "evolved_personality": "",
                    "evolved_scenario": "",
                    "evolution_count": 0,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                    "prime_avatar_index": 1,
                })
                source_session_id = str(source_ms + 1)
                source_session_rows.append({
                    "id": source_session_id,
                    "character_id": source_character_id,
                    "group_id": None,
                    "name": None,
                    "description": None,
                    "author_note": "",
                    "author_note_depth": 4,
                    "summary": None,
                    "summary_last_index": None,
                    "parent_session": None,
                    "fork_index": None,
                    "affection_score": int(source_fp.get("short_term_bond") or 0),
                    "relationship_tier": 0,
                    "long_term_score": int(source_fp.get("long_term_bond") or 0),
                    "long_term_tier": 0,
                    "turns_since_long_term_check": 0,
                    "short_term_deltas_summary": 0,
                    "realism_enabled": 1 if source_fp.get("enabled", True) else 0,
                    "short_term_mood": 0,
                    "mood_decay_counter": 0,
                    "character_emotion": str(source_fp.get("character_emotion") or ""),
                    "emotion_intensity": str(source_fp.get("emotion_intensity") or ""),
                    "time_of_day": self._normalize_front_porch_time_of_day(source_fp.get("time_of_day") or "afternoon"),
                    "day_count": int(source_fp.get("day_count") or 1),
                    "nsfw_cooldown_enabled": 1 if source_fp.get("nsfw_cooldown_enabled", True) else 0,
                    "passage_of_time_enabled": 1 if source_fp.get("passage_of_time_enabled", True) else 0,
                    "arousal_level": 0,
                    "cooldown_turns_remaining": 0,
                    "trust_level": int(source_fp.get("trust_level") or 0),
                    "active_fixation": "",
                    "fixation_lifespan": 0,
                    "spatial_stance": "",
                    "trust_repair_pending": 0,
                    "chaos_mode_enabled": 1 if source_fp.get("chaos_mode_enabled", True) else 0,
                    "chaos_pressure": 0,
                    "evolved_personality": "",
                    "evolved_scenario": "",
                    "evolution_count": 0,
                    "group_evolved_personalities": "{}",
                    "group_evolved_scenarios": "{}",
                    "generation_settings": None,
                    "start_day_of_week": self._normalize_front_porch_start_day_of_week(source_fp.get("start_day_of_week") or 0),
                    "group_realism_state": self._front_porch_empty_group_realism_state(),
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                    "user_persona_id": None,
                })
                source_first = str(source_card_data.get("first_mes") or source_card_data.get("first_message") or "").strip()
                if source_first:
                    source_message_rows.append({
                        "id": str(uuid.uuid4()),
                        "session_id": source_session_id,
                        "position": 0,
                        "sender": member_name,
                        "is_user": 0,
                        "character_id": None,
                        "swipes": json.dumps([source_first], ensure_ascii=False),
                        "swipe_index": 0,
                        "swipe_durations": "[0]",
                        "metadata": None,
                        "swipe_metadata": None,
                        "updated_at": now,
                        "deleted_at": None,
                    })

                member_id = self._uuid_like_or_new("", used_ids)
                member_ids.append(member_id)
                avatar_name = f"{member_id}.png"
                # The group-member snapshot points back to the normal character
                # id used by Front Porch realism/system-prompt blobs, while the
                # row id and avatar filename stay private UUIDs.
                data["_original_stable_id"] = source_character_id
                avatar_diag = self._write_group_member_avatar_file(avatar_dir / avatar_name, data, member_id)
                ext = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}
                front_porch_ext = ext.get("front_porch") if isinstance(ext.get("front_porch"), dict) else {}
                raw_ext = copy.deepcopy(ext)
                member_rows.append({
                    "id": member_id,
                    "group_id": group_id,
                    "name": str(data.get("name") or f"Member {idx}"),
                    "description": str(data.get("description") or ""),
                    "personality": str(data.get("personality") or ""),
                    "scenario": str(data.get("scenario") or ""),
                    "first_message": str(data.get("first_mes") or data.get("first_message") or ""),
                    "mes_example": str(data.get("mes_example") or ""),
                    "system_prompt": str(data.get("system_prompt") or ""),
                    "post_history_instructions": str(data.get("post_history_instructions") or ""),
                    "alternate_greetings": json.dumps(data.get("alternate_greetings") if isinstance(data.get("alternate_greetings"), list) else [], ensure_ascii=False),
                    "tags": json.dumps(data.get("tags") if isinstance(data.get("tags"), list) else [], ensure_ascii=False),
                    "avatar_filename": avatar_name,
                    # Schema drift guard: current Front Porch docs use avatar_filename,
                    # but log/write common aliases if Front Porch changed the column name.
                    # _sqlite_insert_dynamic only writes aliases that actually exist.
                    "avatar_path": avatar_name,
                    "avatar_file": avatar_name,
                    "avatar_file_name": avatar_name,
                    "avatarFilename": avatar_name,
                    "image_path": avatar_name,
                    "image_filename": avatar_name,
                    "image": avatar_name,
                    "tts_voice": data.get("tts_voice"),
                    "lorebook": json.dumps(data.get("character_book") if isinstance(data.get("character_book"), dict) else {"entries": []}, ensure_ascii=False),
                    "world_names": json.dumps(data.get("world_names") if isinstance(data.get("world_names"), list) else [], ensure_ascii=False),
                    "front_porch_extensions": json.dumps(front_porch_ext, ensure_ascii=False),
                    "raw_extensions": json.dumps(raw_ext, ensure_ascii=False),
                    "member_state": "{}",
                    "created_at": member_ts,
                    "updated_at": member_ts,
                })

            profile = (((payload.get("extensions") or {}).get("character_card_forge") or {}).get("group_profile") or {}) if isinstance(payload.get("extensions"), dict) else {}
            if not profile and isinstance(loaded.get("groupProfile"), dict):
                profile = loaded.get("groupProfile")
            group_lorebook = payload.get("group_lorebook") if payload.get("group_lorebook") is not None else json.dumps({"entries": []}, ensure_ascii=False)
            baseline_obj = self._json_loads_or_default(payload.get("baseline_realism_state"), {})
            default_obj = self._json_loads_or_default(payload.get("default_member_realism_state") or payload.get("realism_state"), {})
            prompts_obj = self._json_loads_or_default(payload.get("character_system_prompts"), {})
            # Remap the temporary .group-card stable IDs to the real normal
            # Front Porch character IDs created above.  group_members still use
            # private UUID row IDs/avatar filenames, but the state blobs and
            # legacy character_ids column should resolve to actual characters.
            baseline_obj = self._remap_json_keys(baseline_obj, stable_id_map)
            default_obj = self._remap_json_keys(default_obj, stable_id_map)
            prompts_obj = self._remap_json_keys(prompts_obj, stable_id_map)
            baseline = self._json_string_or_default(baseline_obj, {})
            default_realism = self._json_string_or_default(default_obj, {})
            character_prompts = self._json_string_or_default(prompts_obj, {})
            group_values = {
                "id": group_id,
                "name": str(payload.get("name") or "Group Card"),
                "description": str(profile.get("group_overview") or ""),
                "scenario": str(payload.get("scenario") or ""),
                "first_message": str(payload.get("first_message") or ""),
                "system_prompt": str(payload.get("system_prompt") or ""),
                "turn_order": str(payload.get("turn_order") or "roundRobin"),
                "auto_advance": 1 if payload.get("auto_advance") else 0,
                "director_mode": 1 if payload.get("director_mode") else 0,
                # Match Front Porch-created groups: members come from
                # group_members, while the source character links live inside
                # realism/system-prompt state blobs.  Filling character_ids with
                # private/member/source IDs can make some Front Porch UI paths treat
                # the group as malformed.
                "character_ids": json.dumps([], ensure_ascii=False),
                "characterIds": json.dumps([], ensure_ascii=False),
                "default_member_realism_state": default_realism,
                "baseline_realism_state": baseline,
                "character_system_prompts": character_prompts,
                "group_lorebook": self._json_string_or_default(group_lorebook, {"entries": []}),
                "world_ids": self._json_string_or_default(payload.get("world_ids"), []),
                "inherit_character_lorebooks": 1 if payload.get("inherit_character_lorebooks", True) else 0,
                "chaos_mode_enabled": 1 if payload.get("chaos_mode_enabled") else 0,
                "chaos_nsfw_enabled": 1 if payload.get("chaos_nsfw_enabled") else 0,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
            if "characters" in tables:
                for row in source_character_rows:
                    self._sqlite_insert_dynamic(cur, "characters", row)
            if "sessions" in tables:
                for row in source_session_rows:
                    self._sqlite_insert_dynamic(cur, "sessions", row)
            if "messages" in tables:
                for row in source_message_rows:
                    self._sqlite_insert_dynamic(cur, "messages", row)
            try:
                self._log_event("front_porch_group_source_characters", {
                    "groupId": group_id,
                    "characterIds": source_character_ids,
                    "characterImages": [str(chars_dir / f"{cid}.png") for cid in source_character_ids],
                    "frontPorchAssetRoot": str(asset_root),
                    "groupAvatarDir": str(avatar_dir),
                })
            except Exception:
                pass
            self._sqlite_insert_dynamic(cur, "groups", group_values)
            try:
                groups_info = self._sqlite_table_info(cur, "groups")
                group_select_cols = [c for c in ("id", "name", "character_ids", "characterIds", "turn_order", "auto_advance", "director_mode", "avatar_filename", "avatar_path", "image_path", "cover_image", "thumbnail") if c in groups_info]
                if group_select_cols:
                    q = ", ".join(group_select_cols)
                    r = cur.execute(f"SELECT {q} FROM groups WHERE id = ?", (group_id,)).fetchone()
                    if r:
                        self._log_event("front_porch_group_db_row", {"groupId": group_id, "columns": group_select_cols, "row": {group_select_cols[i]: r[i] for i in range(len(group_select_cols))}})
            except Exception as e:
                self._log_event("front_porch_group_db_row_error", {"groupId": group_id, "error": str(e)})
            for row in member_rows:
                self._sqlite_insert_dynamic(cur, "group_members", row)
            try:
                gm_info = self._sqlite_table_info(cur, "group_members")
                avatar_cols = [c for c in gm_info.keys() if any(tok in c.lower() for tok in ("avatar", "image", "file"))]
                select_cols = ["id", "group_id", "name"] + avatar_cols
                select_cols = [c for c in select_cols if c in gm_info]
                if select_cols:
                    q = ", ".join(select_cols)
                    rows = cur.execute(f"SELECT {q} FROM group_members WHERE group_id = ?", (group_id,)).fetchall()
                    snapshots = []
                    for r in rows:
                        snapshots.append({select_cols[i]: r[i] for i in range(len(select_cols))})
                    self._log_event("front_porch_group_member_db_rows", {"groupId": group_id, "columns": select_cols, "rows": snapshots})
            except Exception as e:
                self._log_event("front_porch_group_member_db_rows_error", {"groupId": group_id, "error": str(e)})

            session_id = str(now_ms + len(source_character_ids) + 1000)
            if "sessions" in tables:
                session_values = {
                    "id": session_id,
                    "character_id": None,
                    "group_id": group_id,
                    "name": str(payload.get("name") or "Group Card"),
                    "description": str(profile.get("group_overview") or ""),
                    "author_note": "",
                    "author_note_depth": 4,
                    "summary": None,
                    "summary_last_index": None,
                    "parent_session": None,
                    "fork_index": None,
                    "affection_score": 0,
                    "relationship_tier": 0,
                    "long_term_score": 0,
                    "long_term_tier": 0,
                    "turns_since_long_term_check": 0,
                    "short_term_deltas_summary": 0,
                    "realism_enabled": 1,
                    "short_term_mood": 0,
                    "mood_decay_counter": 0,
                    "character_emotion": "neutral",
                    "emotion_intensity": "mild",
                    "time_of_day": "afternoon",
                    "day_count": 1,
                    "nsfw_cooldown_enabled": 1,
                    "passage_of_time_enabled": 1,
                    "arousal_level": 0,
                    "cooldown_turns_remaining": 0,
                    "trust_level": 0,
                    "active_fixation": "",
                    "fixation_lifespan": 0,
                    "spatial_stance": "",
                    "trust_repair_pending": 0,
                    "chaos_mode_enabled": 1 if payload.get("chaos_mode_enabled") else 0,
                    "chaos_pressure": 0,
                    "evolved_personality": "",
                    "evolved_scenario": "",
                    "evolution_count": 0,
                    "group_evolved_personalities": "{}",
                    "group_evolved_scenarios": "{}",
                    "generation_settings": None,
                    "group_realism_state": default_realism,
                    "start_day_of_week": 0,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                    "user_persona_id": None,
                }
                self._sqlite_insert_dynamic(cur, "sessions", session_values)
                first_message = str(payload.get("first_message") or "").strip()
                if first_message and "messages" in tables:
                    cur.execute("""
                        INSERT INTO messages (id, session_id, position, sender, is_user, character_id, swipes, swipe_index, swipe_durations, metadata, swipe_metadata, updated_at, deleted_at)
                        VALUES (?, ?, 0, ?, 0, NULL, ?, 0, '[0]', NULL, NULL, ?, NULL)
                    """, (str(uuid.uuid4()), session_id, str(payload.get("name") or "Group"), json.dumps([first_message], ensure_ascii=False), now))
            try:
                cur.execute("UPDATE sync_meta SET version = version + 1, last_modified_at = ? WHERE id = 1", (now,))
            except Exception:
                pass
            con.commit()
            try:
                avatar_checks = []
                for mid in member_ids:
                    avatar_checks.append(self._png_file_diagnostics(avatar_dir / f"{mid}.png"))
                self._log_event("front_porch_group_export_verify", {
                    "groupId": group_id,
                    "db": str(db),
                    "avatarDir": str(avatar_dir),
                    "avatarDirExists": avatar_dir.exists(),
                    "avatarFiles": sorted([p.name for p in avatar_dir.glob("*.png")]) if avatar_dir.exists() else [],
                    "avatarChecks": avatar_checks,
                })
            except Exception as e:
                self._log_event("front_porch_group_export_verify_error", {"groupId": group_id, "error": str(e)})
            con.close()
            self._log_event("front_porch_group_export", {"name": payload.get("name"), "groupId": group_id, "target": selected_target, "targetLabel": target_label, "members": len(member_rows), "sourceCharacterIds": source_character_ids, "db": str(db), "avatarDir": str(avatar_dir), "backup": str(backup_path)})
            return {"ok": True, "name": payload.get("name") or "Group Card", "groupId": group_id, "sessionId": session_id, "target": selected_target, "targetLabel": target_label, "database": str(db), "memberCount": len(member_rows), "memberCharacterIds": source_character_ids, "avatarDir": str(avatar_dir), "charactersDir": str(chars_dir), "backup": str(backup_path)}
        except Exception as e:
            try:
                if con:
                    con.rollback(); con.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Front Porch {target_label} Group Card export failed: {e}. Database backup was created at: {backup_path}"}

    def export_front_porch_from_project(self, project_path, settings=None, target=None, *args):
        """Export a saved project directly into Front Porch AI.

        Keep this tolerant for PyWebView/AppImage version mixes. The frontend normally
        saves the desired Front Porch target first and then calls this with only the
        project path, but beta7 also accepts an optional target/settings payload so
        future callers can choose Stable/Beta without relying on global settings.
        """
        if target is None and args:
            target = args[0]
        if isinstance(settings, str) and target is None:
            target = settings
            settings = None
        loaded = self.load_character_project(project_path)
        if not loaded.get("ok"):
            self._log_event("front_porch_project_export_load_failed", {"project": str(project_path), "error": loaded.get("error")})
            return loaded
        is_group_project = self._loaded_project_is_group_card(loaded)
        self._log_event("front_porch_project_export_start", {
            "project": str(project_path),
            "target": target,
            "isGroupProject": bool(is_group_project),
            "frontend": loaded.get("frontend"),
            "exportFormat": loaded.get("exportFormat"),
            "groupCardPath": loaded.get("groupCardPath"),
            "hasGroupPayload": isinstance(loaded.get("groupPayload"), dict) and loaded.get("groupPayload", {}).get("spec") == "front_porch_group_card",
        })
        if is_group_project:
            merged_settings = {**(loaded.get("settings") or {}), **self.settings}
            if isinstance(settings, dict):
                merged_settings = {**merged_settings, **settings}
            if target:
                merged_settings["frontPorchExportTarget"] = str(target or merged_settings.get("frontPorchExportTarget") or "stable").strip().lower()
            return self.export_group_card_to_front_porch_beta(loaded, merged_settings, target=merged_settings.get("frontPorchExportTarget") or target or "stable")
        # Current app settings win over older settings saved inside the character workspace,
        # otherwise a saved project with a blank Front Porch folder can mask the value the user just entered.
        merged_settings = {**(loaded.get("settings") or {}), **self.settings}
        if isinstance(settings, dict):
            merged_settings = {**merged_settings, **settings}
        if target:
            selected_target = str(target or "stable").strip().lower()
            if selected_target not in {"stable", "beta"}:
                selected_target = "stable"
            merged_settings["frontPorchExportTarget"] = selected_target
            if selected_target == "beta":
                merged_settings["frontPorchDataFolder"] = merged_settings.get("frontPorchBetaDataFolder") or merged_settings.get("frontPorchDataFolder") or ""
            else:
                merged_settings["frontPorchDataFolder"] = merged_settings.get("frontPorchStableDataFolder") or merged_settings.get("frontPorchDataFolder") or ""
        selected_image = (
            loaded.get("imagePath")
            or loaded.get("imageDataUrl")
            or (loaded.get("settings") or {}).get("cardImagePath")
            or (loaded.get("settings") or {}).get("imageDataUrl")
            or ""
        )
        export_image = self._resolve_front_porch_export_image(selected_image, project_path=project_path, loaded_project=loaded, reason="export_front_porch_from_project")
        return self.export_to_front_porch(loaded.get("output") or "", export_image, merged_settings, project_path)

    def export_card(self, output, frontend=None, export_format=None, image_path=None, concept="", template=None, settings=None):
        if not output or not output.strip():
            return {"ok": False, "error": "Nothing to export."}
        template = template or self.template
        output = self._normalise_card_output_for_save(output, template)
        frontend = "front_porch"
        export_format = export_format or "chara_v2_png"
        if export_format == "frontend_json":
            export_format = "chara_v2_json"
        safe_name = self._extract_name(output) or "character_card"
        safe = self._safe_slug(safe_name)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        merged_settings = self._normalise_settings({**self.settings, **(settings or {})})
        export_root = str(merged_settings.get("exportDestinationFolder") or "").strip()
        if export_root:
            export_folder = Path(export_root).expanduser().resolve()
            _safe_mkdir(export_folder)
            if not _path_is_writable_dir(export_folder):
                return {"ok": False, "error": "The selected export folder is not writable."}
        else:
            export_folder = self._character_export_dir(safe_name)

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
        """Extract the actual character display name from generated/raw card text."""
        text = str(text or "")
        if not text.strip():
            return "Character Card"

        # Prefer line-based parsing so divider-heavy output like:
        # ----- / Name / blank / Sayuri / -----
        # cannot accidentally fall back to the generic Character tab name.
        lines = text.splitlines()
        for i, line in enumerate(lines):
            raw = line.strip()
            if not raw or self._looks_like_divider_line(raw):
                continue
            colon = re.match(r"(?i)^\s*name\s*[:：-]\s*(.+?)\s*$", raw)
            if colon:
                name = self._clean_character_name_value(colon.group(1))
                if name and not self._is_generic_character_name(name):
                    return name
            heading = raw.strip("#*` ").strip()
            if re.fullmatch(r"(?i)name", heading):
                for cand in lines[i + 1:]:
                    value = cand.strip()
                    if not value or self._looks_like_divider_line(value):
                        continue
                    # Stop if the next real line is another heading.
                    next_heading = value.strip("#*` ").strip()
                    if re.fullmatch(r"(?i)(description|personality|scenario|first message|alternative first messages|example dialogues|lorebook entries|tags|state tracking|stable diffusion prompt|natural english image prompt)", next_heading):
                        break
                    name = self._clean_character_name_value(value)
                    if name and not self._is_generic_character_name(name):
                        return name
                    break

        # Regex fallbacks for compact card formats.
        m = re.search(r"(?im)^\s*Name\s*[:：-]\s*(.+)$", text)
        if m:
            name = self._clean_character_name_value(m.group(1))
            if name:
                return name
        m = re.search(r"(?ims)^\s*Name\s*$\s*([^\n#-][^\n]*)", text)
        if m:
            name = self._clean_character_name_value(m.group(1))
            if name:
                return name
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
            "natural english image prompt": "natural_image_prompt",
            "natural image prompt": "natural_image_prompt",
            "natural prompt": "natural_image_prompt",
            "natural english image prompt": "natural_image_prompt",
            "natural image prompt": "natural_image_prompt",
            "natural prompt": "natural_image_prompt",
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
        for marker in ["State Tracking", "--- STATE TRACKING ---", "Stable Diffusion Prompt", "Natural English Image Prompt"]:
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

    def _clamp_int_value(self, value, default=0, minimum=None, maximum=None):
        parsed = self._parse_int_value(value, default)
        if minimum is not None and parsed < minimum:
            parsed = minimum
        if maximum is not None and parsed > maximum:
            parsed = maximum
        return parsed

    def _normalize_front_porch_time_of_day(self, value):
        raw = str(value or "").strip().lower()
        raw = re.sub(r"[\s_-]+", " ", raw)
        # Front Porch does not support Late Afternoon. Treat it as Afternoon.
        if raw in {"late afternoon", "late-afternoon", "late_afternoon"}:
            return "afternoon"
        aliases = {
            "early morning": "morning",
            "late morning": "morning",
            "midday": "noon",
            "mid day": "noon",
            "middle of day": "noon",
            "early afternoon": "afternoon",
            "early evening": "evening",
            "late evening": "evening",
            "midnight": "night",
            "late night": "night",
            "overnight": "night",
        }
        raw = aliases.get(raw, raw)
        valid = {"morning", "noon", "afternoon", "evening", "night"}
        if raw not in valid:
            return "afternoon"
        return raw

    def _normalise_front_porch_realism_engine(self, fp):
        fp = dict(fp or {}) if isinstance(fp, dict) else {}
        fp["short_term_bond"] = self._clamp_int_value(fp.get("short_term_bond"), 0, -300, 300)
        fp["long_term_bond"] = self._clamp_int_value(fp.get("long_term_bond"), 0, -300, 300)
        fp["trust_level"] = self._clamp_int_value(fp.get("trust_level"), 0, -100, 100)
        fp["day_count"] = max(1, self._parse_int_value(fp.get("day_count"), 1))
        fp["time_of_day"] = self._normalize_front_porch_time_of_day(fp.get("time_of_day") or "afternoon")
        fp["start_day_of_week"] = self._normalize_front_porch_start_day_of_week(fp.get("start_day_of_week") or fp.get("day_of_week") or 0)
        fp["character_emotion"] = str(fp.get("character_emotion") or "Neutral").strip() or "Neutral"
        fp["emotion_intensity"] = str(fp.get("emotion_intensity") or "moderate").strip().lower() or "moderate"
        fp["enabled"] = bool(fp.get("enabled", True))
        fp["nsfw_cooldown_enabled"] = bool(fp.get("nsfw_cooldown_enabled", True))
        fp["passage_of_time_enabled"] = bool(fp.get("passage_of_time_enabled", True))
        fp["chaos_mode_enabled"] = bool(fp.get("chaos_mode_enabled", True))
        fp["current_task"] = str(fp.get("current_task") or "Interact with {{user}} in character.").strip()
        return fp

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
            key = key.replace("weekday", "day_of_week")
            key = key.replace("starting_weekday", "day_of_week")
            key = key.replace("starting_day_of_week", "day_of_week")
            state[key] = val.strip()
        return state

    def _front_porch_realism_engine(self, state_tracking):
        state = self._parse_state_tracking_map(state_tracking)
        # Front Porch newer ranges:
        # - Short-Term Bond: -300 to 300
        # - Long-Term Bond: -300 to 300
        # - Trust Level: -100 to 100
        # Time of Day must be one of the valid Front Porch values; Late Afternoon is normalized to Afternoon.
        # Day of Week / Start Day of Week: 0 legacy/unset, 1 Monday ... 7 Sunday.
        return self._normalise_front_porch_realism_engine({
            "enabled": True,
            "short_term_bond": state.get("short_term_bond"),
            "long_term_bond": state.get("long_term_bond"),
            "trust_level": state.get("trust_level"),
            "day_count": state.get("day_number") or state.get("day_count"),
            "time_of_day": state.get("time_of_day") or "afternoon",
            "start_day_of_week": state.get("start_day_of_week") or state.get("day_of_week") or state.get("weekday") or 0,
            "character_emotion": state.get("character_emotion") or "Neutral",
            "emotion_intensity": state.get("emotion_intensity") or "moderate",
            "nsfw_cooldown_enabled": True,
            "passage_of_time_enabled": True,
            "chaos_mode_enabled": True,
            "current_task": state.get("current_task") or "Interact with {{user}} in character.",
        })

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
        tags = self._clean_character_tags(sec_by_id("tags", "Tags").replace("\n", ",").split(","))

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
        core_ids = {"name", "description", "personality", "scenario", "first_message", "alternate_first_messages", "example_dialogues", "lorebook", "tags", "system_prompt", "state_tracking", "stable_diffusion", "natural_image_prompt"}
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
            "natural_image_prompt": self._clean_section_text(self._section(output, "Natural English Image Prompt")),
            "tags": data.get("tags", []),
            "raw_card": output,
            "sillytavern_chara_card_v2": card_v2,
        }

    def _image_mime_from_bytes(self, raw):
        """Guess a browser-safe image MIME from decoded bytes."""
        try:
            if not raw:
                return ""
            if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if raw.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
                return "image/webp"
            if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
                return "image/gif"
        except Exception:
            pass
        return ""

    def _raw_base64_image_to_data_url(self, value, preferred_mime=""):
        """Convert raw image base64 into a data URL when the bytes really are an image."""
        try:
            text = str(value or "").strip()
            if len(text) < 256:
                return ""
            if text.lower().startswith(("data:", "http://", "https://", "file://")):
                return ""
            if text.startswith("{") or text.startswith("["):
                return ""
            compact = re.sub(r"\s+", "", text)
            if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
                return ""
            pad = "=" * (-len(compact) % 4)
            candidates = [compact + pad]
            if "-" in compact or "_" in compact:
                candidates.append(compact.replace("-", "+").replace("_", "/") + pad)
            for candidate in candidates:
                try:
                    raw = base64.b64decode(candidate, validate=False)
                except Exception:
                    continue
                mime = preferred_mime if str(preferred_mime or "").lower().startswith("image/") else self._image_mime_from_bytes(raw)
                if not mime:
                    continue
                # Verify it is actually loadable by Pillow before surfacing it.
                try:
                    with Image.open(io.BytesIO(raw)) as img:
                        img.verify()
                except Exception:
                    continue
                return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
        except Exception:
            return ""
        return ""

    def _candidate_image_data_url_from_value(self, value):
        """Return an image data URL found inside a value, if one exists.

        CCF has used several storage shapes over time: normal data URLs, raw
        base64 strings, and dictionaries with base64/b64/bytes plus a MIME field.
        Front Porch group-member avatars need the real image bytes, so this helper
        accepts all of those shapes while rejecting non-image base64 such as chara
        JSON.
        """
        if value is None:
            return ""
        if isinstance(value, str):
            text = value.strip()
            if text.lower().startswith("data:image/") and ";base64," in text.lower():
                return text
            # Some saved JSON/workspace strings can contain a nested data URL.
            m = re.search(r"data:image/[a-z0-9.+-]+(?:;charset=[^;,]+)?;base64,[A-Za-z0-9+/=_\\s-]+", text, re.I)
            if m:
                return m.group(0)
            # Some CCF/browser DB fields store the image as raw base64 only.
            return self._raw_base64_image_to_data_url(text)
        if isinstance(value, dict):
            mime = str(value.get("mime") or value.get("mime_type") or value.get("content_type") or value.get("type") or "").strip()
            # Prefer obvious combined image fields first.
            for key in ("dataUrl", "data_url", "imageDataUrl", "image_data_url", "url", "uri", "src", "image"):
                found = self._candidate_image_data_url_from_value(value.get(key))
                if found:
                    return found
            # Then support split/raw base64 payload fields.
            for key in ("base64", "b64", "bytes", "data", "imageBase64", "image_base64", "thumbnailBase64", "thumbnail_base64"):
                raw_value = value.get(key)
                if isinstance(raw_value, str):
                    found = self._raw_base64_image_to_data_url(raw_value, mime)
                    if found:
                        return found
            # Finally recurse through remaining values.
            for child in value.values():
                found = self._candidate_image_data_url_from_value(child)
                if found:
                    return found
        return ""

    def _save_raw_card_image_bytes(self, raw, mime="image/png", kind="card", label="embedded_card_image"):
        """Persist decoded image bytes and return a local path, verifying with Pillow."""
        if not raw:
            return ""
        try:
            folder = VISION_IMAGES_DIR if str(kind).lower() == "vision" else CARD_IMAGES_DIR
            suffix = self._extension_from_mime(mime or "image/png", "image") or self._embedded_image_suffix_from_mime(mime) or ".png"
            safe_label = self._safe_slug(label or "embedded_card_image")[:48] or "embedded_card_image"
            path = folder / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_label}{suffix}"
            path.write_bytes(raw)
            try:
                with Image.open(path) as img:
                    img.verify()
            except Exception:
                path.unlink(missing_ok=True)
                return ""
            return str(path)
        except Exception:
            return ""

    def _materialize_image_data_url(self, data_url, kind="card", reason="data_url"):
        """Convert an image data URL into a local file path."""
        try:
            text = str(data_url or "").strip()
            m = re.match(r"^data:(image/[a-z0-9.+-]+)(?:;charset=[^;,]+)?;base64,(.*)$", text, re.I | re.S)
            if not m:
                return ""
            mime = (m.group(1) or "image/png").lower()
            raw = base64.b64decode(re.sub(r"\s+", "", m.group(2) or ""), validate=False)
            path = self._save_raw_card_image_bytes(raw, mime, kind, reason or "data_url_image")
            if path:
                self._log_event("card_image_data_url_materialized", {"reason": reason, "kind": kind, "path": path})
            return path
        except Exception as e:
            self._log_event("card_image_data_url_materialize_exception", {"reason": reason, "kind": kind, "error": str(e)})
            return ""

    def _materialize_raw_base64_image(self, value, kind="card", reason="raw_base64"):
        """Handle saved image fields that contain raw base64 without a data:image prefix."""
        try:
            text = str(value or "").strip()
            if len(text) < 256:
                return ""
            # Avoid treating normal paths/URLs/JSON as base64.
            if text.lower().startswith(("http://", "https://", "file://", "data:")):
                return ""
            if text.startswith("{") or text.startswith("["):
                return ""
            compact = re.sub(r"\s+", "", text)
            if not re.match(r"^[A-Za-z0-9+/=_-]+$", compact):
                return ""
            # Accept URL-safe base64 too.
            pad = "=" * (-len(compact) % 4)
            candidates = [compact + pad]
            if "-" in compact or "_" in compact:
                candidates.append(compact.replace("-", "+").replace("_", "/") + pad)
            for candidate in candidates:
                try:
                    raw = base64.b64decode(candidate, validate=False)
                except Exception:
                    continue
                path = self._save_raw_card_image_bytes(raw, "image/png", kind, reason or "raw_base64_image")
                if path:
                    self._log_event("card_image_raw_base64_materialized", {"reason": reason, "kind": kind, "path": path})
                    return path
            return ""
        except Exception as e:
            self._log_event("card_image_raw_base64_materialize_exception", {"reason": reason, "kind": kind, "error": str(e)})
            return ""

    def _iter_image_data_urls_deep(self, value, limit=64):
        """Yield embedded data:image/... base64 URLs from nested project/workspace data."""
        seen = set()
        count = 0
        def walk(obj):
            nonlocal count
            if count >= limit:
                return
            if obj is None:
                return
            if isinstance(obj, str):
                # A field may be exactly a data URL, a raw image base64 string,
                # or a JSON/text blob containing a data URL.
                direct = self._candidate_image_data_url_from_value(obj)
                if direct and direct not in seen:
                    seen.add(direct)
                    count += 1
                    yield direct
                    if count >= limit:
                        return
                for m in re.finditer(r"data:image/[a-z0-9.+-]+(?:;charset=[^;,]+)?;base64,[A-Za-z0-9+/=_\s-]+", obj, re.I):
                    data_url = m.group(0).strip()
                    if data_url and data_url not in seen:
                        seen.add(data_url)
                        count += 1
                        yield data_url
                        if count >= limit:
                            return
                return
            if isinstance(obj, dict):
                # Prefer obvious image fields first so selected/primary images win over random attachments.
                priority = [
                    "imageDataUrl", "cardImageDataUrl", "dataUrl", "data_url", "image_data_url",
                    "cardImagePath", "imagePath", "src", "url", "uri", "image", "data"
                ]
                yielded = set()
                for key in priority:
                    if key in obj:
                        yielded.add(key)
                        yield from walk(obj.get(key))
                        if count >= limit:
                            return
                for key, child in obj.items():
                    if key in yielded:
                        continue
                    yield from walk(child)
                    if count >= limit:
                        return
                return
            if isinstance(obj, (list, tuple)):
                for child in obj:
                    yield from walk(child)
                    if count >= limit:
                        return
        yield from walk(value)

    def _png_file_has_nonblank_visible_pixels(self, path):
        """Return True when an image file appears to contain real visible art."""
        try:
            p = Path(str(path or ""))
            if not p.exists() or not p.is_file():
                return False
            with Image.open(p) as img:
                sample = img.convert("RGBA")
                sample.thumbnail((32, 32))
                pixels = list(sample.getdata())
            if not pixels:
                return False
            channels = list(zip(*pixels))
            rgb_delta = max((max(ch) - min(ch)) for ch in channels[:3]) if len(channels) >= 3 else 0
            alpha_delta = (max(channels[3]) - min(channels[3])) if len(channels) > 3 else 0
            return rgb_delta >= 8 or alpha_delta >= 8
        except Exception:
            return False

    def _avatar_base64_has_nonblank_visible_pixels(self, avatar_b64):
        try:
            raw = base64.b64decode(str(avatar_b64 or ""), validate=False)
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                return False
            with Image.open(io.BytesIO(raw)) as img:
                sample = img.convert("RGBA")
                sample.thumbnail((32, 32))
                pixels = list(sample.getdata())
            if not pixels:
                return False
            channels = list(zip(*pixels))
            rgb_delta = max((max(ch) - min(ch)) for ch in channels[:3]) if len(channels) >= 3 else 0
            alpha_delta = (max(channels[3]) - min(channels[3])) if len(channels) > 3 else 0
            return rgb_delta >= 8 or alpha_delta >= 8
        except Exception:
            return False

    def _front_porch_project_image_from_library_cache(self, project_path, reason="front_porch_library_cache_image"):
        """Recover a Browser thumbnail when older projects lost the original image path."""
        try:
            row = self._library_get_card_row(Path(str(project_path or "")).expanduser())
        except Exception:
            row = None
        if not row:
            return ""
        for key in ("thumbnail_data_url", "image_data_url"):
            thumb = str(row.get(key) or "").strip()
            if not thumb:
                continue
            local = self._ensure_local_card_image_path(thumb, "card", reason)
            if local and Path(local).exists() and self._png_file_has_nonblank_visible_pixels(local):
                self._log_event("front_porch_image_library_cache_materialized", {"project": str(project_path or ""), "key": key, "path": local})
                return local
        return ""

    def _front_porch_project_image_from_assets(self, project_path, selected_path="", reason="front_porch_asset_image"):
        """Restore the selected/main card image from the workspace asset DB using the real project path."""
        canonical_project_path = str(project_path or "")
        try:
            rows = self._load_workspace_assets_from_db(project_path)
        except Exception as e:
            self._log_event("front_porch_image_asset_lookup_failed", {"project": canonical_project_path, "error": str(e)})
            rows = []
        if not rows:
            return ""
        selected = str(selected_path or "").strip()
        selected_name = Path(selected).name if selected and not selected.lower().startswith(("data:", "http://", "https://")) else ""

        def row_matches_selected(row):
            if not selected:
                return False
            source = str(row.get("source_path") or "").strip()
            filename = str(row.get("filename") or "").strip()
            if source and source == selected:
                return True
            if selected_name and (Path(source).name == selected_name or filename == selected_name):
                return True
            try:
                meta = json.loads(row.get("metadata_json") or "{}")
                for key in ("path", "source_path", "filename"):
                    val = str(meta.get(key) or "").strip()
                    if val == selected or (selected_name and Path(val).name == selected_name):
                        return True
            except Exception:
                pass
            return False

        # Order matters: exact selected generated image, selected-card snapshot, then any usable generated/card image.
        ordered = []
        exact = [r for r in rows if row_matches_selected(r)]
        selected_rows = [r for r in rows if (r.get("asset_key") == "selected_card_image" or (r.get("metadata_json") or "").find("selected_card_image") >= 0)]
        image_rows = [r for r in rows if str(r.get("asset_type") or "").lower() in {"image", "generated_image", "tab_generated_image"}]
        for group in (exact, selected_rows, image_rows):
            for r in group:
                if r not in ordered:
                    ordered.append(r)

        for row in ordered:
            blob = row.get("data_blob")
            mime = row.get("mime_type") or "image/png"
            label = f"{reason}_{row.get('asset_key') or 'asset'}"
            path = ""
            if blob:
                path = self._save_raw_card_image_bytes(blob, mime, "card", label)
            if not path:
                data_text = row.get("data_text") or ""
                data_url = self._candidate_image_data_url_from_value(data_text)
                if data_url:
                    path = self._ensure_local_card_image_path(data_url, "card", label + "_data_text")
            if path and self._png_file_has_nonblank_visible_pixels(path):
                self._log_event("front_porch_image_asset_materialized", {
                    "project": str(project_path),
                    "selectedPath": selected,
                    "assetKey": row.get("asset_key"),
                    "assetType": row.get("asset_type"),
                    "path": path,
                })
                return path
            if path:
                self._log_event("front_porch_image_asset_skipped_flat", {
                    "project": str(project_path),
                    "selectedPath": selected,
                    "assetKey": row.get("asset_key"),
                    "assetType": row.get("asset_type"),
                    "path": path,
                })
        return ""

    def _front_porch_project_image_from_json(self, project_path, selected_path="", reason="front_porch_project_json"):
        """Restore a card image by directly scanning a saved project JSON for image paths/base64."""
        canonical_project_path = str(project_path or "")
        try:
            payload = json.loads(Path(project_path).read_text(encoding="utf-8"))
        except Exception as e:
            self._log_event("front_porch_image_project_json_read_failed", {"project": canonical_project_path, "error": str(e)})
            return ""
        project = payload.get("project", payload) if isinstance(payload, dict) else {}
        if not isinstance(project, dict):
            return ""
        workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
        settings = project.get("settings") if isinstance(project.get("settings"), dict) else {}
        selected = str(selected_path or "").strip()

        candidates = []
        def add(v):
            if v is None:
                return
            if isinstance(v, str):
                vv = v.strip()
                if vv and vv not in candidates:
                    candidates.append(vv)
            else:
                data_url = self._candidate_image_data_url_from_value(v)
                if data_url and data_url not in candidates:
                    candidates.append(data_url)

        # Direct selected path first, then explicit card-image fields.
        add(selected)
        for obj in (project, workspace, settings, workspace.get("settings") if isinstance(workspace.get("settings"), dict) else {}):
            if not isinstance(obj, dict):
                continue
            for key in ("cardImagePath", "imagePath", "imageDataUrl", "cardImageDataUrl"):
                add(obj.get(key))
            # Legacy saved cards may have lost the generated-image temp file, but
            # still have a latest/exported Chara Card PNG in the saved card folder.
            # That PNG's visible pixels are a perfectly valid Front Porch main image
            # source, and its metadata will be replaced during the new export.
            for key in ("exportedPath", "cardPath", "cardPngPath", "latestCardPath", "latestCardPng", "exportedCardPath"):
                add(obj.get(key))

        # Prefer generated image entries matching the selected path/name.
        selected_name = Path(selected).name if selected and not selected.lower().startswith(("data:", "http://", "https://")) else ""
        def add_image_list(items):
            if not isinstance(items, list):
                return
            exact = []
            fallback = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_path = str(item.get("path") or item.get("source_path") or item.get("filename") or "").strip()
                data_url = self._candidate_image_data_url_from_value(item)
                if not data_url:
                    continue
                if selected and (item_path == selected or (selected_name and Path(item_path).name == selected_name)):
                    exact.append(data_url)
                else:
                    fallback.append(data_url)
            for v in exact + fallback:
                add(v)
        add_image_list(project.get("generatedImages") or workspace.get("generatedImages") or [])
        tabs = project.get("characterTabs") or workspace.get("characterTabs") or []
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict):
                    add(tab.get("cardImagePath"))
                    add(tab.get("imagePath"))
                    add(tab.get("imageDataUrl"))
                    add(tab.get("cardImageDataUrl"))
                    add_image_list(tab.get("generatedImages") or [])

        for candidate in candidates:
            local = self._ensure_local_card_image_path(candidate, "card", reason)
            if local and self._png_file_has_nonblank_visible_pixels(local):
                self._log_event("front_porch_image_project_json_materialized", {"project": str(project_path), "sourceKind": "candidate", "path": local})
                return local
            if local:
                self._log_event("front_porch_image_project_json_skipped_flat", {"project": str(project_path), "sourceKind": "candidate", "path": local})

        # Last resort: recursively scan the saved project for any embedded image data.
        for data_url in self._iter_image_data_urls_deep(project):
            local = self._ensure_local_card_image_path(data_url, "card", reason + "_deep_scan")
            if local and self._png_file_has_nonblank_visible_pixels(local):
                self._log_event("front_porch_image_project_json_materialized", {"project": str(project_path), "sourceKind": "deep_data_url", "path": local})
                return local
            if local:
                self._log_event("front_porch_image_project_json_skipped_flat", {"project": str(project_path), "sourceKind": "deep_data_url", "path": local})
        return ""

    def _image_file_is_probably_blank_placeholder(self, path):
        """Detect the built-in blank placeholder PNG so legacy fallbacks skip it."""
        try:
            p = Path(str(path or ""))
            if not p.exists() or not p.is_file():
                return True
            with Image.open(p) as img:
                sample = img.convert("RGBA")
                sample.thumbnail((24, 24))
                pixels = list(sample.getdata())
            if not pixels:
                return True
            # The app's blank placeholder is a flat dark image.  Treat images with
            # almost no colour variation as blank so an old *_latest_cardv2.png
            # fallback does not silently re-export the placeholder.
            channels = list(zip(*pixels))
            max_delta = 0
            for ch in channels[:3]:
                max_delta = max(max_delta, max(ch) - min(ch))
            alpha_delta = max(channels[3]) - min(channels[3]) if len(channels) > 3 else 0
            return max_delta < 6 and alpha_delta < 6
        except Exception:
            return True

    def _front_porch_existing_card_png_from_project(self, project_path, reason="front_porch_existing_card_png"):
        """Use an existing saved/auto-exported card PNG as a legacy image fallback.

        Older CCF saves may only remember the selected SD/generated image as a temp
        path under generated_images/.  If that temp file was later cleaned, the raw
        generated base64 may also be gone.  However, the saved card folder usually
        still contains a *_latest_cardv2.png or timestamped *_cardv2.png that was
        written while the image still existed.  Front Porch export can safely use
        those visible pixels as the main image source, then write fresh metadata.
        """
        try:
            project_path = Path(str(project_path or "")).expanduser()
            if not project_path.exists():
                return ""
            folder = project_path.parent
            candidates = []
            def add_path(value):
                if not value:
                    return
                try:
                    raw = Path(str(value)).expanduser()
                    if not raw.is_absolute():
                        raw = (folder / raw).resolve()
                    candidates.append(raw)
                except Exception:
                    pass

            project = {}
            try:
                payload = json.loads(project_path.read_text(encoding="utf-8"))
                project = payload.get("project", payload) if isinstance(payload, dict) else {}
            except Exception as e:
                self._log_event("front_porch_existing_card_png_json_read_failed", {"project": str(project_path), "error": str(e)})
                project = {}
            if isinstance(project, dict):
                workspace = project.get("workspace") if isinstance(project.get("workspace"), dict) else {}
                settings = project.get("settings") if isinstance(project.get("settings"), dict) else {}
                for obj in (project, workspace, settings, workspace.get("settings") if isinstance(workspace.get("settings"), dict) else {}):
                    if not isinstance(obj, dict):
                        continue
                    for key in ("exportedPath", "cardPath", "cardPngPath", "latestCardPath", "latestCardPng", "exportedCardPath"):
                        add_path(obj.get(key))
                name = str(project.get("name") or workspace.get("name") or "").strip()
                if name:
                    add_path(folder / f"{self._safe_slug(name)}_latest_cardv2.png")

            # Folder-level legacy fallbacks. Prefer latest_cardv2, then newest cardv2,
            # then any non-placeholder image in the project folder.
            candidates.extend(sorted(folder.glob("*_latest_cardv2.png"), key=lambda x: x.stat().st_mtime, reverse=True))
            candidates.extend(sorted(folder.glob("*_cardv2.png"), key=lambda x: x.stat().st_mtime, reverse=True))
            extra_images = []
            emotion_names = {f"{e}.png" for e in EMOTION_OPTIONS}
            for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                try:
                    extra_images.extend(folder.glob(pattern))
                except Exception:
                    pass
            for extra in sorted(extra_images, key=lambda x: x.stat().st_mtime, reverse=True):
                low = extra.name.lower()
                if low in emotion_names or ".group." in low or low.endswith(".group.png"):
                    continue
                candidates.append(extra)

            seen = set()
            for candidate in candidates:
                try:
                    candidate = Path(candidate)
                    key = str(candidate.resolve())
                except Exception:
                    key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                if not candidate.exists() or not candidate.is_file():
                    continue
                try:
                    with Image.open(candidate) as img:
                        img.verify()
                except Exception:
                    continue
                if self._image_file_is_probably_blank_placeholder(candidate):
                    self._log_event("front_porch_existing_card_png_skipped_blank", {"reason": reason, "project": str(project_path), "path": str(candidate)})
                    continue
                self._log_event("front_porch_existing_card_png_resolved", {"reason": reason, "project": str(project_path), "path": str(candidate)})
                return str(candidate)
            return ""
        except Exception as e:
            self._log_event("front_porch_existing_card_png_failed", {"reason": reason, "project": str(project_path or ""), "error": str(e)})
            return ""

    def _resolve_front_porch_export_image(self, image_path="", project_path=None, loaded_project=None, reason="front_porch_export"):
        """Return a verified local image for Front Porch export, never the blank fallback."""
        original = str(image_path or "").strip()
        attempts = []
        def try_candidate(candidate, label):
            candidate = str(candidate or "").strip()
            if not candidate:
                return ""
            local = self._ensure_local_card_image_path(candidate, "card", f"{reason}_{label}")
            attempts.append({"label": label, "candidatePrefix": candidate[:120], "ok": bool(local), "local": local})
            return local

        def accept_local(local, method):
            if not local:
                return ""
            if self._png_file_has_nonblank_visible_pixels(local):
                self._log_event("front_porch_image_resolved", {"reason": reason, "method": method, "path": local})
                return local
            self._log_event("front_porch_image_candidate_skipped_flat", {"reason": reason, "method": method, "path": local})
            return ""

        local = accept_local(try_candidate(original, "passed_image_path"), "passed_image_path")
        if local:
            return local

        if isinstance(loaded_project, dict):
            for key in ("imagePath", "imageDataUrl", "cardImagePath", "cardImageDataUrl"):
                local = accept_local(try_candidate(loaded_project.get(key), f"loaded_{key}"), f"loaded_{key}")
                if local:
                    return local
            local = self._resolve_workspace_card_image_path(loaded_project, original, f"{reason}_loaded_workspace")
            attempts.append({"label": "loaded_workspace_candidates", "ok": bool(local), "local": local})
            local = accept_local(local, "loaded_workspace_candidates")
            if local:
                return local

        if project_path:
            # Use the actual project_path supplied by the frontend, not the old embedded projectPath inside JSON.
            local = self._front_porch_project_image_from_assets(project_path, original, f"{reason}_asset_db")
            attempts.append({"label": "asset_db", "ok": bool(local), "local": local})
            local = accept_local(local, "asset_db")
            if local:
                return local
            local = self._front_porch_project_image_from_json(project_path, original, f"{reason}_project_json")
            attempts.append({"label": "project_json", "ok": bool(local), "local": local})
            local = accept_local(local, "project_json")
            if local:
                return local
            local = self._front_porch_project_image_from_library_cache(project_path, f"{reason}_library_cache")
            attempts.append({"label": "library_cache", "ok": bool(local), "local": local})
            local = accept_local(local, "library_cache")
            if local:
                return local
            local = self._front_porch_existing_card_png_from_project(project_path, f"{reason}_existing_card_png")
            attempts.append({"label": "existing_card_png", "ok": bool(local), "local": local})
            local = accept_local(local, "existing_card_png")
            if local:
                return local

        self._log_event("front_porch_image_resolution_failed", {"reason": reason, "imagePathPrefix": original[:200], "project": str(project_path or ""), "attempts": attempts})
        return ""

    def _workspace_card_image_candidates(self, workspace=None, selected_path=""):
        """Yield likely selected-card image candidates, including generated-image base64.

        Generated image files can be cleaned up, but the saved workspace/library DB may
        still contain the generated image as a base64 dataUrl. This lets Front Porch
        export recover the real image instead of writing the blank fallback PNG.
        """
        workspace = workspace or {}
        selected = str(selected_path or "").strip()
        selected_name = Path(selected).name if selected and not selected.lower().startswith("data:") else ""
        seen = set()
        def add(value):
            if value is None:
                return
            if isinstance(value, str):
                v = value.strip()
                if v and v not in seen:
                    seen.add(v)
                    yield v
            else:
                data_url = self._candidate_image_data_url_from_value(value)
                if data_url and data_url not in seen:
                    seen.add(data_url)
                    yield data_url
        for key in ("cardImagePath", "imagePath", "imageDataUrl", "cardImageDataUrl"):
            for v in add(workspace.get(key)):
                yield v
        settings = workspace.get("settings") if isinstance(workspace.get("settings"), dict) else {}
        for key in ("cardImagePath", "imagePath", "imageDataUrl", "cardImageDataUrl"):
            for v in add(settings.get(key)):
                yield v
        def image_list_candidates(items):
            if not isinstance(items, list):
                return
            # First yield exact path/name matches, then other embedded data URLs as last-resort fallbacks.
            exact = []
            fallback = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                data_url = self._candidate_image_data_url_from_value(item)
                if not data_url:
                    continue
                item_path = str(item.get("path") or item.get("source_path") or item.get("filename") or "").strip()
                item_name = Path(item_path).name if item_path else ""
                if selected and (item_path == selected or (selected_name and item_name == selected_name)):
                    exact.append(data_url)
                else:
                    fallback.append(data_url)
            for v in exact + fallback:
                yield v
        for v in image_list_candidates(workspace.get("generatedImages") or []):
            for out in add(v):
                yield out
        tabs = workspace.get("characterTabs") if isinstance(workspace.get("characterTabs"), list) else []
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            tab_selected = str(tab.get("cardImagePath") or "").strip()
            # Prefer images from the tab that selected the same path, but still allow fallback.
            if selected and tab_selected and tab_selected != selected:
                continue
            for key in ("cardImagePath", "imagePath", "imageDataUrl", "cardImageDataUrl"):
                for v in add(tab.get(key)):
                    yield v
            for v in image_list_candidates(tab.get("generatedImages") or []):
                for out in add(v):
                    yield out

    def _resolve_workspace_card_image_path(self, workspace=None, selected_path="", reason="workspace_card_image"):
        """Return a usable local image path using workspace/generated-image fallbacks."""
        for candidate in self._workspace_card_image_candidates(workspace or {}, selected_path):
            local = self._ensure_local_card_image_path(candidate, "card", reason)
            if local:
                return local
        return ""

    def _ensure_local_card_image_path(self, image_path, kind="card", reason=""):
        """Return a local readable image path for card/export work.

        Earlier builds allowed cardImagePath to remain as a remote generated-image
        URL. That was fine for analysis, but Front Porch export and Chara PNG
        writing need real local image bytes. Resolve URLs/data URLs here so every
        export path gets an actual file instead of silently falling back to a blank
        placeholder.
        """
        source = str(image_path or "").strip().strip('"').strip("'")
        if not source:
            return ""
        try:
            # file:// URLs from drag/drop or browser contexts.
            if source.lower().startswith("file://"):
                parsed = urllib.parse.urlparse(source)
                file_path = Path(urllib.parse.unquote(parsed.path or "")).expanduser()
                if file_path.exists() and file_path.is_file():
                    return str(file_path)
        except Exception:
            pass
        try:
            p = Path(source).expanduser()
            if p.exists() and p.is_file():
                return str(p)
        except Exception:
            pass
        try:
            embedded_data_url = self._candidate_image_data_url_from_value(source)
            if embedded_data_url:
                local = self._materialize_image_data_url(embedded_data_url, kind, reason or "card_image_data_url")
                if local:
                    return local
                self._log_event("card_image_data_url_materialize_failed", {"reason": reason, "kind": kind})
                return ""
        except Exception as e:
            self._log_event("card_image_data_url_materialize_exception", {"reason": reason, "kind": kind, "error": str(e)})
            return ""
        try:
            local = self._materialize_raw_base64_image(source, kind, reason or "card_image_raw_base64")
            if local:
                return local
        except Exception:
            pass
        try:
            if self._looks_like_url(source):
                res = self.save_image_from_url(source, kind)
                if res.get("ok") and res.get("path"):
                    self._log_event("card_image_url_materialized", {"reason": reason, "kind": kind, "sourceUrl": source, "path": res.get("path")})
                    return str(res.get("path"))
                self._log_event("card_image_url_materialize_failed", {"reason": reason, "kind": kind, "sourceUrl": source, "error": res.get("error", "unknown")})
                return ""
        except Exception as e:
            self._log_event("card_image_url_materialize_exception", {"reason": reason, "kind": kind, "sourceUrl": source, "error": str(e)})
            return ""
        # Try a path relative to the app/user data folders as a final fallback.
        # Generated images may be restored from JSON/SQLite metadata by filename
        # only, so also search the managed card-image folders recursively by name.
        fallback_bases = (GENERATED_IMAGES_DIR, CARD_IMAGES_DIR, DATA_DIR, EXPORT_DIR, APP_DIR)
        for base in fallback_bases:
            try:
                candidate = (Path(base) / source).expanduser()
                if candidate.exists() and candidate.is_file():
                    return str(candidate)
            except Exception:
                pass
        try:
            source_name = Path(source).name
        except Exception:
            source_name = ""
        if source_name:
            for base in (CARD_IMAGES_DIR, GENERATED_IMAGES_DIR, DATA_DIR):
                try:
                    base_path = Path(base)
                    if not base_path.exists():
                        continue
                    matches = sorted(base_path.rglob(source_name), key=lambda p: p.stat().st_mtime, reverse=True)
                    for candidate in matches[:20]:
                        if candidate.exists() and candidate.is_file():
                            return str(candidate)
                except Exception:
                    pass
        return ""

    def _write_chara_png(self, path, payload, image_path=None, require_image=False):
        source = (image_path or "").strip()
        local_source = self._ensure_local_card_image_path(source, "card", "write_chara_png") if source else ""
        if local_source and Path(local_source).exists():
            img = Image.open(local_source).convert("RGBA")
        else:
            if require_image:
                raise FileNotFoundError(f"No readable image source was available for card PNG export. Source was: {source[:200]}")
            img = Image.new("RGBA", (512, 768), (24, 24, 32, 255))

        # Character Card V2 PNG convention: write base64-encoded JSON into the
        # PNG tEXt chunk named "chara". SillyTavern and compatible frontends can
        # import this directly as a card image.
        metadata = PngInfo()
        json_text = json.dumps(payload, ensure_ascii=False)
        text_chunks = {
            "chara": base64.b64encode(json_text.encode("utf-8")).decode("ascii"),
            "ccf_raw": payload.get("data", {}).get("extensions", {}).get("raw_card", ""),
        }
        for k, v in text_chunks.items():
            metadata.add_text(k, v)
        img.save(path, "PNG", pnginfo=metadata)
        self._ensure_png_text_chunks(path, text_chunks, log_reason="write_chara_png")

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
    api.window = window
    webview.start(gui="qt", debug=False)

if __name__ == "__main__":
    main()
