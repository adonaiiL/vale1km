#!/usr/bin/env python3
"""Vale1Km, etapa 1: baixa do DWD só os arquivos do ICON Global que a janela pede.

Exemplo:
  baixar_icon.py --init 2026-10-21T12 --ini 2026-10-24T15 --fim 2026-10-24T21
"""
import argparse
import bz2
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

BASE = "https://opendata.dwd.de/weather/nwp/icon/grib"
FMT = "%Y-%m-%dT%H"

# (tipo de nível, parâmetro = nome da pasta no servidor, obrigatório)
VARIAVEIS = (
    [("pressure-level", p, True) for p in ("t", "u", "v", "fi", "relhum")]
    + [("pressure-level", p, False) for p in ("qv", "omega")]
    + [("single-level", p, True) for p in ("ps", "pmsl", "t_2m", "u_10m", "v_10m")]
    + [("single-level", p, False)
       for p in ("td_2m", "relhum_2m", "t_g", "w_snow", "h_snow", "qv_s")]
    + [("soil-level", p, False) for p in ("t_so", "w_so")]
    + [("time-invariant", p, True) for p in ("hsurf", "fr_land")]
)

NOME = re.compile(
    r"^icon_global_icosahedral_(?P<tipo>[a-z-]+)_(?P<data>\d{10})"
    r"(?:_(?P<passo>\d{3}))?(?:_(?P<nivel>\d+))?_(?P<par>[A-Z0-9_]+)\.grib2\.bz2$"
)


def http_get(url, tentativas=4):
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vale1km"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            erro = e
        except Exception as e:  # rede instável: tenta de novo
            erro = e
        time.sleep(2 ** i)
    raise erro


def listar(hh, par):
    try:
        html = http_get(f"{BASE}/{hh:02d}/{par}/").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return re.findall(r'href="([^"]+\.grib2\.bz2)"', html)


