@echo off
rem ถอนการติดตั้ง: ลบโฟลเดอร์แอปนี้ทั้งโฟลเดอร์ (ถามยืนยันก่อน)
chcp 65001 >nul
setlocal
set "APPDIR=%~dp0"
if not exist "%APPDIR%app\launch.py" (
  echo ไม่ใช่โฟลเดอร์ Ainulindale — ยกเลิก
  pause & exit /b 1
)
echo.
echo  จะลบโฟลเดอร์นี้ทั้งหมด:  %APPDIR%
echo  (โปรแกรม, Python ส่วนตัว, แพ็กเกจ, และผลลัพธ์ใน workspace ของโฟลเดอร์นี้)
echo.
if exist "%APPDIR%settings.json" (
  echo  ที่เก็บผลลัพธ์ตามการตั้งค่า:
  type "%APPDIR%settings.json"
  echo.
  echo  ถ้าที่เก็บผลลัพธ์อยู่นอกโฟลเดอร์นี้ จะไม่ถูกลบ — ลบเองถ้าไม่ต้องการ
)
echo  ไฟล์ข้อมูลต้นทางของคุณ (เช่น ไฟล์ประชากร/น้ำท่วม) ไม่ถูกลบ เพราะแอปไม่ได้คัดลอกมา
echo  ปิดหน้าต่าง Ainulindale (ตัวประมวลผล) ก่อน ไม่งั้นบางไฟล์ลบไม่ได้
echo.
set /p OK=พิมพ์ YES แล้วกด Enter เพื่อยืนยัน:
if /i not "%OK%"=="YES" (
  echo ยกเลิก
  pause & exit /b
)
cd /d "%TEMP%"
start "" /min cmd /c "timeout /t 2 /nobreak >nul & rmdir /s /q "%APPDIR%" & echo ลบแล้ว"
exit
