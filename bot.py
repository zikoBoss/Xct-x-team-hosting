import os
import sys
import json
import time
import subprocess
import shutil
import zipfile
import threading
import re
import traceback
import hashlib
import base64
import signal
import platform
import tempfile
import io
import queue
import random
import string
import resource
import asyncio
import ast
import html
import importlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata as importlib_metadata

MIN_PYTHON_TELEGRAM_BOT_VERSION = (22, 7)
TELEGRAM_PACKAGE_SPEC = 'python-telegram-bot>=22.7,<23.0'
TELEGRAM_DIST_NAME = 'python-telegram-bot'
CONFLICTING_TELEGRAM_PACKAGES = ('telegram',)

def _safe_base_package_name(package_spec: str) -> str:
    return re.split(r'[\[=<>!~;\s]', (package_spec or '').strip(), 1)[0].strip()

def _normalize_package_spec(package_spec: str) -> str:
    base_name = _safe_base_package_name(package_spec).lower().replace('_', '-')
    if base_name in {'telegram', 'python-telegram-bot'}:
        return TELEGRAM_PACKAGE_SPEC
    return (package_spec or '').strip()

def _version_tuple(version: str) -> Tuple[int, ...]:
    numbers = re.findall(r'\d+', version or '')
    if not numbers:
        return (0,)
    return tuple(int(number) for number in numbers[:4])

def _get_distribution_version(dist_name: str) -> Optional[str]:
    try:
        return importlib_metadata.version(dist_name)
    except importlib_metadata.PackageNotFoundError:
        return None
    except Exception:
        return None

def _is_telegram_bot_version_compatible() -> bool:
    version = _get_distribution_version(TELEGRAM_DIST_NAME)
    return bool(version and _version_tuple(version) >= MIN_PYTHON_TELEGRAM_BOT_VERSION)

def _purge_conflicting_telegram_packages() -> None:
    for package_name in CONFLICTING_TELEGRAM_PACKAGES:
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'uninstall', '-y', package_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        except Exception:
            pass

REQUIRED_PACKAGES = [
    (TELEGRAM_PACKAGE_SPEC, 'telegram'),
    ('psutil>=5.9,<7.0', 'psutil'),
    ('aiohttp>=3.9,<4.0', 'aiohttp'),
    ('schedule>=1.2,<2.0', 'schedule'),
    ('requests>=2.31,<3.0', 'requests')
]

def install_required_packages():
    print('🔧 جاري التحقق من المكتبات المطلوبة...')

    for package_spec, import_name in REQUIRED_PACKAGES:
        normalized_spec = _normalize_package_spec(package_spec)
        base_name = _safe_base_package_name(normalized_spec).lower().replace('_', '-')
        installed_version = None
        needs_install = False

        try:
            __import__(import_name)
            if base_name == TELEGRAM_DIST_NAME:
                installed_version = _get_distribution_version(TELEGRAM_DIST_NAME)
                if not _is_telegram_bot_version_compatible():
                    print(f'  ♻️ إصدار python-telegram-bot الحالي غير متوافق: {installed_version or "غير معروف"}')
                    needs_install = True
            else:
                installed_version = _get_distribution_version(base_name)
        except ImportError:
            needs_install = True

        if not needs_install:
            version_text = f' ({installed_version})' if installed_version else ''
            print(f'  ✅ {normalized_spec} - موجود{version_text}')
            continue

        if base_name == TELEGRAM_DIST_NAME:
            _purge_conflicting_telegram_packages()

        print(f'  📦 جاري تثبيت/تحديث {normalized_spec}...')
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    '-m',
                    'pip',
                    'install',
                    '--upgrade',
                    '--no-cache-dir',
                    normalized_spec,
                    '--quiet',
                    '--no-warn-script-location'
                ],
                capture_output=True,
                text=True,
                timeout=180
            )
            if process.returncode != 0:
                raise RuntimeError(process.stderr.strip() or process.stdout.strip() or 'pip install failed')

            importlib.invalidate_caches()
            if import_name in sys.modules:
                del sys.modules[import_name]
            __import__(import_name)

            installed_version = _get_distribution_version(TELEGRAM_DIST_NAME if base_name == TELEGRAM_DIST_NAME else base_name)
            version_text = f' ({installed_version})' if installed_version else ''
            print(f'  ✅ تم تثبيت/تحديث {normalized_spec}{version_text}')
        except Exception as e:
            print(f'  ❌ فشل تثبيت {normalized_spec}: {e}')
            sys.exit(1)

    print('✅ جميع المكتبات جاهزة!\n')

install_required_packages()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut, BadRequest, Forbidden
import psutil
import schedule
import requests
import aiohttp

TELEGRAM_BOT_TOKEN = "8590832057:AAEq8caGs0VUqu1Svnx1e5WsGP1xZ-RNq-I"
ADMIN_IDS = [8695276303]

ERROR_REPORT_TRACE_LIMIT = 12000
ERROR_REPORT_CHUNK_SIZE = 3200

def _chunk_text(text: str, chunk_size: int = ERROR_REPORT_CHUNK_SIZE) -> List[str]:
    text = text or ""
    if not text:
        return [""]
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

def _build_error_messages(title: str, error_message: str, traceback_text: str,
                          extra_info: Optional[Dict[str, Any]] = None) -> List[str]:
    safe_title = html.escape(title or "خطأ غير معروف")
    safe_error = html.escape((error_message or "خطأ غير معروف")[:1500])
    safe_trace = html.escape((traceback_text or "لا يوجد تتبّع متاح")[:ERROR_REPORT_TRACE_LIMIT])

    info_lines = []
    if extra_info:
        for key, value in extra_info.items():
            if value is None or value == "":
                continue
            info_lines.append(f"<b>{html.escape(str(key))}:</b> <code>{html.escape(str(value))}</code>")

    summary = f"🚨 <b>{safe_title}</b>"
    if info_lines:
        summary += "\n\n" + "\n".join(info_lines)
    summary += f"\n\n<b>الخطأ:</b>\n<code>{safe_error}</code>"

    messages = [summary]
    trace_chunks = _chunk_text(safe_trace)
    total_chunks = len(trace_chunks)
    for index, chunk in enumerate(trace_chunks, 1):
        messages.append(f"📄 <b>التتبّع {index}/{total_chunks}</b>\n<pre>{chunk}</pre>")
    return messages

def send_error_report_sync(error_message: str, traceback_text: str,
                           extra_targets: Optional[List[int]] = None,
                           title: str = "خطأ فادح في البوت",
                           extra_info: Optional[Dict[str, Any]] = None):
    target_ids = list(dict.fromkeys(ADMIN_IDS + (extra_targets or [])))
    messages = _build_error_messages(title, error_message, traceback_text, extra_info)
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for target_id in target_ids:
        for message in messages:
            try:
                requests.post(
                    telegram_url,
                    data={
                        "chat_id": target_id,
                        "text": message,
                        "parse_mode": "HTML"
                    },
                    timeout=15
                )
            except Exception as e:
                print(f"❌ فشل إرسال تقرير الخطأ إلى {target_id}: {e}")

async def send_error_report(error_message: str, traceback_text: str,
                            extra_targets: Optional[List[int]] = None,
                            title: str = "خطأ فادح في البوت",
                            extra_info: Optional[Dict[str, Any]] = None):
    target_ids = list(dict.fromkeys(ADMIN_IDS + (extra_targets or [])))
    messages = _build_error_messages(title, error_message, traceback_text, extra_info)
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    for target_id in target_ids:
        for message in messages:
            try:
                await bot.send_message(chat_id=target_id, text=message, parse_mode=ParseMode.HTML)
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"❌ فشل إرسال تقرير الخطأ إلى {target_id}: {e}")

REQUIRED_CHANNEL = "@fpi_sx_channel"

BASE_DIR = Path(__file__).parent.absolute()
USERS_DIR = BASE_DIR / "users"
CACHE_DIR = BASE_DIR / "cache"
LOG_DIR = BASE_DIR / "logs"
UPLOAD_DIR = BASE_DIR / "uploads"
BACKUP_DIR = BASE_DIR / "backups"
CONFIG_DIR = BASE_DIR / "config"
CONSOLE_DIR = BASE_DIR / "consoles"

