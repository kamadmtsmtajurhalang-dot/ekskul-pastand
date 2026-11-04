#!/usr/bin/env python3
"""
Wizard Interaktif Konfigurasi Otomatisasi GitHub & PythonAnywhere
"""

import os
import getpass

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.deploy")

def main():
    print("=" * 60)
    print("🧙 WIZARD KONFIGURASI OTOMASI GITHUB & PYTHONANYWHERE")
    print("=" * 60)
    print("Panduan ini akan membantu Anda menyimpan token kredensial")
    print("ke dalam file lokal .env.deploy yang aman (ter-ignore dari Git).\n")

    # Ambil nilai saat ini jika ada
    existing = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip().strip('"').strip("'")

    # 1. GitHub
    print("--- [1/2] Konfigurasi GitHub ---")
    gh_user_def = existing.get("GITHUB_USERNAME", "")
    gh_user = input(f"Username GitHub [{gh_user_def}]: ").strip() or gh_user_def

    gh_repo_def = existing.get("GITHUB_REPO", "presensi-ekskul")
    gh_repo = input(f"Nama Repositori [{gh_repo_def}]: ").strip() or gh_repo_def

    gh_token_prompt = "GitHub Personal Access Token (ghp_...): "
    if existing.get("GITHUB_TOKEN"):
        gh_token_prompt = "GitHub Token (tekan Enter untuk tidak mengubah): "
    gh_token = input(gh_token_prompt).strip() or existing.get("GITHUB_TOKEN", "")

    # 2. PythonAnywhere
    print("\n--- [2/2] Konfigurasi PythonAnywhere ---")
    pa_user_def = existing.get("PYTHONANYWHERE_USERNAME", "")
    pa_user = input(f"Username PythonAnywhere [{pa_user_def}]: ").strip() or pa_user_def

    pa_domain_def = existing.get("PYTHONANYWHERE_DOMAIN", f"{pa_user}.pythonanywhere.com" if pa_user else "")
    pa_domain = input(f"Domain WebApp [{pa_domain_def}]: ").strip() or pa_domain_def

    pa_token_prompt = "PythonAnywhere API Token: "
    if existing.get("PYTHONANYWHERE_API_TOKEN"):
        pa_token_prompt = "PythonAnywhere API Token (tekan Enter untuk tidak mengubah): "
    pa_token = input(pa_token_prompt).strip() or existing.get("PYTHONANYWHERE_API_TOKEN", "")

    # Simpan ke .env.deploy
    content = f"""# Konfigurasi Otomatisasi Deploy GitHub & PythonAnywhere
GITHUB_USERNAME={gh_user}
GITHUB_REPO={gh_repo}
GITHUB_TOKEN={gh_token}

PYTHONANYWHERE_USERNAME={pa_user}
PYTHONANYWHERE_DOMAIN={pa_domain}
PYTHONANYWHERE_API_TOKEN={pa_token}
"""

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    os.chmod(ENV_FILE, 0o600)
    print("\n" + "=" * 60)
    print("✅ Konfigurasi berhasil disimpan ke .env.deploy!")
    print("Untuk menguji koneksi sekarang, jalankan:")
    print("  python3 deploy.py check")
    print("=" * 60)

if __name__ == "__main__":
    main()
