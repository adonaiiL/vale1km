#!/usr/bin/env python3
"""Vale1Km: monta um WPS_GEOG enxuto, só com a região de interesse.

Faz streaming do geog_high_res_mandatory.tar.gz (UCAR) sem gravá-lo em disco, em duas passadas:
  1. lê só os arquivos 'index' de cada dataset (geometria da grade);
  2. grava só os datasets que o GEOGRID.TBL pede e, nos datasets em blocos (tiles), só os blocos
     que cobrem a região. O resultado vai para o cache do GitHub Actions.
Uso: prep_geog.py PASTA_SAIDA [GEOGRID.TBL]
"""
import io
import json
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
NOME_TILE = re.compile(r"^(\d+)-(\d+)\.(\d+)-(\d+)")  # aceita sufixos (ex.: parte z)
LIMITE_GB = 10


class FluxoRetomavel(io.RawIOBase):
    """Leitura HTTP que reconecta (com Range) se a conexão cair no meio do download."""

    def __init__(self, url):
        self.url, self.pos, self.resp = url, 0, None

    def readable(self):
        return True

    def _abrir(self):
        req = urllib.request.Request(self.url, headers={"User-Agent": "vale1km"})
        if self.pos:
            req.add_header("Range", f"bytes={self.pos}-")
        self.resp = urllib.request.urlopen(req, timeout=120)
        if self.pos and self.resp.status != 206:
            raise IOError("o servidor não aceita retomar o download")

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


def datasets_pedidos(tbl):
    """Nomes (pasta de topo) dos conjuntos 'default:' do GEOGRID.TBL. Vazio se não houver tabela."""
    if not tbl or not os.path.exists(tbl):
        return set()
    out = set()
    for linha in open(tbl, encoding="utf-8", errors="replace"):
        if "rel_path" in linha and not linha.lstrip().startswith("#"):
            out.update(c.split("/")[0] for c in re.findall(r"default:([A-Za-z0-9_./-]+)", linha))
    return out


def iterar(callback):
    """Percorre o tar em streaming e chama callback(tar, membro, rel) para cada arquivo útil."""
    fluxo = io.BufferedReader(FluxoRetomavel(URL), buffer_size=8 * 1024 * 1024)
    raiz, ultimo = None, time.time()
    with tarfile.open(fileobj=fluxo, mode="r|gz") as tar:
        for m in tar:
            if not m.isfile():
                continue
            partes = [p for p in m.name.split("/") if p not in ("", ".")]
            # lixo de macOS dentro do tar (AppleDouble "._nome", __MACOSX, .DS_Store)
            if not partes or any(p.startswith("._") or p in ("__MACOSX", ".DS_Store") for p in partes):
                continue
            if raiz is None:  # pasta de topo do tar (ex.: WPS_GEOG)
                raiz = partes[0] if "geog" in partes[0].lower() else ""
                print(f"Pasta de topo do tar: '{raiz}'", flush=True)
            rel = partes[1:] if raiz and partes[0] == raiz else partes
            if len(rel) < 2:
                continue
            callback(tar, m, rel)
            if time.time() - ultimo > 60:
                print(f"  lidos {fluxo.raw.pos / 1e9:.1f} GB", flush=True)
                ultimo = time.time()


def ler_index(texto):
    d = {}
    for linha in texto.splitlines():
        if "=" in linha:
            k, v = linha.split("=", 1)
            d[k.strip()] = v.strip().strip('"')
    return d


def bloco_na_regiao(idx, nome):
    """True se o bloco 'xxxxx-xxxxx.yyyyy-yyyyy' toca a região. Sem geometria conhecida, guarda."""
    m = NOME_TILE.match(nome)
    if not m or not idx or idx.get("projection") != "regular_ll":
        return True
    try:
        x0, x1, y0, y1 = (int(g) for g in m.groups())
        dx, dy = abs(float(idx["dx"])), abs(float(idx["dy"]))
        klat, klon = float(idx["known_lat"]), float(idx["known_lon"])
        kx, ky = float(idx.get("known_x", 1)), float(idx.get("known_y", 1))  # no index vem "1.0"
    except (KeyError, ValueError):
        return True
    lon0, lon1 = klon + (x0 - kx - 0.5) * dx, klon + (x1 - kx + 0.5) * dx
    lat0, lat1 = klat + (y0 - ky - 0.5) * dy, klat + (y1 - ky + 0.5) * dy
    if lat1 < LAT[0] or lat0 > LAT[1]:
        return False
    return any(not (lon1 < LON[0] + d or lon0 > LON[1] + d) for d in (0.0, -360.0, 360.0))


