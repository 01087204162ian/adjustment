# EXE 파일 변환 가이드

## 개요

adjustment 프로젝트의 Python 스크립트를 Windows 실행 파일(.exe)로 변환하는 방법입니다.

**대상 스크립트:**
1. `settle_baemin.py` - CLI 스크립트 (명령줄 버전)
2. `app.py` - Streamlit 웹 앱 (웹 인터페이스 버전)

---

## 사전 준비

### 1. PyInstaller 설치

가상환경이 활성화된 상태에서:

```bash
pip install pyinstaller
```

### 2. Python 버전 확인

```bash
python --version
```

Python 3.8 이상 권장

---

## 방법 1: CLI 스크립트 (settle_baemin.py) 변환

### 기본 변환

```bash
pyinstaller settle_baemin.py --name "배민정산계산기" --onefile
```

### 고급 옵션 (권장)

```bash
pyinstaller settle_baemin.py ^
    --name "배민정산계산기" ^
    --onefile ^
    --windowed ^
    --icon=icon.ico ^
    --add-data "requirements.txt;." ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    --hidden-import numpy
```

### 옵션 설명

- `--name`: 생성될 exe 파일 이름
- `--onefile`: 단일 실행 파일 생성 (모든 의존성 포함)
- `--windowed`: 콘솔 창 숨기기 (GUI 앱처럼)
- `--icon`: 아이콘 파일 지정 (선택사항)
- `--hidden-import`: 자동 감지되지 않는 모듈 명시
- `--add-data`: 추가 파일 포함

### 실행 파일 사용법

변환 후 `dist` 폴더에 exe 파일이 생성됩니다:

```bash
# 사용법
배민정산계산기.exe 입력파일.xlsx --out 출력파일.xlsx
```

---

## 방법 2: Streamlit 앱 (app.py) 변환

Streamlit 앱은 웹 서버이므로 일반 exe와는 다르게 처리해야 합니다.

### 방법 2-1: 래퍼 스크립트 사용 (권장)

`run_streamlit_app.py` 파일 생성:

```python
import subprocess
import sys
import os

def main():
    # 현재 스크립트의 디렉토리
    base_dir = os.path.dirname(os.path.abspath(sys.executable))
    app_path = os.path.join(base_dir, "app.py")
    
    # Streamlit 실행
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])

if __name__ == "__main__":
    main()
```

이 래퍼 스크립트를 exe로 변환:

```bash
pyinstaller run_streamlit_app.py ^
    --name "배민정산계산기_웹" ^
    --onefile ^
    --add-data "app.py;." ^
    --add-data "settle_baemin.py;." ^
    --hidden-import streamlit ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    --hidden-import numpy
```

**주의사항:** 이 방법은 Streamlit과 모든 의존성을 포함해야 하므로 파일 크기가 매우 큽니다 (100MB 이상).

### 방법 2-2: 배치 파일로 실행 (간단한 방법)

`배민정산계산기.bat` 파일 생성:

```batch
@echo off
cd /d "%~dp0"
python -m streamlit run app.py
pause
```

이 배치 파일을 exe로 변환하는 도구 사용 (예: Bat To Exe Converter)

---

## 빌드 스크립트

### build_exe.bat (Windows)

```batch
@echo off
echo ===================================
echo 배민 정산 계산기 EXE 빌드 스크립트
echo ===================================
echo.

REM 가상환경 활성화
call venv\Scripts\activate.bat

REM PyInstaller 설치 확인
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller가 설치되지 않았습니다. 설치 중...
    pip install pyinstaller
)

echo.
echo [1/2] CLI 버전 빌드 중...
pyinstaller settle_baemin.py ^
    --name "배민정산계산기_CLI" ^
    --onefile ^
    --clean ^
    --noconfirm ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    --hidden-import numpy

if errorlevel 1 (
    echo CLI 버전 빌드 실패!
    pause
    exit /b 1
)

echo.
echo [2/2] Streamlit 버전 빌드 중...
pyinstaller app_streamlit_wrapper.py ^
    --name "배민정산계산기_웹" ^
    --onefile ^
    --clean ^
    --noconfirm ^
    --add-data "app.py;." ^
    --add-data "settle_baemin.py;." ^
    --hidden-import streamlit ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    --hidden-import numpy

if errorlevel 1 (
    echo Streamlit 버전 빌드 실패!
    pause
    exit /b 1
)

echo.
echo ===================================
echo 빌드 완료!
echo ===================================
echo.
echo 생성된 파일:
echo - dist\배민정산계산기_CLI.exe
echo - dist\배민정산계산기_웹.exe
echo.
pause
```

---

## 문제 해결

### 1. "ModuleNotFoundError" 오류

필요한 모듈을 `--hidden-import`로 추가:

```bash
pyinstaller settle_baemin.py --hidden-import 모듈명
```

### 2. 파일 크기가 너무 큰 경우

- `--onefile` 대신 폴더 형태로 빌드 (더 작은 크기, 하지만 여러 파일)
- 불필요한 모듈 제외: `--exclude-module 모듈명`

### 3. 실행 시 오류 발생

디버그 모드로 빌드:

```bash
pyinstaller settle_baemin.py --log-level DEBUG
```

### 4. Streamlit 앱이 실행되지 않는 경우

- Streamlit의 모든 의존성 포함 확인
- `streamlit run` 명령이 PATH에 있는지 확인
- 임시 해결: 배치 파일 방식 사용

---

## 배포 고려사항

### 1. 파일 크기

- CLI 버전: 약 50-100MB
- Streamlit 버전: 약 200-300MB

### 2. Windows Defender 경고

exe 파일이 처음 실행될 때 Windows Defender가 경고할 수 있습니다. 
이것은 정상이며, "추가 정보" → "실행"을 클릭하면 됩니다.

### 3. 코드 서명 (선택사항)

신뢰성을 높이려면 코드 서명 인증서를 사용할 수 있습니다.

### 4. 배포 방법

1. **직접 배포**: exe 파일만 제공
2. **설치 프로그램**: Inno Setup, NSIS 등으로 설치 프로그램 제작
3. **압축 파일**: ZIP으로 묶어서 배포

---

## 테스트 체크리스트

빌드 후 다음을 테스트하세요:

- [ ] exe 파일이 정상적으로 실행되는가?
- [ ] 필요한 모든 모듈이 포함되어 있는가?
- [ ] Excel 파일을 읽을 수 있는가?
- [ ] 결과 파일을 정상적으로 생성하는가?
- [ ] 오류 메시지가 올바르게 표시되는가?
- [ ] 다른 Windows PC에서 실행 가능한가? (Python 미설치 환경)

---

## 참고 자료

- [PyInstaller 공식 문서](https://pyinstaller.org/)
- [PyInstaller 옵션 목록](https://pyinstaller.org/en/stable/usage.html#options)