for folder in [USERS_DIR, CACHE_DIR, LOG_DIR, UPLOAD_DIR, BACKUP_DIR, CONFIG_DIR, CONSOLE_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

USERS_CONFIG_FILE = CONFIG_DIR / "users_config.json"
BANNED_USERS_FILE = CONFIG_DIR / "banned_users.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
SCHEDULE_FILE = CONFIG_DIR / "schedules.json"
ACTIVITY_LOG_FILE = LOG_DIR / "activity.log"
USER_RESOURCES_FILE = CONFIG_DIR / "user_resources.json"
BOT_ENV_CACHE_FILE = CONFIG_DIR / "bot_env_cache.json"

DEFAULT_USER_RESOURCES = {
    "max_memory_mb": 512,
    "max_cpu_percent": 50,
    "max_processes": 10,
    "max_disk_mb": 1000,
    "network_allowed": True,
    "escape_monitor": True,
    "auto_kill_on_escape": True
}

UNLIMITED_RESOURCES = {
    "max_memory_mb": 0,
    "max_cpu_percent": 0,
    "max_processes": 0,
    "max_disk_mb": 0,
    "network_allowed": True,
    "escape_monitor": True,
    "auto_kill_on_escape": True
}

@dataclass
class UserResources:
    user_id: int
    max_memory_mb: int = 512
    max_cpu_percent: int = 50
    max_processes: int = 10
    max_disk_mb: int = 1000
    network_allowed: bool = True
    escape_monitor: bool = True
    auto_kill_on_escape: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class AutoInstaller:

    _installed_cache: Set[str] = set()
    _cache_lock = threading.Lock()
    _env_cache: Dict[str, Dict[str, Any]] = {}
    _env_cache_loaded = False
    _env_cache_lock = threading.Lock()

    _IMPORT_TO_PACKAGE = {
        'requests': 'requests',
        'jwt': 'PyJWT',
        'PyJWT': 'PyJWT',
        'urllib3': 'urllib3',
        'aiohttp': 'aiohttp',
        'pytz': 'pytz',
        'bs4': 'beautifulsoup4',
        'beautifulsoup': 'beautifulsoup4',
        'PIL': 'Pillow',
        'pillow': 'Pillow',
        'cv2': 'opencv-python',
        'opencv': 'opencv-python',
        'telegram': 'python-telegram-bot',
        'telebot': 'pyTelegramBotAPI',
        'pyrogram': 'pyrogram',
        'aiogram': 'aiogram',
        'telethon': 'telethon',
        'flask': 'Flask',
        'django': 'Django',
        'fastapi': 'fastapi',
        'pandas': 'pandas',
        'numpy': 'numpy',
        'matplotlib': 'matplotlib',
        'scipy': 'scipy',
        'sklearn': 'scikit-learn',
        'scikit-learn': 'scikit-learn',
        'tensorflow': 'tensorflow',
        'torch': 'torch',
        'selenium': 'selenium',
        'playwright': 'playwright',
        'pymongo': 'pymongo',
        'sqlalchemy': 'SQLAlchemy',
        'redis': 'redis',
        'celery': 'celery',
        'paramiko': 'paramiko',
        'cryptography': 'cryptography',
        'boto3': 'boto3',
        'PIL': 'Pillow',
        'bs4': 'beautifulsoup4',
        'lxml': 'lxml',
        'yaml': 'PyYAML',
        'pyyaml': 'PyYAML',
        'toml': 'toml',
        'click': 'click',
        'typer': 'typer',
        'rich': 'rich',
        'tqdm': 'tqdm',
        'colorama': 'colorama',
        'dotenv': 'python-dotenv',
        'environs': 'environs',
        'python-jose': 'python-jose',
        'jose': 'python-jose',
        'bcrypt': 'bcrypt',
        'pydantic': 'pydantic',
        'uvicorn': 'uvicorn',
        'gunicorn': 'gunicorn',
        'httpx': 'httpx',
        'websockets': 'websockets',
        'socketio': 'python-socketio',
        'motor': 'motor',
        'beanie': 'beanie',
        'mongoengine': 'mongoengine',
        'peewee': 'peewee',
        'tortoise': 'tortoise-orm',
        'psycopg2': 'psycopg2-binary',
        'mysql-connector': 'mysql-connector-python',
        'pymysql': 'PyMySQL',
        'sqlite3': None,
        'json': None,
        'csv': None,
        'os': None,
        'sys': None,
        'time': None,
        'datetime': None,
        're': None,
        'math': None,
        'random': None,
        'string': None,
        'hashlib': None,
        'base64': None,
        'binascii': None,
        'pickle': None,
        'threading': None,
        'asyncio': None,
        'subprocess': None,
        'socket': None,
        'ssl': None,
        'typing': None,
        'pathlib': None,
        'collections': None,
        'itertools': None,
        'functools': None,
        'logging': None,
        'argparse': None,
        'configparser': None,
        'tempfile': None,
        'shutil': None,
        'glob': None,
        'zipfile': None,
        'tarfile': None,
    }

    @staticmethod
    def _load_env_cache():
        with AutoInstaller._env_cache_lock:
            if AutoInstaller._env_cache_loaded:
                return
            if BOT_ENV_CACHE_FILE.exists():
                try:
                    AutoInstaller._env_cache = json.loads(BOT_ENV_CACHE_FILE.read_text(encoding='utf-8'))
                except Exception:
                    AutoInstaller._env_cache = {}
            else:
                AutoInstaller._env_cache = {}
            AutoInstaller._env_cache_loaded = True

    @staticmethod
    def _save_env_cache():
        with AutoInstaller._env_cache_lock:
            BOT_ENV_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            BOT_ENV_CACHE_FILE.write_text(
                json.dumps(AutoInstaller._env_cache, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )

    @staticmethod
    def _build_bot_fingerprint(bot_folder: Path) -> str:
        hasher = hashlib.sha256()
        files_to_track = []

        for req_name in ('requirements.txt', 'requirement.txt', 'req.txt'):
            req_path = bot_folder / req_name
            if req_path.exists():
                files_to_track.append(req_path)

        files_to_track.extend(bot_folder.rglob('*.py'))

        for file_path in sorted(files_to_track, key=lambda p: str(p.relative_to(bot_folder)).lower()):
            try:
                stat = file_path.stat()
                hasher.update(str(file_path.relative_to(bot_folder)).encode('utf-8', 'ignore'))
                hasher.update(str(stat.st_size).encode('utf-8'))
                hasher.update(str(stat.st_mtime_ns).encode('utf-8'))
            except FileNotFoundError:
                continue

        return hasher.hexdigest()

    @staticmethod
    def read_requirements(directory: Path) -> List[str]:

        req_files = ['requirements.txt', 'requirement.txt', 'req.txt']
        packages = []
        discovered_files = []

        for req_file in req_files:
            root_candidate = directory / req_file
            if root_candidate.exists():
                discovered_files.append(root_candidate)
            for nested_candidate in directory.rglob(req_file):
                if nested_candidate not in discovered_files:
                    discovered_files.append(nested_candidate)

        for req_path in discovered_files:
            try:
                with open(req_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for raw_line in f:
                        line = raw_line.split('
                        if not line:
                            continue

                        lowered = line.lower()
                        if lowered.startswith(('--index-url', '--extra-index-url', '--trusted-host', '--find-links', '-f ')):
                            continue
                        if lowered.startswith(('-r ', '--requirement ', '-e ', '--editable ')):
                            continue
                        if line.startswith(('.', '/', '../', '~/')):
                            continue
                        if lowered.startswith(('git+', 'http://', 'https://', 'svn+', 'hg+')):
                            egg_match = re.search(r'
                            if egg_match:
                                packages.append(egg_match.group(1).strip())
                            continue
                        if ' @ ' in line:
                            line = line.split(' @ ', 1)[0].strip()

                        package = re.split(r'[=<>!~;\[]', line, 1)[0].strip()
                        if package:
                            packages.append(package)
            except Exception as e:
                log_activity(f"خطأ في قراءة {req_path}: {e}", "ERROR")

        return packages

    @staticmethod
    def _extract_imports_from_file(file_path: Path) -> Set[str]:

        imports = set()
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if getattr(node, 'level', 0):
                            continue
                        if node.module:
                            imports.add(node.module.split('.')[0])
            except SyntaxError:

                import_patterns = [
                    r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                    r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                ]
                for pattern in import_patterns:
                    matches = re.findall(pattern, content, re.MULTILINE)
                    imports.update(matches)
        except Exception:
            pass
        return imports

    @staticmethod
    def _extract_imports_from_directory(directory: Path) -> Set[str]:

        all_imports = set()
        for py_file in directory.rglob("*.py"):
            all_imports.update(AutoInstaller._extract_imports_from_file(py_file))
        return all_imports

    @staticmethod
    def _get_local_module_names(directory: Path) -> Set[str]:

        local_modules = set()
        for py_file in directory.rglob("*.py"):
            try:
                rel = py_file.relative_to(directory)
            except Exception:
                continue

            if py_file.name == '__init__.py' and rel.parts:
                local_modules.add(rel.parts[0].lower())
            else:
                local_modules.add(py_file.stem.lower())
            if rel.parts:
                local_modules.add(rel.parts[0].lower())
        return local_modules

    @staticmethod
    def _get_package_name_from_import(module_name: str) -> Optional[str]:

        module_lower = module_name.lower().replace('_', '-')

        if module_lower in AutoInstaller._IMPORT_TO_PACKAGE:
            return AutoInstaller._IMPORT_TO_PACKAGE[module_lower]

        if module_lower == 'pil':
            return 'Pillow'
        if module_lower == 'cv2':
            return 'opencv-python'
        if module_lower == 'sklearn':
            return 'scikit-learn'

        return None

    @staticmethod
    def is_package_installed(package_name: str) -> bool:

        normalized_spec = _normalize_package_spec(package_name)
        base_name = _safe_base_package_name(normalized_spec).lower().replace('_', '-')
        cache_keys = {package_name, normalized_spec, base_name}

        if not normalized_spec:
            return True

        with AutoInstaller._cache_lock:
            if any(key in AutoInstaller._installed_cache for key in cache_keys if key):
                return True

        if base_name == TELEGRAM_DIST_NAME:
            if _is_telegram_bot_version_compatible():
                with AutoInstaller._cache_lock:
                    AutoInstaller._installed_cache.update(key for key in cache_keys if key)
                return True
            return False

        module_name = base_name.replace('-', '_')

        try:
            __import__(module_name)
            with AutoInstaller._cache_lock:
                AutoInstaller._installed_cache.update(key for key in cache_keys if key)
            return True
        except ImportError:
            pass

        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'show', base_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                with AutoInstaller._cache_lock:
                    AutoInstaller._installed_cache.update(key for key in cache_keys if key)
                return True
        except Exception:
            pass

        return False

    @staticmethod
    def install_package(package_name: str, console: Optional['UserBotConsole'] = None) -> Tuple[bool, str]:

        normalized_spec = _normalize_package_spec(package_name)
        base_name = _safe_base_package_name(normalized_spec).lower().replace('_', '-')

        if not normalized_spec:
            return True, 'لا شيء لتثبيته'

        log_msg = f"📦 جاري تثبيت: {normalized_spec}"
        log_activity(log_msg)
        if console:
            console.add_line(log_msg)

        try:
            if base_name == TELEGRAM_DIST_NAME:
                _purge_conflicting_telegram_packages()

            process = subprocess.run(
                [
                    sys.executable,
                    '-m',
                    'pip',
                    'install',
                    '--upgrade',
                    '--no-cache-dir',
                    normalized_spec,
                    '--quiet',
                    '--no-warn-script-location'
                ],
                capture_output=True,
                text=True,
                timeout=180
            )

            if process.returncode == 0:
                success_msg = f"✅ تم تثبيت {normalized_spec}"
                installed_version = _get_distribution_version(TELEGRAM_DIST_NAME if base_name == TELEGRAM_DIST_NAME else base_name)
                if installed_version:
                    success_msg += f" ({installed_version})"
                log_activity(success_msg)
                if console:
                    console.add_line(success_msg)
                with AutoInstaller._cache_lock:
                    AutoInstaller._installed_cache.update(
                        key for key in {package_name, normalized_spec, base_name} if key
                    )
                return True, success_msg
            else:
                error_msg = f"❌ فشل تثبيت {normalized_spec}: {process.stderr[:200] or process.stdout[:200]}"
                log_activity(error_msg, 'ERROR')
                if console:
                    console.add_line(error_msg)
                return False, error_msg

        except subprocess.TimeoutExpired:
            error_msg = f"⏱️ انتهى الوقت أثناء تثبيت {normalized_spec}"
            log_activity(error_msg, 'ERROR')
            if console:
                console.add_line(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"❌ خطأ في تثبيت {normalized_spec}: {e}"
            log_activity(error_msg, 'ERROR')
            if console:
                console.add_line(error_msg)
            return False, error_msg

    @staticmethod
    def install_packages(package_list: List[str], console: Optional['UserBotConsole'] = None) -> Tuple[int, int, List[str]]:

        if not package_list:
            return 0, 0, []

        success_count = 0
        fail_count = 0
        failed_packages = []

        unique_packages = list(set(p for p in package_list if p))

        if console:
            console.add_line(f"🔧 جاري التحقق من {len(unique_packages)} مكتبة...")

        for package in unique_packages:
            if AutoInstaller.is_package_installed(package):
                if console:
                    console.add_line(f"✅ {package} - موجود")
                success_count += 1
                continue

            success, _ = AutoInstaller.install_package(package, console)
            if success:
                success_count += 1
            else:
                fail_count += 1
                failed_packages.append(package)

            time.sleep(0.5)

        return success_count, fail_count, failed_packages

    @staticmethod
    def setup_bot_environment(bot_folder: Path, console: Optional['UserBotConsole'] = None) -> Tuple[bool, str]:

        cache_key = str(bot_folder.resolve())
        if cache_key in AutoInstaller._env_cache:
            del AutoInstaller._env_cache[cache_key]
            AutoInstaller._save_env_cache()
            if console:
                console.add_line("🗑️ تم حذف كاش قديم لهذا البوت، سيتم التثبيت من جديد")

        AutoInstaller._load_env_cache()
        cache_key = str(bot_folder.resolve())
        fingerprint = AutoInstaller._build_bot_fingerprint(bot_folder)
        cached = AutoInstaller._env_cache.get(cache_key)

        if cached and cached.get('fingerprint') == fingerprint:
            cached_packages = cached.get('packages', [])
            if console:
                console.add_line("⚡ تم استخدام كاش البيئة السابقة")
            return True, f"تم استخدام كاش البيئة ({len(cached_packages)} مكتبة)"

        if console:
            console.add_line("🔍 جاري البحث عن المكتبات المطلوبة...")

        req_packages = AutoInstaller.read_requirements(bot_folder)

        packages_to_install = set()
        if req_packages:
            packages_to_install = set(req_packages)
            if console:
                console.add_line(f"📄 تم العثور على requirements.txt يحتوي على {len(req_packages)} مكتبة")
        else:
            if console:
                console.add_line("📄 لم يتم العثور على requirements.txt، سيتم استخراج المكتبات من الاستيرادات...")
            all_imports = AutoInstaller._extract_imports_from_directory(bot_folder)
            local_modules = AutoInstaller._get_local_module_names(bot_folder)

            def normalize(s: str) -> str:
                return s.lower().replace('-', '_')

            normalized_local = {normalize(name) for name in local_modules}
            skipped = set()
            for imp in all_imports:
                norm_imp = normalize(imp)
                if norm_imp in normalized_local:
                    skipped.add(imp)
                    continue
                pkg = AutoInstaller._get_package_name_from_import(imp)
                if pkg:
                    packages_to_install.add(pkg)

            if console and skipped:
                console.add_line(f"🧩 تم تجاهل {len(skipped)} موديول محلي: {', '.join(list(skipped)[:10])}")
            if console:
                console.add_line(f"📦 تم استخراج {len(packages_to_install)} مكتبة من الاستيرادات")

        if not packages_to_install:
            AutoInstaller._env_cache[cache_key] = {
                'fingerprint': fingerprint,
                'packages': [],
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            AutoInstaller._save_env_cache()
            return True, "لا توجد مكتبات خارجية تحتاج تثبيت"

        if console:
            console.add_line(f"📦 سيتم تثبيت {len(packages_to_install)} مكتبة")

        success, fail, failed = AutoInstaller.install_packages(sorted(packages_to_install), console)

        summary = f"✅ {success} مثبتة | ❌ {fail} فشلت"
        if console:
            console.add_line(f"📊 {summary}")

        if fail > 0:
            warning_msg = f"تم تجهيز البيئة جزئياً: {summary} | غير المثبتة: {', '.join(failed[:8])}"
            if console:
                console.add_line(f"⚠️ {warning_msg}")
            return True, warning_msg

        AutoInstaller._env_cache[cache_key] = {
            'fingerprint': fingerprint,
            'packages': sorted(packages_to_install),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        AutoInstaller._save_env_cache()

        return True, f"تم تجهيز البيئة بنجاح ({success} مكتبة)"

class UserResourcesManager:

    _cache: Dict[int, UserResources] = {}
    _cache_lock = threading.Lock()

    @staticmethod
    def load_all_resources() -> Dict[int, UserResources]:
        if USER_RESOURCES_FILE.exists():
            try:
                with open(USER_RESOURCES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {int(k): UserResources.from_dict(v) for k, v in data.items()}
            except:
                pass
        return {}

    @staticmethod
    def save_all_resources(resources: Dict[int, UserResources]):
        with open(USER_RESOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump({str(k): v.to_dict() for k, v in resources.items()}, f, indent=4, ensure_ascii=False)

    @staticmethod
    def get_user_resources(user_id: int) -> UserResources:
        with UserResourcesManager._cache_lock:
            if user_id in UserResourcesManager._cache:
                return UserResourcesManager._cache[user_id]

            all_resources = UserResourcesManager.load_all_resources()
            if user_id not in all_resources:
                resources = UserResources(user_id=user_id, **DEFAULT_USER_RESOURCES)
                all_resources[user_id] = resources
                UserResourcesManager.save_all_resources(all_resources)
            else:
                resources = all_resources[user_id]

            UserResourcesManager._cache[user_id] = resources
            return resources

    @staticmethod
    def set_user_resources(user_id: int, **kwargs):
        with UserResourcesManager._cache_lock:
            all_resources = UserResourcesManager.load_all_resources()
            if user_id in all_resources:
                resources = all_resources[user_id]
                for key, value in kwargs.items():
                    if hasattr(resources, key):
                        setattr(resources, key, value)
                resources.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                resources = UserResources(user_id=user_id, **kwargs)
                all_resources[user_id] = resources

            UserResourcesManager._cache[user_id] = resources
            UserResourcesManager.save_all_resources(all_resources)
            return resources

    @staticmethod
    def set_unlimited_resources(user_id: int):
        return UserResourcesManager.set_user_resources(user_id, **UNLIMITED_RESOURCES)

    @staticmethod
    def reset_to_default(user_id: int):
        return UserResourcesManager.set_user_resources(user_id, **DEFAULT_USER_RESOURCES)

    @staticmethod
    def format_resources_text(resources: UserResources) -> str:
        mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
        cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
        proc = "∞" if resources.max_processes == 0 else str(resources.max_processes)
        disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

        return (
            f"📊 *مواردك:*\n"
            f"💾 الذاكرة: `{mem}`\n"
            f"💻 CPU: `{cpu}`\n"
            f"🔢 العمليات: `{proc}`\n"
            f"💿 المساحة: `{disk}`\n"
            f"🌐 الشبكة: `{'✅' if resources.network_allowed else '❌'}`\n"
            f"👁️ مراقبة الهروب: `{'✅' if resources.escape_monitor else '❌'}`"
        )

class EscapeMonitor:

    monitored_processes: Dict[str, Dict] = {}
    _lock = threading.Lock()

    @staticmethod
    def start_monitoring(bot_id: str, process: subprocess.Popen, user_id: int, allowed_dir: Path, resources: UserResources):
        if not resources.escape_monitor:
            return

        with EscapeMonitor._lock:
            EscapeMonitor.monitored_processes[bot_id] = {
                'process': process,
                'user_id': user_id,
                'allowed_dir': allowed_dir,
                'resources': resources,
                'killed': False
            }

        monitor_thread = threading.Thread(
            target=EscapeMonitor._monitor_loop,
            args=(bot_id,),
            daemon=True
        )
        monitor_thread.start()

    @staticmethod
    def _monitor_loop(bot_id: str):
        with EscapeMonitor._lock:
            if bot_id not in EscapeMonitor.monitored_processes:
                return
            data = EscapeMonitor.monitored_processes[bot_id]

        process = data['process']
        user_id = data['user_id']
        allowed_dir = data['allowed_dir']
        resources = data['resources']

        try:
            parent = psutil.Process(process.pid)

            while process.poll() is None:
                with EscapeMonitor._lock:
                    if bot_id in EscapeMonitor.monitored_processes and EscapeMonitor.monitored_processes[bot_id].get('killed'):
                        return

                try:
                    all_processes = [parent] + parent.children(recursive=True)

                    for child in all_processes:
                        try:
                            if hasattr(child, 'open_files'):
                                for file in child.open_files():
                                    file_path = Path(file.path)
                                    if not EscapeMonitor._is_path_allowed(file_path, allowed_dir):
                                        escape_path = str(file_path)
                                        log_activity(f"🚨 هروب من البوت {bot_id}: محاولة الوصول إلى {escape_path}", "WARNING")

                                        asyncio.run(EscapeMonitor._notify_admin(bot_id, user_id, escape_path))

                                        if resources.auto_kill_on_escape:
                                            log_activity(f"💀 قتل البوت {bot_id} بسبب محاولة هروب", "WARNING")
                                            EscapeMonitor._kill_process_tree(parent)
                                            with EscapeMonitor._lock:
                                                if bot_id in EscapeMonitor.monitored_processes:
                                                    EscapeMonitor.monitored_processes[bot_id]['killed'] = True
                                            return
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    if not resources.network_allowed:
                        for child in all_processes:
                            try:
                                if hasattr(child, 'connections'):
                                    conns = child.connections()
                                    for conn in conns:
                                        if conn.status == 'ESTABLISHED':
                                            log_activity(f"🚨 اتصال شبكي محظور من {bot_id}: {conn.raddr}", "WARNING")
                                            if resources.auto_kill_on_escape:
                                                EscapeMonitor._kill_process_tree(parent)
                                                with EscapeMonitor._lock:
                                                    if bot_id in EscapeMonitor.monitored_processes:
                                                        EscapeMonitor.monitored_processes[bot_id]['killed'] = True
                                                return
                            except:
                                pass

                    time.sleep(2)

                except Exception as e:
                    if "No such process" not in str(e):
                        log_activity(f"خطأ في مراقبة {bot_id}: {e}", "ERROR")
                    break

        except psutil.NoSuchProcess:
            pass
        finally:
            with EscapeMonitor._lock:
                if bot_id in EscapeMonitor.monitored_processes:
                    del EscapeMonitor.monitored_processes[bot_id]

    @staticmethod
    async def _notify_admin(bot_id: str, user_id: int, escape_path: str):
        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"🚨 *محاولة هروب!*\n\n👤 المستخدم: `{user_id}`\n🤖 البوت: `{bot_id}`\n📁 المسار: `{escape_path}`\n\n⏰ الوقت: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
        except:
            pass

    @staticmethod
    def _kill_process_tree(parent: psutil.Process):
        try:
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except:
                    pass
            parent.kill()
        except:
            pass

    @staticmethod
    def _is_path_allowed(path: Path, allowed_dir: Path) -> bool:
        try:
            if not path or str(path) == '.':
                return True

            if not path.exists():
                return True

            path_resolved = path.resolve()
            allowed_resolved = allowed_dir.resolve()

            try:
                path_resolved.relative_to(allowed_resolved)
                return True
            except ValueError:
                pass

            allowed_system = [
                '/usr', '/lib', '/lib64', '/etc/localtime',
                '/dev/null', '/dev/zero', '/dev/random', '/dev/urandom',
                '/dev/stdin', '/dev/stdout', '/dev/stderr',
                '/proc/self', '/sys', '/tmp'
            ]
            path_str = str(path_resolved)
            for allowed in allowed_system:
                if path_str.startswith(allowed):
                    return True

            return False

        except Exception:
            return True

@dataclass
class BotModes:
    maintenance_mode: bool = False
    maintenance_message: str = "🛠 البوت في وضع الصيانة، يرجى المحاولة لاحقاً."
    privacy_mode: bool = False
    privacy_message: str = "🔒 البوت في وضع خصوصية، غير متاح حالياً."
    owner_only_mode: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class BroadcastSettings:
    subscribers_file: Path = CONFIG_DIR / "subscribers.json"
    broadcast_stats_file: Path = CONFIG_DIR / "broadcast_stats.json"

    def load_subscribers(self) -> List[int]:
        if self.subscribers_file.exists():
            try:
                with open(self.subscribers_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def save_subscribers(self, subscribers: List[int]):
        with open(self.subscribers_file, 'w', encoding='utf-8') as f:
            json.dump(subscribers, f, indent=4, ensure_ascii=False)

    def add_subscriber(self, user_id: int):
        subscribers = self.load_subscribers()
        if user_id not in subscribers:
            subscribers.append(user_id)
            self.save_subscribers(subscribers)

broadcast_settings = BroadcastSettings()

class UserSandbox:
    @staticmethod
    def get_user_dir(user_id: int) -> Path:
        user_dir = USERS_DIR / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "bots").mkdir(exist_ok=True)
        (user_dir / "logs").mkdir(exist_ok=True)
        (user_dir / "consoles").mkdir(exist_ok=True)
        (user_dir / "backups").mkdir(exist_ok=True)
        (user_dir / "uploads").mkdir(exist_ok=True)
        (user_dir / "tmp").mkdir(exist_ok=True)
        return user_dir

    @staticmethod
    def get_user_bots_dir(user_id: int) -> Path:
        return UserSandbox.get_user_dir(user_id) / "bots"

    @staticmethod
    def get_user_logs_dir(user_id: int) -> Path:
        return UserSandbox.get_user_dir(user_id) / "logs"

    @staticmethod
    def get_user_consoles_dir(user_id: int) -> Path:
        return UserSandbox.get_user_dir(user_id) / "consoles"

    @staticmethod
    def get_disk_usage(user_id: int) -> int:
        user_dir = UserSandbox.get_user_dir(user_id)
        try:
            total_size = sum(f.stat().st_size for f in user_dir.rglob('*') if f.is_file())
            return total_size // (1024 * 1024)
        except:
            return 0

class SubscriptionSystem:
    VERIFIED_USERS_FILE = CONFIG_DIR / "verified_users.json"

    @staticmethod
    def load_verified() -> List[int]:
        if SubscriptionSystem.VERIFIED_USERS_FILE.exists():
            try:
                with open(SubscriptionSystem.VERIFIED_USERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    @staticmethod
    def save_verified(verified: List[int]):
        with open(SubscriptionSystem.VERIFIED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(verified, f, indent=4, ensure_ascii=False)

    @staticmethod
    def is_verified(user_id: int) -> bool:
        return user_id in SubscriptionSystem.load_verified()

    @staticmethod
    def verify_user(user_id: int):
        verified = SubscriptionSystem.load_verified()
        if user_id not in verified:
            verified.append(user_id)
            SubscriptionSystem.save_verified(verified)

    @staticmethod
    async def check_subscription(user_id: int, bot: Bot) -> bool:
        if not REQUIRED_CHANNEL or REQUIRED_CHANNEL == "@fpi_sx_channel":
            return True
        if SubscriptionSystem.is_verified(user_id):
            return True
        try:
            member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if member.status in ['member', 'administrator', 'creator']:
                SubscriptionSystem.verify_user(user_id)
                return True
            return False
        except:
            return True

class BanSystem:
    @staticmethod
    def load_banned() -> Dict[int, Dict]:
        if BANNED_USERS_FILE.exists():
            try:
                with open(BANNED_USERS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
            except:
                pass
        return {}

    @staticmethod
    def save_banned(banned: Dict[int, Dict]):
        with open(BANNED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(banned, f, indent=4, ensure_ascii=False)

    @staticmethod
    def is_banned(user_id: int) -> Tuple[bool, Optional[str]]:
        banned = BanSystem.load_banned()
        if user_id in banned:
            return True, banned[user_id].get('reason', 'لا يوجد سبب')
        return False, None

    @staticmethod
    def ban_user(user_id: int, reason: str, banned_by: int):
        banned = BanSystem.load_banned()
        banned[user_id] = {
            'reason': reason,
            'banned_by': banned_by,
            'banned_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'permanent': True
        }
        BanSystem.save_banned(banned)
        log_activity(f"🚫 تم حظر المستخدم {user_id} - السبب: {reason}")

    @staticmethod
    def unban_user(user_id: int):
        banned = BanSystem.load_banned()
        if user_id in banned:
            del banned[user_id]
            BanSystem.save_banned(banned)
            log_activity(f"✅ تم إلغاء حظر المستخدم {user_id}")

POINTS_CONFIG_FILE = CONFIG_DIR / "points_config.json"
USER_POINTS_FILE = CONFIG_DIR / "user_points.json"
POINTS_CODES_FILE = CONFIG_DIR / "points_codes.json"
INVITE_LINKS_FILE = CONFIG_DIR / "invite_links.json"

@dataclass
class PointsConfig:
    points_per_upload: int = 5
    points_per_update: int = 0
    points_per_invite: int = 5

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

def load_points_config() -> PointsConfig:
    if POINTS_CONFIG_FILE.exists():
        try:
            with open(POINTS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return PointsConfig.from_dict(json.load(f))
        except:
            pass
    return PointsConfig()

def save_points_config(config: PointsConfig):
    with open(POINTS_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config.to_dict(), f, indent=4, ensure_ascii=False)

points_config = load_points_config()

class PointsSystem:
    _cache: Dict[int, Dict] = {}
    _cache_lock = threading.Lock()

    @staticmethod
    def load_user_points() -> Dict[int, Dict]:
        if USER_POINTS_FILE.exists():
            try:
                with open(USER_POINTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
            except:
                pass
        return {}

    @staticmethod
    def save_user_points(points_data: Dict[int, Dict]):
        with open(USER_POINTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(points_data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def get_user_points(user_id: int) -> int:
        with PointsSystem._cache_lock:
            if user_id in PointsSystem._cache:
                return PointsSystem._cache[user_id].get('points', 0)

        points_data = PointsSystem.load_user_points()
        return points_data.get(user_id, {}).get('points', 0)

    @staticmethod
    def add_points(user_id: int, points: int, reason: str = "") -> int:
        with PointsSystem._cache_lock:
            points_data = PointsSystem.load_user_points()
            if user_id not in points_data:
                points_data[user_id] = {'points': 0, 'history': []}

            points_data[user_id]['points'] += points
            points_data[user_id]['history'].append({
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'points': points,
                'reason': reason
            })

            PointsSystem._cache[user_id] = points_data[user_id]
            PointsSystem.save_user_points(points_data)
            log_activity(f"تم إضافة {points} نقطة للمستخدم {user_id} - السبب: {reason}")
            return points_data[user_id]['points']

class PointsCodesSystem:
    @staticmethod
    def load_codes() -> Dict[str, Dict]:
        if POINTS_CODES_FILE.exists():
            try:
                with open(POINTS_CODES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    @staticmethod
    def save_codes(codes: Dict[str, Dict]):
        with open(POINTS_CODES_FILE, 'w', encoding='utf-8') as f:
            json.dump(codes, f, indent=4, ensure_ascii=False)

    @staticmethod
    def generate_code(points: int, max_uses: int, expiry_days: int, created_by: int) -> str:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        codes = PointsCodesSystem.load_codes()
        codes[code] = {
            'points': points,
            'max_uses': max_uses,
            'used_count': 0,
            'used_by': [],
            'created_by': created_by,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'expiry': (datetime.now() + timedelta(days=expiry_days)).strftime("%Y-%m-%d %H:%M:%S"),
            'active': True
        }
        PointsCodesSystem.save_codes(codes)
        return code

    @staticmethod
    def use_code(code: str, user_id: int) -> Tuple[bool, str, int]:
        codes = PointsCodesSystem.load_codes()
        if code not in codes:
            return False, "❌ الكود غير موجود", 0

        code_data = codes[code]
        if not code_data['active']:
            return False, "❌ الكود غير نشط", 0
        if user_id in code_data['used_by']:
            return False, "❌ لقد استخدمت هذا الكود مسبقاً", 0
        if code_data['used_count'] >= code_data['max_uses']:
            return False, "❌ الكود وصل للحد الأقصى من الاستخدامات", 0

        expiry_date = datetime.strptime(code_data['expiry'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expiry_date:
            return False, "❌ انتهت صلاحية الكود", 0

        points = code_data['points']
        new_total = PointsSystem.add_points(user_id, points, f"استخدام كود: {code}")

        codes[code]['used_count'] += 1
        codes[code]['used_by'].append(user_id)
        if codes[code]['used_count'] >= codes[code]['max_uses']:
            codes[code]['active'] = False

        PointsCodesSystem.save_codes(codes)
        return True, f"✅ تم إضافة {points} نقطة", new_total

    @staticmethod
    def get_all_codes() -> Dict[str, Dict]:
        return PointsCodesSystem.load_codes()

class InviteSystem:
    @staticmethod
    def load_invites() -> Dict[str, Dict]:
        if INVITE_LINKS_FILE.exists():
            try:
                with open(INVITE_LINKS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    @staticmethod
    def save_invites(invites: Dict[str, Dict]):
        with open(INVITE_LINKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(invites, f, indent=4, ensure_ascii=False)

    @staticmethod
    def generate_invite_code(user_id: int) -> str:
        invite_code = hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:8].upper()
        invites = InviteSystem.load_invites()
        invites[str(user_id)] = {
            'code': invite_code,
            'invited_users': [],
            'total_invites': 0,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        InviteSystem.save_invites(invites)
        return invite_code

    @staticmethod
    def get_invite_code(user_id: int) -> str:
        invites = InviteSystem.load_invites()
        user_id_str = str(user_id)
        if user_id_str not in invites:
            return InviteSystem.generate_invite_code(user_id)
        return invites[user_id_str]['code']

    @staticmethod
    def get_invite_stats(user_id: int) -> Dict:
        invites = InviteSystem.load_invites()
        user_id_str = str(user_id)
        if user_id_str not in invites:
            code = InviteSystem.generate_invite_code(user_id)
            return {'code': code, 'total_invites': 0, 'invited_users': []}
        user_data = invites[user_id_str]
        return {
            'code': user_data.get('code', 'غير متوفر'),
            'total_invites': user_data.get('total_invites', 0),
            'invited_users': user_data.get('invited_users', [])
        }

    @staticmethod
    def add_invite(inviter_id: int, invited_id: int):

        invites = InviteSystem.load_invites()
        inviter_str = str(inviter_id)
        if inviter_str not in invites:
            InviteSystem.generate_invite_code(inviter_id)
            invites = InviteSystem.load_invites()
        if invited_id not in invites[inviter_str].get('invited_users', []):
            invites[inviter_str]['invited_users'].append(invited_id)
            invites[inviter_str]['total_invites'] += 1
            InviteSystem.save_invites(invites)
            PointsSystem.add_points(inviter_id, points_config.points_per_invite, f"دعوة مستخدم {invited_id}")
            log_activity(f"تمت دعوة المستخدم {invited_id} من قبل {inviter_id}")
            return True
        return False

@dataclass
class SystemSettings:
    auto_restart: bool = True
    auto_restart_max_attempts: int = 5
    auto_restart_delay: int = 10
    health_check_interval: int = 60
    notification_on_stop: bool = True
    backup_auto: bool = True
    backup_interval_days: int = 7
    log_retention_days: int = 30
    console_max_lines: int = 2000
    bot_modes: BotModes = field(default_factory=BotModes)

    def to_dict(self):
        data = asdict(self)
        data['bot_modes'] = self.bot_modes.to_dict()
        return data

    @classmethod
    def from_dict(cls, data):
        modes_data = data.pop('bot_modes', {})
        instance = cls(**data)
        instance.bot_modes = BotModes.from_dict(modes_data)
        return instance

def load_settings() -> SystemSettings:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return SystemSettings.from_dict(json.load(f))
        except:
            pass
    return SystemSettings()

def save_settings(settings: SystemSettings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings.to_dict(), f, indent=4, ensure_ascii=False)

system_settings = load_settings()

def log_activity(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    try:
        with open(ACTIVITY_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass
    print(log_entry.strip())

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def check_bot_modes(user_id: int) -> Tuple[bool, str]:
    modes = system_settings.bot_modes
    if modes.maintenance_mode and user_id not in ADMIN_IDS:
        return False, modes.maintenance_message
    if modes.privacy_mode and user_id not in ADMIN_IDS:
        return False, modes.privacy_message
    return True, ""

async def safe_send_message(chat_id, text: str, reply_markup=None, parse_mode=None):
    try:
        return await chat_id.send_message(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Can't parse entities" in str(e) and parse_mode:
            return await chat_id.send_message(text, reply_markup=reply_markup, parse_mode=None)
        raise

async def safe_edit_message(query, text: str, reply_markup=None, parse_mode=None):
    try:
        return await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Can't parse entities" in str(e) and parse_mode:
            return await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
        elif "Message is not modified" in str(e):
            pass
        else:
            raise

def escape_markdown(text: str) -> str:
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

@dataclass
class UserBotConfig:
    id: str
    user_id: int
    name: str
    folder: str
    main_file: str
    added_at: str
    description: str = ""
    auto_start: bool = False
    restart_count: int = 0
    last_restart: Optional[str] = None
    active: bool = True

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class UserBotConsole:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.lines: List[str] = []
        self.max_lines = system_settings.console_max_lines
        self.lock = threading.Lock()

    def add_line(self, line: str):
        with self.lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.lines.append(f"[{timestamp}] {line}")
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines:]

    def get_output(self, lines: Optional[int] = None) -> str:
        with self.lock:
            if lines is None or lines >= len(self.lines):
                return '\n'.join(self.lines)
            return '\n'.join(self.lines[-lines:])

    def get_all_output(self) -> str:
        with self.lock:
            return '\n'.join(self.lines)

    def get_line_count(self) -> int:
        with self.lock:
            return len(self.lines)

    def clear(self):
        with self.lock:
            self.lines = []

    def save_to_file(self, user_id: int) -> Path:
        console_file = UserSandbox.get_user_consoles_dir(user_id) / f"{self.bot_id}_console.log"
        with open(console_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.lines))
        return console_file

class UserBotManager:
    running_bots: Dict[str, subprocess.Popen] = {}
    bot_consoles: Dict[str, UserBotConsole] = {}
    bot_stdin_pipes: Dict[str, Any] = {}
    bot_start_times: Dict[str, datetime] = {}
    _output_threads: Dict[str, threading.Thread] = {}
    _stop_events: Dict[str, threading.Event] = {}

    @staticmethod
    def get_user_config_file(user_id: int) -> Path:
        return UserSandbox.get_user_dir(user_id) / "bots_config.json"

    @staticmethod
    def load_user_bots(user_id: int) -> List[UserBotConfig]:
        config_file = UserBotManager.get_user_config_file(user_id)
        if not config_file.exists():
            return []
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [UserBotConfig.from_dict(b) for b in data]
        except Exception as e:
            log_activity(f"خطأ في تحميل بوتات المستخدم {user_id}: {e}")
            return []

    @staticmethod
    def save_user_bots(user_id: int, bots: List[UserBotConfig]):
        config_file = UserBotManager.get_user_config_file(user_id)
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump([b.to_dict() for b in bots], f, indent=4, ensure_ascii=False)

    @staticmethod
    def generate_bot_id(user_id: int) -> str:
        timestamp = int(time.time())
        random_suffix = hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:6]
        return f"bot_{user_id}_{timestamp}_{random_suffix}"

    @staticmethod
    def get_unique_folder(user_id: int, name: str) -> str:
        base = "".join(c for c in name if c.isalnum() or c in ('-', '_')).strip()
        if not base:
            base = "bot"
        user_bots_dir = UserSandbox.get_user_bots_dir(user_id)
        folder = base
        counter = 1
        while (user_bots_dir / folder).exists():
            folder = f"{base}_{counter}"
            counter += 1
        return folder

    @staticmethod
    def extract_and_setup_bot(user_id: int, zip_path: Path, bot_name: str, 
                               existing_folder: Optional[str] = None) -> Tuple[Optional[str], Optional[str], str]:
        user_bots_dir = UserSandbox.get_user_bots_dir(user_id)

        if existing_folder:
            target_dir = user_bots_dir / existing_folder
            backup_temp = UserSandbox.get_user_dir(user_id) / "backups" / f"temp_backup_{int(time.time())}"
            if target_dir.exists():
                shutil.copytree(target_dir, backup_temp, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                shutil.rmtree(target_dir)
        else:
            folder_name = UserBotManager.get_unique_folder(user_id, bot_name)
            target_dir = user_bots_dir / folder_name

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                file_list = zf.namelist()
                dangerous_files = ['.exe', '.dll', '.so', '.dylib', '.bin']
                for fname in file_list:
                    if any(fname.lower().endswith(ext) for ext in dangerous_files):
                        return None, None, "❌ الملف يحتوي على ملفات تنفيذية غير مسموح بها"
                zf.extractall(target_dir)

            main_file = None
            for root, dirs, files in os.walk(target_dir):
                for f in files:
                    if f.endswith('.py') and f in ('main.py', 'app.py', 'bot.py', 'run.py', 'start.py'):
                        main_file = os.path.relpath(os.path.join(root, f), target_dir)
                        break
                if main_file:
                    break

            if not main_file:
                subdirs = [d for d in target_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
                for subdir in subdirs:
                    for f in subdir.iterdir():
                        if f.is_file() and f.suffix == '.py' and f.name in ('main.py', 'app.py', 'bot.py', 'run.py', 'start.py'):
                            for item in subdir.iterdir():
                                shutil.move(str(item), str(target_dir))
                            shutil.rmtree(subdir)
                            main_file = f.name
                            break
                    if main_file:
                        break

            if not main_file:
                py_files = list(target_dir.rglob('*.py'))
                if py_files:
                    main_file = py_files[0].relative_to(target_dir).as_posix()

            if not main_file:
                if existing_folder and 'backup_temp' in locals() and backup_temp.exists():
                    shutil.rmtree(target_dir)
                    shutil.move(str(backup_temp), str(target_dir))
                else:
                    shutil.rmtree(target_dir)
                return None, None, "❌ لم يتم العثور على ملف Python رئيسي"

            folder_name = target_dir.name
            log_activity(f"تم إعداد البوت '{bot_name}' للمستخدم {user_id}")
            return folder_name, main_file, "✅ تم إعداد البوت بنجاح"

        except Exception as e:
            if existing_folder and 'backup_temp' in locals() and backup_temp.exists():
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.move(str(backup_temp), str(target_dir))
            elif target_dir.exists():
                shutil.rmtree(target_dir)
            log_activity(f"خطأ في إعداد البوت للمستخدم {user_id}: {e}")
            return None, None, f"❌ خطأ: {str(e)}"

    @staticmethod
    def is_bot_running(bot_id: str) -> bool:
        if bot_id not in UserBotManager.running_bots:
            return False
        process = UserBotManager.running_bots[bot_id]
        return process.poll() is None

    @staticmethod
    def _read_output_async(bot_id: str, process: subprocess.Popen, console: UserBotConsole, log_file: Path, stop_event: threading.Event):

        try:
            with open(log_file, 'a', encoding='utf-8') as log:
                while not stop_event.is_set() and process.poll() is None:
                    try:
                        import select
                        if hasattr(process.stdout, 'fileno'):
                            ready, _, _ = select.select([process.stdout], [], [], 0.5)
                            if ready:
                                line = process.stdout.readline()
                                if line:
                                    decoded_line = line.decode('utf-8', errors='ignore').rstrip()
                                    if decoded_line:
                                        console.add_line(decoded_line)
                                        log.write(f"[{datetime.now().strftime('%H:%M:%S')}] {decoded_line}\n")
                                        log.flush()
                                else:
                                    time.sleep(0.1)
                        else:
                            line = process.stdout.readline()
                            if line:
                                decoded_line = line.decode('utf-8', errors='ignore').rstrip()
                                if decoded_line:
                                    console.add_line(decoded_line)
                                    log.write(f"[{datetime.now().strftime('%H:%M:%S')}] {decoded_line}\n")
                                    log.flush()
                            time.sleep(0.1)
                    except:
                        time.sleep(0.1)
        except Exception as e:
            log_activity(f"خطأ في قراءة إخراج البوت {bot_id}: {e}", "ERROR")

    @staticmethod
    def run_bot(user_id: int, bot_id: str,folder: str, main_file: str):

    user_dir = UserSandbox.get_user_dir(user_id)
    log_file = UserSandbox.get_user_logs_dir(user_id) / f"{bot_id}.log"
    bot_folder = UserSandbox.get_user_bots_dir(user_id) / folder
    main_file_path = bot_folder / main_file

    resources = UserResourcesManager.get_user_resources(user_id)
    console = UserBotManager.get_bot_console(bot_id)
    console.clear()

    env = os.environ.copy()

    site_packages_paths = []
    for path in sys.path:
        if 'site-packages' in path and os.path.exists(path):
            site_packages_paths.append(path)
    if site_packages_paths:
        env['PYTHONPATH'] = os.pathsep.join(site_packages_paths) + os.pathsep + env.get('PYTHONPATH', '')
        console.add_line(f"📦 تم إضافة site-packages إلى PYTHONPATH: {len(site_packages_paths)} مسار")

    env['PYTHONPATH'] = str(user_dir) + os.pathsep + env.get('PYTHONPATH', '')
    env['FPI_USER_ID'] = str(user_id)
    env['FPI_BOT_ID'] = bot_id
    env['HOME'] = str(user_dir)
    env['TMPDIR'] = str(user_dir / 'tmp')

    stop_event = None
    process = None

    with open(log_file, 'a', encoding='utf-8') as log:
        log.write(f"\n{'=' * 60}\n[{datetime.now()}] بدء تشغيل البوت {bot_id}\n")
        log.write(f"المستخدم: {user_id}\n")
        log.write(f"المجلد: {bot_folder}\n")
        log.write(f"الموارد: {resources.to_dict()}\n")
        log.write(f"{'=' * 60}\n")

        console.add_line(f"🚀 بدء تشغيل البوت {bot_id}")

        try:
            console.add_line("📦 جاري التحقق من المكتبات المطلوبة...")
            log.write(f"[{datetime.now()}] جاري التحقق من المكتبات...\n")

            auto_install_success, auto_install_msg = AutoInstaller.setup_bot_environment(bot_folder, console)
            log.write(f"[{datetime.now()}] نتيجة تجهيز البيئة: {auto_install_msg}\n")

            if not auto_install_success:
                console.add_line(f"⚠️ تحذير: {auto_install_msg}")
                console.add_line("🔄 سيتم محاولة التشغيل على أي حال...")
            else:
                console.add_line(f"✅ {auto_install_msg}")

            preexec_fn = None
            if platform.system() == 'Linux':
                def limit_resources():
                    try:
                        if resources.max_memory_mb > 0:
                            resource.setrlimit(
                                resource.RLIMIT_AS,
                                (resources.max_memory_mb * 1024 * 1024, resources.max_memory_mb * 1024 * 1024)
                            )

                        if resources.max_processes > 0:
                            resource.setrlimit(resource.RLIMIT_NPROC, (resources.max_processes, resources.max_processes))

                        max_file_size = min(
                            100 * 1024 * 1024,
                            resources.max_disk_mb * 1024 * 1024 if resources.max_disk_mb > 0 else 100 * 1024 * 1024
                        )
                        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_size, max_file_size))
                        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    except Exception as limit_error:
                        print(f"Warning: Could not set resource limits: {limit_error}")

                preexec_fn = limit_resources

            process = subprocess.Popen(
                [sys.executable, '-u', str(main_file_path)],
                cwd=str(bot_folder),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                env=env,
                preexec_fn=preexec_fn,
                bufsize=0,
                universal_newlines=False
            )

            UserBotManager.running_bots[bot_id] = process
            UserBotManager.bot_stdin_pipes[bot_id] = process.stdin
            UserBotManager.bot_start_times[bot_id] = datetime.now()

            stop_event = threading.Event()
            UserBotManager._stop_events[bot_id] = stop_event

            if resources.escape_monitor:
                EscapeMonitor.start_monitoring(bot_id, process, user_id, bot_folder, resources)

            output_thread = threading.Thread(
                target=UserBotManager._read_output_async,
                args=(bot_id, process, console, log_file, stop_event),
                daemon=True
            )
            output_thread.start()
            UserBotManager._output_threads[bot_id] = output_thread

            process.wait()
            returncode = process.returncode
            log.write(f"[{datetime.now()}] توقف البوت {bot_id} (returncode: {returncode})\n")
            console.add_line(f"⛔ توقف البوت (returncode: {returncode})")

            if returncode != 0:
                recent_output = "\n".join(console.get_output(60).splitlines()[-40:])
                error_trace = recent_output or f"No console output captured. Return code: {returncode}"
                send_error_report_sync(
                    f"تعطّل البوت {bot_id} برمز خروج {returncode}",
                    error_trace,
                    extra_targets=[user_id],
                    title="تعطل بوت مرفوع",
                    extra_info={
                        "bot_id": bot_id,
                        "user_id": user_id,
                        "main_file": main_file,
                        "returncode": returncode
                    }
                )

        except Exception as e:
            error_trace = traceback.format_exc()
            log.write(f"[{datetime.now()}] خطأ: {e}\n{error_trace}\n")
            console.add_line(f"❌ خطأ: {e}")
            send_error_report_sync(
                str(e),
                error_trace,
                extra_targets=[user_id],
                title="فشل تشغيل بوت مرفوع",
                extra_info={
                    "bot_id": bot_id,
                    "user_id": user_id,
                    "main_file": main_file
                }
            )
        finally:
            if stop_event is not None:
                stop_event.set()
            if bot_id in UserBotManager._output_threads:
                del UserBotManager._output_threads[bot_id]
            if bot_id in UserBotManager._stop_events:
                del UserBotManager._stop_events[bot_id]
            if bot_id in UserBotManager.running_bots:
                del UserBotManager.running_bots[bot_id]
            if bot_id in UserBotManager.bot_stdin_pipes:
                del UserBotManager.bot_stdin_pipes[bot_id]
            if process and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass

    @staticmethod
    async def notify_admin_bot_started(user_id: int, bot_id: str, bot_name: str, context: ContextTypes.DEFAULT_TYPE):

        try:
            resources = UserResourcesManager.get_user_resources(user_id)
            disk_usage = UserSandbox.get_disk_usage(user_id)

            mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
            cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
            proc = "∞" if resources.max_processes == 0 else str(resources.max_processes)
            disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

            for admin_id in ADMIN_IDS:
                try:
                    keyboard = [
                        [InlineKeyboardButton("📊 تغيير موارده", callback_data=f"admin_edit_resources_{user_id}")],
                        [InlineKeyboardButton("👤 معلوماته", callback_data=f"admin_user_info_{user_id}")]
                    ]
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"🚀 *بوت جديد يعمل!*\n\n"
                             f"👤 المستخدم: `{user_id}`\n"
                             f"🤖 البوت: `{bot_name}`\n"
                             f"🆔 المعرف: `{bot_id}`\n"
                             f"⏰ الوقت: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
                             f"📊 *موارده:*\n"
                             f"💾 الذاكرة: `{mem}`\n"
                             f"💻 CPU: `{cpu}`\n"
                             f"🔢 العمليات: `{proc}`\n"
                             f"💿 المساحة: `{disk_usage}/{disk}` MB\n"
                             f"🌐 الشبكة: `{'✅' if resources.network_allowed else '❌'}`\n"
                             f"👁️ مراقبة الهروب: `{'✅' if resources.escape_monitor else '❌'}`",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    log_activity(f"فشل إرسال إشعار للمالك: {e}", "ERROR")
        except Exception as e:
            log_activity(f"خطأ في إشعار المالك: {e}", "ERROR")

    @staticmethod
    def start_bot(user_id: int, bot_id: str, context: ContextTypes.DEFAULT_TYPE = None) -> Tuple[bool, str]:
        bots = UserBotManager.load_user_bots(user_id)
        bot = next((b for b in bots if b.id == bot_id), None)

        if not bot:
            return False, "❌ البوت غير موجود"

        if UserBotManager.is_bot_running(bot_id):
            return False, "⚠️ البوت يعمل بالفعل"

        bot_folder = UserSandbox.get_user_bots_dir(user_id) / bot.folder
        main_file_path = bot_folder / bot.main_file

        if not main_file_path.exists():
            return False, f"❌ ملف البوت غير موجود: {bot.main_file}"

        resources = UserResourcesManager.get_user_resources(user_id)
        if resources.max_disk_mb > 0:
            disk_usage = UserSandbox.get_disk_usage(user_id)
            if disk_usage >= resources.max_disk_mb:
                return False, f"❌ تجاوزت حد المساحة ({disk_usage}/{resources.max_disk_mb} MB)"

        thread = threading.Thread(
            target=UserBotManager.run_bot,
            args=(user_id, bot_id, bot.folder, bot.main_file),
            daemon=True
        )
        thread.start()

        bot.restart_count += 1
        bot.last_restart = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        UserBotManager.save_user_bots(user_id, bots)

        log_activity(f"المستخدم {user_id} شغل البوت '{bot.name}' ({bot_id})")

        if context:
            asyncio.create_task(UserBotManager.notify_admin_bot_started(user_id, bot_id, bot.name, context))

        return True, "✅ تم تشغيل البوت"

    @staticmethod
    def stop_bot(bot_id: str) -> Tuple[bool, str]:
        if bot_id not in UserBotManager.running_bots:
            return False, "⚠️ البوت ليس قيد التشغيل"

        process = UserBotManager.running_bots[bot_id]

        if bot_id in UserBotManager._stop_events:
            UserBotManager._stop_events[bot_id].set()

        try:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(children, timeout=3)
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.terminate()
            parent.wait(3)
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            log_activity(f"خطأ في إيقاف البوت {bot_id}: {e}")
            return False, f"❌ خطأ: {e}"

        if bot_id in UserBotManager.running_bots:
            del UserBotManager.running_bots[bot_id]
        if bot_id in UserBotManager.bot_stdin_pipes:
            del UserBotManager.bot_stdin_pipes[bot_id]
        if bot_id in UserBotManager._output_threads:
            del UserBotManager._output_threads[bot_id]
        if bot_id in UserBotManager._stop_events:
            del UserBotManager._stop_events[bot_id]

        log_activity(f"تم إيقاف البوت {bot_id}")
        return True, "✅ تم إيقاف البوت"

    @staticmethod
    def restart_bot(user_id: int, bot_id: str, context: ContextTypes.DEFAULT_TYPE = None) -> Tuple[bool, str]:
        UserBotManager.stop_bot(bot_id)
        time.sleep(1)
        return UserBotManager.start_bot(user_id, bot_id, context)

    @staticmethod
    def delete_bot(user_id: int, bot_id: str) -> Tuple[bool, str]:
        bots = UserBotManager.load_user_bots(user_id)
        bot = next((b for b in bots if b.id == bot_id), None)

        if not bot:
            return False, "❌ البوت غير موجود"

        if UserBotManager.is_bot_running(bot_id):
            UserBotManager.stop_bot(bot_id)

        folder_path = UserSandbox.get_user_bots_dir(user_id) / bot.folder

        if folder_path.exists():
            try:
                backup_name = f"deleted_{bot.folder}_{int(time.time())}"
                backup_path = UserSandbox.get_user_dir(user_id) / "backups" / backup_name
                shutil.copytree(folder_path, backup_path)
                shutil.rmtree(folder_path)
            except Exception as e:
                log_activity(f"خطأ في حذف مجلد البوت {bot_id}: {e}")
                return False, f"❌ فشل حذف المجلد: {e}"

        bots = [b for b in bots if b.id != bot_id]
        UserBotManager.save_user_bots(user_id, bots)

        log_file = UserSandbox.get_user_logs_dir(user_id) / f"{bot_id}.log"
        if log_file.exists():
            log_file.unlink()

        if bot_id in UserBotManager.bot_consoles:
            del UserBotManager.bot_consoles[bot_id]

        log_activity(f"المستخدم {user_id} حذف البوت '{bot.name}' ({bot_id})")
        return True, "✅ تم حذف البوت"

    @staticmethod
    def get_bot_console(bot_id: str) -> UserBotConsole:
        if bot_id not in UserBotManager.bot_consoles:
            UserBotManager.bot_consoles[bot_id] = UserBotConsole(bot_id)
        return UserBotManager.bot_consoles[bot_id]

    @staticmethod
    def send_command_to_bot(bot_id: str, command: str) -> bool:
        try:
            if bot_id in UserBotManager.running_bots and bot_id in UserBotManager.bot_stdin_pipes:
                process = UserBotManager.running_bots[bot_id]
                if process.poll() is None:
                    stdin = UserBotManager.bot_stdin_pipes[bot_id]
                    if stdin and not stdin.closed:
                        stdin.write(f"{command}\n".encode('utf-8'))
                        stdin.flush()
                        console = UserBotManager.get_bot_console(bot_id)
                        console.add_line(f">>> {command}")
                        return True
            return False
        except Exception as e:
            console = UserBotManager.get_bot_console(bot_id)
            console.add_line(f"[ERROR] فشل إرسال الأمر: {e}")
            return False

def create_backup(user_id: Optional[int] = None, bot_id: Optional[str] = None) -> Tuple[bool, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if user_id and bot_id:
        bots = UserBotManager.load_user_bots(user_id)
        bot = next((b for b in bots if b.id == bot_id), None)
        if not bot:
            return False, "❌ البوت غير موجود"
        source = UserSandbox.get_user_bots_dir(user_id) / bot.folder
        backup_name = f"backup_{user_id}_{bot.folder}_{timestamp}.zip"
        backup_path = BACKUP_DIR / backup_name
    elif user_id:
        source = UserSandbox.get_user_dir(user_id)
        backup_name = f"backup_user_{user_id}_{timestamp}.zip"
        backup_path = BACKUP_DIR / backup_name
    else:
        source = USERS_DIR
        backup_name = f"backup_all_{timestamp}.zip"
        backup_path = BACKUP_DIR / backup_name

    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(source)
                    zf.write(file_path, arcname)

        size = backup_path.stat().st_size
        log_activity(f"تم إنشاء نسخة احتياطية: {backup_name} ({size/1024/1024:.2f} MB)")
        return True, f"✅ تم إنشاء النسخة: {backup_name}"
    except Exception as e:
        log_activity(f"خطأ في إنشاء نسخة احتياطية: {e}")
        return False, f"❌ خطأ: {e}"

def list_backups() -> List[Tuple[str, str, int]]:
    backups = []
    for backup in sorted(BACKUP_DIR.glob('*.zip'), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = backup.stat()
        size_mb = stat.st_size / 1024 / 1024
        date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        backups.append((backup.name, date, size_mb))
    return backups

def restore_backup(backup_name: str, user_id: Optional[int] = None) -> Tuple[bool, str]:
    backup_path = BACKUP_DIR / backup_name
    if not backup_path.exists():
        return False, "❌ ملف النسخة غير موجود"

    try:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            if user_id:
                target_dir = UserSandbox.get_user_dir(user_id)
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True)
                zf.extractall(target_dir)
            else:
                if USERS_DIR.exists():
                    shutil.rmtree(USERS_DIR)
                USERS_DIR.mkdir()
                zf.extractall(USERS_DIR)

        log_activity(f"تم استعادة النسخة: {backup_name}")
        return True, "✅ تم استعادة النسخة بنجاح"
    except Exception as e:
        log_activity(f"خطأ في استعادة النسخة: {e}")
        return False, f"❌ خطأ: {e}"

def load_schedules() -> List[Dict]:
    if SCHEDULE_FILE.exists():
        try:
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_schedules(schedules: List[Dict]):
    with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4, ensure_ascii=False)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

def scheduled_health_check():
    log_activity("فحص صحة دوري")

def scheduled_backup():
    if system_settings.backup_auto:
        success, msg = create_backup()
        log_activity(f"نسخ احتياطي تلقائي: {msg}")

def cleanup_old_logs():
    retention = timedelta(days=system_settings.log_retention_days)
    now = datetime.now()
    for log_file in LOG_DIR.glob('*.log'):
        file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
        if now - file_time > retention:
            log_file.unlink()
            log_activity(f"تم حذف السجل القديم: {log_file.name}")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    is_banned, reason = BanSystem.is_banned(user_id)
    if is_banned:
        await update.message.reply_text(f"🚫 تم حظرك: {reason}")
        return

    if REQUIRED_CHANNEL and REQUIRED_CHANNEL != "@fpi_sx_channel":
        is_subscribed = await SubscriptionSystem.check_subscription(user_id, context.bot)
        if not is_subscribed:
            keyboard = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")]]
            await update.message.reply_text(
                f"⚠️ *الاشتراك إجباري*\n\nيجب الاشتراك في القناة لاستخدام البوت:\n{REQUIRED_CHANNEL}\n\nبعد الاشتراك أرسل /start مرة أخرى.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return

    allowed, message = check_bot_modes(user_id)
    if not allowed:
        await update.message.reply_text(message)
        return

    broadcast_settings.add_subscriber(user_id)
    UserSandbox.get_user_dir(user_id)

    user_points = PointsSystem.get_user_points(user_id)
    if user_points == 0:
        PointsSystem.add_points(user_id, 5, "رصيد ترحيبي")
        await update.message.reply_text("🎉 تم إضافة 5 نقاط ترحيبية! يمكنك رفع بوت واحد مجاناً.")

    if is_admin(user_id):
        await show_admin_main_menu(update.message)
        return

    await show_user_main_menu_message(update.message, user_id, context)

async def show_user_main_menu_message(message, user_id: int, context: ContextTypes.DEFAULT_TYPE):

    user_points = PointsSystem.get_user_points(user_id)
    bots = UserBotManager.load_user_bots(user_id)
    running = sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
    invite_stats = InviteSystem.get_invite_stats(user_id)
    resources = UserResourcesManager.get_user_resources(user_id)
    disk_usage = UserSandbox.get_disk_usage(user_id)

    keyboard = [
        [InlineKeyboardButton("📊 لوحة التحكم", callback_data="user_dashboard")],
        [InlineKeyboardButton("🤖 إدارة بوتاتي", callback_data="user_manage_bots")],
        [InlineKeyboardButton("📈 إحصائياتي", callback_data="user_stats")],
        [InlineKeyboardButton("💰 نقاطي", callback_data="user_points")],
        [InlineKeyboardButton("🔗 رابط الدعوة", callback_data="user_invite_link")],
        [InlineKeyboardButton("🎁 استخدام كود", callback_data="user_use_code")],
        [InlineKeyboardButton("📜 سجلاتي", callback_data="user_logs_menu")],
        [InlineKeyboardButton("📊 مواردي", callback_data="user_resources")],
    ]

    mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
    cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
    disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

    await message.reply_text(
        f"👋 *مرحباً بك في FPI SX MANAGER!*\n\n"
        f"🤖 *بوتاتك:* `{len(bots)}` (يعمل: `{running}`)\n"
        f"💰 *نقاطك:* `{user_points}`\n"
        f"👥 *دعواتك:* `{invite_stats['total_invites']}`\n\n"
        f"📤 *رفع ملف* يستهلك `{points_config.points_per_upload}` نقطة\n"
        f"🔄 *تحديث ملف* مجاني\n"
        f"👥 *دعوة صديق* = `{points_config.points_per_invite}` نقاط\n\n"
        f"📊 *مواردك:*\n"
        f"💾 الذاكرة: `{mem}`\n"
        f"💻 CPU: `{cpu}`\n"
        f"💿 المساحة: `{disk_usage}/{disk}` MB",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def show_admin_main_menu(message_or_query):
    keyboard = [
        [InlineKeyboardButton("📊 لوحة التحكم", callback_data="admin_dashboard")],
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_manage_users")],
        [InlineKeyboardButton("🤖 جميع البوتات", callback_data="admin_all_bots")],
        [InlineKeyboardButton("🚫 المحظورون", callback_data="admin_banned_users")],
        [InlineKeyboardButton("📢 الإذاعة", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("🎁 أكواد النقاط", callback_data="admin_codes_menu")],
        [InlineKeyboardButton("⚙️ أوضاع البوت", callback_data="admin_modes_menu")],
        [InlineKeyboardButton("📊 موارد المستخدمين", callback_data="admin_resources_menu")],
        [InlineKeyboardButton("💾 النسخ الاحتياطية", callback_data="admin_backups")],
        [InlineKeyboardButton("📈 إحصائيات النظام", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ إعدادات النقاط", callback_data="admin_points_settings")],
    ]

    text = "🌟 *لوحة تحكم المالك*\n\nاختر الإجراء:"

    if hasattr(message_or_query, 'edit_message_text'):
        await safe_edit_message(message_or_query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await message_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    is_banned, reason = BanSystem.is_banned(user_id)
    if is_banned:
        await query.edit_message_text(f"🚫 تم حظرك: {reason}")
        return

    try:

        if data == "user_dashboard":
            await handle_user_dashboard(query, user_id, context)
        elif data == "user_manage_bots":
            await show_user_bots_list(query, user_id)
        elif data == "user_add_bot":
            context.user_data['waiting_for_bot_name'] = True
            await query.edit_message_text("✏️ *إضافة بوت جديد*\n\nأدخل اسم البوت:", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("user_bot_info_"):
            await show_user_bot_info(query, user_id, data[14:])
        elif data.startswith("user_bot_start_"):
            await handle_bot_start(query, user_id, data[15:], context)
        elif data.startswith("user_bot_stop_"):
            await handle_bot_stop(query, user_id, data[14:])
        elif data.startswith("user_bot_restart_"):
            await handle_bot_restart(query, user_id, data[17:], context)
        elif data.startswith("user_bot_console_"):
            await show_user_bot_console(query, user_id, data[17:])
        elif data.startswith("user_bot_sendcmd_"):
            bot_id = data[17:]
            context.user_data['waiting_for_command'] = bot_id
            bots = UserBotManager.load_user_bots(user_id)
            bot = next((b for b in bots if b.id == bot_id), None)
            await query.edit_message_text(f"⌨️ *إرسال أمر للبوت: {bot.name}*\n\nأرسل الأمر:", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("user_bot_log_"):
            await handle_bot_log(query, user_id, data[13:])
        elif data.startswith("user_bot_update_"):
            context.user_data['waiting_for_update_zip'] = data[16:]
            await query.edit_message_text("📦 أرسل ملف ZIP الجديد:")
        elif data.startswith("user_bot_delete_"):
            await handle_bot_delete_confirm(query, user_id, data[16:])
        elif data.startswith("user_confirm_delete_"):
            await handle_bot_delete(query, user_id, data[20:])
        elif data == "user_start_all":
            await handle_start_all(query, user_id, context)
        elif data == "user_stop_all":
            await handle_stop_all(query, user_id)
        elif data == "user_restart_all":
            await handle_restart_all(query, user_id, context)
        elif data == "user_resources":
            await handle_user_resources(query, user_id)
        elif data == "back_to_user_main":
            await show_user_main_menu(query, user_id, context)

        elif data == "admin_dashboard":
            await handle_admin_dashboard(query)
        elif data == "admin_manage_users":
            await handle_admin_manage_users(query)
        elif data.startswith("admin_user_info_"):
            await handle_admin_user_info(query, int(data[16:]))
        elif data.startswith("admin_view_user_bots_"):
            await show_user_bots_list(query, int(data[21:]), is_admin_view=True)
        elif data.startswith("admin_edit_resources_"):
            await handle_admin_edit_resources(query, int(data[21:]))
        elif data.startswith("res_set_mem_"):
            target_user_id = int(data[12:])
            context.user_data['waiting_for_res_memory'] = target_user_id
            resources = UserResourcesManager.get_user_resources(target_user_id)
            mem = "∞" if resources.max_memory_mb == 0 else str(resources.max_memory_mb)
            await query.edit_message_text(f"✏️ *تغيير حد الذاكرة للمستخدم {target_user_id}*\n\nالحالي: `{mem}` MB\n\nأرسل القيمة الجديدة (0 = غير محدود):", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("res_set_cpu_"):
            target_user_id = int(data[12:])
            context.user_data['waiting_for_res_cpu'] = target_user_id
            resources = UserResourcesManager.get_user_resources(target_user_id)
            cpu = "∞" if resources.max_cpu_percent == 0 else str(resources.max_cpu_percent)
            await query.edit_message_text(f"✏️ *تغيير حد CPU للمستخدم {target_user_id}*\n\nالحالي: `{cpu}`%\n\nأرسل القيمة الجديدة (0 = غير محدود):", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("res_set_proc_"):
            target_user_id = int(data[13:])
            context.user_data['waiting_for_res_proc'] = target_user_id
            resources = UserResourcesManager.get_user_resources(target_user_id)
            proc = "∞" if resources.max_processes == 0 else str(resources.max_processes)
            await query.edit_message_text(f"✏️ *تغيير حد العمليات للمستخدم {target_user_id}*\n\nالحالي: `{proc}`\n\nأرسل القيمة الجديدة (0 = غير محدود):", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("res_set_disk_"):
            target_user_id = int(data[13:])
            context.user_data['waiting_for_res_disk'] = target_user_id
            resources = UserResourcesManager.get_user_resources(target_user_id)
            disk = "∞" if resources.max_disk_mb == 0 else str(resources.max_disk_mb)
            await query.edit_message_text(f"✏️ *تغيير حد المساحة للمستخدم {target_user_id}*\n\nالحالي: `{disk}` MB\n\nأرسل القيمة الجديدة (0 = غير محدود):", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("res_toggle_net_"):
            await handle_toggle_net(query, int(data[15:]))
        elif data.startswith("res_toggle_esc_"):
            await handle_toggle_esc(query, int(data[15:]))
        elif data.startswith("res_toggle_kill_"):
            await handle_toggle_kill(query, int(data[16:]))
        elif data.startswith("res_unlimited_"):
            await handle_unlimited_resources(query, int(data[14:]))
        elif data.startswith("res_reset_"):
            await handle_reset_resources(query, int(data[10:]))
        elif data.startswith("admin_ban_"):
            context.user_data['banning_user'] = int(data[10:])
            await query.edit_message_text("🚫 *حظر المستخدم*\n\nأرسل سبب الحظر:", parse_mode=ParseMode.MARKDOWN)
        elif data.startswith("admin_unban_"):
            await handle_unban_user(query, int(data[12:]))
        elif data == "admin_banned_users":
            await handle_banned_users(query)
        elif data == "admin_all_bots":
            await handle_all_bots(query)

        elif data.startswith("admin_add_points_"):
            target_user_id = int(data[17:])
            context.user_data['waiting_for_add_points'] = target_user_id
            await query.edit_message_text("💰 *إضافة نقاط يدوياً*\n\nأرسل عدد النقاط التي تريد إضافتها (يمكن أن تكون سالبة للخصم):", parse_mode=ParseMode.MARKDOWN)

        elif data == "admin_modes_menu":
            await handle_modes_menu(query)
        elif data == "toggle_maintenance":
            await handle_toggle_maintenance(query)
        elif data == "toggle_privacy":
            await handle_toggle_privacy(query)
        elif data == "edit_maintenance_msg":
            context.user_data['waiting_for_maintenance_msg'] = True
            await query.edit_message_text(f"✏️ أرسل الرسالة الجديدة:\n\nالحالية: `{system_settings.bot_modes.maintenance_message}`", parse_mode=ParseMode.MARKDOWN)
        elif data == "edit_privacy_msg":
            context.user_data['waiting_for_privacy_msg'] = True
            await query.edit_message_text(f"✏️ أرسل الرسالة الجديدة:\n\nالحالية: `{system_settings.bot_modes.privacy_message}`", parse_mode=ParseMode.MARKDOWN)

        elif data == "admin_codes_menu":
            await handle_codes_menu(query)
        elif data == "admin_create_code":
            context.user_data['waiting_for_code_details'] = True
            await query.edit_message_text("🎁 *إنشاء كود*\n\nأرسل: `نقاط:استخدامات:أيام_الصلاحية`\nمثال: `100:10:30`", parse_mode=ParseMode.MARKDOWN)
        elif data == "admin_list_codes":
            await show_codes_list(query, 0)
        elif data.startswith("codes_page_"):
            await show_codes_list(query, int(data[11:]))
        elif data.startswith("code_info_"):
            await handle_code_info(query, data[10:])
        elif data.startswith("toggle_code_"):
            await handle_toggle_code(query, data[12:])

        elif data == "admin_broadcast_menu":
            await handle_broadcast_menu(query)
        elif data == "broadcast_any":
            context.user_data['waiting_for_broadcast_any'] = True
            await query.edit_message_text("📢 *إذاعة شاملة*\n\nأرسل أي شيء (نص، صورة، فيديو، صوت، ملف، ملصق، استيكر...)\nسيتم إعادة إرساله كما هو لكل المشتركين.\n\nللإلغاء أرسل /cancel", parse_mode=ParseMode.MARKDOWN)
        elif data == "broadcast_stats":
            await handle_broadcast_stats(query)

        elif data == "admin_backups":
            await handle_backups(query)
        elif data == "admin_create_backup":
            await handle_create_backup(query)
        elif data.startswith("admin_restore_backup_"):
            await handle_restore_backup(query, data[21:])

        elif data == "admin_points_settings":
            await handle_points_settings(query)
        elif data == "admin_set_points_upload":
            context.user_data['waiting_for_points_upload'] = True
            await query.edit_message_text(f"✏️ *تغيير تكلفة الرفع (نقاط تستهلك)*\n\nالحالية: `{points_config.points_per_upload}`", parse_mode=ParseMode.MARKDOWN)
        elif data == "admin_set_points_update":
            context.user_data['waiting_for_points_update'] = True
            await query.edit_message_text(f"✏️ *تغيير نقاط التحديث*\n\nالحالية: `{points_config.points_per_update}` (مجاني حالياً)", parse_mode=ParseMode.MARKDOWN)
        elif data == "admin_set_points_invite":
            context.user_data['waiting_for_points_invite'] = True
            await query.edit_message_text(f"✏️ *تغيير نقاط الدعوة*\n\nالحالية: `{points_config.points_per_invite}`", parse_mode=ParseMode.MARKDOWN)
        elif data == "admin_stats":
            await handle_admin_stats(query)
        elif data == "back_to_admin_main":
            await show_admin_main_menu(query)

        elif data == "user_points":
            await handle_user_points(query, user_id)
        elif data == "user_use_code":
            context.user_data['waiting_for_code_input'] = True
            await query.edit_message_text("🎁 *استخدام كود نقاط*\n\nأرسل الكود:", parse_mode=ParseMode.MARKDOWN)

        elif data == "user_invite_link":
            await handle_invite_link(query, user_id, context)

        elif data == "user_stats":
            await handle_user_stats(query, user_id)

        elif data == "user_logs_menu":
            await handle_logs_menu(query)
        elif data == "user_activity_log":
            await handle_activity_log(query)
        elif data == "user_bots_logs":
            await handle_bots_logs(query, user_id)
        else:
            await query.answer("❓ زر غير معروف")

    except Exception as e:
        log_activity(f"خطأ في معالجة الزر {data}: {e}", "ERROR")
        traceback.print_exc()
        try:
            await query.edit_message_text(f"⚠️ حدث خطأ: {str(e)}")
        except:
            pass

async def handle_user_dashboard(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    bots = UserBotManager.load_user_bots(user_id)
    running = sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
    keyboard = [
        [InlineKeyboardButton("▶️ تشغيل الكل", callback_data="user_start_all"),
         InlineKeyboardButton("⏹️ إيقاف الكل", callback_data="user_stop_all")],
        [InlineKeyboardButton("🔄 إعادة تشغيل الكل", callback_data="user_restart_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main")]
    ]
    await safe_edit_message(query, f"📊 *لوحة التحكم*\n\n📦 إجمالي البوتات: `{len(bots)}`\n🟢 يعمل: `{running}`\n🔴 متوقف: `{len(bots)-running}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_bot_start(query, user_id: int, bot_id: str, context: ContextTypes.DEFAULT_TYPE):
    success, msg = UserBotManager.start_bot(user_id, bot_id, context)
    await query.answer(msg, show_alert=True)
    await show_user_bot_info(query, user_id, bot_id)

async def handle_bot_stop(query, user_id: int, bot_id: str):
    success, msg = UserBotManager.stop_bot(bot_id)
    await query.answer(msg, show_alert=True)
    await show_user_bot_info(query, user_id, bot_id)

async def handle_bot_restart(query, user_id: int, bot_id: str, context: ContextTypes.DEFAULT_TYPE):
    success, msg = UserBotManager.restart_bot(user_id, bot_id, context)
    await query.answer(msg, show_alert=True)
    await show_user_bot_info(query, user_id, bot_id)

async def handle_bot_log(query, user_id: int, bot_id: str):
    log_file = UserSandbox.get_user_logs_dir(user_id) / f"{bot_id}.log"
    if log_file.exists():
        try:
            log_content = log_file.read_text(encoding='utf-8', errors='ignore')
            if len(log_content) > 4000:
                log_content = log_content[-4000:]
            await query.edit_message_text(f"📜 *سجل البوت:*\n```\n{log_content}\n```", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ في قراءة السجل: {e}")
    else:
        await query.edit_message_text("📭 لا يوجد سجل لهذا البوت.")

async def handle_bot_delete_confirm(query, user_id: int, bot_id: str):
    keyboard = [[InlineKeyboardButton("⚠️ نعم، احذف", callback_data=f"user_confirm_delete_{bot_id}")], [InlineKeyboardButton("❌ لا، إلغاء", callback_data=f"user_bot_info_{bot_id}")]]
    await safe_edit_message(query, "🚨 *تحذير!*\n\nهل أنت متأكد من حذف هذا البوت؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_bot_delete(query, user_id: int, bot_id: str):
    success, msg = UserBotManager.delete_bot(user_id, bot_id)
    await query.answer(msg, show_alert=True)
    await show_user_bots_list(query, user_id)

async def handle_start_all(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    bots = UserBotManager.load_user_bots(user_id)
    started = 0
    for bot in bots:
        if not UserBotManager.is_bot_running(bot.id):
            UserBotManager.start_bot(user_id, bot.id, context)
            started += 1
    await query.answer(f"✅ تم تشغيل {started} بوت", show_alert=True)
    await show_user_bots_list(query, user_id)

async def handle_stop_all(query, user_id: int):
    bots = UserBotManager.load_user_bots(user_id)
    stopped = 0
    for bot in bots:
        if UserBotManager.is_bot_running(bot.id):
            UserBotManager.stop_bot(bot.id)
            stopped += 1
    await query.answer(f"⏹️ تم إيقاف {stopped} بوت", show_alert=True)
    await show_user_bots_list(query, user_id)

async def handle_restart_all(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    bots = UserBotManager.load_user_bots(user_id)
    restarted = 0
    for bot in bots:
        UserBotManager.restart_bot(user_id, bot.id, context)
        restarted += 1
    await query.answer(f"🔄 تم إعادة تشغيل {restarted} بوت", show_alert=True)
    await show_user_bots_list(query, user_id)

async def handle_user_resources(query, user_id: int):
    resources = UserResourcesManager.get_user_resources(user_id)
    disk_usage = UserSandbox.get_disk_usage(user_id)
    mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
    cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
    proc = "∞" if resources.max_processes == 0 else str(resources.max_processes)
    disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

    text = (
        f"📊 *مواردك:*\n\n"
        f"💾 الذاكرة: `{mem}`\n"
        f"💻 CPU: `{cpu}`\n"
        f"🔢 العمليات: `{proc}`\n"
        f"💿 المساحة: `{disk_usage}/{disk}` MB\n"
        f"🌐 الشبكة: `{'✅' if resources.network_allowed else '❌'}`\n"
        f"👁️ مراقبة الهروب: `{'✅' if resources.escape_monitor else '❌'}`\n"
        f"💀 قتل تلقائي: `{'✅' if resources.auto_kill_on_escape else '❌'}`"
    )
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main")]]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_admin_dashboard(query):
    total_users = len([d for d in USERS_DIR.iterdir() if d.is_dir()])
    total_bots = 0
    total_running = 0
    for user_dir in USERS_DIR.iterdir():
        if user_dir.is_dir():
            try:
                uid = int(user_dir.name)
                bots = UserBotManager.load_user_bots(uid)
                total_bots += len(bots)
                total_running += sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
            except:
                pass
    banned_count = len(BanSystem.load_banned())
    keyboard = [[InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_manage_users")], [InlineKeyboardButton("🚫 المحظورون", callback_data="admin_banned_users")], [InlineKeyboardButton("📈 إحصائيات", callback_data="admin_stats")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")]]
    await safe_edit_message(query, f"📊 *لوحة تحكم المالك*\n\n👥 المستخدمين: `{total_users}`\n🤖 إجمالي البوتات: `{total_bots}`\n🟢 العاملة: `{total_running}`\n🚫 المحظورون: `{banned_count}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_admin_manage_users(query):
    keyboard = []
    for user_dir in sorted(USERS_DIR.iterdir()):
        if user_dir.is_dir():
            try:
                uid = int(user_dir.name)
                bots = UserBotManager.load_user_bots(uid)
                running = sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
                is_banned, _ = BanSystem.is_banned(uid)
                status = "🚫" if is_banned else "👤"
                keyboard.append([InlineKeyboardButton(f"{status} المستخدم {uid} ({len(bots)} بوت, {running} يعمل)", callback_data=f"admin_user_info_{uid}")])
            except:
                pass
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_dashboard")])
    await safe_edit_message(query, "👥 *إدارة المستخدمين*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_admin_user_info(query, target_user_id: int):
    bots = UserBotManager.load_user_bots(target_user_id)
    running = sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
    is_banned, ban_reason = BanSystem.is_banned(target_user_id)
    resources = UserResourcesManager.get_user_resources(target_user_id)
    disk_usage = UserSandbox.get_disk_usage(target_user_id)

    mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
    cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
    disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

    keyboard = [
        [InlineKeyboardButton("🤖 عرض بوتاته", callback_data=f"admin_view_user_bots_{target_user_id}")],
        [InlineKeyboardButton("📊 تعديل موارده", callback_data=f"admin_edit_resources_{target_user_id}")],
        [InlineKeyboardButton("💰 إضافة نقاط", callback_data=f"admin_add_points_{target_user_id}")]
    ]
    if is_banned:
        keyboard.append([InlineKeyboardButton("✅ إلغاء الحظر", callback_data=f"admin_unban_{target_user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🚫 حظر المستخدم", callback_data=f"admin_ban_{target_user_id}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_manage_users")])

    ban_status = f"🚫 محظور - السبب: {ban_reason}" if is_banned else "✅ نشط"
    await safe_edit_message(query, 
        f"👤 *معلومات المستخدم: {target_user_id}*\n\n"
        f"الحالة: `{ban_status}`\n"
        f"عدد البوتات: `{len(bots)}`\n"
        f"العاملة: `{running}`\n\n"
        f"📊 *موارده:*\n"
        f"💾 الذاكرة: `{mem}`\n"
        f"💻 CPU: `{cpu}`\n"
        f"💿 المساحة: `{disk_usage}/{disk}` MB",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_admin_edit_resources(query, target_user_id: int):
    resources = UserResourcesManager.get_user_resources(target_user_id)
    disk_usage = UserSandbox.get_disk_usage(target_user_id)

    mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
    cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
    proc = "∞" if resources.max_processes == 0 else str(resources.max_processes)
    disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

    keyboard = [
        [InlineKeyboardButton(f"💾 الذاكرة: {mem}", callback_data=f"res_set_mem_{target_user_id}")],
        [InlineKeyboardButton(f"💻 CPU: {cpu}", callback_data=f"res_set_cpu_{target_user_id}")],
        [InlineKeyboardButton(f"🔢 العمليات: {proc}", callback_data=f"res_set_proc_{target_user_id}")],
        [InlineKeyboardButton(f"💿 المساحة: {disk}", callback_data=f"res_set_disk_{target_user_id}")],
        [InlineKeyboardButton(f"🌐 الشبكة: {'✅' if resources.network_allowed else '❌'}", callback_data=f"res_toggle_net_{target_user_id}")],
        [InlineKeyboardButton(f"👁️ مراقبة الهروب: {'✅' if resources.escape_monitor else '❌'}", callback_data=f"res_toggle_esc_{target_user_id}")],
        [InlineKeyboardButton(f"💀 قتل تلقائي: {'✅' if resources.auto_kill_on_escape else '❌'}", callback_data=f"res_toggle_kill_{target_user_id}")],
        [InlineKeyboardButton("♾️ موارد غير محدودة", callback_data=f"res_unlimited_{target_user_id}")],
        [InlineKeyboardButton("🔄 إعادة تعيين", callback_data=f"res_reset_{target_user_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"admin_user_info_{target_user_id}")]
    ]

    await safe_edit_message(query,
        f"📊 *تعديل موارد المستخدم: {target_user_id}*\n\n"
        f"💾 الذاكرة: `{mem}`\n"
        f"💻 CPU: `{cpu}`\n"
        f"🔢 العمليات: `{proc}`\n"
        f"💿 المساحة المستخدمة: `{disk_usage}` MB\n"
        f"💿 حد المساحة: `{disk}`\n"
        f"🌐 الشبكة: `{'✅' if resources.network_allowed else '❌'}`\n"
        f"👁️ مراقبة الهروب: `{'✅' if resources.escape_monitor else '❌'}`\n"
        f"💀 قتل تلقائي: `{'✅' if resources.auto_kill_on_escape else '❌'}`\n\n"
        f"*ملاحظة:* 0 = غير محدود",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_toggle_net(query, target_user_id: int):
    resources = UserResourcesManager.get_user_resources(target_user_id)
    UserResourcesManager.set_user_resources(target_user_id, network_allowed=not resources.network_allowed)
    await query.answer("✅ تم تبديل الشبكة", show_alert=True)
    await handle_admin_edit_resources(query, target_user_id)

async def handle_toggle_esc(query, target_user_id: int):
    resources = UserResourcesManager.get_user_resources(target_user_id)
    UserResourcesManager.set_user_resources(target_user_id, escape_monitor=not resources.escape_monitor)
    await query.answer("✅ تم تبديل مراقبة الهروب", show_alert=True)
    await handle_admin_edit_resources(query, target_user_id)

async def handle_toggle_kill(query, target_user_id: int):
    resources = UserResourcesManager.get_user_resources(target_user_id)
    UserResourcesManager.set_user_resources(target_user_id, auto_kill_on_escape=not resources.auto_kill_on_escape)
    await query.answer("✅ تم تبديل القتل التلقائي", show_alert=True)
    await handle_admin_edit_resources(query, target_user_id)

async def handle_unlimited_resources(query, target_user_id: int):
    UserResourcesManager.set_unlimited_resources(target_user_id)
    await query.answer("✅ تم تعيين موارد غير محدودة", show_alert=True)
    await handle_admin_edit_resources(query, target_user_id)

async def handle_reset_resources(query, target_user_id: int):
    UserResourcesManager.reset_to_default(target_user_id)
    await query.answer("✅ تم إعادة تعيين الموارد", show_alert=True)
    await handle_admin_edit_resources(query, target_user_id)

async def handle_unban_user(query, target_user_id: int):
    BanSystem.unban_user(target_user_id)
    await query.answer("✅ تم إلغاء الحظر", show_alert=True)
    await handle_admin_user_info(query, target_user_id)

async def handle_banned_users(query):
    banned = BanSystem.load_banned()
    if not banned:
        await safe_edit_message(query, "✅ لا يوجد محظورين.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_dashboard")]]))
        return
    text = "🚫 *المحظورون:*\n\n"
    keyboard = []
    for uid, ban_data in banned.items():
        text += f"• `{uid}` - {ban_data.get('reason', 'لا يوجد سبب')}\n"
        keyboard.append([InlineKeyboardButton(f"✅ إلغاء حظر {uid}", callback_data=f"admin_unban_{uid}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_dashboard")])
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_all_bots(query):
    total_bots = 0
    total_running = 0
    for user_dir in USERS_DIR.iterdir():
        if user_dir.is_dir():
            try:
                uid = int(user_dir.name)
                bots = UserBotManager.load_user_bots(uid)
                total_bots += len(bots)
                total_running += sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
            except:
                pass
    await safe_edit_message(query, f"🤖 *جميع البوتات*\n\nإجمالي البوتات: `{total_bots}`\nالعاملة: `{total_running}`\nالمتوقفة: `{total_bots - total_running}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_dashboard")]]), parse_mode=ParseMode.MARKDOWN)

async def handle_modes_menu(query):
    modes = system_settings.bot_modes
    keyboard = [
        [InlineKeyboardButton(f"🛠 وضع الصيانة: {'🟢 ON' if modes.maintenance_mode else '🔴 OFF'}", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(f"🔒 وضع الخصوصية: {'🟢 ON' if modes.privacy_mode else '🔴 OFF'}", callback_data="toggle_privacy")],
        [InlineKeyboardButton("✏️ تعديل رسالة الصيانة", callback_data="edit_maintenance_msg")],
        [InlineKeyboardButton("✏️ تعديل رسالة الخصوصية", callback_data="edit_privacy_msg")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")]
    ]
    text = f"⚙️ *إدارة أوضاع البوت*\n\n🛠 *وضع الصيانة:*\nالحالة: `{'🟢 مفعل' if modes.maintenance_mode else '🔴 معطل'}`\nالرسالة: `{escape_markdown(modes.maintenance_message)}`\n\n🔒 *وضع الخصوصية:*\nالحالة: `{'🟢 مفعل' if modes.privacy_mode else '🔴 معطل'}`\nالرسالة: `{escape_markdown(modes.privacy_message)}`"
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_toggle_maintenance(query):
    system_settings.bot_modes.maintenance_mode = not system_settings.bot_modes.maintenance_mode
    save_settings(system_settings)
    await query.answer("✅ تم التبديل", show_alert=True)
    await handle_modes_menu(query)

async def handle_toggle_privacy(query):
    system_settings.bot_modes.privacy_mode = not system_settings.bot_modes.privacy_mode
    save_settings(system_settings)
    await query.answer("✅ تم التبديل", show_alert=True)
    await handle_modes_menu(query)

async def handle_codes_menu(query):
    all_codes = PointsCodesSystem.get_all_codes()
    active_codes = sum(1 for c in all_codes.values() if c['active'])
    keyboard = [[InlineKeyboardButton("➕ إنشاء كود جديد", callback_data="admin_create_code")], [InlineKeyboardButton("📋 قائمة الأكواد", callback_data="admin_list_codes")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")]]
    await safe_edit_message(query, f"🎁 *نظام أكواد النقاط*\n\n📊 إجمالي الأكواد: `{len(all_codes)}`\nالنشطة: `{active_codes}`\nالاستخدامات: `{sum(c['used_count'] for c in all_codes.values())}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_code_info(query, code: str):
    codes = PointsCodesSystem.load_codes()
    if code in codes:
        code_data = codes[code]
        status = "🟢 نشط" if code_data['active'] else "🔴 غير نشط"
        expiry = code_data.get('expiry', 'غير محدد')
        text = f"ℹ️ *معلومات الكود:* `{code}`\n\n💰 النقاط: `{code_data['points']}`\n👥 الاستخدامات: `{code_data['used_count']}/{code_data['max_uses']}`\nالحالة: {status}\n📅 الإنشاء: `{code_data['created_at']}`\n⏰ الصلاحية: `{expiry}`"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_list_codes")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_toggle_code(query, code: str):
    codes = PointsCodesSystem.load_codes()
    if code in codes:
        codes[code]['active'] = not codes[code]['active']
        PointsCodesSystem.save_codes(codes)
        await query.answer("✅ تم تبديل حالة الكود", show_alert=True)
    await show_codes_list(query, 0)

async def handle_broadcast_menu(query):
    subscribers = broadcast_settings.load_subscribers()
    keyboard = [
        [InlineKeyboardButton("📢 إذاعة شاملة (أي شيء)", callback_data="broadcast_any")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="broadcast_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")]
    ]
    await safe_edit_message(query, f"📢 *نظام الإذاعة*\n\n📊 عدد المشتركين: `{len(subscribers)}`\n\nيمكنك إرسال أي نوع من المحتوى (نص، صورة، فيديو، صوت، ملف، ملصق، استيكر...) وسيتم إعادة إرساله لكل المشتركين.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_broadcast_stats(query):
    subscribers = broadcast_settings.load_subscribers()
    await query.edit_message_text(f"📊 *إحصائيات الإذاعة*\n\n📢 عدد المشتركين: `{len(subscribers)}`", parse_mode=ParseMode.MARKDOWN)

async def handle_backups(query):
    backups = list_backups()
    if not backups:
        keyboard = [[InlineKeyboardButton("💾 نسخة جديدة", callback_data="admin_create_backup")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")]]
        await safe_edit_message(query, "📭 لا توجد نسخ.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    text = "💾 *النسخ الاحتياطية:*\n\n"
    keyboard = []
    for name, date, size in backups[:10]:
        text += f"• `{name}`\n   📅 {date} | 💾 {size:.1f} MB\n\n"
        keyboard.append([InlineKeyboardButton(f"📥 {name[:30]}...", callback_data=f"admin_restore_backup_{name}")])
    keyboard.append([InlineKeyboardButton("💾 نسخة جديدة", callback_data="admin_create_backup")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")])
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_create_backup(query):
    await query.edit_message_text("⏳ جاري إنشاء نسخة...")
    success, msg = create_backup()
    await query.edit_message_text(msg)

async def handle_restore_backup(query, backup_name: str):
    await query.edit_message_text(f"⏳ جاري استعادة النسخة: {backup_name}...")
    success, msg = restore_backup(backup_name)
    await query.edit_message_text(msg)

async def handle_points_settings(query):
    keyboard = [
        [InlineKeyboardButton(f"📤 تكلفة الرفع ({points_config.points_per_upload})", callback_data="admin_set_points_upload")],
        [InlineKeyboardButton(f"🔄 نقاط التحديث ({points_config.points_per_update})", callback_data="admin_set_points_update")],
        [InlineKeyboardButton(f"👥 نقاط الدعوة ({points_config.points_per_invite})", callback_data="admin_set_points_invite")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin_main")]
    ]
    await safe_edit_message(query, f"⚙️ *إعدادات النقاط*\n\n📤 رفع بوت جديد: يستهلك `{points_config.points_per_upload}` نقطة\n🔄 تحديث بوت: `{points_config.points_per_update}` نقطة (مجاني)\n👥 دعوة صديق: `{points_config.points_per_invite}` نقاط", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_admin_stats(query):
    total_users = len([d for d in USERS_DIR.iterdir() if d.is_dir()])
    total_bots = 0
    total_running = 0
    for user_dir in USERS_DIR.iterdir():
        if user_dir.is_dir():
            try:
                uid = int(user_dir.name)
                bots = UserBotManager.load_user_bots(uid)
                total_bots += len(bots)
                total_running += sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
            except:
                pass
    banned_count = len(BanSystem.load_banned())
    try:
        total_size = sum(f.stat().st_size for f in USERS_DIR.rglob('*') if f.is_file()) / 1024 / 1024
    except:
        total_size = 0
    all_points = PointsSystem.load_user_points()
    total_users_points = len(all_points)
    total_points_distributed = sum(data['points'] for data in all_points.values())
    all_codes = PointsCodesSystem.get_all_codes()
    active_codes = sum(1 for c in all_codes.values() if c['active'])
    await safe_edit_message(query, f"📈 *إحصائيات النظام*\n\n👥 المستخدمين: `{total_users}`\n🤖 البوتات: `{total_bots}`\n🟢 العاملة: `{total_running}`\n🚫 المحظورون: `{banned_count}`\n💾 المساحة: `{total_size:.2f}` MB\n\n💰 مستخدمي النقاط: `{total_users_points}`\n💰 إجمالي النقاط: `{total_points_distributed}`\n\n🎁 الأكواد: `{len(all_codes)}` (نشط: `{active_codes}`)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_dashboard")]]), parse_mode=ParseMode.MARKDOWN)

async def handle_user_points(query, user_id: int):
    user_points = PointsSystem.get_user_points(user_id)
    points_data = PointsSystem.load_user_points()
    user_history = points_data.get(user_id, {}).get('history', [])
    text = f"💰 *نقاطك:* `{user_points}`\n\n"
    if user_history:
        text += "📜 *آخر 5 عمليات:*\n"
        for entry in user_history[-5:]:
            text += f"• `{entry['date']}`: {entry['points']:+d} - {entry['reason']}\n"
    keyboard = [[InlineKeyboardButton("🎁 استخدام كود", callback_data="user_use_code")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main")]]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_invite_link(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    invite_stats = InviteSystem.get_invite_stats(user_id)
    bot_username = (await context.bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start=ref_{invite_stats['code']}"
    text = f"🔗 *رابط الدعوة*\n\n`{invite_link}`\n\n👥 *عدد الدعوات:* `{invite_stats['total_invites']}`\n💰 *نقاط لكل دعوة:* `{points_config.points_per_invite}`"
    keyboard = [[InlineKeyboardButton("📤 مشاركة", url=f"https://t.me/share/url?url={invite_link}&text=انضم%20إلى%20FPI%20SX%20MANAGER!")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main")]]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_user_stats(query, user_id: int):
    bots = UserBotManager.load_user_bots(user_id)
    running = sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
    user_points = PointsSystem.get_user_points(user_id)
    invite_stats = InviteSystem.get_invite_stats(user_id)
    text = f"📈 *إحصائياتك:*\n\n🤖 *البوتات:* `{len(bots)}`\n🟢 *العاملة:* `{running}`\n🔴 *المتوقفة:* `{len(bots) - running}`\n\n💰 *نقاطك:* `{user_points}`\n👥 *دعواتك:* `{invite_stats['total_invites']}`"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main")]]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_logs_menu(query):
    keyboard = [
        [InlineKeyboardButton("📜 سجل النشاطات", callback_data="user_activity_log")],
        [InlineKeyboardButton("📜 سجلات البوتات", callback_data="user_bots_logs")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main")]
    ]
    await safe_edit_message(query, "📜 *السجلات*\n\nاختر نوع السجل:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def handle_activity_log(query):
    if ACTIVITY_LOG_FILE.exists():
        try:
            log_content = ACTIVITY_LOG_FILE.read_text(encoding='utf-8', errors='ignore')
            if len(log_content) > 4000:
                log_content = log_content[-4000:]
            await query.edit_message_text(f"📜 *سجل النشاطات:*\n```\n{log_content}\n```", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ في قراءة السجل: {e}")
    else:
        await query.edit_message_text("📭 لا يوجد سجل.")

async def handle_bots_logs(query, user_id: int):
    bots = UserBotManager.load_user_bots(user_id)
    if not bots:
        await query.edit_message_text("📭 لا توجد بوتات.")
    else:
        keyboard = []
        for bot in bots:
            keyboard.append([InlineKeyboardButton(f"📜 {bot.name}", callback_data=f"user_bot_log_{bot.id}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="user_logs_menu")])
        await safe_edit_message(query, "📜 *سجلات البوتات:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_user_bots_list(query, user_id: int, is_admin_view: bool = False):
    bots = UserBotManager.load_user_bots(user_id)
    if not bots:
        keyboard = [[InlineKeyboardButton("➕ إضافة بوت", callback_data="user_add_bot")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main" if not is_admin_view else f"admin_user_info_{user_id}")]]
        await safe_edit_message(query, "📭 لا توجد بوتات.\n\nاضغط 'إضافة بوت' لرفع بوت جديد.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    keyboard = []
    for bot in bots:
        status = "🟢" if UserBotManager.is_bot_running(bot.id) else "🔴"
        keyboard.append([InlineKeyboardButton(f"{status} {bot.name}", callback_data=f"user_bot_info_{bot.id}")])
    keyboard.append([InlineKeyboardButton("➕ إضافة بوت", callback_data="user_add_bot")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_user_main" if not is_admin_view else f"admin_user_info_{user_id}")])
    await safe_edit_message(query, f"📋 *قائمة بوتاتك ({len(bots)}):*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_user_bot_info(query, user_id: int, bot_id: str):
    bots = UserBotManager.load_user_bots(user_id)
    bot = next((b for b in bots if b.id == bot_id), None)
    if not bot:
        await query.answer("❌ البوت غير موجود")
        return
    is_running = UserBotManager.is_bot_running(bot_id)
    status = "🟢 يعمل" if is_running else "🔴 متوقف"
    uptime = ""
    if is_running and bot_id in UserBotManager.bot_start_times:
        delta = datetime.now() - UserBotManager.bot_start_times[bot_id]
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"⏱ وقت التشغيل: `{hours}h {minutes}m`\n"
    text = f"🤖 *{bot.name}*\n🆔 `{bot.id}`\n📁 `{bot.folder}`\n📄 `{bot.main_file}`\n📊 الحالة: {status}\n🔄 إعادة التشغيل: `{bot.restart_count}`\n{uptime}📅 الإضافة: `{bot.added_at}`"
    keyboard = [
        [InlineKeyboardButton("▶️ تشغيل", callback_data=f"user_bot_start_{bot.id}"), InlineKeyboardButton("⏹️ إيقاف", callback_data=f"user_bot_stop_{bot.id}"), InlineKeyboardButton("🔄 إعادة", callback_data=f"user_bot_restart_{bot.id}")],
        [InlineKeyboardButton("🖥 Console", callback_data=f"user_bot_console_{bot.id}"), InlineKeyboardButton("📜 السجل", callback_data=f"user_bot_log_{bot.id}")],
        [InlineKeyboardButton("📦 تحديث", callback_data=f"user_bot_update_{bot.id}"), InlineKeyboardButton("🗑️ حذف", callback_data=f"user_bot_delete_{bot.id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="user_manage_bots")]
    ]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_user_bot_console(query, user_id: int, bot_id: str):
    bots = UserBotManager.load_user_bots(user_id)
    bot = next((b for b in bots if b.id == bot_id), None)
    if not bot:
        await query.answer("❌ البوت غير موجود")
        return
    console = UserBotManager.get_bot_console(bot_id)
    output = console.get_output(50)
    line_count = console.get_line_count()
    is_running = UserBotManager.is_bot_running(bot_id)
    status = "🟢 يعمل" if is_running else "🔴 متوقف"
    text = f"🖥 *Console البوت: {bot.name}*\n\n📊 الحالة: {status}\n📄 إجمالي الأسطر: `{line_count}`\n\n*آخر 50 سطر:*\n```\n{output or 'لا يوجد إخراج بعد...'}\n```"
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث", callback_data=f"user_bot_console_{bot_id}"), InlineKeyboardButton("⌨️ إرسال أمر", callback_data=f"user_bot_sendcmd_{bot_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"user_bot_info_{bot_id}")]
    ]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_codes_list(query, page: int = 0):
    all_codes = PointsCodesSystem.get_all_codes()
    codes_list = list(all_codes.items())
    if not codes_list:
        keyboard = [[InlineKeyboardButton("➕ إنشاء كود", callback_data="admin_create_code")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_codes_menu")]]
        await safe_edit_message(query, "📭 لا توجد أكواد.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    per_page = 5
    total_pages = (len(codes_list) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    current_codes = codes_list[start:end]
    text = f"📋 *قائمة الأكواد* (صفحة {page + 1}/{total_pages})\n\n"
    keyboard = []
    for code, code_data in current_codes:
        status = "🟢" if code_data['active'] else "🔴"
        text += f"{status} *{code}*\n  💰 النقاط: `{code_data['points']}`\n  👥 الاستخدامات: `{code_data['used_count']}/{code_data['max_uses']}`\n  ⏰ الصلاحية: `{code_data.get('expiry', 'غير محدد')}`\n\n"
        keyboard.append([InlineKeyboardButton(f"ℹ️ {code[:15]}...", callback_data=f"code_info_{code}"), InlineKeyboardButton("🗑️" if code_data['active'] else "✅", callback_data=f"toggle_code_{code}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"codes_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"codes_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_codes_menu")])
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_user_main_menu(query, user_id: int, context: ContextTypes.DEFAULT_TYPE = None):

    user_points = PointsSystem.get_user_points(user_id)
    bots = UserBotManager.load_user_bots(user_id)
    running = sum(1 for b in bots if UserBotManager.is_bot_running(b.id))
    invite_stats = InviteSystem.get_invite_stats(user_id)
    resources = UserResourcesManager.get_user_resources(user_id)
    disk_usage = UserSandbox.get_disk_usage(user_id)

    keyboard = [
        [InlineKeyboardButton("📊 لوحة التحكم", callback_data="user_dashboard")],
        [InlineKeyboardButton("🤖 إدارة بوتاتي", callback_data="user_manage_bots")],
        [InlineKeyboardButton("📈 إحصائياتي", callback_data="user_stats")],
        [InlineKeyboardButton("💰 نقاطي", callback_data="user_points")],
        [InlineKeyboardButton("🔗 رابط الدعوة", callback_data="user_invite_link")],
        [InlineKeyboardButton("🎁 استخدام كود", callback_data="user_use_code")],
        [InlineKeyboardButton("📜 سجلاتي", callback_data="user_logs_menu")],
        [InlineKeyboardButton("📊 مواردي", callback_data="user_resources")],
    ]

    mem = "∞" if resources.max_memory_mb == 0 else f"{resources.max_memory_mb} MB"
    cpu = "∞" if resources.max_cpu_percent == 0 else f"{resources.max_cpu_percent}%"
    disk = "∞" if resources.max_disk_mb == 0 else f"{resources.max_disk_mb} MB"

    text = (
        f"👋 *مرحباً بك في FPI SX MANAGER!*\n\n"
        f"🤖 *بوتاتك:* `{len(bots)}` (يعمل: `{running}`)\n"
        f"💰 *نقاطك:* `{user_points}`\n"
        f"👥 *دعواتك:* `{invite_stats['total_invites']}`\n\n"
        f"📤 *رفع ملف* يستهلك `{points_config.points_per_upload}` نقطة\n"
        f"🔄 *تحديث ملف* مجاني\n"
        f"👥 *دعوة صديق* = `{points_config.points_per_invite}` نقاط\n\n"
        f"📊 *مواردك:*\n"
        f"💾 الذاكرة: `{mem}`\n"
        f"💻 CPU: `{cpu}`\n"
        f"💿 المساحة: `{disk_usage}/{disk}` MB"
    )

    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def broadcast_any_content(update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str, file_id: str = None, caption: str = None, sticker_file_id: str = None):

    subscribers = broadcast_settings.load_subscribers()
    if not subscribers:
        await update.message.reply_text("❌ لا يوجد مشتركين.")
        return
    await update.message.reply_text(f"⏳ جاري الإذاعة لـ {len(subscribers)} مشترك...")
    success = 0
    fail = 0
    for sub_id in subscribers:
        try:
            if content_type == 'text':
                await context.bot.send_message(sub_id, text=caption, parse_mode=ParseMode.MARKDOWN)
            elif content_type == 'photo':
                await context.bot.send_photo(sub_id, photo=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            elif content_type == 'video':
                await context.bot.send_video(sub_id, video=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            elif content_type == 'document':
                await context.bot.send_document(sub_id, document=file_id, caption=caption)
            elif content_type == 'sticker':
                await context.bot.send_sticker(sub_id, sticker=sticker_file_id)
            elif content_type == 'audio':
                await context.bot.send_audio(sub_id, audio=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            elif content_type == 'voice':
                await context.bot.send_voice(sub_id, voice=file_id, caption=caption)
            elif content_type == 'animation':
                await context.bot.send_animation(sub_id, animation=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await update.message.reply_text(f"📢 *تمت الإذاعة*\n\n✅ نجح: `{success}`\n❌ فشل: `{fail}`", parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    is_banned, reason = BanSystem.is_banned(user_id)
    if is_banned:
        await update.message.reply_text(f"🚫 تم حظرك: {reason}")
        return

    if REQUIRED_CHANNEL and REQUIRED_CHANNEL != "@fpi_sx_channel":
        is_subscribed = await SubscriptionSystem.check_subscription(user_id, context.bot)
        if not is_subscribed:
            await update.message.reply_text("⚠️ يجب الاشتراك في القناة أولاً!")
            return

    allowed, message = check_bot_modes(user_id)
    if not allowed:
        await update.message.reply_text(message)
        return

    broadcast_settings.add_subscriber(user_id)

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if text == "/cancel":
        context.user_data.clear()
        await update.message.reply_text("❌ تم الإلغاء.")
        return

    if context.user_data.get('waiting_for_bot_name'):
        bot_name = text
        context.user_data['bot_name'] = bot_name
        context.user_data['waiting_for_bot_name'] = False
        context.user_data['waiting_for_zip'] = True
        await update.message.reply_text(f"📛 اسم البوت: `{bot_name}`\n📦 الآن أرسل ملف ZIP.", parse_mode=ParseMode.MARKDOWN)
        return

    if context.user_data.get('waiting_for_command'):
        bot_id = context.user_data.pop('waiting_for_command')
        command = text
        success = UserBotManager.send_command_to_bot(bot_id, command)
        if success:
            await update.message.reply_text(f"✅ *تم إرسال الأمر:*\n```\n{command}\n```", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ فشل إرسال الأمر")
        keyboard = [[InlineKeyboardButton("🖥 رجوع للكونسول", callback_data=f"user_bot_console_{bot_id}")]]
        await update.message.reply_text("اختر الخطوة التالية:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if context.user_data.get('waiting_for_code_input'):
        code = text.strip().upper()
        context.user_data.pop('waiting_for_code_input', None)
        success, msg, new_total = PointsCodesSystem.use_code(code, user_id)
        keyboard = [[InlineKeyboardButton("💰 نقاطي", callback_data="user_points")], [InlineKeyboardButton("🎁 استخدام كود آخر", callback_data="user_use_code")]]
        await update.message.reply_text(f"{msg}\n\n💰 *رصيدك:* `{new_total}` نقطة", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        return

    if context.user_data.get('banning_user') and is_admin(user_id):
        target_user_id = context.user_data.pop('banning_user')
        BanSystem.ban_user(target_user_id, text, user_id)
        await update.message.reply_text(f"🚫 تم حظر المستخدم {target_user_id}\nالسبب: {text}")
        return

    if context.user_data.get('waiting_for_add_points') and is_admin(user_id):
        target_user_id = context.user_data.pop('waiting_for_add_points')
        try:
            points = int(text)
            new_total = PointsSystem.add_points(target_user_id, points, f"إضافة يدوية من المالك {user_id}")
            await update.message.reply_text(f"✅ تم إضافة {points} نقطة للمستخدم {target_user_id}\n💰 الرصيد الجديد: {new_total}")
        except ValueError:
            await update.message.reply_text("❌ يجب إدخال رقم صحيح")
        return

    if context.user_data.get('waiting_for_maintenance_msg') and is_admin(user_id):
        context.user_data.pop('waiting_for_maintenance_msg')
        system_settings.bot_modes.maintenance_message = text
        save_settings(system_settings)
        await update.message.reply_text(f"✅ تم تعديل رسالة الصيانة:\n\n`{text}`", parse_mode=ParseMode.MARKDOWN)
        return

    if context.user_data.get('waiting_for_privacy_msg') and is_admin(user_id):
        context.user_data.pop('waiting_for_privacy_msg')
        system_settings.bot_modes.privacy_message = text
        save_settings(system_settings)
        await update.message.reply_text(f"✅ تم تعديل رسالة الخصوصية:\n\n`{text}`", parse_mode=ParseMode.MARKDOWN)
        return

    if context.user_data.get('waiting_for_code_details') and is_admin(user_id):
        context.user_data.pop('waiting_for_code_details')
        try:
            parts = text.split(':')
            if len(parts) != 3:
                raise ValueError("يجب إدخال ثلاثة أرقام: نقاط:استخدامات:أيام_الصلاحية")
            points = int(parts[0])
            max_uses = int(parts[1])
            expiry_days = int(parts[2])
            code = PointsCodesSystem.generate_code(points, max_uses, expiry_days, user_id)
            await update.message.reply_text(f"🎁 *تم إنشاء الكود!*\n\n*الكود:* `{code}`\n💰 النقاط: `{points}`\n👥 الاستخدامات: `{max_uses}`\n⏰ الصلاحية: `{expiry_days}` يوم", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}\n\nاستخدم: `نقاط:استخدامات:أيام_الصلاحية`", parse_mode=ParseMode.MARKDOWN)
        return

    if context.user_data.get('waiting_for_points_upload') and is_admin(user_id):
        context.user_data.pop('waiting_for_points_upload')
        try:
            points_config.points_per_upload = int(text)
            save_points_config(points_config)
            await update.message.reply_text(f"✅ تم تغيير تكلفة الرفع إلى: `{text}` نقطة", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_points_update') and is_admin(user_id):
        context.user_data.pop('waiting_for_points_update')
        try:
            points_config.points_per_update = int(text)
            save_points_config(points_config)
            await update.message.reply_text(f"✅ تم تغيير نقاط التحديث إلى: `{text}` نقطة", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_points_invite') and is_admin(user_id):
        context.user_data.pop('waiting_for_points_invite')
        try:
            points_config.points_per_invite = int(text)
            save_points_config(points_config)
            await update.message.reply_text(f"✅ تم تغيير نقاط الدعوة إلى: `{text}` نقطة", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_res_memory') and is_admin(user_id):
        target_user_id = context.user_data.pop('waiting_for_res_memory')
        try:
            value = int(text)
            UserResourcesManager.set_user_resources(target_user_id, max_memory_mb=value)
            mem = "∞" if value == 0 else f"{value} MB"
            await update.message.reply_text(f"✅ تم تغيير حد الذاكرة للمستخدم {target_user_id} إلى: `{mem}`", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_res_cpu') and is_admin(user_id):
        target_user_id = context.user_data.pop('waiting_for_res_cpu')
        try:
            value = int(text)
            UserResourcesManager.set_user_resources(target_user_id, max_cpu_percent=value)
            cpu = "∞" if value == 0 else f"{value}%"
            await update.message.reply_text(f"✅ تم تغيير حد CPU للمستخدم {target_user_id} إلى: `{cpu}`", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_res_proc') and is_admin(user_id):
        target_user_id = context.user_data.pop('waiting_for_res_proc')
        try:
            value = int(text)
            UserResourcesManager.set_user_resources(target_user_id, max_processes=value)
            proc = "∞" if value == 0 else str(value)
            await update.message.reply_text(f"✅ تم تغيير حد العمليات للمستخدم {target_user_id} إلى: `{proc}`", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_res_disk') and is_admin(user_id):
        target_user_id = context.user_data.pop('waiting_for_res_disk')
        try:
            value = int(text)
            UserResourcesManager.set_user_resources(target_user_id, max_disk_mb=value)
            disk = "∞" if value == 0 else f"{value} MB"
            await update.message.reply_text(f"✅ تم تغيير حد المساحة للمستخدم {target_user_id} إلى: `{disk}`", parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ قيمة غير صالحة")
        return

    if context.user_data.get('waiting_for_broadcast_any') and is_admin(user_id):
        context.user_data.pop('waiting_for_broadcast_any')
        await broadcast_any_content(update, context, 'text', caption=text)
        return

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    is_banned, reason = BanSystem.is_banned(user_id)
    if is_banned:
        await update.message.reply_text(f"🚫 تم حظرك: {reason}")
        return

    if REQUIRED_CHANNEL and REQUIRED_CHANNEL != "@fpi_sx_channel":
        is_subscribed = await SubscriptionSystem.check_subscription(user_id, context.bot)
        if not is_subscribed:
            await update.message.reply_text("⚠️ يجب الاشتراك في القناة أولاً!")
            return

    document = update.message.document
    if not document or not document.file_name.endswith('.zip'):
        await update.message.reply_text("❗ أرسل ملف ZIP صالح.")
        return

    if context.user_data.get('waiting_for_zip'):
        bot_name = context.user_data.get('bot_name')
        if not bot_name:
            await update.message.reply_text("❗ لم يتم إرسال اسم البوت.")
            return

        user_points = PointsSystem.get_user_points(user_id)
        if user_points < points_config.points_per_upload:
            await update.message.reply_text(f"❌ لا تملك نقاط كافية لرفع بوت. تحتاج `{points_config.points_per_upload}` نقطة. احصل على نقاط عبر كود أو اشتراك.", parse_mode=ParseMode.MARKDOWN)
            context.user_data.pop('waiting_for_zip', None)
            context.user_data.pop('bot_name', None)
            return

        resources = UserResourcesManager.get_user_resources(user_id)
        if resources.max_disk_mb > 0:
            disk_usage = UserSandbox.get_disk_usage(user_id)
            if disk_usage >= resources.max_disk_mb:
                await update.message.reply_text(f"❌ تجاوزت حد المساحة ({disk_usage}/{resources.max_disk_mb} MB)")
                context.user_data.pop('waiting_for_zip', None)
                context.user_data.pop('bot_name', None)
                return

        await update.message.reply_text("⏳ جاري تحميل الملف...")
        file = await context.bot.get_file(document.file_id)
        user_uploads = UserSandbox.get_user_dir(user_id) / "uploads"
        temp_zip = user_uploads / f"temp_{int(time.time())}.zip"
        await file.download_to_drive(str(temp_zip))

        await update.message.reply_text("⚙️ جاري فك الضغط وإعداد البوت... قد يستغرق هذا بعض الوقت لتثبيت المكتبات.")
        folder, main_file, msg = UserBotManager.extract_and_setup_bot(user_id, temp_zip, bot_name)
        temp_zip.unlink()

        if folder:
            await update.message.reply_text("📦 جاري تثبيت المكتبات المطلوبة للبوت...")
            try:
                bot_folder_path = UserSandbox.get_user_bots_dir(user_id) / folder
                setup_success, setup_msg = AutoInstaller.setup_bot_environment(bot_folder_path)
                if not setup_success:
                    raise RuntimeError(setup_msg)
                await update.message.reply_text(f"✅ {setup_msg} للبوت `{bot_name}`.\n⚡ تم تجهيز التشغيل السريع.")
            except Exception as e:
                await update.message.reply_text(f"❌ فشل تثبيت المكتبات للبوت `{bot_name}`: {e}")
                shutil.rmtree(UserSandbox.get_user_bots_dir(user_id) / folder, ignore_errors=True)
                context.user_data.pop('waiting_for_zip', None)
                context.user_data.pop('bot_name', None)
                return

        if not folder:
            await update.message.reply_text(f"❌ فشل: {msg}")
            context.user_data.pop('waiting_for_zip', None)
            context.user_data.pop('bot_name', None)
            return

        bot_id = UserBotManager.generate_bot_id(user_id)
        bots = UserBotManager.load_user_bots(user_id)
        bots.append(UserBotConfig(
            id=bot_id,
            user_id=user_id,
            name=bot_name,
            folder=folder,
            main_file=main_file,
            added_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        UserBotManager.save_user_bots(user_id, bots)

        new_total = PointsSystem.add_points(user_id, -points_config.points_per_upload, f"رفع بوت: {bot_name}")

        await update.message.reply_text(
            f"✅ تمت إضافة البوت `{bot_name}` بنجاح.\n"
            f"🆔 المعرف: `{bot_id}`\n"
            f"💰 تم خصم `{points_config.points_per_upload}` نقطة\n"
            f"📊 رصيدك: `{new_total}` نقطة",
            parse_mode=ParseMode.MARKDOWN
        )

        context.user_data.pop('waiting_for_zip', None)
        context.user_data.pop('bot_name', None)
        return

    if context.user_data.get('waiting_for_update_zip'):
        bot_id = context.user_data.get('waiting_for_update_zip')
        bots = UserBotManager.load_user_bots(user_id)
        bot = next((b for b in bots if b.id == bot_id), None)
        if not bot:
            await update.message.reply_text("❌ البوت غير موجود")
            context.user_data.pop('waiting_for_update_zip', None)
            return

        was_running = UserBotManager.is_bot_running(bot_id)
        if was_running:
            UserBotManager.stop_bot(bot_id)

        await update.message.reply_text("⏳ جاري تحميل الملف...")
        file = await context.bot.get_file(document.file_id)
        user_uploads = UserSandbox.get_user_dir(user_id) / "uploads"
        temp_zip = user_uploads / f"temp_update_{int(time.time())}.zip"
        await file.download_to_drive(str(temp_zip))

        await update.message.reply_text("⚙️ جاري تحديث البوت... قد يستغرق هذا بعض الوقت لتثبيت المكتبات.")
        folder, main_file, msg = UserBotManager.extract_and_setup_bot(user_id, temp_zip, bot.name, existing_folder=bot.folder)
        temp_zip.unlink()

        if folder:
            await update.message.reply_text("📦 جاري تثبيت المكتبات المطلوبة للبوت المحدث...")
            try:
                bot_folder_path = UserSandbox.get_user_bots_dir(user_id) / folder
                setup_success, setup_msg = AutoInstaller.setup_bot_environment(bot_folder_path)
                if not setup_success:
                    raise RuntimeError(setup_msg)
                await update.message.reply_text(f"✅ {setup_msg} للبوت المحدث `{bot.name}`.\n⚡ تم تجهيز التشغيل السريع.")
            except Exception as e:
                await update.message.reply_text(f"❌ فشل تثبيت المكتبات للبوت المحدث `{bot.name}`: {e}")
                if was_running:
                    await update.message.reply_text("⚠️ فشل تثبيت المكتبات، لم يتم إعادة تشغيل البوت.")
                context.user_data.pop('waiting_for_update_zip', None)
                return

            bot.main_file = main_file or bot.main_file
            UserBotManager.save_user_bots(user_id, bots)

            await update.message.reply_text(f"✅ تم تحديث البوت `{bot.name}` مجاناً!")
            if was_running:
                time.sleep(1)
                UserBotManager.start_bot(user_id, bot_id, context)
                await update.message.reply_text("🔄 تم إعادة تشغيل البوت")
        else:
            await update.message.reply_text(f"❌ فشل التحديث: {msg}")

        context.user_data.pop('waiting_for_update_zip', None)
        return

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        await broadcast_any_content(update, context, 'photo', photo.file_id, caption)
        return

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        video = update.message.video
        caption = update.message.caption or ""
        await broadcast_any_content(update, context, 'video', video.file_id, caption)
        return

async def handle_document_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        doc = update.message.document
        caption = update.message.caption or ""
        await broadcast_any_content(update, context, 'document', doc.file_id, caption)
        return

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        sticker = update.message.sticker
        await broadcast_any_content(update, context, 'sticker', sticker_file_id=sticker.file_id)
        return

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        audio = update.message.audio
        caption = update.message.caption or ""
        await broadcast_any_content(update, context, 'audio', audio.file_id, caption)
        return

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        voice = update.message.voice
        caption = update.message.caption or ""
        await broadcast_any_content(update, context, 'voice', voice.file_id, caption)
        return

async def handle_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast_any') and is_admin(update.effective_user.id):
        del context.user_data['waiting_for_broadcast_any']
        animation = update.message.animation
        caption = update.message.caption or ""
        await broadcast_any_content(update, context, 'animation', animation.file_id, caption)
        return

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_activity(f"❌ خطأ: {context.error}", "ERROR")
    error_message = str(context.error)
    tb_text = ''.join(traceback.format_exception(None, context.error, getattr(context.error, '__traceback__', None)))

    try:
        await send_error_report(
            error_message,
            tb_text,
            title="خطأ داخل مدير البوت",
            extra_info={
                "update": type(update).__name__ if update else 'None'
            }
        )
    except Exception as report_error:
        print(f"❌ فشل إرسال تقرير الخطأ من error_handler: {report_error}")

    print(tb_text)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args and context.args[0].startswith('ref_'):
        invite_code = context.args[0][4:]

        invites = InviteSystem.load_invites()
        for inviter_str, data in invites.items():
            if data.get('code') == invite_code:
                inviter_id = int(inviter_str)
                if inviter_id != user_id:
                    InviteSystem.add_invite(inviter_id, user_id)
                break

    is_banned, reason = BanSystem.is_banned(user_id)
    if is_banned:
        await update.message.reply_text(f"🚫 تم حظرك: {reason}")
        return

    if REQUIRED_CHANNEL and REQUIRED_CHANNEL != "@fpi_sx_channel":
        is_subscribed = await SubscriptionSystem.check_subscription(user_id, context.bot)
        if not is_subscribed:
            keyboard = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")]]
            await update.message.reply_text(
                f"⚠️ *الاشتراك إجباري*\n\nيجب الاشتراك في القناة لاستخدام البوت:\n{REQUIRED_CHANNEL}\n\nبعد الاشتراك أرسل /start مرة أخرى.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return

    allowed, message = check_bot_modes(user_id)
    if not allowed:
        await update.message.reply_text(message)
        return

    broadcast_settings.add_subscriber(user_id)
    UserSandbox.get_user_dir(user_id)

    user_points = PointsSystem.get_user_points(user_id)
    if user_points == 0:
        PointsSystem.add_points(user_id, 5, "رصيد ترحيبي")
        await update.message.reply_text("🎉 تم إضافة 5 نقاط ترحيبية! يمكنك رفع بوت واحد مجاناً.")

    if is_admin(user_id):
        await show_admin_main_menu(update.message)
        return

    await show_user_main_menu_message(update.message, user_id, context)

def main():
    log_activity("=" * 60)
    log_activity("بدء تشغيل FPI SX MANAGER - نظام موارد فردي")
    log_activity("نسخة محسّنة مع تثبيت تلقائي للمكتبات (يعتمد فقط على requirements.txt)")
    log_activity(f"مجلد المستخدمين: {USERS_DIR}")
    log_activity(f"المشرفون: {ADMIN_IDS}")
    log_activity(f"قناة الاشتراك: {REQUIRED_CHANNEL}")

    schedule.every(system_settings.health_check_interval).minutes.do(scheduled_health_check)
    schedule.every(system_settings.backup_interval_days).days.do(scheduled_backup)
    schedule.every().day.at("00:00").do(cleanup_old_logs)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    log_activity("تم تشغيل المجدول")

    try:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    except AttributeError as e:
        if '_Updater__polling_cleanup_cb' in str(e):
            log_activity('تم اكتشاف نسخة قديمة/غير متوافقة من python-telegram-bot. جاري فرض الإصدار الحديث...', 'WARNING')
            ok, msg = AutoInstaller.install_package(TELEGRAM_PACKAGE_SPEC)
            if ok:
                raise RuntimeError('تم تحديث python-telegram-bot إلى إصدار متوافق. أعد تشغيل الخدمة مرة واحدة ليعمل البوت بالمكتبة الجديدة.') from e
            raise RuntimeError(f'فشل تحديث python-telegram-bot تلقائياً: {msg}') from e
        raise

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_media))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.ANIMATION, handle_animation))

    log_activity("🚀 تم تشغيل البوت بنجاح!")
    log_activity("=" * 60)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = str(e)
        tb_text = traceback.format_exc()
        print(f"❌ خطأ فادح غير معالج: {error_message}")
        print(tb_text)
        try:
            send_error_report_sync(
                error_message,
                tb_text,
                title="خطأ فادح غير معالج في مدير البوت"
            )
        except Exception as send_e:
            print(f"❌ فشل إرسال تقرير الخطأ النهائي: {send_e}")
        sys.exit(1)