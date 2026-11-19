"""Vale1Km: termodinâmica e cinemática vetorizadas (numpy puro).

Convenções: pressão em Pa, temperatura em K, razão de mistura em kg/kg, alturas em m, vento em m/s.
Hemisfério Sul: a tempestade ciclônica é a left-mover de Bunkers; SRH e UH negativos = ciclônico.
"""
import numpy as np

G, RD, CP, LV, EPS = 9.80665, 287.04, 1005.7, 2.501e6, 0.62197
KAPPA = RD / CP


def vorticidade_relativa_grade(u, v, mapfac_u, mapfac_v, mapfac_m, dx, dy):
    """Vorticidade vertical relativa (s-1) com fatores de escala da grade WRF.

    u e v já devem estar destaggers para a grade de massa e relativos à grade.
    Esta aproximação métrica não reproduz os termos de inclinação eta/terreno
    usados pelo cálculo nativo de helicidade do WRF.
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    mfu = np.asarray(mapfac_u, dtype=float)
    mfv = np.asarray(mapfac_v, dtype=float)
    mfm = np.asarray(mapfac_m, dtype=float)
    if u.shape != v.shape or u.ndim < 2:
        raise ValueError("u e v devem ter a mesma forma (..., ny, nx)")
    ny, nx = u.shape[-2:]
    if mfu.shape != (ny, nx + 1) or mfv.shape != (ny + 1, nx) or mfm.shape != (ny, nx):
        raise ValueError("formas incompatíveis nos fatores MAPFAC_U/V/M")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx e dy devem ser positivos")
    mfu_m = 0.5 * (mfu[:, :-1] + mfu[:, 1:])
    mfv_m = 0.5 * (mfv[:-1, :] + mfv[1:, :])
    if np.any(~np.isfinite(mfu_m)) or np.any(mfu_m <= 0) or np.any(~np.isfinite(mfv_m)) or np.any(mfv_m <= 0):
        raise ValueError("MAPFAC_U/V inválidos")
    if np.any(~np.isfinite(mfm)) or np.any(mfm <= 0):
        raise ValueError("MAPFAC_M inválido")
    u_metric = u / mfu_m
    v_metric = v / mfv_m
    dvdx = np.gradient(v_metric, dx, axis=-1, edge_order=1)
    dudy = np.gradient(u_metric, dy, axis=-2, edge_order=1)
    return (mfm ** 2) * (dvdx - dudy)


def vorticidade_em_altura_agl(zagl, u, v, alturas, mapfac_u, mapfac_v, mapfac_m, dx, dy):
    """Vorticidade relativa em superfícies de altura AGL constante (s-1).

    Interpola primeiro os ventos grid-relative para alturas geométricas fixas
    e só então calcula o curl horizontal, reduzindo o erro de derivar em
    superfícies eta inclinadas pelo relevo.
    """
    z = np.asarray(zagl, dtype=float)
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    h = np.asarray(alturas, dtype=float)
    if z.shape != u.shape or z.shape != v.shape or z.ndim < 3:
        raise ValueError("zagl, u e v devem ter a mesma forma (nz, ny, nx)")
    if h.ndim != 1 or h.size < 2 or np.any(~np.isfinite(h)) or np.any(np.diff(h) <= 0):
        raise ValueError("alturas deve ser 1D, finita e estritamente crescente")
    uz = perfil_agl(z, u, h)
    vz = perfil_agl(z, v, h)
    vort = vorticidade_relativa_grade(uz, vz, mapfac_u, mapfac_v, mapfac_m, dx, dy)
    coluna_valida = np.all(np.isfinite(z), axis=0) & (np.max(z, axis=0) >= h[-1])
    return np.where(coluna_valida[None, ...], vort, np.nan)


def vorticidade_em_pressao(p, u, v, pressao_pa, mapfac_u, mapfac_v, mapfac_m, dx, dy, psfc=None):
    """Vorticidade relativa em uma isóbara (s-1), sem extrapolar sob o terreno.

    p está em Pa; u/v são grid-relative e já estão na grade de massa.
    """
    p = np.asarray(p, dtype=float)
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    alvo = float(pressao_pa)
    if p.shape != u.shape or p.shape != v.shape or p.ndim < 3:
        raise ValueError("p, u e v devem ter a mesma forma (nz, ny, nx)")
    if not np.isfinite(alvo) or alvo <= 0:
        raise ValueError("pressao_pa deve ser positiva e finita")
    u_nivel = interp_z(-p, u, -alvo)
    v_nivel = interp_z(-p, v, -alvo)
    pmax = np.nanmax(p, axis=0)
    pmin = np.nanmin(p, axis=0)
    valido = np.isfinite(pmax) & np.isfinite(pmin) & (pmax >= alvo) & (pmin <= alvo)
    if psfc is not None:
        superficie = np.asarray(psfc, dtype=float)
        if superficie.shape != p.shape[-2:]:
            raise ValueError("psfc deve ter forma (ny, nx)")
        valido &= np.isfinite(superficie) & (superficie >= alvo)
    vort = vorticidade_relativa_grade(u_nivel, v_nivel, mapfac_u, mapfac_v, mapfac_m, dx, dy)
    return np.where(valido, vort, np.nan)


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
    """Temperatura potencial equivalente, Bolton (1980) eq. 43 (r em kg/kg)."""
    Td = np.minimum(dewpoint(p, r), T)
    Tl = 1.0 / (1.0 / (Td - 56.0) + np.log(T / Td) / 800.0) + 56.0
    e = np.minimum(r * p / (EPS + r), 0.99 * p) / 100.0  # hPa
    rg = r * 1000.0
    th_dl = T * (1000.0 / (p / 100.0 - e)) ** 0.2854 * (T / Tl) ** (0.28e-3 * rg)
    return th_dl * np.exp((3.036e3 / Tl - 1.78) * 1e-3 * rg * (1.0 + 0.448e-3 * rg))


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

    Devolve dict com CAPE/CIN em J/kg e LCL/LFC/EL em m AGL.
    Colunas com parcela inicial inválida são retornadas como NaN.
    """
    p0 = np.asarray(p0, dtype=float)
    T0 = np.asarray(T0, dtype=float)
    r0 = np.asarray(r0, dtype=float)
    if p0.ndim != 1 or T0.shape != p0.shape or r0.shape != p0.shape:
        raise ValueError("p0, T0 e r0 devem ser vetores de mesma forma")
    if dp <= 0:
        raise ValueError("dp deve ser positivo")
    N = p0.size
    valido_inicio = (np.isfinite(p0) & (p0 > 9000.0) &
                     np.isfinite(T0) & (T0 > 150.0) & (T0 < 350.0) &
                     np.isfinite(r0) & (r0 >= 0.0))
    if not np.any(valido_inicio):
        raise ValueError("nenhuma parcela inicial válida para CAPE/CIN")
    pmax = float(np.max(p0[valido_inicio]))
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
        ativo = valido_inicio & (p <= p0 + 1e-6)
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
    # Altura AGL do LCL: usar apenas pontos válidos, sem substituir NaN por zero.
    zl = np.full(N, np.nan)
    xpress = -np.log(pg)
    for j in np.flatnonzero(valido_inicio & np.isfinite(plcl) & (plcl > 0.0)):
        bons = np.isfinite(zenv[:, j])
        if bons.sum() >= 2:
            xj = xpress[bons]
            alvo = -np.log(plcl[j])
            if xj[0] <= alvo <= xj[-1]:
                zl[j] = np.interp(alvo, xj, zenv[bons, j])

    # O índice da primeira camada de empuxo médio positivo define a integração
    # CAPE/CIN; o LFC reportado é refinado pelo cruzamento b=0 interpolado.
    lfc = np.where(tem, zm[np.maximum(idx, 0), cols], np.nan)
    for j in np.flatnonzero(valido_inicio & np.isfinite(zl) & np.isfinite(plcl)):
        bons = np.isfinite(b[:, j]) & np.isfinite(zenv[:, j])
        if bons.sum() < 2:
            continue
        xj = xpress[bons]
        bj = b[bons, j]
        zj = zenv[bons, j]
        alvo = -np.log(plcl[j])
        if alvo < xj[0] or alvo > xj[-1]:
            continue
        b_lcl = float(np.interp(alvo, xj, bj))
        z_lcl = float(zl[j])
        if b_lcl >= 0.0:
            lfc[j] = z_lcl
            continue
        k0 = int(np.searchsorted(xj, alvo, side="right"))
        b_ant, z_ant = b_lcl, z_lcl
        for k in range(k0, len(xj)):
            b_atual, z_atual = float(bj[k]), float(zj[k])
            if b_ant <= 0.0 < b_atual:
                frac = -b_ant / (b_atual - b_ant)
                lfc[j] = z_ant + frac * (z_atual - z_ant)
                break
            b_ant, z_ant = b_atual, z_atual

    # EL: última camada com empuxo positivo
    posA = ok & (bm > 0) & acima
    ult = np.where(posA.any(axis=0), bm.shape[0] - 1 - posA[::-1].argmax(axis=0), -1)
    el = np.where(ult >= 0, zm[np.maximum(ult, 0), cols], np.nan)
    cape = np.where(valido_inicio, cape, np.nan)
    cin = np.where(valido_inicio, cin, np.nan)
    el = np.where(valido_inicio, el, np.nan)
    return dict(cape=cape, cin=cin, lcl_z=zl, lfc_z=lfc, el_z=el,
                pg=pg, Tp=Tp, rp=rp, Tvp=Tvp, Tve=Tve, zg=zenv, b=b, plcl=plcl)


