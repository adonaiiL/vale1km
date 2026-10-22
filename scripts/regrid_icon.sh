#!/usr/bin/env bash
# Vale1Km, etapa 1: passa o ICON da grade triangular para lat/lon (0,125°) e recorta o Sul/Sudeste.
# Usa a imagem do DWD, que já traz os pesos de interpolação do ICON Global.
set -euo pipefail

mkdir -p dados/icon_reg
cat > dados/_um.sh <<'INNER'
#!/usr/bin/env bash
set -e
f="$1"; b=$(basename "$f")
cdo -s -f grb2 sellonlatbox,-58,-40,-34,-19 \
  -remap,/data/descriptions/icon/icon_description.txt,/data/weights/icon/icon_weights.nc \
  "$f" "/dados/icon_reg/$b"
echo "ok $b"
INNER
chmod +x dados/_um.sh

docker run --rm -v "$PWD/dados:/dados" deutscherwetterdienst/regrid:icon \
  bash -c 'ls /dados/icon_raw/*.grib2 | xargs -P 4 -n 1 /dados/_um.sh'
rm -f dados/_um.sh

entrada=$(ls dados/icon_raw/*.grib2 | wc -l)
saida=$(ls dados/icon_reg/*.grib2 | wc -l)
echo "Regrid: $saida de $entrada arquivos."
test "$entrada" -eq "$saida"
