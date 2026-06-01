import os
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from functools import wraps

import requests
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)

DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "bot_data.db")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

def _safe_int(value, default):
    try:
        return int(str(value).strip())
    except Exception:
        return default

def _normalize_username(value: str) -> str:
    value = (value or "").strip()
    return value[1:] if value.startswith("@") else value

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "XcT-x-TeaM-BoT-iS-BesT")
SECRET_KEY = os.getenv("SECRET_KEY", "xct-x-team-panel-secret-key")
OWNER_ID = _safe_int(os.getenv("OWNER_ID", "8695276303"), 8695276303)
OWNER_USERNAME = _normalize_username(os.getenv("OWNER_USERNAME", "XcT_xAyOuB"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "@XcT_x_HostinG_BoT")

app = Flask(__name__)
app.secret_key = SECRET_KEY

class BotState:
    process = None
    started_at = None
    status = "stopped"
    lock = threading.Lock()

bot_state = BotState()

def db_conn():
    return sqlite3.connect(DB_PATH, timeout=30)

def db_query(sql, params=(), one=False):
    try:
        with db_conn() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            if one:
                return rows[0] if rows else None
            return rows
    except Exception as exc:
        print(f"[DB] {exc}")
        return None if one else []

def get_stats():
    def q(sql, default=0):
        try:
            with db_conn() as conn:
                row = conn.execute(sql).fetchone()
                return row[0] if row and row[0] is not None else default
        except Exception:
            return default

    return {
        "users_total": q("SELECT COUNT(*) FROM users"),
        "users_active": q("SELECT COUNT(*) FROM users WHERE banned=0"),
        "users_banned": q("SELECT COUNT(*) FROM users WHERE banned=1"),
        "users_admins": q("SELECT COUNT(*) FROM users WHERE is_admin=1"),
        "files_total": q("SELECT COUNT(*) FROM files"),
        "files_pending": q("SELECT COUNT(*) FROM files WHERE status='pending'"),
        "files_approved": q("SELECT COUNT(*) FROM files WHERE status='approved'"),
        "files_rejected": q("SELECT COUNT(*) FROM files WHERE status='rejected'"),
        "files_running": q("SELECT COUNT(*) FROM files WHERE running=1"),
        "channels": q("SELECT COUNT(*) FROM channels"),
    }

def get_users(limit=200, offset=0):
    rows = db_query(
        "SELECT id, username, first, last, joined, banned, is_admin "
        "FROM users ORDER BY joined DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) or []
    data = []
    for r in rows:
        data.append(
            {
                "user_id": r[0],
                "username": (r[1] or "").lstrip("@"),
                "first_name": r[2] or "",
                "last_name": r[3] or "",
                "joined_at": str(r[4] or ""),
                "is_banned": bool(r[5]),
                "is_admin": bool(r[6]),
                "avatar_url": f"/api/users/{r[0]}/avatar",
            }
        )
    return data

def _derive_file_log_path(file_row):
    if not file_row:
        return None
    cont_id = file_row[9] if len(file_row) > 9 else None
    if cont_id:
        candidate = os.path.join(LOGS_DIR, f"{str(cont_id)[:12]}.log")
        if os.path.exists(candidate):
            return candidate

    stored_name = file_row[2] if len(file_row) > 2 else ""
    if stored_name:
        prefix = os.path.splitext(stored_name)[0][:12]
        candidate = os.path.join(LOGS_DIR, f"{prefix}.log")
        if os.path.exists(candidate):
            return candidate
    return None

def get_file_row(fid):
    return db_query("SELECT * FROM files WHERE id=?", (fid,), one=True)

def get_file_logs(fid, lines=120):
    file_row = get_file_row(fid)
    if not file_row:
        return None, "الملف غير موجود"
    log_path = _derive_file_log_path(file_row)
    if not log_path:
        return "", "لا يوجد ملف لوجز لهذا العنصر حالياً"
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
            return "".join(handle.readlines()[-lines:]), None
    except Exception as exc:
        return "", f"تعذر قراءة اللوجز: {exc}"

def get_files(limit=200):
    rows = db_query(
        "SELECT id, user_id, filename, orig_name, filepath, size, ftype, uploaded, status, cont_id, port, running "
        "FROM files ORDER BY uploaded DESC LIMIT ?",
        (limit,),
    ) or []
    data = []
    for r in rows:
        log_path = _derive_file_log_path(r)
        data.append(
            {
                "id": r[0],
                "user_id": r[1],
                "filename": r[2] or "",
                "orig_name": r[3] or r[2] or "",
                "filepath": r[4] or "",
                "size": int(r[5] or 0),
                "file_type": r[6] or "",
                "created_at": str(r[7] or ""),
                "status": r[8] or "unknown",
                "container_id": r[9] or "",
                "port": r[10],
                "is_running": bool(r[11]),
                "can_download": bool(r[4] and os.path.exists(r[4])),
                "has_logs": bool(log_path and os.path.exists(log_path)),
            }
        )
    return data

def get_admins():
    rows = db_query(
        "SELECT id, username, first FROM users WHERE is_admin=1 ORDER BY joined DESC"
    ) or []
    return [
        {
            "user_id": r[0],
            "username": (r[1] or "").lstrip("@"),
            "first_name": r[2] or "",
        }
        for r in rows
    ]

def get_active_user_ids():
    rows = db_query("SELECT id FROM users WHERE banned=0") or []
    return [row[0] for row in rows]

def start_bot_process():
    with bot_state.lock:
        if bot_state.process and bot_state.process.poll() is None:
            return False, "البوت يعمل بالفعل"
        bot_state.status = "starting"
        try:
            log_path = os.path.join(LOGS_DIR, "bot_runtime.log")
            log_file = open(log_path, "a", buffering=1, encoding="utf-8")
            log_file.write(f"\n\n===== Bot started at {datetime.utcnow().isoformat()} =====\n")
            env = os.environ.copy()
            env["WEB_PANEL_MODE"] = "1"
            bot_state.process = subprocess.Popen(
                ["python", "-u", "bot.py"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=os.setsid,
            )
            bot_state.started_at = datetime.utcnow().isoformat()
            bot_state.status = "running"
            return True, "تم تشغيل البوت بنجاح"
        except Exception as exc:
            bot_state.status = "stopped"
            return False, f"فشل تشغيل البوت: {exc}"

def stop_bot_process():
    with bot_state.lock:
        if not bot_state.process or bot_state.process.poll() is not None:
            bot_state.status = "stopped"
            return False, "البوت متوقف بالفعل"
        bot_state.status = "stopping"
        try:
            os.killpg(os.getpgid(bot_state.process.pid), signal.SIGTERM)
            try:
                bot_state.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(bot_state.process.pid), signal.SIGKILL)
            bot_state.process = None
            bot_state.status = "stopped"
            return True, "تم إيقاف البوت"
        except Exception as exc:
            bot_state.status = "stopped"
            return False, f"تعذر الإيقاف: {exc}"

def bot_is_running():
    if bot_state.process and bot_state.process.poll() is None:
        return True
    if bot_state.status == "running":
        bot_state.status = "stopped"
    return False

def send_broadcast(message_text):
    if not BOT_TOKEN:
        return {"success": 0, "failed": 0, "total": 0, "error": "BOT_TOKEN غير مضبوط"}
    text = f"📢 <b>رسالة من الإدارة</b>\n\n{message_text}\n\n👑 @{OWNER_USERNAME}"
    success = 0
    failed = 0
    user_ids = get_active_user_ids()
    for uid in user_ids:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": uid, "text": text, "parse_mode": "HTML"},
                timeout=12,
            )
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code == 200 and payload.get("ok"):
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        time.sleep(0.05)
    return {"success": success, "failed": failed, "total": len(user_ids)}

def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper

def _placeholder_avatar_svg(label: str):
    chars = (label or "U")[:2].upper()
    svg = f.strip()
    return Response(svg, mimetype="image/svg+xml")

def _fetch_avatar_binary(uid: int):
    if not BOT_TOKEN:
        return None
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos",
            params={"user_id": uid, "limit": 1},
            timeout=12,
        )
        data = resp.json()
        if not data.get("ok") or not data.get("result", {}).get("photos"):
            return None
        photos = data["result"]["photos"][0]
        photo = photos[-1]
        file_resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": photo["file_id"]},
            timeout=12,
        )
        file_data = file_resp.json()
        if not file_data.get("ok"):
            return None
        file_path = file_data["result"].get("file_path")
        if not file_path:
            return None
        bin_resp = requests.get(
            f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
            timeout=20,
        )
        if bin_resp.status_code != 200:
            return None
        return {
            "content": bin_resp.content,
            "content_type": bin_resp.headers.get("content-type", "image/jpeg"),
        }
    except Exception:
        return None

