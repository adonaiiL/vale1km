#!/usr/bin/env python3
"""Vale1Km: gera mapas (14 produtos) e sondagens (A, F, K) a partir da saída do WRF de 1 km.

Uso: plotar.py --wrf run_wrf/wrf --manifesto dados/manifesto.json --ini 2026-10-24T15 --fim 2026-10-24T21 --passo 1 --saida site/resultados
"""
import argparse
import json
import os
import sys
import subprocess
import traceback
from datetime import datetime, timedelta

import numpy as np


def _json_default(obj):
    """Converte tipos NumPy para tipos nativos aceitos pelo JSON do navegador."""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Tipo não serializável no manifesto: {type(obj).__name__}")

import dominio as D
import leitura as L
import mapas as M
import sondagem as S_
import vetores as V

FMT = "%Y-%m-%dT%H"
ROTULOS = [(k, v[0]) for k, v in M.PARAMS.items()]


def painel_neve(ctx, c, neve_ant):
    azul = M._cmap("Blues", 9)
    niv_neve = [0.0, 0.1, 0.5, 1, 2, 5, 10, 20, 30, 50]
    return [("Neve acumulada total [cm]", c["neve_cm"], niv_neve, azul, "max", None),
            ("Neve na última hora [cm]", np.maximum(c["neve_cm"] - neve_ant, 0.0), niv_neve, azul, "max", None),
            ("Temperatura a 2 m [°C] (contorno de 0 °C)", c["t2"], M.lv(-10, 30, 2.5), M._cmap("RdYlBu_r", 16), "both", c["t2"]),
            ("Altura da isoterma de 0 °C [m AGL]", c["z0"], M.lv(0, 5000, 500), M._cmap("viridis_r", 10), "max", None)]


def painel_shear(c):
    v = lambda a, b, n: (M.lv(a, b, (b - a) / n), M._cmap("viridis", n))
    l1, c1 = v(0, 40, 8); l3, c3 = v(0, 60, 12); l6, c6 = v(0, 80, 8)
    return [("Cisalhamento 0-1 km [kt]", c["sh01"], l1, c1, "max", None),
            ("Cisalhamento 0-3 km [kt]", c["sh03"], l3, c3, "max", None),
            ("Cisalhamento 0-6 km [kt]", c["sh06"], l6, c6, "max", None)]


def progresso(pct, msg):
    """Atualiza o andamento no release do GitHub (se houver GH_TOKEN); nunca derruba a rodada."""
    if not os.environ.get("GH_TOKEN"):
        return
    try:
        subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)), "progresso.sh"), str(int(pct)), msg],
                       timeout=60, check=False)
    except Exception:
        pass


def salvar_estado(args, tag, est, S, c):
    """Guarda o estado 3D do horário (float32 comprimido) para gerar sondagens de qualquer ponto depois."""
    if not getattr(args, "estado", None):
        return
    os.makedirs(args.estado, exist_ok=True)
    np.savez_compressed(os.path.join(args.estado, f"estado_{tag}.npz"), lat=S.lat.astype("f4"), lon=S.lon.astype("f4"),
                        p=est["p"].astype("f4"), T=est["T"].astype("f4"), r=est["r"].astype("f4"), zagl=est["zagl"].astype("f4"),
                        u=est["u"].astype("f4"), v=est["v"].astype("f4"), w=est["w"].astype("f4"),
                        u10=est["u10"].astype("f4"), v10=est["v10"].astype("f4"), refl=c["refl"].astype("f4"))