def parcela_mu(pe, Te, re, ze, profundidade_pa=30000.0):
    """Seleciona a parcela de maior theta-e nos 300 hPa inferiores (padrão MU).

    Exclui valores ausentes/não físicos e nunca permite que argmax escolha NaN.
    Colunas sem candidato válido retornam p/T/r NaN, índice -1 e valido=False.
    """
    pe = np.asarray(pe, dtype=float)
    Te = np.asarray(Te, dtype=float)
    re = np.asarray(re, dtype=float)
    ze = np.asarray(ze, dtype=float)
    if pe.ndim != 2 or pe.shape != Te.shape or pe.shape != re.shape or pe.shape != ze.shape:
        raise ValueError("pe, Te, re e ze devem ter a mesma forma (nz, N)")
    if profundidade_pa <= 0:
        raise ValueError("profundidade_pa deve ser positiva")
    ps = pe[0]
    camada = ((pe <= ps[None, :] + 1.0) &
              (pe >= (ps - profundidade_pa)[None, :]) &
              np.isfinite(pe) & (pe > 9000.0) &
              np.isfinite(Te) & (Te > 150.0) & (Te < 350.0) &
              np.isfinite(re) & (re >= 0.0) &
              np.isfinite(ze))
    te = theta_e(pe, Te, re)
    candidatos = camada & np.isfinite(te)
    score = np.where(candidatos, te, -np.inf)
    indice = np.argmax(score, axis=0)
    valido = np.any(candidatos, axis=0)
    colunas = np.arange(pe.shape[1])
    p0 = np.where(valido, pe[indice, colunas], np.nan)
    T0 = np.where(valido, Te[indice, colunas], np.nan)
    r0 = np.where(valido, re[indice, colunas], np.nan)
    indice = np.where(valido, indice, -1)
    return p0, T0, r0, indice, valido