LOGIN_HTML = 

DASHBOARD_HTML = 

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        error = 'كلمة المرور غير صحيحة'
    return render_template_string(LOGIN_HTML, error=error, bot_username=BOT_USERNAME, owner_username=OWNER_USERNAME)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@require_login
def dashboard():
    return render_template_string(
        DASHBOARD_HTML,
        bot_username=BOT_USERNAME,
        owner_username=OWNER_USERNAME,
        owner_id=OWNER_ID,
    )

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'bot': bot_state.status, 'time': datetime.utcnow().isoformat()})

@app.route('/ping')
def ping():
    return 'pong'

@app.route('/api/status')
@require_login
def api_status():
    running = bot_is_running()
    uptime = ''
    if running and bot_state.started_at:
        try:
            delta = datetime.utcnow() - datetime.fromisoformat(bot_state.started_at)
            seconds = int(delta.total_seconds())
            hours, rem = divmod(seconds, 3600)
            minutes, sec = divmod(rem, 60)
            uptime = f'{hours}س {minutes}د {sec}ث'
        except Exception:
            uptime = ''
    return jsonify({'status': bot_state.status, 'running': running, 'started_at': bot_state.started_at, 'uptime': uptime})

@app.route('/api/stats')
@require_login
def api_stats():
    return jsonify(get_stats())

