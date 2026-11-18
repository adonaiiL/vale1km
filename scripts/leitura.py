"""Vale1Km: leitura da saída do WRF (domínio de 1 km: wrfout + auxhist2) e produtos derivados."""
import glob
import os
from datetime import datetime, timedelta

import numpy as np
from scipy.ndimage import uniform_filter

import dominio as D
import termo as t

ALT = np.arange(0.0, 6001.0, 250.0)  # alturas AGL do mapa de cisalhamento/Bunkers/hodomap
G_WRF = 9.81                         # constantes do próprio WRF (g, R/cp)
KAPPA_WRF = 287.0 / 1004.5


def temperatura_wrf(theta_pert, qv_mistura, p):
    """Reconstrói T (K) quando use_theta_m=1 no namelist do Vale1Km.

    WRF armazena T como perturbação de theta_m; QVAPOR é razão de mistura.
    theta_m = theta * (1 + 1.61 * QVAPOR).
    """
    theta_m = np.asarray(theta_pert, dtype=float) + 300.0
    r = np.asarray(qv_mistura, dtype=float)
    pressao = np.asarray(p, dtype=float)
    theta = theta_m / (1.0 + 1.61 * r)
    return theta * (pressao / 1.0e5) ** KAPPA_WRF


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
        arqs = sorted(glob.glob(os.path.join(pasta, "wrfout_d0[0-9]_*")))
        dom = max(os.path.basename(a)[7:10] for a in arqs)  # domínio mais fino: d02 (ponte + 1 km) ou d01 (só 1 km)
        self.wrf = _abrir(next(a for a in arqs if os.path.basename(a)[7:10] == dom))
        aux = sorted(glob.glob(os.path.join(pasta, f"auxhist2_{dom}_*")))
        self.aux = _abrir(aux[0]) if aux else None
        self.tempos = _tempos(self.wrf)
        self.tempos_aux = _tempos(self.aux) if self.aux else []
        self.lat = np.array(self.wrf["XLAT"][0])
        self.lon = np.array(self.wrf["XLONG"][0])
        self.cosa = np.array(self.wrf["COSALPHA"][0])
        self.sina = np.array(self.wrf["SINALPHA"][0])
        self.dx = float(self.wrf.DX)
        self.dy = float(self.wrf.DY)
        ny, nx = self.lat.shape
        self.mapfac_m = np.array(self.wrf["MAPFAC_M"][0]) if "MAPFAC_M" in self.wrf.variables else np.ones((ny, nx))
        self.mapfac_u = np.array(self.wrf["MAPFAC_U"][0]) if "MAPFAC_U" in self.wrf.variables else np.ones((ny, nx + 1))
        self.mapfac_v = np.array(self.wrf["MAPFAC_V"][0]) if "MAPFAC_V" in self.wrf.variables else np.ones((ny + 1, nx))

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
        r = np.array(w["QVAPOR"][i])  # razão de mistura de vapor (kg/kg de ar seco)
        T = temperatura_wrf(np.array(w["T"][i]), r, P)
        qv = r / (1.0 + r)           # umidade específica, para diagnósticos que a exigirem
        zs = (np.array(w["PH"][i]) + np.array(w["PHB"][i])) / G_WRF
        zm = _mass(zs, 0)
        agl = zm - zs[0][None]
        U_grade = _mass(np.array(w["U"][i]), 2)
        V_grade = _mass(np.array(w["V"][i]), 1)
        U, V = self.rot(U_grade, V_grade)
        Wm = _mass(np.array(w["W"][i]), 0)
        refl = np.array(w["REFL_10CM"][i])
        u10, v10 = self.rot(np.array(w["U10"][i]), np.array(w["V10"][i]))
        nwp = {}
        for nome in ("WSPD10MAX", "W_UP_MAX", "W_DN_MAX", "W_MEAN", "GRPL_MAX", "HAIL_MAX2D", "UP_HELI_MAX"):
            if nome in w.variables:
                nwp[nome] = np.asarray(np.ma.filled(w[nome][i], np.nan), dtype=float)
        return dict(p=P, T=T, r=r, q=qv, zagl=agl, zasl=zm, u=U, v=V,
                    ugrid=U_grade, vgrid=V_grade, w=Wm, refl3d=refl, u10=u10, v10=v10, nwp=nwp,
                    t2=np.array(w["T2"][i]), q2=np.array(w["Q2"][i]), psfc=np.array(w["PSFC"][i]),
                    chuva=np.array(w["RAINC"][i]) + np.array(w["RAINNC"][i]),
                    neve=np.array(w["SNOWNC"][i]) if "SNOWNC" in w.variables else np.zeros_like(P[0]))

    # ------------------------------------------------------------ UH 2-5 km (extremos na última hora)
    def uh_interval(self, quando):
        """UH = integral(w * zeta) dz entre 2 e 5 km AGL.

        Interpola U, V e W para alturas geométricas constantes antes da
        derivada horizontal; integra por trapézios (3000 m de camada).
        """
        if self.aux is None:
            return None
        ini = quando - timedelta(hours=1)
        idx = [k for k, tt in enumerate(self.tempos_aux) if ini <= tt <= quando]
        if not idx:
            return None
        a = self.aux
        alt = np.arange(2000.0, 5000.1, 250.0)
        melhor_min = None
        melhor_max = None
        amostras = []
        for k in idx:
            zs = (np.asarray(a["PH"][k], dtype=float) + np.asarray(a["PHB"][k], dtype=float)) / G_WRF
            agl = _mass(zs, 0) - zs[0][None]
            U = _mass(np.asarray(a["U"][k], dtype=float), 2)
            V = _mass(np.asarray(a["V"][k], dtype=float), 1)
            Wm = _mass(np.asarray(a["W"][k], dtype=float), 0)
            wz = t.perfil_agl(agl, Wm, alt)
            vort = t.vorticidade_em_altura_agl(
                agl, U, V, alt, self.mapfac_u, self.mapfac_v, self.mapfac_m, self.dx, self.dy
            )
            vort = uniform_filter(vort, size=(1, 3, 3))
            produto = np.maximum(wz, 0.0) * vort
            dz = np.diff(alt)[:, None, None]
            uh = np.sum(0.5 * (produto[1:] + produto[:-1]) * dz, axis=0)
            valido = np.all(np.isfinite(wz), axis=0) & np.all(np.isfinite(vort), axis=0)
            uh = np.where(valido, uh, np.nan)
            # Bordas do aninhamento são ausentes, não são UH fisicamente igual a zero.
            b = 6
            uh[:b, :] = np.nan
            uh[-b:, :] = np.nan
            uh[:, :b] = np.nan
            uh[:, -b:] = np.nan
            melhor_min = uh.copy() if melhor_min is None else np.fmin(melhor_min, uh)
            melhor_max = uh.copy() if melhor_max is None else np.fmax(melhor_max, uh)
            finitos = uh[np.isfinite(uh)]
            amostras.append({
                "utc": self.tempos_aux[k].strftime("%Y-%m-%dT%H:%M:%S"),
                "min_m2s2": float(np.min(finitos)) if finitos.size else None,
                "max_m2s2": float(np.max(finitos)) if finitos.size else None,
            })
        return {
            "min": melhor_min,
            "max": melhor_max,
            "n_samples": len(idx),
            "sample_times": [self.tempos_aux[k].strftime("%Y-%m-%dT%H:%M:%S") for k in idx],
            "samples": amostras,
            "layer_m_agl": [2000.0, 5000.0],
            "integration": "trapezoidal",
        }

    def uh_min(self, quando):
        """Compatibilidade com o mapa: UH ciclônica mínima na última hora."""
        resultado = self.uh_interval(quando)
        return None if resultado is None else resultado["min"]


