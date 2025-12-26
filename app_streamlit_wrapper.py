"""
Streamlit 앱 실행 래퍼
이 파일은 exe로 변환하기 위한 래퍼 스크립트입니다.
"""
import subprocess
import sys
import os
from pathlib import Path

def main():
    """Streamlit 앱 실행"""
    try:
        # PyInstaller로 빌드된 경우 임시 디렉토리 확인
        if getattr(sys, 'frozen', False):
            # PyInstaller의 임시 디렉토리 (_MEIPASS)
            if hasattr(sys, '_MEIPASS'):
                # --onefile 모드: 임시 디렉토리에서 파일 찾기
                base_dir = sys._MEIPASS
            else:
                # --onedir 모드: 실행 파일과 같은 디렉토리
                base_dir = os.path.dirname(sys.executable)
        else:
            # Python 스크립트로 실행 중인 경우
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        app_path = os.path.join(base_dir, "app.py")
        settle_baemin_path = os.path.join(base_dir, "settle_baemin.py")
        
        # app.py 파일이 존재하는지 확인
        if not os.path.exists(app_path):
            print(f"오류: app.py 파일을 찾을 수 없습니다.")
            print(f"검색 경로: {app_path}")
            print(f"기본 디렉토리: {base_dir}")
            if hasattr(sys, '_MEIPASS'):
                print(f"임시 디렉토리 (_MEIPASS): {sys._MEIPASS}")
            input("Enter 키를 눌러 종료하세요...")
            sys.exit(1)
        
        # settle_baemin.py도 확인 (선택사항)
        if not os.path.exists(settle_baemin_path):
            print(f"경고: settle_baemin.py를 찾을 수 없습니다: {settle_baemin_path}")
            print("app.py는 독립적으로 실행됩니다.")
        
        # Streamlit 실행
        print("배민 정산 계산기 웹 앱을 시작합니다...")
        print("브라우저가 자동으로 열립니다.")
        print()
        print(f"디버그 정보:")
        print(f"  - Python 실행 파일: {sys.executable}")
        print(f"  - app.py 경로: {app_path}")
        print(f"  - 기본 디렉토리: {base_dir}")
        print()
        
        # Streamlit 실행 (오류 캡처)
        try:
            result = subprocess.run(
                [
                    sys.executable, 
                    "-m", 
                    "streamlit", 
                    "run", 
                    app_path,
                    "--server.headless", "false",  # 브라우저 자동 열기
                    "--server.port", "8501",
                    "--browser.gatherUsageStats", "false"
                ],
                check=True,
                capture_output=False,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"\n오류: Streamlit 실행 실패")
            print(f"반환 코드: {e.returncode}")
            print(f"오류 메시지: {e}")
            print("\n가능한 원인:")
            print("1. Streamlit이 설치되지 않았거나 경로를 찾을 수 없습니다")
            print("2. app.py 파일에 오류가 있습니다")
            print("3. 필요한 모듈이 누락되었습니다")
            print()
            input("Enter 키를 눌러 종료하세요...")
            sys.exit(1)
        except FileNotFoundError:
            print(f"\n오류: Python 또는 Streamlit을 찾을 수 없습니다")
            print(f"Python 경로: {sys.executable}")
            print("\n해결 방법:")
            print("1. Python이 올바르게 설치되어 있는지 확인하세요")
            print("2. Streamlit이 설치되어 있는지 확인하세요: pip install streamlit")
            print()
            input("Enter 키를 눌러 종료하세요...")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"\n예상치 못한 오류 발생:")
        print(f"오류 타입: {type(e).__name__}")
        print(f"오류 메시지: {e}")
        print("\n상세 오류:")
        traceback.print_exc()
        print()
        input("Enter 키를 눌러 종료하세요...")
        sys.exit(1)

if __name__ == "__main__":
    main()

