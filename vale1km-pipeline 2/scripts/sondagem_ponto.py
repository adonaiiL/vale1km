#!/usr/bin/env python3
"""Vale1Km: sondagem de qualquer ponto do mapa, a partir do estado 3D guardado pela rodada.

Uso: sondagem_ponto.py --estado estado_cache --tempo 2026102415 --lat -26.80 --lon -49.10 --init 2026-10-24T12 --saida sond.png
"""
import argparse
import glob
import os
import sys
from datetime import datetime

import numpy as np

import dominio as D
import sondagem as S_
import vetores as V

FMT = "%Y%m%d%H"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", default="estado_cache")
    ap.add_argument("--tempo", required=True, help="AAAAMMDDHH (UTC)")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--init", default="")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--cache", default="dados/vetores")
    a = ap.parse_args()
    arq = os.path.join(a.estado, f"estado_{a.tempo}.npz")
    if not os.path.exists(arq):
        disp = sorted(os.path.basename(f)[7:17] for f in glob.glob(os.path.join(a.estado, "estado_*.npz")))
        sys.exit(f"ERRO: não há estado para {a.tempo}. Horários disponíveis: {disp}")
    z = np.load(arq)
    lat2, lon2 = z["lat"], z["lon"]
    if not (lat2.min() <= a.lat <= lat2.max() and lon2.min() <= a.lon <= lon2.max()):
        sys.exit(f"ERRO: ponto fora do domínio de 1 km (lat {lat2.min():.3f} a {lat2.max():.3f}, lon {lon2.min():.3f} a {lon2.max():.3f})")
    d = (lat2 - a.lat) ** 2 + ((lon2 - a.lon) * np.cos(np.radians(a.lat))) ** 2
    j, i = np.unravel_index(np.argmin(d), d.shape)
    col = dict(p=z["p"][:, j, i].astype(float), T=z["T"][:, j, i].astype(float), r=z["r"][:, j, i].astype(float),
               zagl=z["zagl"][:, j, i].astype(float), u=z["u"][:, j, i].astype(float), v=z["v"][:, j, i].astype(float),
               w=z["w"][:, j, i].astype(float), u10=float(z["u10"][j, i]), v10=float(z["v10"][j, i]))
    val = datetime.strptime(a.tempo, FMT)
    init = datetime.strptime(a.init, "%Y-%m-%dT%H") if a.init else val
    col.update(lon=a.lon, lat=a.lat, letra="P", nome="ponto escolhido", init=init, val=val)
    calc = S_.calcular(col)
    c = 4
    ext = (float(lon2[c:-c, c:-c].min()), float(lon2[c:-c, c:-c].max()), float(lat2[c:-c, c:-c].min()), float(lat2[c:-c, c:-c].max()))
    caixa = (float(lon2.min()) - 0.1, float(lon2.max()) + 0.1, float(lat2.min()) - 0.1, float(lat2.max()) + 0.1)
    os.makedirs(a.cache, exist_ok=True)
    mun = V.municipios(os.path.join(a.cache, "ibge_municipios.json"), caixa)
    rod = V.rodovias(os.path.join(a.cache, "rodovias.json"), caixa)
    refl = z["refl"]
    inset = dict(lon=lon2, lat=lat2, refl=refl, mun=mun, rod=rod, ext=ext, max=float(np.nanmax(refl)))
    fig = S_.figura(col, calc, inset)
    fig.savefig(a.saida, dpi=150, facecolor="white")
    print(f"Sondagem de ({a.lat:.4f}, {a.lon:.4f}) usando a célula ({lat2[j, i]:.4f}, {lon2[j, i]:.4f}) em {a.saida}")


if __name__ == "__main__":
    main()
