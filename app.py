import os
import sys
import gc
import re
import ast
import json
import time
import uuid
import html
import shutil
import socket
import signal
import string
import random
import secrets
import hashlib
import logging
import platform
import zipfile
import tarfile
import threading
import subprocess
import warnings
from datetime import datetime, timedelta
from functools import wraps
from collections import deque

try:
    import resource
except ImportError:
    resource = None

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_file, Response
from werkzeug.utils import secure_filename

warnings.filterwarnings('ignore')

# =============================================================================
# 1)  وضع المصادر اللا‌محدود
# =============================================================================
def set_unlimited_resources():
    if not resource:
        return False
    try:
        resource.setrlimit(resource.RLIMIT_AS,    (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        resource.setrlimit(resource.RLIMIT_DATA,  (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        resource.setrlimit(resource.RLIMIT_NOFILE,(999999, 999999))
        resource.setrlimit(resource.RLIMIT_NPROC, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        print("[🔥 UNLIMITED] Resource limits removed")
        return True
    except Exception as e:
        print(f"[⚠️ UNLIMITED] partial: {e}")
        return False

UNLIMITED_ACTIVE = set_unlimited_resources()

def unlimited_memory_monitor():
    while True:
        time.sleep(30)
        try:
            gc.collect()
            try:
                with open('/proc/sys/vm/drop_caches', 'w') as f:
                    f.write('3')
            except Exception:
                pass
        except Exception:
            pass

threading.Thread(target=unlimited_memory_monitor, daemon=True).start()

# =============================================================================
# 2)  المسارات والإعدادات (Replit-friendly)
# =============================================================================
# على Replit، استخدم المجلد الحالي بدل /tmp
DEFAULT_BASE = os.environ.get('BASE_PATH') or (
    os.path.join(os.getcwd(), 'panel_data') if os.path.exists('/home/runner') or 'REPL_ID' in os.environ else '/tmp'
)
BASE_PATH          = DEFAULT_BASE
os.makedirs(BASE_PATH, exist_ok=True)

USERS_FOLDER       = os.path.join(BASE_PATH, 'users_data')
USERS_FILE         = os.path.join(BASE_PATH, 'users.json')
PROCESSES_FILE     = os.path.join(BASE_PATH, 'processes.json')
SCHEDULES_FILE     = os.path.join(BASE_PATH, 'schedules.json')
LOGS_FILE          = os.path.join(BASE_PATH, 'activity.log')
USER_SESSIONS_FILE = os.path.join(BASE_PATH, 'user_sessions.json')
BACKUPS_FOLDER     = os.path.join(BASE_PATH, 'backups')
TEMP_FOLDER        = os.path.join(BASE_PATH, 'temp')
PACKAGES_FILE      = os.path.join(BASE_PATH, 'packages.json')
DOCKER_FILE        = os.path.join(BASE_PATH, 'docker.json')
MASTER_CONFIG_FILE = os.path.join(BASE_PATH, 'master_config.json')
BOT_CONFIG_FILE    = os.path.join(BASE_PATH, 'bot_config.json')
BOT_DATA_FILE      = os.path.join(BASE_PATH, 'bot_data.json')
PORTS_FILE         = os.path.join(BASE_PATH, 'ports.json')
ACTIVITY_FILE      = os.path.join(BASE_PATH, 'activity_feed.json')
NOTIFICATIONS_FILE = os.path.join(BASE_PATH, 'notifications.json')

PROFILE_IMAGE_URL = "https://files.manuscdn.com/user_upload_by_module/session_file/310519663299109277/qXMPQJGpGmBBKCfH.png"

# =============================================================================
# 3)  أدوات JSON
# =============================================================================
def init_json_file(file_path, default_data):
    if not os.path.exists(file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def load_json_file(file_path, default=None):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default if default is not None else {}

def save_json_file(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception:
        return False

# =============================================================================
# 4)  إعدادات لوحة المالك (Flask)
# =============================================================================
def load_master_config():
    default_config = {
        'master_username': '@xAyOuB',
        'master_password_hash': hashlib.sha256('@xAyOuB'.encode()).hexdigest(),
        'port': int(os.environ.get('PORT', 3278)),
        'maintenance_mode': False,
        'maintenance_message': 'الموقع في صيانة مؤقتة، يرجى المحاولة لاحقاً.'
    }
    if not os.path.exists(MASTER_CONFIG_FILE):
        save_json_file(MASTER_CONFIG_FILE, default_config)
        return default_config
    cfg = load_json_file(MASTER_CONFIG_FILE)
    if not cfg:
        return default_config
    for k, v in default_config.items():
        cfg.setdefault(k, v)
    return cfg

MASTER_CONFIG        = load_master_config()
MASTER_USERNAME      = MASTER_CONFIG.get('master_username', '@xAyOuB')
MASTER_PASSWORD_HASH = MASTER_CONFIG.get('master_password_hash')
SERVER_START_TIME    = time.time()

# =============================================================================
# 6)  إنشاء المجلدات والملفات
# =============================================================================
for folder in [USERS_FOLDER, TEMP_FOLDER, BACKUPS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

init_json_file(USERS_FILE, {})
init_json_file(PROCESSES_FILE, {})
init_json_file(SCHEDULES_FILE, {})
init_json_file(USER_SESSIONS_FILE, {})
init_json_file(PACKAGES_FILE, {'pip': [], 'apt': [], 'custom': []})
init_json_file(DOCKER_FILE, {'containers': [], 'images': []})
init_json_file(PORTS_FILE, {'ports': []})
init_json_file(ACTIVITY_FILE, {'events': []})
init_json_file(NOTIFICATIONS_FILE, {})

# =============================================================================
# 7)  Flask App
# =============================================================================
app = Flask(__name__)

# ---- مفتاح ثابت يُحفظ في ملف حتى لا تبطل الجلسات عند إعادة التشغيل ----
_SECRET_KEY_FILE = os.path.join(BASE_PATH, '.secret_key')
try:
    if os.path.exists(_SECRET_KEY_FILE):
        with open(_SECRET_KEY_FILE, 'r') as _f:
            _sk = _f.read().strip()
        if len(_sk) < 32:
            raise ValueError('short')
    else:
        _sk = secrets.token_hex(64)
        with open(_SECRET_KEY_FILE, 'w') as _f:
            _f.write(_sk)
except Exception:
    _sk = secrets.token_hex(64)
app.secret_key = _sk

app.permanent_session_lifetime = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = None
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# =============================================================================
# 8)  أدوات اللوحة (Activity feed محسّن لعرض على الواجهة)
# =============================================================================
def add_activity_event(username, action, details=""):
    """يضيف حدثاً للـ Activity feed (مثل صفحة Activity في Lunes Host)"""
    try:
        events = load_json_file(ACTIVITY_FILE, {'events': []}).get('events', [])
        events.insert(0, {
            'id': str(uuid.uuid4())[:8],
            'username': username,
            'action': action,
            'details': details,
            'ip': request.remote_addr if request else '-',
            'timestamp': datetime.now().isoformat(),
            'time_text': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        events = events[:300]  # احتفظ بأحدث 300 حدث
        save_json_file(ACTIVITY_FILE, {'events': events})
    except Exception:
        pass

def log_activity(username, action, details=""):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOGS_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] [{username}] {action} | {details}\n")
        add_activity_event(username, action, details)
    except Exception:
        pass

def load_users():            return load_json_file(USERS_FILE)
def save_users(u):           save_json_file(USERS_FILE, u)
def load_processes():        return load_json_file(PROCESSES_FILE)
def save_processes(p):       save_json_file(PROCESSES_FILE, p)
def load_schedules():        return load_json_file(SCHEDULES_FILE)
def save_schedules(s):       save_json_file(SCHEDULES_FILE, s)
def load_user_sessions():    return load_json_file(USER_SESSIONS_FILE)
def save_user_sessions(s):   save_json_file(USER_SESSIONS_FILE, s)
def load_packages():         return load_json_file(PACKAGES_FILE)
def save_packages(p):        save_json_file(PACKAGES_FILE, p)
def load_ports():            return load_json_file(PORTS_FILE, {'ports': []}).get('ports', [])
def save_ports(p):           save_json_file(PORTS_FILE, {'ports': p})

def load_notifications():    return load_json_file(NOTIFICATIONS_FILE, {})
def save_notifications(n):   save_json_file(NOTIFICATIONS_FILE, n)

def add_notification(username, title, message, notif_type='info'):
    """يضيف إشعاراً للمستخدم."""
    try:
        data = load_notifications()
        if username not in data:
            data[username] = []
        data[username].insert(0, {
            'id': str(uuid.uuid4())[:8],
            'title': title,
            'message': message,
            'type': notif_type,
            'read': False,
            'timestamp': datetime.now().isoformat(),
            'time_text': datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
        data[username] = data[username][:100]
        save_notifications(data)
    except Exception:
        pass

def check_expiry_notification(username):
    """يفحص إذا الحساب ينتهي قريباً ويرسل إشعار."""
    try:
        users = load_users()
        ud = users.get(username, {})
        if not isinstance(ud, dict):
            return
        expiry = ud.get('expiry')
        if not expiry:
            return
        exp_dt = datetime.fromisoformat(expiry)
        diff = exp_dt - datetime.now()
        days = diff.days
        if days < 0:
            return
        if days <= 1:
            add_notification(username, '⚠️ حسابك على وشك الانتهاء',
                f'سينتهي حسابك خلال أقل من 24 ساعة. تواصل مع الإدارة لتجديده.', 'danger')
        elif days <= 3:
            add_notification(username, '⏰ تذكير: حسابك ينتهي قريباً',
                f'سينتهي حسابك خلال {days} أيام. تواصل مع الإدارة لتجديده.', 'warning')
    except Exception:
        pass

def get_user_path(username):
    if username == MASTER_USERNAME:
        return BASE_PATH
    return os.path.join(USERS_FOLDER, username)

def ensure_user_folder(username):
    if username == MASTER_USERNAME:
        return
    p = get_user_path(username)
    os.makedirs(p, exist_ok=True)

def _is_within_base(base_path, candidate_path):
    try:
        return os.path.commonpath([os.path.realpath(base_path), os.path.realpath(candidate_path)]) == os.path.realpath(base_path)
    except Exception:
        return False

def is_path_allowed(username, requested_path):
    if not requested_path:
        return False
    if username == MASTER_USERNAME:
        return True
    user_path = os.path.realpath(get_user_path(username))
    try:
        raw_path = requested_path if os.path.isabs(requested_path) else os.path.join(user_path, requested_path)
        normalized = os.path.normpath(raw_path)
        existing_target = normalized if os.path.exists(normalized) else os.path.dirname(normalized) or user_path
        if not _is_within_base(user_path, existing_target):
            return False
        final_target = os.path.join(os.path.realpath(os.path.dirname(normalized) or user_path), os.path.basename(normalized))
        return _is_within_base(user_path, final_target)
    except Exception:
        return False

def sanitize_user_filename(filename):
    cleaned = secure_filename(os.path.basename((filename or '').replace('\\', '/')))
    return cleaned or f"file_{uuid.uuid4().hex[:8]}"

def resolve_user_path(username, requested_path=None):
    base_path = get_user_path(username)
    if username == MASTER_USERNAME:
        return os.path.realpath(requested_path or base_path)
    raw_path = requested_path or base_path
    normalized = os.path.normpath(raw_path if os.path.isabs(raw_path) else os.path.join(base_path, raw_path))
    parent_path = normalized if os.path.exists(normalized) else os.path.dirname(normalized) or base_path
    if not _is_within_base(base_path, parent_path):
        raise PermissionError('Forbidden path')
    final_path = os.path.join(os.path.realpath(os.path.dirname(normalized) or base_path), os.path.basename(normalized))
    if not _is_within_base(base_path, final_path):
        raise PermissionError('Forbidden path')
    return final_path

def can_user_login(username):
    sessions = load_user_sessions()
    users = load_users()
    if username not in users:
        return False
    ud = users[username] if isinstance(users[username], dict) else {}
    if ud.get('banned', False):
        return False
    max_s = ud.get('max_sessions', 999)
    return sessions.get(username, 0) < max_s

def get_login_error(username, password_ok):
    """Returns a specific error message for login failures."""
    if not password_ok:
        return '❌ بيانات الدخول غير صحيحة'
    users = load_users()
    if username not in users:
        return '❌ بيانات الدخول غير صحيحة'
    ud = users[username] if isinstance(users[username], dict) else {}
    if ud.get('banned', False):
        return '🚫 تم حظر حسابك من قبل المدير. تواصل مع الإدارة.'
    sessions = load_user_sessions()
    max_s = ud.get('max_sessions', 999)
    if sessions.get(username, 0) >= max_s:
        return '⚠️ لقد تجاوزت الحد الأقصى للأجهزة المسموح بها'
    return '❌ بيانات الدخول غير صحيحة'

def register_session(username):
    sessions = load_user_sessions()
    sessions[username] = sessions.get(username, 0) + 1
    save_user_sessions(sessions)

def unregister_session(username):
    sessions = load_user_sessions()
    if username in sessions:
        sessions[username] = max(0, sessions[username] - 1)
        save_user_sessions(sessions)

def get_system_stats():
    try:
        net = psutil.net_io_counters()
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_used_mb': psutil.virtual_memory().used / (1024**2),
            'memory_total_mb': psutil.virtual_memory().total / (1024**2),
            'memory_used_gb': psutil.virtual_memory().used / (1024**3),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'disk_percent': psutil.disk_usage('/').percent,
            'disk_used_mb': psutil.disk_usage('/').used / (1024**2),
            'disk_used_gb': psutil.disk_usage('/').used / (1024**3),
            'disk_total_gb': psutil.disk_usage('/').total / (1024**3),
            'uptime': time.time() - SERVER_START_TIME,
            'uptime_system': time.time() - psutil.boot_time(),
            'net_in_kb': net.bytes_recv / 1024,
            'net_out_kb': net.bytes_sent / 1024,
            'platform': platform.platform(),
            'hostname': socket.gethostname(),
        }
    except Exception:
        return {}

def format_uptime(secs):
    secs = int(secs or 0)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h}h {m}m {s}s"

# =============================================================================
# 9)  أدوات تشغيل الملفات (كاملة مع run/stop/output/input)
# =============================================================================
running_processes = {}
running_files     = {}
file_processes    = {}
port_processes    = {}  # للبورتات الإضافية

def extract_and_find_main(zip_path, extract_to):
    try:
        base_extract = os.path.realpath(extract_to)
        with zipfile.ZipFile(zip_path, 'r') as z:
            for member in z.infolist():
                target = os.path.realpath(os.path.join(base_extract, member.filename))
                if not _is_within_base(base_extract, target):
                    raise ValueError('Unsafe archive path detected')
            z.extractall(base_extract)
        main_files = ['main.py', 'app.py', 'bot.py', 'run.py', 'start.py', 'index.py']
        for root, dirs, files in os.walk(base_extract):
            for f in files:
                if f.lower() in main_files:
                    return os.path.join(root, f)
        for root, dirs, files in os.walk(base_extract):
            for f in files:
                if f.endswith(('.py', '.js', '.php', '.sh')):
                    return os.path.join(root, f)
    except Exception:
        pass
    return None

def validate_python_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().strip()
        if not content:
            return False, "File is empty"
        try:
            ast.parse(content)
            return True, "Valid Python code"
        except SyntaxError as e:
            return False, f"Python syntax error: {e}"
    except Exception:
        return True, ""

def get_run_command(filepath):
    ext = filepath.split('.')[-1].lower()
    commands = {
        'py':   f'python3 -u "{filepath}"',
        'js':   f'node "{filepath}"',
        'php':  f'php "{filepath}"',
        'sh':   f'bash "{filepath}"',
        'bash': f'bash "{filepath}"',
        'rb':   f'ruby "{filepath}"',
        'pl':   f'perl "{filepath}"',
        'lua':  f'lua "{filepath}"',
        'go':   f'go run "{filepath}"',
        'java': f'java "{filepath}"',
        'jar':  f'java -jar "{filepath}"',
        'c':    f'gcc "{filepath}" -o "{os.path.splitext(filepath)[0]}" && "{os.path.splitext(filepath)[0]}"',
        'cpp':  f'g++ "{filepath}" -o "{os.path.splitext(filepath)[0]}" && "{os.path.splitext(filepath)[0]}"',
        'rs':   f'rustc "{filepath}" && "{os.path.splitext(filepath)[0]}"',
        'dart': f'dart "{filepath}"',
        'r':    f'Rscript "{filepath}"',
        'jl':   f'julia "{filepath}"',
    }
    return commands.get(ext, f'python3 -u "{filepath}"')

def get_next_free_port(start_port=8000, end_port=9000):
    used = set()
    for info in file_processes.values():
        p = info.get('port')
        if p:
            used.add(int(p))
    for p in load_ports():
        try:
            used.add(int(p.get('port')))
        except Exception:
            pass
    for port in range(start_port, end_port + 1):
        if port in used:
            continue
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        except Exception:
            return port
        finally:
            s.close()
    return start_port

def get_assigned_port_for_new_user():
    """يعطي كل مستخدم جديد بورت ثابت فريد في نطاق 8001-8999."""
    users = load_users()
    used = set()
    for u, ud in users.items():
        if isinstance(ud, dict) and ud.get('assigned_port'):
            used.add(int(ud['assigned_port']))
    for port in range(8001, 9000):
        if port not in used:
            return port
    return 8001

def get_user_assigned_port(username):
    """يرجع البورت الثابت المخصص للمستخدم."""
    if username == MASTER_USERNAME:
        return None
    users = load_users()
    ud = users.get(username, {})
    if isinstance(ud, dict):
        return ud.get('assigned_port')
    return None

def read_process_output(proc_id, process, max_lines=2000, store=None):
    store = store if store is not None else file_processes
    output_buffer = deque(maxlen=max_lines)
    try:
        for line in iter(process.stdout.readline, ''):
            if proc_id not in store:
                break
            output_buffer.append(line.rstrip('\n'))
            store[proc_id]['output'] = list(output_buffer)
    except Exception:
        pass

def auto_install_dependencies(filepath):
    installed, failed = [], []
    try:
        cur = os.path.dirname(filepath)
        for _ in range(3):
            req_path = os.path.join(cur, 'requirements.txt')
            if os.path.exists(req_path):
                try:
                    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req_path],
                                       capture_output=True, text=True, timeout=300)
                    (installed if r.returncode == 0 else failed).append('requirements.txt')
                except Exception:
                    failed.append('requirements.txt')
                break
            cur = os.path.dirname(cur)

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        packages = []
        if filepath.endswith('.py'):
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for a in node.names:
                            packages.append(a.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            packages.append(node.module.split('.')[0])
            except Exception:
                packages = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
        elif filepath.endswith('.js'):
            packages = re.findall(r'require\([\'"]([^\'"]+)[\'"]\)', content)
            packages += re.findall(r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', content)

        package_map = {
            'telegram': 'python-telegram-bot', 'telebot': 'pyTelegramBotAPI',
            'discord': 'discord.py', 'PIL': 'Pillow', 'cv2': 'opencv-python',
            'sklearn': 'scikit-learn', 'flask_sqlalchemy': 'Flask-SQLAlchemy',
            'flask_cors': 'Flask-Cors', 'bs4': 'beautifulsoup4', 'yaml': 'PyYAML',
            'dotenv': 'python-dotenv', 'mysql': 'mysql-connector-python',
            'psycopg2': 'psycopg2-binary', 'youtube_dl': 'youtube-dl',
            'yt_dlp': 'yt-dlp',
        }
        std_libs = {'os','sys','time','json','re','math','random','datetime','threading',
                    'subprocess','collections','io','typing','abc','flask','requests',
                    'psutil','hashlib','base64','uuid','socket','platform','signal',
                    'warnings','gc','resource','shutil','zipfile','tarfile','secrets',
                    'functools','itertools','string','textwrap','pathlib','glob',
                    'tempfile','contextlib','html','logging','ast'}

        for pkg in set(packages):
            if not pkg or pkg.startswith('.') or pkg in std_libs:
                continue
            actual = package_map.get(pkg, pkg)
            try:
                __import__(pkg)
            except Exception:
                try:
                    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--user', actual],
                                       capture_output=True, text=True, timeout=180)
                    (installed if r.returncode == 0 else failed).append(actual)
                except Exception:
                    failed.append(actual)
        return {'installed': installed, 'failed': failed}
    except Exception as e:
        return {'installed': installed, 'failed': failed + [str(e)]}

# =============================================================================
# 10)  ديكورات الـ Flask
# =============================================================================
def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Session expired'}), 401
            return redirect('/login')
        return f(*a, **kw)
    return w

def master_required(f):
    @wraps(f)
    def w(*a, **kw):
        if session.get('username') != MASTER_USERNAME:
            return jsonify({'success': False, 'error': 'Master only'}), 403
        return f(*a, **kw)
    return w

# =============================================================================
# 11)  قالب تسجيل الدخول (شكل Pterodactyl/Lunes Host)
# =============================================================================
MAINTENANCE_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>صيانة — XcT x TeaM LLC</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter','Segoe UI',Tahoma,sans-serif}
html,body{height:100%;background:#1f2933;color:#d6dde3;display:flex;align-items:center;justify-content:center;min-height:100vh}
.maint-box{
  width:min(480px,92vw);background:#2b3a43;border:1px solid #3a4a55;
  border-radius:10px;padding:40px 32px;text-align:center;
  box-shadow:0 10px 40px rgba(0,0,0,.5);
}
.maint-icon{font-size:54px;margin-bottom:18px}
.maint-box h1{font-size:22px;font-weight:700;color:#fff;margin-bottom:10px}
.maint-box .accent{color:#29c7d3}
.maint-msg{
  background:#1f2933;border:1px solid #3a4a55;border-radius:8px;
  padding:18px;margin:20px 0;font-size:15px;color:#c9d6de;line-height:1.7;
}
.back-btn{
  display:inline-block;margin-top:8px;padding:10px 28px;
  background:#2f6fed;color:#fff;border-radius:5px;font-size:13px;
  text-decoration:none;font-weight:600;transition:.2s;
}
.back-btn:hover{background:#1d5cd8}
.foot{margin-top:20px;font-size:11px;color:#5a6c78}
</style>
</head>
<body>
<div class="maint-box">
  <div class="maint-icon">🛠️</div>
  <h1>XcT x TeaM<span class="accent">LLC</span></h1>
  <div class="maint-msg">{{ message }}</div>
  <a href="/login" class="back-btn">← الرجوع لتسجيل الدخول</a>
  <div class="foot"><a href="/register" style="color:#8bb7ff;text-decoration:none">إنشاء حساب / طلب حساب</a><br>Pterodactyl® © 2015 - 2026</div>
</div>
</body>
</html>
'''

LOGIN_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XcT x TeaM LLC — Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter','Segoe UI',Tahoma,sans-serif}
html,body{height:100%;overflow:hidden}
body{
  color:#d6dde3;display:flex;align-items:center;justify-content:center;min-height:100vh;
  position:relative;
}
/* ---- video background ---- */
.bg-video{
  position:fixed;top:0;left:0;width:100%;height:100%;
  object-fit:cover;z-index:0;
  filter:brightness(0.38) saturate(1.1);
}
.bg-overlay{
  position:fixed;top:0;left:0;width:100%;height:100%;
  background:linear-gradient(135deg,rgba(15,25,35,.7) 0%,rgba(30,50,65,.5) 100%);
  z-index:1;
}
/* ---- card ---- */
.card{
  position:relative;z-index:2;
  width:min(420px,92vw);
  background:rgba(30,42,52,.82);
  border:1px solid rgba(41,199,211,.25);
  border-radius:10px;
  padding:34px 30px;
  box-shadow:0 20px 60px rgba(0,0,0,.6);
  backdrop-filter:blur(12px);
}
.brand{text-align:center;margin-bottom:26px}
.brand h1{font-size:21px;font-weight:700;color:#fff;margin-bottom:6px;letter-spacing:.5px}
.brand .accent{color:#29c7d3}
.brand p{color:#7a8c98;font-size:12px}
.field{margin-bottom:15px}
.field label{display:block;color:#9aa9b3;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.field input{
  width:100%;padding:11px 14px;
  background:rgba(15,25,35,.7);
  border:1px solid #3a4a55;
  border-radius:5px;color:#fff;font-size:14px;outline:none;transition:.2s;
}
.field input:focus{border-color:#29c7d3;box-shadow:0 0 0 2px rgba(41,199,211,.18)}
.btn{
  width:100%;padding:12px;border:0;border-radius:5px;cursor:pointer;
  background:#2f6fed;color:#fff;font-weight:700;font-size:14px;
  transition:.2s;margin-top:6px;letter-spacing:.3px;
}
.btn:hover{background:#1d5cd8;transform:translateY(-1px)}
.error{
  margin-top:14px;padding:10px;border-radius:5px;
  background:rgba(229,57,53,.15);
  border:1px solid rgba(229,57,53,.4);
  color:#ff8a8a;text-align:center;font-size:13px;
}
.foot{text-align:center;margin-top:20px;font-size:11px;color:#5a6c78}
</style>
</head>
<body>
<video class="bg-video" src="https://files.manuscdn.com/user_upload_by_module/session_file/310519663195216670/JYByYKWiHkXkPYxv.mp4"
  autoplay muted loop playsinline></video>
<div class="bg-overlay"></div>
<div class="card">
  <div class="brand">
    <h1>XcT x TeaM<span class="accent">LLC</span></h1>
    <p>Server Management Panel</p>
  </div>
  <form method="post" action="/login">
    <div class="field">
      <label>Username</label>
      <input type="text" name="username" placeholder="Username" required autofocus autocomplete="username">
    </div>
    <div class="field">
      <label>Password</label>
      <input type="password" name="password" placeholder="Password" required autocomplete="current-password">
    </div>
    <button class="btn" type="submit">Login</button>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
  </form>
  <div class="foot"><a href="/register" style="color:#8bb7ff;text-decoration:none">إنشاء حساب / طلب حساب</a><br>Pterodactyl® © 2015 - 2026</div>
</div>
</body>
</html>
'''

REGISTER_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XcT x TeaM LLC — Register</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter','Segoe UI',Tahoma,sans-serif}
body{background:#111a21;color:#d6dde3;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.card{width:min(520px,94vw);background:#1f2933;border:1px solid rgba(41,199,211,.25);border-radius:12px;padding:28px;box-shadow:0 20px 60px rgba(0,0,0,.45)}
h1{font-size:24px;margin-bottom:12px;color:#fff}.accent{color:#29c7d3}.msg{line-height:1.9;color:#b8c5cf;font-size:15px}.actions{margin-top:20px;display:flex;gap:12px;flex-wrap:wrap}.btn{display:inline-block;padding:11px 16px;border-radius:8px;text-decoration:none;font-weight:700}.btn-primary{background:#2f6fed;color:#fff}.btn-secondary{background:#2b3a43;color:#d6dde3}
</style>
</head>
<body>
  <div class="card">
    <h1>XcT x TeaM <span class="accent">LLC</span></h1>
    <div class="msg">
      إنشاء الحسابات يتم من لوحة المالك فقط حتى لا يتم فتح تسجيل عشوائي داخل السيرفر.<br>
      إذا كنت مالك الموقع فقم بالدخول بحساب المالك ثم أضف المستخدم من تبويب <b>Users</b> داخل اللوحة.<br>
      وإذا كنت مستخدماً عادياً فاطلب من المالك إنشاء حساب لك.
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="/login">العودة لتسجيل الدخول</a>
    </div>
  </div>
</body>
</html>
'''

# =============================================================================
# 12)  القالب الرئيسي (شكل Pterodactyl / Lunes Host)
# =============================================================================
def get_html_template(is_master, current_username=''):
    master_tabs = ''
    if is_master:
        master_tabs = '''
        <div class="tab-item" data-tab="users">Users</div>
        <div class="tab-item" data-tab="backups">Backups</div>
        <div class="tab-item" data-tab="network">Network</div>
        <div class="tab-item" data-tab="startup">Startup</div>
        <div class="tab-item" data-tab="settings">Settings</div>
        <div class="tab-item" data-tab="activity">Activity</div>
        '''
    else:
        master_tabs = '''
        <div class="tab-item" data-tab="settings">Settings</div>
        <div class="tab-item" data-tab="activity">Activity</div>
        '''

    return r'''
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XcT x TeaM LLC — Server Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter','Segoe UI',Tahoma,sans-serif}
html,body{background:#1f2933;color:#d6dde3;min-height:100vh}

/* ============== HEADER ============== */
.topbar{
  background:#1a242c;
  border-bottom:1px solid #2a3640;
  padding:14px 20px;
  display:flex;align-items:center;justify-content:space-between;
}
.topbar .brand{font-size:18px;font-weight:600;color:#fff}
.topbar .brand .lc{color:#29c7d3}
.topbar .icons{display:flex;gap:18px;align-items:center}
.topbar .icons .ic{
  color:#9aa9b3;font-size:18px;cursor:pointer;
  background:none;border:0;
}
.topbar .icons .ic:hover{color:#fff}
.topbar .avatar{
  width:28px;height:28px;border-radius:50%;
  background:linear-gradient(135deg,#f6b73c,#65c466);
  display:inline-block;
}
.topbar .clock-btn{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  background:#2b3a43;border:1px solid #3a4a55;border-radius:6px;
  padding:4px 10px;cursor:default;min-width:90px;
}
.topbar .clock-btn .clock-time{
  font-size:13px;font-weight:700;color:#29c7d3;font-family:monospace;letter-spacing:1px;
}
.topbar .clock-btn .clock-date{
  font-size:10px;color:#9aa9b3;margin-top:1px;
}

/* ============== TABS ============== */
.tabs{
  background:#1f2933;
  border-bottom:1px solid #2a3640;
  display:flex;
  overflow-x:auto;
  padding:0 10px;
  scrollbar-width:thin;
}
.tabs::-webkit-scrollbar{height:3px}
.tabs::-webkit-scrollbar-thumb{background:#3a4a55;border-radius:3px}
.tab-item{
  padding:14px 18px;
  color:#9aa9b3;
  cursor:pointer;
  font-size:14px;
  white-space:nowrap;
  border-bottom:2px solid transparent;
  transition:.2s;
  user-select:none;
}
.tab-item:hover{color:#fff}
.tab-item.active{color:#29c7d3;border-bottom-color:#29c7d3}

/* ============== CONTENT ============== */
.container{
  max-width:1100px;
  margin:0 auto;
  padding:18px;
}
.tab-content{display:none;animation:fadein .25s}
.tab-content.active{display:block}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}

/* ============== CONSOLE ============== */
.power-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px}
.btn-power{
  padding:12px;border:0;border-radius:4px;font-weight:600;font-size:14px;cursor:pointer;
  color:#fff;transition:.2s;
}
.btn-start{background:#2f6fed}
.btn-start:hover{background:#1d5cd8}
.btn-restart{background:#5a6c78}
.btn-restart:hover{background:#4a5b66}
.btn-stop{background:#e53935}
.btn-stop:hover{background:#c62828}

.console-box{
  background:#0d1419;
  border:1px solid #2a3640;
  border-radius:4px;
  padding:14px;
  font-family:'Consolas','Monaco',monospace;
  font-size:12px;
  color:#c8d4dc;
  height:340px;
  overflow-y:auto;
  white-space:pre-wrap;
  word-break:break-all;
  margin-bottom:10px;
}
.console-box::-webkit-scrollbar{width:6px}
.console-box::-webkit-scrollbar-thumb{background:#3a4a55;border-radius:3px}

.cmd-input{
  display:flex;align-items:center;
  background:#1a242c;
  border:1px solid #2a3640;
  border-radius:4px;
  padding:0 12px;margin-bottom:14px;
}
.cmd-input .prompt{color:#29c7d3;margin-right:8px;font-weight:700}
.cmd-input input{
  flex:1;background:none;border:0;outline:0;color:#d6dde3;
  padding:11px 0;font-family:monospace;font-size:13px;
}

/* ============== STATS GRID ============== */
.stats-grid{
  display:grid;grid-template-columns:1fr 1fr;gap:8px;
}
.stat-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-left:3px solid #29c7d3;
  border-radius:4px;
  padding:10px 12px;
}
.stat-card.alt{border-left-color:#f6b73c}
.stat-card.alt2{border-left-color:#65c466}
.stat-card.alt3{border-left-color:#e53935}
.stat-card .lbl{font-size:11px;color:#9aa9b3;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}
.stat-card .val{font-size:14px;color:#fff;font-weight:600}
.stat-card .val .max{color:#7a8c98;font-weight:400;font-size:12px}

/* ============== CONSOLE STATUS BAR ============== */
.console-status{
  display:flex;align-items:center;gap:10px;
  background:#1a242c;border:1px solid #2a3640;border-radius:4px;
  padding:9px 14px;margin-bottom:10px;flex-wrap:wrap;
}
.cs-badge{
  padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.5px;
  flex-shrink:0;
}
.cs-badge.running{background:rgba(101,196,102,.15);color:#65c466;border:1px solid rgba(101,196,102,.5)}
.cs-badge.stopped{background:rgba(90,108,120,.15);color:#9aa9b3;border:1px solid #5a6c78}
.cs-file{color:#fff;font-size:13px;font-family:monospace;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cs-main-lbl{color:#f6b73c;font-size:11px;white-space:nowrap;flex-shrink:0}

/* ============== FILE ACTION BUTTONS ============== */
.file-row{cursor:default !important}
.file-name-click{cursor:pointer;flex:1;color:#d6dde3;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-name-click:hover{color:#fff}
.file-actions{display:flex;gap:3px;flex-shrink:0;align-items:center;flex-wrap:wrap}
.btn-fac{padding:3px 8px;border:0;border-radius:3px;cursor:pointer;font-size:11px;font-weight:700;color:#fff;transition:.15s;white-space:nowrap}
.btn-fac.f-edit{background:#2f6fed}.btn-fac.f-edit:hover{background:#1d5cd8}
.btn-fac.f-run{background:#65c466;color:#1f2933}.btn-fac.f-run:hover{background:#4fb350}
.btn-fac.f-stop{background:#e53935}.btn-fac.f-stop:hover{background:#c62828}
.btn-fac.f-rename{background:#5a6c78}.btn-fac.f-rename:hover{background:#4a5b66}
.btn-fac.f-del{background:#e53935}.btn-fac.f-del:hover{background:#c62828}
.btn-fac.f-main{background:#f6b73c;color:#1a242c}.btn-fac.f-main:hover{background:#e5a828}
.badge-run{background:rgba(101,196,102,.15);color:#65c466;border:1px solid rgba(101,196,102,.4);border-radius:10px;padding:1px 7px;font-size:10px;font-weight:700;flex-shrink:0}
.badge-main-f{background:rgba(246,183,60,.12);color:#f6b73c;border:1px solid rgba(246,183,60,.4);border-radius:10px;padding:1px 7px;font-size:10px;font-weight:700;flex-shrink:0}

/* ============== FILES ============== */
.action-buttons{display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.btn-bar{
  width:100%;padding:13px;border:0;border-radius:4px;cursor:pointer;
  font-size:14px;font-weight:600;color:#fff;transition:.2s;
}
.btn-create-dir{background:#5a6c78}
.btn-create-dir:hover{background:#4a5b66}
.btn-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.btn-upload,.btn-newfile{background:#2f6fed}
.btn-upload:hover,.btn-newfile:hover{background:#1d5cd8}

.breadcrumb{
  padding:8px 4px;color:#9aa9b3;font-size:13px;margin-bottom:8px;
  display:flex;align-items:center;gap:6px;flex-wrap:wrap;
}
.breadcrumb .crumb{color:#29c7d3;cursor:pointer}
.breadcrumb .crumb:hover{text-decoration:underline}
.breadcrumb .sep{color:#5a6c78}

.file-list{background:transparent}
.file-row{
  display:flex;align-items:center;gap:10px;
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;
  padding:10px 12px;
  margin-bottom:4px;
  cursor:pointer;
  transition:.15s;
}
.file-row:hover{background:#324250}
.file-row .chk{width:14px;height:14px;border:1px solid #5a6c78;border-radius:2px;flex-shrink:0}
.file-row .ico{font-size:18px;flex-shrink:0;color:#9aa9b3}
.file-row .name{flex:1;color:#d6dde3;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-row .menu{
  color:#9aa9b3;cursor:pointer;padding:4px 8px;font-size:18px;
  border-radius:3px;
}
.file-row .menu:hover{background:#3a4a55;color:#fff}

/* ============== SECTION CARDS ============== */
.section-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;
  margin-bottom:14px;
  overflow:hidden;
}
.section-head{
  padding:12px 16px;
  border-bottom:1px solid #3a4a55;
  font-size:12px;color:#9aa9b3;text-transform:uppercase;letter-spacing:1px;font-weight:600;
}
.section-body{padding:16px}
.field-block{margin-bottom:14px}
.field-block:last-child{margin-bottom:0}
.field-block label{display:block;color:#9aa9b3;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.field-block input,.field-block textarea,.field-block select{
  width:100%;padding:10px 12px;
  background:#1f2933;
  border:1px solid #3a4a55;
  border-radius:4px;color:#fff;font-size:13px;outline:none;
  font-family:inherit;
}
.field-block input:focus,.field-block textarea:focus{border-color:#29c7d3}
.field-block textarea{min-height:80px;resize:vertical}

.btn-action{
  padding:10px 22px;border:0;border-radius:4px;cursor:pointer;
  background:#2f6fed;color:#fff;font-weight:600;font-size:13px;
}
.btn-action:hover{background:#1d5cd8}
.btn-action.danger{background:#e53935}
.btn-action.danger:hover{background:#c62828}
.btn-action.gray{background:#5a6c78}
.btn-action.gray:hover{background:#4a5b66}

.row-end{display:flex;justify-content:flex-end;margin-top:8px}

/* ============== ACTIVITY FEED ============== */
.activity-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;
  padding:12px 16px;
  margin-bottom:6px;
}
.activity-card .a-head{
  color:#fff;font-size:14px;margin-bottom:4px;
}
.activity-card .a-head .user{color:#29c7d3;font-weight:600}
.activity-card .a-head .action{color:#fff;font-weight:500}
.activity-card .a-desc{color:#9aa9b3;font-size:13px;margin-bottom:4px}
.activity-card .a-desc code{background:#1a242c;padding:1px 6px;border-radius:3px;color:#f6b73c}
.activity-card .a-meta{color:#7a8c98;font-size:12px}

/* ============== NETWORK / PORTS ============== */
.port-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;padding:14px;margin-bottom:8px;
}
.port-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.port-host{
  background:#1a242c;border-radius:3px;padding:4px 10px;color:#fff;font-size:13px;
  font-family:monospace;
}
.port-badge{
  background:#1a242c;border-radius:3px;padding:4px 10px;color:#fff;font-size:13px;font-weight:600;
}
.port-note{color:#7a8c98;font-size:12px;margin-top:4px}

/* ============== WELCOME OVERLAY ============== */
.welcome-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.7);
  display:flex;align-items:center;justify-content:center;z-index:3000;
  animation:fadein .35s;
}
.welcome-box{
  background:linear-gradient(135deg,#1a2c3a 0%,#2b3a43 100%);
  border:1px solid rgba(41,199,211,.35);
  border-radius:14px;padding:36px 32px;text-align:center;
  width:min(420px,92vw);
  box-shadow:0 24px 60px rgba(0,0,0,.6);position:relative;
}
.welcome-box .wb-icon{font-size:52px;margin-bottom:12px}
.welcome-box h2{color:#fff;font-size:22px;font-weight:700;margin-bottom:6px}
.welcome-box .wb-badge{
  display:inline-block;padding:3px 14px;border-radius:20px;font-size:12px;font-weight:700;
  margin-bottom:18px;
}
.wb-badge.vip{background:rgba(245,197,24,.15);color:#f5c518;border:1px solid rgba(245,197,24,.4)}
.wb-badge.normal{background:rgba(41,199,211,.1);color:#29c7d3;border:1px solid rgba(41,199,211,.3)}
.wb-badge.master{background:rgba(229,57,53,.1);color:#ff8a8a;border:1px solid rgba(229,57,53,.4)}
.welcome-box .wb-info{
  background:#1f2933;border-radius:8px;padding:14px;margin-bottom:18px;
  text-align:right;font-size:13px;line-height:2;color:#c9d6de;
}
.welcome-box .wb-info span{color:#29c7d3;font-weight:600}
.welcome-box .wb-close{
  background:#2f6fed;color:#fff;border:0;border-radius:6px;
  padding:11px 32px;font-size:14px;font-weight:700;cursor:pointer;width:100%;
}
.welcome-box .wb-close:hover{background:#1d5cd8}

/* ============== PROFILE MODAL ============== */
.prof-field{display:flex;justify-content:space-between;align-items:center;
  padding:10px 0;border-bottom:1px solid #2a3640}
.prof-field:last-child{border-bottom:0}
.prof-field .pf-lbl{color:#7a8c98;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.prof-field .pf-val{color:#fff;font-size:14px;font-weight:500}

/* ============== USER EDIT MODAL ============== */
.edit-user-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}

/* ============== USER LIST ============== */
.user-row{
  display:flex;justify-content:space-between;align-items:center;
  background:#2b3a43;border:1px solid #3a4a55;border-radius:4px;
  padding:10px 14px;margin-bottom:6px;
}
.user-row .uname{color:#fff;font-weight:500}
.user-row .meta{color:#7a8c98;font-size:12px}

/* ============== MODAL ============== */
.modal{
  position:fixed;inset:0;background:rgba(0,0,0,.7);
  display:none;align-items:center;justify-content:center;z-index:1000;padding:14px;
}
.modal.show{display:flex}
.modal-box{
  background:#2b3a43;border:1px solid #3a4a55;border-radius:6px;
  width:min(560px,100%);max-height:90vh;overflow-y:auto;
}
.modal-head{padding:14px 18px;border-bottom:1px solid #3a4a55;display:flex;justify-content:space-between;align-items:center}
.modal-head h3{color:#fff;font-size:16px;font-weight:600}
.modal-head .close{background:none;border:0;color:#9aa9b3;font-size:24px;cursor:pointer;line-height:1}
.modal-body{padding:18px}
.modal-foot{padding:12px 18px;border-top:1px solid #3a4a55;display:flex;justify-content:flex-end;gap:8px}

.editor-textarea{
  width:100%;min-height:55vh;
  background:#0d1419;border:1px solid #3a4a55;border-radius:4px;
  color:#c8d4dc;font-family:monospace;font-size:13px;padding:12px;outline:none;
  resize:vertical;
}

.toast{
  position:fixed;bottom:16px;right:16px;
  background:#2b3a43;border:1px solid #29c7d3;
  color:#fff;padding:10px 16px;border-radius:4px;font-size:13px;
  box-shadow:0 6px 20px rgba(0,0,0,.5);z-index:2000;
  animation:tin .3s;
}
.toast.error{border-color:#e53935}
@keyframes tin{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}

.foot-pterod{text-align:center;color:#5a6c78;font-size:11px;padding:18px 0}

/* ============== NOTIFICATIONS ============== */
.notif-btn{position:relative}
.notif-badge{
  position:absolute;top:-6px;right:-6px;
  background:#e53935;color:#fff;
  border-radius:50%;width:18px;height:18px;
  font-size:10px;font-weight:700;
  display:flex;align-items:center;justify-content:center;
  pointer-events:none;
}
.notif-panel{
  position:fixed;top:60px;right:16px;width:340px;max-height:480px;
  background:#1a242c;border:1px solid #2a3640;border-radius:10px;
  box-shadow:0 8px 32px rgba(0,0,0,.6);z-index:3000;
  display:flex;flex-direction:column;overflow:hidden;
}
.notif-head{
  padding:14px 16px;border-bottom:1px solid #2a3640;
  display:flex;justify-content:space-between;align-items:center;
}
.notif-head h4{color:#fff;font-size:14px;font-weight:600}
.notif-head button{background:none;border:0;color:#9aa9b3;cursor:pointer;font-size:12px}
.notif-head button:hover{color:#fff}
.notif-body{overflow-y:auto;flex:1}
.notif-item{
  padding:12px 16px;border-bottom:1px solid #1f2933;
  cursor:pointer;transition:background .15s;
}
.notif-item:hover{background:#212e38}
.notif-item.unread{border-left:3px solid #29c7d3}
.notif-item.type-warning{border-left-color:#f5c518}
.notif-item.type-danger{border-left-color:#e53935}
.notif-item .n-title{font-size:13px;font-weight:600;color:#d6dde3;margin-bottom:3px}
.notif-item .n-msg{font-size:12px;color:#9aa9b3;line-height:1.4}
.notif-item .n-time{font-size:10px;color:#5a6c78;margin-top:4px}
.notif-empty{padding:32px 16px;text-align:center;color:#5a6c78;font-size:13px}

/* ============== RESPONSIVE ============== */
@media (max-width:520px){
  .stats-grid{grid-template-columns:1fr 1fr}
  .topbar .brand{font-size:15px}
  .container{padding:12px}
}
</style>
</head>
<body>

<!-- ===== TOPBAR ===== -->
<div class="topbar">
  <div class="brand">XcT x HosT<span class="lc">LLC</span></div>
  <div class="icons">
    <div class="clock-btn" id="topbar-clock">
      <span class="clock-time" id="clock-time">--:--:--</span>
      <span class="clock-date" id="clock-date">----/--/--</span>
    </div>
    <button class="ic" onclick="loadSearch()" title="Search">🔍</button>
    <button class="ic notif-btn" onclick="toggleNotifPanel()" title="الإشعارات" id="notif-btn">
      🔔<span class="notif-badge" id="notif-badge" style="display:none">0</span>
    </button>
    <button class="ic" onclick="showProfile()" title="Profile" style="font-size:20px">👤</button>
    <span class="avatar" id="topbar-avatar" onclick="showProfile()" title="''' + html.escape(MASTER_USERNAME if is_master else current_username) + r'''" style="cursor:pointer">''' + (MASTER_USERNAME if is_master else current_username)[:2].upper() + r'''</span>
    <button class="ic" onclick="location.href='/logout'" title="Logout">↪</button>
  </div>
</div>

<!-- ===== TABS ===== -->
<div class="tabs" id="tabs">
  <div class="tab-item active" data-tab="console">Console</div>
  <div class="tab-item" data-tab="files">Files</div>
  <div class="tab-item" data-tab="databases">Databases</div>
  <div class="tab-item" data-tab="schedules">Schedules</div>
  ''' + master_tabs + r'''
</div>

<div class="container">

<!-- ===== CONSOLE TAB ===== -->
<div class="tab-content active" id="tab-console">

  <!-- Status bar -->
  <div class="console-status">
    <span class="cs-badge stopped" id="cs-badge">⏹ STOPPED</span>
    <span class="cs-file" id="cs-file">لا يوجد ملف يعمل حالياً</span>
    <span class="cs-main-lbl" id="cs-main-lbl">⭐ الرئيسي: لا يوجد</span>
  </div>

  <div class="power-row">
    <button class="btn-power btn-start" onclick="powerAction('start')">▶ Start</button>
    <button class="btn-power btn-restart" onclick="powerAction('restart')">↺ Restart</button>
    <button class="btn-power btn-stop" onclick="powerAction('stop')">■ Stop</button>
  </div>

  <div class="console-box" id="console-output">مرحباً بك في XcT x HosT Panel
قم برفع ملف من تبويب Files ثم اضغط ▶ Run أو حدد ملف رئيسي واضغط Start
</div>

  <div class="cmd-input">
    <span class="prompt">»</span>
    <input id="cmd-field" placeholder="اكتب أمراً..." onkeydown="if(event.key==='Enter') runCmd()">
  </div>

  <div class="stats-grid" id="stats-grid">
    <div class="stat-card"><div class="lbl">Address</div><div class="val" id="s-addr">—</div></div>
    <div class="stat-card alt"><div class="lbl">Uptime</div><div class="val" id="s-uptime">—</div></div>
    <div class="stat-card"><div class="lbl">CPU Load</div><div class="val" id="s-cpu">—</div></div>
    <div class="stat-card"><div class="lbl">Memory</div><div class="val" id="s-mem">—</div></div>
    <div class="stat-card"><div class="lbl">Disk</div><div class="val" id="s-disk">—</div></div>
    <div class="stat-card alt2"><div class="lbl">Network (Inbound)</div><div class="val" id="s-in">—</div></div>
    <div class="stat-card alt3"><div class="lbl">Network (Outbound)</div><div class="val" id="s-out">—</div></div>
    <div class="stat-card"><div class="lbl">Hostname</div><div class="val" id="s-host">—</div></div>
  </div>
</div>

<!-- ===== FILES TAB ===== -->
<div class="tab-content" id="tab-files">
  <div class="action-buttons">
    <button class="btn-bar btn-create-dir" onclick="createDir()">Create Directory</button>
    <div class="btn-row">
      <button class="btn-bar btn-upload" onclick="document.getElementById('file-up').click()">Upload</button>
      <button class="btn-bar btn-newfile" onclick="newFile()">New File</button>
    </div>
    <input type="file" id="file-up" style="display:none" onchange="uploadFile(this)">
  </div>

  <div class="breadcrumb" id="breadcrumb">/ home / container /</div>

  <div class="file-list" id="file-list"></div>
</div>

<!-- ===== DATABASES TAB ===== -->
<div class="tab-content" id="tab-databases">
  <div class="section-card">
    <div class="section-head">DATABASES</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:13px;margin-bottom:12px">Manage SQLite / JSON databases stored in your panel folder.</p>
      <div class="field-block">
        <label>Database Name</label>
        <input id="db-name" placeholder="my_database">
      </div>
      <div class="row-end"><button class="btn-action" onclick="createDB()">Create Database</button></div>
    </div>
  </div>
  <div id="db-list"></div>
</div>

<!-- ===== SCHEDULES TAB ===== -->
<div class="tab-content" id="tab-schedules">
  <div class="section-card">
    <div class="section-head">CREATE SCHEDULE</div>
    <div class="section-body">
      <div class="field-block"><label>Name</label><input id="sch-name" placeholder="Daily backup"></div>
      <div class="field-block"><label>Command</label><input id="sch-cmd" placeholder="echo hello"></div>
      <div class="field-block"><label>Cron</label><input id="sch-cron" placeholder="* * * * *" value="* * * * *"></div>
      <div class="row-end"><button class="btn-action" onclick="addSchedule()">Add Schedule</button></div>
    </div>
  </div>
  <div id="sch-list"></div>
</div>

''' + (r'''
<!-- ===== USERS TAB (master only) ===== -->
<div class="tab-content" id="tab-users">
  <div class="section-card">
    <div class="section-head">➕ إضافة مستخدم جديد</div>
    <div class="section-body">
      <div class="field-block"><label>اسم المستخدم</label><input id="u-name" placeholder="username"></div>
      <div class="field-block"><label>كلمة المرور</label><input id="u-pass" type="password" placeholder="password"></div>
      <div class="field-block"><label>أقصى عدد أجهزة</label><input id="u-max" type="number" value="3"></div>
      <div class="field-block"><label>تاريخ الانتهاء</label><input id="u-expiry" type="datetime-local"></div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        <input type="checkbox" id="u-vip" style="width:16px;height:16px">
        <label for="u-vip" style="color:#f5c518;font-weight:600;font-size:13px">⭐ عضو VIP</label>
      </div>
      <div class="row-end"><button class="btn-action" onclick="addUser()">➕ إضافة مستخدم</button></div>
    </div>
  </div>
  <div id="user-list"></div>

  <div class="section-card" style="margin-top:16px">
    <div class="section-head">📢 إرسال إشعار للمستخدمين</div>
    <div class="section-body">
      <div class="field-block">
        <label>المستخدم</label>
        <select id="notify-target" style="width:100%;padding:10px;background:#1a242c;border:1px solid #3a4a55;color:#d6dde3;border-radius:4px;font-size:13px">
          <option value="__all__">📢 جميع المستخدمين</option>
        </select>
      </div>
      <div class="field-block">
        <label>عنوان الإشعار</label>
        <input id="notify-title" placeholder="مثال: تنبيه مهم">
      </div>
      <div class="field-block">
        <label>نص الرسالة</label>
        <textarea id="notify-msg" rows="3" style="width:100%;padding:10px;background:#1a242c;border:1px solid #3a4a55;color:#d6dde3;border-radius:4px;font-size:13px;resize:vertical" placeholder="اكتب رسالتك هنا..."></textarea>
      </div>
      <div class="field-block">
        <label>نوع الإشعار</label>
        <select id="notify-type" style="width:100%;padding:10px;background:#1a242c;border:1px solid #3a4a55;color:#d6dde3;border-radius:4px;font-size:13px">
          <option value="info">ℹ️ معلومة</option>
          <option value="warning">⚠️ تحذير</option>
          <option value="danger">🔴 خطر</option>
        </select>
      </div>
      <div class="row-end"><button class="btn-action" onclick="sendNotification()">📤 إرسال الإشعار</button></div>
    </div>
  </div>
</div>

<!-- ===== BACKUPS TAB ===== -->
<div class="tab-content" id="tab-backups">
  <div class="section-card">
    <div class="section-head">BACKUPS</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:13px;margin-bottom:12px">Create compressed snapshots (.tar.gz) of your panel data.</p>
      <div class="row-end"><button class="btn-action" onclick="createBackup()">Create Backup</button></div>
    </div>
  </div>
  <div id="backup-list"></div>
</div>

<!-- ===== NETWORK TAB ===== -->
<div class="tab-content" id="tab-network">
  <div class="section-card">
    <div class="section-head">PRIMARY ALLOCATION</div>
    <div class="section-body">
      <div class="port-card">
        <div class="port-head">
          <div class="port-host" id="primary-host">node70.lunes.ho...</div>
          <div class="port-badge" id="primary-port">3278</div>
        </div>
        <div class="field-block">
          <label>Notes</label>
          <textarea id="primary-port-note" readonly placeholder="Notes"></textarea>
        </div>
        <div class="row-end"><button class="btn-action" id="primary-port-btn">Primary</button></div>
      </div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">ADDITIONAL PORTS (Multi-port for Flask apps)</div>
    <div class="section-body">
      <div class="field-block"><label>Port Number</label><input id="new-port" type="number" placeholder="5000"></div>
      <div class="field-block"><label>Description</label><input id="new-port-note" placeholder="My Flask App"></div>
      <div class="row-end"><button class="btn-action" onclick="addPort()">Add Port</button></div>
    </div>
  </div>
  <div id="port-list"></div>

  <div class="section-card">
    <div class="section-head">PORT SCANNER</div>
    <div class="section-body">
      <div class="field-block"><label>Host</label><input id="scan-host" value="127.0.0.1"></div>
      <div class="field-block"><label>Ports (comma separated)</label><input id="scan-ports" value="22,80,443,3177,5000,8080"></div>
      <div class="row-end"><button class="btn-action" onclick="scanPorts()">Scan</button></div>
      <div id="scan-out" style="margin-top:10px;font-family:monospace;font-size:12px;color:#9aa9b3"></div>
    </div>
  </div>
</div>

<!-- ===== STARTUP TAB ===== -->
<div class="tab-content" id="tab-startup">
  <div class="section-card">
    <div class="section-head">STARTUP COMMAND</div>
    <div class="section-body">
      <div class="field-block">
        <input id="startup-cmd" value="python3 vps_panel.py" readonly>
      </div>
    </div>
  </div>
  <div class="section-card">
    <div class="section-head">DOCKER IMAGE</div>
    <div class="section-body">
      <div class="field-block">
        <select id="docker-img">
          <option>ghcr.io/parkervcp/yolks:python_3.13</option>
          <option>ghcr.io/parkervcp/yolks:python_3.11</option>
          <option>ghcr.io/parkervcp/yolks:nodejs_20</option>
        </select>
        <p style="color:#7a8c98;font-size:11px;margin-top:6px">Advanced feature — choose a Docker image (cosmetic on Replit).</p>
      </div>
    </div>
  </div>
  <div class="section-card">
    <div class="section-head">VARIABLES</div>
    <div class="section-body">
      <div class="field-block">
        <label>STARTUP COMMAND</label>
        <input value="python3 vps_panel.py" readonly>
        <p style="color:#7a8c98;font-size:11px;margin-top:6px">the command to run to start it up</p>
      </div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">PIP PACKAGE INSTALLER</div>
    <div class="section-body">
      <div class="field-block"><label>Package</label><input id="pip-pkg" placeholder="flask"></div>
      <div class="row-end"><button class="btn-action" onclick="installPip()">Install</button></div>
    </div>
  </div>
</div>
''' if is_master else r'''
''') + r'''

<!-- ===== SETTINGS TAB ===== -->
<div class="tab-content" id="tab-settings">
  <div class="section-card">
    <div class="section-head">SFTP DETAILS</div>
    <div class="section-body">
      <div class="field-block">
        <label>Server Address</label>
        <input id="sftp-addr" readonly>
      </div>
      <div class="field-block">
        <label>Username</label>
        <input id="sftp-user" readonly>
      </div>
      <p style="color:#7a8c98;font-size:12px">Your SFTP password is the same as the password you use to access the panel.</p>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">DEBUG INFORMATION</div>
    <div class="section-body">
      <div class="field-block"><label>Node</label><input id="dbg-node" readonly></div>
      <div class="field-block"><label>Server ID</label><input id="dbg-id" readonly></div>
      <div class="field-block"><label>Platform</label><input id="dbg-plat" readonly></div>
    </div>
  </div>

  ''' + (r'''
  <div class="section-card">
    <div class="section-head">CHANGE MASTER CREDENTIALS</div>
    <div class="section-body">
      <div class="field-block"><label>New Username</label><input id="m-newuser" placeholder="new username"></div>
      <div class="row-end"><button class="btn-action" onclick="changeUser()">Save Username</button></div>
      <hr style="margin:14px 0;border:0;border-top:1px solid #3a4a55">
      <div class="field-block"><label>Current Password</label><input id="m-curpass" type="password"></div>
      <div class="field-block"><label>New Password</label><input id="m-newpass" type="password"></div>
      <div class="row-end"><button class="btn-action" onclick="changePass()">Save Password</button></div>
      <hr style="margin:14px 0;border:0;border-top:1px solid #3a4a55">
      <div class="field-block"><label>Server Port</label><input id="m-port" type="number"></div>
      <div class="row-end"><button class="btn-action" onclick="changePort()">Save Port (restarts panel)</button></div>
      <hr style="margin:14px 0;border:0;border-top:1px solid #3a4a55">
      <div class="row-end"><button class="btn-action danger" onclick="restartPanel()">Restart Panel</button></div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">🛠️ وضع الصيانة (MAINTENANCE MODE)</div>
    <div class="section-body">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
        <span style="color:#9aa9b3;font-size:13px">الحالة:</span>
        <span id="maint-badge" style="font-size:13px;font-weight:600;padding:4px 12px;border-radius:20px;background:#2a3a2a;color:#65c466">متوقف</span>
        <button id="maint-toggle-btn" class="btn-action" style="margin:0" onclick="toggleMaintenance()">تفعيل الصيانة</button>
      </div>
      <div class="field-block">
        <label>رسالة الصيانة (تظهر للمستخدمين)</label>
        <textarea id="maint-msg" rows="3" style="width:100%;background:#1f2933;border:1px solid #3a4a55;border-radius:5px;color:#fff;padding:10px;font-size:13px;resize:vertical"></textarea>
      </div>
      <div class="row-end">
        <button class="btn-action" onclick="saveMaintMsg()">💾 حفظ الرسالة</button>
      </div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">SYSTEM ACTIONS</div>
    <div class="section-body">
      <div class="row-end" style="gap:8px">
        <button class="btn-action gray" onclick="sysAction('clean')">Clean Memory</button>
        <button class="btn-action gray" onclick="sysAction('update')">apt update</button>
        <button class="btn-action gray" onclick="clearLogs()">Clear Logs</button>
      </div>
    </div>
  </div>
  ''' if is_master else r'''
  ''') + r'''
</div>

<!-- ===== ACTIVITY TAB (NEW - shows logins/logouts/operations) ===== -->
<div class="tab-content" id="tab-activity">
  <div class="section-card">
    <div class="section-head">ACTIVITY FEED</div>
    <div class="section-body" style="padding:8px">
      <p style="color:#9aa9b3;font-size:12px;padding:6px 10px">Latest logins, logouts and operations performed by users.</p>
      <div class="row-end" style="padding:0 10px 10px"><button class="btn-action gray" onclick="loadActivity()">Refresh</button></div>
    </div>
  </div>
  <div id="activity-list"></div>
</div>

<div class="foot-pterod">Pterodactyl® © 2015 - 2026</div>
</div>

<!-- ===== NOTIFICATION PANEL ===== -->
<div class="notif-panel" id="notif-panel" style="display:none">
  <div class="notif-head">
    <h4>🔔 مركز الإشعارات</h4>
    <div style="display:flex;gap:10px;align-items:center">
      <button onclick="markAllNotifRead()" style="color:#29c7d3">تحديد الكل كمقروء</button>
      <button onclick="toggleNotifPanel()">✕</button>
    </div>
  </div>
  <div class="notif-body" id="notif-body">
    <div class="notif-empty">لا توجد إشعارات</div>
  </div>
</div>

<!-- ===== FILE EDIT MODAL ===== -->
<div class="modal" id="edit-modal">
  <div class="modal-box">
    <div class="modal-head">
      <h3 id="edit-title">Edit File</h3>
      <button class="close" onclick="closeModal('edit-modal')">×</button>
    </div>
    <div class="modal-body">
      <textarea class="editor-textarea" id="edit-content"></textarea>
    </div>
    <div class="modal-foot">
      <button class="btn-action gray" onclick="closeModal('edit-modal')">Cancel</button>
      <button class="btn-action" onclick="saveEdit()">Save</button>
      <button class="btn-action" style="background:#65c466" onclick="runCurrentFile()">▶ Run</button>
    </div>
  </div>
</div>

<!-- ===== WELCOME OVERLAY ===== -->
<div class="welcome-overlay" id="welcome-overlay" style="display:none" onclick="if(event.target===this)closeWelcome()">
  <div class="welcome-box" id="welcome-box">
    <div class="wb-icon">👋</div>
    <h2>مرحباً!</h2>
    <div class="wb-badge-wrap" style="margin-bottom:18px"></div>
    <div class="wb-info"></div>
    <button class="wb-close" onclick="closeWelcome()">✓ تسجيل الدخول</button>
  </div>
</div>

<!-- ===== PROFILE MODAL ===== -->
<div class="modal" id="profile-modal" onclick="if(event.target===this)closeModal('profile-modal')">
  <div class="modal-box" style="max-width:440px">
    <div class="modal-head">
      <h3>👤 الملف الشخصي</h3>
      <button class="close" onclick="closeModal('profile-modal')">×</button>
    </div>
    <div class="modal-body" id="prof-content" style="padding:0 4px"></div>
    <div class="modal-foot">
      <button class="btn-action gray" onclick="closeModal('profile-modal')">إغلاق</button>
    </div>
  </div>
</div>

<!-- ===== EDIT USER MODAL (master only) ===== -->
<div class="modal" id="edit-user-modal" onclick="if(event.target===this)closeModal('edit-user-modal')">
  <div class="modal-box" style="max-width:460px">
    <div class="modal-head">
      <h3>✏️ تعديل مستخدم</h3>
      <button class="close" onclick="closeModal('edit-user-modal')">×</button>
    </div>
    <div class="modal-body">
      <div class="field-block">
        <label>اسم المستخدم الحالي</label>
        <input id="eu-username" readonly style="opacity:.6">
      </div>
      <div class="field-block">
        <label>اسم المستخدم الجديد (اختياري)</label>
        <input id="eu-new-username" placeholder="اتركه فارغاً إذا لم تريد التغيير">
      </div>
      <div class="field-block">
        <label>أقصى عدد أجهزة</label>
        <input id="eu-max" type="number" min="1" max="999">
      </div>
      <div class="field-block">
        <label>تاريخ الانتهاء</label>
        <input id="eu-expiry" type="datetime-local">
      </div>
      <div style="display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;color:#f5c518;font-weight:600;font-size:13px">
          <input type="checkbox" id="eu-vip" style="width:16px;height:16px"> ⭐ عضو VIP
        </label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;color:#ff8a8a;font-weight:600;font-size:13px">
          <input type="checkbox" id="eu-banned" style="width:16px;height:16px"> 🚫 محظور
        </label>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn-action gray" onclick="closeModal('edit-user-modal')">إلغاء</button>
      <button class="btn-action" onclick="saveEditUser()">💾 حفظ التعديلات</button>
    </div>
  </div>
</div>

<!-- run modal removed - output goes to main console -->

<script>
const IS_MASTER = ''' + ('true' if is_master else 'false') + r''';
const USER_PATH = ''' + json.dumps(get_user_path(MASTER_USERNAME if is_master else current_username)) + r''';
let currentPath = USER_PATH;
let currentEditPath = null;
let currentRunPid = null;
let runPoll = null;

/* =========== TABS =========== */
document.querySelectorAll('.tab-item').forEach(t=>{
  t.addEventListener('click',()=>{
    document.querySelectorAll('.tab-item').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    const tn = t.dataset.tab;
    const el = document.getElementById('tab-'+tn);
    if(el) el.classList.add('active');
    onTabChange(tn);
  });
});
function onTabChange(t){
  if(t==='files') loadFiles();
  if(t==='activity') loadActivity();
  if(t==='users' && IS_MASTER) loadUsers();
  if(t==='backups' && IS_MASTER) loadBackups();
  if(t==='schedules') loadSchedules();
  if(t==='network' && IS_MASTER) loadPorts();
  if(t==='settings') loadSettings();
}

/* =========== TOAST =========== */
function toast(msg, err){
  const d=document.createElement('div');
  d.className='toast'+(err?' error':'');
  d.textContent=msg;
  document.body.appendChild(d);
  setTimeout(()=>d.remove(),3000);
}

/* =========== CONSOLE / STATS =========== */
async function loadStats(){
  try{
    const r=await fetch('/api/system'); const d=await r.json();
    const panelPort = d.port || ''' + str(MASTER_CONFIG.get('port', 3278)) + r''';
    document.getElementById('s-addr').innerHTML = (d.hostname||'localhost')+':'+panelPort;
    const primaryPortEl = document.getElementById('primary-port');
    if(primaryPortEl) primaryPortEl.textContent = panelPort;
    const up=Math.floor(d.uptime||0);
    const h=Math.floor(up/3600), m=Math.floor((up%3600)/60), s=up%60;
    document.getElementById('s-uptime').textContent = h+'h '+m+'m '+s+'s';
    document.getElementById('s-cpu').innerHTML = (d.cpu_percent||0).toFixed(2)+'% <span class="max">/ 100%</span>';
    document.getElementById('s-mem').innerHTML = (d.memory_used_mb||0).toFixed(1)+' MiB <span class="max">/ '+(d.memory_total_mb||0).toFixed(0)+' MiB</span>';
    document.getElementById('s-disk').innerHTML = (d.disk_used_gb||0).toFixed(2)+' GiB <span class="max">/ '+(d.disk_total_gb||0).toFixed(0)+' GiB</span>';
    document.getElementById('s-in').textContent = (d.net_in_kb||0).toFixed(2)+' KiB';
    document.getElementById('s-out').textContent = (d.net_out_kb||0).toFixed(2)+' KiB';
    document.getElementById('s-host').textContent = d.hostname||'-';
  }catch(e){}
}
setInterval(loadStats, 4000);
loadStats();

/* live clock */
function updateClock(){
  const now = new Date();
  const hh = String(now.getHours()).padStart(2,'0');
  const mm = String(now.getMinutes()).padStart(2,'0');
  const ss = String(now.getSeconds()).padStart(2,'0');
  const yyyy = now.getFullYear();
  const mo = String(now.getMonth()+1).padStart(2,'0');
  const dd = String(now.getDate()).padStart(2,'0');
  const ct = document.getElementById('clock-time');
  const cd = document.getElementById('clock-date');
  if(ct) ct.textContent = hh+':'+mm+':'+ss;
  if(cd) cd.textContent = yyyy+'/'+mo+'/'+dd;
}
updateClock();
setInterval(updateClock, 1000);

/* =========== CONSOLE HELPERS =========== */
let mainFile = localStorage.getItem('mainFile_'+USER_PATH) || null;
let runningFilename = null;

function appendConsole(t){
  const c=document.getElementById('console-output');
  c.textContent += t + '\n';
  c.scrollTop = c.scrollHeight;
}
function setConsoleText(t){
  const c=document.getElementById('console-output');
  c.textContent = t;
  c.scrollTop = c.scrollHeight;
}
function updateConsoleStatus(){
  const badge=document.getElementById('cs-badge');
  const fileEl=document.getElementById('cs-file');
  const mainEl=document.getElementById('cs-main-lbl');
  if(mainEl) mainEl.textContent = '⭐ الرئيسي: '+(mainFile ? mainFile.split('/').pop() : 'لا يوجد');
  if(currentRunPid && runningFilename){
    badge.className='cs-badge running'; badge.textContent='🟢 RUNNING';
    fileEl.textContent = runningFilename;
  } else {
    badge.className='cs-badge stopped'; badge.textContent='⏹ STOPPED';
    fileEl.textContent = 'لا يوجد ملف يعمل حالياً';
  }
}
function switchToConsole(){
  document.querySelectorAll('.tab-item').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));
  const ti = document.querySelector('[data-tab="console"]');
  if(ti) ti.classList.add('active');
  const tc = document.getElementById('tab-console');
  if(tc) tc.classList.add('active');
}

/* =========== POWER (Start/Stop/Restart) =========== */
async function powerAction(a){
  if(a==='start'){
    if(!mainFile){ toast('حدد ملفاً رئيسياً أولاً من Files ⭐',true); return; }
    const fname = mainFile.split('/').pop();
    const fpath = mainFile.substring(0, mainFile.lastIndexOf('/'));
    await runFileIn(fpath, fname);
  } else if(a==='restart'){
    if(currentRunPid){
      await fetch('/api/file/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:currentRunPid})});
      currentRunPid=null; runningFilename=null;
      if(runPoll){ clearInterval(runPoll); runPoll=null; }
    }
    if(!mainFile){ toast('حدد ملفاً رئيسياً أولاً ⭐',true); return; }
    const fname = mainFile.split('/').pop();
    const fpath = mainFile.substring(0, mainFile.lastIndexOf('/'));
    setTimeout(()=>runFileIn(fpath, fname), 600);
  } else if(a==='stop'){
    if(!currentRunPid){ toast('لا يوجد عملية تعمل',true); return; }
    await fetch('/api/file/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:currentRunPid})});
    appendConsole('\n[■] تم إيقاف العملية');
    currentRunPid=null; runningFilename=null;
    if(runPoll){ clearInterval(runPoll); runPoll=null; }
    updateConsoleStatus(); loadFiles(true);
    toast('تم الإيقاف');
  }
}

async function runCmd(){
  const f=document.getElementById('cmd-field');
  const c=f.value.trim(); if(!c) return;
  appendConsole('» '+c);
  f.value='';
  try{
    const r=await fetch('/api/exec',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:c})});
    const d=await r.json();
    if(d.success) appendConsole(d.output||'(no output)');
    else appendConsole('[ERR] '+(d.error||''));
  }catch(e){ appendConsole('[ERR] '+e); }
}

/* =========== FILES =========== */
async function loadFiles(silent=false){
  try{
    const [runningRes, filesRes] = await Promise.all([
      fetch('/api/file/running').then(r=>r.json()).catch(()=>({running:[]})),
      fetch('/api/files?path='+encodeURIComponent(currentPath)).then(r=>r.json())
    ]);
    const runningList = runningRes.running||[];
    const list=document.getElementById('file-list');
    document.getElementById('breadcrumb').innerHTML = renderCrumb(currentPath);
    let html = '';
    if(currentPath !== USER_PATH){
      html += '<div class="file-row" style="cursor:pointer" onclick="goUp()"><span class="ico">⬅</span><span class="file-name-click">..</span></div>';
    }
    (filesRes.files||[]).forEach(f=>{
      const ico = f.is_dir ? '📁' : '📄';
      const safe = f.name.replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'&quot;');
      const fp = currentPath+'/'+f.name;
      const isMain = mainFile === fp;
      const runEntry = runningList.find(x=>x.filename===f.name);
      const isRunning = !f.is_dir && !!runEntry;
      const badges = (isMain?'<span class="badge-main-f">⭐ رئيسي</span>':'')+
                     (isRunning?'<span class="badge-run">🟢 يعمل</span>':'');
      let actions = '';
      if(f.is_dir){
        actions = `<button class="btn-fac f-rename" onclick="event.stopPropagation();renameFile('${safe}')">✏️ تسمية</button>
                   <button class="btn-fac f-del" onclick="event.stopPropagation();deleteFile('${safe}',true)">🗑 حذف</button>`;
      } else {
        const runPid = runEntry ? runEntry.process_id : null;
        const stopBtn = isRunning
          ? `<button class="btn-fac f-stop" onclick="event.stopPropagation();stopFileByPid(${runPid})">■ إيقاف</button>`
          : `<button class="btn-fac f-run" onclick="event.stopPropagation();runFile('${safe}')">▶ تشغيل</button>`;
        actions = `
          <button class="btn-fac f-edit" onclick="event.stopPropagation();openEdit('${safe}')">📝 تعديل</button>
          ${stopBtn}
          <button class="btn-fac f-main" onclick="event.stopPropagation();setMainFile('${fp.replace(/'/g,"\\'")}','${safe}')">⭐ رئيسي</button>
          <button class="btn-fac f-rename" onclick="event.stopPropagation();renameFile('${safe}')">✏️ تسمية</button>
          <button class="btn-fac f-del" onclick="event.stopPropagation();deleteFile('${safe}',false)">🗑 حذف</button>`;
      }
      html += `
        <div class="file-row">
          <span class="ico">${ico}</span>
          <span class="file-name-click" onclick="${f.is_dir?`enterDir('${safe}')`:`openEdit('${safe}')`}">${escapeHtml(f.name)}</span>
          ${badges}
          <div class="file-actions">${actions}</div>
        </div>`;
    });
    list.innerHTML = html;
  }catch(e){ if(!silent) toast('فشل تحميل الملفات',true); }
}
function renderCrumb(p){
  const parts = p.split('/').filter(Boolean);
  let acc='';
  let html='<span class="crumb sep">/</span>';
  parts.forEach((seg)=>{
    acc += '/'+seg;
    html += `<span class="crumb" onclick="navTo('${acc}')">${seg}</span><span class="sep">/</span>`;
  });
  return html;
}
function navTo(p){ currentPath=p; loadFiles(); }
function enterDir(name){ currentPath = currentPath.replace(/\/$/,'')+'/'+name; loadFiles(); }
function goUp(){
  const p = currentPath.replace(/\/$/,'').split('/'); p.pop();
  currentPath = p.join('/') || '/';
  if(!currentPath.startsWith(USER_PATH) && !IS_MASTER) currentPath = USER_PATH;
  loadFiles();
}
async function createDir(){
  const n = prompt('اسم المجلد:'); if(!n) return;
  const r=await fetch('/api/files/folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path: currentPath+'/'+n})});
  const d=await r.json(); if(d.success){toast('تم الإنشاء');loadFiles();}else toast('فشل: '+(d.error||''),true);
}
async function newFile(){
  const n = prompt('اسم الملف (مثلاً bot.py):'); if(!n) return;
  const r=await fetch('/api/files/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path: currentPath+'/'+n,content:''})});
  const d=await r.json(); if(d.success){toast('تم الإنشاء');loadFiles();}else toast('فشل: '+(d.error||''),true);
}
async function uploadFile(inp){
  const f=inp.files[0]; if(!f) return;
  toast('جاري الرفع وتثبيت المكتبات...');
  switchToConsole();
  appendConsole('[↑] جاري رفع الملف: '+f.name+' ...');
  const fd=new FormData(); fd.append('file',f); fd.append('path',currentPath);
  const r=await fetch('/api/files/upload',{method:'POST',body:fd});
  const d=await r.json();
  if(d.success){
    appendConsole('[✓] تم رفع الملف: '+f.name);
    appendConsole('[📦] جاري تثبيت المكتبات تلقائياً...');
    const ir=await fetch('/api/file/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentPath,filename:f.name})});
    const id=await ir.json();
    if(id.installed && id.installed.length) appendConsole('[✓] تم تثبيت: '+id.installed.join(', '));
    if(id.failed && id.failed.length) appendConsole('[!] فشل تثبيت: '+id.failed.join(', '));
    if(!id.installed?.length && !id.failed?.length) appendConsole('[i] لا توجد مكتبات إضافية مطلوبة');
    toast('تم الرفع بنجاح');
    loadFiles(true);
  } else {
    appendConsole('[ERR] فشل رفع الملف: '+(d.error||''));
    toast('فشل الرفع',true);
  }
  inp.value='';
}
function setMainFile(fp, name){
  mainFile = fp;
  localStorage.setItem('mainFile_'+USER_PATH, fp);
  toast('✓ تم تعيين '+name+' كملف رئيسي');
  updateConsoleStatus();
  loadFiles();
}
async function renameFile(name){
  const nn = prompt('الاسم الجديد:', name); if(!nn||nn===name) return;
  const fp = currentPath+'/'+name;
  const r=await fetch('/api/files/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old_path:fp,new_name:nn})});
  const d=await r.json(); if(d.success){toast('تم التسمية');loadFiles();}else toast('فشل',true);
}
async function deleteFile(name, isDir){
  if(!confirm('حذف '+name+'؟')) return;
  const fp = currentPath+'/'+name;
  const r=await fetch('/api/files/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:fp})});
  const d=await r.json(); if(d.success){toast('تم الحذف');loadFiles();}else toast('فشل',true);
}
async function openEdit(name){
  const fp = currentPath+'/'+name;
  const r=await fetch('/api/files/content?path='+encodeURIComponent(fp));
  const d=await r.json();
  if(d.content===undefined){ toast('لا يمكن قراءة الملف',true); return; }
  currentEditPath = fp;
  document.getElementById('edit-title').textContent = 'تعديل: '+name;
  document.getElementById('edit-content').value = d.content;
  document.getElementById('edit-modal').classList.add('show');
}
async function saveEdit(){
  const c = document.getElementById('edit-content').value;
  const r=await fetch('/api/files/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentEditPath,content:c})});
  const d=await r.json(); if(d.success){toast('تم الحفظ');closeModal('edit-modal');}else toast('فشل',true);
}
function runCurrentFile(){
  if(!currentEditPath) return;
  const name = currentEditPath.split('/').pop();
  const path = currentEditPath.substring(0, currentEditPath.lastIndexOf('/'));
  closeModal('edit-modal');
  runFileIn(path, name);
}
async function runFile(name){
  await runFileIn(currentPath, name);
}
async function runFileIn(path, name){
  switchToConsole();
  setConsoleText('[▶] جاري تشغيل: '+name+'\n[📦] تثبيت المكتبات...\n');
  updateConsoleStatus();
    const r=await fetch('/api/file/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path, filename:name})});
  const d=await r.json();
  if(!d.success){ appendConsole('[ERR] '+( d.error||'فشل التشغيل')); toast('فشل التشغيل',true); return; }
  currentRunPid = d.process_id;
  runningFilename = name;
  if(d.installed_result){
    if(d.installed_result.installed?.length) appendConsole('[✓] مكتبات مثبتة: '+d.installed_result.installed.join(', '));
    if(d.installed_result.failed?.length) appendConsole('[!] فشل تثبيت: '+d.installed_result.failed.join(', '));
  }
  appendConsole('[🟢] تم تشغيل '+name+' (PID: '+currentRunPid+')');
  if(d.port){
    const proxyUrl = window.location.origin+'/proxy/'+d.port+'/';
    appendConsole('[🌐] البورت الخاص: '+d.port);
    appendConsole('[🔗] رابط تطبيقك: '+proxyUrl);
  }
  if(runPoll) clearInterval(runPoll);
  runPoll = setInterval(pollRunOutput, 1000);
  updateConsoleStatus();
  loadFiles(true);
}
async function pollRunOutput(){
  if(!currentRunPid) return;
  try{
    const r=await fetch('/api/file/output/'+currentRunPid);
    const d=await r.json();
    if(d.success){
      const c=document.getElementById('console-output');
      const out=(d.output||[]).join('\n');
      c.textContent = out;
      c.scrollTop = c.scrollHeight;
      if(!d.is_running){
        clearInterval(runPoll); runPoll=null;
        appendConsole('\n[■] انتهت العملية');
        currentRunPid=null; runningFilename=null;
        updateConsoleStatus(); loadFiles(true);
      }
    }
  }catch(e){}
}
async function stopCurrentRun(){
  if(!currentRunPid) return;
  await stopFileByPid(currentRunPid);
}
async function stopFileByPid(pid){
  if(!pid) return;
  await fetch('/api/file/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:pid})});
  appendConsole('\n[■] تم الإيقاف');
  if(pid === currentRunPid){
    currentRunPid=null; runningFilename=null;
    if(runPoll){ clearInterval(runPoll); runPoll=null; }
    updateConsoleStatus();
  }
  loadFiles(true);
  toast('تم إيقاف العملية');
}
async function sendRunInput(){
  const f=document.getElementById('cmd-field'); const v=f.value.trim();
  if(!v||!currentRunPid) return; f.value='';
  appendConsole('» '+v);
  await fetch('/api/file/input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:currentRunPid,input:v})});
}
function closeModal(id){ document.getElementById(id).classList.remove('show'); }

/* =========== ACTIVITY =========== */
async function loadActivity(){
  try{
    const r=await fetch('/api/activity'); const d=await r.json();
    const list = document.getElementById('activity-list');
    list.innerHTML = '';
    (d.events||[]).forEach(e=>{
      list.innerHTML += `
        <div class="activity-card">
          <div class="a-head"><span class="user">${escapeHtml(e.username||'-')}</span> — <span class="action">${escapeHtml(e.action||'')}</span></div>
          ${e.details?`<div class="a-desc">${escapeHtml(e.details)}</div>`:''}
          <div class="a-meta">${escapeHtml(e.ip||'-')} | ${escapeHtml(e.time_text||'')}</div>
        </div>`;
    });
    if(!(d.events||[]).length) list.innerHTML = '<div class="activity-card"><div class="a-desc">No activity yet.</div></div>';
  }catch(e){ toast('Failed',true); }
}
function escapeHtml(s){ return (s||'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

/* =========== SETTINGS =========== */
let _maintMode = false;

async function loadSettings(){
  try{
    const r=await fetch('/api/system'); const d=await r.json();
    const port = d.port || ''' + str(MASTER_CONFIG.get('port', 3278)) + r''';
    document.getElementById('sftp-addr').value = 'sftp://'+(d.hostname||'localhost')+':2022';
    document.getElementById('sftp-user').value = ''' + json.dumps(MASTER_USERNAME if is_master else 'user') + r''';
    document.getElementById('dbg-node').value = d.hostname || 'Local Node';
    document.getElementById('dbg-id').value = ''' + json.dumps(str(uuid.uuid4())) + r''';
    document.getElementById('dbg-plat').value = d.platform || '-';
    if(IS_MASTER){
      const mp=document.getElementById('m-port'); if(mp) mp.value = port;
    }
    document.getElementById('primary-host').textContent = (d.hostname||'localhost');
    const primaryPortEl = document.getElementById('primary-port');
    if(primaryPortEl) primaryPortEl.textContent = d.port || port;
  }catch(e){}
  if(IS_MASTER) loadMaintenance();
}
async function loadMaintenance(){
  try{
    const r=await fetch('/api/master/maintenance'); const d=await r.json();
    _maintMode = d.maintenance_mode;
    const badge=document.getElementById('maint-badge');
    const btn=document.getElementById('maint-toggle-btn');
    const ta=document.getElementById('maint-msg');
    if(!badge) return;
    if(_maintMode){
      badge.textContent='🔴 مفعّل'; badge.style.background='rgba(229,57,53,.2)'; badge.style.color='#ff8a8a';
      btn.textContent='إيقاف الصيانة'; btn.style.background='#e53935';
    } else {
      badge.textContent='🟢 متوقف'; badge.style.background='rgba(101,196,102,.12)'; badge.style.color='#65c466';
      btn.textContent='تفعيل الصيانة'; btn.style.background='#2f6fed';
    }
    if(ta) ta.value = d.maintenance_message || '';
  }catch(e){}
}
async function toggleMaintenance(){
  _maintMode = !_maintMode;
  const ta=document.getElementById('maint-msg');
  const msg = ta ? ta.value.trim() : '';
  const r=await fetch('/api/master/maintenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({maintenance_mode:_maintMode,maintenance_message:msg})});
  const d=await r.json();
  if(d.success){ toast(_maintMode?'🔴 وضع الصيانة مفعّل':'🟢 وضع الصيانة متوقف'); loadMaintenance(); }
  else{ toast('فشل',true); _maintMode=!_maintMode; }
}
async function saveMaintMsg(){
  const ta=document.getElementById('maint-msg'); if(!ta) return;
  const r=await fetch('/api/master/maintenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({maintenance_mode:_maintMode,maintenance_message:ta.value.trim()})});
  const d=await r.json(); toast(d.success?'✓ تم حفظ الرسالة':'فشل',!d.success);
}
async function changeUser(){
  const v=document.getElementById('m-newuser').value.trim(); if(!v) return;
  const r=await fetch('/api/master/change-username',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_username:v})});
  const d=await r.json(); toast(d.success?'Saved (re-login)':'Failed', !d.success);
}
async function changePass(){
  const cur=document.getElementById('m-curpass').value; const nw=document.getElementById('m-newpass').value;
  if(!cur||!nw) return;
  const r=await fetch('/api/master/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:cur,new_password:nw})});
  const d=await r.json(); toast(d.success?'Password changed':'Wrong current password', !d.success);
}
async function changePort(){
  const p=parseInt(document.getElementById('m-port').value); if(!p) return;
  if(!confirm('Change port and restart panel?')) return;
  await fetch('/api/master/change-port',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p})});
  toast('Restarting...');
}
async function restartPanel(){
  if(!confirm('Restart panel?')) return;
  await fetch('/api/master/restart',{method:'POST'}); toast('Restarting...');
}
async function sysAction(a){
  const r=await fetch('/api/system/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})});
  const d=await r.json(); toast(d.success?('OK: '+a):'Failed', !d.success);
}
async function clearLogs(){
  await fetch('/api/logs/clear',{method:'POST'}); toast('Logs cleared');
}

/* =========== USERS =========== */
async function loadUsers(){
  if(!IS_MASTER) return;
  const r=await fetch('/api/users/list'); const d=await r.json();
  const list=document.getElementById('user-list'); list.innerHTML='';
  (d.users||[]).forEach(u=>{
    const expTxt = u.expiry ? '⏰ '+u.expiry.replace('T',' ') : '∞ بلا انتهاء';
    const isExpired = u.expiry && new Date(u.expiry) < new Date();
    const vipBadge = u.vip ? '<span style="background:rgba(245,197,24,.15);color:#f5c518;border:1px solid rgba(245,197,24,.4);padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700">⭐ VIP</span>' : '';
    const banBadge = u.banned ? '<span style="background:rgba(229,57,53,.15);color:#ff8a8a;border:1px solid rgba(229,57,53,.4);padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700">🚫 محظور</span>' : '';
    const uSafe = escapeHtml(u.username);
    list.innerHTML += `
      <div class="user-row" style="${u.banned?'opacity:.7':''}">
        <div style="flex:1">
          <div class="uname" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${uSafe} ${vipBadge} ${banBadge}</div>
          <div class="meta">أجهزة: ${u.active_sessions||0}/${u.max_sessions||999} &nbsp;|&nbsp; <span style="color:${isExpired?'#e53935':'#65c466'}">${expTxt}</span>${u.assigned_port ? ' &nbsp;|&nbsp; <span style="color:#29c7d3">🔌 بورت: '+u.assigned_port+'</span> <a href="/proxy/'+u.assigned_port+'/" target="_blank" style="color:#2f6fed;font-size:11px">[رابط]</a>' : ''}</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn-action gray" style="padding:8px 14px" onclick="openEditUser(${JSON.stringify(u).replace(/"/g,'&quot;')})">✏️ تعديل</button>
          <button class="btn-action danger" style="padding:8px 14px" onclick="delUser('${uSafe}')">🗑 حذف</button>
        </div>
      </div>`;
  });
}
async function addUser(){
  const u=document.getElementById('u-name').value.trim();
  const p=document.getElementById('u-pass').value;
  const m=document.getElementById('u-max').value||3;
  const ex=document.getElementById('u-expiry').value;
  const vip=document.getElementById('u-vip').checked;
  if(!u||!p){ toast('أدخل اسم المستخدم وكلمة المرور',true); return; }
  const body={username:u,password:p,max_sessions:m,vip:vip};
  if(ex) body.expiry=ex;
  const r=await fetch('/api/users/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.success){
    toast('✓ تم إضافة المستخدم' + (d.assigned_port ? ' — بورت: '+d.assigned_port : ''));
    document.getElementById('u-name').value='';
    document.getElementById('u-pass').value='';
    document.getElementById('u-max').value='3';
    document.getElementById('u-expiry').value='';
    document.getElementById('u-vip').checked=false;
    loadUsers();
  }else toast('فشل: '+(d.error||'خطأ غير معروف'),true);
}
async function delUser(u){
  if(!confirm('حذف المستخدم '+u+'؟')) return;
  await fetch('/api/users/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u})});
  toast('✓ تم الحذف'); loadUsers();
}
let _editingUser = null;
function openEditUser(u){
  _editingUser = u;
  document.getElementById('eu-username').value = u.username;
  document.getElementById('eu-new-username').value = '';
  document.getElementById('eu-max').value = u.max_sessions||3;
  document.getElementById('eu-expiry').value = u.expiry ? u.expiry.slice(0,16) : '';
  document.getElementById('eu-vip').checked = !!u.vip;
  document.getElementById('eu-banned').checked = !!u.banned;
  document.getElementById('edit-user-modal').classList.add('show');
}
async function saveEditUser(){
  if(!_editingUser) return;
  const newU = document.getElementById('eu-new-username').value.trim();
  const body = {
    username: _editingUser.username,
    max_sessions: parseInt(document.getElementById('eu-max').value)||3,
    expiry: document.getElementById('eu-expiry').value||null,
    vip: document.getElementById('eu-vip').checked,
    banned: document.getElementById('eu-banned').checked,
  };
  if(newU && newU !== _editingUser.username) body.new_username = newU;
  const r=await fetch('/api/users/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.success){ toast('✓ تم التحديث'); closeModal('edit-user-modal'); loadUsers(); }
  else toast('فشل: '+(d.error||''),true);
}

/* =========== PROFILE & WELCOME =========== */
let _profileData = null;
async function showProfile(){
  const r=await fetch('/api/profile'); const d=await r.json();
  _profileData = d;
  const modal = document.getElementById('profile-modal');
  const av = document.getElementById('topbar-avatar');
  const isMaster = d.is_master;
  const vip = d.vip;
  let badgeHtml = isMaster
    ? '<span class="wb-badge master">👑 Master</span>'
    : vip ? '<span class="wb-badge vip">⭐ VIP</span>'
    : '<span class="wb-badge normal">🔵 مستخدم عادي</span>';
  const fmtDate = s => s ? s.replace('T',' ').slice(0,16) : '—';
  const expiry = d.expiry ? fmtDate(d.expiry) : (isMaster ? '∞ مدى الحياة' : '∞ بلا انتهاء');
  const created = fmtDate(d.created);
  const maskedPass = '••••••••';
  document.getElementById('prof-content').innerHTML = `
    <div style="text-align:center;margin-bottom:20px">
      <div style="font-size:54px;margin-bottom:8px">${isMaster?'👑':vip?'⭐':'👤'}</div>
      <div style="font-size:20px;font-weight:700;color:#fff;margin-bottom:6px">${escapeHtml(d.username)}</div>
      ${badgeHtml}
    </div>
    <div class="prof-field"><span class="pf-lbl">اسم المستخدم</span><span class="pf-val">${escapeHtml(d.username)}</span></div>
    <div class="prof-field"><span class="pf-lbl">كلمة المرور</span><span class="pf-val" style="letter-spacing:3px">${maskedPass}</span></div>
    ${!isMaster?`<div class="prof-field"><span class="pf-lbl">تاريخ الإنشاء</span><span class="pf-val">${created}</span></div>`:''}
    ${!isMaster?`<div class="prof-field"><span class="pf-lbl">تاريخ الانتهاء</span><span class="pf-val" style="color:${d.expiry && new Date(d.expiry)<new Date()?'#e53935':'#65c466'}">${expiry}</span></div>`:''}
    <div class="prof-field"><span class="pf-lbl">حجم الملفات</span><span class="pf-val">${(d.disk_usage_gb||0).toFixed(3)} GB</span></div>
    ${!isMaster?`<div class="prof-field"><span class="pf-lbl">عدد الأجهزة المسموحة</span><span class="pf-val">${d.max_sessions||999}</span></div>`:''}
  `;
  modal.classList.add('show');
  if(av) av.textContent = (d.username||'').slice(0,2).toUpperCase();
}
function showWelcome(d){
  const isMaster = d.is_master;
  const vip = d.vip;
  let badgeHtml = isMaster
    ? '<span class="wb-badge master">👑 Master</span>'
    : vip ? '<span class="wb-badge vip">⭐ VIP</span>'
    : '<span class="wb-badge normal">🔵 مستخدم عادي</span>';
  const fmtDate = s => s ? s.replace('T',' ').slice(0,16) : '—';
  const expiry = d.expiry ? fmtDate(d.expiry) : (isMaster ? '∞ مدى الحياة' : '∞ بلا انتهاء');
  const created = fmtDate(d.created);
  const box = document.getElementById('welcome-box');
  box.querySelector('.wb-icon').textContent = isMaster?'👑':vip?'⭐':'👋';
  box.querySelector('h2').textContent = 'مرحباً، '+d.username+'!';
  box.querySelector('.wb-badge-wrap').innerHTML = badgeHtml;
  box.querySelector('.wb-info').innerHTML =
    (!isMaster ? `<div>📅 تاريخ الإنشاء: <span>${created}</span></div>` : '') +
    (!isMaster ? `<div>⏰ تاريخ الانتهاء: <span style="color:${d.expiry && new Date(d.expiry)<new Date()?'#e53935':'#65c466'}">${expiry}</span></div>` : '') +
    `<div>💾 استخدام المساحة: <span>${(d.disk_usage_gb||0).toFixed(3)} GB</span></div>`;
  document.getElementById('welcome-overlay').style.display='flex';
}
function closeWelcome(){
  document.getElementById('welcome-overlay').style.display='none';
}
async function initPage(){
  const r=await fetch('/api/profile').catch(()=>null);
  if(!r||!r.ok) return;
  const d=await r.json();
  const av=document.getElementById('topbar-avatar');
  if(av) av.textContent=(d.username||'').slice(0,2).toUpperCase();
  if(d.show_welcome) showWelcome(d);
  const rn=await fetch('/api/file/running').then(x=>x.json()).catch(()=>({running:[]}));
  const running=(rn.running||[]);
  if(running.length>0){
    const first=running[0];
    if(!currentRunPid){
      currentRunPid=first.process_id;
      runningFilename=first.filename;
      if(runPoll) clearInterval(runPoll);
      runPoll=setInterval(pollRunOutput,1000);
    }
    updateConsoleStatus();
  }
}
initPage();

/* =========== BACKUPS =========== */
async function loadBackups(){
  if(!IS_MASTER) return;
  const r=await fetch('/api/backups/list'); const d=await r.json();
  const list=document.getElementById('backup-list'); list.innerHTML='';
  (d.backups||[]).forEach(b=>{
    list.innerHTML += `<div class="user-row"><div><div class="uname">${escapeHtml(b.name)}</div><div class="meta">${b.size}</div></div></div>`;
  });
  if(!(d.backups||[]).length) list.innerHTML='<div class="activity-card"><div class="a-desc">No backups yet.</div></div>';
}
async function createBackup(){
  toast('Creating backup...');
  const r=await fetch('/api/backups/create',{method:'POST'});
  const d=await r.json(); toast(d.success?'Backup created':'Failed', !d.success);
  loadBackups();
}

/* =========== SCHEDULES =========== */
async function loadSchedules(){
  try{
    const r=await fetch('/api/schedules/list'); const d=await r.json();
    const list=document.getElementById('sch-list'); list.innerHTML='';
    (d.schedules||[]).forEach(s=>{
      list.innerHTML += `<div class="user-row"><div><div class="uname">${escapeHtml(s.name)}</div><div class="meta">${escapeHtml(s.command)} — ${escapeHtml(s.schedule)}</div></div></div>`;
    });
  }catch(e){}
}
async function addSchedule(){
  const n=document.getElementById('sch-name').value.trim();
  const c=document.getElementById('sch-cmd').value.trim();
  const cr=document.getElementById('sch-cron').value.trim()||'* * * * *';
  if(!n||!c){ toast('Fill all fields',true); return; }
  const r=await fetch('/api/schedules/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,command:c,schedule:cr})});
  const d=await r.json(); if(d.success){toast('Added');loadSchedules();}else toast('Failed',true);
}

/* =========== PORTS / NETWORK =========== */
async function loadPorts(){
  if(!IS_MASTER) return;
  const r=await fetch('/api/ports/list'); const d=await r.json();
  const list=document.getElementById('port-list'); if(!list) return; list.innerHTML='';
  (d.ports||[]).forEach(p=>{
    list.innerHTML += `
      <div class="port-card">
        <div class="port-head">
          <div class="port-host">${escapeHtml(p.note||'Port')}</div>
          <div class="port-badge">${p.port}</div>
        </div>
        <div class="port-note">Status: ${p.status||'idle'}</div>
        <div class="row-end" style="gap:6px;margin-top:8px">
          <button class="btn-action danger" onclick="delPort(${p.port})">Remove</button>
        </div>
      </div>`;
  });
}
async function addPort(){
  const p=parseInt(document.getElementById('new-port').value);
  const n=document.getElementById('new-port-note').value||'Custom port';
  if(!p){ toast('Invalid port',true); return; }
  const r=await fetch('/api/ports/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p,note:n})});
  const d=await r.json(); if(d.success){toast('Added');loadPorts();}else toast(d.error||'Failed',true);
}
async function delPort(p){
  if(!confirm('Remove port '+p+'?')) return;
  await fetch('/api/ports/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p})});
  toast('Removed'); loadPorts();
}
async function scanPorts(){
  const h=document.getElementById('scan-host').value;
  const ps=document.getElementById('scan-ports').value.split(',').map(x=>x.trim()).filter(Boolean);
  const r=await fetch('/api/network/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:h,ports:ps})});
  const d=await r.json();
  document.getElementById('scan-out').innerHTML = (d.results||[]).map(x=>`Port ${x.port}: <span style="color:${x.open?'#65c466':'#e53935'}">${x.open?'OPEN':'CLOSED'}</span>`).join('<br>');
}

/* =========== PIP =========== */
async function installPip(){
  const p=document.getElementById('pip-pkg').value.trim(); if(!p) return;
  toast('Installing '+p+'...');
  const r=await fetch('/api/packages/install/pip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package:p})});
  const d=await r.json(); toast(d.success?'Installed':'Failed', !d.success);
}

/* =========== SEARCH =========== */
function loadSearch(){
  const q=prompt('Search (placeholder):'); if(q) toast('Search: '+q);
}

/* =========== DB (simple) =========== */
async function createDB(){
  const n=document.getElementById('db-name').value.trim(); if(!n) return;
  const r=await fetch('/api/files/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:USER_PATH+'/'+n+'.json',content:'{}'})});
  const d=await r.json(); toast(d.success?'DB created':'Failed', !d.success);
}

/* =========== NOTIFICATIONS =========== */
let _notifOpen = false;
async function loadNotifications(){
  try{
    const r=await fetch('/api/notifications'); const d=await r.json();
    const items=d.notifications||[];
    const unread=items.filter(n=>!n.read).length;
    const badge=document.getElementById('notif-badge');
    if(badge){
      badge.textContent=unread;
      badge.style.display=unread>0?'flex':'none';
    }
    const body=document.getElementById('notif-body');
    if(!body) return;
    if(!items.length){body.innerHTML='<div class="notif-empty">📭 لا توجد إشعارات</div>';return;}
    const typeIcon={'info':'ℹ️','warning':'⚠️','danger':'🔴'};
    body.innerHTML=items.map(n=>`
      <div class="notif-item ${n.read?'':'unread'} type-${n.type||'info'}" onclick="markNotifRead('${n.id}')">
        <div class="n-title">${typeIcon[n.type||'info']||'ℹ️'} ${escapeHtml(n.title)}</div>
        <div class="n-msg">${escapeHtml(n.message)}</div>
        <div class="n-time">${escapeHtml(n.time_text||'')}</div>
      </div>`).join('');
    if(IS_MASTER) populateNotifySelect(d.all_users||[]);
  }catch(e){}
}
function toggleNotifPanel(){
  const p=document.getElementById('notif-panel');
  if(!p) return;
  _notifOpen=!_notifOpen;
  p.style.display=_notifOpen?'flex':'none';
  if(_notifOpen) loadNotifications();
}
document.addEventListener('click',function(e){
  const panel=document.getElementById('notif-panel');
  const btn=document.getElementById('notif-btn');
  if(_notifOpen && panel && !panel.contains(e.target) && !btn.contains(e.target)){
    _notifOpen=false; panel.style.display='none';
  }
});
async function markNotifRead(id){
  await fetch('/api/notifications/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
  loadNotifications();
}
async function markAllNotifRead(){
  await fetch('/api/notifications/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({all:true})});
  loadNotifications();
}
function populateNotifySelect(users){
  const sel=document.getElementById('notify-target');
  if(!sel) return;
  const cur=sel.value;
  while(sel.options.length>1) sel.remove(1);
  users.forEach(u=>{
    const o=document.createElement('option');
    o.value=u; o.textContent='👤 '+u;
    sel.appendChild(o);
  });
  sel.value=cur||'__all__';
}
async function sendNotification(){
  const target=document.getElementById('notify-target')?.value||'__all__';
  const title=(document.getElementById('notify-title')?.value||'').trim();
  const msg=(document.getElementById('notify-msg')?.value||'').trim();
  const type=document.getElementById('notify-type')?.value||'info';
  if(!title||!msg){toast('أدخل العنوان والرسالة',true);return;}
  const r=await fetch('/api/master/notify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target,title,message:msg,type})});
  const d=await r.json();
  if(d.success){
    toast(`✓ تم الإرسال لـ ${d.count} مستخدم`);
    document.getElementById('notify-title').value='';
    document.getElementById('notify-msg').value='';
  }else toast(d.error||'فشل الإرسال',true);
}
/* poll notifications every 30s */
setInterval(loadNotifications, 30000);
loadNotifications();

/* init */
loadFiles(true);
updateConsoleStatus();
</script>
</body>
</html>
'''

# =============================================================================
# 13)  مسارات الـ Flask
# =============================================================================
@app.route('/')
@login_required
def index():
    is_master = (session.get('username') == MASTER_USERNAME)
    return render_template_string(
        get_html_template(is_master, session.get('username', '')),
        session=session,
        user_path=get_user_path(session['username'])
    )

@app.route('/register')
def register_page():
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        return render_template_string(LOGIN_TEMPLATE, error=None)
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    h = hashlib.sha256(password.encode()).hexdigest()
    if username == MASTER_USERNAME and h == MASTER_PASSWORD_HASH:
        session.permanent = True
        session['logged_in'] = True
        session['username'] = username
        register_session(username)
        log_activity(username, 'auth.login', 'Master login successful')
        return redirect('/')
    users = load_users()
    ud = users.get(username, {}) if isinstance(users.get(username), dict) else {}
    password_ok = username in users and ud.get('password') == h
    if password_ok and not ud.get('banned', False) and can_user_login(username):
        if MASTER_CONFIG.get('maintenance_mode', False):
            return redirect('/maintenance')
        session.permanent = True
        session['logged_in'] = True
        session['username'] = username
        session['show_welcome'] = True
        register_session(username)
        os.makedirs(get_user_path(username), exist_ok=True)
        log_activity(username, 'auth.login', 'User login successful')
        threading.Thread(target=check_expiry_notification, args=(username,), daemon=True).start()
        return redirect('/')
    err = get_login_error(username, password_ok)
    log_activity(username or '-', 'auth.login.failed', err)
    return render_template_string(LOGIN_TEMPLATE, error=err)

@app.route('/logout')
def logout():
    if 'username' in session:
        log_activity(session['username'], 'auth.logout', 'User logged out')
        unregister_session(session['username'])
    session.clear()
    return redirect('/login')

@app.route('/api/profile')
@login_required
def get_profile():
    u = session['username']
    p = get_user_path(u)
    size = 0
    if os.path.exists(p):
        for r, d, f in os.walk(p):
            for fl in f:
                fp = os.path.join(r, fl)
                if os.path.exists(fp):
                    size += os.path.getsize(fp)
    users = load_users()
    ud = users.get(u, {}) if isinstance(users.get(u), dict) else {}
    is_master = (u == MASTER_USERNAME)
    show_welcome = session.pop('show_welcome', False)
    return jsonify({
        'username': u,
        'is_master': is_master,
        'vip': ud.get('vip', False) if not is_master else False,
        'banned': ud.get('banned', False) if not is_master else False,
        'created': ud.get('created', '') if not is_master else '',
        'expiry': ud.get('expiry', None) if not is_master else None,
        'max_sessions': ud.get('max_sessions', 999) if not is_master else 999,
        'disk_usage_gb': round(size / (1024**3), 3),
        'show_welcome': show_welcome,
        'port': MASTER_CONFIG.get('port', 3278),
        'assigned_port': ud.get('assigned_port') if not is_master else None,
    })

@app.route('/api/system')
@login_required
def system_info():
    return jsonify(get_system_stats())

@app.route('/api/sysinfo')
@login_required
def sysinfo():
    return jsonify({'info': f"Platform: {platform.platform()}\nCPU: {psutil.cpu_percent()}%\nMemory: {psutil.virtual_memory().percent}%"})

@app.route('/api/system/action', methods=['POST'])
@login_required
def system_action_api():
    a = (request.json or {}).get('action')
    try:
        if a == 'clean':
            gc.collect()
        elif a == 'update':
            subprocess.run(['apt-get', 'update'], capture_output=True, timeout=120)
        log_activity(session['username'], 'system.action', a or '')
        return jsonify({'success': True, 'action': a})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ----- Activity feed -----
@app.route('/api/activity')
@login_required
def activity_api():
    data = load_json_file(ACTIVITY_FILE, {'events': []})
    events = data.get('events', [])
    if session.get('username') != MASTER_USERNAME:
        events = [e for e in events if e.get('username') == session.get('username')]
    return jsonify({'events': events[:200]})

# ----- ملفات -----
@app.route('/api/files')
@login_required
def list_files_api():
    try:
        p = resolve_user_path(session['username'], request.args.get('path', get_user_path(session['username'])))
    except PermissionError:
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    files = []
    try:
        for n in sorted(os.listdir(p), key=lambda x: (not os.path.isdir(os.path.join(p, x)), x.lower())):
            fp = os.path.join(p, n)
            files.append({
                'name': n,
                'is_dir': os.path.isdir(fp),
                'size': f"{os.path.getsize(fp)//1024} KB" if os.path.isfile(fp) else '',
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'files': files})

@app.route('/api/files/upload', methods=['POST'])
@login_required
def upload_file_api():
    try:
        f = request.files.get('file')
        if not f:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        p = resolve_user_path(session['username'], request.form.get('path', get_user_path(session['username'])))
        os.makedirs(p, exist_ok=True)
        safe_name = sanitize_user_filename(f.filename or 'upload')
        f.save(os.path.join(p, safe_name))
        log_activity(session['username'], 'server.file.upload', safe_name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/folder', methods=['POST'])
@login_required
def create_folder_api():
    try:
        d = request.json or {}
        path = d.get('path', '')
        if not path:
            return jsonify({'success': False, 'error': 'No path provided'}), 400
        path = resolve_user_path(session['username'], path)
        os.makedirs(path, exist_ok=True)
        log_activity(session['username'], 'server.file.mkdir', path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/create', methods=['POST'])
@login_required
def create_file_api():
    try:
        d = request.json or {}
        path = d.get('path', '')
        if not path:
            return jsonify({'success': False, 'error': 'No path provided'}), 400
        path = resolve_user_path(session['username'], path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(d.get('content', ''))
        log_activity(session['username'], 'server.file.create', path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/rename', methods=['POST'])
@login_required
def rename_file_api():
    try:
        d = request.json or {}
        old_path = resolve_user_path(session['username'], d.get('old_path', ''))
        new_name = d.get('new_name', '')
        if not old_path or not new_name:
            return jsonify({'success': False, 'error': 'Missing params'}), 400
        safe_new_name = sanitize_user_filename(new_name)
        if not safe_new_name:
            return jsonify({'success': False, 'error': 'Invalid name'}), 400
        new_path = resolve_user_path(session['username'], os.path.join(os.path.dirname(old_path), safe_new_name))
        os.rename(old_path, new_path)
        log_activity(session['username'], 'server.file.rename', f'{old_path} → {new_path}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/file/install', methods=['POST'])
@login_required
def install_deps_api():
    try:
        d = request.json or {}
        safe_filename = sanitize_user_filename(d.get('filename', ''))
        base_path = resolve_user_path(session['username'], d.get('path', '') or get_user_path(session['username']))
        filepath = resolve_user_path(session['username'], os.path.join(base_path, safe_filename))
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        result = auto_install_dependencies(filepath)
        return jsonify({'success': True, 'installed': result.get('installed', []), 'failed': result.get('failed', [])})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/delete', methods=['POST'])
@login_required
def delete_file_api():
    d = request.json
    p = d['path']
    if not is_path_allowed(session['username'], p):
        return jsonify({'success': False}), 403
    return jsonify({'success': False, 'error': 'File deletion is disabled'}), 403

@app.route('/api/files/content')
@login_required
def get_file_content():
    p = request.args.get('path')
    if not p:
        return jsonify({'success': False}), 403
    try:
        p = resolve_user_path(session['username'], p)
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            log_activity(session['username'], 'server.file.read', p)
            return jsonify({'content': f.read()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/save', methods=['POST'])
@login_required
def save_file_api():
    try:
        d = request.json or {}
        path = d.get('path', '')
        if not path:
            return jsonify({'success': False, 'error': 'No path provided'}), 400
        path = resolve_user_path(session['username'], path)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(d.get('content', ''))
        log_activity(session['username'], 'server.file.write', path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ----- تشغيل/إيقاف الملفات -----
@app.route('/api/file/run', methods=['POST'])
@login_required
def run_file_api():
    d = request.json or {}
    safe_filename = sanitize_user_filename(d.get('filename',''))
    base_path = resolve_user_path(session['username'], d.get('path','') or get_user_path(session['username']))
    filepath = resolve_user_path(session['username'], os.path.join(base_path, safe_filename))
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'File not found'})
    if safe_filename.lower().endswith('.zip'):
        extract_dir = resolve_user_path(session['username'], os.path.join(base_path, safe_filename.replace('.zip', '')))
        os.makedirs(extract_dir, exist_ok=True)
        main = extract_and_find_main(filepath, extract_dir)
        if main:
            filepath = main
        else:
            return jsonify({'success': False, 'error': 'Main file not found'})
    installed = auto_install_dependencies(filepath)
    cmd = get_run_command(filepath)
    assigned = get_user_assigned_port(session['username'])
    run_port = assigned if assigned else get_next_free_port()
    try:
        kwargs = dict(shell=True, cwd=os.path.dirname(filepath),
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT, text=True, bufsize=1)
        env = os.environ.copy()
        env['PORT'] = str(run_port)
        kwargs['env'] = env
        if hasattr(os, 'setsid'):
            kwargs['preexec_fn'] = os.setsid
        p = subprocess.Popen(cmd, **kwargs)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    pid = f"{session['username']}_{safe_filename or 'f'}_{int(time.time())}"
    file_processes[pid] = {'process': p, 'filename': safe_filename, 'username': session['username'], 'output': [], 'port': run_port}
    threading.Thread(target=read_process_output, args=(pid, p), kwargs={'store': file_processes}, daemon=True).start()
    log_activity(session['username'], 'server.file.run', f"{safe_filename} ({pid}) on {run_port}")
    return jsonify({'success': True, 'process_id': pid, 'installed_result': installed, 'port': run_port})

@app.route('/api/file/stop', methods=['POST'])
@login_required
def stop_file_api():
    pid = (request.json or {}).get('process_id')
    if pid in file_processes:
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(file_processes[pid]['process'].pid), signal.SIGKILL)
            else:
                file_processes[pid]['process'].kill()
        except Exception:
            pass
        log_activity(session['username'], 'server.file.stop', pid)
        del file_processes[pid]
    return jsonify({'success': True})

@app.route('/api/file/output/<pid>')
@login_required
def get_file_output_api(pid):
    if pid in file_processes:
        info = file_processes[pid]
        return jsonify({
            'success': True,
            'output': info.get('output', []),
            'is_running': info['process'].poll() is None
        })
    return jsonify({'success': False})

@app.route('/api/file/input', methods=['POST'])
@login_required
def send_file_input_api():
    d = request.json or {}
    pid = d.get('process_id')
    if pid in file_processes:
        try:
            file_processes[pid]['process'].stdin.write(d.get('input','') + '\n')
            file_processes[pid]['process'].stdin.flush()
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': True})

@app.route('/api/file/running')
@login_required
def get_running_files_api():
    user    = session['username']
    running = []
    dead    = []
    for pid, info in file_processes.items():
        if info['username'] == user or user == MASTER_USERNAME:
            if info['process'].poll() is None:
                running.append({'process_id': pid, 'filename': info['filename'], 'username': info['username']})
            else:
                dead.append(pid)
    for d in dead:
        file_processes.pop(d, None)
    return jsonify({'success': True, 'running': running})

# ----- تنفيذ أوامر -----
@app.route('/api/exec', methods=['POST'])
@login_required
def execute_command_api():
    if session.get('username') != MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Terminal access is restricted to the owner'}), 403
    d = request.json
    cmd = d['command']
    cwd = d.get('cwd', get_user_path(session['username']))
    log_activity(session['username'], 'server.exec', cmd[:120])
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=60)
        return jsonify({'output': r.stdout + r.stderr, 'success': True})
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout (60s)', 'success': False})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False})

# ----- العمليات -----
@app.route('/api/process/start', methods=['POST'])
@login_required
def start_process_api():
    if session.get('username') != MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Custom process start is restricted to the owner'}), 403
    d = request.json
    def run():
        kwargs = dict(shell=True, cwd=d.get('cwd', BASE_PATH))
        if hasattr(os, 'setsid'):
            kwargs['preexec_fn'] = os.setsid
        p = subprocess.Popen(d['command'], **kwargs)
        running_processes[d['name']] = {'process': p, 'owner': session.get('username'), 'command': d['command']}
        p.wait()
    threading.Thread(target=run, daemon=True).start()
    log_activity(session['username'], 'server.process.start', d.get('name',''))
    return jsonify({'success': True})

@app.route('/api/process/stop', methods=['POST'])
@login_required
def stop_process_api():
    n = request.json['name']
    if n in running_processes:
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(running_processes[n]['process'].pid), signal.SIGKILL)
            else:
                running_processes[n]['process'].kill()
        except Exception:
            pass
        del running_processes[n]
    log_activity(session['username'], 'server.process.stop', n)
    return jsonify({'success': True})

@app.route('/api/process/stop-all', methods=['POST'])
@login_required
def stop_all_processes_api():
    for p in list(running_processes.values()):
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(p['process'].pid), signal.SIGKILL)
            else:
                p['process'].kill()
        except Exception:
            pass
    running_processes.clear()
    return jsonify({'success': True})

@app.route('/api/process/list')
@login_required
def list_processes_api():
    procs = {}
    for n, i in running_processes.items():
        procs[n] = {'status': 'running' if i['process'].poll() is None else 'stopped', 'command': i['command']}
    return jsonify(procs)

# ----- شبكة / بورتات متعددة (Replit-friendly) -----
@app.route('/api/network/scan', methods=['POST'])
@login_required
def scan_ports_api():
    d = request.json
    out = []
    for p in d.get('ports', []):
        try:
            s = socket.socket()
            s.settimeout(1)
            r = s.connect_ex((d['host'], int(p)))
            out.append({'port': p, 'open': r == 0})
            s.close()
        except Exception:
            out.append({'port': p, 'open': False})
    return jsonify({'results': out})

@app.route('/api/ports/list')
@login_required
def list_ports_api():
    return jsonify({'ports': load_ports()})

@app.route('/api/ports/add', methods=['POST'])
@master_required
def add_port_api():
    d = request.json
    try:
        port = int(d.get('port', 0))
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid port'})
    if port <= 0 or port > 65535:
        return jsonify({'success': False, 'error': 'Invalid port range'})
    ports = load_ports()
    if any(p.get('port') == port for p in ports):
        return jsonify({'success': False, 'error': 'Port already exists'})
    ports.append({'port': port, 'note': d.get('note', ''), 'status': 'idle', 'created': datetime.now().isoformat()})
    save_ports(ports)
    log_activity(session['username'], 'server.port.add', str(port))
    return jsonify({'success': True})

@app.route('/api/ports/delete', methods=['POST'])
@master_required
def del_port_api():
    port = (request.json or {}).get('port')
    ports = [p for p in load_ports() if p.get('port') != port]
    save_ports(ports)
    log_activity(session['username'], 'server.port.delete', str(port))
    return jsonify({'success': True})

# ----- مستخدمي اللوحة -----
@app.route('/api/users/list')
@master_required
def list_panel_users_api():
    users = load_users()
    sessions = load_user_sessions()
    return jsonify({'users': [
        {
            'username': u,
            'max_sessions': users[u].get('max_sessions', 999) if isinstance(users[u], dict) else 999,
            'active_sessions': sessions.get(u, 0),
            'expiry': users[u].get('expiry') if isinstance(users[u], dict) else None,
            'created': users[u].get('created') if isinstance(users[u], dict) else None,
            'vip': users[u].get('vip', False) if isinstance(users[u], dict) else False,
            'banned': users[u].get('banned', False) if isinstance(users[u], dict) else False,
            'assigned_port': users[u].get('assigned_port') if isinstance(users[u], dict) else None,
        }
        for u in users
    ]})

@app.route('/api/users/add', methods=['POST'])
@master_required
def add_panel_user_api():
    try:
        d = request.json or {}
        username = (d.get('username') or '').strip()
        password = d.get('password') or ''
        if not username:
            return jsonify({'success': False, 'error': 'اسم المستخدم مطلوب'})
        if not password:
            return jsonify({'success': False, 'error': 'كلمة المرور مطلوبة'})
        users = load_users()
        if username in users:
            return jsonify({'success': False, 'error': 'اسم المستخدم موجود مسبقاً'})
        assigned_port = get_assigned_port_for_new_user()
        users[username] = {
            'password': hashlib.sha256(password.encode()).hexdigest(),
            'max_sessions': int(d.get('max_sessions') or 999),
            'created': datetime.now().isoformat(),
            'expiry': d.get('expiry') or None,
            'vip': bool(d.get('vip', False)),
            'banned': False,
            'assigned_port': assigned_port,
        }
        save_users(users)
        os.makedirs(os.path.join(USERS_FOLDER, username), exist_ok=True)
        log_activity(session['username'], 'server.user.add', username)
        return jsonify({'success': True, 'assigned_port': assigned_port})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/update', methods=['POST'])
@master_required
def update_panel_user_api():
    d = request.json or {}
    username = d.get('username')
    users = load_users()
    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    ud = users[username] if isinstance(users[username], dict) else {}
    if 'vip' in d:
        ud['vip'] = bool(d['vip'])
    if 'banned' in d:
        ud['banned'] = bool(d['banned'])
    if 'expiry' in d:
        ud['expiry'] = d['expiry'] or None
    if 'max_sessions' in d:
        ud['max_sessions'] = int(d['max_sessions'])
    if 'new_username' in d and d['new_username'] and d['new_username'] != username:
        new_u = d['new_username']
        if new_u in users:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        users[new_u] = ud
        del users[username]
        old_path = os.path.join(USERS_FOLDER, username)
        new_path = os.path.join(USERS_FOLDER, new_u)
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
        log_activity(session['username'], 'server.user.rename', f'{username} → {new_u}')
    else:
        users[username] = ud
    save_users(users)
    log_activity(session['username'], 'server.user.update', str(d))
    return jsonify({'success': True})

@app.route('/api/users/delete', methods=['POST'])
@master_required
def delete_panel_user_api():
    try:
        d = request.json or {}
        username = (d.get('username') or '').strip()
        if not username:
            return jsonify({'success': False, 'error': 'اسم المستخدم مطلوب'})
        users = load_users()
        if username in users:
            del users[username]
            save_users(users)
            user_folder = os.path.join(USERS_FOLDER, username)
            if os.path.exists(user_folder):
                shutil.rmtree(user_folder, ignore_errors=True)
            log_activity(session['username'], 'server.user.delete', username)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ----- الجدولة -----
@app.route('/api/schedules/list')
@login_required
def list_schedules_api():
    return jsonify({'schedules': list(load_schedules().values())})

@app.route('/api/schedules/add', methods=['POST'])
@login_required
def add_schedule_api():
    try:
        d = request.json or {}
        name = (d.get('name') or '').strip()
        command = (d.get('command') or '').strip()
        if not name or not command:
            return jsonify({'success': False, 'error': 'الاسم والأمر مطلوبان'})
        sch = load_schedules()
        sid = str(uuid.uuid4())[:8]
        sch[sid] = {'id': sid, 'name': name, 'command': command, 'schedule': d.get('schedule', '* * * * *'), 'owner': session['username']}
        save_schedules(sch)
        log_activity(session['username'], 'server.schedule.add', name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ----- النسخ -----
@app.route('/api/backups/list')
@master_required
def list_backups_api():
    backs = []
    if os.path.exists(BACKUPS_FOLDER):
        for f in os.listdir(BACKUPS_FOLDER):
            if f.endswith('.tar.gz'):
                backs.append({'name': f, 'size': f"{os.path.getsize(os.path.join(BACKUPS_FOLDER, f))/1024**2:.2f} MB"})
    return jsonify({'backups': backs})

@app.route('/api/backups/create', methods=['POST'])
@master_required
def create_backup_api():
    name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    try:
        with tarfile.open(os.path.join(BACKUPS_FOLDER, name), 'w:gz') as tar:
            for root, dirs, files in os.walk(BASE_PATH):
                rel_root = os.path.relpath(root, BASE_PATH)
                if rel_root == '.':
                    rel_root = ''
                for fname in files:
                    if fname in ('users.json', 'user_sessions.json'):
                        continue
                    full = os.path.join(root, fname)
                    arc = os.path.join('backup', rel_root, fname)
                    tar.add(full, arcname=arc)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    log_activity(session['username'], 'server.backup.create', name)
    return jsonify({'success': True})

# ----- الحزم -----
@app.route('/api/packages/list')
@master_required
def list_packages_api():
    return jsonify(load_packages())

@app.route('/api/packages/install/pip', methods=['POST'])
@master_required
def install_pip_api():
    pkg = request.json['package']
    subprocess.run([sys.executable, '-m', 'pip', 'install', pkg], capture_output=True)
    pkgs = load_packages()
    if pkg not in pkgs.get('pip', []):
        pkgs.setdefault('pip', []).append(pkg)
        save_packages(pkgs)
    log_activity(session['username'], 'server.package.install', pkg)
    return jsonify({'success': True})

# ----- Docker -----
@app.route('/api/docker/list')
@master_required
def list_docker_api():
    out = []
    try:
        r = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}|{{.Status}}'],
                           capture_output=True, text=True)
        for line in (r.stdout or '').strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 2:
                    out.append({'name': parts[0], 'status': parts[1]})
    except Exception:
        pass
    return jsonify({'containers': out})

@app.route('/api/docker/run', methods=['POST'])
@master_required
def run_docker_api():
    d = request.json
    cmd = ['docker', 'run', '-d']
    if d.get('name'): cmd.extend(['--name', d['name']])
    if d.get('ports'):
        for p in d['ports'].split(','):
            cmd.extend(['-p', p.strip()])
    cmd.append(d['image'])
    subprocess.run(cmd, capture_output=True)
    return jsonify({'success': True})

# ----- الإشعارات -----
@app.route('/api/notifications')
@login_required
def get_notifications_api():
    username = session['username']
    data = load_notifications()
    notifs = data.get(username, [])
    result = {'notifications': notifs}
    if username == MASTER_USERNAME:
        users = load_users()
        result['all_users'] = list(users.keys())
    return jsonify(result)

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read_api():
    try:
        username = session['username']
        d = request.json or {}
        data = load_notifications()
        notifs = data.get(username, [])
        if d.get('all'):
            for n in notifs:
                n['read'] = True
        else:
            nid = d.get('id')
            for n in notifs:
                if n.get('id') == nid:
                    n['read'] = True
                    break
        data[username] = notifs
        save_notifications(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/master/notify', methods=['POST'])
@master_required
def send_notification_api():
    try:
        d = request.json or {}
        title = (d.get('title') or '').strip()
        message = (d.get('message') or '').strip()
        notif_type = d.get('type', 'info')
        target = d.get('target', '__all__')
        if not title or not message:
            return jsonify({'success': False, 'error': 'العنوان والرسالة مطلوبان'})
        users = load_users()
        if target == '__all__':
            targets = list(users.keys())
        else:
            targets = [target] if target in users else []
        for u in targets:
            add_notification(u, title, message, notif_type)
        log_activity(session['username'], 'notify.send', f"→ {target}: {title}")
        return jsonify({'success': True, 'count': len(targets)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ----- السجلات -----
@app.route('/api/logs')
@master_required
def get_logs_api():
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            return jsonify({'logs': f.read()[-50000:]})
    return jsonify({'logs': ''})

@app.route('/api/logs/clear', methods=['POST'])
@master_required
def clear_logs_api():
    with open(LOGS_FILE, 'w') as f:
        f.write(f"[{datetime.now()}] CLEARED\n")
    save_json_file(ACTIVITY_FILE, {'events': []})
    return jsonify({'success': True})

# ----- إعدادات المالك -----
@app.route('/api/master/change-username', methods=['POST'])
@master_required
def change_master_username_api():
    global MASTER_USERNAME
    MASTER_USERNAME = request.json['new_username']
    MASTER_CONFIG['master_username'] = MASTER_USERNAME
    save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
    return jsonify({'success': True})

@app.route('/api/master/change-password', methods=['POST'])
@master_required
def change_master_password_api():
    global MASTER_PASSWORD_HASH
    d = request.json
    if hashlib.sha256(d['current_password'].encode()).hexdigest() == MASTER_PASSWORD_HASH:
        MASTER_PASSWORD_HASH = hashlib.sha256(d['new_password'].encode()).hexdigest()
        MASTER_CONFIG['master_password_hash'] = MASTER_PASSWORD_HASH
        save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/master/change-port', methods=['POST'])
@master_required
def change_port_api():
    try:
        port = int((request.json or {}).get('port', 3278))
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid port'})
    MASTER_CONFIG['port'] = port
    save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
    threading.Thread(target=lambda: (time.sleep(1), os.execv(sys.executable, [sys.executable] + sys.argv))).start()
    return jsonify({'success': True})

@app.route('/api/master/restart', methods=['POST'])
@master_required
def restart_panel_api():
    log_activity(session['username'], 'server.power.restart', 'Panel restart requested')
    threading.Thread(target=lambda: (time.sleep(1), os.execv(sys.executable, [sys.executable] + sys.argv))).start()
    return jsonify({'success': True})

@app.route('/api/master/maintenance', methods=['GET'])
@login_required
def get_maintenance_api():
    return jsonify({
        'maintenance_mode': MASTER_CONFIG.get('maintenance_mode', False),
        'maintenance_message': MASTER_CONFIG.get('maintenance_message', '')
    })

@app.route('/api/master/maintenance', methods=['POST'])
@master_required
def set_maintenance_api():
    d = request.json or {}
    MASTER_CONFIG['maintenance_mode'] = bool(d.get('maintenance_mode', False))
    MASTER_CONFIG['maintenance_message'] = d.get('maintenance_message', MASTER_CONFIG.get('maintenance_message', ''))
    save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
    log_activity(session['username'], 'server.maintenance', f"Maintenance: {MASTER_CONFIG['maintenance_mode']}")
    return jsonify({'success': True})

@app.route('/maintenance')
def maintenance_page():
    msg = MASTER_CONFIG.get('maintenance_message', 'الموقع في صيانة مؤقتة.')
    return render_template_string(MAINTENANCE_TEMPLATE, message=msg)


# =============================================================================
# 14)  ميزة Multi-Port: تشغيل Sub-servers على بورتات إضافية
# =============================================================================
def run_extra_port(port, note=""):
    """يشغل Flask sub-server على بورت إضافي يقدم نفس اللوحة."""
    try:
        from flask import Flask as _F
        sub = _F(f"sub_{port}")
        @sub.route('/')
        def _h():
            return f"<h1 style='font-family:sans-serif;color:#29c7d3;background:#1f2933;padding:40px;text-align:center'>XcT x— Port {port}</h1><p style='color:#9aa9b3;text-align:center'>{html.escape(note)}</p><p style='text-align:center'><a style='color:#2f6fed' href='/'>Open user app here</a></p>"
        sub.run(host='0.0.0.0', port=port, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        print(f"[port {port}] failed: {e}")

def start_configured_extra_ports():
    for p in load_ports():
        try:
            threading.Thread(target=run_extra_port, args=(int(p['port']), p.get('note','')), daemon=True).start()
        except Exception:
            pass

# =============================================================================
# 15)  Reverse Proxy — /proxy/<port>/<subpath>
# =============================================================================
@app.route('/proxy/<int:port>/', defaults={'subpath': ''})
@app.route('/proxy/<int:port>/<path:subpath>')
@login_required
def proxy_user_port(port, subpath):
    username = session.get('username')
    if username != MASTER_USERNAME:
        assigned = get_user_assigned_port(username)
        if not assigned or int(assigned) != port:
            return "<h2 style='font-family:sans-serif;color:#e53935;padding:40px'>403 — غير مسموح بالوصول لهذا البورت</h2>", 403
    target_url = f"http://127.0.0.1:{port}/{subpath}"
    qs = request.query_string.decode()
    if qs:
        target_url += '?' + qs
    try:
        skip_headers = {'host', 'content-length', 'transfer-encoding', 'connection'}
        fwd_headers = {k: v for k, v in request.headers if k.lower() not in skip_headers}
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=fwd_headers,
            data=request.get_data(),
            allow_redirects=False,
            timeout=30,
            stream=True,
        )
        excluded = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
        out_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        return Response(resp.content, resp.status_code, out_headers)
    except Exception as e:
        return f"<div style='font-family:sans-serif;padding:40px;background:#1f2933;color:#e53935'><h2>🔴 التطبيق غير شغال على البورت {port}</h2><p style='color:#9aa9b3'>تأكد أن ملفك يعمل ويستخدم <b>PORT={port}</b></p><small style='color:#5a6a74'>{html.escape(str(e))}</small></div>", 502

# =============================================================================
# التشغيل الرئيسي
# =============================================================================
if __name__ == '__main__':
    print(r"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🔥 VeNoM ULTIMATE — Lunes Host LLC Style Panel 🔥              ║
║   ˣᶜᵀ × 𝑽𝒆𝑵𝒐𝑴 𝑻𝒆𝒂𝑴                                              ║
║                                                                  ║
║   Master  : {mu:<48} ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""".format(mu=MASTER_USERNAME))

    # شغّل بورتات إضافية إن وُجدت
    start_configured_extra_ports()
    port = int(os.environ.get('PORT', MASTER_CONFIG.get('port') or 3278))
    print(f"🌐 Panel: http://0.0.0.0:{port}")
    print(f"   Login: {MASTER_USERNAME} / @xAyOuB (default)")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)