import os
import math
import csv
import io
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, session, Response, flash
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
    
    # Ambil data pelatih dan ekskul yang diampunya
    user = conn.execute("SELECT * FROM users WHERE id = ?", (pelatih_id,)).fetchone()
    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (user['ekskul_id'],)).fetchone()
    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()
    
    if not ekskul:
        conn.close()
        return "Ekskul belum dihubungkan ke akun pelatih ini. Hubungi Admin.", 400

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

    # Riwayat sesi latihan pelatih ini
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
    return redirect(url_for('pelatih_dashboard'))

@app.route('/pelatih/pengajuan/approval/<int:pengajuan_id>', methods=['POST'])
@role_required('pelatih')
def approval_pengajuan(pengajuan_id):
    action = request.form.get('action') # 'DISETUJUI' atau 'DITOLAK'
    catatan = request.form.get('catatan_pelatih', '').strip()
    
    conn = get_db()
    conn.execute("""
    UPDATE pengajuan_izin 
    SET status_approval = ?, catatan_pelatih = ?
    WHERE id = ?
    """, (action, catatan, pengajuan_id))
    conn.commit()
    conn.close()
    flash(f"Pengajuan siswa telah {action.lower()}.", "success")
    return redirect(url_for('pelatih_dashboard'))

@app.route('/pelatih/riwayat')
@role_required('pelatih')
def pelatih_riwayat():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (user['ekskul_id'],)).fetchone()
    
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
    return render_template('pelatih_riwayat.html', ekskul=ekskul, sesi_list=sesi_list)

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
# 3. AKUN ADMIN MASTER (PENGATURAN EKSKUL, GURU, IMPORT SISWA)
# =========================================================

