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
        # 현재 실행 파일의 디렉토리
        if getattr(sys, 'frozen', False):
            # exe로 실행 중인 경우
            base_dir = os.path.dirname(sys.executable)
        else:
            # Python 스크립트로 실행 중인 경우
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        app_path = os.path.join(base_dir, "app.py")
        
        # app.py 파일이 존재하는지 확인
        if not os.path.exists(app_path):
            print(f"오류: app.py 파일을 찾을 수 없습니다: {app_path}")
            input("Enter 키를 눌러 종료하세요...")
            sys.exit(1)
        
        # Streamlit 실행
        print("배민 정산 계산기 웹 앱을 시작합니다...")
        print("브라우저가 자동으로 열립니다.")
        print()
        
        subprocess.run([
            sys.executable, 
            "-m", 
            "streamlit", 
            "run", 
            app_path,
            "--server.headless", "true",
            "--server.port", "8501"
        ])
        
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {e}")
        input("Enter 키를 눌러 종료하세요...")
        sys.exit(1)

if __name__ == "__main__":
    main()

