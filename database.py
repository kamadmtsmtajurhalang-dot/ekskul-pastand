import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "presensi_ekskul.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Tabel Ekskul
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ekskul (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT UNIQUE NOT NULL,
        kategori TEXT,
        icon TEXT,
        hari_latihan TEXT,
        jam_latihan TEXT,
        pelatih_nama TEXT,
        deskripsi TEXT
    )
    """)

    # 2. Tabel Users (Admin, Pelatih, Siswa)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        nama TEXT NOT NULL,
        role TEXT NOT NULL, -- 'admin', 'pelatih', 'siswa'
        ekskul_id INTEGER,  -- untuk pelatih / ekskul utama siswa
        kelas TEXT,         -- khusus siswa: 'Kelas 7', 'Kelas 8', 'Kelas 9'
        nisn TEXT,
        jenis_kelamin TEXT, -- 'L' / 'P'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id)
    )
    """)

    # 3. Tabel Siswa_Ekskul (Relasi Siswa memilih Ekskul)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS siswa_ekskul (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ekskul_id INTEGER NOT NULL,
        tanggal_daftar TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'AKTIF',
        UNIQUE(user_id, ekskul_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id)
    )
    """)

    # 3b. Tabel Pelatih_Ekskul (Relasi 1 Pelatih/Guru memegang beberapa Ekskul)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pelatih_ekskul (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ekskul_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, ekskul_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id)
    )
    """)

    # 4. Tabel Pengajuan Pra-Presensi Siswa (Sebelum Latihan)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pengajuan_izin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ekskul_id INTEGER NOT NULL,
        tanggal_latihan TEXT NOT NULL,
        status_pengajuan TEXT NOT NULL, -- 'Akan Hadir', 'Izin', 'Sakit'
        alasan TEXT,
        status_approval TEXT DEFAULT 'MENUNGGU', -- 'MENUNGGU', 'DISETUJUI', 'DITOLAK'
        catatan_pelatih TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id)
    )
    """)

    # 5. Tabel Sesi Latihan (Presensi Guru/Pelatih)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sesi_latihan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ekskul_id INTEGER NOT NULL,
        pelatih_id INTEGER NOT NULL,
        nama_pelatih TEXT NOT NULL,
        tanggal TEXT NOT NULL,
        jam_mulai TEXT NOT NULL,
        jam_selesai TEXT,
        lokasi_lat REAL,
        lokasi_lng REAL,
        jarak_meter REAL,
        status_lokasi TEXT, -- 'VALID' / 'DILUAR_AREA'
        materi_latihan TEXT,
        catatan TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id),
        FOREIGN KEY (pelatih_id) REFERENCES users(id)
    )
    """)

    # 6. Tabel Presensi Siswa per Sesi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS presensi_siswa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sesi_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        status_kehadiran TEXT NOT NULL, -- 'Hadir', 'Izin', 'Sakit', 'Alpa'
        keterangan TEXT,
        is_preapproved INTEGER DEFAULT 0,
        FOREIGN KEY (sesi_id) REFERENCES sesi_latihan(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # 7. Tabel Pengaturan Lokasi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pengaturan_lokasi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_lokasi TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        radius_meter INTEGER DEFAULT 250,
        is_active INTEGER DEFAULT 1
    )
    """)

    # 8. Tabel Permohonan Lupa / Reset Password
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reset_password_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT NOT NULL,
        nama TEXT,
        role TEXT,
        keterangan TEXT,
        status TEXT DEFAULT 'PENDING', -- 'PENDING', 'SELESAI', 'DITOLAK'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    conn.commit()

    # Migrasi data relasi pelatih ke tabel pelatih_ekskul
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO pelatih_ekskul (user_id, ekskul_id)
        SELECT id, ekskul_id FROM users
        WHERE role = 'pelatih' AND ekskul_id IS NOT NULL
        """)
        conn.commit()
    except Exception:
        pass

    # Seeding Default Data jika kosong
    cursor.execute("SELECT COUNT(*) FROM ekskul")
    if cursor.fetchone()[0] == 0:
        ekskuls = [
            ("Voli", "Olahraga", "🏐", "Selasa & Jumat", "15:30 - 17:00", "Coach Rahmat Hidayat", "Latihan teknik bola voli, passing, smash, dan kerja sama tim."),
            ("Futsal Putra", "Olahraga", "⚽", "Senin & Kamis", "15:30 - 17:15", "Coach Mulyadi, S.Pd.", "Pengembangan skill futsal, taktik bermain, dan turnamen."),
            ("Futsal Putri", "Olahraga", "⚽", "Rabu & Sabtu", "15:30 - 17:00", "Coach Suci Lestari", "Latihan dasar futsal putri, kebugaran jasmani, dan kekompakan."),
            ("Hizbul Wathan", "Kepanduan", "🏕️", "Jumat", "13:30 - 15:30", "Ramanda Samaun, S.P., Gr.", "Pendidikan kepanduan Islami, kedisiplinan, pioneering, dan kemandirian."),
            ("Tapak Suci", "Bela Diri", "🥋", "Sabtu", "08:00 - 10:30", "Pendekar Ahmad Fauzi", "Seni bela diri Tapak Suci Putera Muhammadiyah, jurus dasar, dan ketangkasan."),
            ("Badminton", "Olahraga", "🏸", "Rabu & Ahad", "15:30 - 17:00", "Coach Santi Mulyasari, S.Hum.", "Teknik bulutangkis, footwork, netting, smash, dan kebugaran.")
        ]
        cursor.executemany("""
        INSERT INTO ekskul (nama, kategori, icon, hari_latihan, jam_latihan, pelatih_nama, deskripsi)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ekskuls)

    # Lokasi Lapangan Default
    cursor.execute("SELECT COUNT(*) FROM pengaturan_lokasi")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO pengaturan_lokasi (nama_lokasi, latitude, longitude, radius_meter, is_active)
        VALUES (?, ?, ?, ?, ?)
        """, ("Kampus & Lapangan MTs Muhammadiyah Tajurhalang", -6.47892, 106.75805, 300, 1))

    # Cek & Tambah Akun Default
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # 1. Admin Master
        cursor.execute("""
        INSERT INTO users (username, password, nama, role)
        VALUES ('admin', 'admin123', 'Administrator Madrasah (Kamad)', 'admin')
        """)

        # 2. Akun Pelatih untuk masing-masing ekskul (id 1 s.d 6)
        pelatih_data = [
            ('coach_voli', 'voli123', 'Coach Rahmat Hidayat', 'pelatih', 1),
            ('coach_futsal_pa', 'futsal123', 'Coach Mulyadi, S.Pd.', 'pelatih', 2),
            ('coach_futsal_pi', 'futsal123', 'Coach Suci Lestari', 'pelatih', 3),
            ('pembina_hw', 'hw123', 'Ramanda Samaun, S.P., Gr.', 'pelatih', 4),
            ('pelatih_ts', 'ts123', 'Pendekar Ahmad Fauzi', 'pelatih', 5),
            ('coach_badminton', 'badminton123', 'Coach Santi Mulyasari, S.Hum.', 'pelatih', 6),
        ]
        cursor.executemany("""
        INSERT INTO users (username, password, nama, role, ekskul_id)
        VALUES (?, ?, ?, ?, ?)
        """, pelatih_data)

        # 3. Akun Siswa Awal
        sample_siswa = [
            # Voli (ekskul 1)
            ('siswa1', 'siswa123', 'Ahmad Rifai', 'siswa', 1, 'Kelas 7', 'L'),
            ('siswa2', 'siswa123', 'Bagas Pratama', 'siswa', 1, 'Kelas 8', 'L'),
            ('siswa3', 'siswa123', 'Cahya Ramadhan', 'siswa', 1, 'Kelas 8', 'L'),
            ('siswa4', 'siswa123', 'Daffa Arya', 'siswa', 1, 'Kelas 9', 'L'),
            ('siswa5', 'siswa123', 'Eka Febriansyah', 'siswa', 1, 'Kelas 7', 'L'),
            # Futsal Putra (ekskul 2)
            ('siswa6', 'siswa123', 'Aldi Firmansyah', 'siswa', 2, 'Kelas 8', 'L'),
            ('siswa7', 'siswa123', 'Bima Sakti', 'siswa', 2, 'Kelas 7', 'L'),
            ('siswa8', 'siswa123', 'Danang Prasetyo', 'siswa', 2, 'Kelas 9', 'L'),
            ('siswa9', 'siswa123', 'Faris Al-Ghifari', 'siswa', 2, 'Kelas 8', 'L'),
            ('siswa10', 'siswa123', 'Haikal Malik', 'siswa', 2, 'Kelas 9', 'L'),
            # Futsal Putri (ekskul 3)
            ('siswa11', 'siswa123', 'Aisyah Zahra', 'siswa', 3, 'Kelas 7', 'P'),
            ('siswa12', 'siswa123', 'Bella Anggraini', 'siswa', 3, 'Kelas 8', 'P'),
            ('siswa13', 'siswa123', 'Citra Lestari', 'siswa', 3, 'Kelas 8', 'P'),
            ('siswa14', 'siswa123', 'Dinda Permata', 'siswa', 3, 'Kelas 9', 'P'),
            # Hizbul Wathan (ekskul 4)
            ('siswa15', 'siswa123', 'Aditya Pratama', 'siswa', 4, 'Kelas 7', 'L'),
            ('siswa16', 'siswa123', 'Anisa Rahma', 'siswa', 4, 'Kelas 7', 'P'),
            ('siswa17', 'siswa123', 'Fatimah Azzahra', 'siswa', 4, 'Kelas 9', 'P'),
            ('siswa18', 'siswa123', 'Gunawan Santoso', 'siswa', 4, 'Kelas 7', 'L'),
            # Tapak Suci (ekskul 5)
            ('siswa19', 'siswa123', 'Alif Al-Farizi', 'siswa', 5, 'Kelas 7', 'L'),
            ('siswa20', 'siswa123', 'Bintang Satria', 'siswa', 5, 'Kelas 8', 'L'),
            ('siswa21', 'siswa123', 'Halimah Tusadiah', 'siswa', 5, 'Kelas 7', 'P'),
            # Badminton (ekskul 6)
            ('siswa22', 'siswa123', 'Kevin Sanjaya', 'siswa', 6, 'Kelas 9', 'L'),
            ('siswa23', 'siswa123', 'Anthony Ginting', 'siswa', 6, 'Kelas 7', 'L'),
            ('siswa24', 'siswa123', 'Gregoria Mariska', 'siswa', 6, 'Kelas 8', 'P')
        ]
        cursor.executemany("""
        INSERT INTO users (username, password, nama, role, ekskul_id, kelas, jenis_kelamin)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_siswa)

        # Masukkan ke tabel relasi siswa_ekskul
        cursor.execute("""
        INSERT INTO siswa_ekskul (user_id, ekskul_id)
        SELECT id, ekskul_id FROM users WHERE role = 'siswa' AND ekskul_id IS NOT NULL
        """)

    conn.commit()

    # Migrasi data relasi pelatih ke tabel pelatih_ekskul
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO pelatih_ekskul (user_id, ekskul_id)
        SELECT id, ekskul_id FROM users
        WHERE role = 'pelatih' AND ekskul_id IS NOT NULL
        """)
        conn.commit()
    except Exception:
        pass
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database Presensi Multi-Role Berhasil Diinisialisasi!")
