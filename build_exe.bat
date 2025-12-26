@echo off
chcp 65001 >nul
echo ===================================
echo 배민 정산 계산기 EXE 빌드 스크립트
echo ===================================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM 가상환경 활성화
if exist "venv\Scripts\activate.bat" (
    echo [1/5] 가상환경 활성화 중...
    call venv\Scripts\activate.bat
) else (
    echo 경고: 가상환경을 찾을 수 없습니다.
    echo Python 환경에서 직접 실행 중입니다.
)

REM PyInstaller 설치 확인
echo.
echo [2/5] PyInstaller 확인 중...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller가 설치되지 않았습니다. 설치 중...
    pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller 설치 실패!
        pause
        exit /b 1
    )
) else (
    echo PyInstaller가 이미 설치되어 있습니다.
)

REM 기존 빌드 파일 정리
echo.
echo [3/5] 기존 빌드 파일 정리 중...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /q "*.spec"

REM CLI 버전 빌드
echo.
echo [4/5] CLI 버전 빌드 중...
pyinstaller settle_baemin.py ^
    --name "배민정산계산기_CLI" ^
    --onefile ^
    --clean ^
    --noconfirm ^
    --console ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    --hidden-import numpy ^
    --hidden-import argparse

if errorlevel 1 (
    echo.
    echo CLI 버전 빌드 실패!
    pause
    exit /b 1
)

echo CLI 버전 빌드 완료!

REM Streamlit 버전 빌드 (선택사항)
echo.
echo [5/5] Streamlit 웹 버전 빌드 중...
echo (이 작업은 시간이 오래 걸릴 수 있습니다...)

pyinstaller app_streamlit_wrapper.py ^
    --name "배민정산계산기_웹" ^
    --onefile ^
    --clean ^
    --noconfirm ^
    --console ^
    --add-data "app.py;." ^
    --add-data "settle_baemin.py;." ^
    --hidden-import streamlit ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    --hidden-import numpy ^
    --hidden-import altair ^
    --hidden-import pydeck ^
    --collect-all streamlit

if errorlevel 1 (
    echo.
    echo Streamlit 버전 빌드 실패!
    echo (CLI 버전은 정상적으로 빌드되었습니다)
    pause
    exit /b 1
)

echo Streamlit 버전 빌드 완료!

echo.
echo ===================================
echo 빌드 완료!
echo ===================================
echo.
echo 생성된 파일 위치:
echo   dist\배민정산계산기_CLI.exe
echo   dist\배민정산계산기_웹.exe
echo.
echo 파일 크기:
dir dist\*.exe | findstr /C:"배민정산계산기"
echo.
echo 테스트:
echo   dist\배민정산계산기_CLI.exe 입력파일.xlsx --out 출력파일.xlsx
echo.
pause

