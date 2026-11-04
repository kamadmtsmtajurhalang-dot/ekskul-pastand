#!/usr/bin/env python3
"""
Skrip Otomatisasi Deploy Presensi Ekskul MTs Muhammadiyah Tajurhalang
Sinkronisasi Git -> GitHub -> PythonAnywhere (Git Pull & Web Reload)
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.deploy")

def load_env():
    """Membaca konfigurasi dari file .env.deploy atau environment variables"""
    config = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    
    # Environment variables overwrite file configs
    for key in ["GITHUB_USERNAME", "GITHUB_REPO", "GITHUB_TOKEN", 
                "PYTHONANYWHERE_USERNAME", "PYTHONANYWHERE_API_TOKEN", "PYTHONANYWHERE_DOMAIN"]:
        if os.environ.get(key):
            config[key] = os.environ.get(key)
            
    return config

def pa_api_request(endpoint, token, method="GET", data=None):
    """Kirim request ke PythonAnywhere API"""
    url = f"https://www.pythonanywhere.com/api/v0/user/{endpoint}"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            if body:
                return resp.status, json.loads(body)
            return resp.status, {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"error": err_body}
    except Exception as e:
        return 500, {"error": str(e)}

def check_status(cfg):
    """Cek koneksi ke GitHub dan PythonAnywhere"""
    print("=" * 60)
    print("🔍 MEMERIKSA STATUS KONEKSI OTOMATISASI")
    print("=" * 60)
    
    # 1. Cek Konfigurasi GitHub
    gh_user = cfg.get("GITHUB_USERNAME")
    gh_repo = cfg.get("GITHUB_REPO")
    gh_token = cfg.get("GITHUB_TOKEN")
    
    print("\n[1] GitHub Configuration:")
    if gh_user and gh_repo and gh_token:
        masked_token = gh_token[:4] + "..." + gh_token[-4:] if len(gh_token) > 8 else "***"
        print(f"  - User  : {gh_user}")
        print(f"  - Repo  : {gh_repo}")
        print(f"  - Token : {masked_token}")
        
        # Test GitHub API
        gh_req = urllib.request.Request(
            f"https://api.github.com/repos/{gh_user}/{gh_repo}",
            headers={"Authorization": f"Bearer {gh_token}", "User-Agent": "Antigravity-Deploy"}
        )
        try:
            with urllib.request.urlopen(gh_req, timeout=10) as r:
                res = json.loads(r.read().decode())
                print(f"  ✅ Koneksi GitHub Berhasil! Repo ditemukan: {res.get('full_name')}")
        except Exception as e:
            print(f"  ⚠️ Peringatan GitHub: {e}")
    else:
        print("  ❌ Konfigurasi GitHub belum lengkap di .env.deploy")

    # 2. Cek Konfigurasi PythonAnywhere
    pa_user = cfg.get("PYTHONANYWHERE_USERNAME")
    pa_token = cfg.get("PYTHONANYWHERE_API_TOKEN")
    pa_domain = cfg.get("PYTHONANYWHERE_DOMAIN") or (f"{pa_user}.pythonanywhere.com" if pa_user else None)
    
    print("\n[2] PythonAnywhere Configuration:")
    if pa_user and pa_token:
        masked_pa = pa_token[:4] + "..." + pa_token[-4:] if len(pa_token) > 8 else "***"
        print(f"  - User   : {pa_user}")
        print(f"  - Domain : {pa_domain}")
        print(f"  - Token  : {masked_pa}")
        
        # Test CPU quota API
        status, res = pa_api_request(f"{pa_user}/cpu/", pa_token)
        if status == 200:
            print(f"  ✅ Koneksi PythonAnywhere Berhasil!")
            print(f"     CPU Usage: {res.get('daily_cpu_total_usage_seconds', 0):.1f}s / {res.get('daily_cpu_limit_seconds', 0):.0f}s")
        else:
            print(f"  ❌ Gagal koneksi PythonAnywhere: (HTTP {status}) {res}")
            
        # Test Webapp
        if pa_domain:
            status, res = pa_api_request(f"{pa_user}/webapps/{pa_domain}/", pa_token)
            if status == 200:
                print(f"  ✅ Webapp ditemukan di PythonAnywhere: {pa_domain}")
            else:
                print(f"  ⚠️ Webapp {pa_domain} belum terdaftar atau dicek: {res}")
    else:
        print("  ❌ Konfigurasi PythonAnywhere belum lengkap di .env.deploy")

def push_github(cfg):
    """Push commit terbaru ke GitHub"""
    print("\n[GIT] Mempersiapkan push ke GitHub...")
    gh_user = cfg.get("GITHUB_USERNAME")
    gh_repo = cfg.get("GITHUB_REPO")
    gh_token = cfg.get("GITHUB_TOKEN")
    
    if not (gh_user and gh_repo and gh_token):
        print("❌ Gagal: Kredensial GitHub tidak lengkap.")
        return False
        
    remote_url = f"https://{gh_token}@github.com/{gh_user}/{gh_repo}.git"
    
    # Update remote origin
    subprocess.run(["git", "remote", "remove", "origin"], stderr=subprocess.DEVNULL)
    res = subprocess.run(["git", "remote", "add", "origin", remote_url], capture_output=True, text=True)
    if res.returncode != 0:
        subprocess.run(["git", "remote", "set-url", "origin", remote_url])
        
    # Get current branch
    branch_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    branch = branch_res.stdout.strip() or "master"
    
    print(f"🚀 Pushing branch '{branch}' ke GitHub...")
    push_res = subprocess.run(["git", "push", "-u", "origin", branch], capture_output=True, text=True)
    
    if push_res.returncode == 0:
        print("✅ Berhasil push ke GitHub!")
        return True
    else:
        # Bersihkan token dari output error jika ada
        safe_err = push_res.stderr.replace(gh_token, "[TOKEN]")
        print(f"❌ Gagal push ke GitHub:\n{safe_err}")
        return False

def reload_pythonanywhere(cfg):
    """Reload web application di PythonAnywhere via API"""
    pa_user = cfg.get("PYTHONANYWHERE_USERNAME")
    pa_token = cfg.get("PYTHONANYWHERE_API_TOKEN")
    pa_domain = cfg.get("PYTHONANYWHERE_DOMAIN") or f"{pa_user}.pythonanywhere.com"
    
    if not (pa_user and pa_token):
        print("❌ Gagal: Kredensial PythonAnywhere tidak lengkap.")
        return False
        
    print(f"\n🔄 Melakukan reload web app di PythonAnywhere ({pa_domain})...")
    status, res = pa_api_request(f"{pa_user}/webapps/{pa_domain}/reload/", pa_token, method="POST")
    
    if status in (200, 201):
        print(f"✅ Web App berhasil di-reload! Versi terbaru sudah aktif di: https://{pa_domain}")
        return True
    else:
        print(f"❌ Gagal reload web app (HTTP {status}): {res}")
        return False

def main():
    cfg = load_env()
    
    action = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if action == "check":
        check_status(cfg)
    elif action == "github":
        push_github(cfg)
    elif action == "reload":
        reload_pythonanywhere(cfg)
    elif action == "all":
        print("🚀 Memulai Deploy Otomatis (GitHub & PythonAnywhere)...")
        if push_github(cfg):
            reload_pythonanywhere(cfg)
    else:
        print("Penggunaan:")
        print("  python3 deploy.py check   - Cek status koneksi GitHub & PythonAnywhere")
        print("  python3 deploy.py github  - Push kode ke GitHub")
        print("  python3 deploy.py reload  - Reload web app di PythonAnywhere")
        print("  python3 deploy.py all     - Push ke GitHub lalu reload PythonAnywhere")

if __name__ == "__main__":
    main()
