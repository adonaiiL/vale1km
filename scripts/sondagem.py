"""Vale1Km: sondagem (Skew-T, hodógrafa, perfis e tabela) no layout de referência (2240 x 1650)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib import patheffects as pe

import dominio as D
import termo as t
from mapas import RF

W, H = 2240, 1650
KT = 1.943844
P0, PTOP, KSKEW = 1022.0, 100.0, 26.7
XMIN, XMAX = -50.0, 50.0


# ------------------------------------------------------------------ cálculo
def _vento_agl(col, h):
    z = np.concatenate([[10.0], col["zagl"][col["zagl"] > 10.0]])
    u = np.concatenate([[col["u10"]], col["u"][col["zagl"] > 10.0]])
    v = np.concatenate([[col["v10"]], col["v"][col["zagl"] > 10.0]])
    return np.interp(h, z, u), np.interp(h, z, v)


def calcular(col):
    """Todos os índices e perfis usados na figura. Vento em m/s; alturas em m AGL."""
    p, T, r, z = col["p"], col["T"], col["r"], col["zagl"]
    pe, Te, re, ze = p[:, None], T[:, None], r[:, None], z[:, None]
    c = {}
    par = {}
    for tipo in ("SB", "ML", "MU"):
        p0, T0, r0 = t.parcelas(pe, Te, re, ze, tipo)
        o = t.cape_cin(pe, Te, re, ze, p0, T0, r0, dp=250.0)
        par[tipo] = o
        cape = float(o["cape"][0])
        dep = (o["el_z"][0] - o["lfc_z"][0]) if np.isfinite(o["el_z"][0]) and np.isfinite(o["lfc_z"][0]) else np.nan
        c[tipo] = dict(cape=cape, cin=float(o["cin"][0]), lcl=float(o["lcl_z"][0]), lfc=float(o["lfc_z"][0]),
                       el=float(o["el_z"][0]), ncape=(cape / dep if dep and dep > 0 else np.nan),
                       c03=t.area_pos(o, max(0, o["lfc_z"][0] if np.isfinite(o["lfc_z"][0]) else 1e9), 3000.0),
                       c06=t.area_pos(o, max(0, o["lfc_z"][0] if np.isfinite(o["lfc_z"][0]) else 1e9), 6000.0))
    Tc = T - 273.15
    z10, z30 = t.z_da_temperatura(Tc, z, -10.0), t.z_da_temperatura(Tc, z, -30.0)
    for tipo in par:
        c[tipo]["hgz"] = t.area_pos(par[tipo], z10, z30) if np.isfinite(z10) and np.isfinite(z30) else 0.0
    c["par"] = par
    # vento em grade regular
    h = np.arange(0.0, 14001.0, 100.0)
    u, v = _vento_agl(col, h)
    c["h"], c["u"], c["v"] = h, u, v
    h6 = h <= 6000.0
    (um, vm), rm, lm, (sdu, sdv) = t.bunkers(u[h6][:, None], v[h6][:, None], h[h6])
    c["mean"] = (float(um[0]), float(vm[0]))
    c["rm"] = (float(rm[0][0]), float(rm[1][0]))
    c["lm"] = (float(lm[0][0]), float(lm[1][0]))
    cm = c["lm"]  # hemisfério Sul: tempestade ciclônica = left-mover
    sr = lambda a, b: float(t.srh(u[:, None], v[:, None], h, cm, a, b)[0])
    c["srh05"], c["srh1"], c["srh3"] = sr(0, 500), sr(0, 1000), sr(0, 3000)
    bw = lambda a, b: float(np.hypot(*[float(x[0]) for x in t.shear_vec(u[:, None], v[:, None], h, a, b)]))
    c["bwd6"], c["bwd3"], c["bwd1"] = bw(0, 6000), bw(0, 3000), bw(0, 1000)
    # camada efetiva de entrada
    ks = [k for k in range(len(z)) if z[k] <= 3000.0]
    N = len(ks)
    rep = lambda a: np.repeat(a[:, None], N, axis=1)
    oe = t.cape_cin(rep(p), rep(T), rep(r), rep(z), p[ks], T[ks], r[ks], dp=250.0)
    ok = (oe["cape"] >= 100.0) & (oe["cin"] >= -250.0)
    base = top = None
    if ok.any():
        i0 = int(ok.argmax())
        i1 = i0
        while i1 + 1 < N and ok[i1 + 1]:
            i1 += 1
        base, top = float(z[ks[i0]]), float(z[ks[i1]])
        c["eil_k"] = ks[i0]
    c["eil"] = (base, top)
    if base is not None:
        el_mu = c["MU"]["el"] if np.isfinite(c["MU"]["el"]) else 12000.0
        zt = base + 0.5 * max(el_mu - base, 0.0)
        c["bwd_eff"] = float(np.hypot(*[float(x[0]) for x in t.shear_vec(u[:, None], v[:, None], h, base, zt)]))
        c["srh_eff"] = sr(base, top)
        c["eil_depth"] = top - base
        ke = c["eil_k"]  # parcela efetiva: a do nível de base da camada
        c["par_eff"] = t.cape_cin(pe, Te, re, ze, p[[ke]], T[[ke]], r[[ke]], dp=250.0)
    else:
        c["bwd_eff"], c["srh_eff"], c["eil_depth"], c["par_eff"] = np.nan, np.nan, np.nan, None
    lcl_ml = c["ML"]["lcl"]
    el_ml = c["ML"]["el"]
    c["bwd_cloud"] = (float(np.hypot(*[float(x[0]) for x in t.shear_vec(u[:, None], v[:, None], h, lcl_ml, el_ml)]))
                      if np.isfinite(el_ml) and el_ml > lcl_ml else np.nan)
    # taxas de variação
    zi = lambda pp: float(np.interp(-np.log(pp), -np.log(p), z))
    Ti = lambda pp: float(np.interp(-np.log(pp), -np.log(p), Tc))
    zz = lambda a: float(np.interp(a, z, Tc))
    c["g75"] = (Ti(70000.0) - Ti(50000.0)) / ((zi(50000.0) - zi(70000.0)) / 1000.0)
    c["g85"] = (Ti(85000.0) - Ti(50000.0)) / ((zi(50000.0) - zi(85000.0)) / 1000.0)
    c["g03"] = (zz(0.0) - zz(3000.0)) / 3.0
    c["g36"] = (zz(3000.0) - zz(6000.0)) / 3.0
    c["gmax"] = max((zz(a) - zz(a + 2000.0)) / 2.0 for a in range(0, 5001, 250))
    # compostos
    mu = c["MU"]; ml = c["ML"]; sb = c["SB"]
    sh6 = c["bwd6"]
    c["scp"] = np.nan
    if base is not None:
        ebwd = c["bwd_eff"]
        eb = 0.0 if ebwd < 10 else (1.0 if ebwd >= 20 else ebwd / 20.0)
        cint = 1.0 if mu["cin"] > -40 else -40.0 / mu["cin"]
        c["scp"] = (mu["cape"] / 1000.0) * (-c["srh_eff"] / 50.0) * eb * cint
        lclt = 1.0 if ml["lcl"] < 1000 else (0.0 if ml["lcl"] > 2000 else (2000.0 - ml["lcl"]) / 1000.0)
        ebs = 0.0 if ebwd < 12.5 else (1.5 if ebwd > 30 else ebwd / 20.0)
        cinm = 1.0 if ml["cin"] > -50 else (0.0 if ml["cin"] < -200 else (200.0 + ml["cin"]) / 150.0)
        c["stp_cin"] = (ml["cape"] / 1500.0) * lclt * (-c["srh_eff"] / 150.0) * ebs * cinm
    else:
        c["stp_cin"] = np.nan
    lcls = 1.0 if sb["lcl"] < 1000 else (0.0 if sb["lcl"] > 2000 else (2000.0 - sb["lcl"]) / 1000.0)
    bs = 0.0 if sh6 < 12.5 else (1.5 if sh6 > 30 else sh6 / 20.0)
    c["stp_fix"] = (sb["cape"] / 1500.0) * lcls * (-c["srh1"] / 150.0) * bs
    k_mu = np.argmax(t.theta_e(pe[:, 0][:12], Te[:, 0][:12], re[:, 0][:12]))
    mumr = float(np.clip(r[k_mu] * 1000.0, 11.0, 13.6))
    t500 = min(Ti(50000.0), -5.5)
    frz = t.z_da_temperatura(Tc, z, 0.0)
    ship = mu["cape"] * mumr * c["g75"] * (-t500) * float(np.clip(sh6, 7, 27)) / 42e6
    if mu["cape"] < 1300: ship *= mu["cape"] / 1300.0
    if c["g75"] < 5.8: ship *= c["g75"] / 5.8
    if np.isfinite(frz) and frz < 2400: ship *= frz / 2400.0
    c["ship"] = ship
    c["dcape"] = t.dcape(p, T, r, z)
    q = r / (1 + r)
    c["pw"] = float(np.sum(0.5 * (q[1:] + q[:-1]) * -np.diff(p)) / t.G)
    c["frz"] = float(frz)
    # vorticidade horizontal e fluxo relativo à tempestade
    du, dv = np.gradient(u, h), np.gradient(v, h)
    wx, wy = -dv, du
    sru, srv = u - cm[0], v - cm[1]
    spd = np.maximum(np.hypot(sru, srv), 0.5)
    ws = (wx * sru + wy * srv) / spd
    wc = (wx * -srv + wy * sru) / spd
    c["ws"], c["wc"], c["wh"], c["srspd"] = ws, wc, np.hypot(wx, wy), np.hypot(sru, srv)
    c["ws05"] = float(ws[h <= 500].mean())
    # Corfidi
    m = (p >= 30000.0) & (p <= 85000.0)
    ucl, vcl = col["u"][m].mean(), col["v"][m].mean()
    ull, vll = u[h <= 1500].mean(), v[h <= 1500].mean()
    up = (ucl - ull, vcl - vll)
    c["cup"] = up                              # Corfidi upshear: Vcl - Vllj
    c["cdn"] = (ucl + up[0], vcl + up[1])      # Corfidi downshear: Vcl + Vup
    return c


# ------------------------------------------------------------------ figura
def _x(Tc, p):
    return Tc + KSKEW * np.log(P0 / p)


def _ang(u, v):
    return (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0


def _fmt(v, f="{:.0f}", suf=""):
    if v is None or not np.isfinite(v):
        return "—"
    if f == "{:.0f}" and abs(v) < 0.5:
        v = 0.0
    return f.format(v) + suf


def figura(col, c, inset):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor="white")
    fx = lambda x0, y0, x1, y1: [x0 / W, 1 - y1 / H, (x1 - x0) / W, (y1 - y0) / H]
    p, T, r, z = col["p"], col["T"], col["r"], col["zagl"]
    Td = t.dewpoint(p, r)
    Tv = t.tvirt(T, r)
    Tw = np.array([float(t.bulbo_umido(np.array(a), np.array(b), np.array(d))) for a, b, d in zip(p, T, r)])
    ph = p / 100.0
    ptxt = f"{col['letra']} ({col['nome']}) | LON: {col['lon']:.2f} | LAT: {col['lat']:.2f}"
    fig.text(78 / W, 1 - 27 / H, ptxt, fontsize=18, fontweight="bold", va="center")
    fig.text(78 / W, 1 - 51 / H, f"WRF {D.NOME} 1 km", fontsize=18, fontweight="bold", va="center")
    fig.text(2216 / W, 1 - 27 / H, f"Ini: {col['init']:%Y-%m-%d %H}:00:00 UTC", fontsize=18, fontweight="bold", ha="right", va="center")
    brt = (col["val"].hour - 3) % 24
    fig.text(2216 / W, 1 - 51 / H, f"Val: {col['val']:%Y-%m-%d %H}:00:00 UTC ({brt:02d}:00 Brasília)", fontsize=18, fontweight="bold", ha="right", va="center")

    # ---------------- Skew-T
    ax = fig.add_axes(fx(88, 144, 1117, 1255))
    ax.set_yscale("log")
    ax.set_ylim(P0, PTOP)
    ax.set_xlim(XMIN, XMAX)
    pgrade = np.array([P0, PTOP])
    for Ti in range(-140, 51, 10):
        dest = Ti in (-10, -30)
        ax.plot(_x(Ti, pgrade), pgrade, color="#0000ff" if dest else "#e2e2e2", lw=1.8 if dest else 1.1,
                ls=(0, (6, 4)) if dest else "-", zorder=1)
    for pp in range(100, 1001, 100):
        ax.axhline(pp, color="#c8c8c8", lw=1.0, ls=(0, (4, 4)), zorder=1)
    pp = np.linspace(P0, PTOP, 60)
    for th in range(250, 480, 10):
        Tk = th * (pp / 1000.0) ** t.KAPPA - 273.15
        ax.plot(_x(Tk, pp), pp, color="#e9dfc4", lw=0.9, zorder=1)
    for w in (1, 2, 4, 7, 10, 16, 24, 32):
        pm = np.linspace(P0, 600, 20)
        e = w / 1000.0 * pm * 100 / (0.622 + w / 1000.0)
        Tm = 243.5 * np.log(e / 611.2) / (17.67 - np.log(e / 611.2))
        ax.plot(_x(Tm, pm), pm, color="#9ec79a", lw=0.9, ls=(0, (4, 4)), zorder=1)
        ax.text(_x(Tm[-1], pm[-1]), 597, str(w), fontsize=11, color="#4a9a4a", ha="center", va="top")
    # CAPE/CIN (ML)
    o = c["par"]["ML"]
    pg = o["pg"] / 100.0
    Tpx = _x(o["Tp"][:, 0] - 273.15, pg)
    Tenv = np.interp(-np.log(o["pg"]), -np.log(p), T) - 273.15
    Tvenv = o["Tve"][:, 0] - 273.15
    # parcela em T (não virtual) para o desenho: usa a virtual convertida
    rpa = np.interp(-np.log(o["pg"]), -np.log(p), r)
    Tp_plot = o["Tp"][:, 0]
    ax.plot(_x(Tp_plot - 273.15, pg), pg, color="black", lw=1.8, ls=(0, (6, 4)), zorder=5)
    zg = o["zg"][:, 0]
    pos = (o["b"][:, 0] > 0) & (zg <= 3000.0) & (zg >= (c["ML"]["lfc"] if np.isfinite(c["ML"]["lfc"]) else 1e9))
    neg = (o["b"][:, 0] < 0) & (zg <= (c["ML"]["lfc"] if np.isfinite(c["ML"]["lfc"]) else 0.0))
    ax.fill_betweenx(pg, _x(Tenv, pg), _x(Tp_plot - 273.15, pg), where=pos, color="#f9b8b8", alpha=.9, zorder=3, interpolate=True)
    ax.fill_betweenx(pg, _x(Tenv, pg), _x(Tp_plot - 273.15, pg), where=neg, color="#bdbcf5", alpha=.9, zorder=3, interpolate=True)
    if np.isfinite(z10 := t.z_da_temperatura(T - 273.15, z, -10.0)) and np.isfinite(z30 := t.z_da_temperatura(T - 273.15, z, -30.0)):
        hg = (o["b"][:, 0] > 0) & (zg >= z10) & (zg <= z30)
        ax.fill_betweenx(pg, _x(Tenv, pg), _x(Tp_plot - 273.15, pg), where=hg, color="#fff59d", alpha=.95, zorder=3, interpolate=True)
    if c.get("par_eff") is not None:
        oe = c["par_eff"]
        ax.plot(_x(oe["Tp"][:, 0] - 273.15, oe["pg"] / 100.0), oe["pg"] / 100.0, color="#f90", lw=1.8, ls=(0, (6, 4)), zorder=5)
    # parcela descendente (aproximação: pseudo-adiabática a partir do bulbo úmido do mínimo theta-e)
    sel = (p >= p[0] - 40000.0) & (p <= p[0] - 10000.0)
    if sel.any():
        k0 = np.where(sel)[0][t.theta_e(p[sel], T[sel], r[sel]).argmin()]
        pd = np.arange(p[k0], p[0] + 1, 500.0)
        Tdp = [float(t.bulbo_umido(np.array(p[k0]), np.array(T[k0]), np.array(r[k0])))]
        for a, b in zip(pd[:-1], pd[1:]):
            Tdp.append(float(t.pseudo_step(np.array(a), np.array(Tdp[-1]), np.array(b))))
        ax.plot(_x(np.array(Tdp) - 273.15, pd / 100.0), pd / 100.0, color="#c0c", lw=1.8, ls=(0, (6, 4)), zorder=5)
    ax.plot(_x(Tv - 273.15, ph), ph, color="#f88", lw=1.4, ls=(0, (4, 3)), zorder=6)
    ax.plot(_x(Tw - 273.15, ph), ph, color="#0bb", lw=1.4, zorder=6)
    ax.plot(_x(Td - 273.15, ph), ph, color="#008000", lw=3.0, zorder=7)
    ax.plot(_x(T - 273.15, ph), ph, color="#e00000", lw=3.0, zorder=8)
    # marcas
    zp = lambda zz: float(np.exp(np.interp(zz, z, np.log(ph))))
    def marca(zz, nome, cor, dx):
        if np.isfinite(zz):
            pm = zp(zz)
            ax.plot([dx - 14, dx + 6], [pm, pm], color=cor, lw=2.2, zorder=9)
            ax.text(dx + 10, pm, f"{nome} {zz:.0f}m", color=cor, fontsize=14, fontweight="bold", va="center", zorder=9)
    marca(c["ML"]["el"], "EL", "#8000c0", -30)
    marca(c["ML"]["lfc"], "LFC", "#b8860b", 18)
    marca(c["ML"]["lcl"], "LCL", "#007000", 24)
    b0, b1 = c["eil"]
    if b0 is not None:
        xb = -24
        ax.plot([xb, xb], [zp(b0), zp(b1)], color="#008b8b", lw=2.2, zorder=9)
        for q in (b0, b1):
            ax.plot([xb - 3, xb + 3], [zp(q), zp(q)], color="#008b8b", lw=2.2, zorder=9)
        ax.text(xb + 4, zp((b0 + b1) / 2), f"{b1 - b0:.0f} m", color="#008b8b", fontsize=14, fontweight="bold", va="center")
        ax.text(xb + 4, zp(b0) * 0.88, f"{c['srh_eff']:.0f} m²/s²", color="#008b8b", fontsize=13, fontweight="bold", va="center")
    for km, nm in ((1, "1 km"), (3, "3 km"), (6, "6 km"), (9, "9 km"), (12, "12 km"), (15, "15 km")):
        if km * 1000 <= z.max():
            ax.text(XMIN + 1.2, zp(km * 1000), nm, color="#d00000", fontsize=14, va="center", zorder=10)
    ax.set_xticks(range(-50, 51, 10)); ax.set_xticklabels([str(i).replace("-", "−") for i in range(-50, 51, 10)], fontsize=16)
    ax.set_yticks(range(100, 1001, 100)); ax.set_yticklabels([str(i) for i in range(100, 1001, 100)], fontsize=16)
    ax.minorticks_off()
    ax.set_xlabel("T [°C]", fontsize=16)
    ax.set_ylabel("P [hPa]", fontsize=16)
    for s in ax.spines.values():
        s.set_linewidth(1.6)
    # ômega
    ao = fig.add_axes(fx(88, 144, 263, 1255)); ao.patch.set_alpha(0)
    ao.set_yscale("log"); ao.set_ylim(P0, PTOP); ao.set_xlim(10, -10); ao.axis("off")
    ao.axvline(0, color="#e0e", lw=1.5, ls=(0, (6, 4)))
    ao.axvline(-10, color="#e0e", lw=1.0, ls=(0, (6, 4)), alpha=.5)
    rho = p / (t.RD * Tv)
    om = -rho * t.G * col["w"]
    for lev in range(150, 1001, 50):
        w_ = float(np.interp(-np.log(lev * 100.0), -np.log(p), om))
        ao.hlines(lev, 0, np.clip(w_, -10, 10), colors="#e00000" if w_ < 0 else "#1e90ff", lw=2.2)
    fig.text(100 / W, 1 - 138 / H, "+10", color="#1e90ff", fontsize=11, va="center")
    fig.text(146 / W, 1 - 138 / H, "OMEGA", color="#e0e", fontsize=13, fontweight="bold", va="center")
    fig.text(240 / W, 1 - 138 / H, "−10", color="#e0e", fontsize=11, va="center")
    # legenda
    hl = [Rectangle((0, 0), 1, 1, fc="#f9b8b8"), Rectangle((0, 0), 1, 1, fc="#fff59d"), Rectangle((0, 0), 1, 1, fc="#bdbcf5"),
          Line2D([], [], color="#e00000", lw=3), Line2D([], [], color="#008000", lw=3), Line2D([], [], color="#f88", lw=1.5, ls=(0, (4, 3))),
          Line2D([], [], color="#0bb", lw=1.5), Line2D([], [], color="#c0c", lw=1.8, ls=(0, (6, 4))),
          Line2D([], [], color="black", lw=1.8, ls=(0, (6, 4))), Line2D([], [], color="#f90", lw=1.8, ls=(0, (6, 4)))]
    nomes = ["CAPE 0-3 km (ML)", "CAPE HGZ (-10 a -30 °C)", "CIN (ML)", "Temperatura", "Ponto de orvalho", "Temperatura Virtual",
             "Bulbo Úmido", "Parcela Descendente", "Parcela ML", "Parcela Efetiva (eCAPE)"]
    leg = ax.legend(hl, nomes, loc="upper right", fontsize=11.5, framealpha=.95, borderpad=.5, labelspacing=.35, handlelength=2.0)
    leg.set_zorder(30)
    # barbelas
    ab = fig.add_axes(fx(1120, 144, 1225, 1255)); ab.patch.set_alpha(0)
    ab.set_yscale("log"); ab.set_ylim(P0, PTOP); ab.set_xlim(0, 1); ab.axis("off")
    pl = np.array([1000, 950, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300, 250, 200, 150, 120])
    pl = pl[(pl * 100.0 <= p[0]) & (pl * 100.0 >= p[-1])]
    ub = np.interp(-np.log(pl * 100.0), -np.log(p), col["u"]) * KT
    vb = np.interp(-np.log(pl * 100.0), -np.log(p), col["v"]) * KT
    ab.barbs(np.full(pl.size, 0.5), pl, ub, vb, length=7.5, linewidth=1.4)

    # ---------------- mini-mapa de refletividade máxima
    fig.patches.append(Rectangle((785 / W, 1 - 650 / H), 325 / W, 266 / H, transform=fig.transFigure, fc="white", ec="#999999", lw=1.2, zorder=20))
    fig.text(947 / W, 1 - 400 / H, f"MAX dBZ ({inset['max']:.0f})", fontsize=11.5, fontweight="bold", ha="center", va="center", zorder=21)
    am = fig.add_axes(fx(797, 410, 1098, 636), zorder=22)
    am.contourf(inset["lon"], inset["lat"], np.ma.masked_invalid(inset["refl"]), levels=list(range(5, 80, 5)),
                colors=RF, extend="max")
    for ref, aneis in inset["mun"].items():
        am.add_collection(LineCollection(aneis, colors="black" if ref in D.MUNICIPIOS else "#777", linewidths=1.0))
    am.plot([col["lon"]], [col["lat"]], "o", ms=7, color="black", zorder=9)
    am.set_xlim(inset["ext"][0], inset["ext"][1]); am.set_ylim(inset["ext"][2], inset["ext"][3])
    am.set_xticks([]); am.set_yticks([])

    # ---------------- hodógrafa
    ah = fig.add_axes(fx(1383, 144, 2208, 970), zorder=5)
    allp = [(0, 0), c["rm"], c["lm"], c["mean"]]
    pts = np.array(allp) * KT
    pts = np.vstack([pts, np.column_stack([c["u"][c["h"] <= 12000], c["v"][c["h"] <= 12000]]) * KT])
    cx, cy = (pts[:, 0].min() + pts[:, 0].max()) / 2, (pts[:, 1].min() + pts[:, 1].max()) / 2
    cx, cy = float(np.clip(cx, -15, 45)), float(np.clip(cy, -20, 25))
    ah.set_xlim(cx - 60, cx + 60); ah.set_ylim(cy - 60, cy + 60)
    ah.set_aspect("equal")
    ah.axhline(0, color="#bbbbbb", lw=1); ah.axvline(0, color="#bbbbbb", lw=1)
    th = np.linspace(0, 2 * np.pi, 200)
    for rr in range(10, 130, 10):
        ah.plot(rr * np.cos(th), rr * np.sin(th), color="#cccccc", lw=1.0, zorder=1)
        ah.text(rr + 1.2, 1.5, str(rr), fontsize=12, fontweight="bold", color="#b0b0b0", zorder=2)
    ah.set_xticks([]); ah.set_yticks([])
    # fluxo relativo (setas lavanda): do LM aos pontos do hodógrafa em 0.5, 1, 2, 3 km
    cmv = plt.get_cmap("PuBu_r")
    lm = (c["lm"][0] * KT, c["lm"][1] * KT)
    for zz in (500, 1000, 1500, 2000, 2500, 3000):
        i = int(zz / 100)
        wv = float(np.clip(c["ws"][i], -0.05, 0.0))
        col_ = cmv(1.0 - abs(wv) / 0.05 * 0.85)
        ah.annotate("", xy=(c["u"][i] * KT, c["v"][i] * KT), xytext=lm, arrowprops=dict(arrowstyle="-|>", color=col_, lw=2.2), zorder=3)
    # curva por altura
    faixas = [(0, 3000, "#dc143c"), (3000, 6000, "#ff8c00"), (6000, 9000, "#f5c800"), (9000, 14000, "#2e8b2e")]
    for a, b, cor in faixas:
        s_ = (c["h"] >= a) & (c["h"] <= b)
        ah.plot(c["u"][s_] * KT, c["v"][s_] * KT, color=cor, lw=4.2, zorder=6, solid_capstyle="round")
    for km in (0.5, 1, 3, 6, 9, 12):
        i = int(km * 10)
        if i < c["h"].size:
            ah.plot([c["u"][i] * KT], [c["v"][i] * KT], "o", mfc="white", mec="black", ms=7, zorder=8)
            ah.text(c["u"][i] * KT + 1.0, c["v"][i] * KT - 2.5, f"{km:g}", fontsize=15, fontweight="bold", zorder=9, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    for (u_, v_), cor, nm, mk in ((c["lm"], "#ff0000", "lm", "o"), (c["rm"], "#0000ff", "rm", "o")):
        ah.plot([u_ * KT], [v_ * KT], mk, mfc=cor, mec="black", ms=11, zorder=10)
        ah.text(u_ * KT + 2, v_ * KT - 4, f"{np.hypot(u_, v_) * KT:.0f}/{_ang(u_, v_):.0f}", fontsize=15, fontweight="bold", zorder=10)
    um, vm = c["mean"]
    ah.plot([um * KT], [vm * KT], "s", mfc="#666666", mec="black", ms=9, zorder=10)
    ah.text(um * KT + 2, vm * KT - 4, f"{np.hypot(um, vm) * KT:.0f}/{_ang(um, vm):.0f}", fontsize=13, fontweight="bold", color="#666666", zorder=10)
    ah.plot([c["cup"][0] * KT], [c["cup"][1] * KT], "^", mfc="#064", mec="black", ms=9, zorder=10)
    ah.plot([c["cdn"][0] * KT], [c["cdn"][1] * KT], "v", mfc="#064", mec="black", ms=9, zorder=10)
    ah.text(c["cdn"][0] * KT + 2, c["cdn"][1] * KT + 2, f"{np.hypot(*c['cdn']) * KT:.0f}/{_ang(*c['cdn']):.0f}", fontsize=13, fontweight="bold", color="#064", zorder=10)
    ah.text(0.03, 0.955, D.NOME, transform=ah.transAxes, fontsize=16, fontweight="bold", va="top", zorder=12)
    hh = [Line2D([], [], marker="o", ls="", mfc="#ff0000", mec="black", ms=9), Line2D([], [], marker="o", ls="", mfc="#0000ff", mec="black", ms=9),
          Line2D([], [], marker="s", ls="", mfc="#666", mec="black", ms=8), Line2D([], [], marker="^", ls="", mfc="#064", mec="black", ms=8),
          Line2D([], [], marker="v", ls="", mfc="#064", mec="black", ms=8)]
    nh = ["left-mover (Bunkers)", "right-mover (Bunkers)", "mean wind 0-6 km", "Corfidi upshear", "Corfidi downshear"]
    lg2 = ah.legend(hh, nh, loc="upper right", fontsize=11.5, framealpha=.95, borderpad=.5, labelspacing=.35)
    lg2.set_zorder(30)
    for s in ah.spines.values():
        s.set_linewidth(1.6)
    cax = fig.add_axes(fx(1415, 903, 1695, 920), zorder=30)
    sm = plt.cm.ScalarMappable(cmap=cmv, norm=matplotlib.colors.Normalize(-0.05, 0.0))
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal"); cb.ax.tick_params(labelsize=9)
    fig.text(1415 / W, 1 - 957 / H, "0-3 km streamwise vorticity [s⁻¹]", fontsize=10)

    # ---------------- painéis de perfis
    ht = c["h"]
    # θ / θe
    a1 = fig.add_axes(fx(1368, 1013, 1612, 1255))
    th_ = T * (1e5 / p) ** t.KAPPA
    tee = t.theta_e(p, T, r)
    s6 = z <= 6000
    a1.plot(th_[s6], z[s6], color="#f39c12", lw=2.2, label="θ"); a1.plot(tee[s6], z[s6], color="#2e8b57", lw=2.2, label="θe")
    a1.set_ylim(0, 6000); a1.set_xlim(np.floor(th_[s6].min() / 5) * 5 - 5, np.ceil(tee[s6].max() / 5) * 5 + 5); a1.legend(fontsize=10, loc="upper left", framealpha=.9)
    a1.set_title("θ / θe  0-6 km", fontsize=12, fontweight="bold"); a1.set_xlabel("K", fontsize=12); a1.set_ylabel("m AGL", fontsize=12)
    a1.grid(alpha=.3); a1.tick_params(labelsize=10)
    a2 = fig.add_axes(fx(1675, 1013, 1915, 1255))
    s14 = ht <= 14000
    a2.plot(c["srspd"][s14] * KT, ht[s14], color="#483d8b", lw=2.2)
    a2.axvline(15, color="#777", lw=.8, ls=":"); a2.axvline(25, color="#777", lw=.8, ls=":")
    a2.set_ylim(0, 14000); a2.set_xlim(0, 50)
    a2.set_title("Storm-Relative Wind  0-14 km", fontsize=12, fontweight="bold"); a2.set_xlabel("SR wind [kt]", fontsize=12)
    a2.grid(alpha=.3); a2.tick_params(labelsize=10)
    a3 = fig.add_axes(fx(1975, 1013, 2210, 1255))
    s3 = ht <= 3000
    a3.plot(c["ws"][s3] * 100, ht[s3], color="#dc143c", lw=2.0, label="ωs")
    a3.plot(c["wc"][s3] * 100, ht[s3], color="#008b8b", lw=2.0, label="ωc")
    a3.plot(c["wh"][s3] * 100, ht[s3], color="#555", lw=1.6, ls=":", label="|ωh|")
    a3.set_ylim(0, 3000); a3.set_xlim(-1.5, 1.5); a3.axvline(0, color="#777", lw=.8, ls=":")
    a3.legend(fontsize=9, loc="upper right", ncol=3, framealpha=.9, columnspacing=.8, handlelength=1.2)
    a3.set_xlabel("vorticity [s⁻¹]  ×1e-2", fontsize=12); a3.set_ylabel("m AGL", fontsize=12); a3.grid(alpha=.3); a3.tick_params(labelsize=10)
    a3.set_title("streamwiseness", fontsize=11, color="#800080")

    # ---------------- tabela
    at = fig.add_axes(fx(75, 1360, 2218, 1648)); at.axis("off")
    at.add_patch(Rectangle((0, 0), 1, 1, transform=at.transAxes, fc="#eef3f8", ec="#cfd9e4", lw=1.2, zorder=0))
    mono = dict(family="DejaVu Sans Mono", fontsize=12.5)
    def cab(x, txt):
        at.text(x, .945, txt, transform=at.transAxes, ha="center", va="center", fontsize=15, fontweight="bold")
    def lin(x0, x1, rows, y0=.80, dy=.082, cor="#a0522d"):
        for i, (nm, val) in enumerate(rows):
            y = y0 - i * dy
            at.text(x0, y, nm, transform=at.transAxes, va="center", color="#444", **mono)
            at.text(x1, y, val, transform=at.transAxes, va="center", ha="right", color=cor, fontweight="bold", **mono)
    X = lambda px: (px - 75) / (2218 - 75)
    cab(X(507), "PARCEL"); cab(X(1087), "LAPSE RATES"); cab(X(1382), "WIND SHEAR"); cab(X(1875), "KINEMATICS / COMPOSITES")
    for xc, nm in ((225, "MU"), (512, "ML"), (795, "SB")):
        at.text(X(xc), .865, nm, transform=at.transAxes, ha="center", va="center", fontsize=13, fontweight="bold")
    for (x0, x1, tipo) in ((100, 350, "MU"), (385, 640, "ML"), (672, 917, "SB")):
        d = c[tipo]
        lin(X(x0), X(x1), [("CAPE", _fmt(d["cape"], "{:.0f}", " J/kg")), ("ECAPE", "—"), ("CIN", _fmt(d["cin"], "{:.0f}", " J/kg")),
                           ("LCL", _fmt(d["lcl"], "{:.0f}", " m")), ("LFC", _fmt(d["lfc"], "{:.0f}", " m")), ("0-3 km", _fmt(d["c03"], "{:.0f}", " J/kg")),
                           ("0-6 km", _fmt(d["c06"], "{:.0f}", " J/kg")), ("HGZ", _fmt(d["hgz"], "{:.0f}", " J/kg")),
                           ("NCAPE", _fmt(d["ncape"], "{:.2f}", " m/s²"))], dy=.0775, y0=.79)
    lin(X(965), X(1210), [("Γ 700–500", _fmt(c["g75"], "{:.1f}", " °C/km")), ("Γ 850–500", _fmt(c["g85"], "{:.1f}", " °C/km")),
                          ("Γ 0–3 km", _fmt(c["g03"], "{:.1f}", " °C/km")), ("Γ 3–6 km", _fmt(c["g36"], "{:.1f}", " °C/km")),
                          ("Γ MAX", _fmt(c["gmax"], "{:.1f}", " °C/km"))], dy=.145, cor="#2e7d32", y0=.79)
    lin(X(1262), X(1502), [("BWD 0–6", _fmt(c["bwd6"] * KT, "{:.1f}", " kt")), ("BWD 0–3", _fmt(c["bwd3"] * KT, "{:.1f}", " kt")),
                           ("BWD 0–1", _fmt(c["bwd1"] * KT, "{:.1f}", " kt")), ("BWD EFF", _fmt(c["bwd_eff"] * KT, "{:.1f}", " kt")),
                           ("BWD CLOUD", _fmt(c["bwd_cloud"] * KT, "{:.1f}", " kt"))], dy=.145, cor="#c62828", y0=.79)
    lin(X(1562), X(1862), [("SRH 0–0.5", _fmt(c["srh05"], "{:.0f}", " m²/s²")), ("SRH 0–1", _fmt(c["srh1"], "{:.0f}", " m²/s²")),
                           ("SRH 0–3", _fmt(c["srh3"], "{:.0f}", " m²/s²")), ("SRH EFF", _fmt(c["srh_eff"], "{:.0f}", " m²/s²")),
                           ("ωs 0–0.5", _fmt(c["ws05"], "{:.4f}", " /s")), ("EIL DEPTH", _fmt(c["eil_depth"], "{:.0f}", " m"))],
        dy=.118, cor="#444", y0=.79)
    lin(X(1900), X(2200), [("SHIP", _fmt(c["ship"], "{:.2f}")), ("SCP", _fmt(c["scp"], "{:.2f}")), ("STP (CIN)", _fmt(c["stp_cin"], "{:.2f}")),
                           ("STP (FIX)", _fmt(c["stp_fix"], "{:.2f}")), ("DCAPE", _fmt(c["dcape"], "{:.0f}", " J/kg")),
                           ("PW", _fmt(c["pw"], "{:.1f}", " mm")), ("0°C HGT", _fmt(c["frz"], "{:.0f}", " m"))], dy=.1, cor="#444", y0=.79)
    for i, (nm, cor) in enumerate((("WEAK", "#cfd3d8"), ("NOTABLE", "#b9dcc4"), ("ELEVATED", "#ecd2b5"), ("HIGH", "#e8c5a0"), ("EXTREME", "#f2b8c0"))):
        x0 = 0.004 + i * 0.1985
        at.add_patch(Rectangle((x0, 0.03), 0.19, 0.012, transform=at.transAxes, fc=cor, ec="none"))
        at.text(x0 + 0.095, 0.012, nm, transform=at.transAxes, ha="center", va="center", fontsize=8, color="#889")
    return fig