@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    conn = get_db()
    
    ekskul_list = conn.execute("""
    SELECT e.*, 
           (SELECT COUNT(*) FROM siswa_ekskul se WHERE se.ekskul_id = e.id AND se.status = 'AKTIF') as total_siswa,
           (SELECT COUNT(*) FROM sesi_latihan s WHERE s.ekskul_id = e.id) as total_sesi
    FROM ekskul e
    ORDER BY e.nama ASC
    """).fetchall()

    pelatih_list = conn.execute("""
    SELECT u.*, e.nama as nama_ekskul, e.icon as icon_ekskul 
    FROM users u
    LEFT JOIN ekskul e ON u.ekskul_id = e.id
    WHERE u.role = 'pelatih'
    ORDER BY u.nama ASC
    """).fetchall()

    siswa_list = conn.execute("""
    SELECT u.*, e.nama as nama_ekskul, e.icon as icon_ekskul 
    FROM users u
    LEFT JOIN ekskul e ON u.ekskul_id = e.id
    WHERE u.role = 'siswa'
    ORDER BY e.nama ASC, u.kelas ASC, u.nama ASC
    """).fetchall()

    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()

    total_siswa_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'siswa'").fetchone()[0]
    total_pelatih_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'pelatih'").fetchone()[0]
    total_sesi_count = conn.execute("SELECT COUNT(*) FROM sesi_latihan").fetchone()[0]

    conn.close()
    return render_template('admin_dashboard.html',
                           ekskul_list=ekskul_list,
                           pelatih_list=pelatih_list,
                           siswa_list=siswa_list,
                           lokasi=lokasi,
                           total_siswa=total_siswa_count,
                           total_pelatih=total_pelatih_count,
                           total_sesi=total_sesi_count)

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
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/pelatih/tambah', methods=['POST'])
@role_required('admin')
def admin_tambah_pelatih():
    nama = request.form.get('nama', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    ekskul_id = request.form.get('ekskul_id')

    if nama and username and password:
        conn = get_db()
        try:
            conn.execute("""
            INSERT INTO users (username, password, nama, role, ekskul_id)
            VALUES (?, ?, ?, 'pelatih', ?)
            """, (username, password, nama, ekskul_id))
            conn.commit()
            flash(f"Akun Pelatih '{nama}' berhasil dibuat!", "success")
        except Exception:
            flash(f"Username '{username}' sudah digunakan.", "danger")
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/siswa/import', methods=['POST'])
@role_required('admin')
def admin_import_siswa():
    """Mengimpor data siswa dari berkas CSV / Excel (.csv)."""
    file = request.files.get('file_siswa')
    if not file or file.filename == '':
        flash("Silakan pilih berkas CSV untuk diimpor.", "danger")
        return redirect(url_for('admin_dashboard'))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8", errors='ignore'), newline=None)
        csv_reader = csv.reader(stream)
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Peta nama ekskul ke ID ekskul
        ekskul_rows = conn.execute("SELECT id, LOWER(nama) as nama_lower FROM ekskul").fetchall()
        ekskul_map = {row['nama_lower']: row['id'] for row in ekskul_rows}

        berhasil = 0
        gagal = 0
        
        for i, row in enumerate(csv_reader):
            if not row or len(row) < 3:
                continue
            # Lewati baris header jika ada
            if i == 0 and any(keyword in row[0].lower() for keyword in ['nama', 'no', 'siswa']):
                continue
                
            nama_siswa = row[0].strip()
            kelas = row[1].strip() if len(row) > 1 else 'Kelas 7'
            jk = row[2].strip().upper() if len(row) > 2 else 'L'
            nama_ekskul_target = row[3].strip().lower() if len(row) > 3 else ''
            
            # Buat username otomatis unik
            base_user = "".join(filter(str.isalnum, nama_siswa.lower()))[:10]
            username = f"{base_user}{i+1}"
            password = "siswa123" # password default
            
            # Cari ekskul ID
            target_ekskul_id = None
            for key_ekskul, eid in ekskul_map.items():
                if key_ekskul in nama_ekskul_target or nama_ekskul_target in key_ekskul:
                    target_ekskul_id = eid
                    break
            if not target_ekskul_id and len(ekskul_map) > 0:
                target_ekskul_id = list(ekskul_map.values())[0]

            try:
                cursor.execute("""
                INSERT INTO users (username, password, nama, role, ekskul_id, kelas, jenis_kelamin)
                VALUES (?, ?, ?, 'siswa', ?, ?, ?)
                """, (username, password, nama_siswa, target_ekskul_id, kelas, jk))
                new_uid = cursor.lastrowid
                
                cursor.execute("""
                INSERT INTO siswa_ekskul (user_id, ekskul_id) VALUES (?, ?)
                """, (new_uid, target_ekskul_id))
                berhasil += 1
            except Exception:
                gagal += 1

        conn.commit()
        conn.close()
        flash(f"Impor Berhasil: {berhasil} siswa ditambahkan ({gagal} dilewati).", "success")
    except Exception as e:
        flash(f"Gagal memproses file CSV: {str(e)}", "danger")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/template-csv')
@role_required('admin')
def download_template_csv():
    """Download template CSV untuk impor data siswa."""
    output = "Nama Siswa,Kelas,Jenis Kelamin,Ekskul\n"
    output += "Ahmad Fauzi,Kelas 7,L,Futsal Putra\n"
    output += "Siti Nurhaliza,Kelas 8,P,Futsal Putri\n"
    output += "Budi Santoso,Kelas 9,L,Voli\n"
    output += "Dewi Sartika,Kelas 7,P,Hizbul Wathan\n"
    output += "Rizky Ramadhan,Kelas 8,L,Tapak Suci\n"
    output += "Nabila Putri,Kelas 9,P,Badminton\n"

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Template_Import_Siswa_Ekskul.csv"}
    )

@app.route('/admin/lokasi/update', methods=['POST'])
@role_required('admin')
def admin_update_lokasi():
    nama_lokasi = request.form.get('nama_lokasi')
    lat = float(request.form.get('latitude', 0))
    lng = float(request.form.get('longitude', 0))
    radius = int(request.form.get('radius_meter', 250))

    conn = get_db()
    conn.execute("""
    UPDATE pengaturan_lokasi 
    SET nama_lokasi = ?, latitude = ?, longitude = ?, radius_meter = ?
    WHERE is_active = 1
    """, (nama_lokasi, lat, lng, radius))
    conn.commit()
    conn.close()
    flash("Titik koordinat dan radius geofence lapangan berhasil diperbarui!", "success")
    return redirect(url_for('admin_dashboard'))

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

if __name__ == '__main__':
    print("Memulai Server Presensi Ekskul Multi-Role MTs Muhammadiyah Tajurhalang...")
    app.run(host='0.0.0.0', port=5000, debug=False)
