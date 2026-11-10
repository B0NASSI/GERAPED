# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

app_datas = [
    ('icone.ico', '.'),
    ('logo_completa.png', '.'),
    ('Modelo/PEDIDOS.docx', 'Modelo'),
    ('versao.txt', '.'),
    ('NOTAS DE ATUALIZAÇÃO', 'NOTAS DE ATUALIZAÇÃO'),
] + collect_data_files('ttkbootstrap')
app_binaries = []
app_hiddenimports = []
# 'requests' entra aqui porque main.py importa launcher.py em runtime (dentro de
# _avisar_se_desatualizado, pra checar atualização mesmo quando o GERAPED.exe é aberto
# direto, sem passar pelo launcher) - precisa do collect_all completo, não só do hidden
# import, senão a checagem quebra em silêncio (sem crash, só nunca encontra atualização -
# já aconteceu no REQUERID). Por isso 'excludes' do app.py continua vazio: 'email'/'http'
# NÃO podem ser excluídos, requests depende deles por baixo dos panos (via urllib3).
for pacote in ('requests',):
    tmp_ret = collect_all(pacote)
    app_datas += tmp_ret[0]; app_binaries += tmp_ret[1]; app_hiddenimports += tmp_ret[2]

a_app = Analysis(
    ['main.py'],
    pathex=[],
    binaries=app_binaries,
    datas=app_datas,
    hiddenimports=app_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz_app = PYZ(a_app.pure)

# ---------------------------------------------------------------------------
# GERAPED.exe - programa principal
# ---------------------------------------------------------------------------
exe_app = EXE(
    pyz_app,
    a_app.scripts,
    [],
    exclude_binaries=True,
    name='GERAPED',
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
    icon=['icone.ico'],
)

# onedir: pasta com o .exe + dependências soltas ao lado (_internal), em vez
# de um único .exe que se autoextrai pra uma pasta temporária a cada execução
# (o que deixaria a abertura bem mais lenta).
coll_app = COLLECT(
    exe_app,
    a_app.binaries,
    a_app.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GERAPED',
)

# ---------------------------------------------------------------------------
# GERAPED Launcher.exe - checa atualizações no GitHub antes de abrir o GERAPED.exe
# ---------------------------------------------------------------------------
launcher_datas = [
    ('icone.ico', '.'),
]
launcher_binaries = []
launcher_hiddenimports = []
for pacote in ('ttkbootstrap', 'PIL', 'requests'):
    tmp_ret = collect_data_files(pacote)
    launcher_datas += tmp_ret

a_launcher = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=launcher_binaries,
    datas=launcher_datas,
    hiddenimports=launcher_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz_launcher = PYZ(a_launcher.pure)

# contents_directory: nome de pasta próprio (_internal_launcher) pra não
# colidir com o _internal do GERAPED.exe quando os dois ficam lado a lado na
# mesma pasta de instalação
exe_launcher = EXE(
    pyz_launcher,
    a_launcher.scripts,
    [],
    exclude_binaries=True,
    name='GERAPED Launcher',
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
    icon=['icone.ico'],
    contents_directory='_internal_launcher',
)

coll_launcher = COLLECT(
    exe_launcher,
    a_launcher.binaries,
    a_launcher.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GERAPED Launcher',
)
