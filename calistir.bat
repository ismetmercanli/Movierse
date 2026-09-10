@echo off
title MOVIERSE - AI Movie Discovery Platform
color 0B
mode con: cols=70 lines=15

echo ========================================
echo MOVIERSE - AI Movie Discovery Platform
echo ========================================
echo.

REM Python kontrolü
python --version 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo [HATA] Python bulunamadi!
    echo.
    echo Lutfen Python yukleyin: https://www.python.org/downloads/
    echo.
    echo Devam etmek icin bir tusa basin...
    pause >nul
    exit /b 1
)

echo [1/4] Python kontrol edildi.
echo.

REM PyQt6 kontrolü
python -c "import PyQt6" 2>nul
if errorlevel 1 (
    echo [2/4] PyQt6 yukleniyor...
    pip install PyQt6 --quiet --disable-pip-version-check
    if errorlevel 1 (
        color 0C
        echo [HATA] PyQt6 yuklenemedi!
        echo Devam etmek icin bir tusa basin...
        pause >nul
        exit /b 1
    )
    echo [2/4] PyQt6 yuklendi.
) else (
    echo [2/4] PyQt6 hazir.
)
echo.

REM psycopg2 kontrolü (PostgreSQL için)
python -c "import psycopg2" 2>nul
if errorlevel 1 (
    echo [3/4] psycopg2-binary yukleniyor...
    pip install psycopg2-binary --quiet --disable-pip-version-check
    if errorlevel 1 (
        color 0C
        echo [HATA] psycopg2-binary yuklenemedi!
        echo Devam etmek icin bir tusa basin...
        pause >nul
        exit /b 1
    )
    echo [3/4] psycopg2-binary yuklendi.
) else (
    echo [3/4] psycopg2-binary hazir.
)
echo.

REM requests kontrolü
python -c "import requests" 2>nul
if errorlevel 1 (
    echo [4/4] requests yukleniyor...
    pip install requests --quiet --disable-pip-version-check
    if errorlevel 1 (
        color 0C
        echo [HATA] requests yuklenemedi!
        echo Devam etmek icin bir tusa basin...
        pause >nul
        exit /b 1
    )
    echo [4/4] requests yuklendi.
) else (
    echo [4/4] requests hazir.
)
echo.

REM PostgreSQL servis kontrolü (isteğe bağlı)
sc query postgresql-x64-* >nul 2>&1
if errorlevel 1 (
    echo [UYARI] PostgreSQL servisi bulunamadi.
    echo Uygulama calisabilir ama veritabani baglantisi kurulamayabilir.
    echo.
) else (
    echo [BILGI] PostgreSQL servisi calisiyor.
    echo.
)

echo ========================================
echo Uygulama baslatiliyor...
echo ========================================
echo.

REM Uygulamayı başlat (hata mesajlarını görmek için)
python main.py 2>&1
set PYTHON_EXIT=%ERRORLEVEL%

if %PYTHON_EXIT% NEQ 0 (
    echo.
    echo ========================================
    echo [HATA] Uygulama baslatilamadi!
    echo ========================================
    echo.
    echo Hata kodu: %PYTHON_EXIT%
    echo.
    echo Olası nedenler:
    echo - PostgreSQL servisi calismiyor
    echo - Veritabani baglanti bilgileri yanlis
    echo - movies_db veritabani olusturulmamis
    echo - Python modulleri eksik
    echo.
    echo Cozum:
    echo 1. pgAdmin 4'te movies_db veritabaninin olusturuldugundan emin olun
    echo 2. PostgreSQL servisinin calistigindan emin olun
    echo 3. main.py dosyasindaki baglanti bilgilerini kontrol edin
    echo 4. Yukaridaki hata mesajlarini kontrol edin
    echo.
    echo.
    echo Devam etmek icin bir tusa basin...
    pause >nul
    exit /b 1
)

echo.
echo [BILGI] Uygulama kapatildi.
timeout /t 2 >nul
exit /b 0


