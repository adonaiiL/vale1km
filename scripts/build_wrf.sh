#!/usr/bin/env bash
# Vale1Km: compila WRF 4.7.1 (dmpar) e WPS 4.6.0 (geogrid e metgrid) e junta o necessário em wrf_install/.
# Roda só quando o cache não existe. Leva de 30 a 60 minutos.
set -Eeuo pipefail
trap 'echo "ERRO (código $?) na linha $LINENO: $BASH_COMMAND" >&2' ERR

WRF_TAG="v4.7.1"
WPS_TAG="v4.6.0"
RAIZ="$PWD"
DEST="$RAIZ/wrf_install"
CONSTR="$RAIZ/wrf_build"

echo "$(date -u +%T) instalando dependências"
sudo timeout 300 apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 update -qq || true
sudo apt-get install -y -qq build-essential csh m4 gfortran mpich libmpich-dev \
  libnetcdf-dev libnetcdff-dev libpng-dev zlib1g-dev > /dev/null

# O NETCDF do WRF espera include/ e lib/ no mesmo prefixo; no Ubuntu eles ficam separados.
export NETCDF="$RAIZ/netcdf_stage"
rm -rf "$NETCDF"; mkdir -p "$NETCDF/include" "$NETCDF/lib"
find /usr/include -maxdepth 3 \( -name 'netcdf*.h' -o -name 'netcdf*.inc' -o -name 'netcdf*.mod' -o -name 'typesizes.mod' \) \
  -exec ln -sf {} "$NETCDF/include/" \;
for f in /usr/lib/x86_64-linux-gnu/libnetcdf*; do ln -sf "$f" "$NETCDF/lib/"; done
ls "$NETCDF/include" | head -20
ls "$NETCDF/lib" | head -20
test -e "$NETCDF/include/netcdf.inc" || { echo "ERRO: netcdf.inc não encontrado"; exit 1; }

export WRF_EM_CORE=1
export FC=gfortran CC=gcc
mkdir -p "$CONSTR"; cd "$CONSTR"

if [ -f WRF/configure.wrf ] && [ -d WPS ]; then
  echo "$(date -u +%T) retomando a partir da árvore de compilação em cache"
  cd WRF
else
  rm -rf WRF WPS
  echo "$(date -u +%T) baixando WRF $WRF_TAG (com submódulos) e WPS $WPS_TAG"
  git clone --depth 1 --branch "$WRF_TAG" --recurse-submodules --shallow-submodules https://github.com/wrf-model/WRF.git WRF
  git clone --depth 1 --branch "$WPS_TAG" https://github.com/wrf-model/WPS.git WPS

  echo "$(date -u +%T) configurando WRF"
  cd WRF
  chmod +x configure compile clean 2>/dev/null || true
  echo "ambiente: NETCDF=$NETCDF | perl=$(command -v perl || echo AUSENTE) | csh=$(command -v csh || echo AUSENTE) | $(gfortran --version | sed -n 1p) | $(command -v mpif90 || echo mpif90-AUSENTE)"
  # 1a chamada: só para listar as opções. O configure repete o menu sem parar com respostas inválidas, então o limite é curto.
  set +e
  printf '0\n0\n0\n' | timeout 15 ./configure > configure_menu.log 2>&1
  set -e
  opt=$(awk '/GNU \(gfortran\/gcc\)/ { if (match($0, /[0-9]+\. \(dmpar\)/)) { s = substr($0, RSTART, RLENGTH); sub(/\..*/, "", s); print s; exit } }' configure_menu.log)
  if [ -z "$opt" ]; then echo "ERRO: não achei a opção gfortran dmpar no menu do configure:"; sed -n '1,60p' configure_menu.log; exit 1; fi
  echo "opção gfortran dmpar = $opt"
  printf '%s\n1\n' "$opt" | timeout 300 ./configure > configure.log 2>&1 || { tail -60 configure.log; exit 1; }
  test -f configure.wrf || { echo "ERRO: configure.wrf não foi criado"; tail -60 configure.log; exit 1; }
  grep -E '^(DM_FC|DM_CC|SFC|SCC|FCOPTIM|NETCDFPATH)' configure.wrf | head -12 || true
  grep -n -i -E 'lnetcdf|LIB_EXTERNAL' configure.wrf | head -12 || true