def validar(saida, tbl):
    """Confere se cada rel_path 'default:' do GEOGRID.TBL tem um arquivo index. Só avisa; não derruba."""
    if not tbl or not os.path.exists(tbl):
        return []
    caminhos = set()
    for linha in open(tbl, encoding="utf-8", errors="replace"):
        if "rel_path" in linha and not linha.lstrip().startswith("#"):
            caminhos.update(re.findall(r"default:([A-Za-z0-9_./-]+)", linha))
    faltam = sorted(c for c in caminhos if not os.path.isfile(os.path.join(saida, c.rstrip("/"), "index")))
    print(f"GEOGRID.TBL pede {len(caminhos)} conjuntos 'default'; faltam {len(faltam)}")
    for c in faltam:
        print(f"  FALTA: {c}")
    return faltam


def main():
    print("prep_geog.py versão 5 (duas passadas; aceita known_x 1.0)", flush=True)
    os.makedirs(SAIDA, exist_ok=True)
    tbl = sys.argv[2] if len(sys.argv) > 2 else None
    pedidos = datasets_pedidos(tbl)
    print(f"Datasets pedidos pelo GEOGRID.TBL ({len(pedidos)}): {sorted(pedidos)}" if pedidos
          else "Sem GEOGRID.TBL: guardando todos os datasets", flush=True)
    util = lambda rel: (not pedidos) or rel[0] in pedidos

    # ---- passada 1: geometria de cada dataset
    indices = {}

    def p1(tar, m, rel):
        if rel[-1] == "index" and util(rel):
            indices["/".join(rel[:-1])] = ler_index(tar.extractfile(m).read().decode("utf-8", "replace"))

    print("Passada 1: lendo os arquivos 'index'", flush=True)
    iterar(p1)
    regulares = sum(1 for v in indices.values() if v.get("projection") == "regular_ll")
    print(f"  {len(indices)} datasets com index ({regulares} em grade lat/lon regular)")
    json.dump(indices, open(os.path.join(SAIDA, "_indices.json"), "w"), indent=1)

    # ---- passada 2: gravação
    guardados, ignorados, bytes_ok = {}, 0, [0]

    def p2(tar, m, rel):
        nonlocal ignorados
        if not util(rel):
            return
        dir_rel = "/".join(rel[:-1])
        if not bloco_na_regiao(indices.get(dir_rel), rel[-1]):
            ignorados += 1
            return
        destino = os.path.join(SAIDA, *rel[:-1])
        os.makedirs(destino, exist_ok=True)
        with open(os.path.join(destino, rel[-1]), "wb") as f:
            f.write(tar.extractfile(m).read())
        guardados[rel[0]] = guardados.get(rel[0], 0) + 1
        bytes_ok[0] += m.size
        if bytes_ok[0] > LIMITE_GB * 1e9:
            sys.exit(f"ERRO: já guardei {bytes_ok[0] / 1e9:.0f} GB, bem mais que o esperado. "
                     f"Último arquivo: {dir_rel}/{rel[-1]}; geometria: {indices.get(dir_rel)}")

    print("Passada 2: gravando só o que cobre a região", flush=True)
    iterar(p2)
    print("\nDatasets guardados (arquivos):")
    for d in sorted(guardados):
        print(f"  {d:45s} {guardados[d]}")
    print(f"Ignorados: {ignorados} blocos fora da região; guardados {bytes_ok[0] / 1e6:.0f} MB")
    essenciais = ["topo_gmted2010_30s", "soiltemp_1deg"]
    faltam = [d for d in essenciais if d not in guardados]
    uso = [d for d in guardados if d.startswith("modis_landuse")]
    if faltam or not uso:
        sys.exit(f"ERRO: faltam datasets essenciais: {faltam or ''} {'' if uso else 'uso do solo'}")
    validar(SAIDA, tbl)
    open(os.path.join(SAIDA, ".ok"), "w").write("ok\n")


if __name__ == "__main__":
    main()
