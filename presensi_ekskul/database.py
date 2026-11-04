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
        pelatih_default TEXT
    )
    """)
    
    # 2. Tabel Siswa
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS siswa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ekskul_id INTEGER NOT NULL,
        nama TEXT NOT NULL,
        kelas TEXT NOT NULL,
        nisn TEXT,
        jenis_kelamin TEXT,
        status_aktif INTEGER DEFAULT 1,
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id)
    )
    """)
    
    # 3. Tabel Pengaturan Lokasi Lapangan
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
    
    # 4. Tabel Sesi Latihan (Presensi Pelatih / Guru)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sesi_latihan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ekskul_id INTEGER NOT NULL,
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
        FOREIGN KEY (ekskul_id) REFERENCES ekskul(id)
    )
    """)
    
    # 5. Tabel Presensi Siswa per Sesi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS presensi_siswa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sesi_id INTEGER NOT NULL,
        siswa_id INTEGER NOT NULL,
        status_kehadiran TEXT NOT NULL, -- 'Hadir', 'Izin', 'Sakit', 'Alpa'
        keterangan TEXT,
        FOREIGN KEY (sesi_id) REFERENCES sesi_latihan(id),
        FOREIGN KEY (siswa_id) REFERENCES siswa(id)
    )
    """)
    
    # Isi data bawaan jika tabel ekskul masih kosong
    cursor.execute("SELECT COUNT(*) FROM ekskul")
    if cursor.fetchone()[0] == 0:
        ekskul_data = [
            ("Voli", "Olahraga", "🏐", "Selasa & Jumat", "15:30 - 17:00", "Coach Rahmat Hidayat"),
            ("Futsal Putra", "Olahraga", "⚽", "Senin & Kamis", "15:30 - 17:15", "Coach Mulyadi, S.Pd."),
            ("Futsal Putri", "Olahraga", "⚽", "Rabu & Sabtu", "15:30 - 17:00", "Coach Suci Lestari"),
            ("Hizbul Wathan", "Kepanduan", "🏕️", "Jumat", "13:30 - 15:30", "Ramanda Samaun, S.P., Gr."),
            ("Tapak Suci", "Bela Diri", "🥋", "Sabtu", "08:00 - 10:30", "Pendekar Ahmad Fauzi"),
            ("Badminton", "Olahraga", "🏸", "Rabu & Ahad", "15:30 - 17:00", "Coach Santi Mulyasari, S.Hum.")
        ]
        cursor.executemany("""
        INSERT INTO ekskul (nama, kategori, icon, hari_latihan, jam_latihan, pelatih_default)
        VALUES (?, ?, ?, ?, ?, ?)
        """, ekskul_data)
        
        # Default Lokasi Lapangan MTs Muhammadiyah Tajurhalang
        # Koordinat Tajurhalang Bogor: Sekitar -6.47892, 106.75805
        cursor.execute("""
        INSERT INTO pengaturan_lokasi (nama_lokasi, latitude, longitude, radius_meter, is_active)
        VALUES (?, ?, ?, ?, ?)
        """, ("Kampus & Lapangan MTs Muhammadiyah Tajurhalang", -6.47892, 106.75805, 300, 1))
        
        # Sample Siswa per Ekskul
        siswa_samples = [
            # 1. Voli (ekskul_id 1)
            (1, "Ahmad Rifai", "Kelas 7", "L"),
            (1, "Bagas Pratama", "Kelas 8", "L"),
            (1, "Cahya Ramadhan", "Kelas 8", "L"),
            (1, "Daffa Arya", "Kelas 9", "L"),
            (1, "Eka Febriansyah", "Kelas 7", "L"),
            (1, "Fajar Nugraha", "Kelas 9", "L"),
            (1, "Galih Saputra", "Kelas 8", "L"),
            (1, "Hafiz Maulana", "Kelas 7", "L"),
            (1, "Ilham Kurnia", "Kelas 9", "L"),
            (1, "Jovan Alamsyah", "Kelas 8", "L"),
            
            # 2. Futsal Putra (ekskul_id 2)
            (2, "Aldi Firmansyah", "Kelas 8", "L"),
            (2, "Bima Sakti", "Kelas 7", "L"),
            (2, "Danang Prasetyo", "Kelas 9", "L"),
            (2, "Faris Al-Ghifari", "Kelas 8", "L"),
            (2, "Gibran Rakabuming", "Kelas 7", "L"),
            (2, "Haikal Malik", "Kelas 9", "L"),
            (2, "Kusuma Wijaya", "Kelas 8", "L"),
            (2, "Lukman Hakim", "Kelas 9", "L"),
            (2, "Naufal Zaidan", "Kelas 7", "L"),
            (2, "Rizky Ramadhan", "Kelas 8", "L"),
            (2, "Syahrul Gunawan", "Kelas 9", "L"),
            (2, "Zulfa Rahman", "Kelas 7", "L"),
            
            # 3. Futsal Putri (ekskul_id 3)
            (3, "Aisyah Zahra", "Kelas 7", "P"),
            (3, "Bella Anggraini", "Kelas 8", "P"),
            (3, "Citra Lestari", "Kelas 8", "P"),
            (3, "Dinda Permata", "Kelas 9", "P"),
            (3, "Fitri Handayani", "Kelas 7", "P"),
            (3, "Gita Savitri", "Kelas 9", "P"),
            (3, "Hana Salsabila", "Kelas 8", "P"),
            (3, "Intan Nuraini", "Kelas 7", "P"),
            (3, "Kirana Ayu", "Kelas 9", "P"),
            (3, "Nabila Syakieb", "Kelas 8", "P"),
            
            # 4. Hizbul Wathan (ekskul_id 4)
            (4, "Aditya Pratama", "Kelas 7", "L"),
            (4, "Anisa Rahma", "Kelas 7", "P"),
            (4, "Bayu Permana", "Kelas 8", "L"),
            (4, "Dewi Sartika", "Kelas 8", "P"),
            (4, "Faisal Basri", "Kelas 9", "L"),
            (4, "Fatimah Azzahra", "Kelas 9", "P"),
            (4, "Gunawan Santoso", "Kelas 7", "L"),
            (4, "Hasan Basri", "Kelas 8", "L"),
            (4, "Indah Permatasari", "Kelas 8", "P"),
            (4, "Jamilah Hasan", "Kelas 9", "P"),
            (4, "Muhammad Iqbal", "Kelas 7", "L"),
            (4, "Nurul Hidayah", "Kelas 9", "P"),
            
            # 5. Tapak Suci (ekskul_id 5)
            (5, "Alif Al-Farizi", "Kelas 7", "L"),
            (5, "Bintang Satria", "Kelas 8", "L"),
            (5, "Chandra Wibawa", "Kelas 9", "L"),
            (5, "Dzaky Mubarak", "Kelas 7", "L"),
            (5, "Fauzan Azima", "Kelas 8", "L"),
            (5, "Ghani Rahmatullah", "Kelas 9", "L"),
            (5, "Halimah Tusadiah", "Kelas 7", "P"),
            (5, "Ihsan Kamil", "Kelas 8", "L"),
            (5, "Khadijah Al-Kubro", "Kelas 8", "P"),
            (5, "Raihan Fadillah", "Kelas 9", "L"),
            
            # 6. Badminton (ekskul_id 6)
            (6, "Kevin Sanjaya", "Kelas 9", "L"),
            (6, "Marcus Gideon", "Kelas 8", "L"),
            (6, "Anthony Ginting", "Kelas 7", "L"),
            (6, "Gregoria Mariska", "Kelas 8", "P"),
            (6, "Apriyani Rahayu", "Kelas 9", "P"),
            (6, "Fajar Alfian", "Kelas 7", "L"),
            (6, "Rian Ardianto", "Kelas 8", "L"),
            (6, "Putri Kusuma", "Kelas 7", "P"),
            (6, "Jonatan Christie", "Kelas 9", "L"),
            (6, "Siti Fadia", "Kelas 8", "P")
        ]
        
        cursor.executemany("""
        INSERT INTO siswa (ekskul_id, nama, kelas, jenis_kelamin)
        VALUES (?, ?, ?, ?)
        """, siswa_samples)
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database Presensi Ekskul berhasil diinisialisasi!")
