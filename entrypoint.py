# PyInstaller 빌드용 진입점 (python -m runner.main 대신 사용)
from runner.main import main

if __name__ == "__main__":
    main()
