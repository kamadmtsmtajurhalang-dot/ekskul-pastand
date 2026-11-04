import os
import math
import csv
import io
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, session, Response, flash, send_from_directory
)
from database import get_db, init_db

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
        nama = request.form.get('nama', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        kelas = request.form.get('kelas', 'Kelas 7')
        jk = request.form.get('jenis_kelamin', 'L')
        ekskul_id = request.form.get('ekskul_id')

        if not nama or not username or not password or not ekskul_id:
            flash("Semua kolom wajib diisi!", "danger")
        else:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO users (username, password, nama, role, ekskul_id, kelas, jenis_kelamin)
                VALUES (?, ?, ?, 'siswa', ?, ?, ?)
                """, (username, password, nama, ekskul_id, kelas, jk))
                new_user_id = cursor.lastrowid
                
                # Masukkan ke relasi siswa_ekskul
                cursor.execute("""
                INSERT INTO siswa_ekskul (user_id, ekskul_id) VALUES (?, ?)
                """, (new_user_id, ekskul_id))
                
                conn.commit()
                conn.close()
                flash("Pendaftaran berhasil! Silakan login dengan username dan kata sandi Anda.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                flash(f"Pendaftaran gagal: Username '{username}' mungkin sudah digunakan.", "danger")
    
    conn.close()
    return render_template('register_siswa.html', ekskul_list=ekskul_list)

# =========================================================
# 1. AKUN PELATIH (CLEAN UI & KHUSUS EKSKULNYA SAJA)
# =========================================================

@app.route('/pelatih')
@role_required('pelatih')
def pelatih_dashboard():
    pelatih_id = session['user_id']
    conn = get_db()
    
    # Ambil data pelatih
    user = conn.execute("SELECT * FROM users WHERE id = ?", (pelatih_id,)).fetchone()
    
    # Ambil seluruh cabang ekskul yang diampu oleh pelatih ini
    assigned_ekskuls = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN pelatih_ekskul pe ON e.id = pe.ekskul_id
    WHERE pe.user_id = ?
    ORDER BY e.nama ASC
    """, (pelatih_id,)).fetchall()

    # Fallback jika belum di pelatih_ekskul tapi ada ekskul_id di users
    if not assigned_ekskuls and user['ekskul_id']:
        assigned_ekskuls = conn.execute("SELECT * FROM ekskul WHERE id = ?", (user['ekskul_id'],)).fetchall()

    if not assigned_ekskuls:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini. Silakan hubungi Admin Master.", 400

    # Tentukan cabang ekskul yang sedang aktif dibuka
    active_ekskul_id = request.args.get('ekskul_id', type=int)
    ekskul = None
    if active_ekskul_id:
        for e in assigned_ekskuls:
            if e['id'] == active_ekskul_id:
                ekskul = e
                break
    if not ekskul:
        ekskul = assigned_ekskuls[0]

    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()

    # Ambil daftar siswa yang memilih ekskul ini
    siswa_list = conn.execute("""
    SELECT u.* FROM users u
    JOIN siswa_ekskul se ON u.id = se.user_id
    WHERE se.ekskul_id = ? AND u.role = 'siswa' AND se.status = 'AKTIF'
    ORDER BY u.kelas ASC, u.nama ASC
    """, (ekskul['id'],)).fetchall()

    # Ambil permohonan izin pra-presensi siswa hari ini
    today_str = datetime.now().strftime('%Y-%m-%d')
    pengajuan_izin = conn.execute("""
    SELECT p.*, u.nama as nama_siswa, u.kelas 
    FROM pengajuan_izin p
    JOIN users u ON p.user_id = u.id
    WHERE p.ekskul_id = ? AND p.tanggal_latihan = ?
    ORDER BY p.created_at DESC
    """, (ekskul['id'], today_str)).fetchall()

    # Riwayat sesi latihan pelatih untuk ekskul ini
    sesi_terakhir = conn.execute("""
    SELECT s.*, 
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id AND ps.status_kehadiran = 'Hadir') as total_hadir,
           (SELECT COUNT(*) FROM presensi_siswa ps WHERE ps.sesi_id = s.id) as total_peserta
    FROM sesi_latihan s
    WHERE s.ekskul_id = ?
    ORDER BY s.tanggal DESC, s.jam_mulai DESC LIMIT 5
    """, (ekskul['id'],)).fetchall()

    conn.close()
    return render_template('pelatih_dashboard.html', 
                           user=user, 
                           ekskul=ekskul, 
                           assigned_ekskuls=assigned_ekskuls,
                           lokasi=lokasi, 
                           siswa_list=siswa_list,
                           pengajuan_izin=pengajuan_izin,
                           sesi_terakhir=sesi_terakhir,
                           today_str=today_str)

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
    return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id))