def baixar(item, pasta):
    url, nome = item
    destino = os.path.join(pasta, nome[:-4])  # tira o .bz2
    if os.path.exists(destino):
        return os.path.getsize(destino)
    dados = bz2.decompress(http_get(url))
    with open(destino + ".tmp", "wb") as f:
        f.write(dados)
    os.replace(destino + ".tmp", destino)
    return len(dados)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--init", required=True, help="inicialização, AAAA-MM-DDTHH (UTC)")
    ap.add_argument("--ini", required=True, help="primeiro horário válido da janela")
    ap.add_argument("--fim", required=True, help="último horário válido da janela")
    ap.add_argument("--spinup", type=int, default=3,
                    help="horas antes da janela usadas como condição inicial do WRF")
    ap.add_argument("--passo", type=int, default=3,
                    help="intervalo das condições de contorno, em horas")
    ap.add_argument("--saida", default="dados/icon_raw")
    a = ap.parse_args()

    init = datetime.strptime(a.init, FMT)
    t0 = max(datetime.strptime(a.ini, FMT) - timedelta(hours=a.spinup), init)
    t1 = datetime.strptime(a.fim, FMT)
    if t1 < t0:
        sys.exit("Erro: a janela termina antes de começar.")

    validos, t = [], t0
    while True:
        validos.append(t)
        if t >= t1:
            break
        t += timedelta(hours=a.passo)
    if len(validos) < 2:  # o WRF precisa de pelo menos dois horários de contorno
        validos.append(validos[0] + timedelta(hours=a.passo))
    leads = [int((v - init).total_seconds() // 3600) for v in validos]

    limite = 180 if init.hour % 12 == 0 else 120
    if leads[-1] > limite:
        sys.exit(f"Erro: a janela chega a +{leads[-1]} h, e o ICON da rodada {init.hour:02d}Z "
                 f"vai até +{limite} h. Escolha uma janela mais próxima da inicialização.")

    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    idade = (agora - init).total_seconds() / 3600
    print(f"Inicialização {a.init}Z, há {idade:.0f} h.")
    if idade > 48:
        print("Aviso: o DWD guarda só cerca de 48 h de dados; essa rodada pode já ter sido apagada.")
    print("Horários necessários (UTC / passo da previsão):")
    for v, l in zip(validos, leads):
        print(f"  {v:%d/%m %HZ}  f{l:03d}")

    caminho = os.path.join(os.path.dirname(a.saida) or ".", "manifesto.json")
    if os.path.exists(caminho):  # tentativa repetida: reaproveita o que o cache devolveu
        try:
            with open(caminho, encoding="utf-8") as f:
                m = json.load(f)
            if (m.get("init") == a.init and m.get("passos") == leads and m["arquivos"]
                    and all(os.path.exists(os.path.join(a.saida, x["arquivo"][:-4]))
                            for x in m["arquivos"])):
                print(f"Usando {len(m['arquivos'])} arquivos já baixados (cache), sem consultar o DWD.")
                return
        except (ValueError, KeyError, OSError):
            pass

    carimbo = init.strftime("%Y%m%d%H")
    hh = init.hour
    itens, resumo, faltam, datas_vistas = [], [], [], set()
    for tipo, par, obrig in VARIAVEIS:
        sel = []
        for n in listar(hh, par):
            m = NOME.match(n)
            if not m or m["tipo"] != tipo:
                continue
            datas_vistas.add(m["data"])
            if m["data"] != carimbo:
                continue
            if tipo != "time-invariant":
                if m["passo"] is None or int(m["passo"]) not in leads:
                    continue
            sel.append({"url": f"{BASE}/{hh:02d}/{par}/{n}", "arquivo": n, "tipo": tipo,
                        "par": m["par"], "passo": m["passo"], "nivel": m["nivel"]})
        if tipo == "time-invariant":
            achou_ok = len(sel) > 0
            ausentes = []
        else:
            achados = {int(s["passo"]) for s in sel}
            ausentes = sorted(set(leads) - achados)
            achou_ok = len(sel) > 0 and not ausentes
        niveis = sorted({int(s["nivel"]) for s in sel if s["nivel"]})
        resumo.append((tipo, par, obrig, len(sel), niveis, ausentes))
        if obrig and not achou_ok:
            faltam.append(f"{tipo}/{par}" + (f" (passos ausentes: {ausentes})" if sel else ""))
        itens.extend(sel)

    print("\nO que existe no servidor para esses horários:")
    for tipo, par, obrig, n, niveis, ausentes in resumo:
        marca = "obrigatório" if obrig else "opcional"
        extra = f", níveis {niveis}" if niveis else ""
        print(f"  {tipo:15s} {par:10s} {marca:11s} {n:4d} arquivos{extra}")

    if faltam:
        if carimbo not in datas_vistas:
            print(f"\nA rodada {carimbo} não está no servidor. Rodadas {hh:02d}Z encontradas: "
                  f"{sorted(datas_vistas) or 'nenhuma'}.")
            print("Ela pode ainda não ter sido publicada (leva algumas horas) ou já ter sido apagada.")
        sys.exit("Erro: faltam dados obrigatórios: " + "; ".join(faltam))

    os.makedirs(a.saida, exist_ok=True)
    print(f"\nBaixando {len(itens)} arquivos...")
    ini_t = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        tamanhos = list(ex.map(lambda it: baixar((it["url"], it["arquivo"]), a.saida), itens))
    mb = sum(tamanhos) / 1e6
    print(f"Pronto: {mb:.0f} MB em {time.time() - ini_t:.0f} s.")

    manifesto = {
        "init": a.init,
        "horarios_utc": [f"{v:%Y-%m-%dT%H}" for v in validos],
        "passos": leads,
        "arquivos": [{k: s[k] for k in ("arquivo", "tipo", "par", "passo", "nivel")} for s in itens],
        "opcionais_ausentes": [f"{t}/{p}" for t, p, o, n, _, _ in resumo if not o and n == 0],
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(manifesto, f, indent=1, ensure_ascii=False)

    resumo_md = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo_md:
        with open(resumo_md, "a", encoding="utf-8") as f:
            f.write(f"### ICON baixado\n\n{len(itens)} arquivos, {mb:.0f} MB. "
                    f"Passos: {', '.join(f'f{l:03d}' for l in leads)}.\n\n")
            if manifesto["opcionais_ausentes"]:
                f.write("Opcionais ausentes: " + ", ".join(manifesto["opcionais_ausentes"]) + "\n")


if __name__ == "__main__":
    main()