def umidade_relativa(T, r, p):
    """UR (%) a partir da razão de mistura r (kg/kg)."""
    e = r * p / (0.622 + r)
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
    out["td"] = t.dewpoint(est["psfc"], est["q2"]) - 273.15  # Q2 do WRF é razão de mistura
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
    out["srh01"] = t.srh(Ua, Va, ALT, lm, 0.0, 1000.0)
    out["srh03"] = t.srh(Ua, Va, ALT, lm, 0.0, 3000.0)
    # SCP de camadas fixas: distinto do SCP efetivo calculado nas sondagens.
    # BRN shear = 1/2 do quadrado da diferença entre o vento médio 0-500 m
    # e o vento médio 0.5-6 km ponderado pela densidade.
    rho = est["p"] / (t.RD * est["T"])
    rho_alt = t.perfil_agl(zc, rho, ALT)
    baixo = ALT <= 500.0
    medio = (ALT > 500.0) & (ALT <= 6000.0)
    rho_m = np.maximum(rho_alt[medio], 1e-6)
    u_baixo, v_baixo = Ua[baixo].mean(axis=0), Va[baixo].mean(axis=0)
    u_medio = np.sum(Ua[medio] * rho_m, axis=0) / np.sum(rho_m, axis=0)
    v_medio = np.sum(Va[medio] * rho_m, axis=0) / np.sum(rho_m, axis=0)
    out["brnsh"] = 0.5 * ((u_medio - u_baixo) ** 2 + (v_medio - v_baixo) ** 2)
    out["sc"] = (out["mu"] / 1000.0) * (np.maximum(-out["srh03"], 0.0) / 150.0) * (out["brnsh"] / 40.0)
    # Vorticidade relativa em 850 hPa (10^-5 s^-1), sem extrapolar abaixo do solo.
    out["vo"] = t.vorticidade_em_pressao(
        est["p"], est["ugrid"], est["vgrid"], 85000.0,
        S.mapfac_u, S.mapfac_v, S.mapfac_m, S.dx, S.dy, psfc=est["psfc"]
    ) * 1e5
    # Diagnósticos NWP opcionais do WRF 4.7.1.
    nwp = est.get("nwp", {})
    if "WSPD10MAX" in nwp:
        out["gust"] = np.maximum(nwp["WSPD10MAX"], 0.0) * 1.943844
    if "W_UP_MAX" in nwp:
        out["wu"] = np.maximum(nwp["W_UP_MAX"], 0.0)
    if "W_DN_MAX" in nwp:
        out["wd"] = np.maximum(-nwp["W_DN_MAX"], 0.0)
    if "W_MEAN" in nwp:
        out["wm"] = nwp["W_MEAN"]
    if "GRPL_MAX" in nwp:
        out["gr"] = np.maximum(nwp["GRPL_MAX"], 0.0)
    if "HAIL_MAX2D" in nwp:
        out["hail"] = np.maximum(nwp["HAIL_MAX2D"], 0.0) * 1000.0
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
