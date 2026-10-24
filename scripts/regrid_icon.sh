#!/usr/bin/env bash
# Vale1Km, etapa 1: passa o ICON da grade triangular para lat/lon (0,125°) e recorta o Sul/Sudeste.
# O DWD publica o ICON com compressão CCSDS, que o ecCodes da imagem Docker do DWD não lê.
# Por isso usamos o CDO do Ubuntu (ecCodes novo, com AEC) e só aproveitamos da imagem
# do DWD os arquivos de pesos de interpolação do ICON Global.
set -euo pipefail

echo "$(date -u +%T) apt update"
sudo timeout 300 apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 update -qq \
  || echo "apt update falhou ou demorou demais; tentando instalar mesmo assim"
echo "$(date -u +%T) instalando o CDO"
sudo timeout 900 apt-get install -y -qq cdo > /dev/null
cdo -V 2>&1 | head -1 || true

echo "$(date -u +%T) pesos de interpolação do ICON (imagem do DWD)"
id=$(docker create deutscherwetterdienst/regrid:icon /bin/true)
docker cp "$id:/data/weights/icon/icon_weights.nc" dados/icon_weights.nc
docker cp "$id:/data/descriptions/icon/icon_description.txt" dados/icon_description.txt
docker rm "$id" > /dev/null

mkdir -p dados/icon_reg
cat > dados/_um.sh <<'INNER'
#!/usr/bin/env bash
set -e
f="$1"; b=$(basename "$f" .grib2).nc
cdo -s -f nc sellonlatbox,-58,-40,-34,-19 \
  -remap,dados/icon_description.txt,dados/icon_weights.nc \
  "$f" "dados/icon_reg/$b"
INNER

arquivos=(dados/icon_raw/*.grib2)
echo "$(date -u +%T) ${#arquivos[@]} arquivos para converter"

# testa em um arquivo antes de rodar todos, para falhar cedo e com log curto
primeiro="${arquivos[0]}"
echo "Teste com $(basename "$primeiro")"
bash dados/_um.sh "$primeiro"
cdo -s griddes "dados/icon_reg/$(basename "$primeiro" .grib2).nc" > dados/_grade.txt
head -12 dados/_grade.txt
echo "Teste ok, convertendo os demais..."

printf '%s\n' "${arquivos[@]}" | xargs -P 4 -n 1 bash dados/_um.sh
rm -f dados/_um.sh dados/_grade.txt

saidas=(dados/icon_reg/*.nc)
echo "$(date -u +%T) Regrid: ${#saidas[@]} de ${#arquivos[@]} arquivos."
test "${#saidas[@]}" -eq "${#arquivos[@]}"
