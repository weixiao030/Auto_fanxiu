"""PyInstaller entry. A self-test uses an isolated profile and never touches a game."""
import os
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        index = sys.argv.index('--self-test')
        report = Path(sys.argv[index+1]).resolve()
        with tempfile.TemporaryDirectory(prefix='FanxiuSelfTest-') as folder:
            os.environ['FANXIU_ASSISTANT_DATA_DIR'] = folder
            from fanxiu_assistant.desktop import self_test
            self_test(report)
    else:
        from fanxiu_assistant.desktop import main
        main()
