@echo off
setlocal enabledelayedexpansion

REM ====== CẤU HÌNH (SỬA CHO PHÙ HỢP MÁY ANH) ======
set "REPO_DIR=C:\KT_SL_TTD\DAITRUNGBO\UP_BABTIN\auto-upload-bantin"
set "SRC_DIR=D:\bantin"   REM <<< Thư mục chứa file bản tin gốc của anh
set "DST_FILE=%REPO_DIR%\bantin\ban_tin.pdf"
REM =================================================

REM Lấy ngày hôm nay & hôm qua (yyyyMMdd)
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd')"') do set "TODAY=%%i"
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString('yyyyMMdd')"') do set "YEST=%%i"

REM Ứng viên theo mẫu tên
set "CAND1=%SRC_DIR%\BanTin_QT_%TODAY%_1700.pdf"
set "CAND2=%SRC_DIR%\BanTin_QT_%YEST%_1700.pdf"

set "SRC_FILE="

if exist "%CAND1%" set "SRC_FILE=%CAND1%"
if not defined SRC_FILE if exist "%CAND2%" set "SRC_FILE=%CAND2%"

REM Fallback: lấy PDF mới nhất trong SRC_DIR
if not defined SRC_FILE (
  for /f "delims=" %%f in ('dir /b /a:-d /o:-d "%SRC_DIR%\*.pdf" 2^>nul') do (
    set "SRC_FILE=%SRC_DIR%\%%f"
    goto :haveSrc
  )
)

:haveSrc
if not defined SRC_FILE (
  echo [ERROR] Khong tim thay file PDF trong "%SRC_DIR%".
  pause
  exit /b 1
)

echo [INFO] Nguon: "%SRC_FILE%"
echo [INFO] Dich : "%DST_FILE%"

REM Đảm bảo thư mục bantin tồn tại
if not exist "%REPO_DIR%\bantin" mkdir "%REPO_DIR%\Upbantin"

REM Copy đè
copy /Y "%SRC_FILE%" "%DST_FILE%" >nul
if errorlevel 1 (
  echo [ERROR] Copy that bai.
  pause
  exit /b 2
)

REM Git add/commit/push
pushd "%REPO_DIR%"
git add "bantin\ban_tin.pdf"

REM Kiểm tra có thay đổi không
set "CHANGED="
for /f %%s in ('git status --porcelain') do set "CHANGED=1"

if not defined CHANGED (
  echo [INFO] Khong co thay doi de commit.
) else (
  for /f %%d in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')"') do set "NOW=%%d"
  git commit -m "Update ban_tin.pdf at %NOW%"
)

git push

popd
echo [DONE] Da push len GitHub.
pause
