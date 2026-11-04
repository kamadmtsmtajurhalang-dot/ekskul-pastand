import os
import math
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
from database import get_db, init_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'presensi-ekskul-tajurhalang-2026'

# Pastikan basis data terinisialisasi saat server berjalan di cloud maupun lokal
init_db()

def haversine(lat1, lon1, lat2, lon2):
    """Menghitung jarak antara dua koordinat GPS dalam satuan meter (Formula Haversine)."""
    R = 6371000 # Radius bumi dalam meter
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    meters = R * c
    return round(meters, 1)

@app.route('/')
def index():
    conn = get_db()
    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()
    conn.close()
    return render_template('index.html', ekskul_list=ekskul_list, lokasi=lokasi)

@app.route('/api/ekskul/<int:ekskul_id>/siswa')
def get_siswa_ekskul(ekskul_id):
    conn = get_db()
    siswa = conn.execute("""
        SELECT * FROM siswa 
        WHERE ekskul_id = ? AND status_aktif = 1 
        ORDER BY kelas ASC, nama ASC
    """, (ekskul_id,)).fetchall()
    
    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (ekskul_id,)).fetchone()
    conn.close()
    
    return jsonify({
        'ekskul': dict(ekskul) if ekskul else None,
        'siswa': [dict(s) for s in siswa]
    })

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
def simpan_presensi():
    data = request.get_json() or {}
    
    ekskul_id = data.get('ekskul_id')
    nama_pelatih = data.get('nama_pelatih', '').strip()
    tanggal = data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')
    jam_mulai = data.get('jam_mulai') or datetime.now().strftime('%H:%M')
    materi_latihan = data.get('materi_latihan', '').strip()
    catatan = data.get('catatan', '').strip()
    
    user_lat = float(data.get('latitude') or 0)
    user_lng = float(data.get('longitude') or 0)
    
    presensi_list = data.get('presensi_siswa', []) # list of {siswa_id, status_kehadiran, keterangan}
    
    if not ekskul_id or not nama_pelatih:
        return jsonify({'status': 'ERROR', 'pesan': 'Data ekskul dan nama pelatih wajib diisi!'}), 400
        
    conn = get_db()
    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()
    
    jarak = 0
    status_lokasi = 'VALID'
    if lokasi and user_lat != 0 and user_lng != 0:
        jarak = haversine(user_lat, user_lng, lokasi['latitude'], lokasi['longitude'])
        status_lokasi = 'VALID' if jarak <= lokasi['radius_meter'] else 'DILUAR_AREA'
        
    # Insert sesi latihan
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sesi_latihan (
        ekskul_id, nama_pelatih, tanggal, jam_mulai, 
        lokasi_lat, lokasi_lng, jarak_meter, status_lokasi, 
        materi_latihan, catatan
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ekskul_id, nama_pelatih, tanggal, jam_mulai,
        user_lat, user_lng, jarak, status_lokasi,
        materi_latihan, catatan
    ))
    
    sesi_id = cursor.lastrowid
    
    # Insert presensi setiap siswa
    for item in presensi_list:
        cursor.execute("""
        INSERT INTO presensi_siswa (sesi_id, siswa_id, status_kehadiran, keterangan)
        VALUES (?, ?, ?, ?)
        """, (sesi_id, item['siswa_id'], item.get('status_kehadiran', 'Hadir'), item.get('keterangan', '')))
        
    conn.commit()
    conn.close()
    
    return jsonify({
        'status': 'SUCCESS',
        'pesan': 'Presensi latihan berhasil disimpan!',
        'sesi_id': sesi_id
    })

@app.route('/riwayat')
def riwayat():
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
    
    return render_template('riwayat.html', sesi_list=sesi_list, ekskul_list=ekskul_list, selected_ekskul=ekskul_id)

