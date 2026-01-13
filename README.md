# Absensi Eskul Jepang — Lightweight Responsive Flask App
Dibuat oleh: Riky Ernanto

Fitur:
- Tampilan responsive (mobile/tablet/desktop)
- Ringan, cocok untuk Termux / HP
- Anti-spam (rate limit), honeypot field
- Export CSV / ZIP (dapat diunduh dari admin)
- Notifikasi Telegram (opsional) via env vars
- Admin login sederhana (PASSWORD via ADMIN_PASS env var)

Cara pakai singkat:
1. Ekstrak ZIP.
2. (Opsional) buat virtualenv: `python -m venv venv && source venv/bin/activate`
3. Install: `pip install flask requests`
4. Siapkan environment variables (recommended):
   - `FLASK_SECRET` (optional)
   - `ADMIN_PASS` (default: admin123 — ubah ini sebelum produksi)
   - `TELEGRAM_TOKEN` (jika mau notifikasi)
   - `TELEGRAM_CHAT_ID` (jika mau notifikasi)
5. Jalankan: `python app.py`
6. Buka `http://127.0.0.1:8080/` untuk form, `http://127.0.0.1:8080/login` untuk admin.

**PENTING**: Jangan masukkan token Telegram ke dalam ZIP jika kamu bagikan ke orang lain. Simpan token di environment atau file lokal yang tidak dibagikan.
