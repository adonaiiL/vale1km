#!/usr/bin/env bash
# Vale1Km: compila WRF 4.7.1 (dmpar) e WPS 4.6.0 (geogrid e metgrid) e junta o necessário em wrf_install/.
# Roda só quando o cache não existe. Leva de 30 a 60 minutos.
set -euo pipefail

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
rm -rf "$CONSTR"; mkdir -p "$CONSTR"; cd "$CONSTR"

echo "$(date -u +%T) baixando WRF $WRF_TAG (com submódulos) e WPS $WPS_TAG"
git clone --depth 1 --branch "$WRF_TAG" --recurse-submodules --shallow-submodules https://github.com/wrf-model/WRF.git WRF
git clone --depth 1 --branch "$WPS_TAG" https://github.com/wrf-model/WPS.git WPS

echo "$(date -u +%T) configurando WRF"
cd WRF
menu=$(printf '0\n' | ./configure 2>&1 || true)
opt=$(printf '%s\n' "$menu" | grep -E 'GNU \(gfortran/gcc\)' | head -1 | grep -oE '[0-9]+\. \(dmpar\)' | grep -oE '^[0-9]+' || true)
if [ -z "$opt" ]; then echo "ERRO: não achei a opção gfortran dmpar no menu do configure:"; printf '%s\n' "$menu" | tail -40; exit 1; fi
echo "opção gfortran dmpar = $opt"
printf '%s\n1\n' "$opt" | ./configure > configure.log 2>&1 || { tail -40 configure.log; exit 1; }

echo "$(date -u +%T) compilando WRF (em_real); pode levar de 30 a 60 minutos"
./compile -j "$(nproc)" em_real > compile.log 2>&1 || true
if [ ! -x main/wrf.exe ] || [ ! -x main/real.exe ]; then
  echo "ERRO: a compilação do WRF falhou. Últimas linhas do log:"; tail -120 compile.log; exit 1
fi
echo "$(date -u +%T) WRF compilado"

echo "$(date -u +%T) configurando WPS"
cd ../WPS
menu=$(printf '0\n' | ./configure 2>&1 || true)
opt=$(printf '%s\n' "$menu" | grep -E 'gfortran +\(serial_NO_GRIB2\)' | head -1 | awk '{print $1}' | tr -d '.' || true)
if [ -z "$opt" ]; then echo "ERRO: não achei gfortran serial_NO_GRIB2 no menu do WPS:"; printf '%s\n' "$menu" | tail -30; exit 1; fi
echo "opção WPS = $opt"
printf '%s\n' "$opt" | ./configure > configure.log 2>&1 || { tail -40 configure.log; exit 1; }
./compile > compile.log 2>&1 || true
if [ ! -e geogrid.exe ] || [ ! -e metgrid.exe ]; then
  echo "ERRO: a compilação do WPS falhou. Últimas linhas do log:"; tail -80 compile.log; exit 1
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
