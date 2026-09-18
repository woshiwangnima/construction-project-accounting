# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the ConstructionAccounting desktop app.

Kept under packaging/ (not build/) because build.bat wipes build/ before each run.
Paths are derived from SPECPATH so the spec works from any checkout location.
"""

import os

ROOT = os.path.dirname(SPECPATH)

# 应用只使用 PySide6 的 QtCore / QtGui / QtWidgets。
# 以下模块与本应用无关（无 Web 引擎、QML/Quick、3D、图表、多媒体、串口/蓝牙等），
# 排除后可显著缩小发布包体积。新增第三方依赖时请同步复查本清单。
QT_EXCLUDES = [
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick', 'PySide6.QtWebView',
    'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtNetworkAuth',
    'PySide6.QtQml', 'PySide6.QtQmlModels', 'PySide6.QtQmlWorkerScript',
    'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2',
    'PySide6.QtQuick3D', 'PySide6.QtQuick3DUtils', 'PySide6.QtQuick3DRender',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
    'PySide6.QtSerialPort', 'PySide6.QtSensors',
    'PySide6.QtTest', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools',
    'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtStateMachine',
    'PySide6.QtSql', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech',
]

# 界面已完全迁移到 Qt，不再需要 Tkinter。
OTHER_EXCLUDES = ['tkinter', '_tkinter', 'tkinter.font']

# `excludes` 只能挡住 Python 绑定（*.pyd），底层 Qt6 原生 DLL 仍会被 hook 收进来。
# 这里在 Analysis 之后再做一层二进制过滤，剔除真正的体积大头：
#   opengl32sw.dll  19.7 MB —— Mesa 软件渲染后备，Widgets 应用走 raster 后端，用不到
#   Qt6Quick/Qt6Qml —— 未使用 QML
#   QtOpenGL        —— 未使用 QOpenGLWidget
#   QtPdf           —— 未使用 PDF 渲染
# 注意：保留 Qt6Network（更新检查）与 Qt6Svg（qtawesome 图标）。
BIN_EXCLUDE_KEYWORDS = (
    'opengl32sw',
    'Qt6Quick', 'QtQuick',
    'Qt6Qml', 'QtQml',
    'Qt6OpenGL', 'QtOpenGL',
    'Qt6Pdf', 'QtPdf',
)

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'config'), 'config'),
        (os.path.join(ROOT, 'assets'), 'assets'),
    ],
    hiddenimports=['pyttsx3', 'comtypes', 'comtypes.gen', 'pythoncom', 'pywintypes', 'qtawesome', 'qfluentwidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=QT_EXCLUDES + OTHER_EXCLUDES,
    noarchive=False,
    optimize=0,
)

a.binaries = [
    entry for entry in a.binaries
    if not any(keyword in entry[0] for keyword in BIN_EXCLUDE_KEYWORDS)
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ConstructionAccounting',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, 'assets', 'icon.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ConstructionAccounting',
)
