@echo off
chcp 65001 >nul
echo ===================================
echo 배민 정산 계산기 웹 앱 실행
echo ===================================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM 가상환경 활성화 (있는 경우)
if exist "venv\Scripts\activate.bat" (
    echo 가상환경 활성화 중...
    call venv\Scripts\activate.bat
)

REM Streamlit 실행
echo Streamlit 웹 앱을 시작합니다...
echo 브라우저가 자동으로 열립니다.
echo.
echo 종료하려면 Ctrl+C를 누르세요.
echo.

streamlit run app.py --server.port 8501

pause