def gerar(S, args, mun, rod):
    ini = datetime.strptime(args.ini, FMT)
    fim = datetime.strptime(args.fim, FMT)
    init = datetime.strptime(args.init, FMT)
    quandos = []
    t = ini
    while t <= fim:
        if t in S.tempos:
            quandos.append(t)
        else:
            print(f"Aviso: {t:%Y-%m-%d %H}Z não está na saída do WRF; ignorado")
        t += timedelta(hours=args.passo)
    if not quandos:
        sys.exit("ERRO: nenhum horário da janela existe na saída do WRF")
    os.makedirs(args.saida, exist_ok=True)
    t2_serie = S.serie("T2")
    t2_min_acum = np.minimum.accumulate(t2_serie - 273.15, axis=0) if t2_serie is not None else None
    neve_serie = S.serie("SNOWNC")
    manifesto = dict(modelo=D.NOME, init=args.init, resolucao_km=1, uh_limiar=D.UH_LIMIAR,
                     vetores=dict(municipios=len(mun), rodovias=len(rod)),
                     parametros=[dict(chave=k, rotulo=r) for k, r in ROTULOS],
                     pontos={k: dict(nome=v[0], lat=v[1], lon=v[2]) for k, v in D.PONTOS.items()},
                     tempos=[], falhas=[])
    for n_, quando in enumerate(quandos):
        progresso(85 + 12 * n_ / len(quandos), f"Gerando mapas e sondagens ({n_ + 1} de {len(quandos)})")
        i = S.indice(quando)
        tag = quando.strftime("%Y%m%d%H")
        print(f"\n== {quando:%Y-%m-%d %H}Z ==", flush=True)
        est = S.estado(i)
        c = L.derivar(est, S)
        uh = S.uh_min(quando)
        ctx = M.Ctx(S.lon, S.lat, init, quando, mun, rod, uh)
        manifesto["geom"] = dict(W=M.W, H=M.H, x0=20, y0=196, w=1985, h=min(1985 / ctx.ratio, 1648),
                                 lon0=float(ctx.ext[0]), lon1=float(ctx.ext[1]), lat0=float(ctx.ext[2]), lat1=float(ctx.ext[3]))
        arquivos, sond = {}, {}

        def produto(chave, fn):
            nome = f"{chave}_{tag}.png"
            try:
                fig = fn()
                M.salvar(fig, os.path.join(args.saida, nome))
                arquivos[chave] = nome
            except Exception:
                traceback.print_exc()
                manifesto["falhas"].append(f"{chave} {tag}")

        produto("rf", lambda: M.mapa_simples("rf", ctx, c["refl"]))
        produto("ws", lambda: M.mapa_simples("ws", ctx, c["ws"], barbs=(c["u10"] * 1.943844, c["v10"] * 1.943844, 5)))
        produto("t2", lambda: M.mapa_simples("t2", ctx, c["t2"]))
        produto("rh", lambda: M.mapa_simples("rh", ctx, c["rh"]))
        produto("pr", lambda: M.mapa_simples("pr", ctx, c["pr"]))
        produto("td", lambda: M.mapa_simples("td", ctx, c["td"]))
        tmin = t2_min_acum[i] if t2_min_acum is not None else c["t2"]
        produto("fr", lambda: M.mapa_simples("fr", ctx, tmin))
        produto("ml", lambda: M.mapa_simples("ml", ctx, c["ml"]))
        produto("mu", lambda: M.mapa_simples("mu", ctx, c["mu"]))
        produto("sc", lambda: M.mapa_simples("sc", ctx, c["sc"]))
        produto("vo", lambda: M.mapa_simples("vo", ctx, c["vo"]))
        nant = neve_serie[i - 1] * 1.0 if (neve_serie is not None and i > 0) else np.zeros_like(c["neve_cm"])
        produto("sn", lambda: M.mosaico("sn", ctx, painel_neve(ctx, c, nant), (2, 2)))
        produto("sh", lambda: M.mosaico("sh", ctx, painel_shear(c), (2, 2)))
        produto("hd", lambda: M.hodomap(ctx, c["mu"], L.ALT, c["U"], c["V"], c["rm"], c["lm"]))

        inset = dict(lon=S.lon, lat=S.lat, refl=c["refl"], mun=mun, rod=rod, ext=ctx.ext, max=float(np.nanmax(c["refl"])))
        salvar_estado(args, tag, est, S, c)
        for letra, (nome, lat, lon) in D.PONTOS.items():
            nomearq = f"sond_{letra}_{tag}.png"
            try:
                col, _ = L.coluna(est, S, lat, lon)
                col.update(lon=lon, lat=lat, letra=letra, nome=nome, init=init, val=quando)
                calc = S_.calcular(col)
                fig = S_.figura(col, calc, inset)
                fig.savefig(os.path.join(args.saida, nomearq), dpi=150, facecolor="white")
                S_.plt.close(fig)
                sond[letra] = nomearq
            except Exception:
                traceback.print_exc()
                manifesto["falhas"].append(f"sond_{letra} {tag}")
        brt = quando - timedelta(hours=3)
        manifesto["tempos"].append(dict(utc=quando.strftime(FMT), brt=brt.strftime(FMT), mapas=arquivos, sondagens=sond))
        print(f"   {len(arquivos)} mapas, {len(sond)} sondagens", flush=True)
    # Grava o manifesto de forma atômica. A geometria derivada dos arrays do WRF
    # pode conter escalares numpy.float32, não aceitos pelo encoder JSON padrão.
    caminho_manifesto = os.path.join(args.saida, "manifest.json")
    temporario = caminho_manifesto + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1, default=_json_default, allow_nan=False)
    os.replace(temporario, caminho_manifesto)
    ok = sum(len(x["mapas"]) + len(x["sondagens"]) for x in manifesto["tempos"])
    total = len(quandos) * (len(M.PARAMS) + len(D.PONTOS))
    print(f"\nProdutos gerados: {ok} de {total}")
    if ok < total * 0.5:
        sys.exit("ERRO: menos da metade dos produtos foi gerada")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrf", required=True)
    ap.add_argument("--init", required=True, help="inicialização do ICON (AAAA-MM-DDTHH)")
    ap.add_argument("--ini", required=True)
    ap.add_argument("--fim", required=True)
    ap.add_argument("--passo", type=int, default=1)
    ap.add_argument("--saida", default="site/resultados")
    ap.add_argument("--cache", default="dados/vetores")
    ap.add_argument("--estado", default="estado_cache", help="pasta onde guardar o estado 3D de cada horário")
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    S = L.Saida(a.wrf)
    caixa = (float(S.lon.min()) - 0.1, float(S.lon.max()) + 0.1, float(S.lat.min()) - 0.1, float(S.lat.max()) + 0.1)
    mun = V.municipios(os.path.join(a.cache, "ibge_sc.json"), caixa)
    rod = V.rodovias(os.path.join(a.cache, "rodovias.json"), caixa)
    print(f"Municípios na caixa: {len(mun)}; trechos de rodovia: {len(rod)}")
    if not mun or not rod:
        print("AVISO: mapas sairão sem " + ("limites municipais " if not mun else "") + ("rodovias" if not rod else ""))
    gerar(S, a, mun, rod)


if __name__ == "__main__":
    main()
