"""Vale1Km: termodinâmica e cinemática vetorizadas (numpy puro).

Convenções: pressão em Pa, temperatura em K, razão de mistura em kg/kg, alturas em m, vento em m/s.
Hemisfério Sul: a tempestade ciclônica é a left-mover de Bunkers; SRH e UH negativos = ciclônico.
"""
import numpy as np

G, RD, CP, LV, EPS = 9.80665, 287.04, 1005.7, 2.501e6, 0.62197
KAPPA = RD / CP


def esat(T):  # Pa, Bolton (1980)
    Tc = T - 273.15
    return 611.2 * np.exp(17.67 * Tc / (Tc + 243.5))


def rs(p, T):
    e = np.minimum(esat(T), 0.99 * p)
    return EPS * e / (p - e)


def tvirt(T, r):
    return T * (1.0 + r / EPS) / (1.0 + r)


def dewpoint(p, r):
    e = np.maximum(r * p / (EPS + r), 1e-3)
    ln = np.log(e / 611.2)
    return 243.5 * ln / (17.67 - ln) + 273.15


def theta_e(p, T, r):
    Td = dewpoint(p, r)
    Tl = 1.0 / (1.0 / (Td - 56.0) + np.log(T / Td) / 800.0) + 56.0
    th = T * (1e5 / p) ** (KAPPA * (1 - 0.28 * r))
    return th * np.exp((3036.0 / Tl - 0.00178) * r * 1000 * (1 + 0.448 * r * 1000) * 1e-3 * 1.0)


def lcl_p(p, T, r):
    Td = dewpoint(p, r)
    Tl = 1.0 / (1.0 / (np.minimum(Td, T) - 56.0) + np.log(T / np.minimum(Td, T)) / 800.0) + 56.0
    return p * (Tl / T) ** (1.0 / KAPPA), Tl


def _dTdp(p, T):
    r = rs(p, T)
    L = LV - 2370.0 * (T - 273.15)
    return (RD * T + L * r) / (p * (CP + (L * L * r * EPS) / (RD * T * T)))


def pseudo_step(p0, T0, p1):
    """Integra a adiabática pseudo-saturada de p0 a p1 (RK4, 1 passo)."""
    h = p1 - p0
    k1 = _dTdp(p0, T0)
    k2 = _dTdp(p0 + h / 2, T0 + h / 2 * k1)
    k3 = _dTdp(p0 + h / 2, T0 + h / 2 * k2)
    k4 = _dTdp(p1, T0 + h * k3)
    return T0 + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


def interp_col(pe, fe, pg):
    """pe, fe: (nz,N) com pe decrescente em k; pg: (M,) decrescente. Devolve (M,N), interpolação linear em ln p."""
    nz, N = pe.shape
    out = np.empty((pg.size, N))
    lg = np.log(pg)
    for j in range(N):
        x = -np.log(pe[:, j])
        out[:, j] = np.interp(-lg, x, fe[:, j], left=np.nan, right=np.nan)
    return out


