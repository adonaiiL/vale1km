#!/usr/bin/env python3
"""Vale1Km: monta um WPS_GEOG enxuto, só com a região de interesse.

Faz streaming do geog_high_res_mandatory.tar.gz (UCAR) sem gravá-lo em disco. Dos datasets de
30" (topografia, uso do solo e tipo de solo) guarda só os blocos que cobrem a região; dos demais
guarda tudo. O resultado (algumas centenas de MB) vai para o cache do GitHub Actions.
"""
import io
import os
import re
import sys
import tarfile
import time
import urllib.request

URL = "https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz"
SAIDA = sys.argv[1] if len(sys.argv) > 1 else "geog_mini"

# Região: d01 tem ~355 km em volta de (-26,83; -49,12). Margem generosa.
LON = (-53.5, -44.5)
LAT = (-31.5, -22.0)
TILE = 1200
RES = 120  # pontos por grau nos datasets de 30"
GRANDES = ("topo_gmted2010_30s", "modis_landuse_20class_30s", "soiltype_top_30s", "soiltype_bot_30s")
NOME_TILE = re.compile(r"^(\d{5})-(\d{5})\.(\d{5})-(\d{5})$")


def blocos(minv, maxv, offset):
    i0 = int((minv + offset) * RES) + 1
    i1 = int((maxv + offset) * RES) + 1
    ini = ((i0 - 1) // TILE) * TILE + 1
    fim = ((i1 - 1) // TILE) * TILE + 1
    return set(range(ini, fim + 1, TILE))


X0 = blocos(LON[0], LON[1], 180.0)
Y0 = blocos(LAT[0], LAT[1], 90.0)


def quer(dataset, nome):
    """Decide se o arquivo do tar deve ser guardado."""
    if any(dataset.startswith(g) for g in GRANDES):
        m = NOME_TILE.match(nome)
        if not m:
            return True  # index e afins
        return int(m.group(1)) in X0 and int(m.group(3)) in Y0
    return True


class FluxoRetomavel(io.RawIOBase):
    """Leitura HTTP que reconecta (com Range) se a conexão cair no meio de 15 GB."""

    def __init__(self, url):
        self.url, self.pos, self.resp = url, 0, None
        self.total = None

    def readable(self):
        return True

    def _abrir(self):
        req = urllib.request.Request(self.url, headers={"User-Agent": "vale1km"})
        if self.pos:
            req.add_header("Range", f"bytes={self.pos}-")
        self.resp = urllib.request.urlopen(req, timeout=120)
        if self.pos and self.resp.status != 206:
            raise IOError("o servidor não aceita retomar o download")
        if self.total is None:
            self.total = int(self.resp.headers.get("Content-Length", 0)) or None

    def readinto(self, b):
        for tentativa in range(8):
            try:
                if self.resp is None:
                    self._abrir()
                dados = self.resp.read(len(b))
                b[:len(dados)] = dados
                self.pos += len(dados)
                return len(dados)
            except Exception as e:
                print(f"  conexão interrompida em {self.pos / 1e9:.2f} GB ({e}); tentando de novo", flush=True)
                self.resp = None
                time.sleep(2 ** min(tentativa, 5))
        raise IOError("download interrompido várias vezes")


def main():
    os.makedirs(SAIDA, exist_ok=True)
    print(f"Blocos de 30\" que vamos guardar: x={sorted(X0)} y={sorted(Y0)}", flush=True)
    fluxo = io.BufferedReader(FluxoRetomavel(URL), buffer_size=8 * 1024 * 1024)
    guardados, ignorados, bytes_ok, ultimo = {}, 0, 0, time.time()
    with tarfile.open(fileobj=fluxo, mode="r|gz") as tar:
        for m in tar:
            if not m.isfile():
                continue
            partes = [p for p in m.name.split("/") if p not in ("", ".")]
            if len(partes) < 2:
                continue
            dataset, nome = partes[-2], partes[-1]
            if not quer(dataset, nome):
                ignorados += 1
                continue
            destino = os.path.join(SAIDA, dataset)
            os.makedirs(destino, exist_ok=True)
            with open(os.path.join(destino, nome), "wb") as f:
                f.write(tar.extractfile(m).read())
            guardados[dataset] = guardados.get(dataset, 0) + 1
            bytes_ok += m.size
            if time.time() - ultimo > 60:
                print(f"  lidos {fluxo.raw.pos / 1e9:.1f} GB, guardados {bytes_ok / 1e6:.0f} MB", flush=True)
                ultimo = time.time()
    print("\nDatasets guardados (arquivos):")
    for d in sorted(guardados):
        print(f"  {d:45s} {guardados[d]}")
    print(f"Ignorados: {ignorados} arquivos fora da região; guardados {bytes_ok / 1e6:.0f} MB")
    essenciais = ["topo_gmted2010_30s", "soiltemp_1deg"]
    faltam = [d for d in essenciais if d not in guardados]
    uso = [d for d in guardados if d.startswith("modis_landuse")]
    if faltam or not uso:
        sys.exit(f"ERRO: faltam datasets essenciais: {faltam or ''} {'' if uso else 'uso do solo'}")
    # dentro de cada dataset grande tem que ter ao menos um bloco
    for g in GRANDES:
        achou = [d for d in guardados if d.startswith(g)]
        if achou and guardados[achou[0]] < 2:
            sys.exit(f"ERRO: nenhum bloco de {g} cobre a região")
    open(os.path.join(SAIDA, ".ok"), "w").write("ok\n")


if __name__ == "__main__":
    main()
