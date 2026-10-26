# -*- mode: python ; coding: utf-8 -*-
a=Analysis(['pc_app.py'],pathex=[],binaries=[],datas=[('assets','assets'),('LICENSE','.'),('THIRD_PARTY_LICENSES.txt','.')],hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['numpy','dxcam','cv2','matplotlib','pandas','scipy','polars','IPython','pytest'],noarchive=False,optimize=1)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='RuneTimer',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,icon=['assets/ui/high/maple_timer_custom_icon.ico'],manifest='pc.manifest')
