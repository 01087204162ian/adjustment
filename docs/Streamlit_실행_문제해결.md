# Streamlit 웹 앱 실행 문제 해결 가이드

## 문제: exe 파일 실행 시 브라우저가 열리지 않음

### 원인

Streamlit은 웹 서버 애플리케이션이므로, exe 파일로 변환할 때 다음과 같은 문제가 발생할 수 있습니다:

1. **Streamlit 모듈 경로 문제**: exe 환경에서 Streamlit 모듈을 찾지 못함
2. **Python 인터프리터 문제**: exe 내부의 Python이 Streamlit을 실행하지 못함
3. **의존성 누락**: Streamlit의 모든 의존성이 포함되지 않음

### 해결 방법

#### 방법 1: 배치 파일 사용 (권장)

가장 간단하고 안정적인 방법입니다.

**`run_streamlit_app.bat` 파일 사용:**

```batch
run_streamlit_app.bat
```

이 방법은:
- Python과 Streamlit이 설치된 환경에서 실행
- 가장 안정적이고 빠름
- 브라우저 자동 열기 정상 작동

#### 방법 2: Python 직접 실행

```bash
# 가상환경 활성화
venv\Scripts\activate

# Streamlit 실행
streamlit run app.py
```

#### 방법 3: exe 파일 사용 (제한적)

exe 파일은 현재 완전히 독립적으로 작동하지 않을 수 있습니다. 

**개선된 exe 파일 사용:**

1. exe 파일을 다시 빌드 (개선된 래퍼 스크립트 사용)
2. 실행 시 디버그 정보 확인
3. 오류 메시지에 따라 문제 해결

### 디버깅

exe 파일 실행 시 다음 정보를 확인하세요:

1. **디버그 정보 출력 확인**
   - Python 실행 파일 경로
   - app.py 경로
   - 기본 디렉토리

2. **오류 메시지 확인**
   - Streamlit 실행 실패 원인
   - 모듈 누락 여부

3. **수동 테스트**
   ```bash
   # Python에서 직접 테스트
   python app_streamlit_wrapper.py
   ```

### 권장 사항

**프로덕션 환경에서는:**

1. **배치 파일 방식 사용** (가장 안정적)
   - `run_streamlit_app.bat` 실행
   - Python 환경이 필요하지만 가장 확실함

2. **설치 프로그램 제공**
   - Python + Streamlit 자동 설치
   - 배치 파일 실행

3. **웹 서버 배포** (고급)
   - Streamlit Cloud
   - 자체 서버에 배포

### 대안: CLI 버전 사용

웹 인터페이스가 필요하지 않다면 CLI 버전을 사용하세요:

```bash
배민정산계산기_CLI.exe 입력파일.xlsx --out 출력파일.xlsx
```

이 버전은 완전히 독립적으로 작동합니다.

### 향후 개선

1. Streamlit 완전 포함 exe 빌드 (매우 큰 파일 크기)
2. 웹 서버 배포 버전 제공
3. 설치 프로그램으로 Python 환경 자동 구성

