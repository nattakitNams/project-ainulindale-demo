@echo off
rem จำลอง "หน้าเว็บที่ deploy แล้ว" บนเครื่อง (คนละ origin กับตัวประมวลผล) — ใช้ทดสอบก่อนขึ้น GitHub Pages / Cloudflare Pages
cd /d "%~dp0"
python -m http.server 8090 --bind 127.0.0.1 -d web
