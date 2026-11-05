@echo off
rem ตัวประมวลผลในเครื่อง (Ainulindale v1) — รันค้างไว้ แล้วใช้งานผ่านหน้าเว็บ
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m app.server
pause