@app.route('/pelatih/pengajuan/approval/<int:pengajuan_id>', methods=['POST'])
@role_required('pelatih')
def approval_pengajuan(pengajuan_id):
    action = request.form.get('action') # 'DISETUJUI' atau 'DITOLAK'
    catatan = request.form.get('catatan_pelatih', '').strip()
    ekskul_id = request.form.get('ekskul_id')
    
    conn = get_db()
    conn.execute("""
    UPDATE pengajuan_izin 
    SET status_approval = ?, catatan_pelatih = ?
    WHERE id = ?
    """, (action, catatan, pengajuan_id))
    conn.commit()
    conn.close()
    flash(f"Pengajuan siswa telah {action.lower()}.", "success")
    return redirect(url_for('pelatih_dashboard', ekskul_id=ekskul_id) if ekskul_id else url_for('pelatih_dashboard'))

@app.route('/pelatih/riwayat')
@role_required('pelatih')
def pelatih_riwayat():
    conn = get_db()
    pelatih_id = session['user_id']
    user = conn.execute("SELECT * FROM users WHERE id = ?", (pelatih_id,)).fetchone()
    
    assigned_ekskuls = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN pelatih_ekskul pe ON e.id = pe.ekskul_id
    WHERE pe.user_id = ?
    ORDER BY e.nama ASC
    """, (pelatih_id,)).fetchall()

    if not assigned_ekskuls and user['ekskul_id']:
        assigned_ekskuls = conn.execute("SELECT * FROM ekskul WHERE id = ?", (user['ekskul_id'],)).fetchall()

    active_ekskul_id = request.args.get('ekskul_id', type=int)
    ekskul = None
    if active_ekskul_id:
        for e in assigned_ekskuls:
            if e['id'] == active_ekskul_id:
                ekskul = e
                break
    if not ekskul and assigned_ekskuls:
        ekskul = assigned_ekskuls[0]

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
                           ekskul=ekskul, 
                           assigned_ekskuls=assigned_ekskuls, 
                           sesi_list=sesi_list)

# =========================================================
# 2. AKUN SISWA (PILIH EKSKUL & INFO PRA-PRESENSI)
# =========================================================

@app.route('/siswa')
@role_required('siswa')
def siswa_dashboard():
    siswa_id = session['user_id']
    conn = get_db()
    
    user = conn.execute("SELECT * FROM users WHERE id = ?", (siswa_id,)).fetchone()
    
    # Ambil ekskul yang diikuti siswa
    ekskul_diikuti = conn.execute("""
    SELECT e.* FROM ekskul e
    JOIN siswa_ekskul se ON e.id = se.ekskul_id
    WHERE se.user_id = ? AND se.status = 'AKTIF'
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

    today_str = datetime.now().strftime('%Y-%m-%d')
    conn.close()
    
    return render_template('siswa_dashboard.html', 
                           user=user, 
                           ekskul_diikuti=ekskul_diikuti, 
                           all_ekskul=all_ekskul,
                           riwayat_pengajuan=riwayat_pengajuan,
                           statistik=statistik_kehadiran,
                           today_str=today_str)

@app.route('/siswa/ekskul/pilih', methods=['POST'])
@role_required('siswa')
def siswa_pilih_ekskul():
    siswa_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id')
    
    conn = get_db()
    # Update ekskul utama di users
    conn.execute("UPDATE users SET ekskul_id = ? WHERE id = ?", (ekskul_id, siswa_id))
    # Insert or ignore di siswa_ekskul
    try:
        conn.execute("INSERT INTO siswa_ekskul (user_id, ekskul_id) VALUES (?, ?)", (siswa_id, ekskul_id))
    except Exception:
        pass
    conn.commit()
    conn.close()
    
    flash("Pilihan cabang ekstrakurikuler berhasil diperbarui!", "success")
    return redirect(url_for('siswa_dashboard'))

