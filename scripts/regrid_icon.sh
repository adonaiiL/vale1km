#!/usr/bin/env bash
# Vale1Km, etapa 1: passa o ICON da grade triangular para lat/lon (0,125°) e recorta o Sul/Sudeste.
# O DWD publica o ICON com compressão CCSDS, que o ecCodes da imagem Docker do DWD não lê.
# Por isso usamos o CDO do Ubuntu (ecCodes novo, com AEC). A interpolação é por média ponderada pela
# distância dos 4 pontos mais próximos (gendis), mais precisa que o vizinho mais próximo; se isso não
# funcionar, cai para os pesos de vizinho mais próximo que o DWD já publica na imagem Docker.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/apt_seguro.sh"
apt_instalar cdo
cdo -V 2>&1 | head -1 || true

mkdir -p dados/icon_reg

echo "$(date -u +%T) pesos de vizinho mais próximo (imagem do DWD, plano B)"
id=$(docker create deutscherwetterdienst/regrid:icon /bin/true)
docker cp "$id:/data/weights/icon/icon_weights.nc" dados/icon_weights.nc
docker cp "$id:/data/descriptions/icon/icon_description.txt" dados/icon_description.txt
docker rm "$id" > /dev/null

# grade regional de saída: mesmos nós da grade global de 0,125° do DWD
cat > dados/grade_regional.txt <<'GRADE'
gridtype = lonlat
xsize    = 145
ysize    = 121
xfirst   = -58
xinc     = 0.125
yfirst   = -34
yinc     = 0.125
GRADE

MODO=nn
echo "$(date -u +%T) tentando pesos por distância ponderada (gendis)"
if id2=$(docker create deutscherwetterdienst/regrid:icon-grids /bin/true 2> /dev/null); then
  if docker cp "$id2:/data/grids/icon/icon_grid.nc" dados/icon_grid.nc 2> /dev/null \
     && timeout 900 cdo -s gendis,dados/grade_regional.txt dados/icon_grid.nc dados/pesos_dis.nc 2> dados/gendis.log; then
    MODO=dis
  else
    echo "  gendis não funcionou; seguindo com vizinho mais próximo. Final do log: $(tail -2 dados/gendis.log 2> /dev/null | tr '\n' ' ')"
  fi
  docker rm "$id2" > /dev/null 2>&1 || true
else
  echo "  imagem icon-grids indisponível; seguindo com vizinho mais próximo"
fi

escrever_um() {  # $1 = dis | nn
  if [ "$1" = dis ]; then
    cat > dados/_um.sh <<'INNER'
#!/usr/bin/env bash
set -e
f="$1"; b=$(basename "$f" .grib2).nc
cdo -s -f nc remap,dados/grade_regional.txt,dados/pesos_dis.nc "$f" "dados/icon_reg/$b"
INNER
  else
    cat > dados/_um.sh <<'INNER'
#!/usr/bin/env bash
set -e
f="$1"; b=$(basename "$f" .grib2).nc
cdo -s -f nc sellonlatbox,-58,-40,-34,-19 \
  -remap,dados/icon_description.txt,dados/icon_weights.nc \
  "$f" "dados/icon_reg/$b"
INNER
  fi
}

arquivos=(dados/icon_raw/*.grib2)
echo "$(date -u +%T) ${#arquivos[@]} arquivos para converter"
primeiro="${arquivos[0]}"
saida1="dados/icon_reg/$(basename "$primeiro" .grib2).nc"

# testa em um arquivo antes de rodar todos; se o método novo der erro ou valores inválidos, volta ao plano B
valido() {
  local v
  v=$(cdo -s output -fldmean "$saida1" 2> /dev/null | sed -n 1p | tr -d ' ')
  [ -n "$v" ] && [[ "$v" != *nan* ]] && [[ "$v" != *inf* ]]
}
if [ "$MODO" = dis ]; then
  escrever_um dis
  if bash dados/_um.sh "$primeiro" && valido; then
    echo "Regrid por distância ponderada: ok no teste"
  else
    echo "Regrid por distância ponderada falhou no teste; voltando ao vizinho mais próximo"
    MODO=nn
  fi
fi
if [ "$MODO" = nn ]; then
  escrever_um nn
  echo "Teste com $(basename "$primeiro") (vizinho mais próximo)"
  bash dados/_um.sh "$primeiro"
fi
echo "método de interpolação: $MODO"
cdo -s griddes "$saida1" > dados/_grade.txt
head -12 dados/_grade.txt
echo "Teste ok, convertendo os demais..."

printf '%s\n' "${arquivos[@]}" | xargs -P 4 -n 1 bash dados/_um.sh
rm -f dados/_um.sh dados/_grade.txt

saidas=(dados/icon_reg/*.nc)
echo "$(date -u +%T) Regrid: ${#saidas[@]} de ${#arquivos[@]} arquivos (método: $MODO)."
test "${#saidas[@]}" -eq "${#arquivos[@]}"
