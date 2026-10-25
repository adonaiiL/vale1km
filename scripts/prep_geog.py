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


def datasets_pedidos(tbl):
    """Nomes (pasta de topo) dos conjuntos 'default:' do GEOGRID.TBL. Vazio se não houver tabela."""
    if not tbl or not os.path.exists(tbl):
        return set()
    out = set()
    for linha in open(tbl, encoding="utf-8", errors="replace"):
        if "rel_path" in linha and not linha.lstrip().startswith("#"):
            out.update(c.split("/")[0] for c in re.findall(r"default:([A-Za-z0-9_./-]+)", linha))
    return out


PEDIDOS = set()


def quer(dataset, nome):
    """Decide se o arquivo do tar deve ser guardado."""
    if PEDIDOS and dataset not in PEDIDOS:
        return False
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
    print("prep_geog.py versão 3 (ignora ._*, guarda só os datasets do GEOGRID.TBL)", flush=True)
    os.makedirs(SAIDA, exist_ok=True)
    tbl = sys.argv[2] if len(sys.argv) > 2 else None
    global PEDIDOS
    PEDIDOS = datasets_pedidos(tbl)
    print(f"Datasets pedidos pelo GEOGRID.TBL ({len(PEDIDOS)}): {sorted(PEDIDOS)}" if PEDIDOS else "Sem GEOGRID.TBL: guardando todos os datasets", flush=True)
    print(f"Blocos de 30\" que vamos guardar: x={sorted(X0)} y={sorted(Y0)}", flush=True)
    fluxo = io.BufferedReader(FluxoRetomavel(URL), buffer_size=8 * 1024 * 1024)
    guardados, ignorados, bytes_ok, ultimo, raiz = {}, 0, 0, time.time(), None
    with tarfile.open(fileobj=fluxo, mode="r|gz") as tar:
        for m in tar:
            if not m.isfile():
                continue
            partes = [p for p in m.name.split("/") if p not in ("", ".")]
            # lixo de macOS dentro do tar (AppleDouble "._nome", __MACOSX, .DS_Store)
            if not partes or any(p.startswith("._") or p in ("__MACOSX", ".DS_Store") for p in partes):
                continue
            if raiz is None:  # pasta de topo do tar (ex.: WPS_GEOG); se o primeiro item já for um dataset, não há
                raiz = partes[0] if "geog" in partes[0].lower() else ""
                print(f"Pasta de topo do tar: '{raiz}'", flush=True)
            rel = partes[1:] if raiz and partes[0] == raiz else partes
            if len(rel) < 2:
                continue
            dataset, nome = rel[0], rel[-1]
            if not quer(dataset, nome):
                ignorados += 1
                continue
            destino = os.path.join(SAIDA, *rel[:-1])
            os.makedirs(destino, exist_ok=True)
            with open(os.path.join(destino, nome), "wb") as f:
                f.write(tar.extractfile(m).read())
            guardados[dataset] = guardados.get(dataset, 0) + 1
            bytes_ok += m.size
            if bytes_ok > 10e9:
                sys.exit(f"ERRO: já guardei {bytes_ok / 1e9:.0f} GB, bem mais que o esperado; o filtro não está funcionando "
                         f"(datasets até agora: {sorted(guardados)[:8]})")
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
    for g in GRANDES:
        achou = [d for d in guardados if d.startswith(g)]
        if achou and guardados[achou[0]] < 2:
            sys.exit(f"ERRO: nenhum bloco de {g} cobre a região")
    validar(SAIDA, tbl)
    open(os.path.join(SAIDA, ".ok"), "w").write("ok\n")


if __name__ == "__main__":
    main()
