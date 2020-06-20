# -*- mode: python -*-

block_cipher = None


a = Analysis(['start_rfid_server.py'],
             pathex=None,
             binaries=None,
             datas=None,
             hiddenimports=['pymysql'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='rfid_server',
          debug=False,
          strip=False,
          upx=True,
          console=False,
          icon='rfid.ico')

coll = COLLECT(
              [('settings.ini','common\settings.ini','DATA')],
              strip=None,
              upx=True,
              name='common')