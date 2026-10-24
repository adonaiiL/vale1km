#!/usr/bin/env python3
"""Vale1Km: converte o ICON (NetCDF em lat/lon, já recortado) para o formato intermediário do WPS.

Escreve um arquivo FILE:AAAA-MM-DD_HH por horário em --saida. Dispensa o ungrib: os campos já
vêm identificados pelo nome do arquivo do DWD, então não depende de Vtable para o ICON.
"""
import argparse
import json
import os
import re
import struct
import sys
from datetime import datetime

import numpy as np

NOME = re.compile(
    r"^icon_global_icosahedral_(?P<tipo>[a-z-]+)_(?P<data>\d{10})"
    r"(?:_(?P<passo>\d{3}))?(?:_(?P<nivel>\d+))?_(?P<par>[A-Z0-9_]+)\.nc$"
)
G = 9.80665
RD = 287.04
# Camadas do Noah (cm): 0-10, 10-40, 40-100, 100-200
NOAH = [(0, 10), (10, 40), (40, 100), (100, 200)]
NOAH_NOME = ["000010", "010040", "040100", "100200"]
# Camadas do solo do ICON (cm). O rótulo do W_SO é o topo da camada.
ICON_TOPOS = [0, 1, 3, 9, 27, 81, 243, 729, 2187]


# ---------------------------------------------------------------- leitura
def ler_nc(caminho):
    """Devolve (lat1d crescente, lon1d, campo 2D com NaN onde faltar)."""
    import netCDF4
    with netCDF4.Dataset(caminho) as ds:
        nomes = list(ds.variables)
        lat = next(n for n in nomes if n.lower() in ("lat", "latitude"))
        lon = next(n for n in nomes if n.lower() in ("lon", "longitude"))
        la, lo = np.array(ds[lat][:], dtype=float), np.array(ds[lon][:], dtype=float)
        dado = None
        for n in nomes:
            v = ds[n]
            if n in (lat, lon) or len(v.dimensions) < 2:
                continue
            if v.shape[-2:] == (la.size, lo.size):
                dado = np.ma.filled(np.ma.masked_invalid(v[:]).astype(float), np.nan)
                break
        if dado is None:
            raise ValueError(f"nenhuma variável em grade lat/lon em {caminho}")
    dado = np.squeeze(dado)
    if dado.ndim != 2:
        dado = dado.reshape(la.size, lo.size)
    if la[0] > la[-1]:
        la, dado = la[::-1], dado[::-1]
    dado[np.abs(dado) > 1e15] = np.nan
    return la, lo, dado


def indexar(pasta):
    idx = {}
    for n in os.listdir(pasta):
        m = NOME.match(n)
        if m:
            chave = (m["tipo"], m["par"], int(m["passo"]) if m["passo"] else None,
                     int(m["nivel"]) if m["nivel"] else None)
            idx[chave] = os.path.join(pasta, n)
    return idx


# ---------------------------------------------------------------- utilitários numéricos
def preencher_vizinho(a):
    """Troca NaN pelo valor válido mais próximo (horizontal)."""
    if not np.isnan(a).any():
        return a
    if np.isnan(a).all():
        return np.zeros_like(a)
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(np.isnan(a), return_distances=False, return_indices=True)
    return a[tuple(idx)]


def preencher_vertical(cubo):
    """cubo[k] com k de baixo (maior pressão) para cima: NaN abaixo do solo recebe o valor do nível acima."""
    for k in range(cubo.shape[0] - 2, -1, -1):
        cubo[k] = np.where(np.isnan(cubo[k]), cubo[k + 1], cubo[k])
    return cubo


def umidade_de_td(t, td):
    a, b = 17.625, 243.04
    return 100.0 * np.exp(a * (td - 273.15) / (b + td - 273.15) - a * (t - 273.15) / (b + t - 273.15))


# ---------------------------------------------------------------- escrita do formato intermediário (versão 5)
def registro(f, payload):
    n = struct.pack(">i", len(payload))
    f.write(n + payload + n)


def txt(s, n):
    return s.encode("ascii", "replace")[:n].ljust(n)


def escrever_campo(f, data, nome, unidade, desc, nivel, campo, la, lo, fonte="ICON-GLOBAL DWD 0.125 regrid"):
    ny, nx = campo.shape
    cab = (txt(data, 24) + struct.pack(">f", 0.0) + txt(fonte, 32) + txt(nome, 9) + txt(unidade, 25)
           + txt(desc, 46) + struct.pack(">f", float(nivel)) + struct.pack(">iii", nx, ny, 0))
    registro(f, struct.pack(">i", 5))
    registro(f, cab)
    dlat = float(np.mean(np.diff(la)))
    dlon = float(np.mean(np.diff(lo)))
    registro(f, txt("SWCORNER", 8) + struct.pack(">fffff", float(la[0]), float(lo[0]), dlat, dlon, 6367.470215))
    registro(f, struct.pack(">i", 0))
    registro(f, np.ascontiguousarray(campo, dtype=">f4").tobytes())


