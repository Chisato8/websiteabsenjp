import os, time, csv, sqlite3, zipfile, io, secrets, json
import requests
from flask import (
    Flask, render_template, request, redirect,
    url_for, send_file, flash, session, abort, jsonify
)

# =============================
# APP INIT
# =============================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(16))

# =============================
# DATABASE (VERCEL SAFE)
# =============================
DB = "/tmp/absensi.db"   # WAJIB /tmp di Vercel
ADMIN_PASS = os.environ.get("ADMIN_PASS", "rikyganteng")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# =============================
# INIT DB
# =============================
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT,
            kelas TEXT,
            status TEXT,
            waktu TEXT,
            ip TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =============================
# TELEGRAM
# =============================
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=5
        )
    except:
        pass

# =============================
# ANTI SPAM
# =============================
RATE = {}
MIN_INTERVAL = 5

# =============================
# INDEX / ABSENSI
# =============================
@app.route("/", methods=["GET", "POST"])
def index():
    ip = request.remote_addr or "unknown"
    now = time.time()

    if request.method == "POST":
        if now - RATE.get(ip, 0) < MIN_INTERVAL:
            flash("Terlalu cepat, tunggu sebentar.")
            return redirect(url_for("index"))
        RATE[ip] = now

        # honeypot
        if request.form.get("hp_field"):
            return ("", 204)

        nama = request.form.get("nama", "").strip()
        kelas = request.form.get("kelas", "").strip()
        status = request.form.get("status", "").strip()

        if not nama:
            flash("Nama wajib diisi.")
            return redirect(url_for("index"))

        waktu = time.strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO attendance (nama,kelas,status,waktu,ip) VALUES (?,?,?,?,?)",
            (nama, kelas, status, waktu, ip)
        )
        conn.commit()
        conn.close()

        if status.lower() in ("sakit", "izin", "alpa"):
            send_telegram_message(
                f"[ABSENSI]\n{nama} | {kelas} | {status} | {waktu}"
            )

        flash("Absensi berhasil!")
        return redirect(url_for("index"))

    return render_template("index.html")

# =============================
# LOGIN ADMIN
# =============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("pass") == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Password salah")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

def require_admin():
    if not session.get("admin"):
        abort(403)

# =============================
# ADMIN PANEL
# =============================
@app.route("/admin")
def admin():
    require_admin()
    return render_template("admin.html")

# =============================
# GET DATA
# =============================
@app.route("/get-all")
def get_all():
    require_admin()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM attendance ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    data = [
        {"id": r[0], "nama": r[1], "kelas": r[2], "status": r[3], "waktu": r[4], "ip": r[5]}
        for r in rows
    ]
    return jsonify(data)

# =============================
# EXPORT CSV
# =============================
@app.route("/export-csv")
def export_csv():
    require_admin()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID","Nama","Kelas","Status","Waktu","IP"])

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    for r in cur.execute("SELECT * FROM attendance"):
        cw.writerow(r)
    conn.close()

    mem = io.BytesIO()
    mem.write(si.getvalue().encode())
    mem.seek(0)

    return send_file(mem, as_attachment=True, download_name="absensi.csv")

# =============================
# EXPORT ZIP
# =============================
@app.route("/export-zip")
def export_zip():
    require_admin()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID","Nama","Kelas","Status","Waktu","IP"])

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    for r in cur.execute("SELECT * FROM attendance"):
        cw.writerow(r)
    conn.close()

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("absensi.csv", si.getvalue())
    mem.seek(0)

    return send_file(mem, as_attachment=True, download_name="absensi.zip")

# =============================
# 404
# =============================
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404
