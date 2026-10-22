#!/usr/bin/env bash
# Vale1Km, etapa 1: passa o ICON da grade triangular para lat/lon (0,125°) e recorta o Sul/Sudeste.
# O DWD publica o ICON com compressão CCSDS, que o ecCodes da imagem Docker do DWD não lê.
# Por isso usamos o CDO do Ubuntu (ecCodes novo, com AEC) e só aproveitamos da imagem
# do DWD os arquivos de pesos de interpolação do ICON Global.
set -euo pipefail

sudo apt-get update -qq
sudo apt-get install -y -qq cdo
cdo -V 2>&1 | head -4

id=$(docker create deutscherwetterdienst/regrid:icon /bin/true)
docker cp "$id:/data/weights/icon/icon_weights.nc" dados/icon_weights.nc
docker cp "$id:/data/descriptions/icon/icon_description.txt" dados/icon_description.txt
docker rm "$id" > /dev/null

mkdir -p dados/icon_reg
cat > dados/_um.sh <<'INNER'
#!/usr/bin/env bash
set -e
f="$1"; b=$(basename "$f")
cdo -s -f grb2 sellonlatbox,-58,-40,-34,-19 \
  -remap,dados/icon_description.txt,dados/icon_weights.nc \
  "$f" "dados/icon_reg/$b"
INNER

# testa em um arquivo antes de rodar todos, para falhar cedo e com log curto
primeiro=$(ls dados/icon_raw/*.grib2 | head -1)
echo "Teste com $(basename "$primeiro")"
bash dados/_um.sh "$primeiro"
echo "Teste ok, convertendo o resto..."

ls dados/icon_raw/*.grib2 | xargs -P 4 -n 1 bash dados/_um.sh
rm -f dados/_um.sh

entrada=$(ls dados/icon_raw/*.grib2 | wc -l)
saida=$(ls dados/icon_reg/*.grib2 | wc -l)
echo "Regrid: $saida de $entrada arquivos."
test "$entrada" -eq "$saida"
