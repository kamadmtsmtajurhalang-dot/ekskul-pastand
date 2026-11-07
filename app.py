import os
import math
import csv
import io
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, session, Response, flash, send_from_directory
)
from database import get_db, init_db

# Zona Waktu Indonesia Barat (WIB = UTC+7) untuk Tajurhalang Bogor
WIB = timezone(timedelta(hours=7))

def get_wib_datetime():
    return datetime.now(WIB)

def get_wib_today_str():
    return datetime.now(WIB).strftime('%Y-%m-%d')

def get_wib_time_str():
    return datetime.now(WIB).strftime('%H:%M')

NAMA_BULAN = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}

NAMA_HARI = {
    0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis',
    4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'
}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'presensi-ekskul-tajurhalang-multi-role-2026'

# Inisialisasi basis data jika belum ada
init_db()

# =========================================================
# HELPER & AUTH DECORATORS
# =========================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash("Anda tidak memiliki hak akses ke halaman tersebut.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def haversine(lat1, lon1, lat2, lon2):
    """Formula Haversine untuk menghitung jarak GPS dalam meter."""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def get_pengaturan_laporan(conn=None):
    """Mengambil konfigurasi pejabat penandatangan laporan (Kamad, Bendahara, Staf TU, Waka Kesiswaan)."""
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True
    row = conn.execute("SELECT * FROM pengaturan_laporan ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        conn.execute("""
        INSERT INTO pengaturan_laporan (
            nama_kamad, nbm_kamad, jabatan_kamad,
            nama_bendahara, nbm_bendahara, jabatan_bendahara,
            nama_staff_tu, nbm_staff_tu, jabatan_staff_tu,
            nama_waka_kesiswaan, nbm_waka_kesiswaan, jabatan_waka_kesiswaan,
            kota_tanda_tangan
        ) VALUES (
            'H. E. Samsul Rizal, S.Ag., M.Pd.', 'NBM. 1089234', 'Kepala MTs Muhammadiyah Tajurhalang',
            'Hj. Siti Rohmah, S.E.', 'NBM. 1120455', 'Bendahara Madrasah',
            'Ahmad Syarifudin, S.Kom.', 'NBM. 1198302', 'Staf Tata Usaha',
            'Mulyadi, S.Pd.', 'NBM. 1054321', 'Waka Kesiswaan MTs Muhammadiyah',
            'Tajurhalang'
        )
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM pengaturan_laporan ORDER BY id DESC LIMIT 1").fetchone()
    if close_after:
        conn.close()
    return dict(row) if row else {}

# =========================================================
# PWA (PROGRESSIVE WEB APP) ROUTES
# =========================================================

@app.route('/sw.js')
def service_worker():
    response = send_from_directory('static', 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/manifest.json')
def manifest():
    response = send_from_directory('static', 'manifest.json')
    response.headers['Content-Type'] = 'application/manifest+json'
    return response

# =========================================================
# AUTHENTICATION ROUTES (LOGIN / LOGOUT / REGISTER SISWA)
# =========================================================

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'pelatih':
        return redirect(url_for('pelatih_dashboard'))
    elif role == 'siswa':
        return redirect(url_for('siswa_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nama'] = user['nama']
            session['role'] = user['role']
            session['ekskul_id'] = user['ekskul_id']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'pelatih':
                return redirect(url_for('pelatih_dashboard'))
            else:
                return redirect(url_for('siswa_dashboard'))
        else:
            flash("Username atau kata sandi salah. Silakan coba lagi.", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Anda telah berhasil keluar.", "info")
    return redirect(url_for('login'))

@app.route('/lupa-password', methods=['GET', 'POST'])
def lupa_password():
    """Form pengajuan lupa password / lupa akun bagi siswa & pelatih"""
    if request.method == 'POST':
        identitas = request.form.get('identitas', '').strip()
        role = request.form.get('role', 'siswa').strip()
        keterangan = request.form.get('keterangan', '').strip()

        if not identitas:
            flash("Silakan masukkan username atau nama lengkap Anda.", "danger")
            return redirect(url_for('lupa_password'))

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(nama) = LOWER(?) LIMIT 1",
                            (identitas, identitas)).fetchone()

        user_id = user['id'] if user else None
        target_username = user['username'] if user else identitas
        target_nama = user['nama'] if user else identitas
        target_role = user['role'] if user else role

        conn.execute("""
        INSERT INTO reset_password_requests (user_id, username, nama, role, keterangan)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, target_username, target_nama, target_role, keterangan))
        conn.commit()
        conn.close()

        flash("Permohonan reset password Anda berhasil dikirim ke Admin Master! Silakan hubungi Guru/Admin Madrasah.", "success")
        return redirect(url_for('login'))

    return render_template('lupa_password.html')

@app.route('/register-siswa', methods=['GET', 'POST'])
def register_siswa():
    conn = get_db()
    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    
    if request.method == 'POST':
        master_siswa_id = request.form.get('master_siswa_id')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        ekskul_id = request.form.get('ekskul_id')

        if not master_siswa_id or not username or not password or not confirm_password or not ekskul_id:
            flash("Semua kolom (Tingkat Kelas, Nama Siswa, Cabang Ekskul, Username, Kata Sandi, dan Konfirmasi Kata Sandi) wajib diisi!", "danger")
        elif password != confirm_password:
            flash("Kata sandi dan konfirmasi kata sandi tidak cocok! Pastikan kedua kolom kata sandi sama persis untuk menghindari kesalahan pengetikan.", "danger")
        else:
            # Validasi data pokok siswa dari master_siswa
            m_siswa = conn.execute("SELECT * FROM master_siswa WHERE id = ?", (master_siswa_id,)).fetchone()
            if not m_siswa:
                flash("Data siswa tidak ditemukan dalam Database Siswa MTs Muhammadiyah Tajurhalang.", "danger")
            elif m_siswa['user_id'] is not None:
                flash(f"Siswa atas nama '{m_siswa['nama']}' sudah pernah membuat akun login. Setiap siswa hanya dapat membuat 1 akun.", "danger")
            else:
                # Periksa apakah username sudah terpakai
                user_check = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                if user_check:
                    flash(f"Username '{username}' sudah digunakan oleh pengguna lain. Silakan gunakan username berbeda.", "danger")
                else:
                    try:
                        cursor = conn.cursor()
                        # Buat user baru dengan nama, kelas, jenis kelamin, dan NIS resmi dari master_siswa
                        cursor.execute("""
                        INSERT INTO users (username, password, nama, role, ekskul_id, kelas, jenis_kelamin, nisn, no_hp)
                        VALUES (?, ?, ?, 'siswa', ?, ?, ?, ?, ?)
                        """, (username, password, m_siswa['nama'], ekskul_id, m_siswa['kelas'], m_siswa['jenis_kelamin'], m_siswa['nis'], m_siswa['no_whatsapp']))
                        new_user_id = cursor.lastrowid
                        
                        # Tautkan user_id ke tabel master_siswa agar nama ini terkunci dan tidak bisa didaftarkan lagi
                        cursor.execute("""
                        UPDATE master_siswa SET user_id = ? WHERE id = ?
                        """, (new_user_id, master_siswa_id))

                        # Masukkan ke relasi siswa_ekskul dengan status MENUNGGU persetujuan pelatih
                        cursor.execute("""
                        INSERT INTO siswa_ekskul (user_id, ekskul_id, status) VALUES (?, ?, 'MENUNGGU')
                        """, (new_user_id, ekskul_id))
                        
                        conn.commit()
                        conn.close()
                        flash(f"Pendaftaran akun atas nama '{m_siswa['nama']}' berhasil! Pendaftaran ekskul Anda sedang menunggu persetujuan Pelatih. Silakan masuk.", "success")
                        return redirect(url_for('login'))
                    except Exception as e:
                        conn.rollback()
                        flash(f"Pendaftaran gagal: {e}", "danger")
    
    # Ambil siswa master yang BELUM punya akun login (user_id IS NULL)
    master_siswa_rows = conn.execute("""
    SELECT id, nis, nama, kelas, jenis_kelamin, no_whatsapp 
    FROM master_siswa 
    WHERE user_id IS NULL 
    ORDER BY kelas ASC, nama ASC
    """).fetchall()
    
    master_siswa_list = [dict(row) for row in master_siswa_rows]
    conn.close()
    return render_template('register_siswa.html', ekskul_list=ekskul_list, master_siswa_list=master_siswa_list)

# =========================================================
# 1. AKUN PELATIH (CLEAN UI & KHUSUS EKSKULNYA SAJA)
# =========================================================

def get_pelatih_context(pelatih_id, active_ekskul_id=None):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (pelatih_id,)).fetchone()
    
    assigned_ekskuls = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN pelatih_ekskul pe ON e.id = pe.ekskul_id
    WHERE pe.user_id = ?
    ORDER BY e.nama ASC
    """, (pelatih_id,)).fetchall()

    if not assigned_ekskuls and user['ekskul_id']:
        assigned_ekskuls = conn.execute("SELECT * FROM ekskul WHERE id = ?", (user['ekskul_id'],)).fetchall()

    if not assigned_ekskuls:
        return conn, user, [], None, 0, 0, 0

    if not active_ekskul_id:
        active_ekskul_id = request.args.get('ekskul_id', type=int)

    ekskul = None
    if active_ekskul_id:
        for e in assigned_ekskuls:
            if e['id'] == active_ekskul_id:
                ekskul = e
                break
    if not ekskul:
        ekskul = assigned_ekskuls[0]

    assigned_ids = [e['id'] for e in assigned_ekskuls]
    placeholders = ','.join(['?'] * len(assigned_ids))

    # Total calon siswa menunggu persetujuan pelatih (di seluruh ekskul yang diampu)
    pending_row = conn.execute(f"""
    SELECT COUNT(*) as cnt FROM siswa_ekskul se
    JOIN users u ON se.user_id = u.id
    WHERE se.ekskul_id IN ({placeholders}) AND se.status = 'MENUNGGU'
    """, assigned_ids).fetchone()
    total_pending = pending_row['cnt'] if pending_row else 0

    # Total permohonan izin / sakit siswa yang menunggu persetujuan pelatih (di seluruh ekskul yang diampu)
    izin_row = conn.execute(f"""
    SELECT COUNT(*) as cnt FROM pengajuan_izin
    WHERE ekskul_id IN ({placeholders}) 
      AND status_approval = 'MENUNGGU'
      AND status_pengajuan IN ('Izin', 'Sakit')
    """, assigned_ids).fetchone()
    total_izin = izin_row['cnt'] if izin_row else 0

    # Total anggota siswa aktif di ekskul yang sedang aktif dibuka
    aktif_row = conn.execute("""
    SELECT COUNT(*) as cnt FROM siswa_ekskul se
    JOIN users u ON se.user_id = u.id
    WHERE se.ekskul_id = ? AND u.role = 'siswa' AND se.status = 'AKTIF'
    """, (ekskul['id'],)).fetchone()
    total_siswa_aktif = aktif_row['cnt'] if aktif_row else 0

    return conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif

@app.route('/pelatih')
@role_required('pelatih')
def pelatih_dashboard():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini. Silakan hubungi Admin Master.", 400

    now_wib = get_wib_datetime()
    today_str = get_wib_today_str()
    hari_str = NAMA_HARI.get(now_wib.weekday(), '')
    today_formatted = f"{hari_str}, {now_wib.day} {NAMA_BULAN.get(now_wib.month, '')} {now_wib.year}"

    # Cek apakah sudah ada sesi presensi hari ini
    sesi_hari_ini = conn.execute("""
    SELECT * FROM sesi_latihan WHERE ekskul_id = ? AND tanggal = ?
    """, (ekskul['id'], today_str)).fetchone()

    # Jadwal terdekat dan materi pelatihan dari silabus jika ada
    sesi_count = conn.execute("""
    SELECT COUNT(*) as cnt FROM sesi_latihan 
    WHERE ekskul_id = ? AND tanggal LIKE ?
    """, (ekskul['id'], f"{now_wib.year:04d}-{now_wib.month:02d}%")).fetchone()['cnt']
    next_ptm = sesi_count + 1

    materi_row = conn.execute("""
    SELECT lmm.materi, lmm.pertemuan_ke FROM laporan_materi_mingguan lmm
    JOIN laporan_bulanan lb ON lmm.laporan_id = lb.id
    WHERE lb.ekskul_id = ? AND lb.bulan = ? AND lb.tahun = ? AND lmm.pertemuan_ke >= ?
    ORDER BY lmm.pertemuan_ke ASC LIMIT 1
    """, (ekskul['id'], now_wib.month, now_wib.year, next_ptm)).fetchone()

    if not materi_row:
        materi_row = conn.execute("""
        SELECT lmm.materi, lmm.pertemuan_ke FROM laporan_materi_mingguan lmm
        JOIN laporan_bulanan lb ON lmm.laporan_id = lb.id
        WHERE lb.ekskul_id = ? AND lb.bulan = ? AND lb.tahun = ?
        ORDER BY lmm.pertemuan_ke ASC LIMIT 1
        """, (ekskul['id'], now_wib.month, now_wib.year)).fetchone()

    materi_terdekat = f"Pertemuan {materi_row['pertemuan_ke']}: {materi_row['materi']}" if materi_row else (ekskul['deskripsi'] or 'Latihan reguler mingguan')

    # Pengumuman / Info dari Admin Master (berupa angka & daftar)
    pengumuman_admin_rows = conn.execute("""
    SELECT * FROM pengumuman 
    WHERE tipe = 'admin' AND (target_role IN ('pelatih', 'semua'))
    ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    pengumuman_admin_list = [dict(p) for p in pengumuman_admin_rows]
    total_pengumuman_admin = len(pengumuman_admin_list)

    # Pengumuman / pengingat yang pernah dikirim oleh pelatih ke siswa ekskul ini
    pengumuman_pelatih_rows = conn.execute("""
    SELECT * FROM pengumuman
    WHERE tipe = 'pelatih' AND ekskul_id = ?
    ORDER BY created_at DESC LIMIT 5
    """, (ekskul['id'],)).fetchall()
    pengumuman_pelatih_list = [dict(p) for p in pengumuman_pelatih_rows]

    conn.close()
    return render_template('pelatih_dashboard.html',
                           active_menu='dashboard',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           today_str=today_str,
                           today_formatted=today_formatted,
                           sesi_hari_ini=sesi_hari_ini,
                           materi_terdekat=materi_terdekat,
                           total_pengumuman_admin=total_pengumuman_admin,
                           pengumuman_admin_list=pengumuman_admin_list,
                           pengumuman_pelatih_list=pengumuman_pelatih_list)

@app.route('/pelatih/presensi')
@role_required('pelatih')
def pelatih_presensi():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini. Silakan hubungi Admin Master.", 400

    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()

    # Ambil daftar siswa resmi aktif yang mengikuti ekskul ini
    siswa_list = conn.execute("""
    SELECT u.* FROM users u
    JOIN siswa_ekskul se ON u.id = se.user_id
    WHERE se.ekskul_id = ? AND u.role = 'siswa' AND se.status = 'AKTIF'
    ORDER BY u.kelas ASC, u.nama ASC
    """, (ekskul['id'],)).fetchall()

    today_str = get_wib_today_str()
    pengajuan_izin = conn.execute("""
    SELECT p.*, u.nama as nama_siswa, u.kelas 
    FROM pengajuan_izin p
    JOIN users u ON p.user_id = u.id
    WHERE p.ekskul_id = ? AND p.tanggal_latihan = ?
    ORDER BY p.created_at DESC
    """, (ekskul['id'], today_str)).fetchall()

    now_wib = get_wib_datetime()
    curr_bulan = now_wib.month
    curr_tahun = now_wib.year

    # Cari rencana silabus materi bulanan
    silabus_rows = conn.execute("""
    SELECT lmm.*, lb.bulan, lb.tahun, lb.status_rencana
    FROM laporan_materi_mingguan lmm
    JOIN laporan_bulanan lb ON lmm.laporan_id = lb.id
    WHERE lb.ekskul_id = ? AND lb.bulan = ? AND lb.tahun = ?
    ORDER BY lmm.pertemuan_ke ASC
    """, (ekskul['id'], curr_bulan, curr_tahun)).fetchall()

    silabus_periode = f"{NAMA_BULAN.get(curr_bulan, '')} {curr_tahun}"
    is_silabus_fallback = False

    if not silabus_rows:
        silabus_rows = conn.execute("""
        SELECT lmm.*, lb.bulan, lb.tahun, lb.status_rencana
        FROM laporan_materi_mingguan lmm
        JOIN laporan_bulanan lb ON lmm.laporan_id = lb.id
        WHERE lb.ekskul_id = ?
        ORDER BY lb.tahun DESC, lb.bulan DESC, lmm.pertemuan_ke ASC
        """, (ekskul['id'],)).fetchall()
        if silabus_rows:
            is_silabus_fallback = True
            silabus_periode = f"{NAMA_BULAN.get(silabus_rows[0]['bulan'], '')} {silabus_rows[0]['tahun']} (Terbaru)"

    silabus_list = [dict(s) for s in silabus_rows]

    # Hitung sesi yang telah terlaksana bulan ini untuk rekomendasi pertemuan
    sesi_bulan_count = conn.execute("""
    SELECT COUNT(*) as cnt FROM sesi_latihan
    WHERE ekskul_id = ? AND tanggal LIKE ?
    """, (ekskul['id'], f"{curr_tahun:04d}-{curr_bulan:02d}%")).fetchone()['cnt']
    recommended_ptm = sesi_bulan_count + 1

    conn.close()
    return render_template('pelatih_presensi.html', 
                           active_menu='presensi',
                           user=user, 
                           ekskul=ekskul, 
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           lokasi=lokasi, 
                           siswa_list=siswa_list,
                           pengajuan_izin=pengajuan_izin,
                           today_str=today_str,
                           silabus_list=silabus_list,
                           silabus_periode=silabus_periode,
                           is_silabus_fallback=is_silabus_fallback,
                           recommended_ptm=recommended_ptm)

@app.route('/api/pelatih/silabus')
@role_required('pelatih')
def api_pelatih_silabus():
    pelatih_id = session['user_id']
    ekskul_id = request.args.get('ekskul_id', type=int)
    tanggal = request.args.get('tanggal', '').strip()

    now_wib = get_wib_datetime()
    bulan = now_wib.month
    tahun = now_wib.year

    if tanggal:
        try:
            parts = tanggal.split('-')
            if len(parts) >= 2:
                tahun = int(parts[0])
                bulan = int(parts[1])
        except Exception:
            pass

    conn = get_db()
    # Verifikasi hak akses pelatih atas ekskul ini
    assigned = conn.execute("""
    SELECT * FROM pelatih_ekskul WHERE user_id = ? AND ekskul_id = ?
    """, (pelatih_id, ekskul_id)).fetchone()

    if not assigned and session.get('role') != 'admin':
        conn.close()
        return jsonify({'status': 'ERROR', 'pesan': 'Akses tidak diizinkan'}), 403

    silabus_rows = conn.execute("""
    SELECT lmm.id, lmm.pertemuan_ke, lmm.tanggal_rencana, lmm.materi, lmm.indikator_ketercapaian,
           lb.bulan, lb.tahun, lb.status_rencana
    FROM laporan_materi_mingguan lmm
    JOIN laporan_bulanan lb ON lmm.laporan_id = lb.id
    WHERE lb.ekskul_id = ? AND lb.bulan = ? AND lb.tahun = ?
    ORDER BY lmm.pertemuan_ke ASC
    """, (ekskul_id, bulan, tahun)).fetchall()

    is_fallback = False
    nama_periode = f"{NAMA_BULAN.get(bulan, '')} {tahun}"

    if not silabus_rows:
        silabus_rows = conn.execute("""
        SELECT lmm.id, lmm.pertemuan_ke, lmm.tanggal_rencana, lmm.materi, lmm.indikator_ketercapaian,
               lb.bulan, lb.tahun, lb.status_rencana
        FROM laporan_materi_mingguan lmm
        JOIN laporan_bulanan lb ON lmm.laporan_id = lb.id
        WHERE lb.ekskul_id = ?
        ORDER BY lb.tahun DESC, lb.bulan DESC, lmm.pertemuan_ke ASC
        """, (ekskul_id,)).fetchall()
        if silabus_rows:
            is_fallback = True
            nama_periode = f"{NAMA_BULAN.get(silabus_rows[0]['bulan'], '')} {silabus_rows[0]['tahun']} (Terbaru)"

    sesi_count = conn.execute("""
    SELECT COUNT(*) as cnt FROM sesi_latihan
    WHERE ekskul_id = ? AND tanggal LIKE ?
    """, (ekskul_id, f"{tahun:04d}-{bulan:02d}%")).fetchone()['cnt']
    recommended_ptm = sesi_count + 1

    conn.close()

    return jsonify({
        'status': 'SUCCESS',
        'bulan': bulan,
        'tahun': tahun,
        'nama_periode': nama_periode,
        'is_fallback': is_fallback,
        'recommended_ptm': recommended_ptm,
        'silabus': [dict(r) for r in silabus_rows]
    })

@app.route('/pelatih/laporan-pekan-terakhir')
@role_required('pelatih')
def pelatih_pekan_terakhir():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)

    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    now_wib = get_wib_datetime()
    current_year = now_wib.year
    selected_bulan = request.args.get('bulan', type=int) or now_wib.month
    selected_tahun = request.args.get('tahun', type=int) or current_year

    if selected_bulan < 1 or selected_bulan > 12:
        selected_bulan = now_wib.month

    month_prefix = f"{selected_tahun:04d}-{selected_bulan:02d}"

    # Sesi latihan pekan terakhir (tanggal 22 s/d akhir bulan)
    sesi_rows = conn.execute("""
    SELECT s.*,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
    FROM sesi_latihan s
    WHERE s.ekskul_id = ? AND s.tanggal LIKE ? AND CAST(substr(s.tanggal, 9, 2) AS INTEGER) >= 22
    ORDER BY s.tanggal ASC, s.jam_mulai ASC
    """, (ekskul['id'], f"{month_prefix}%")).fetchall()
    
    # Jika belum ada di tanggal >= 22 tapi ada sesi di bulan itu, ambil 2 sesi penutup terakhir
    if not sesi_rows:
        sesi_rows = conn.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
        FROM sesi_latihan s
        WHERE s.ekskul_id = ? AND s.tanggal LIKE ?
        ORDER BY s.tanggal DESC, s.jam_mulai DESC LIMIT 2
        """, (ekskul['id'], f"{month_prefix}%")).fetchall()
        sesi_rows = list(reversed(sesi_rows))

    sesi_pekan_terakhir = [dict(s) for s in sesi_rows]

    # Hitung rata-rata kehadiran pekan terakhir
    total_hadir_sum = sum(s['total_hadir'] for s in sesi_pekan_terakhir)
    total_peserta_sum = sum(s['total_peserta'] for s in sesi_pekan_terakhir)
    persen_hadir_pekan_terakhir = (total_hadir_sum / total_peserta_sum * 100) if total_peserta_sum > 0 else 0.0

    # Cek laporan bulanan
    laporan = conn.execute("""
    SELECT * FROM laporan_bulanan WHERE ekskul_id = ? AND bulan = ? AND tahun = ?
    """, (ekskul['id'], selected_bulan, selected_tahun)).fetchone()

    conn.close()
    return render_template('pelatih_pekan_terakhir.html',
                           active_menu='pekan_terakhir',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           sesi_pekan_terakhir=sesi_pekan_terakhir,
                           persen_hadir_pekan_terakhir=persen_hadir_pekan_terakhir,
                           laporan=laporan,
                           list_bulan=NAMA_BULAN,
                           nama_bulan=NAMA_BULAN.get(selected_bulan, ''),
                           selected_bulan=selected_bulan,
                           selected_tahun=selected_tahun,
                           current_year=current_year)

@app.route('/pelatih/pengumuman/kirim', methods=['POST'])
@role_required('pelatih')
def pelatih_kirim_pengumuman():
    pelatih_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id', type=int)
    isi = request.form.get('isi_pengumuman', '').strip()

    if not isi:
        flash("Isi pesan pengingat tidak boleh kosong.", "danger")
        return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

    conn = get_db()
    conn.execute("""
    INSERT INTO pengumuman (tipe, pengirim_id, ekskul_id, judul, isi, target_role)
    VALUES ('pelatih', ?, ?, 'Pengingat dari Pelatih', ?, 'siswa')
    """, (pelatih_id, ekskul_id, isi))
    conn.commit()
    conn.close()

    flash("Pesan pengingat berhasil dikirim ke dashboard seluruh siswa ekskul ini!", "success")
    return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

@app.route('/pelatih/pengumuman/hapus/<int:pengumuman_id>', methods=['POST'])
@role_required('pelatih')
def pelatih_hapus_pengumuman(pengumuman_id):
    pelatih_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id', type=int)

    conn = get_db()
    conn.execute("DELETE FROM pengumuman WHERE id = ? AND pengirim_id = ?", (pengumuman_id, pelatih_id))
    conn.commit()
    conn.close()

    flash("Pengumuman / pengingat berhasil ditarik/dihapus.", "success")
    return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

@app.route('/pelatih/persetujuan')
@role_required('pelatih')
def pelatih_persetujuan():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    pending_siswa = conn.execute("""
    SELECT se.id as se_id, se.tanggal_daftar, se.status,
           u.id as user_id, u.nama, u.username, u.kelas, u.jenis_kelamin,
           e.nama as nama_ekskul, e.icon as icon_ekskul
    FROM siswa_ekskul se
    JOIN users u ON se.user_id = u.id
    JOIN ekskul e ON se.ekskul_id = e.id
    WHERE se.ekskul_id = ? AND se.status = 'MENUNGGU'
    ORDER BY se.tanggal_daftar DESC
    """, (ekskul['id'],)).fetchall()

    riwayat_persetujuan = conn.execute("""
    SELECT se.id as se_id, se.tanggal_daftar, se.status,
           u.id as user_id, u.nama, u.username, u.kelas, u.jenis_kelamin,
           e.nama as nama_ekskul, e.icon as icon_ekskul
    FROM siswa_ekskul se
    JOIN users u ON se.user_id = u.id
    JOIN ekskul e ON se.ekskul_id = e.id
    WHERE se.ekskul_id = ? AND se.status != 'MENUNGGU'
    ORDER BY se.tanggal_daftar DESC LIMIT 15
    """, (ekskul['id'],)).fetchall()

    conn.close()
    return render_template('pelatih_persetujuan.html',
                           active_menu='persetujuan',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           pending_siswa=pending_siswa,
                           riwayat_persetujuan=riwayat_persetujuan)

@app.route('/pelatih/persetujuan/<int:se_id>/approve', methods=['POST'])
@role_required('pelatih')
def pelatih_approve_siswa(se_id):
    ekskul_id = request.form.get('ekskul_id', type=int)
    conn = get_db()
    
    se = conn.execute("""
    SELECT se.*, u.nama as nama_siswa 
    FROM siswa_ekskul se
    JOIN users u ON se.user_id = u.id
    WHERE se.id = ?
    """, (se_id,)).fetchone()
    
    if not se:
        conn.close()
        flash("Data pendaftaran tidak ditemukan.", "danger")
        return redirect(url_for('pelatih_persetujuan', ekskul_id=ekskul_id))

    conn.execute("UPDATE siswa_ekskul SET status = 'AKTIF' WHERE id = ?", (se_id,))
    conn.execute("UPDATE users SET ekskul_id = ? WHERE id = ? AND ekskul_id IS NULL", (se['ekskul_id'], se['user_id']))
    conn.commit()
    conn.close()

    flash(f"Berhasil! Siswa '{se['nama_siswa']}' telah disetujui dan resmi menjadi anggota ekskul. Siswa kini masuk database dan siap mengikuti presensi latihan.", "success")
    return redirect(url_for('pelatih_persetujuan', ekskul_id=ekskul_id or se['ekskul_id']))

@app.route('/pelatih/persetujuan/<int:se_id>/reject', methods=['POST'])
@role_required('pelatih')
def pelatih_reject_siswa(se_id):
    ekskul_id = request.form.get('ekskul_id', type=int)
    conn = get_db()
    
    se = conn.execute("""
    SELECT se.*, u.nama as nama_siswa 
    FROM siswa_ekskul se
    JOIN users u ON se.user_id = u.id
    WHERE se.id = ?
    """, (se_id,)).fetchone()
    
    if not se:
        conn.close()
        flash("Data pendaftaran tidak ditemukan.", "danger")
        return redirect(url_for('pelatih_persetujuan', ekskul_id=ekskul_id))

    conn.execute("UPDATE siswa_ekskul SET status = 'DITOLAK' WHERE id = ?", (se_id,))
    conn.commit()
    conn.close()

    flash(f"Pendaftaran siswa '{se['nama_siswa']}' telah ditolak.", "info")
    return redirect(url_for('pelatih_persetujuan', ekskul_id=ekskul_id or se['ekskul_id']))

@app.route('/pelatih/siswa')
@role_required('pelatih')
def pelatih_siswa():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    siswa_list = conn.execute("""
    SELECT u.*, se.id as se_id, se.tanggal_daftar,
           (SELECT COUNT(*) FROM presensi_siswa ps 
            JOIN sesi_latihan sl ON ps.sesi_id = sl.id 
            WHERE ps.user_id = u.id AND sl.ekskul_id = ? AND ps.status_kehadiran = 'Hadir') as total_hadir,
           (SELECT COUNT(*) FROM presensi_siswa ps 
            JOIN sesi_latihan sl ON ps.sesi_id = sl.id 
            WHERE ps.user_id = u.id AND sl.ekskul_id = ?) as total_sesi
    FROM users u
    JOIN siswa_ekskul se ON u.id = se.user_id
    WHERE se.ekskul_id = ? AND u.role = 'siswa' AND se.status = 'AKTIF'
    ORDER BY u.kelas ASC, u.nama ASC
    """, (ekskul['id'], ekskul['id'], ekskul['id'])).fetchall()

    total_laki = sum(1 for s in siswa_list if s['jenis_kelamin'] == 'L')
    total_perempuan = sum(1 for s in siswa_list if s['jenis_kelamin'] == 'P')

    conn.close()
    return render_template('pelatih_siswa.html',
                           active_menu='siswa',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           siswa_list=siswa_list,
                           total_laki=total_laki,
                           total_perempuan=total_perempuan)

@app.route('/pelatih/siswa/remove/<int:user_id>', methods=['POST'])
@role_required('pelatih')
def pelatih_remove_siswa(user_id):
    ekskul_id = request.form.get('ekskul_id', type=int)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.execute("DELETE FROM siswa_ekskul WHERE user_id = ? AND ekskul_id = ?", (user_id, ekskul_id))
    conn.commit()
    conn.close()
    flash(f"Siswa '{user['nama'] if user else user_id}' telah dikeluarkan dari cabang ekskul.", "info")
    return redirect(url_for('pelatih_siswa', ekskul_id=ekskul_id))

@app.route('/pelatih/izin')
@role_required('pelatih')
def pelatih_izin():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    today_str = get_wib_today_str()

    # 1. Seluruh pengajuan izin / sakit yang MENUNGGU persetujuan pelatih (diutamakan agar bisa langsung di-approve/reject)
    pengajuan_menunggu = conn.execute("""
    SELECT p.*, u.nama as nama_siswa, u.kelas, u.jenis_kelamin, u.username 
    FROM pengajuan_izin p
    JOIN users u ON p.user_id = u.id
    WHERE p.ekskul_id = ? AND p.status_approval = 'MENUNGGU'
    ORDER BY p.tanggal_latihan ASC, p.created_at DESC
    """, (ekskul['id'],)).fetchall()

    # 2. Riwayat seluruh permohonan izin (termasuk yang disetujui & ditolak)
    riwayat_semua_izin = conn.execute("""
    SELECT p.*, u.nama as nama_siswa, u.kelas, u.jenis_kelamin, u.username 
    FROM pengajuan_izin p
    JOIN users u ON p.user_id = u.id
    WHERE p.ekskul_id = ?
    ORDER BY p.tanggal_latihan DESC, p.created_at DESC LIMIT 50
    """, (ekskul['id'],)).fetchall()

    conn.close()
    return render_template('pelatih_izin.html',
                           active_menu='izin',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           today_str=today_str,
                           pengajuan_menunggu=pengajuan_menunggu,
                           riwayat_semua_izin=riwayat_semua_izin)

@app.route('/pelatih/riwayat')
@role_required('pelatih')
def pelatih_riwayat():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    sesi_list = []
    if ekskul:
        sesi_list = conn.execute("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Izin') as total_izin,
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Sakit') as total_sakit,
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Alpa') as total_alpa,
               (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
        FROM sesi_latihan s
        WHERE s.ekskul_id = ?
        ORDER BY s.tanggal DESC, s.jam_mulai DESC
        """, (ekskul['id'],)).fetchall()
    
    conn.close()
    return render_template('pelatih_riwayat.html', 
                           active_menu='riwayat',
                           user=user,
                           ekskul=ekskul, 
                           assigned_ekskuls=assigned_ekskuls, 
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           sesi_list=sesi_list)

@app.route('/pelatih/pengaturan', methods=['GET', 'POST'])
@role_required('pelatih')
def pelatih_pengaturan():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    if request.method == 'POST':
        hari = request.form.get('hari_latihan', '').strip()
        jam = request.form.get('jam_latihan', '').strip()
        conn.execute("UPDATE ekskul SET hari_latihan = ?, jam_latihan = ? WHERE id = ?", (hari, jam, ekskul['id']))
        conn.commit()
        conn.close()
        flash("Jadwal rutin latihan berhasil diperbarui!", "success")
        return redirect(url_for('pelatih_pengaturan', ekskul_id=ekskul['id']))

    conn.close()
    return render_template('pelatih_pengaturan.html',
                           active_menu='pengaturan',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif)

@app.route('/pelatih/jadwal/update', methods=['POST'])
@role_required('pelatih')
def update_jadwal_pelatih():
    ekskul_id = request.form.get('ekskul_id')
    hari = request.form.get('hari_latihan', '').strip()
    jam = request.form.get('jam_latihan', '').strip()
    
    conn = get_db()
    conn.execute("UPDATE ekskul SET hari_latihan = ?, jam_latihan = ? WHERE id = ?", (hari, jam, ekskul_id))
    conn.commit()
    conn.close()
    flash("Jadwal latihan berhasil diperbarui!", "success")
    return redirect(url_for('pelatih_pengaturan', ekskul_id=ekskul_id))

@app.route('/pelatih/pengajuan/approval/<int:pengajuan_id>', methods=['POST'])
@role_required('pelatih')
def approval_pengajuan(pengajuan_id):
    action = request.form.get('action') # 'DISETUJUI' atau 'DITOLAK'
    catatan = request.form.get('catatan_pelatih', '').strip()
    ekskul_id = request.form.get('ekskul_id')
    ref = request.form.get('ref', 'izin')
    
    conn = get_db()
    conn.execute("""
    UPDATE pengajuan_izin 
    SET status_approval = ?, catatan_pelatih = ?
    WHERE id = ?
    """, (action, catatan, pengajuan_id))
    conn.commit()
    conn.close()
    
    label_status = "disetujui" if action == 'DISETUJUI' else "ditolak"
    flash(f"Permohonan izin siswa berhasil {label_status}!", "success" if action == 'DISETUJUI' else "info")
    if ref == 'dashboard':
        return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))
    return redirect(url_for('pelatih_izin', ekskul_id=ekskul_id) if ekskul_id else url_for('pelatih_dashboard'))

@app.route('/pelatih/profil/update', methods=['POST'])
@role_required('pelatih')
def pelatih_update_profil():
    pelatih_id = session['user_id']
    nama = request.form.get('nama', '').strip()
    username = request.form.get('username', '').strip()
    password_baru = request.form.get('password_baru', '').strip()
    ekskul_id = request.form.get('ekskul_id')

    if not nama or not username:
        flash("Nama dan username tidak boleh kosong.", "danger")
        return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

    conn = get_db()
    conflict = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, pelatih_id)).fetchone()
    if conflict:
        conn.close()
        flash(f"Username '{username}' sudah digunakan pengguna lain.", "danger")
        return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

    if password_baru:
        conn.execute("UPDATE users SET nama = ?, username = ?, password = ? WHERE id = ?", (nama, username, password_baru, pelatih_id))
    else:
        conn.execute("UPDATE users SET nama = ?, username = ? WHERE id = ?", (nama, username, pelatih_id))

    conn.commit()
    conn.close()

    session['nama'] = nama
    session['username'] = username
    flash("Profil dan informasi akun pelatih berhasil diperbarui!", "success")
    return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

# =========================================================
# 1b. LAPORAN BULANAN PELATIH (SILABUS, REKAP NILAI, HONOR TU)
# =========================================================

@app.route('/pelatih/laporan-bulanan')
@role_required('pelatih')
def pelatih_laporan_bulanan():
    pelatih_id = session['user_id']
    conn, user, assigned_ekskuls, ekskul, total_pending, total_izin, total_siswa_aktif = get_pelatih_context(pelatih_id)
    
    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini.", 400

    now_wib = get_wib_datetime()
    current_year = now_wib.year
    selected_bulan = request.args.get('bulan', type=int) or now_wib.month
    selected_tahun = request.args.get('tahun', type=int) or current_year

    if selected_bulan < 1 or selected_bulan > 12:
        selected_bulan = now_wib.month

    # Ambil data laporan_bulanan jika sudah pernah dibuat
    laporan = conn.execute("""
    SELECT * FROM laporan_bulanan 
    WHERE ekskul_id = ? AND bulan = ? AND tahun = ?
    """, (ekskul['id'], selected_bulan, selected_tahun)).fetchone()

    materi_list = []
    is_rencana_lengkap = False
    is_penilaian_selesai = False

    if laporan:
        is_rencana_lengkap = (laporan['status_rencana'] == 'LENGKAP')
        is_penilaian_selesai = (laporan['status_penilaian'] == 'SELESAI')
        materi_rows = conn.execute("""
        SELECT * FROM laporan_materi_mingguan 
        WHERE laporan_id = ? 
        ORDER BY pertemuan_ke ASC
        """, (laporan['id'],)).fetchall()
        materi_list = [dict(m) for m in materi_rows]

    # Ambil sesi latihan riil yang telah terlaksana pada bulan & tahun tersebut
    month_prefix = f"{selected_tahun:04d}-{selected_bulan:02d}"
    sesi_rows = conn.execute("""
    SELECT s.*,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
    FROM sesi_latihan s
    WHERE s.ekskul_id = ? AND s.tanggal LIKE ?
    ORDER BY s.tanggal ASC, s.jam_mulai ASC
    """, (ekskul['id'], f"{month_prefix}%")).fetchall()
    sesi_list = [dict(s) for s in sesi_rows]
    total_sesi_terlaksana = len(sesi_list)

    # Ambil daftar siswa aktif untuk penilaian
    siswa_penilaian = []
    if is_rencana_lengkap and laporan:
        active_students = conn.execute("""
        SELECT u.id, u.nama, u.kelas, u.jenis_kelamin
        FROM users u
        JOIN siswa_ekskul se ON u.id = se.user_id
        WHERE se.ekskul_id = ? AND se.status = 'AKTIF' AND u.role = 'siswa'
        ORDER BY u.kelas ASC, u.nama ASC
        """, (ekskul['id'],)).fetchall()

        # Ambil penilaian yang sudah tersimpan jika ada
        saved_penilaian = conn.execute("""
        SELECT * FROM laporan_penilaian_siswa WHERE laporan_id = ?
        """, (laporan['id'],)).fetchall()
        penilaian_map = {p['siswa_id']: dict(p) for p in saved_penilaian}

        for st in active_students:
            s_id = st['id']
            # Hitung kehadiran riil siswa ini di sesi latihan bulan tersebut
            att_stat = conn.execute("""
            SELECT 
                SUM(CASE WHEN ps.status_kehadiran = 'Hadir' THEN 1 ELSE 0 END) as hadir,
                SUM(CASE WHEN ps.status_kehadiran = 'Izin' THEN 1 ELSE 0 END) as izin,
                SUM(CASE WHEN ps.status_kehadiran = 'Sakit' THEN 1 ELSE 0 END) as sakit,
                SUM(CASE WHEN ps.status_kehadiran = 'Alpa' THEN 1 ELSE 0 END) as alpa
            FROM presensi_siswa ps
            JOIN sesi_latihan sl ON ps.sesi_id = sl.id
            WHERE ps.user_id = ? AND sl.ekskul_id = ? AND sl.tanggal LIKE ?
            """, (s_id, ekskul['id'], f"{month_prefix}%")).fetchone()

            tot_hadir = att_stat['hadir'] or 0
            tot_izin = att_stat['izin'] or 0
            tot_sakit = att_stat['sakit'] or 0
            tot_alpa = att_stat['alpa'] or 0
            persen = (tot_hadir / total_sesi_terlaksana * 100.0) if total_sesi_terlaksana > 0 else 0.0

            sp_item = {
                'siswa_id': s_id,
                'nama': st['nama'],
                'kelas': st['kelas'],
                'jenis_kelamin': st['jenis_kelamin'],
                'total_hadir': tot_hadir,
                'total_izin': tot_izin,
                'total_sakit': tot_sakit,
                'total_alpa': tot_alpa,
                'persentase_kehadiran': persen
            }

            if s_id in penilaian_map:
                sp_item['nilai_skor'] = penilaian_map[s_id]['nilai_skor']
                sp_item['predikat'] = penilaian_map[s_id]['predikat']
                sp_item['catatan_evaluasi'] = penilaian_map[s_id]['catatan_evaluasi']
            else:
                sp_item['nilai_skor'] = 85
                sp_item['predikat'] = 'Baik (B)'
                sp_item['catatan_evaluasi'] = ''

            siswa_penilaian.append(sp_item)

    conn.close()
    return render_template('pelatih_laporan_bulanan.html',
                           active_menu='laporan_bulanan',
                           user=user,
                           ekskul=ekskul,
                           assigned_ekskuls=assigned_ekskuls,
                           total_pending=total_pending,
                           total_izin=total_izin,
                           total_siswa_aktif=total_siswa_aktif,
                           laporan=laporan,
                           materi_list=materi_list,
                           is_rencana_lengkap=is_rencana_lengkap,
                           is_penilaian_selesai=is_penilaian_selesai,
                           sesi_list=sesi_list,
                           total_sesi_terlaksana=total_sesi_terlaksana,
                           siswa_penilaian=siswa_penilaian,
                           list_bulan=NAMA_BULAN,
                           nama_bulan=NAMA_BULAN.get(selected_bulan, ''),
                           selected_bulan=selected_bulan,
                           selected_tahun=selected_tahun,
                           current_year=current_year)

@app.route('/pelatih/laporan-bulanan/materi/simpan', methods=['POST'])
@role_required('pelatih')
def pelatih_simpan_materi_bulanan():
    pelatih_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id', type=int)
    bulan = request.form.get('bulan', type=int)
    tahun = request.form.get('tahun', type=int)
    laporan_id = request.form.get('laporan_id', type=int)

    pertemuan_ke_list = request.form.getlist('pertemuan_ke[]')
    tanggal_rencana_list = request.form.getlist('tanggal_rencana[]')
    materi_list = request.form.getlist('materi[]')
    indikator_list = request.form.getlist('indikator_ketercapaian[]')

    # Validasi bahwa ada materi yang terisi
    clean_items = []
    for i in range(len(materi_list)):
        mat = materi_list[i].strip() if i < len(materi_list) else ''
        if mat:
            ptm = int(pertemuan_ke_list[i]) if i < len(pertemuan_ke_list) and pertemuan_ke_list[i].isdigit() else (len(clean_items) + 1)
            tgl = tanggal_rencana_list[i].strip() if i < len(tanggal_rencana_list) else ''
            ind = indikator_list[i].strip() if i < len(indikator_list) else ''
            clean_items.append((ptm, tgl, mat, ind))

    if not clean_items:
        flash("Minimal harus mengisi 1 materi pertemuan dalam rencana silabus.", "danger")
        return redirect(url_for('pelatih_laporan_bulanan', ekskul_id=ekskul_id, bulan=bulan, tahun=tahun))

    now_str = get_wib_datetime().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()

    # Dapatkan atau buat laporan_bulanan
    if not laporan_id:
        existing = conn.execute("""
        SELECT id FROM laporan_bulanan WHERE ekskul_id = ? AND bulan = ? AND tahun = ?
        """, (ekskul_id, bulan, tahun)).fetchone()
        if existing:
            laporan_id = existing['id']

    if laporan_id:
        conn.execute("""
        UPDATE laporan_bulanan 
        SET pelatih_id = ?, status_rencana = 'LENGKAP', updated_at = ?
        WHERE id = ?
        """, (pelatih_id, now_str, laporan_id))
    else:
        cur = conn.execute("""
        INSERT INTO laporan_bulanan (ekskul_id, pelatih_id, bulan, tahun, status_rencana, updated_at)
        VALUES (?, ?, ?, ?, 'LENGKAP', ?)
        """, (ekskul_id, pelatih_id, bulan, tahun, now_str))
        laporan_id = cur.lastrowid

    # Refresh tabel laporan_materi_mingguan
    conn.execute("DELETE FROM laporan_materi_mingguan WHERE laporan_id = ?", (laporan_id,))
    for ptm, tgl, mat, ind in clean_items:
        conn.execute("""
        INSERT INTO laporan_materi_mingguan (laporan_id, pertemuan_ke, tanggal_rencana, materi, indikator_ketercapaian)
        VALUES (?, ?, ?, ?, ?)
        """, (laporan_id, ptm, tgl, mat, ind))

    conn.commit()
    conn.close()

    flash(f"Rencana Silabus Materi Bulanan ({len(clean_items)} Pertemuan) berhasil disimpan! Fitur 2 (Rekap Presensi & Nilai Siswa) dan Fitur 3 (Lembar Honor TU) kini telah terbuka.", "success")
    return redirect(url_for('pelatih_laporan_bulanan', ekskul_id=ekskul_id, bulan=bulan, tahun=tahun))

@app.route('/pelatih/laporan-bulanan/penilaian/simpan', methods=['POST'])
@role_required('pelatih')
def pelatih_simpan_penilaian_bulanan():
    pelatih_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id', type=int)
    bulan = request.form.get('bulan', type=int)
    tahun = request.form.get('tahun', type=int)
    laporan_id = request.form.get('laporan_id', type=int)
    catatan_umum = request.form.get('catatan_umum', '').strip()

    siswa_id_list = request.form.getlist('siswa_id[]')
    total_hadir_list = request.form.getlist('total_hadir[]')
    total_izin_list = request.form.getlist('total_izin[]')
    total_sakit_list = request.form.getlist('total_sakit[]')
    total_alpa_list = request.form.getlist('total_alpa[]')
    persentase_list = request.form.getlist('persentase[]')
    nilai_skor_list = request.form.getlist('nilai_skor[]')
    predikat_list = request.form.getlist('predikat[]')
    catatan_evaluasi_list = request.form.getlist('catatan_evaluasi[]')

    if not laporan_id:
        flash("Silakan simpan Rencana Silabus Materi (Fitur 1) terlebih dahulu.", "danger")
        return redirect(url_for('pelatih_laporan_bulanan', ekskul_id=ekskul_id, bulan=bulan, tahun=tahun))

    now_str = get_wib_datetime().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()

    conn.execute("""
    UPDATE laporan_bulanan 
    SET catatan_umum = ?, status_penilaian = 'SELESAI', updated_at = ?
    WHERE id = ?
    """, (catatan_umum, now_str, laporan_id))

    count_saved = 0
    for i in range(len(siswa_id_list)):
        s_id = int(siswa_id_list[i])
        skor = int(nilai_skor_list[i]) if i < len(nilai_skor_list) and nilai_skor_list[i].isdigit() else 80
        pred = predikat_list[i] if i < len(predikat_list) else 'Baik (B)'
        eval_note = catatan_evaluasi_list[i].strip() if i < len(catatan_evaluasi_list) else ''
        th = int(total_hadir_list[i]) if i < len(total_hadir_list) and total_hadir_list[i].isdigit() else 0
        ti = int(total_izin_list[i]) if i < len(total_izin_list) and total_izin_list[i].isdigit() else 0
        ts = int(total_sakit_list[i]) if i < len(total_sakit_list) and total_sakit_list[i].isdigit() else 0
        ta = int(total_alpa_list[i]) if i < len(total_alpa_list) and total_alpa_list[i].isdigit() else 0
        pr = float(persentase_list[i]) if i < len(persentase_list) and persentase_list[i] else 0.0

        conn.execute("""
        INSERT INTO laporan_penilaian_siswa (
            laporan_id, siswa_id, nilai_skor, predikat, catatan_evaluasi,
            total_hadir, total_izin, total_sakit, total_alpa, persentase_kehadiran
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(laporan_id, siswa_id) DO UPDATE SET
            nilai_skor = excluded.nilai_skor,
            predikat = excluded.predikat,
            catatan_evaluasi = excluded.catatan_evaluasi,
            total_hadir = excluded.total_hadir,
            total_izin = excluded.total_izin,
            total_sakit = excluded.total_sakit,
            total_alpa = excluded.total_alpa,
            persentase_kehadiran = excluded.persentase_kehadiran
        """, (laporan_id, s_id, skor, pred, eval_note, th, ti, ts, ta, pr))
        count_saved += 1

    conn.commit()
    conn.close()

    flash(f"Penilaian ketercapaian materi untuk {count_saved} siswa berhasil disimpan dan telah dikirimkan ke akun masing-masing siswa!", "success")
    return redirect(url_for('pelatih_laporan_bulanan', ekskul_id=ekskul_id, bulan=bulan, tahun=tahun))

@app.route('/pelatih/laporan-bulanan/cetak/<int:laporan_id>')
@app.route('/laporan/cetak/<int:laporan_id>')
@login_required
def cetak_laporan_bulanan(laporan_id):
    conn = get_db()
    laporan = conn.execute("SELECT * FROM laporan_bulanan WHERE id = ?", (laporan_id,)).fetchone()
    if not laporan:
        conn.close()
        return "Laporan bulanan tidak ditemukan.", 404

    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (laporan['ekskul_id'],)).fetchone()
    pelatih = conn.execute("SELECT * FROM users WHERE id = ?", (laporan['pelatih_id'],)).fetchone()
    
    # Hak akses: pelatih pemilik / admin
    if session.get('role') == 'pelatih':
        user_id = session.get('user_id')
        pe = conn.execute("SELECT * FROM pelatih_ekskul WHERE user_id = ? AND ekskul_id = ?", (user_id, laporan['ekskul_id'])).fetchone()
        u = conn.execute("SELECT * FROM users WHERE id = ? AND ekskul_id = ?", (user_id, laporan['ekskul_id'])).fetchone()
        if not pe and not u:
            conn.close()
            return "Anda tidak memiliki akses ke laporan ekskul ini.", 403

    materi_rows = conn.execute("""
    SELECT * FROM laporan_materi_mingguan WHERE laporan_id = ? ORDER BY pertemuan_ke ASC
    """, (laporan_id,)).fetchall()
    materi_list = [dict(m) for m in materi_rows]

    month_prefix = f"{laporan['tahun']:04d}-{laporan['bulan']:02d}"
    sesi_rows = conn.execute("""
    SELECT s.*,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Izin') as total_izin,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Sakit') as total_sakit,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Alpa') as total_alpa,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
    FROM sesi_latihan s
    WHERE s.ekskul_id = ? AND s.tanggal LIKE ?
    ORDER BY s.tanggal ASC, s.jam_mulai ASC
    """, (laporan['ekskul_id'], f"{month_prefix}%")).fetchall()

    sesi_list = []
    total_rekap_hadir = 0
    total_rekap_izin = 0
    total_rekap_sakit = 0
    total_rekap_alpa = 0
    total_rekap_peserta = 0

    for s in sesi_rows:
        sd = dict(s)
        h = sd.get('total_hadir') or 0
        i = sd.get('total_izin') or 0
        sk = sd.get('total_sakit') or 0
        a = sd.get('total_alpa') or 0
        tot = sd.get('total_peserta') or (h + i + sk + a)
        pct = round((h / tot * 100), 1) if tot > 0 else 0.0

        sd['total_hadir'] = h
        sd['total_izin'] = i
        sd['total_sakit'] = sk
        sd['total_alpa'] = a
        sd['total_peserta'] = tot
        sd['persen_hadir'] = pct

        total_rekap_hadir += h
        total_rekap_izin += i
        total_rekap_sakit += sk
        total_rekap_alpa += a
        total_rekap_peserta += tot

        sesi_list.append(sd)

    rekap_total = {
        'hadir': total_rekap_hadir,
        'izin': total_rekap_izin,
        'sakit': total_rekap_sakit,
        'alpa': total_rekap_alpa,
        'peserta': total_rekap_peserta,
        'persen_rata': round((total_rekap_hadir / total_rekap_peserta * 100), 1) if total_rekap_peserta > 0 else 0.0
    }

    total_siswa_aktif = conn.execute("""
    SELECT COUNT(*) FROM siswa_ekskul WHERE ekskul_id = ? AND status = 'AKTIF'
    """, (laporan['ekskul_id'],)).fetchone()[0]

    siswa_penilaian = conn.execute("""
    SELECT lp.*, u.nama, u.kelas, u.jenis_kelamin
    FROM laporan_penilaian_siswa lp
    JOIN users u ON lp.siswa_id = u.id
    WHERE lp.laporan_id = ?
    ORDER BY u.kelas ASC, u.nama ASC
    """, (laporan_id,)).fetchall()
    siswa_penilaian = [dict(sp) for sp in siswa_penilaian]

    now_wib = get_wib_datetime()
    print_date = now_wib.strftime('%d-%m-%Y %H:%M')
    nama_bulan = NAMA_BULAN.get(laporan['bulan'], f"Bulan {laporan['bulan']}")
    tgl_laporan = f"{now_wib.day} {NAMA_BULAN.get(now_wib.month)} {now_wib.year}"

    pejabat = get_pengaturan_laporan(conn)

    conn.close()
    return render_template('cetak_laporan_bulanan.html',
                           laporan=laporan,
                           ekskul=ekskul,
                           pelatih=pelatih,
                           bulan=laporan['bulan'],
                           tahun=laporan['tahun'],
                           nama_bulan=nama_bulan,
                           materi_list=materi_list,
                           sesi_list=sesi_list,
                           rekap_total=rekap_total,
                           total_siswa_aktif=total_siswa_aktif,
                           siswa_penilaian=siswa_penilaian,
                           print_date=print_date,
                           tgl_laporan=tgl_laporan,
                           pejabat=pejabat)

# =========================================================
# 2. AKUN SISWA (PILIH EKSKUL & INFO PRA-PRESENSI)
# =========================================================

@app.route('/siswa')
@role_required('siswa')
def siswa_dashboard():
    siswa_id = session['user_id']
    conn = get_db()
    
    user = conn.execute("SELECT * FROM users WHERE id = ?", (siswa_id,)).fetchone()
    
    # Ambil ekskul resmi aktif yang diikuti siswa
    ekskul_diikuti = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN siswa_ekskul se ON e.id = se.ekskul_id
    WHERE se.user_id = ? AND se.status = 'AKTIF'
    """, (siswa_id,)).fetchall()

    # Ambil ekskul yang masih menunggu persetujuan pelatih
    ekskul_menunggu = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN siswa_ekskul se ON e.id = se.ekskul_id
    WHERE se.user_id = ? AND se.status = 'MENUNGGU'
    """, (siswa_id,)).fetchall()

    # Ambil ekskul yang ditolak
    ekskul_ditolak = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN siswa_ekskul se ON e.id = se.ekskul_id
    WHERE se.user_id = ? AND se.status = 'DITOLAK'
    """, (siswa_id,)).fetchall()
    
    # Seluruh pilihan ekskul untuk opsi tambah/ganti
    all_ekskul = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    
    # Pengajuan izin siswa yang pernah dikirim
    riwayat_pengajuan = conn.execute("""
    SELECT p.*, e.nama as nama_ekskul, e.icon as icon_ekskul
    FROM pengajuan_izin p
    JOIN ekskul e ON p.ekskul_id = e.id
    WHERE p.user_id = ?
    ORDER BY p.tanggal_latihan DESC, p.created_at DESC LIMIT 10
    """, (siswa_id,)).fetchall()

    # Statistik kehadiran pribadi siswa ini
    statistik_kehadiran = conn.execute("""
    SELECT 
        COUNT(ps.id) as total_sesi,
        SUM(CASE WHEN ps.status_kehadiran = 'Hadir' THEN 1 ELSE 0 END) as hadir,
        SUM(CASE WHEN ps.status_kehadiran = 'Izin' THEN 1 ELSE 0 END) as izin,
        SUM(CASE WHEN ps.status_kehadiran = 'Sakit' THEN 1 ELSE 0 END) as sakit,
        SUM(CASE WHEN ps.status_kehadiran = 'Alpa' THEN 1 ELSE 0 END) as alpa
    FROM presensi_siswa ps
    WHERE ps.user_id = ?
    """, (siswa_id,)).fetchone()

    # Rapor perkembangan bulanan siswa dari pelatih
    rapor_rows = conn.execute("""
    SELECT lp.*, lb.bulan, lb.tahun, e.nama as nama_ekskul, e.icon as icon_ekskul, u.nama as nama_pelatih
    FROM laporan_penilaian_siswa lp
    JOIN laporan_bulanan lb ON lp.laporan_id = lb.id
    JOIN ekskul e ON lb.ekskul_id = e.id
    JOIN users u ON lb.pelatih_id = u.id
    WHERE lp.siswa_id = ?
    ORDER BY lb.tahun DESC, lb.bulan DESC
    """, (siswa_id,)).fetchall()
    
    rapor_bulanan = []
    for r in rapor_rows:
        rd = dict(r)
        rd['nama_bulan'] = NAMA_BULAN.get(r['bulan'], f"Bulan {r['bulan']}")
        rapor_bulanan.append(rd)

    # Pengumuman & pengingat dari Pelatih atau Madrasah
    pengumuman_rows = conn.execute("""
    SELECT p.*, u.nama as nama_pengirim, e.nama as nama_ekskul
    FROM pengumuman p
    LEFT JOIN users u ON p.pengirim_id = u.id
    LEFT JOIN ekskul e ON p.ekskul_id = e.id
    WHERE (p.tipe = 'admin' AND p.target_role IN ('siswa', 'semua'))
       OR (p.tipe = 'pelatih' AND p.ekskul_id IN (
           SELECT ekskul_id FROM siswa_ekskul WHERE user_id = ? AND status = 'AKTIF'
       ))
    ORDER BY p.created_at DESC LIMIT 5
    """, (siswa_id,)).fetchall()
    pengumuman_list = [dict(p) for p in pengumuman_rows]

    today_str = get_wib_today_str()
    conn.close()
    
    return render_template('siswa_dashboard.html', 
                           user=user, 
                           ekskul_diikuti=ekskul_diikuti, 
                           ekskul_menunggu=ekskul_menunggu,
                           ekskul_ditolak=ekskul_ditolak,
                           all_ekskul=all_ekskul,
                           riwayat_pengajuan=riwayat_pengajuan,
                           statistik=statistik_kehadiran,
                           rapor_bulanan=rapor_bulanan,
                           pengumuman_list=pengumuman_list,
                           today_str=today_str)

@app.route('/siswa/ekskul/pilih', methods=['POST'])
@role_required('siswa')
def siswa_pilih_ekskul():
    siswa_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id')
    if not ekskul_id:
        flash("Silakan pilih cabang ekstrakurikuler terlebih dahulu.", "danger")
        return redirect(url_for('siswa_dashboard'))
    
    conn = get_db()
    existing = conn.execute("""
    SELECT * FROM siswa_ekskul WHERE user_id = ? AND ekskul_id = ?
    """, (siswa_id, ekskul_id)).fetchone()
    
    if existing:
        if existing['status'] == 'AKTIF':
            flash("Anda sudah menjadi anggota resmi di cabang ekstrakurikuler ini.", "info")
        elif existing['status'] == 'MENUNGGU':
            flash("Pendaftaran Anda di cabang ini sedang menunggu persetujuan pelatih.", "warning")
        else:
            conn.execute("""
            UPDATE siswa_ekskul SET status = 'MENUNGGU', tanggal_daftar = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (existing['id'],))
            conn.commit()
            flash("Permohonan Anda berhasil diajukan kembali ke pelatih! Menunggu persetujuan.", "success")
    else:
        conn.execute("""
        INSERT INTO siswa_ekskul (user_id, ekskul_id, status) VALUES (?, ?, 'MENUNGGU')
        """, (siswa_id, ekskul_id))
        conn.commit()
        flash("Permohonan memilih ekskul berhasil dikirim! Menunggu persetujuan dari Pelatih.", "success")
        
    conn.close()
    return redirect(url_for('siswa_dashboard'))

@app.route('/siswa/pengajuan/kirim', methods=['POST'])
@role_required('siswa')
def siswa_kirim_pengajuan():
    siswa_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id')
    tanggal = request.form.get('tanggal_latihan') or get_wib_today_str()
    status_pengajuan = request.form.get('status_pengajuan') # 'Akan Hadir', 'Izin', 'Sakit'
    alasan = request.form.get('alasan', '').strip()

    if not ekskul_id or not status_pengajuan:
        flash("Silakan pilih ekskul dan status konfirmasi Anda.", "danger")
        return redirect(url_for('siswa_dashboard'))

    conn = get_db()
    # Cek apakah sudah pernah mengajukan untuk tanggal ini
    existing = conn.execute("""
    SELECT id FROM pengajuan_izin 
    WHERE user_id = ? AND ekskul_id = ? AND tanggal_latihan = ?
    """, (siswa_id, ekskul_id, tanggal)).fetchone()

    if existing:
        conn.execute("""
        UPDATE pengajuan_izin 
        SET status_pengajuan = ?, alasan = ?, status_approval = 'MENUNGGU'
        WHERE id = ?
        """, (status_pengajuan, alasan, existing['id']))
    else:
        conn.execute("""
        INSERT INTO pengajuan_izin (user_id, ekskul_id, tanggal_latihan, status_pengajuan, alasan)
        VALUES (?, ?, ?, ?, ?)
        """, (siswa_id, ekskul_id, tanggal, status_pengajuan, alasan))

    conn.commit()
    conn.close()

    flash(f"Konfirmasi '{status_pengajuan}' berhasil diajukan ke Pelatih!", "success")
    return redirect(url_for('siswa_dashboard'))

# =========================================================
# 3. AKUN ADMIN MASTER (MULTI-HALAMAN & SIDEBAR NAVIGATION)
# =========================================================

@app.route('/admin')
@app.route('/admin/dashboard')
@app.route('/kelola')
@role_required('admin')
def admin_dashboard():
    """Halaman 1: Ringkasan Dashboard & Notifikasi Permohonan Reset"""
    conn = get_db()
    current_admin = conn.execute("SELECT * FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

    total_ekskul_count = conn.execute("SELECT COUNT(*) FROM ekskul").fetchone()[0]
    total_pelatih_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'pelatih'").fetchone()[0]
    total_siswa_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'siswa'").fetchone()[0]
    total_sesi_count = conn.execute("SELECT COUNT(*) FROM sesi_latihan").fetchone()[0]

    # Data Real-Time Partisipasi Siswa MTs Muhammadiyah Tajurhalang
    total_master_siswa = conn.execute("SELECT COUNT(*) FROM master_siswa").fetchone()[0]
    total_siswa_pilih_ekskul = conn.execute("SELECT COUNT(*) FROM master_siswa WHERE user_id IS NOT NULL").fetchone()[0]
    total_siswa_belum_pilih = conn.execute("SELECT COUNT(*) FROM master_siswa WHERE user_id IS NULL").fetchone()[0]
    persen_pilih_ekskul = round((total_siswa_pilih_ekskul / total_master_siswa * 100), 1) if total_master_siswa > 0 else 0

    stats_per_kelas = conn.execute("""
    SELECT 
        kelas,
        COUNT(*) as total,
        SUM(CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) as sudah_pilih,
        SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as belum_pilih
    FROM master_siswa
    GROUP BY kelas
    ORDER BY kelas ASC
    """).fetchall()

    siswa_belum_pilih_list = conn.execute("""
    SELECT * FROM master_siswa
    WHERE user_id IS NULL
    ORDER BY kelas ASC, nama ASC
    """).fetchall()

    # Permohonan Reset Password Pending
    reset_requests = conn.execute("""
    SELECT r.*, u.nama as nama_user, u.role as role_user
    FROM reset_password_requests r
    LEFT JOIN users u ON r.user_id = u.id
    WHERE r.status = 'PENDING'
    ORDER BY r.created_at DESC
    """).fetchall()

    # Sesi latihan terbaru
    recent_sessions = conn.execute("""
    SELECT s.*, e.nama as nama_ekskul, e.icon as icon_ekskul,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as hadir_count,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_presensi
    FROM sesi_latihan s
    JOIN ekskul e ON s.ekskul_id = e.id
    ORDER BY s.id DESC LIMIT 5
    """).fetchall()

    conn.close()
    return render_template('admin_dashboard.html',
                           current_admin=current_admin,
                           total_ekskul=total_ekskul_count,
                           total_pelatih=total_pelatih_count,
                           total_siswa=total_siswa_count,
                           total_sesi=total_sesi_count,
                           total_master_siswa=total_master_siswa,
                           total_siswa_pilih_ekskul=total_siswa_pilih_ekskul,
                           total_siswa_belum_pilih=total_siswa_belum_pilih,
                           persen_pilih_ekskul=persen_pilih_ekskul,
                           stats_per_kelas=stats_per_kelas,
                           siswa_belum_pilih_list=siswa_belum_pilih_list,
                           reset_requests=reset_requests,
                           recent_sessions=recent_sessions,
                           active_menu='dashboard')

@app.route('/admin/pelatih')
@role_required('admin')
def admin_pelatih():
    """Halaman 2: Data Master Pelatih & Tambah Akun Pelatih"""
    conn = get_db()
    current_admin = conn.execute("SELECT * FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

    raw_pelatih_list = conn.execute("""
    SELECT u.*, e.nama as nama_ekskul, e.icon as icon_ekskul, e.hari_latihan, e.jam_latihan 
    FROM users u
    LEFT JOIN ekskul e ON u.ekskul_id = e.id
    WHERE u.role = 'pelatih'
    ORDER BY u.nama ASC
    """).fetchall()

    pelatih_list = []
    for p in raw_pelatih_list:
        p_dict = dict(p)
        assigned = conn.execute("""
        SELECT e.* FROM ekskul e
        JOIN pelatih_ekskul pe ON e.id = pe.ekskul_id
        WHERE pe.user_id = ?
        ORDER BY e.nama ASC
        """, (p['id'],)).fetchall()

        if not assigned and p['ekskul_id']:
            assigned = conn.execute("SELECT * FROM ekskul WHERE id = ?", (p['ekskul_id'],)).fetchall()

        p_dict['assigned_ekskuls'] = assigned
        p_dict['assigned_ids'] = [e['id'] for e in assigned]
        pelatih_list.append(p_dict)

    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    reset_requests = conn.execute("SELECT * FROM reset_password_requests WHERE status = 'PENDING'").fetchall()
    conn.close()

    return render_template('admin_pelatih.html',
                           current_admin=current_admin,
                           pelatih_list=pelatih_list,
                           ekskul_list=ekskul_list,
                           reset_requests=reset_requests,
                           total_pelatih=len(pelatih_list),
                           active_menu='pelatih')

@app.route('/admin/siswa')
@role_required('admin')
def admin_siswa():
    """Halaman 3: Data Master Siswa MTs Muhammadiyah Tajurhalang, Import CSV & Kelola Akun"""
    conn = get_db()
    current_admin = conn.execute("SELECT * FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

    master_siswa_list = conn.execute("""
    SELECT m.id as master_id, m.nis, m.nama, m.kelas, m.jenis_kelamin, m.no_whatsapp, m.user_id,
           u.username, u.id as u_id,
           COALESCE(
               (SELECT GROUP_CONCAT(e2.icon || ' ' || e2.nama, ', ')
                FROM siswa_ekskul se2
                JOIN ekskul e2 ON se2.ekskul_id = e2.id
                WHERE se2.user_id = u.id AND se2.status IN ('AKTIF', 'MENUNGGU')),
               e.icon || ' ' || e.nama
           ) as daftar_ekskul,
           (SELECT se3.status FROM siswa_ekskul se3 WHERE se3.user_id = u.id LIMIT 1) as status_approval_ekskul
    FROM master_siswa m
    LEFT JOIN users u ON m.user_id = u.id
    LEFT JOIN ekskul e ON u.ekskul_id = e.id
    ORDER BY m.kelas ASC, m.nama ASC
    """).fetchall()

    # Hitung metrik real-time master siswa
    total_master = len(master_siswa_list)
    total_sudah_pilih = sum(1 for m in master_siswa_list if m['user_id'] is not None)
    total_belum_pilih = sum(1 for m in master_siswa_list if m['user_id'] is None)

    # Siswa yang sudah memiliki akun (kompatibilitas backward)
    siswa_list = [m for m in master_siswa_list if m['user_id'] is not None]

    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    reset_requests = conn.execute("SELECT * FROM reset_password_requests WHERE status = 'PENDING'").fetchall()
    conn.close()

    return render_template('admin_siswa.html',
                           current_admin=current_admin,
                           master_siswa_list=master_siswa_list,
                           siswa_list=siswa_list,
                           ekskul_list=ekskul_list,
                           reset_requests=reset_requests,
                           total_master=total_master,
                           total_sudah_pilih=total_sudah_pilih,
                           total_belum_pilih=total_belum_pilih,
                           total_siswa=total_sudah_pilih,
                           active_menu='siswa')

@app.route('/admin/ekskul-gps')
@role_required('admin')
def admin_ekskul_gps():
    """Halaman 4: Kelola Cabang Ekskul & Kalibrasi GPS Lapangan"""
    conn = get_db()
    current_admin = conn.execute("SELECT * FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

    ekskul_list = conn.execute("""
    SELECT e.*, 
           (SELECT COUNT(*) FROM siswa_ekskul se WHERE se.ekskul_id = e.id AND se.status = 'AKTIF') as total_siswa,
           (SELECT COUNT(*) FROM sesi_latihan s WHERE s.ekskul_id = e.id) as total_sesi
    FROM ekskul e
    ORDER BY e.nama ASC
    """).fetchall()

    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()
    reset_requests = conn.execute("SELECT * FROM reset_password_requests WHERE status = 'PENDING'").fetchall()
    conn.close()

    return render_template('admin_ekskul_gps.html',
                           current_admin=current_admin,
                           ekskul_list=ekskul_list,
                           lokasi=lokasi,
                           reset_requests=reset_requests,
                           total_ekskul=len(ekskul_list),
                           active_menu='ekskul_gps')

@app.route('/admin/profil/update', methods=['POST'])
@role_required('admin')
def admin_profil_update():
    """Ubah username, nama, dan password untuk Admin Master"""
    admin_id = session.get('user_id')
    nama = request.form.get('nama', '').strip()
    username = request.form.get('username', '').strip()
    password_baru = request.form.get('password_baru', '').strip()

    if not nama or not username:
        flash("Nama dan Username tidak boleh kosong.", "danger")
        return redirect(request.referrer or url_for('admin_dashboard'))

    conn = get_db()
    exist = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, admin_id)).fetchone()
    if exist:
        conn.close()
        flash(f"Username '{username}' sudah digunakan pengguna lain. Silakan pilih username berbeda.", "danger")
        return redirect(request.referrer or url_for('admin_dashboard'))

    if password_baru:
        conn.execute("UPDATE users SET nama = ?, username = ?, password = ? WHERE id = ?",
                     (nama, username, password_baru, admin_id))
        flash("Profil dan kata sandi Admin Master berhasil diperbarui!", "success")
    else:
        conn.execute("UPDATE users SET nama = ?, username = ? WHERE id = ?",
                     (nama, username, admin_id))
        flash("Profil Admin Master berhasil diperbarui!", "success")

    conn.commit()
    conn.close()

    session['nama'] = nama
    session['username'] = username
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/user/reset-password', methods=['POST'])
@role_required('admin')
def admin_reset_password():
    """Reset password akun Pelatih atau Siswa"""
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password', '').strip()
    request_id = request.form.get('request_id')

    if not user_id:
        flash("ID Pengguna tidak valid.", "danger")
        return redirect(request.referrer or url_for('admin_dashboard'))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash("Akun pengguna tidak ditemukan.", "danger")
        return redirect(request.referrer or url_for('admin_dashboard'))

    # Default password jika tidak diisi manual
    if not new_password:
        new_password = 'siswa123' if user['role'] == 'siswa' else 'pelatih123'

    conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user_id))

    if request_id:
        conn.execute("UPDATE reset_password_requests SET status = 'SELESAI' WHERE id = ?", (request_id,))

    conn.commit()
    conn.close()

    flash(f"Kata sandi akun '{user['nama']}' ({user['username']}) berhasil direset menjadi: '{new_password}'", "success")
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/reset-request/tolak/<int:req_id>', methods=['POST'])
@role_required('admin')
def admin_tolak_reset_request(req_id):
    """Tolak permohonan reset password"""
    conn = get_db()
    conn.execute("UPDATE reset_password_requests SET status = 'DITOLAK' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    flash("Permohonan reset password telah ditolak.", "info")
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/siswa/delete/<int:user_id>', methods=['POST'])
@role_required('admin')
def admin_delete_siswa(user_id):
    """Hapus akun siswa yang duplikat/salah dan reset status di master_siswa"""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'siswa'", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash("Akun siswa tidak ditemukan.", "danger")
        return redirect(url_for('admin_siswa'))

    # Putuskan relasi user_id di master_siswa agar siswa bisa mendaftar kembali
    conn.execute("UPDATE master_siswa SET user_id = NULL WHERE user_id = ?", (user_id,))

    conn.execute("DELETE FROM laporan_penilaian_siswa WHERE siswa_id = ?", (user_id,))
    conn.execute("DELETE FROM siswa_ekskul WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM pengajuan_izin WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM presensi_siswa WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM reset_password_requests WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()
    flash(f"Akun siswa '{user['nama']}' (@{user['username']}) berhasil dihapus. Status master siswa direset sehingga siswa dapat mendaftar kembali jika diperlukan.", "success")
    return redirect(url_for('admin_siswa'))

@app.route('/admin/siswa/delete-all', methods=['POST'])
@role_required('admin')
def admin_delete_all_siswa():
    """Hapus seluruh akun login siswa dari sistem (Reset Akun Login Siswa)"""
    conn = get_db()
    count_row = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'siswa'").fetchone()
    total_siswa = count_row[0] if count_row else 0

    if total_siswa == 0:
        conn.close()
        flash("Tidak ada data akun login siswa yang dapat direset.", "warning")
        return redirect(url_for('admin_siswa'))

    # Reset relasi user_id di master_siswa
    conn.execute("UPDATE master_siswa SET user_id = NULL")

    # Hapus semua data yang berelasi dengan akun siswa
    conn.execute("DELETE FROM laporan_penilaian_siswa WHERE siswa_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM siswa_ekskul WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM pengajuan_izin WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM presensi_siswa WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM reset_password_requests WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM users WHERE role = 'siswa'")

    conn.commit()
    conn.close()

    flash(f"Berhasil! Seluruh data akun login siswa ({total_siswa} siswa) telah dihapus dari sistem. Data master pokok siswa MTs tetap tersimpan dan status pendaftaran telah direset.", "success")
    return redirect(url_for('admin_siswa'))

@app.route('/admin/master-siswa/delete-all', methods=['POST'])
@app.route('/admin/siswa/delete-all-total', methods=['POST'])
@role_required('admin')
def admin_delete_all_master_siswa():
    """Hapus seluruh data siswa secara menyeluruh (Master Data MTs + Akun Login + Seluruh Riwayat Siswa) untuk keperluan reset total."""
    conn = get_db()
    cursor = conn.cursor()

    count_master = cursor.execute("SELECT COUNT(*) FROM master_siswa").fetchone()[0]
    count_users = cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'siswa'").fetchone()[0]

    if count_master == 0 and count_users == 0:
        conn.close()
        flash("Tidak ada data siswa yang dapat dihapus (database siswa sudah kosong).", "warning")
        return redirect(request.referrer or url_for('admin_siswa'))

    # Hapus semua data yang berelasi dengan akun siswa
    cursor.execute("DELETE FROM laporan_penilaian_siswa WHERE siswa_id IN (SELECT id FROM users WHERE role = 'siswa')")
    cursor.execute("DELETE FROM siswa_ekskul WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    cursor.execute("DELETE FROM pengajuan_izin WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    cursor.execute("DELETE FROM presensi_siswa WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    cursor.execute("DELETE FROM reset_password_requests WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    cursor.execute("DELETE FROM users WHERE role = 'siswa'")

    # Hapus seluruh basis data pokok master siswa MTs
    cursor.execute("DELETE FROM master_siswa")

    conn.commit()
    conn.close()

    flash(f"Berhasil! Seluruh data siswa ({count_master} data pokok master MTs & {count_users} akun login) beserta seluruh riwayat presensinya telah dihapus dan direset total. Database siswa kini bersih untuk keperluan data baru.", "success")
    return redirect(request.referrer or url_for('admin_siswa'))

@app.route('/admin/master-siswa/tambah', methods=['POST'])
@role_required('admin')
def admin_tambah_master_siswa():
    """Tambah 1 data master siswa MTs Muhammadiyah Tajurhalang secara manual"""
    nis = request.form.get('nis', '').strip()
    nama = request.form.get('nama', '').strip()
    kelas = request.form.get('kelas', 'Kelas 7')
    jk = request.form.get('jenis_kelamin', 'L')
    no_wa = request.form.get('no_whatsapp', '').strip()

    if not nis or not nama:
        flash("NIS dan Nama Siswa wajib diisi!", "danger")
        return redirect(url_for('admin_siswa'))

    conn = get_db()
    try:
        conn.execute("""
        INSERT INTO master_siswa (nis, nama, kelas, jenis_kelamin, no_whatsapp)
        VALUES (?, ?, ?, ?, ?)
        """, (nis, nama, kelas, jk, no_wa or '085111508528'))
        conn.commit()
        flash(f"Siswa '{nama}' (NIS: {nis}) berhasil ditambahkan ke Database Master Siswa MTs Muhammadiyah!", "success")
    except Exception as e:
        flash(f"Gagal menambahkan data: NIS '{nis}' mungkin sudah terdaftar ({e}).", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin_siswa'))

@app.route('/admin/master-siswa/edit', methods=['POST'])
@app.route('/admin/master-siswa/edit/<int:master_id>', methods=['POST'])
@role_required('admin')
def admin_edit_master_siswa(master_id=None):
    """Ubah / Edit data siswa (NIS, Nama, Kelas, Jenis Kelamin, No WhatsApp) secara manual dan sinkronkan ke akun siswa jika terhubung"""
    if not master_id:
        master_id = request.form.get('master_id', type=int)

    nis = request.form.get('nis', '').strip()
    nama = request.form.get('nama', '').strip()
    kelas = request.form.get('kelas', 'Kelas 7').strip()
    jk = request.form.get('jenis_kelamin', 'L').strip()
    no_wa = request.form.get('no_whatsapp', '').strip()
    username = request.form.get('username', '').strip()

    if not master_id or not nis or not nama:
        flash("ID Siswa, NIS, dan Nama Siswa wajib diisi!", "danger")
        return redirect(url_for('admin_siswa'))

    conn = get_db()
    m = conn.execute("SELECT * FROM master_siswa WHERE id = ?", (master_id,)).fetchone()
    if not m:
        conn.close()
        flash("Data siswa tidak ditemukan dalam basis data master!", "danger")
        return redirect(url_for('admin_siswa'))

    # Cek keunikan NIS terhadap siswa master lain
    duplikat_nis = conn.execute(
        "SELECT id, nama FROM master_siswa WHERE nis = ? AND id != ?",
        (nis, master_id)
    ).fetchone()
    if duplikat_nis:
        conn.close()
        flash(f"Gagal: NIS '{nis}' sudah terdaftar untuk siswa '{duplikat_nis['nama']}'. Silakan gunakan NIS lain.", "danger")
        return redirect(url_for('admin_siswa'))

    try:
        # Perbarui tabel master_siswa
        conn.execute("""
        UPDATE master_siswa
        SET nis = ?, nama = ?, kelas = ?, jenis_kelamin = ?, no_whatsapp = ?
        WHERE id = ?
        """, (nis, nama, kelas, jk, no_wa, master_id))

        # Jika siswa sudah memiliki akun login (user_id terhubung), sinkronkan data ke tabel users
        if m['user_id']:
            conn.execute("""
            UPDATE users
            SET nama = ?, kelas = ?, nisn = ?, jenis_kelamin = ?, no_hp = ?
            WHERE id = ?
            """, (nama, kelas, nis, jk, no_wa, m['user_id']))

            # Jika username juga diubah, periksa keunikan lalu update
            if username:
                dup_user = conn.execute(
                    "SELECT id FROM users WHERE username = ? AND id != ?",
                    (username, m['user_id'])
                ).fetchone()
                if dup_user:
                    flash(f"Data siswa diperbarui, namun username '@{username}' sudah dipakai pengguna lain.", "warning")
                else:
                    conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, m['user_id']))

        conn.commit()
        flash(f"Data siswa '{nama}' (NIS: {nis}) berhasil diperbarui dan disinkronkan secara aman!", "success")
    except Exception as e:
        flash(f"Terjadi kesalahan saat menyimpan perubahan data siswa: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin_siswa'))

@app.route('/admin/master-siswa/delete/<int:master_id>', methods=['POST'])
@role_required('admin')
def admin_delete_master_siswa(master_id):
    """Hapus siswa dari Master Siswa MTs Muhammadiyah"""
    conn = get_db()
    m = conn.execute("SELECT * FROM master_siswa WHERE id = ?", (master_id,)).fetchone()
    if m:
        if m['user_id']:
            user_id = m['user_id']
            conn.execute("DELETE FROM laporan_penilaian_siswa WHERE siswa_id = ?", (user_id,))
            conn.execute("DELETE FROM siswa_ekskul WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM pengajuan_izin WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM presensi_siswa WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM reset_password_requests WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM master_siswa WHERE id = ?", (master_id,))
        conn.commit()
        flash(f"Data siswa '{m['nama']}' berhasil dihapus dari Master Siswa MTs Muhammadiyah.", "success")
    conn.close()
    return redirect(url_for('admin_siswa'))

@app.route('/admin/pelatih/delete/<int:user_id>', methods=['POST'])
@role_required('admin')
def admin_delete_pelatih(user_id):
    """Hapus akun pelatih"""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'pelatih'", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash("Akun pelatih tidak ditemukan.", "danger")
        return redirect(url_for('admin_pelatih'))

    # Kosongkan nama pelatih di tabel ekskul yang dipegang
    conn.execute("""
    UPDATE ekskul SET pelatih_nama = 'Belum Ada' 
    WHERE id IN (SELECT ekskul_id FROM pelatih_ekskul WHERE user_id = ?)
       OR id = ?
    """, (user_id, user['ekskul_id']))

    conn.execute("DELETE FROM pelatih_ekskul WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM reset_password_requests WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()
    flash(f"Akun pelatih '{user['nama']}' ({user['username']}) berhasil dihapus.", "success")
    return redirect(url_for('admin_pelatih'))

@app.route('/admin/sesi/delete/<int:sesi_id>', methods=['POST'])
@role_required('admin')
def admin_delete_sesi(sesi_id):
    """Hapus satu sesi latihan beserta data presensinya (Admin Master)"""
    conn = get_db()
    sesi = conn.execute("""
    SELECT s.*, e.nama as nama_ekskul
    FROM sesi_latihan s
    JOIN ekskul e ON s.ekskul_id = e.id
    WHERE s.id = ?
    """, (sesi_id,)).fetchone()

    if not sesi:
        conn.close()
        flash("Sesi latihan tidak ditemukan.", "danger")
        return redirect(url_for('admin_dashboard'))

    conn.execute("DELETE FROM presensi_siswa WHERE sesi_id = ?", (sesi_id,))
    conn.execute("DELETE FROM sesi_latihan WHERE id = ?", (sesi_id,))
    conn.commit()
    conn.close()

    flash(f"Sesi latihan '{sesi['nama_ekskul']}' tanggal {sesi['tanggal']} berhasil dihapus dari sistem.", "success")
    
    referer = request.referrer or ''
    if '/sesi/' in referer or f'/riwayat/{sesi_id}' in referer:
        return redirect(url_for('riwayat'))
    return redirect(referer or url_for('admin_dashboard'))

@app.route('/admin/sesi/delete-all', methods=['POST'])
@role_required('admin')
def admin_delete_all_sesi():
    """Hapus seluruh riwayat sesi latihan beserta data presensinya (Bulk Delete)"""
    conn = get_db()
    count_row = conn.execute("SELECT COUNT(*) FROM sesi_latihan").fetchone()
    total_sesi = count_row[0] if count_row else 0

    if total_sesi == 0:
        conn.close()
        flash("Tidak ada riwayat sesi latihan yang dapat dihapus.", "warning")
        return redirect(request.referrer or url_for('admin_dashboard'))

    conn.execute("DELETE FROM presensi_siswa")
    conn.execute("DELETE FROM sesi_latihan")
    conn.commit()
    conn.close()

    flash(f"Berhasil! Seluruh riwayat sesi latihan ({total_sesi} sesi) beserta data presensinya telah dihapus dari sistem.", "success")
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/ekskul/tambah', methods=['POST'])
@role_required('admin')
def admin_tambah_ekskul():
    nama = request.form.get('nama', '').strip()
    kategori = request.form.get('kategori', 'Olahraga').strip()
    icon = request.form.get('icon', '🏅').strip()
    hari = request.form.get('hari_latihan', '').strip()
    jam = request.form.get('jam_latihan', '').strip()
    pelatih = request.form.get('pelatih_nama', '').strip()
    deskripsi = request.form.get('deskripsi', '').strip()

    if nama:
        conn = get_db()
        try:
            conn.execute("""
            INSERT INTO ekskul (nama, kategori, icon, hari_latihan, jam_latihan, pelatih_nama, deskripsi)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nama, kategori, icon, hari, jam, pelatih, deskripsi))
            conn.commit()
            flash(f"Cabang Ekskul '{nama}' berhasil ditambahkan!", "success")
        except Exception:
            flash(f"Ekskul '{nama}' sudah ada di database.", "danger")
        conn.close()
    return redirect(url_for('admin_ekskul_gps'))

@app.route('/admin/pelatih/tambah', methods=['POST'])
@role_required('admin')
def admin_tambah_pelatih():
    nama = request.form.get('nama', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    ekskul_ids = request.form.getlist('ekskul_ids')

    # Fallback jika hanya 1 ekskul_id dikirim
    if not ekskul_ids and request.form.get('ekskul_id'):
        ekskul_ids = [request.form.get('ekskul_id')]

    if not nama or not username or not password:
        flash("Nama, username, dan kata sandi wajib diisi.", "danger")
        return redirect(url_for('admin_pelatih'))

    if not ekskul_ids:
        flash("Pilih minimal satu cabang ekstrakurikuler yang diampu oleh pelatih/guru ini.", "warning")
        return redirect(url_for('admin_pelatih'))

    primary_ekskul = ekskul_ids[0]

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO users (username, password, nama, role, ekskul_id)
        VALUES (?, ?, ?, 'pelatih', ?)
        """, (username, password, nama, primary_ekskul))
        new_user_id = cursor.lastrowid

        for eid in ekskul_ids:
            cursor.execute("""
            INSERT OR IGNORE INTO pelatih_ekskul (user_id, ekskul_id)
            VALUES (?, ?)
            """, (new_user_id, eid))
            cursor.execute("UPDATE ekskul SET pelatih_nama = ? WHERE id = ?", (nama, eid))

        conn.commit()
        flash(f"Akun Pelatih '{nama}' berhasil dibuat dan memegang {len(ekskul_ids)} cabang ekskul!", "success")
    except Exception as e:
        flash(f"Gagal membuat akun: Username '{username}' sudah digunakan ({e}).", "danger")
    conn.close()
    return redirect(url_for('admin_pelatih'))

@app.route('/admin/pelatih/update-ekskul', methods=['POST'])
@role_required('admin')
def admin_update_ekskul_pelatih():
    """Ubah cabang ekskul yang diampu oleh pelatih yang sudah terdaftar"""
    user_id = request.form.get('user_id')
    ekskul_ids = request.form.getlist('ekskul_ids')

    if not user_id:
        flash("ID Pelatih tidak valid.", "danger")
        return redirect(url_for('admin_pelatih'))

    if not ekskul_ids:
        flash("Pilih minimal satu cabang ekskul untuk pelatih ini.", "warning")
        return redirect(url_for('admin_pelatih'))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'pelatih'", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash("Akun pelatih tidak ditemukan.", "danger")
        return redirect(url_for('admin_pelatih'))

    primary_ekskul = ekskul_ids[0]
    conn.execute("UPDATE users SET ekskul_id = ? WHERE id = ?", (primary_ekskul, user_id))
    
    # Hapus penetapan ekskul lama dan masukkan yang baru
    conn.execute("DELETE FROM pelatih_ekskul WHERE user_id = ?", (user_id,))
    for eid in ekskul_ids:
        conn.execute("INSERT OR IGNORE INTO pelatih_ekskul (user_id, ekskul_id) VALUES (?, ?)", (user_id, eid))
        conn.execute("UPDATE ekskul SET pelatih_nama = ? WHERE id = ?", (user['nama'], eid))

    conn.commit()
    conn.close()
    flash(f"Cabang ekskul yang diampu pelatih '{user['nama']}' berhasil diperbarui ({len(ekskul_ids)} ekskul)!", "success")
    return redirect(url_for('admin_pelatih'))

@app.route('/admin/siswa/import', methods=['POST'])
@role_required('admin')
def admin_import_siswa():
    """Mengimpor data Master Siswa MTs Muhammadiyah Tajurhalang dari berkas CSV (NIS, Nama, Kelas, Jenis Kelamin, No WhatsApp)."""
    file = request.files.get('file_siswa')
    if not file or file.filename == '':
        flash("Silakan pilih berkas CSV untuk diimpor.", "danger")
        return redirect(url_for('admin_siswa'))

    try:
        raw_bytes = file.stream.read()
        try:
            content = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw_bytes.decode("latin-1", errors='ignore')

        if not content.strip():
            flash("Berkas CSV kosong atau tidak dapat dibaca.", "danger")
            return redirect(url_for('admin_siswa'))

        # Deteksi delimiter (; untuk Excel Indonesia, , untuk standar)
        sample = content[:2048]
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
        
        stream = io.StringIO(content, newline=None)
        csv_reader = csv.reader(stream, delimiter=delimiter)
        
        conn = get_db()
        cursor = conn.cursor()
        
        count_processed = 0
        for i, row in enumerate(csv_reader):
            if not row or len(row) < 2:
                continue
            
            # Lewati baris header jika terdapat kata kunci
            if i == 0 and any(keyword in str(row[0]).lower() for keyword in ['nis', 'nama', 'name', 'no', 'siswa', 'id']):
                continue
            
            # Format 5 Kolom: NIS, Nama, Kelas, Jenis Kelamin, No WhatsApp
            col0 = str(row[0]).strip()
            col1 = str(row[1]).strip() if len(row) > 1 else ''
            
            # Deteksi apakah format standar (kolom 0 = NIS) atau lama (kolom 0 = Nama)
            if col0.isdigit() or (len(row) >= 3 and any(k in str(row[2]).lower() for k in ['kelas', '7', '8', '9'])):
                nis = col0
                nama = col1
                kelas_raw = str(row[2]).strip() if len(row) > 2 else 'Kelas 7'
                jk_raw = str(row[3]).strip() if len(row) > 3 else 'L'
                no_wa_raw = str(row[4]).strip() if len(row) > 4 else ''
            else:
                # Format cadangan: Nama, Kelas, JK
                nama = col0
                kelas_raw = col1
                jk_raw = str(row[2]).strip() if len(row) > 2 else 'L'
                no_wa_raw = ''
                nis = f"10{cursor.execute('SELECT COUNT(*) FROM master_siswa').fetchone()[0] + 101}"

            if not nama:
                continue

            # Normalisasi Kelas
            if '8' in kelas_raw:
                kelas_clean = 'Kelas 8'
            elif '9' in kelas_raw:
                kelas_clean = 'Kelas 9'
            else:
                kelas_clean = 'Kelas 7'

            # Normalisasi Jenis Kelamin
            jk_upper = jk_raw.upper().strip()
            if jk_upper.startswith('P') or 'PEREMPUAN' in jk_upper:
                jk_clean = 'P'
            else:
                jk_clean = 'L'

            # Normalisasi Nomor WhatsApp
            no_wa_clean = "".join(ch for ch in no_wa_raw if ch.isdigit() or ch == '+')
            if not no_wa_clean:
                no_wa_clean = '085111508528'

            # Masukkan atau perbarui ke tabel master_siswa
            cursor.execute("""
            INSERT INTO master_siswa (nis, nama, kelas, jenis_kelamin, no_whatsapp)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(nis) DO UPDATE SET
                nama = excluded.nama,
                kelas = excluded.kelas,
                jenis_kelamin = excluded.jenis_kelamin,
                no_whatsapp = excluded.no_whatsapp
            """, (nis, nama, kelas_clean, jk_clean, no_wa_clean))
            count_processed += 1

        conn.commit()
        conn.close()
        flash(f"Berhasil mengimpor / memperbarui {count_processed} data Master Siswa MTs Muhammadiyah Tajurhalang dari berkas CSV!", "success")
    except Exception as e:
        flash(f"Gagal memproses berkas CSV: {e}", "danger")

    return redirect(url_for('admin_siswa'))

@app.route('/admin/template-csv')
@role_required('admin')
def admin_template_csv():
    """Mengunduh berkas template CSV contoh master data siswa MTs Muhammadiyah Tajurhalang."""
    # Sertakan UTF-8 BOM (\ufeff) agar terbaca langsung dengan kolom rapi di Microsoft Excel
    csv_content = "\ufeffNIS,Nama,Kelas,Jenis Kelamin,No WhatsApp\n" \
                  "1071,Ahmad Fadhil,Kelas 7,L,081234567801\n" \
                  "1072,Annisa Rahmadani,Kelas 7,P,081234567802\n" \
                  "1073,Bintang Pratama,Kelas 8,L,081234567803\n" \
                  "1074,Citra Khairunnisa,Kelas 8,P,081234567804\n" \
                  "1075,Danu Wijaya,Kelas 9,L,081234567805\n" \
                  "1076,Farah Diba,Kelas 9,P,081234567806\n"
    
    return Response(
        csv_content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": "attachment; filename=template_master_siswa_mts.csv"}
    )

@app.route('/admin/lokasi/update', methods=['POST'])
@role_required('admin')
def admin_update_lokasi():
    nama = request.form.get('nama_lokasi', '').strip()
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    radius = request.form.get('radius_meter', 250)

    if nama and lat and lng:
        conn = get_db()
        conn.execute("UPDATE pengaturan_lokasi SET is_active = 0")
        conn.execute("""
        INSERT INTO pengaturan_lokasi (nama_lokasi, latitude, longitude, radius_meter, is_active)
        VALUES (?, ?, ?, ?, 1)
        """, (nama, float(lat), float(lng), int(radius)))
        conn.commit()
        conn.close()
        flash("Titik koordinat GPS lapangan madrasah berhasil diperbarui!", "success")
    return redirect(url_for('admin_ekskul_gps'))

# =========================================================
# PENGATURAN PEJABAT PENANDATANGAN LAPORAN (KAMAD, BENDAHARA, TU, WAKA)
# =========================================================

@app.route('/admin/pejabat')
@app.route('/admin/pengaturan-laporan')
@role_required('admin')
def admin_pejabat():
    """Halaman Pengaturan Pejabat Penandatangan Laporan (Kamad, Bendahara, Staf TU, Waka Kesiswaan)."""
    conn = get_db()
    current_admin = conn.execute("SELECT * FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()
    pejabat = get_pengaturan_laporan(conn)
    reset_requests = conn.execute("SELECT * FROM reset_password_requests WHERE status = 'PENDING'").fetchall()
    
    # Ambil sampel laporan bulanan jika ada untuk tombol preview cetak
    sample_laporan = conn.execute("SELECT id FROM laporan_bulanan ORDER BY id DESC LIMIT 1").fetchone()
    sample_sesi = conn.execute("SELECT id FROM sesi_latihan ORDER BY id DESC LIMIT 1").fetchone()
    
    conn.close()
    return render_template('admin_pejabat.html',
                           current_admin=current_admin,
                           pejabat=pejabat,
                           reset_requests=reset_requests,
                           sample_laporan_id=sample_laporan['id'] if sample_laporan else None,
                           sample_sesi_id=sample_sesi['id'] if sample_sesi else None,
                           active_menu='pejabat')

@app.route('/admin/pejabat/simpan', methods=['POST'])
@role_required('admin')
def admin_simpan_pejabat():
    """Menyimpan pembaruan data pejabat penandatangan laporan."""
    nama_kamad = request.form.get('nama_kamad', '').strip()
    nbm_kamad = request.form.get('nbm_kamad', '').strip()
    jabatan_kamad = request.form.get('jabatan_kamad', 'Kepala MTs Muhammadiyah Tajurhalang').strip()

    nama_bendahara = request.form.get('nama_bendahara', '').strip()
    nbm_bendahara = request.form.get('nbm_bendahara', '').strip()
    jabatan_bendahara = request.form.get('jabatan_bendahara', 'Bendahara Madrasah').strip()

    nama_staff_tu = request.form.get('nama_staff_tu', '').strip()
    nbm_staff_tu = request.form.get('nbm_staff_tu', '').strip()
    jabatan_staff_tu = request.form.get('jabatan_staff_tu', 'Staf Tata Usaha').strip()

    nama_waka_kesiswaan = request.form.get('nama_waka_kesiswaan', '').strip()
    nbm_waka_kesiswaan = request.form.get('nbm_waka_kesiswaan', '').strip()
    jabatan_waka_kesiswaan = request.form.get('jabatan_waka_kesiswaan', 'Waka Kesiswaan MTs Muhammadiyah').strip()

    kota_tanda_tangan = request.form.get('kota_tanda_tangan', 'Tajurhalang').strip()

    if not nama_kamad or not nama_bendahara or not nama_staff_tu:
        flash("Nama Kepala Madrasah, Bendahara, dan Staf TU wajib diisi!", "danger")
        return redirect(url_for('admin_pejabat'))

    conn = get_db()
    existing = conn.execute("SELECT id FROM pengaturan_laporan ORDER BY id DESC LIMIT 1").fetchone()
    if existing:
        conn.execute("""
        UPDATE pengaturan_laporan SET
            nama_kamad = ?,
            nbm_kamad = ?,
            jabatan_kamad = ?,
            nama_bendahara = ?,
            nbm_bendahara = ?,
            jabatan_bendahara = ?,
            nama_staff_tu = ?,
            nbm_staff_tu = ?,
            jabatan_staff_tu = ?,
            nama_waka_kesiswaan = ?,
            nbm_waka_kesiswaan = ?,
            jabatan_waka_kesiswaan = ?,
            kota_tanda_tangan = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (
            nama_kamad, nbm_kamad, jabatan_kamad,
            nama_bendahara, nbm_bendahara, jabatan_bendahara,
            nama_staff_tu, nbm_staff_tu, jabatan_staff_tu,
            nama_waka_kesiswaan, nbm_waka_kesiswaan, jabatan_waka_kesiswaan,
            kota_tanda_tangan, existing['id']
        ))
    else:
        conn.execute("""
        INSERT INTO pengaturan_laporan (
            nama_kamad, nbm_kamad, jabatan_kamad,
            nama_bendahara, nbm_bendahara, jabatan_bendahara,
            nama_staff_tu, nbm_staff_tu, jabatan_staff_tu,
            nama_waka_kesiswaan, nbm_waka_kesiswaan, jabatan_waka_kesiswaan,
            kota_tanda_tangan
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nama_kamad, nbm_kamad, jabatan_kamad,
            nama_bendahara, nbm_bendahara, jabatan_bendahara,
            nama_staff_tu, nbm_staff_tu, jabatan_staff_tu,
            nama_waka_kesiswaan, nbm_waka_kesiswaan, jabatan_waka_kesiswaan,
            kota_tanda_tangan
        ))
    conn.commit()
    conn.close()

    flash("Data pejabat penandatangan laporan (Kamad, Bendahara, Staf TU, Waka Kesiswaan) berhasil disimpan dan telah terintegrasi ke seluruh hasil cetak laporan!", "success")
    return redirect(url_for('admin_pejabat'))

# =========================================================
# API & PRESENSI UMUM (GEOFENCE & SUBMISSION)
# =========================================================

@app.route('/api/lokasi/cek', methods=['POST'])
def cek_lokasi():
    data = request.get_json() or {}
    user_lat = float(data.get('latitude', 0))
    user_lng = float(data.get('longitude', 0))

    conn = get_db()
    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()
    conn.close()

    if not lokasi:
        return jsonify({'status': 'ERROR', 'pesan': 'Titik lokasi belum disetel'}), 400

    jarak = haversine(user_lat, user_lng, lokasi['latitude'], lokasi['longitude'])
    is_valid = jarak <= lokasi['radius_meter']

    return jsonify({
        'jarak_meter': jarak,
        'radius_meter': lokasi['radius_meter'],
        'nama_lokasi': lokasi['nama_lokasi'],
        'is_valid': is_valid,
        'status': 'VALID' if is_valid else 'DILUAR_AREA',
        'pesan': f"Anda berada {jarak} meter dari titik {lokasi['nama_lokasi']}."
    })

@app.route('/api/presensi/simpan', methods=['POST'])
@login_required
def simpan_presensi():
    data = request.get_json() or {}

    ekskul_id = data.get('ekskul_id')
    pelatih_id = session.get('user_id')
    nama_pelatih = session.get('nama')
    tanggal = data.get('tanggal') or get_wib_today_str()
    jam_mulai = data.get('jam_mulai') or get_wib_time_str()
    materi_latihan = data.get('materi_latihan', '').strip()
    catatan = data.get('catatan', '').strip()

    user_lat = float(data.get('latitude') or 0)
    user_lng = float(data.get('longitude') or 0)

    presensi_list = data.get('presensi_siswa', [])

    conn = get_db()
    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()

    jarak = 0
    status_lokasi = 'VALID'
    if lokasi and user_lat != 0 and user_lng != 0:
        jarak = haversine(user_lat, user_lng, lokasi['latitude'], lokasi['longitude'])
        status_lokasi = 'VALID' if jarak <= lokasi['radius_meter'] else 'DILUAR_AREA'

    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sesi_latihan (
        ekskul_id, pelatih_id, nama_pelatih, tanggal, jam_mulai, 
        lokasi_lat, lokasi_lng, jarak_meter, status_lokasi, 
        materi_latihan, catatan
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ekskul_id, pelatih_id, nama_pelatih, tanggal, jam_mulai,
        user_lat, user_lng, jarak, status_lokasi,
        materi_latihan, catatan
    ))

    sesi_id = cursor.lastrowid

    for item in presensi_list:
        cursor.execute("""
        INSERT INTO presensi_siswa (sesi_id, user_id, status_kehadiran, keterangan)
        VALUES (?, ?, ?, ?)
        """, (sesi_id, item['siswa_id'], item.get('status_kehadiran', 'Hadir'), item.get('keterangan', '')))

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'SUCCESS',
        'pesan': 'Presensi latihan berhasil disimpan!',
        'sesi_id': sesi_id
    })

@app.route('/cetak/<int:sesi_id>')
@login_required
def cetak_sesi(sesi_id):
    conn = get_db()
    sesi = conn.execute("""
    SELECT s.*, e.nama as nama_ekskul, e.icon as icon_ekskul, e.kategori
    FROM sesi_latihan s
    JOIN ekskul e ON s.ekskul_id = e.id
    WHERE s.id = ?
    """, (sesi_id,)).fetchone()

    if not sesi:
        conn.close()
        return "Sesi tidak ditemukan", 404

    presensi = conn.execute("""
    SELECT ps.*, u.nama, u.kelas, u.jenis_kelamin
    FROM presensi_siswa ps
    JOIN users u ON ps.user_id = u.id
    WHERE ps.sesi_id = ?
    ORDER BY u.kelas ASC, u.nama ASC
    """, (sesi_id,)).fetchall()

    pejabat = get_pengaturan_laporan(conn)
    conn.close()
    return render_template('cetak.html', sesi=sesi, presensi=presensi, pejabat=pejabat)

@app.route('/export-csv/<int:ekskul_id>')
@login_required
def export_csv(ekskul_id):
    conn = get_db()
    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (ekskul_id,)).fetchone()

    rekap_siswa = conn.execute("""
    SELECT u.nama, u.kelas, u.jenis_kelamin,
           COUNT(ps.id) as total_sesi,
           SUM(CASE WHEN ps.status_kehadiran = 'Hadir' THEN 1 ELSE 0 END) as hadir,
           SUM(CASE WHEN ps.status_kehadiran = 'Izin' THEN 1 ELSE 0 END) as izin,
           SUM(CASE WHEN ps.status_kehadiran = 'Sakit' THEN 1 ELSE 0 END) as sakit,
           SUM(CASE WHEN ps.status_kehadiran = 'Alpa' THEN 1 ELSE 0 END) as alpa
    FROM users u
    JOIN siswa_ekskul se ON u.id = se.user_id
    LEFT JOIN presensi_siswa ps ON u.id = ps.user_id
    WHERE se.ekskul_id = ? AND u.role = 'siswa' AND se.status = 'AKTIF'
    GROUP BY u.id
    ORDER BY u.kelas ASC, u.nama ASC
    """, (ekskul_id,)).fetchall()

    pejabat = get_pengaturan_laporan(conn)
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["REKAPITULASI PRESENSI EKSTRAKURIKULER", ekskul['nama'] if ekskul else ''])
    cw.writerow(["MTs Muhammadiyah Tajurhalang Bogor"])
    cw.writerow(["Tanggal Cetak", datetime.now().strftime("%d-%m-%Y %H:%M")])
    cw.writerow([])
    cw.writerow(["No", "Nama Siswa", "Kelas", "L/P", "Hadir", "Izin", "Sakit", "Alpa", "% Kehadiran"])

    for idx, r in enumerate(rekap_siswa, 1):
        total = (r['hadir'] or 0) + (r['izin'] or 0) + (r['sakit'] or 0) + (r['alpa'] or 0)
        persen = round(((r['hadir'] or 0) / total) * 100, 1) if total > 0 else 0
        cw.writerow([idx, r['nama'], r['kelas'], r['jenis_kelamin'], r['hadir'] or 0, r['izin'] or 0, r['sakit'] or 0, r['alpa'] or 0, f"{persen}%"])

    # Blok Tanda Tangan & Pengesahan Pejabat Madrasah di Hasil Unduhan Excel
    cw.writerow([])
    cw.writerow(["PENGESAHAN LAPORAN PRESENSI"])
    cw.writerow([f"{pejabat.get('kota_tanda_tangan', 'Tajurhalang')}, {datetime.now().strftime('%d-%m-%Y')}"])
    cw.writerow([])
    cw.writerow(["Mengetahui / Memverifikasi:", "", "Verifikasi Administrasi & Honor:", "", "Menyetujui:"])
    cw.writerow([
        pejabat.get('jabatan_waka_kesiswaan', 'Waka Kesiswaan'),
        "",
        f"{pejabat.get('jabatan_staff_tu', 'Staf TU')} & {pejabat.get('jabatan_bendahara', 'Bendahara')}",
        "",
        pejabat.get('jabatan_kamad', 'Kepala Madrasah')
    ])
    cw.writerow([])
    cw.writerow([])
    cw.writerow([
        pejabat.get('nama_waka_kesiswaan', ''),
        "",
        f"{pejabat.get('nama_staff_tu', '')} / {pejabat.get('nama_bendahara', '')}",
        "",
        pejabat.get('nama_kamad', '')
    ])
    cw.writerow([
        pejabat.get('nbm_waka_kesiswaan', ''),
        "",
        f"{pejabat.get('nbm_staff_tu', '')} / {pejabat.get('nbm_bendahara', '')}",
        "",
        pejabat.get('nbm_kamad', '')
    ])

    output = '\ufeff' + si.getvalue()
    nama_file = f"Rekap_Presensi_{ekskul['nama'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        output,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename={nama_file}"}
    )

# =========================================================
# REKAPITULASI & RIWAYAT SESI LATIHAN (ADMIN & PELATIH)
# =========================================================

@app.route('/rekap')
@app.route('/rekap/<int:ekskul_id>')
@login_required
def rekap(ekskul_id=None):
    """Halaman Rekapitulasi Presensi Anggota Ekskul"""
    conn = get_db()
    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()

    if not ekskul_list:
        conn.close()
        flash("Belum ada cabang ekstrakurikuler yang terdaftar.", "warning")
        return redirect(url_for('index'))

    # Ambil ekskul_id dari argumen query atau parameter rute atau ekskul pertama
    if not ekskul_id:
        ekskul_id = request.args.get('ekskul_id', type=int) or ekskul_list[0]['id']

    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (ekskul_id,)).fetchone()
    if not ekskul:
        ekskul = ekskul_list[0]
        ekskul_id = ekskul['id']

    rekap_siswa = conn.execute("""
    SELECT u.id, u.nama, u.kelas, u.jenis_kelamin,
           COUNT(ps.id) as total_sesi,
           SUM(CASE WHEN ps.status_kehadiran = 'Hadir' THEN 1 ELSE 0 END) as hadir,
           SUM(CASE WHEN ps.status_kehadiran = 'Izin' THEN 1 ELSE 0 END) as izin,
           SUM(CASE WHEN ps.status_kehadiran = 'Sakit' THEN 1 ELSE 0 END) as sakit,
           SUM(CASE WHEN ps.status_kehadiran = 'Alpa' THEN 1 ELSE 0 END) as alpa
    FROM users u
    LEFT JOIN siswa_ekskul se ON u.id = se.user_id AND se.status = 'AKTIF'
    LEFT JOIN presensi_siswa ps ON u.id = ps.user_id AND ps.sesi_id IN (SELECT id FROM sesi_latihan WHERE ekskul_id = ?)
    WHERE (se.ekskul_id = ? OR u.ekskul_id = ?) AND u.role = 'siswa'
    GROUP BY u.id
    ORDER BY u.kelas ASC, u.nama ASC
    """, (ekskul_id, ekskul_id, ekskul_id)).fetchall()

    total_latihan = conn.execute("SELECT COUNT(*) FROM sesi_latihan WHERE ekskul_id = ?", (ekskul_id,)).fetchone()[0]
    conn.close()

    return render_template('rekap.html',
                           ekskul=ekskul,
                           ekskul_list=ekskul_list,
                           rekap_siswa=rekap_siswa,
                           total_latihan=total_latihan)

@app.route('/riwayat')
@login_required
def riwayat():
    """Daftar riwayat sesi latihan ekstrakurikuler"""
    ekskul_id = request.args.get('ekskul_id', type=int)
    conn = get_db()

    query = """
    SELECT s.*, e.nama as nama_ekskul, e.icon as icon_ekskul,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Izin') as total_izin,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Sakit') as total_sakit,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Alpa') as total_alpa,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
    FROM sesi_latihan s
    JOIN ekskul e ON s.ekskul_id = e.id
    """
    params = []
    if ekskul_id:
        query += " WHERE s.ekskul_id = ?"
        params.append(ekskul_id)

    query += " ORDER BY s.tanggal DESC, s.jam_mulai DESC LIMIT 50"

    sesi_list = conn.execute(query, params).fetchall()
    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    conn.close()

    return render_template('riwayat.html',
                           sesi_list=sesi_list,
                           ekskul_list=ekskul_list,
                           selected_ekskul=ekskul_id)

@app.route('/riwayat/<int:sesi_id>')
@app.route('/sesi/<int:sesi_id>')
@login_required
def detail_sesi(sesi_id):
    """Detail satu sesi latihan beserta daftar presensi siswa"""
    conn = get_db()
    sesi = conn.execute("""
    SELECT s.*, e.nama as nama_ekskul, e.icon as icon_ekskul, e.kategori
    FROM sesi_latihan s
    JOIN ekskul e ON s.ekskul_id = e.id
    WHERE s.id = ?
    """, (sesi_id,)).fetchone()

    if not sesi:
        conn.close()
        flash("Sesi latihan tidak ditemukan.", "warning")
        return redirect(url_for('riwayat'))

    presensi = conn.execute("""
    SELECT ps.*, u.nama, u.kelas, u.jenis_kelamin
    FROM presensi_siswa ps
    JOIN users u ON ps.user_id = u.id
    WHERE ps.sesi_id = ?
    ORDER BY u.kelas ASC, u.nama ASC
    """, (sesi_id,)).fetchall()

    conn.close()
    return render_template('detail_sesi.html', sesi=sesi, presensi=presensi)

if __name__ == '__main__':
    print("Memulai Server Presensi Ekskul Multi-Role MTs Muhammadiyah Tajurhalang...")
    app.run(host='0.0.0.0', port=5000, debug=False)