SUPERFICIE = 200100.0


# ---------------------------------------------------------------- conversão de um horário
def converter_horario(idx, passo, ti_path, saida_dir, data_wps, ler=ler_nc):
    def L(tipo, par, nivel=None, p=passo, obrig=True):
        chave = (tipo, par, None if tipo == "time-invariant" else p, nivel)
        if chave not in idx:
            if obrig:
                raise KeyError(f"falta no ICON: {chave}")
            return None
        return ler(idx[chave])

    la = lo = None
    niveis = sorted({k[3] for k in idx if k[0] == "pressure-level" and k[1] == "T" and k[2] == passo}, reverse=True)
    if not niveis:
        raise KeyError(f"sem níveis de pressão para o passo {passo}")

    def cubo(par):
        nonlocal la, lo
        arr = []
        for n in niveis:
            la, lo, a = L("pressure-level", par, n)
            arr.append(a)
        return np.stack(arr)

    T, U, V, FI, RH = cubo("T"), cubo("U"), cubo("V"), cubo("FI"), cubo("RELHUM")
    T, U, V, RH = (preencher_vertical(x) for x in (T, U, V, RH))
    # geopotencial abaixo do solo: extrapola hipsometricamente a partir do nível acima
    for k in range(len(niveis) - 2, -1, -1):
        falta = np.isnan(FI[k])
        if falta.any():
            tm = np.where(np.isnan(T[k]), T[k + 1], T[k])
            dz = RD * tm / G * np.log(niveis[k + 1] / niveis[k]) * -1.0
            FI[k] = np.where(falta, FI[k + 1] + G * dz, FI[k])
    GHT = FI / G
    for c in (T, U, V, RH, GHT):
        for k in range(c.shape[0]):
            c[k] = preencher_vizinho(c[k])
    RH = np.clip(RH, 0.0, 100.0)

    _, _, ps = L("single-level", "PS")
    _, _, pmsl = L("single-level", "PMSL")
    _, _, t2 = L("single-level", "T_2M")
    _, _, u10 = L("single-level", "U_10M")
    _, _, v10 = L("single-level", "V_10M")
    rh2 = L("single-level", "RELHUM_2M", obrig=False)
    td2 = L("single-level", "TD_2M", obrig=False)
    tg = L("single-level", "T_G", obrig=False)
    ps, pmsl, t2, u10, v10 = (preencher_vizinho(x) for x in (ps, pmsl, t2, u10, v10))
    if rh2 is not None:
        rh2 = preencher_vizinho(rh2[2])
    elif td2 is not None:
        rh2 = umidade_de_td(t2, preencher_vizinho(td2[2]))
    else:
        rh2 = RH[0]
    rh2 = np.clip(rh2, 1.0, 100.0)
    skin = preencher_vizinho(tg[2]) if tg is not None else t2
    hsurf = preencher_vizinho(ler(ti_path["HSURF"])[2])
    frland = preencher_vizinho(ler(ti_path["FR_LAND"])[2])
    landsea = (frland >= 0.5).astype(float)

    # solo: temperatura por profundidade e umidade volumétrica por camada do Noah
    st, sm = soilfields(idx, passo, t2, ler)

    os.makedirs(saida_dir, exist_ok=True)
    caminho = os.path.join(saida_dir, "FILE:" + data_wps[:13])
    with open(caminho, "wb") as f:
        for k, n in enumerate(niveis):
            p = n * 100.0
            escrever_campo(f, data_wps, "TT", "K", "Temperature", p, T[k], la, lo)
            escrever_campo(f, data_wps, "UU", "m s-1", "U", p, U[k], la, lo)
            escrever_campo(f, data_wps, "VV", "m s-1", "V", p, V[k], la, lo)
            escrever_campo(f, data_wps, "RH", "%", "Relative Humidity", p, RH[k], la, lo)
            escrever_campo(f, data_wps, "GHT", "m", "Height", p, GHT[k], la, lo)
        s = SUPERFICIE
        escrever_campo(f, data_wps, "TT", "K", "Temperature at 2 m", s, t2, la, lo)
        escrever_campo(f, data_wps, "RH", "%", "Relative Humidity at 2 m", s, rh2, la, lo)
        escrever_campo(f, data_wps, "UU", "m s-1", "U at 10 m", s, u10, la, lo)
        escrever_campo(f, data_wps, "VV", "m s-1", "V at 10 m", s, v10, la, lo)
        escrever_campo(f, data_wps, "PSFC", "Pa", "Surface Pressure", s, ps, la, lo)
        escrever_campo(f, data_wps, "PMSL", "Pa", "Sea-level Pressure", s, pmsl, la, lo)
        escrever_campo(f, data_wps, "SKINTEMP", "K", "Skin temperature", s, skin, la, lo)
        escrever_campo(f, data_wps, "SOILHGT", "m", "Terrain field of source analysis", s, hsurf, la, lo)
        escrever_campo(f, data_wps, "LANDSEA", "0/1 Flag", "Land/Sea flag", s, landsea, la, lo)
        escrever_campo(f, data_wps, "SEAICE", "proprtn", "Ice flag", s, np.zeros_like(t2), la, lo)
        escrever_campo(f, data_wps, "SNOW", "kg m-2", "Water equivalent snow depth", s, np.zeros_like(t2), la, lo)
        for i, nome in enumerate(NOAH_NOME):
            escrever_campo(f, data_wps, "ST" + nome, "K", "Soil temperature " + nome, s, st[i], la, lo)
            escrever_campo(f, data_wps, "SM" + nome, "m3 m-3", "Soil moisture " + nome, s, sm[i], la, lo)
    return caminho, niveis