@app.route('/api/users')
@require_login
def api_users():
    return jsonify(get_users())

@app.route('/api/users/<int:uid>/avatar')
@require_login
def api_user_avatar(uid):
    row = db_query('SELECT username, first, last FROM users WHERE id=?', (uid,), one=True)
    label = 'U'
    if row:
        username = (row[0] or '').strip().lstrip('@')
        first = (row[1] or '').strip()
        last = (row[2] or '').strip()
        label = username[:2] or (first[:1] + last[:1]).strip() or first[:2] or 'U'
    avatar = _fetch_avatar_binary(uid)
    if avatar:
        return Response(avatar['content'], mimetype=avatar['content_type'])
    return _placeholder_avatar_svg(label)

@app.route('/api/files')
@require_login
def api_files():
    return jsonify(get_files())

@app.route('/api/files/<int:fid>/download')
@require_login
def api_file_download(fid):
    row = get_file_row(fid)
    if not row:
        abort(404)
    path = row[4]
    download_name = row[3] or row[2] or f'file-{fid}'
    if not path or not os.path.exists(path):
        return jsonify({'ok': False, 'message': 'الملف غير موجود على الخادم'}), 404
    return send_file(path, as_attachment=True, download_name=download_name)

@app.route('/api/files/<int:fid>/logs')
@require_login
def api_file_logs(fid):
    log, error = get_file_logs(fid)
    if log is None:
        return jsonify({'ok': False, 'message': error or 'الملف غير موجود'}), 404
    return jsonify({'ok': True, 'log': log or '', 'message': error or ''})

@app.route('/api/admins')
@require_login
def api_admins():
    return jsonify(get_admins())

