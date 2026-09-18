# -*- coding: utf-8 -*-
"""Gera o arquivo de checksum (SHA256) do pacote de release do GERAPED.

Uso:
    python gerar_checksum.py caminho/para/GERAPED-app.zip

Gera "GERAPED-app.zip.sha256" ao lado do .zip (texto simples com o hex do
hash). Suba os dois arquivos juntos como assets da release no GitHub —
o launcher usa esse segundo arquivo para confirmar que o download não
foi corrompido antes de aplicar a atualização (ver verificar_checksum()
em launcher.py). Sem ele, a release ainda funciona, só sem essa
verificação extra.
"""
import hashlib
import sys
from pathlib import Path

CHUNK_SIZE = 65536


def main():
    if len(sys.argv) != 2:
        print("Uso: python gerar_checksum.py caminho/para/GERAPED-app.zip")
        sys.exit(1)

    zip_path = Path(sys.argv[1])
    if not zip_path.is_file():
        print(f"Arquivo não encontrado: {zip_path}")
        sys.exit(1)

    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for bloco in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(bloco)

    checksum_path = zip_path.with_name(zip_path.name + ".sha256")
    checksum_path.write_text(h.hexdigest() + "\n", encoding="utf-8")
    print(f"{checksum_path.name}: {h.hexdigest()}")


if __name__ == "__main__":
    main()
