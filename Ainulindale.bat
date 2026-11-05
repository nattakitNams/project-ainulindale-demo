@echo off
rem Ainulindale — เปิดแอป (ครั้งแรก = ตัวช่วยติดตั้งในหน้าเว็บ · ครั้งต่อไป = ตัวประมวลผล)
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONNOUSERSITE=1
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PIP_NO_CACHE_DIR=1
if exist "python\python.exe" (set "PY=python\python.exe") else (set "PY=python")
title Ainulindale — ปิดหน้าต่างนี้ = หยุดตัวประมวลผล
"%PY%" -m app.launch %*
pause
