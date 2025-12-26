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

REM 실행 중인 exe 프로세스 종료 시도
echo 실행 중인 프로세스 확인 중...
taskkill /F /IM "배민정산계산기_CLI.exe" >nul 2>&1
taskkill /F /IM "배민정산계산기_웹.exe" >nul 2>&1
timeout /t 1 /nobreak >nul

REM 빌드 폴더 삭제
if exist "build" (
    echo build 폴더 삭제 중...
    rmdir /s /q "build" 2>nul
)

REM dist 폴더의 파일 삭제 (더 강력한 방법)
if exist "dist" (
    echo dist 폴더 정리 중...
    REM dist 폴더 내의 모든 파일 삭제 시도
    del /f /q "dist\*.*" >nul 2>&1
    REM 잠시 대기 후 폴더 삭제
    timeout /t 1 /nobreak >nul
    rmdir /s /q "dist" 2>nul
    REM 폴더가 여전히 있으면 다시 시도
    if exist "dist" (
        echo 경고: dist 폴더를 완전히 삭제할 수 없습니다.
        echo 실행 중인 파일이 있을 수 있습니다. 수동으로 확인해주세요.
        echo.
        pause
    )
)

REM spec 파일 삭제 (선택사항 - 기존 spec 파일 유지하려면 주석 처리)
REM if exist "*.spec" del /q "*.spec"

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

REM spec 파일이 있으면 사용, 없으면 직접 빌드
if exist "배민정산계산기_웹.spec" (
    echo spec 파일을 사용하여 빌드합니다...
    pyinstaller 배민정산계산기_웹.spec ^
        --clean ^
        --noconfirm
) else (
    echo 직접 빌드합니다...
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
)

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