def cape_cin(pe, Te, re, ze, p0, T0, r0, dp=500.0, topo=None):
    """Parcela de (p0,T0,r0) subindo através do ambiente (pe,Te,re,ze), todos (nz,N).

    Devolve dict com cape, cin (J/kg, cin<=0), lcl_z, lfc_z, el_z (m AGL) e o perfil da parcela.
    ze é altura AGL. p0,T0,r0 têm forma (N,)."""
    N = p0.size
    pmax = p0.max()
    pg = np.arange(pmax, 9000.0, -dp)
    Tenv = interp_col(pe, Te, pg)
    renv = interp_col(pe, re, pg)
    zenv = interp_col(pe, ze, pg)
    plcl, Tlcl = lcl_p(p0, T0, r0)
    Tp = np.full((pg.size, N), np.nan)
    rp = np.full((pg.size, N), np.nan)
    rr = np.minimum(r0, rs(p0, T0))
    sat = np.zeros(N, bool)
    Tcur = T0.copy()
    pprev = np.full(N, np.nan)
    for i, p in enumerate(pg):
        ativo = p <= p0 + 1e-6
        pp = np.where(ativo, p, p0)
        seco = ativo & (p >= plcl)
        Tseco = T0 * (pp / p0) ** KAPPA
        # a partir do LCL: sobe pseudo-adiabaticamente
        novo_sat = ativo & ~seco
        if i == 0:
            Tcur = np.where(ativo, Tseco, Tcur)
        else:
            # quem acabou de saturar parte da T no LCL (via passo seco ao LCL) e integra até p
            primeiro = novo_sat & ~sat
            Tstart = np.where(primeiro, Tlcl, Tcur)
            pstart = np.where(primeiro, plcl, pprev)
            Tmoist = pseudo_step(pstart, Tstart, pp)
            Tcur = np.where(novo_sat, Tmoist, np.where(ativo, Tseco, Tcur))
        sat |= novo_sat
        pprev = np.where(ativo, p, pprev)
        Tp[i] = np.where(ativo, Tcur, np.nan)
        rp[i] = np.where(novo_sat, rs(pp, Tcur), rr)
        rp[i] = np.where(ativo, rp[i], np.nan)
    Tvp = tvirt(Tp, rp)
    Tve = tvirt(Tenv, renv)
    b = G * (Tvp - Tve) / Tve
    dz = np.diff(zenv, axis=0)
    bm = 0.5 * (b[1:] + b[:-1])
    ok = np.isfinite(bm) & np.isfinite(dz)
    bmz = np.where(ok, bm * dz, 0.0)
    zm = 0.5 * (zenv[1:] + zenv[:-1])
    pm = 0.5 * (pg[1:, None] + pg[:-1, None]) * np.ones((1, N))
    pos = ok & (bm > 0) & (pm <= plcl[None, :] + 1.0)
    # LFC: primeira camada acima do LCL com empuxo positivo
    idx = np.where(pos.any(axis=0), pos.argmax(axis=0), -1)
    tem = idx >= 0
    cols = np.arange(N)
    abaixo = np.arange(bm.shape[0])[:, None] < idx[None, :]
    acima = np.arange(bm.shape[0])[:, None] >= idx[None, :]
    cape = np.where(tem, np.sum(np.where(acima, np.maximum(bmz, 0), 0.0), axis=0), 0.0)
    cin = np.where(tem, np.sum(np.where(abaixo, np.minimum(bmz, 0), 0.0), axis=0), 0.0)
    cin = np.maximum(cin, -1000.0)
    lfc = np.where(tem, zm[np.maximum(idx, 0), cols], np.nan)
    # EL: última camada com empuxo positivo
    posA = ok & (bm > 0) & acima
    ult = np.where(posA.any(axis=0), bm.shape[0] - 1 - posA[::-1].argmax(axis=0), -1)
    el = np.where(ult >= 0, zm[np.maximum(ult, 0), cols], np.nan)
    # altura do LCL por interpolação em ln p
    zl = np.empty(N)
    for j in range(N):
        zl[j] = np.interp(-np.log(plcl[j]), -np.log(pg), np.nan_to_num(zenv[:, j]))
    return dict(cape=cape, cin=cin, lcl_z=zl, lfc_z=lfc, el_z=el, pg=pg, Tp=Tp, Tve=Tve, zg=zenv, b=b, plcl=plcl)


def parcelas(pe, Te, re, ze, tipo):
    """Parcelas SB, ML (média dos 100 hPa mais baixos) ou MU (máx. theta-e nos 300 hPa mais baixos)."""
    ps = pe[0]
    if tipo == "SB":
        return pe[0].copy(), Te[0].copy(), re[0].copy()
    if tipo == "ML":
        m = pe >= (ps - 10000.0)[None, :]
        w = np.where(m, 1.0, 0.0)
        th = Te * (1e5 / pe) ** KAPPA
        thm = (th * w).sum(0) / w.sum(0)
        rm = (re * w).sum(0) / w.sum(0)
        return ps.copy(), thm * (ps / 1e5) ** KAPPA, rm
    te = theta_e(pe, Te, re)
    m = pe >= (ps - 30000.0)[None, :]
    te = np.where(m, te, -np.inf)
    k = te.argmax(axis=0)
    c = np.arange(pe.shape[1])
    return pe[k, c], Te[k, c], re[k, c]


# ------------------------------------------------------------------ cinemática
def interp_z(zagl, f, alvo):
    """zagl, f: (nz, ...) com z crescente; alvo escalar. Interpolação linear em z, vetorizada."""
    nz = zagl.shape[0]
    n = np.clip((zagl <= alvo).sum(axis=0) - 1, 0, nz - 2)
    z0 = np.take_along_axis(zagl, n[None], 0)[0]
    z1 = np.take_along_axis(zagl, (n + 1)[None], 0)[0]
    f0 = np.take_along_axis(f, n[None], 0)[0]
    f1 = np.take_along_axis(f, (n + 1)[None], 0)[0]
    w = np.clip((alvo - z0) / np.where(z1 - z0 == 0, 1, z1 - z0), 0, 1)
    return f0 * (1 - w) + f1 * w