@app.route('/riwayat/<int:sesi_id>')
def detail_sesi(sesi_id):
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
    SELECT ps.*, sw.nama, sw.kelas, sw.jenis_kelamin
    FROM presensi_siswa ps
    JOIN siswa sw ON ps.siswa_id = sw.id
    WHERE ps.sesi_id = ?
    ORDER BY sw.kelas ASC, sw.nama ASC
    """, (sesi_id,)).fetchall()
    
    conn.close()
    return render_template('detail_sesi.html', sesi=sesi, presensi=presensi)

@app.route('/cetak/<int:sesi_id>')
def cetak_sesi(sesi_id):
    conn = get_db()
    sesi = conn.execute("""
    SELECT s.*, e.nama as nama_ekskul, e.icon as icon_ekskul, e.kategori
    FROM sesi_latihan s
    JOIN ekskul e ON s.ekskul_id = e.id
    WHERE s.id = ?
    """, (sesi_id,)).fetchone()
    
    presensi = conn.execute("""
    SELECT ps.*, sw.nama, sw.kelas, sw.jenis_kelamin
    FROM presensi_siswa ps
    JOIN siswa sw ON ps.siswa_id = sw.id
    WHERE ps.sesi_id = ?
    ORDER BY sw.kelas ASC, sw.nama ASC
    """, (sesi_id,)).fetchall()
    
    conn.close()
    return render_template('cetak.html', sesi=sesi, presensi=presensi)

@app.route('/rekap')
def rekap():
    ekskul_id = request.args.get('ekskul_id', type=int) or 1
    conn = get_db()
    
    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (ekskul_id,)).fetchone()
    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    
    # Ambil siswa ekskul ini beserta statistik kehadiran total
    rekap_siswa = conn.execute("""
    SELECT sw.id, sw.nama, sw.kelas, sw.jenis_kelamin,
           COUNT(ps.id) as total_sesi,
           SUM(CASE WHEN ps.status_kehadiran = 'Hadir' THEN 1 ELSE 0 END) as hadir,
           SUM(CASE WHEN ps.status_kehadiran = 'Izin' THEN 1 ELSE 0 END) as izin,
           SUM(CASE WHEN ps.status_kehadiran = 'Sakit' THEN 1 ELSE 0 END) as sakit,
           SUM(CASE WHEN ps.status_kehadiran = 'Alpa' THEN 1 ELSE 0 END) as alpa
    FROM siswa sw
    LEFT JOIN presensi_siswa ps ON sw.id = ps.siswa_id
    WHERE sw.ekskul_id = ? AND sw.status_aktif = 1
    GROUP BY sw.id
    ORDER BY sw.kelas ASC, sw.nama ASC
    """, (ekskul_id,)).fetchall()
    
    total_latihan = conn.execute("SELECT COUNT(*) FROM sesi_latihan WHERE ekskul_id = ?", (ekskul_id,)).fetchone()[0]
    conn.close()
    
    return render_template('rekap.html', 
                           ekskul=ekskul, 
                           ekskul_list=ekskul_list, 
                           rekap_siswa=rekap_siswa,
                           total_latihan=total_latihan)

@app.route('/export-csv/<int:ekskul_id>')
def export_csv(ekskul_id):
    conn = get_db()
    ekskul = conn.execute("SELECT * FROM ekskul WHERE id = ?", (ekskul_id,)).fetchone()
    
    rekap_siswa = conn.execute("""
    SELECT sw.nama, sw.kelas, sw.jenis_kelamin,
           COUNT(ps.id) as total_sesi,
           SUM(CASE WHEN ps.status_kehadiran = 'Hadir' THEN 1 ELSE 0 END) as hadir,
           SUM(CASE WHEN ps.status_kehadiran = 'Izin' THEN 1 ELSE 0 END) as izin,
           SUM(CASE WHEN ps.status_kehadiran = 'Sakit' THEN 1 ELSE 0 END) as sakit,
           SUM(CASE WHEN ps.status_kehadiran = 'Alpa' THEN 1 ELSE 0 END) as alpa
    FROM siswa sw
    LEFT JOIN presensi_siswa ps ON sw.id = ps.siswa_id
    WHERE sw.ekskul_id = ? AND sw.status_aktif = 1
    GROUP BY sw.id
    ORDER BY sw.kelas ASC, sw.nama ASC
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
        total = r['total_sesi'] or 1
        persen = round(((r['hadir'] or 0) / total) * 100, 1) if total > 0 else 0
        cw.writerow([idx, r['nama'], r['kelas'], r['jenis_kelamin'], r['hadir'] or 0, r['izin'] or 0, r['sakit'] or 0, r['alpa'] or 0, f"{persen}%"])
        
    output = si.getvalue()
    nama_file = f"Rekap_Presensi_{ekskul['nama'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={nama_file}"}
    )

@app.route('/kelola')
def kelola():
    conn = get_db()
    ekskul_list = conn.execute("SELECT * FROM ekskul ORDER BY nama ASC").fetchall()
    lokasi = conn.execute("SELECT * FROM pengaturan_lokasi WHERE is_active = 1 LIMIT 1").fetchone()
    siswa_list = conn.execute("""
        SELECT sw.*, e.nama as nama_ekskul, e.icon as icon_ekskul
        FROM siswa sw
        JOIN ekskul e ON sw.ekskul_id = e.id
        WHERE sw.status_aktif = 1
        ORDER BY e.nama ASC, sw.kelas ASC, sw.nama ASC
    """).fetchall()
    conn.close()
    return render_template('kelola.html', ekskul_list=ekskul_list, lokasi=lokasi, siswa_list=siswa_list)

@app.route('/api/siswa/tambah', methods=['POST'])
def tambah_siswa():
    data = request.form
    ekskul_id = data.get('ekskul_id')
    nama = data.get('nama', '').strip()
    kelas = data.get('kelas', 'Kelas 7')
    jk = data.get('jenis_kelamin', 'L')
    
    if not ekskul_id or not nama:
        return redirect(url_for('kelola'))
        
    conn = get_db()
    conn.execute("INSERT INTO siswa (ekskul_id, nama, kelas, jenis_kelamin) VALUES (?, ?, ?, ?)",
                 (ekskul_id, nama, kelas, jk))
    conn.commit()
    conn.close()
    return redirect(url_for('kelola'))

@app.route('/api/siswa/hapus/<int:siswa_id>', methods=['POST'])
def hapus_siswa(siswa_id):
    conn = get_db()
    conn.execute("UPDATE siswa SET status_aktif = 0 WHERE id = ?", (siswa_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('kelola'))

@app.route('/api/lokasi/update', methods=['POST'])
def update_lokasi():
    data = request.form
    nama_lokasi = data.get('nama_lokasi')
    lat = float(data.get('latitude'))
    lng = float(data.get('longitude'))
    radius = int(data.get('radius_meter', 250))
    
    conn = get_db()
    conn.execute("""
    UPDATE pengaturan_lokasi 
    SET nama_lokasi = ?, latitude = ?, longitude = ?, radius_meter = ?
    WHERE is_active = 1
    """, (nama_lokasi, lat, lng, radius))
    conn.commit()
    conn.close()
    return redirect(url_for('kelola'))

if __name__ == '__main__':
    init_db()
    print("Memulai Web App Presensi Ekskul MTs Muhammadiyah Tajurhalang...")
    app.run(host='0.0.0.0', port=5000, debug=False)
