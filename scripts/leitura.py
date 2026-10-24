"""Vale1Km: leitura da saída do WRF (wrfout_d02 + auxhist2_d02) e produtos derivados."""
import glob
import os
from datetime import datetime, timedelta

import numpy as np

import dominio as D
import termo as t

ALT = np.arange(0.0, 6001.0, 250.0)  # alturas AGL do mapa de cisalhamento/Bunkers/hodomap


def _abrir(caminho):
    import netCDF4
    return netCDF4.Dataset(caminho)


def _tempos(nc):
    import netCDF4
    txt = netCDF4.chartostring(nc["Times"][:])
    return [datetime.strptime(str(s), "%Y-%m-%d_%H:%M:%S") for s in txt]


def _mass(a, eixo):
    s = [slice(None)] * a.ndim
    s0, s1 = list(s), list(s)
    s0[eixo], s1[eixo] = slice(0, -1), slice(1, None)
    return 0.5 * (a[tuple(s0)] + a[tuple(s1)])


class Saida:
    def __init__(self, pasta):
        self.wrf = _abrir(sorted(glob.glob(os.path.join(pasta, "wrfout_d02_*")))[0])
        aux = sorted(glob.glob(os.path.join(pasta, "auxhist2_d02_*")))
        self.aux = _abrir(aux[0]) if aux else None
        self.tempos = _tempos(self.wrf)
        self.tempos_aux = _tempos(self.aux) if self.aux else []
        self.lat = np.array(self.wrf["XLAT"][0])
        self.lon = np.array(self.wrf["XLONG"][0])
        self.cosa = np.array(self.wrf["COSALPHA"][0])
        self.sina = np.array(self.wrf["SINALPHA"][0])
        self.dx = float(self.wrf.DX)

    def rot(self, u, v):
        return u * self.cosa - v * self.sina, v * self.cosa + u * self.sina

    def serie(self, nome):
        return np.array(self.wrf[nome][:]) if nome in self.wrf.variables else None

    def indice(self, quando):
        return self.tempos.index(quando)

    # ------------------------------------------------------------ estado 3D de um horário
    def estado(self, i):
        w = self.wrf
        P = np.array(w["P"][i]) + np.array(w["PB"][i])
        th = np.array(w["T"][i]) + 300.0
        T = th * (P / 1e5) ** t.KAPPA
        qv = np.array(w["QVAPOR"][i])
        r = qv / (1.0 - qv)
        zs = (np.array(w["PH"][i]) + np.array(w["PHB"][i])) / t.G
        zm = _mass(zs, 0)
        agl = zm - zs[0][None]
        U = _mass(np.array(w["U"][i]), 2)
        V = _mass(np.array(w["V"][i]), 1)
        U, V = self.rot(U, V)
        Wm = _mass(np.array(w["W"][i]), 0)
        refl = np.array(w["REFL_10CM"][i])
        u10, v10 = self.rot(np.array(w["U10"][i]), np.array(w["V10"][i]))
        return dict(p=P, T=T, r=r, q=qv, zagl=agl, zasl=zm, u=U, v=V, w=Wm, refl3d=refl, u10=u10, v10=v10,
                    t2=np.array(w["T2"][i]), q2=np.array(w["Q2"][i]), psfc=np.array(w["PSFC"][i]),
                    chuva=np.array(w["RAINC"][i]) + np.array(w["RAINNC"][i]),
                    neve=np.array(w["SNOWNC"][i]) if "SNOWNC" in w.variables else np.zeros_like(P[0]))

    # ------------------------------------------------------------ UH 2-5 km (mínimo na última hora)
    def uh_min(self, quando):
        if self.aux is None:
            return None
        ini = quando - timedelta(hours=1)
        idx = [k for k, tt in enumerate(self.tempos_aux) if ini < tt <= quando]
        if not idx:
            return None
        a = self.aux
        melhor = None
        for k in idx:
            zs = (np.array(a["PH"][k]) + np.array(a["PHB"][k])) / t.G
            agl = _mass(zs, 0) - zs[0][None]
            U = _mass(np.array(a["U"][k]), 2)
            V = _mass(np.array(a["V"][k]), 1)
            Wm = _mass(np.array(a["W"][k]), 0)
            vort = np.gradient(V, self.dx, axis=2) - np.gradient(U, self.dx, axis=1)
            alt = np.arange(2000.0, 5001.0, 250.0)
            wz = t.perfil_agl(agl, Wm, alt)
            zz = t.perfil_agl(agl, vort, alt)
            uh = np.sum(np.maximum(wz, 0.0) * zz, axis=0) * 250.0
            melhor = uh if melhor is None else np.minimum(melhor, uh)
        return melhor