def soilfields(idx, passo, t2, ler):
    """Interpola T_SO em profundidade e média a umidade (W_SO) nas camadas do Noah."""
    rot = lambda r: {0: 0.0, 5: 0.5}.get(r, float(r))  # rótulo 5 do T_SO = 0,5 cm
    tn = sorted({k[3] for k in idx if k[0] == "soil-level" and k[1] == "T_SO" and k[2] == passo})
    wn = sorted({k[3] for k in idx if k[0] == "soil-level" and k[1] == "W_SO" and k[2] == passo})
    ny, nx = t2.shape
    if tn:
        prof = np.array([rot(n) for n in tn])
        ordem = np.argsort(prof)
        prof = prof[ordem]
        campos = np.stack([preencher_vizinho(ler(idx[("soil-level", "T_SO", passo, tn[o])])[2]) for o in ordem])
        st = []
        for (a, b) in NOAH:
            alvo = (a + b) / 2.0 if a else 5.0
            j = int(np.clip(np.searchsorted(prof, alvo) - 1, 0, len(prof) - 2))
            w = np.clip((alvo - prof[j]) / (prof[j + 1] - prof[j]), 0.0, 1.0)
            st.append(campos[j] * (1 - w) + campos[j + 1] * w)
    else:
        st = [t2 for _ in NOAH]
    sm = []
    if wn:
        topos = ICON_TOPOS
        agua = {n: preencher_vizinho(ler(idx[("soil-level", "W_SO", passo, n)])[2]) for n in wn}
        camadas = []
        for n in wn:
            i = topos.index(n)
            camadas.append((topos[i], topos[i + 1], agua[n]))
        for (a, b) in NOAH:
            num = np.zeros((ny, nx))
            den = 0.0
            for (c0, c1, w) in camadas:
                sobre = max(0.0, min(b, c1) - max(a, c0))
                if sobre > 0:
                    theta = w / (10.0 * (c1 - c0))  # kg/m2 -> m3/m3
                    num += theta * sobre
                    den += sobre
            th = num / den if den > 0 else np.full((ny, nx), 0.3)
            sm.append(th)
        if not (0.0 < np.nanmean(sm[0]) < 0.8):
            print("Aviso: umidade do solo fora do esperado; usando 0,3 m3/m3 constante", file=sys.stderr)
            sm = [np.full((ny, nx), 0.3) for _ in NOAH]
        sm = [np.clip(x, 0.02, 0.6) for x in sm]
    else:
        sm = [np.full((ny, nx), 0.3) for _ in NOAH]
    return st, sm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="dados/icon_reg")
    ap.add_argument("--manifesto", default="dados/manifesto.json")
    ap.add_argument("--saida", default="wps_in")
    a = ap.parse_args()
    man = json.load(open(a.manifesto, encoding="utf-8"))
    idx = indexar(a.entrada)
    ti = {k[1]: v for k, v in idx.items() if k[0] == "time-invariant"}
    for nec in ("HSURF", "FR_LAND"):
        if nec not in ti:
            sys.exit(f"ERRO: falta o campo fixo {nec}")
    init = datetime.strptime(man["init"], "%Y-%m-%dT%H")
    for h, passo in zip(man["horarios_utc"], man["passos"]):
        t = datetime.strptime(h, "%Y-%m-%dT%H")
        data = t.strftime("%Y-%m-%d_%H:00:00")
        caminho, niveis = converter_horario(idx, passo, ti, a.saida, data)
        print(f"{data}  f{passo:03d}  {len(niveis)} níveis  {os.path.getsize(caminho) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
