import os
import sudachipy
import sudachidict_core
import jamdict
import jamdict_data

sudachi_data = os.path.dirname(sudachidict_core.__file__)
jamdict_pkg = os.path.dirname(jamdict.__file__)
jamdict_data_pkg = os.path.dirname(jamdict_data.__file__)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web', 'web'),
        (sudachi_data, 'sudachidict_core'),
        (jamdict_pkg, 'jamdict'),
        (jamdict_data_pkg, 'jamdict_data'),
    ],
    hiddenimports=['server', 'server.main', 'server.analyze', 'server.db',
                   'server.dictionary', 'server.render', 'server.scheduler',
                   'server.stats', 'server.export', 'server.resources',
                   'server.importer', 'server.importer.vocab_intake',
                   'server.importer.extract'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='japanese-reader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