def umidade_relativa(T, q, p):
    e = q * p / (0.622 + 0.378 * q)
    return np.clip(100.0 * e / t.esat(T), 0.0, 100.0)


def derivar(est, S):
    """Campos 2D de todos os produtos a partir do estado 3D."""
    nz, ny, nx = est["p"].shape
    N = ny * nx
    pe = est["p"].reshape(nz, N)
    Te = est["T"].reshape(nz, N)
    re = est["r"].reshape(nz, N)
    ze = est["zagl"].reshape(nz, N)
    out = {}
    out["refl"] = np.nanmax(np.where(est["refl3d"] > -30, est["refl3d"], np.nan), axis=0)
    out["refl"] = np.where(np.isfinite(out["refl"]), out["refl"], 0.0)
    out["t2"] = est["t2"] - 273.15
    out["rh"] = umidade_relativa(est["t2"], est["q2"], est["psfc"])
    r2 = est["q2"] / (1 - est["q2"])
    out["td"] = t.dewpoint(est["psfc"], r2) - 273.15
    out["pr"] = est["chuva"]
    out["neve_cm"] = est["neve"] * 1.0  # 1 mm de água equivalente ~ 1 cm de neve (razão 10:1)
    out["u10"], out["v10"] = est["u10"], est["v10"]
    out["ws"] = np.hypot(est["u10"], est["v10"]) * 1.943844
    # CAPE
    for tipo, chave in (("ML", "ml"), ("MU", "mu")):
        p0, T0, r0 = t.parcelas(pe, Te, re, ze, tipo)
        o = t.cape_cin(pe, Te, re, ze, p0, T0, r0, dp=500.0)
        out[chave] = o["cape"].reshape(ny, nx)
        out[chave + "_cin"] = o["cin"].reshape(ny, nx)
    # ventos em alturas AGL
    zc = est["zagl"]
    Ua, Va = t.perfil_agl(zc, est["u"], ALT), t.perfil_agl(zc, est["v"], ALT)
    Ua[0], Va[0] = est["u10"], est["v10"]
    out["U"], out["V"] = Ua, Va
    mean, rm, lm, _ = t.bunkers(Ua, Va, ALT)
    out["rm"], out["lm"] = rm, lm
    sh = lambda a, b: np.hypot(Ua[b] - Ua[a], Va[b] - Va[a]) * 1.943844
    out["sh01"], out["sh03"], out["sh06"] = sh(0, 4), sh(0, 12), sh(0, 24)
    srh03 = t.srh(Ua, Va, ALT, lm, 0.0, 3000.0)
    out["srh03"] = srh03
    bwd = out["sh06"] / 1.943844
    eb = np.where(bwd < 10, 0.0, np.minimum(bwd / 20.0, 1.0))
    cin = np.where(out["mu_cin"] > -40, 1.0, -40.0 / np.minimum(out["mu_cin"], -1e-3))
    out["sc"] = (out["mu"] / 1000.0) * (np.maximum(-srh03, 0.0) / 50.0) * eb * cin
    # vorticidade relativa em 850 hPa (10^-5 s^-1)
    u850 = t.interp_z(-est["p"], est["u"], -85000.0)
    v850 = t.interp_z(-est["p"], est["v"], -85000.0)
    out["vo"] = (np.gradient(v850, S.dx, axis=1) - np.gradient(u850, S.dx, axis=0)) * 1e5
    # altura da isoterma de 0 °C (m AGL; 0 onde o solo já está abaixo de 0 °C)
    Tc = est["T"] - 273.15
    z0 = np.full((ny, nx), np.nan)
    for k in range(nz - 1, 0, -1):
        cruza = (Tc[k] <= 0) & (Tc[k - 1] > 0)
        f = Tc[k - 1] / np.where(Tc[k - 1] - Tc[k] == 0, 1, Tc[k - 1] - Tc[k])
        z0 = np.where(cruza, est["zagl"][k - 1] + f * (est["zagl"][k] - est["zagl"][k - 1]), z0)
    out["z0"] = np.where(Tc[0] <= 0, 0.0, z0)
    return out


def coluna(est, S, lat, lon):
    """Coluna do ponto mais próximo (em graus) para a sondagem."""
    d = (S.lat - lat) ** 2 + ((S.lon - lon) * np.cos(np.radians(lat))) ** 2
    j, i = np.unravel_index(np.argmin(d), d.shape)
    return dict(p=est["p"][:, j, i], T=est["T"][:, j, i], r=est["r"][:, j, i], zagl=est["zagl"][:, j, i],
                u=est["u"][:, j, i], v=est["v"][:, j, i], w=est["w"][:, j, i], u10=float(est["u10"][j, i]),
                v10=float(est["v10"][j, i])), (j, i)