def parcelas(pe, Te, re, ze, tipo):
    """Parcelas SB, ML (100 hPa médios) ou MU (máx. theta-e nos 300 hPa inferiores)."""
    ps = pe[0]
    if tipo == "SB":
        return pe[0].copy(), Te[0].copy(), re[0].copy()
    if tipo == "ML":
        m = pe >= (ps - 10000.0)[None, :]
        dp_nivel = np.abs(np.gradient(pe, axis=0))
        w = np.where(m & np.isfinite(pe) & np.isfinite(Te) & np.isfinite(re), dp_nivel, 0.0)
        th = Te * (1e5 / pe) ** KAPPA
        soma_w = np.sum(w, axis=0)
        thm = np.sum(np.where(w > 0, th * w, 0.0), axis=0) / np.where(soma_w > 0, soma_w, np.nan)
        rm = np.sum(np.where(w > 0, re * w, 0.0), axis=0) / np.where(soma_w > 0, soma_w, np.nan)
        return ps.copy(), thm * (ps / 1e5) ** KAPPA, rm
    p0, T0, r0, _indice, _valido = parcela_mu(pe, Te, re, ze)
    return p0, T0, r0


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
    """SRH meteorológica conforme a convenção de Markowski/MetPy.

    Soma (u_top-cx)*(v_bottom-cy) - (u_bottom-cx)*(v_top-cy).
    A SRH positiva é associada à rotação ciclônica para o right mover no HS Norte;
    no HS Sul, o left mover ciclônico tende a apresentar SRH negativa.
    """
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