def perfil_agl(zagl, f, alturas):
    return np.stack([interp_z(zagl, f, h) for h in alturas])


def bunkers(u, v, h):
    """u,v: (nh, ...) em alturas h (m AGL, de 0 a 6000, passo uniforme). Devolve (mean, RM, LM, shear)."""
    sel = h <= 6000.0
    um, vm = u[sel].mean(0), v[sel].mean(0)
    lo = h <= 500.0
    hi = h >= 5500.0
    du = u[hi].mean(0) - u[lo].mean(0)
    dv = v[hi].mean(0) - v[lo].mean(0)
    mod = np.maximum(np.hypot(du, dv), 1e-6)
    ex, ey = dv / mod, -du / mod  # perpendicular à direita do cisalhamento
    D = 7.5
    rm = (um + D * ex, vm + D * ey)
    lm = (um - D * ex, vm - D * ey)
    return (um, vm), rm, lm, (du, dv)


def srh(u, v, h, c, z0, z1):
    """SRH entre z0 e z1 (m) com movimento c=(cu,cv). Positivo para giro horário do hodógrafo."""
    sel = (h >= z0) & (h <= z1)
    uu, vv = u[sel] - c[0], v[sel] - c[1]
    return np.sum(uu[1:] * vv[:-1] - uu[:-1] * vv[1:], axis=0)


def shear_vec(u, v, h, z0, z1):
    a, b = np.argmin(abs(h - z0)), np.argmin(abs(h - z1))
    return u[b] - u[a], v[b] - v[a]


# ------------------------------------------------------------------ utilidades para uma coluna (sondagem)
def area_pos(o, z0, z1):
    """Área de empuxo positivo (J/kg) da parcela entre z0 e z1 (m AGL), de um resultado de cape_cin para 1 coluna."""
    b, zg = o["b"][:, 0], o["zg"][:, 0]
    ok = np.isfinite(b) & np.isfinite(zg)
    b, zg = b[ok], zg[ok]
    if b.size < 2:
        return 0.0
    bm, zm, dz = 0.5 * (b[1:] + b[:-1]), 0.5 * (zg[1:] + zg[:-1]), np.diff(zg)
    sel = (zm >= z0) & (zm <= z1) & (bm > 0)
    return float(np.sum(bm[sel] * dz[sel]))


def z_da_temperatura(Tc, z, alvo):
    """Primeira altura (de baixo para cima) em que a temperatura (°C) cruza 'alvo'. NaN se não cruza."""
    for i in range(len(Tc) - 1):
        a, b = Tc[i] - alvo, Tc[i + 1] - alvo
        if a == 0:
            return z[i]
        if a * b < 0:
            return z[i] + (z[i + 1] - z[i]) * a / (a - b)
    return np.nan


def bulbo_umido(p, T, r):
    """Temperatura de bulbo úmido: sobe seco até o LCL e desce pela pseudo-adiabática até p."""
    pl, Tl = lcl_p(p, T, r)
    return pseudo_step(pl, Tl, p)


def dcape(pe, Te, re, ze):
    """DCAPE (J/kg) para uma coluna (arrays 1D de baixo para cima)."""
    ps = pe[0]
    sel = (pe >= ps - 40000.0) & (pe <= ps - 10000.0)
    if not sel.any():
        return 0.0
    te = theta_e(pe[sel], Te[sel], re[sel])
    k0 = np.where(sel)[0][te.argmin()]
    p0, T0, r0 = pe[k0], Te[k0], re[k0]
    Tw = float(bulbo_umido(np.array(p0), np.array(T0), np.array(r0)))
    pg = np.arange(p0, ps + 250.0, 500.0)
    pg = np.append(pg[pg < ps], ps)
    Tp = [Tw]
    for a, b in zip(pg[:-1], pg[1:]):
        Tp.append(float(pseudo_step(np.array(a), np.array(Tp[-1]), np.array(b))))
    Tp = np.array(Tp)
    Ten = np.interp(-np.log(pg), -np.log(pe), Te)
    ren = np.interp(-np.log(pg), -np.log(pe), re)
    zen = np.interp(-np.log(pg), -np.log(pe), ze)
    Tvp, Tve = tvirt(Tp, rs(pg, Tp)), tvirt(Ten, ren)
    b = G * (Tvp - Tve) / Tve
    bm = 0.5 * (b[1:] + b[:-1])
    dz = -np.diff(zen)
    return float(np.sum(np.maximum(-bm, 0) * dz))
