@echo off
chcp 65001 >nul
echo ===================================
echo 빌드 파일 정리 스크립트
echo ===================================
echo.

REM 실행 중인 exe 프로세스 종료
echo [1/3] 실행 중인 프로세스 종료 중...
taskkill /F /IM "배민정산계산기_CLI.exe" >nul 2>&1
if errorlevel 1 (
    echo 배민정산계산기_CLI.exe가 실행 중이지 않습니다.
) else (
    echo 배민정산계산기_CLI.exe 프로세스를 종료했습니다.
)

taskkill /F /IM "배민정산계산기_웹.exe" >nul 2>&1
if errorlevel 1 (
    echo 배민정산계산기_웹.exe가 실행 중이지 않습니다.
) else (
    echo 배민정산계산기_웹.exe 프로세스를 종료했습니다.
)

timeout /t 2 /nobreak >nul

REM 빌드 폴더 삭제
echo.
echo [2/3] build 폴더 삭제 중...
if exist "build" (
    rmdir /s /q "build"
    echo build 폴더를 삭제했습니다.
) else (
    echo build 폴더가 없습니다.
)

REM dist 폴더 삭제
echo.
echo [3/3] dist 폴더 삭제 중...
if exist "dist" (
    REM 파일 삭제
    del /f /q "dist\*.*" >nul 2>&1
    timeout /t 1 /nobreak >nul
    rmdir /s /q "dist"
    if exist "dist" (
        echo 경고: dist 폴더를 완전히 삭제할 수 없습니다.
        echo 일부 파일이 사용 중일 수 있습니다.
        echo 수동으로 확인 후 다시 시도하세요.
    ) else (
        echo dist 폴더를 삭제했습니다.
    )
) else (
    echo dist 폴더가 없습니다.
)

echo.
echo ===================================
echo 정리 완료!
echo ===================================
pause

