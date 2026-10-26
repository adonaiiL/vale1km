#!/usr/bin/env bash
# Vale1Km: geogrid, conversão do ICON, metgrid, real e wrf. Uso: rodar_wrf.sh AAAA-MM-DDTHH  (fim da janela, UTC)
set -Eeuo pipefail
trap 'echo "ERRO (código $?) na linha $LINENO: $BASH_COMMAND" >&2' ERR

FIM="$1"
RAIZ="$PWD"
INST="$RAIZ/wrf_install"
GEOG="$RAIZ/geog_mini"
RUN="$RAIZ/run_wrf"
NP="${NP:-$(nproc)}"
ulimit -s unlimited || true

relogio() { echo "$(date -u +%T) $*"; }
falhou() { echo "ERRO: $1"; shift; for f in "$@"; do [ -f "$f" ] && { echo "--- $f (final)"; tail -60 "$f"; }; done; exit 1; }

relogio "bibliotecas de execução"
sudo timeout 300 apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 update -qq || true
sudo apt-get install -y -qq mpich libnetcdff-dev > /dev/null

rm -rf "$RUN"; mkdir -p "$RUN/wps" "$RUN/wrf"
cp -r "$INST/WPS/." "$RUN/wps/"
cp -a "$INST/WRF/run/." "$RUN/wrf/"
export PYTHONPATH="$RAIZ/scripts"

relogio "geogrid (domínios de 5 km e 1 km)"
python scripts/gerar_namelists.py wps --manifesto dados/manifesto.json --fim "$FIM" --geog "$GEOG" --saida "$RUN/wps/namelist.wps"
cd "$RUN/wps"
./geogrid.exe > geogrid.log 2>&1 || true
grep -q "Successful completion of geogrid" geogrid.log || falhou "geogrid não terminou" geogrid.log
ls geo_em.d01.nc geo_em.d02.nc > /dev/null

relogio "convertendo o ICON para o formato do WPS"
cd "$RAIZ"
python scripts/icon2wps.py --entrada dados/icon_reg --manifesto dados/manifesto.json --saida "$RUN/wps"

relogio "metgrid"
cd "$RUN/wps"
./metgrid.exe > metgrid.log 2>&1 || true
grep -q "Successful completion of metgrid" metgrid.log || falhou "metgrid não terminou" metgrid.log
ls met_em.d01.*.nc met_em.d02.*.nc > /dev/null
arq=(met_em.d01.*.nc)
primeiro="${arq[0]}"
NIVEIS=$(python - "$primeiro" <<'PY'
import sys, netCDF4
print(netCDF4.Dataset(sys.argv[1]).dimensions["num_metgrid_levels"].size)
PY
)
echo "níveis do met_em: $NIVEIS"

relogio "real.exe"
cd "$RAIZ"
python scripts/gerar_namelists.py input --manifesto dados/manifesto.json --fim "$FIM" --niveis "$NIVEIS" --saida "$RUN/wrf/namelist.input"
ln -sf "$RUN"/wps/met_em.d0*.nc "$RUN/wrf/"
cd "$RUN/wrf"

# O MPICH do Ubuntu tenta InfiniBand via UCX e quebra nas máquinas do GitHub
# ("ibv_create_srq() failed"). Testamos configurações até o MPI inicializar.
MPI_ENV=""
for cfg in "UCX_TLS=sm,tcp,self" "MPIR_CVAR_CH4_NETMOD=ofi FI_PROVIDER=tcp" "MPIR_CVAR_CH4_NETMOD=ofi FI_PROVIDER=sockets"; do
  rm -f rsl.error.* rsl.out.* real.log
  echo "MPI: tentando $cfg"
  env $cfg mpirun -np 1 ./real.exe > real.log 2>&1 || true
  if grep -q "SUCCESS COMPLETE REAL_EM INIT" rsl.error.0000 2>/dev/null; then MPI_ENV="$cfg"; break; fi
  if grep -q -E "MPI_Init|UCX|internal_Init|Fatal error in" real.log; then
    echo "  o MPI não inicializou com $cfg:"; grep -m 3 -E "ERROR|Fatal|failed" real.log | cut -c1-200
    continue
  fi
  falhou "real.exe falhou (não é problema de MPI)" rsl.error.0000 real.log
done
[ -n "$MPI_ENV" ] || falhou "nenhuma configuração do MPI funcionou" real.log
echo "MPI ok com: $MPI_ENV"
ls wrfinput_d01 wrfinput_d02 wrfbdy_d01 > /dev/null

relogio "wrf.exe com $NP processos (pode levar de dezenas de minutos a algumas horas)"
( while sleep 300; do echo "$(date -u +%T) $(grep -c 'Timing for main' rsl.error.0000 2>/dev/null; true) passos; $(tail -1 rsl.error.0000 2>/dev/null | cut -c1-120)"; done ) &
MON=$!
env $MPI_ENV mpirun -np "$NP" ./wrf.exe > wrf.log 2>&1 || true
kill "$MON" 2>/dev/null || true
if ! grep -q "SUCCESS COMPLETE WRF" rsl.error.0000; then
  grep -h -i -E "cfl|segmentation|fatal|error" rsl.error.* 2>/dev/null | sort | uniq -c | sort -rn | head -15 || true
  falhou "wrf.exe falhou" rsl.error.0000 wrf.log
fi
ls wrfout_d02_* auxhist2_d02_* > /dev/null
relogio "WRF terminou"
ls -la wrfout_d02_* auxhist2_d02_*
