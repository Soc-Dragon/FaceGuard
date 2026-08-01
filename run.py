"""FaceGuard 顶层入口。

PyInstaller 必须以本文件作为入口（而非 faceguard/__main__.py）。
原因：直接把包内 __main__.py 当脚本执行时 __package__ 为空，
`from . import xxx` 这类相对导入会报
"ImportError: attempted relative import with no known parent package"。
通过顶层入口导入 faceguard 包，包内相对导入即可正常工作。
"""

from faceguard.__main__ import main

if __name__ == "__main__":
    import sys
    sys.exit(main())