@app.route('/api/users/<int:uid>/ban', methods=['POST'])
@require_login
def api_ban(uid):
    try:
        with db_conn() as conn:
            conn.execute('UPDATE users SET banned=1 WHERE id=?', (uid,))
            conn.commit()
        return jsonify({'ok': True, 'message': f'تم حظر المستخدم {uid}'})
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 500

@app.route('/api/users/<int:uid>/unban', methods=['POST'])
@require_login
def api_unban(uid):
    try:
        with db_conn() as conn:
            conn.execute('UPDATE users SET banned=0 WHERE id=?', (uid,))
            conn.commit()
        return jsonify({'ok': True, 'message': f'تم فك حظر المستخدم {uid}'})
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 500

@app.route('/api/broadcast', methods=['POST'])
@require_login
def api_broadcast():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'الرسالة فارغة'}), 400
    return jsonify({'ok': True, 'result': send_broadcast(message)})

@app.route('/api/bot/start', methods=['POST'])
@require_login
def api_bot_start():
    ok, message = start_bot_process()
    return jsonify({'ok': ok, 'message': message})

@app.route('/api/bot/stop', methods=['POST'])
@require_login
def api_bot_stop():
    ok, message = stop_bot_process()
    return jsonify({'ok': ok, 'message': message})

@app.route('/api/logs')
@require_login
def api_logs():
    path = os.path.join(LOGS_DIR, 'bot_runtime.log')
    if not os.path.exists(path):
        return jsonify({'log': '(لا يوجد سجل بعد)'})
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
            return jsonify({'log': handle.read()[-20000:]})
    except Exception as exc:
        return jsonify({'log': f'خطأ أثناء قراءة السجل: {exc}'})

@app.route('/api/settings')
@require_login
def api_get_settings():
    return jsonify({
        'ok': True,
        'data': {
            'BOT_TOKEN': BOT_TOKEN,
            'BOT_USERNAME': BOT_USERNAME,
            'OWNER_ID': str(OWNER_ID),
            'OWNER_USERNAME': OWNER_USERNAME,
            'ADMIN_PASSWORD': ADMIN_PASSWORD
        }
    })

@app.route('/api/settings', methods=['POST'])
@require_login
def api_save_settings():
    global BOT_TOKEN, BOT_USERNAME, OWNER_ID, OWNER_USERNAME, ADMIN_PASSWORD

    data = request.get_json(silent=True) or {}

    bot_token = (data.get('BOT_TOKEN') or '').strip()
    bot_username = (data.get('BOT_USERNAME') or '').strip()
    owner_id = (data.get('OWNER_ID') or '').strip()
    owner_username = (data.get('OWNER_USERNAME') or '').strip()
    admin_password = (data.get('ADMIN_PASSWORD') or '').strip()

    if not all([bot_token, bot_username, owner_id, owner_username, admin_password]):
        return jsonify({'ok': False, 'error': 'جميع الحقول مطلوبة'}), 400

    try:
        owner_id_int = int(owner_id)
    except ValueError:
        return jsonify({'ok': False, 'error': 'OWNER_ID يجب أن يكون رقما'}), 400

    env_content = f

    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)

        BOT_TOKEN = bot_token
        BOT_USERNAME = bot_username
        OWNER_ID = owner_id_int
        OWNER_USERNAME = owner_username
        ADMIN_PASSWORD = admin_password

        stop_bot_process()
        time.sleep(1)
        start_bot_process()

        return jsonify({
            'ok': True,
            'message': 'تم حفظ الإعدادات وإعادة تشغيل البوت'
        })
    except Exception as exc:
        return jsonify({'ok': False, 'error': f'خطأ: {str(exc)}'}), 500

def auto_start_bot():
    time.sleep(3)
    print('[Panel] Auto-starting bot...')
    ok, msg = start_bot_process()
    print(f'[Panel] {msg}')

if __name__ == '__main__':
    port = int(os.getenv('PORT', '10000'))
    threading.Thread(target=auto_start_bot, daemon=True).start()
    try:
        from keepalive import start_keepalive
        start_keepalive()
    except Exception as exc:
        print(f'[KeepAlive] failed: {exc}')
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)