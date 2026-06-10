# ─── TilinX Website Installer ──────────────────────────
# Run this from the repo root:
#   python website/setup.py

import os, sys, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
DEST = "/home/runner/tilinx/website"
FILES = [
    "website.py", "models.py", "start.sh", "deploy.sh", "nginx.conf",
    "requirements.txt", "robots.txt", "sitemap.xml",
]

def copy():
    os.makedirs(DEST, exist_ok=True)
    for f in FILES:
        src = os.path.join(BASE, f)
        dst = os.path.join(DEST, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✅ {f}")
    for sub in ["assets/css", "assets/js", "assets/img", "assets/fonts", "templates", "api", "admin"]:
        src_dir = os.path.join(BASE, sub)
        dst_dir = os.path.join(DEST, sub)
        if os.path.exists(src_dir):
            shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
            print(f"  ✅ {sub}/")
    print(f"\n📁 Files copied to {DEST}")
    print("▶ Run: bash website/deploy.sh")

if __name__ == "__main__":
    copy()