@app.route('/siswa/pengajuan/kirim', methods=['POST'])
@role_required('siswa')
def siswa_kirim_pengajuan():
    siswa_id = session['user_id']
    ekskul_id = request.form.get('ekskul_id')
    tanggal = request.form.get('tanggal_latihan') or datetime.now().strftime('%Y-%m-%d')
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
    """Halaman 3: Data Master Siswa, Import CSV & Hapus Akun"""
    conn = get_db()
    current_admin = conn.execute("SELECT * FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

    siswa_list = conn.execute("""
    SELECT u.*, 
           COALESCE(
               (SELECT GROUP_CONCAT(e2.icon || ' ' || e2.nama, ', ')
                FROM siswa_ekskul se2
                JOIN ekskul e2 ON se2.ekskul_id = e2.id
                WHERE se2.user_id = u.id AND se2.status = 'AKTIF'),
               e.icon || ' ' || e.nama
           ) as daftar_ekskul,
           e.nama as nama_ekskul, 
           e.icon as icon_ekskul 
    FROM users u
    LEFT JOIN ekskul e ON u.ekskul_id = e.id
    WHERE u.role = 'siswa'
    ORDER BY u.kelas ASC, u.nama ASC
    """).fetchall()

    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    reset_requests = conn.execute("SELECT * FROM reset_password_requests WHERE status = 'PENDING'").fetchall()
    conn.close()

    return render_template('admin_siswa.html',
                           current_admin=current_admin,
                           siswa_list=siswa_list,
                           ekskul_list=ekskul_list,
                           reset_requests=reset_requests,
                           total_siswa=len(siswa_list),
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
    """Hapus akun siswa yang duplikat/salah"""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'siswa'", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash("Akun siswa tidak ditemukan.", "danger")
        return redirect(url_for('admin_siswa'))

    conn.execute("DELETE FROM siswa_ekskul WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM pengajuan_izin WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM presensi_siswa WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM reset_password_requests WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()
    flash(f"Akun siswa '{user['nama']}' ({user['username']}) berhasil dihapus dari sistem.", "success")
    return redirect(url_for('admin_siswa'))

@app.route('/admin/siswa/delete-all', methods=['POST'])
@role_required('admin')
def admin_delete_all_siswa():
    """Hapus seluruh akun data siswa dari sistem (Bulk Delete)"""
    conn = get_db()
    count_row = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'siswa'").fetchone()
    total_siswa = count_row[0] if count_row else 0

    if total_siswa == 0:
        conn.close()
        flash("Tidak ada data siswa yang dapat dihapus.", "warning")
        return redirect(url_for('admin_siswa'))

    # Hapus semua data yang berelasi dengan siswa
    conn.execute("DELETE FROM siswa_ekskul WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM pengajuan_izin WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM presensi_siswa WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM reset_password_requests WHERE user_id IN (SELECT id FROM users WHERE role = 'siswa')")
    conn.execute("DELETE FROM users WHERE role = 'siswa'")

    conn.commit()
    conn.close()

    flash(f"Berhasil! Seluruh data akun siswa ({total_siswa} siswa) beserta seluruh riwayat presensinya telah dihapus dari sistem.", "success")
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
    """Mengimpor data siswa dari berkas CSV / Excel (.csv)."""
    file = request.files.get('file_siswa')
    if not file or file.filename == '':
        flash("Silakan pilih berkas CSV untuk diimpor.", "danger")
        return redirect(url_for('admin_siswa'))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8", errors='ignore'), newline=None)
        csv_reader = csv.reader(stream)
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Peta nama ekskul ke ID ekskul
        ekskul_rows = conn.execute("SELECT id, LOWER(nama) as nama_lower FROM ekskul").fetchall()
        ekskul_map = {row['nama_lower']: row['id'] for row in ekskul_rows}
        
        count_inserted = 0
        for i, row in enumerate(csv_reader):
            if not row or len(row) < 2:
                continue
            if i == 0 and any(keyword in str(row[0]).lower() for keyword in ['nama', 'name', 'siswa']):
                continue
            
            nama = row[0].strip()
            kelas = row[1].strip() if len(row) > 1 else 'Kelas 7'
            jk = row[2].strip().upper() if len(row) > 2 else 'L'
            nama_ekskul_raw = row[3].strip().lower() if len(row) > 3 else ''

            if not nama:
                continue

            # Buat username acak ramah
            base_user = "".join(filter(str.isalnum, nama.lower().replace(" ", "")))[:8]
            username = f"{base_user}{cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0] + 1}"
            password = 'siswa123'
            
            ekskul_id = ekskul_map.get(nama_ekskul_raw)

            try:
                cursor.execute("""
                INSERT INTO users (username, password, nama, role, ekskul_id, kelas, jenis_kelamin)
                VALUES (?, ?, ?, 'siswa', ?, ?, ?)
                """, (username, password, nama, ekskul_id, kelas, jk))
                new_user_id = cursor.lastrowid

                if ekskul_id:
                    cursor.execute("""
                    INSERT OR IGNORE INTO siswa_ekskul (user_id, ekskul_id)
                    VALUES (?, ?)
                    """, (new_user_id, ekskul_id))

                count_inserted += 1
            except Exception:
                continue

        conn.commit()
        conn.close()
        flash(f"Berhasil mengimpor {count_inserted} siswa dari berkas CSV!", "success")
    except Exception as e:
        flash(f"Gagal memproses berkas CSV: {e}", "danger")

    return redirect(url_for('admin_siswa'))

@app.route('/admin/template-csv')
@role_required('admin')
def admin_template_csv():
    """Mengunduh berkas template CSV contoh untuk pendaftaran siswa."""
    csv_content = "Nama Siswa,Kelas,Jenis Kelamin (L/P),Nama Ekskul\n" \
                  "Ahmad Zaki Fauzan,Kelas 7,L,Voli\n" \
                  "Bunga Citra Lestari,Kelas 8,P,Futsal Putri\n" \
                  "Dimas Pratama,Kelas 9,L,Futsal Putra\n" \
                  "Dewi Anggraini,Kelas 7,P,Hizbul Wathan\n" \
                  "Farhan Maulana,Kelas 8,L,Tapak Suci\n" \
                  "Gita Nirmala,Kelas 9,P,Badminton\n"
    
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=template_import_siswa_ekskul.csv"}
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
    tanggal = data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')
    jam_mulai = data.get('jam_mulai') or datetime.now().strftime('%H:%M')
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

    conn.close()
    return render_template('cetak.html', sesi=sesi, presensi=presensi)

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

    output = si.getvalue()
    nama_file = f"Rekap_Presensi_{ekskul['nama'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        output,
        mimetype="text/csv",
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
