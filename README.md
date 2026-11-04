# Web App Presensi Ekstrakurikuler Berbasis Lokasi (GPS Geofence)
### MTs Muhammadiyah Tajurhalang Bogor

Aplikasi web presensi mobile-first yang dirancang khusus untuk mempermudah pelatih/pembina ekstrakurikuler dalam melakukan presensi kehadiran diri sendiri (guru/pelatih) dan seluruh siswa anggota saat sesi latihan berlangsung langsung dari smartphone.

---

## 🌟 Fitur Utama

1. **6 Cabang Ekstrakurikuler Lengkap**:
   - 🏐 **Voli** (Selasa & Jumat)
   - ⚽ **Futsal Putra** (Senin & Kamis)
   - ⚽ **Futsal Putri** (Rabu & Sabtu)
   - 🏕️ **Hizbul Wathan (HW)** (Jumat)
   - 🥋 **Tapak Suci (TS)** (Sabtu)
   - 🏸 **Badminton** (Rabu & Ahad)

2. **Validasi Lokasi GPS (Geofencing Lapangan)**:
   - Otomatis mendeteksi koordinat GPS HP pelatih saat membuka web app.
   - Menghitung jarak presisi (menggunakan formula *Haversine*) dari posisi HP ke titik pusat Lapangan MTs Muhammadiyah Tajurhalang.
   - Indikator Visual: **🟢 Valid (Di Lapangan)** vs **🔴 Luar Radius**.
   - Dilengkapi fitur **1-Klik Kalibrasi**: *"Gunakan Lokasi HP Saya Saat Ini Sebagai Titik Pusat Lapangan"*.

3. **Presensi Guru / Pelatih (Check-In Latihan)**:
   - Nama pelatih otomatis terisi sesuai jadwal ekskul.
   - Jam presensi otomatis tercatat saat sesi dimulai.
   - Jurnal Pelatihan: Kolom materi/fokus latihan harian & catatan lapangan.

4. **Presensi Siswa Ramah Jempol (Mobile-First UI)**:
   - Tombol toggle status kehadiran 4 warna yang besar dan responsif di layar sentuh:
     * **H (Hadir - Hijau)**
     * **I (Izin - Kuning)**
     * **S (Sakit - Biru)**
     * **A (Alpa - Merah)**
   - Fitur **"✅ Semua Hadir"** dengan 1 sentuhan cepat.
   - Filter pencarian nama siswa instan.

5. **Rekapitulasi & Lembar Cetak Laporan**:
   - **Riwayat Sesi:** Daftar seluruh sesi latihan beserta total kehadiran dan status verifikasi GPS.
   - **Lembar Cetak Resmi:** Template cetak/PDF ber-Kop MTs Muhammadiyah Tajurhalang dengan tanda tangan Pelatih dan Waka Kesiswaan.
   - **Export Excel / CSV:** Unduh rekap statistik persentase kehadiran siswa per cabang ekskul.

---

## 🚀 Cara Menjalankan Server

Aplikasi ini dibangun menggunakan Python Flask dan SQLite tanpa perlu konfigurasi rumit:

```bash
cd /home/rfn-x/presensi_ekskul
python3 app.py
```
Aplikasi akan aktif di `http://0.0.0.0:5000`.

### Akses dari HP Pelatih:
1. Pastikan HP pelatih terhubung ke jaringan Wi-Fi yang sama dengan komputer server madrasah (atau melalui tethering/port forwarding).
2. Buka browser di HP (Chrome / Safari) lalu ketik:
   `http://[IP_KOMPUTER]:5000` (contoh: `http://192.168.1.50:5000` atau `http://localhost:5000`).
3. Izinkan akses **Lokasi (GPS)** saat muncul *pop-up* di browser HP.