fi

echo "$(date -u +%T) compilando WRF (em_real); pode levar de 30 a 60 minutos"
( while sleep 300; do echo "$(date -u +%T) compilando... ($(wc -l < compile.log 2>/dev/null; true) linhas de log)"; done ) &
HB=$!
./compile -j "$(nproc)" em_real > compile.log 2>&1 || true
if [ ! -x main/wrf.exe ] || [ ! -x main/real.exe ]; then
  # com -j, a ligação dos executáveis às vezes roda antes das bibliotecas ficarem prontas: repete em série
  echo "$(date -u +%T) executáveis ausentes; repetindo ./compile em série (só refaz a ligação)"
  ./compile em_real > compile2.log 2>&1 || true
fi
kill "$HB" 2>/dev/null || true
if [ ! -x main/wrf.exe ] || [ ! -x main/real.exe ]; then
  echo "ERRO: a compilação do WRF falhou, mesmo na segunda passada."
  echo "--- referências indefinidas (mais frequentes):"
  grep -h -o "undefined reference to .*" compile2.log compile.log | sort | uniq -c | sort -rn | head -30 || true
  echo "--- contexto do primeiro erro de ligação:"
  grep -n -m 1 -B 25 "collect2: error" compile2.log || grep -n -m 1 -B 25 "collect2: error" compile.log || true
  echo "--- outros erros:"
  grep -h -n -E "Error [0-9]|error:|cannot find|multiple definition" compile2.log | head -30 || true
  echo "--- final do log:"; tail -40 compile2.log
  exit 1
fi
echo "$(date -u +%T) WRF compilado"

echo "$(date -u +%T) configurando WPS"
cd ../WPS
chmod +x configure compile clean 2>/dev/null || true
if [ ! -f configure.wps ]; then
  set +e
  printf '0\n0\n' | timeout 15 ./configure > configure_menu.log 2>&1
  set -e
  opt=$(awk '/gfortran +\(serial_NO_GRIB2\)/ { sub(/\..*/, "", $1); print $1; exit }' configure_menu.log)
  if [ -z "$opt" ]; then echo "ERRO: não achei gfortran serial_NO_GRIB2 no menu do WPS:"; sed -n '1,40p' configure_menu.log; exit 1; fi
  echo "opção WPS = $opt"
  printf '%s\n' "$opt" | timeout 300 ./configure > configure.log 2>&1 || { tail -40 configure.log; exit 1; }
fi
./compile > compile.log 2>&1 || true
if [ ! -e geogrid.exe ] || [ ! -e metgrid.exe ]; then
  echo "ERRO: a compilação do WPS falhou."
  grep -h -o "undefined reference to .*" compile.log | sort | uniq -c | sort -rn | head -20 || true
  grep -n -m 1 -B 20 "collect2: error" compile.log || true
  grep -n -m 25 -E "Error|error:|Fatal" compile.log || true
  echo "Últimas linhas do log:"; tail -60 compile.log; exit 1
fi
echo "$(date -u +%T) WPS compilado"

echo "$(date -u +%T) juntando em $DEST"
cd "$RAIZ"
rm -rf "$DEST"; mkdir -p "$DEST/WRF" "$DEST/WPS/geogrid" "$DEST/WPS/metgrid"
cp -rL "$CONSTR/WRF/run" "$DEST/WRF/run"
rm -f "$DEST/WRF/run/ndown.exe" "$DEST/WRF/run/tc.exe" "$DEST/WRF/run/namelist.input"
cp -L "$CONSTR/WPS/geogrid.exe" "$CONSTR/WPS/metgrid.exe" "$DEST/WPS/"
cp "$CONSTR/WPS/geogrid/GEOGRID.TBL.ARW" "$DEST/WPS/geogrid/GEOGRID.TBL"
cp "$CONSTR/WPS/metgrid/METGRID.TBL.ARW" "$DEST/WPS/metgrid/METGRID.TBL"
du -sh "$DEST"
rm -rf "$CONSTR" "$NETCDF"
echo "$(date -u +%T) pronto"
