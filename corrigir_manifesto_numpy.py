#!/usr/bin/env python3
"""Corrige a serialização de escalares NumPy no manifesto do Vale1Km.
Execute na raiz do clone do repositório: python corrigir_manifesto_numpy.py
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import sys

ALVO = Path("scripts/plotar.py")
IMPORT_ANCHOR = "import numpy as np\n"
HELPER = '''import numpy as np


def _json_default(obj):
    """Converte tipos NumPy para tipos nativos aceitos pelo JSON do navegador."""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Tipo não serializável no manifesto: {type(obj).__name__}")
'''
OLD_DUMP = '    json.dump(manifesto, open(os.path.join(args.saida, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)\n'
NEW_DUMP = '''    # Grava o manifesto de forma atômica. A geometria derivada dos arrays do WRF
    # pode conter escalares numpy.float32, não aceitos pelo encoder JSON padrão.
    caminho_manifesto = os.path.join(args.saida, "manifest.json")
    temporario = caminho_manifesto + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1, default=_json_default, allow_nan=False)
    os.replace(temporario, caminho_manifesto)
'''


def main() -> int:
    if not ALVO.is_file():
        print(f"ERRO: não encontrei {ALVO}. Execute este script na raiz do repositório vale1km.", file=sys.stderr)
        return 2

    original = ALVO.read_text(encoding="utf-8")
    if "def _json_default(obj):" in original and "default=_json_default" in original:
        print("A correção já está aplicada em scripts/plotar.py. Nenhuma alteração necessária.")
        return 0

    if IMPORT_ANCHOR not in original:
        print("ERRO: não encontrei o ponto de inserção de NumPy; arquivo diferente do esperado.", file=sys.stderr)
        return 3
    if OLD_DUMP not in original:
        print("ERRO: a linha antiga de json.dump não foi encontrada. Não alterei o arquivo para evitar uma edição incorreta.", file=sys.stderr)
        return 4

    atualizado = original.replace(IMPORT_ANCHOR, HELPER, 1).replace(OLD_DUMP, NEW_DUMP, 1)
    try:
        ast.parse(atualizado, filename=str(ALVO))
    except SyntaxError as exc:
        print(f"ERRO: a correção gerou sintaxe inválida: {exc}", file=sys.stderr)
        return 5

    backup = ALVO.with_suffix(ALVO.suffix + ".bak")
    n = 1
    while backup.exists():
        backup = ALVO.with_suffix(ALVO.suffix + f".bak{n}")
        n += 1

    # Primeiro preserva a versão original; depois troca o arquivo atomicamente.
    backup.write_text(original, encoding="utf-8")
    temporario = ALVO.with_suffix(ALVO.suffix + ".tmp")
    temporario.write_text(atualizado, encoding="utf-8")
    os.replace(temporario, ALVO)

    print("Correção aplicada com sucesso.")
    print(f"Arquivo corrigido: {ALVO}")
    print(f"Backup original:   {backup}")
    print("Ajuste: o manifesto agora converte np.float32/np.int64/arrays NumPy e é gravado atomicamente.")
    print("Próximo passo: revise com git diff e envie um commit ao GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
