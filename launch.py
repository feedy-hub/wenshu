"""Quiet Windows launcher with an actionable error message."""
import os
import sys
import traceback
from pathlib import Path

root=Path(__file__).resolve().parent
os.chdir(root)
app_dir=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else root
default_data=Path.home()/'Library'/'Application Support'/'文枢' if sys.platform=='darwin' and getattr(sys,'frozen',False) else app_dir/'.data'
data=Path(os.environ.get('SHORE_READER_DATA',str(default_data)))
data.mkdir(parents=True,exist_ok=True)
log=open(data/'startup.log','a',encoding='utf-8')
sys.stdout=log
sys.stderr=log
try:
    from app import main
    sys.argv=[str(root/'app.py'),*(sys.argv[1:] or ['--open'])]
    main()
except Exception:
    traceback.print_exc()
    log.flush()
    if os.name=='nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,'文枢启动失败。请查看数据目录中的 startup.log，或按使用说明检查运行环境及端口。','文枢 · 启动提示',0)
finally:
    log.close()
