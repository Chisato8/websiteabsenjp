import os, time, csv, sqlite3, zipfile, io, secrets, requests, subprocess, json
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session, abort, jsonify

# tambahan untuk monitoring
try:
    import psutil
except Exception:
    psutil = None

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(16))

DB = "absensi.db"
ADMIN_PASS = os.environ.get("ADMIN_PASS", "rikyganteng")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ===================================================
# INIT DB + TRIGGER ANTI DOUBLE (SAMA HARI)
# ===================================================
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
    cur.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_no_duplicate_same_day'")
    if not cur.fetchone():
        cur.execute("""
        CREATE TRIGGER trg_no_duplicate_same_day
        BEFORE INSERT ON attendance
        WHEN (SELECT COUNT(*) FROM attendance WHERE nama=NEW.nama AND date(waktu)=date(NEW.waktu)) > 0
        BEGIN
            SELECT RAISE(ABORT, 'duplicate_same_day');
        END;
        """)
    conn.commit()
    conn.close()

init_db()

# ===================================================
# ANTI SPAM
# ===================================================
RATE = {}
MIN_INTERVAL = 5  # detik

# ===================================================
# TELEGRAM
# ===================================================
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        return r.ok
    except:
        return False

# ===================================================
# HALAMAN UTAMA ABSENSI
# ===================================================
@app.route("/", methods=["GET", "POST"])
def index():
    ip = request.remote_addr or "unknown"
    now = time.time()

    last = RATE.get(ip, 0)
    if request.method == "POST":
        if now - last < MIN_INTERVAL:
            flash("Terlalu cepat. Tunggu beberapa detik.")
            return redirect(url_for("index"))

        RATE[ip] = now

        # HONEYPOT
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
        try:
            cur.execute("INSERT INTO attendance (nama,kelas,status,waktu,ip) VALUES (?,?,?,?,?)",
                        (nama, kelas, status, waktu, ip))
            conn.commit()
            inserted = True
        except sqlite3.IntegrityError:
            inserted = False
        except Exception:
            conn.close()
            flash("Terjadi kesalahan saat menyimpan absensi.")
            return redirect(url_for("index"))

        conn.close()

        if inserted:
            if status.lower() in ("sakit", "izin", "alpa", "absent", "tidak hadir"):
                send_telegram_message(f"[ABSENSI] {nama} | {kelas} | {status} | {waktu}")
            flash("Absensi terkirim!")
        else:
            flash("Kamu sudah absen hari ini (tidak akan duplikat).")

        return redirect(url_for("index"))

    return render_template("index.html")

# ===================================================
# LOGIN ADMIN
# ===================================================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("pass", "")
        if pw == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Password salah")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

def require_admin():
    if not session.get("admin"):
        abort(403)

# ===================================================
# ADMIN PANEL
# ===================================================
@app.route("/admin")
def admin():
    require_admin()
    return render_template("admin.html")

# ===================================================
# GET ALL DATA
# ===================================================
@app.route("/get-all")
def get_all():
    require_admin()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id,nama,kelas,status,waktu,ip FROM attendance ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    data = [
        {"id": r[0], "nama": r[1], "kelas": r[2], "status": r[3], "waktu": r[4], "ip": r[5]}
        for r in rows
    ]
    return jsonify({"data": data})

# ===================================================
# STREAM REALTIME
# ===================================================
@app.route("/stream")
def stream():
    def event_stream():
        last_id = 0
        while True:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("SELECT id,nama,kelas,status,waktu,ip FROM attendance ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            conn.close()

            if row and row[0] != last_id:
                last_id = row[0]
                yield f"data:{json.dumps({'id':row[0],'nama':row[1],'kelas':row[2],'status':row[3],'waktu':row[4],'ip':row[5]})}\n\n"
            time.sleep(1)

    return app.response_class(event_stream(), mimetype="text/event-stream")

# ===================================================
# MONITOR
# ===================================================
@app.route("/monitor")
def monitor():
    require_admin()
    cpu = psutil.cpu_percent() if psutil else 0
    ram = psutil.virtual_memory().percent if psutil else 0
    try:
        out = subprocess.check_output(["ping", "-c", "1", "google.com"], stderr=subprocess.STDOUT, universal_newlines=True)
        if "time=" in out:
            ms = out.split("time=")[1].split(" ")[0]
        else:
            ms = "0"
    except:
        ms = "0"
    return jsonify({"cpu": cpu, "ram": ram, "ping": ms})

# ===================================================
# EXPORT CSV
# ===================================================
@app.route("/export-csv")
def export_csv():
    require_admin()
    si = io.StringIO()
    cw = csv.writer(si)

    cw.writerow(["ID","Nama","Kelas","Status","Waktu","IP"])

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    for r in cur.execute("SELECT id,nama,kelas,status,waktu,ip FROM attendance ORDER BY id"):
        cw.writerow(list(r))
    conn.close()

    mem = io.BytesIO()
    mem.write(si.getvalue().encode())
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="absensi_jepang.csv")

# ===================================================
# EXPORT ZIP
# ===================================================
@app.route("/export-zip")
def export_zip():
    require_admin()
    si = io.StringIO()
    cw = csv.writer(si)

    cw.writerow(["ID","Nama","Kelas","Status","Waktu","IP"])

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    for r in cur.execute("SELECT id,nama,kelas,status,waktu,ip FROM attendance ORDER BY id"):
        cw.writerow(list(r))
    conn.close()

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("absensi_jepang.csv", si.getvalue())
        z.writestr("manifest.txt", f"Created {time.strftime('%Y-%m-%d %H:%M:%S')}\nBy Riky Ernanto")
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="absensi_jepang.zip")

# ===================================================
# DOWNLOAD BACKUP DB
# ===================================================
@app.route("/download-db")
def download_db():
    require_admin()
    if os.path.exists(DB):
        return send_file(DB, as_attachment=True, download_name=DB)
    abort(404)

# ===================================================
# 404 PAGE (INI YANG KAMU MINTA)
# ===================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# ===================================================
# RUN
# ===================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
