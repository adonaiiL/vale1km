#!/usr/bin/env bash
# Aplica uma correção segura à falha HTTP 503 ao baixar os pacotes MPICH.
# Execute na raiz do clone do repositório vale1km.
set -Eeuo pipefail

ARQ="scripts/rodar_wrf.sh"
if [[ ! -f "$ARQ" ]]; then
  echo "ERRO: não encontrei $ARQ. Execute este script na raiz do repositório vale1km." >&2
  exit 1
fi

python3 - "$ARQ" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = '''  for d in libmpich12_4.2.0-5.1_amd64.deb libmpich-dev_4.2.0-5.1_amd64.deb mpich_4.2.0-5.1_amd64.deb; do
    curl -fsSL -L -o "/tmp/mpich-fix/$d" "$base/$d"
  done
'''
new = '''  for d in libmpich12_4.2.0-5.1_amd64.deb libmpich-dev_4.2.0-5.1_amd64.deb mpich_4.2.0-5.1_amd64.deb; do
    destino="/tmp/mpich-fix/$d"
    baixado=0

    # O Launchpad pode responder HTTP 503. Repetimos com timeout e validamos
    # o pacote antes de prosseguir; um download incompleto nunca é instalado.
    for tentativa in 1 2 3 4 5; do
      echo "$(date -u +%T) MPICH: baixando $d (tentativa $tentativa/5)"
      rm -f "$destino.tmp"
      if curl --fail --location --silent --show-error \\
          --connect-timeout 20 --max-time 90 \\
          -o "$destino.tmp" "$base/$d" \\
          && dpkg-deb --info "$destino.tmp" >/dev/null 2>&1 \\
          && [ "$(dpkg-deb -f "$destino.tmp" Version 2>/dev/null)" = "4.2.0-5.1" ] \\
          && [ "$(dpkg-deb -f "$destino.tmp" Architecture 2>/dev/null)" = "amd64" ]; then
        mv "$destino.tmp" "$destino"
        baixado=1
        break
      fi
      rm -f "$destino.tmp"
      if [ "$tentativa" -lt 5 ]; then
        echo "Aviso: download falhou ou pacote inválido; nova tentativa em 8 segundos." >&2
        sleep 8
      fi
    done

    if [ "$baixado" -ne 1 ]; then
      echo "ERRO: não foi possível baixar um pacote MPICH válido após 5 tentativas: $d" >&2
      echo "O Launchpad pode estar temporariamente indisponível (HTTP 503)." >&2
      exit 1
    fi
  done
'''
if text.count(old) != 1:
    print("ERRO: o bloco original não foi encontrado exatamente uma vez; nenhum arquivo foi alterado.", file=sys.stderr)
    sys.exit(2)
backup = path.with_suffix(path.suffix + ".bak")
if backup.exists():
    print(f"ERRO: backup já existe ({backup}); nenhum arquivo foi alterado para não sobrescrever uma cópia.", file=sys.stderr)
    sys.exit(3)
backup.write_text(text, encoding="utf-8")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print(f"Correção aplicada em {path}; cópia original salva em {backup}.")
PY

bash -n "$ARQ"
echo "Validação bash -n: OK"
echo
echo "Resumo da alteração:"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff -- "$ARQ" || true
else
  echo "O diretório não é um clone Git; a alteração foi aplicada e validada localmente."
fi
echo
echo "Próximo passo: revisar a alteração e enviar o commit para o GitHub."
