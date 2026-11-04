# 🤖 Panduan Lengkap Otomatisasi GitHub & PythonAnywhere
### Web App Presensi Ekskul MTs Muhammadiyah Tajurhalang

Dokumen ini menjelaskan alur otomatisasi penuh agar Anda tidak perlu lagi melakukan setup dan deploy manual.

---

## 🚀 Pilihan Cara Pengisian Kredensial

Anda memiliki 2 cara mudah untuk mengisi token:

### Opsi A: Melalui Chat Antigravity
Cukup kirimkan informasi berikut di jendela chat:
- Username GitHub
- Nama Repo GitHub
- GitHub Personal Access Token (`ghp_...`)
- Username PythonAnywhere
- PythonAnywhere API Token
- Domain WebApp (misal: `namapengguna.pythonanywhere.com`)

Antigravity akan langsung menyimpannya ke konfigurasi lokal dan menguji koneksinya.

### Opsi B: Menggunakan Wizard Interaktif di Terminal
Jika Anda ingin mengetikkan token secara pribadi langsung di terminal:
```bash
cd /home/rfn-x/presensi_ekskul
python3 setup_automation.py
```
Ikuti instruksi di layar, dan file rahasia `.env.deploy` akan dibuat otomatis dengan izin akses terbatas (`chmod 600`).

---

## 🛠️ Perintah Otomasi yang Tersedia

Setelah token tersimpan, Anda atau Antigravity cukup menjalankan perintah berikut dari folder `/home/rfn-x/presensi_ekskul`:

| Perintah | Fungsi |
| :--- | :--- |
| `python3 deploy.py check` | Memeriksa apakah token GitHub & PythonAnywhere valid dan aktif. |
| `python3 deploy.py github` | Menyetel Git remote otomatis dan mem-push commit terbaru ke GitHub. |
| `python3 deploy.py reload` | Mengirimkan sinyal API ke PythonAnywhere untuk me-reload web app seketika. |
| `python3 deploy.py all` | Melakukan seluruh alur: Push ke GitHub lalu Reload server PythonAnywhere sekaligus! |

---

## ⚡ CI/CD Otomatis via GitHub Actions

Workflow GitHub Actions sudah terpasang di [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml).

Jika Anda memasukkan 3 Secret di GitHub:
1. Buka repo Anda di GitHub -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Tambahkan Repository Secrets:
   - `PYTHONANYWHERE_USERNAME`
   - `PYTHONANYWHERE_API_TOKEN`
   - `PYTHONANYWHERE_DOMAIN`

Maka setiap kali ada perubahan kode yang di-push ke GitHub, PythonAnywhere akan **otomatis re-deploy dan reload** tanpa Anda perlu membuka terminal atau browser lagi!
