"""Vale1Km: mapas no layout de referência (2295 x 1904 px): título, caixa do mapa e barra de cores com seta."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects as pe
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

import dominio as D

W, H = 2295, 1904
DPI = 100
HALO = [pe.withStroke(linewidth=5, foreground="white")]

RF = ['#87d7ff', '#00eaf0', '#00aaff', '#00ff00', '#00c800', '#009600', '#ffff00', '#e6c000',
      '#ff9000', '#ff0000', '#c80000', '#e066ff', '#c000f0', '#5a007d']
CAPE_C = ['#ffffcc', '#ffeda0', '#fed976', '#feb24c', '#fd8d3c', '#fc4e2a', '#e31a1c', '#bd0026', '#800026', '#4a0014']
PREC_C = ['#d9f0ff', '#a6dcff', '#5ab4f0', '#2c7bdc', '#1b4fb0', '#6a3fc0', '#9c27b0', '#c2185b', '#e53935', '#ff7043', '#ffb300', '#fff176']
GEADA_C = ['#4a148c', '#7b1fa2', '#1a237e', '#3f51b5', '#29b6f6', '#b2ebf2', '#f5f5f5']


def _cmap(nome, n):
    cm = plt.get_cmap(nome)
    return [matplotlib.colors.to_hex(cm(i / max(n - 1, 1))) for i in range(n)]


def lv(a, b, passo):
    return list(np.round(np.arange(a, b + passo / 2, passo), 6))


# chave: (rótulo, título, níveis, cores, extensão, unidade da barra, UH?)
PARAMS = {
    "rf": ("Refletividade", "Refletividade Composta [dBZ] | UH 2-5 km 1-hr [&lt;{u:.0f} m²/s²]", lv(5, 75, 5), RF, "max"),
    "ws": ("Ventos", "Vento a 10 m [kt] | barbelas", lv(0, 60, 5), _cmap("viridis", 12), "max"),
    "t2": ("Temperatura", "Temperatura a 2 m [°C]", lv(-5, 40, 2.5), _cmap("RdYlBu_r", 18), "both"),
    "rh": ("Umidade", "Umidade relativa a 2 m [%]", lv(0, 100, 10), _cmap("YlGnBu", 10), "neither"),
    "pr": ("Precip. acumulada", "Precipitação acumulada total [mm]", [0.1, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150], PREC_C, "max"),
    "td": ("Ponto de orvalho", "Ponto de orvalho a 2 m [°C]", lv(-5, 30, 2.5), _cmap("YlGnBu", 14), "both"),
    "fr": ("Geada", "Previsão de geada | Tmín 2 m desde o início [°C]", [-10, -3, -1, 1, 3, 5, 8, 12], GEADA_C, "neither"),
    "ml": ("MLCAPE", "MLCAPE [J/kg]", [0, 100, 250, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000], CAPE_C, "max"),
    "mu": ("MUCAPE", "MUCAPE [J/kg]", [0, 100, 250, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000], CAPE_C, "max"),
    "sc": ("SCP", "Supercell Composite Parameter (SCP, SRH 0-3 km, cisalhamento 0-6 km)", [0, 0.5, 1, 2, 4, 6, 8, 12, 16, 20, 30], CAPE_C, "max"),
    "vo": ("Vorticidade 850 hPa", "Vorticidade relativa 850 hPa [10⁻⁵ s⁻¹] (ciclônica &lt; 0)", lv(-60, 60, 10), _cmap("RdBu", 12), "both"),
    "sn": ("Neve acumulada", "Mosaico de neve acumulada", None, None, None),
    "sh": ("Cisalhamento", "Mosaico de cisalhamento do vento [kt]", None, None, None),
    "hd": ("Hodomap", "Hodomap 0-6 km | MUCAPE [J/kg] | Bunkers (LM vermelho, RM azul)", [0, 100, 250, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000], CAPE_C, "max"),
}


class Ctx:
    """Dados comuns a todos os mapas de um horário."""

    def __init__(self, lon, lat, init, val, mun, rod, uh=None):
        self.lon, self.lat, self.init, self.val, self.mun, self.rod, self.uh = lon, lat, init, val, mun, rod, uh
        c = 4
        self.ext = (lon[c:-c, c:-c].min(), lon[c:-c, c:-c].max(), lat[c:-c, c:-c].min(), lat[c:-c, c:-c].max())
        lat0 = np.radians((self.ext[2] + self.ext[3]) / 2)
        self.ratio = (self.ext[1] - self.ext[0]) * np.cos(lat0) / (self.ext[3] - self.ext[2])


def _t(s):
    return s.replace("&lt;", "<")


def figura(titulo, ctx, mosaico=False):
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor="white")
    fig.text(20 / W, 1 - 128 / H, _t(titulo), fontsize=23, ha="left", va="baseline")
    fig.text(20 / W, 1 - 172 / H, f"WRF {D.NOME} 1 km", fontsize=23, ha="left", va="baseline")
    brt = ctx.val.hour - 3 if ctx.val.hour >= 3 else ctx.val.hour + 21
    fig.text(2005 / W, 1 - 128 / H, f"Inic.: {ctx.init:%Y-%m-%d %H}:00:00 UTC", fontsize=23, ha="right", va="baseline")
    fig.text(2005 / W, 1 - 172 / H,
             f"Val.: {ctx.val:%Y-%m-%d %H}:00:00 UTC ({brt:02d}:00 Brasília)", fontsize=23, ha="right", va="baseline")
    mw = 1985
    mh = min(mw / ctx.ratio, 1648)
    ax = fig.add_axes([20 / W, 1 - (196 + mh) / H, mw / W, mh / H])
    return fig, ax


def moldura(ax, ctx):
    ax.set_xlim(ctx.ext[0], ctx.ext[1])
    ax.set_ylim(ctx.ext[2], ctx.ext[3])
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(2.5)


def handles_legenda(uh=False):
    h = []
    if uh:
        h.append(Line2D([], [], color="black", lw=2.4, label=f"UH 2-5 km 1-hr (< {D.UH_LIMIAR:.0f} m²/s²)"))
    h += [Line2D([], [], color="black", lw=3.0, label="Limite municipal (Blumenau e Pomerode)"),
          Line2D([], [], color="#6b6b6b", lw=1.2, label="Municípios vizinhos"),
          Line2D([], [], color="#b45309", lw=3.0, label="Rodovias (BR e SC)"),
          Line2D([], [], marker="o", ls="", mfc="#ffe600", mec="black", mew=2, ms=11,
                 label="A Adonai, F Fabrício, K Kelvin")]
    return h


def vetores(ax, ctx, legenda=False, rotulos=True, esc=1.0):
    mun_lw = []
    for cod, aneis in ctx.mun.items():
        dest = cod in D.MUNICIPIOS
        lc = LineCollection(aneis, colors="black" if dest else "#6b6b6b", linewidths=(3.0 if dest else 1.2) * max(esc, .6), zorder=6 if dest else 5)
        ax.add_collection(lc)
        if dest and rotulos:
            xs = np.array([p[0] for a in aneis for p in a]); ys = np.array([p[1] for a in aneis for p in a])
            cx, cy = np.clip(xs.mean(), ctx.ext[0] + .03, ctx.ext[1] - .03), np.clip(ys.mean(), ctx.ext[2] + .02, ctx.ext[3] - .02)
            ax.text(cx, cy, D.MUNICIPIOS[cod], fontsize=17, fontweight="bold", color="black", ha="center", zorder=7,
                    path_effects=HALO, alpha=.85)
    vistos = {}
    for ref, pts in ctx.rod:
        ax.add_collection(LineCollection([pts], colors="#b45309", linewidths=3.0 * max(esc, .6), zorder=7))
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        dentro = sum(ctx.ext[0] < x < ctx.ext[1] and ctx.ext[2] < y < ctx.ext[3] for x, y in pts)
        if rotulos and ref and dentro > vistos.get(ref, (0,))[0]:
            vistos[ref] = (dentro, pts[len(pts) // 2])
    for ref, (n, (x, y)) in vistos.items():
        if n >= 3 and ctx.ext[0] < x < ctx.ext[1] and ctx.ext[2] < y < ctx.ext[3]:
            ax.text(x, y, ref.split(";")[0], fontsize=13, color="#7c2d00", fontweight="bold", zorder=8, path_effects=HALO, ha="center")
    for k, (nome, la, lo) in D.PONTOS.items():
        ax.scatter([lo], [la], s=150 * esc ** 2, c="#ffe600", edgecolors="black", linewidths=2.2 * max(esc, .6), zorder=12)
        ax.text(lo + 0.006, la - 0.004, k, fontsize=26 * esc, fontweight="bold", color="black", zorder=13, path_effects=HALO)
    ax.text(0.985, 0.025, D.NOME, transform=ax.transAxes, fontsize=34 * esc, fontweight="bold", ha="right", va="bottom",
            color="black", path_effects=[pe.withStroke(linewidth=6, foreground="white")], zorder=14)
    if legenda:
        leg = ax.legend(handles=handles_legenda(uh=(legenda == 'uh')), loc="lower left", fontsize=17, framealpha=.94,
                        borderpad=.8, labelspacing=.6)
        leg.set_zorder(20)


def barra(fig, cs, levels, rot=None):
    cax = fig.add_axes([2118 / W, 44 / H, 82 / W, 1752 / H])
    cb = fig.colorbar(cs, cax=cax)
    ticks = levels if len(levels) <= 16 else levels[::2]
    cb.set_ticks(ticks)
    cb.ax.set_yticklabels([f"{t:g}" for t in ticks])
    cb.ax.tick_params(labelsize=21, length=8, width=1.5)
    cb.outline.set_linewidth(2.5)
    return cb


def _norm(levels, cores, ext):
    n = len(levels) - 1
    cm = ListedColormap(cores[:n])
    if ext in ("max", "both"):
        cm.set_over(cores[n] if len(cores) > n else cores[-1])
    if ext in ("min", "both"):
        cm.set_under(cores[0])
    return cm, BoundaryNorm(levels, cm.N)


def mapa_simples(chave, ctx, campo, barbs=None, dest=None):
    rot, tit, levels, cores, ext = PARAMS[chave]
    tit = tit.format(u=D.UH_LIMIAR) if "{u" in tit else tit
    fig, ax = figura(tit, ctx)
    moldura(ax, ctx)
    cm, nm = _norm(levels, cores, ext)
    cs = ax.contourf(ctx.lon, ctx.lat, np.ma.masked_invalid(campo), levels=levels, cmap=cm, norm=nm, extend=ext, zorder=2)
    barra(fig, cs, levels)
    if barbs is not None:
        u, v, s = barbs
        ax.barbs(ctx.lon[::s, ::s], ctx.lat[::s, ::s], u[::s, ::s], v[::s, ::s], length=6.5, linewidth=1.3, zorder=4,
                 sizes=dict(emptybarb=0.1))
    if chave == "rf" and ctx.uh is not None and np.nanmin(ctx.uh) <= D.UH_LIMIAR:
        ax.contour(ctx.lon, ctx.lat, np.ma.masked_invalid(ctx.uh), levels=[D.UH_LIMIAR], colors="k", linewidths=2.2, linestyles="solid", zorder=9)
    vetores(ax, ctx, legenda="uh" if chave == "rf" else True)
    return fig


def mosaico(chave, ctx, paineis, shape):
    """paineis: lista de (titulo, campo, levels, cores, ext, contorno_0C ou None). shape=(linhas, colunas)."""
    rot, tit, *_ = PARAMS[chave]
    fig, _ax = figura(tit, ctx, mosaico=True)
    _ax.remove()
    nl, nc = shape
    x0, y0, w, h = 20, 262, 2255, 1480
    gx, gy = 50, 125
    pw, ph = (w - gx * (nc - 1)) / nc, (h - gy * (nl - 1)) / nl
    ah = min(pw / ctx.ratio, ph - 95)
    aw = ah * ctx.ratio
    for i, (t, campo, levels, cores, ext, c0) in enumerate(paineis):
        r, c = divmod(i, nc)
        px = x0 + c * (pw + gx) + (pw - aw) / 2
        py = y0 + r * (ph + gy)
        ax = fig.add_axes([px / W, 1 - (py + ah) / H, aw / W, ah / H])
        moldura(ax, ctx)
        cm, nm = _norm(levels, cores, ext)
        cs = ax.contourf(ctx.lon, ctx.lat, np.ma.masked_invalid(campo), levels=levels, cmap=cm, norm=nm, extend=ext, zorder=2)
        if c0 is not None and np.nanmin(c0) < 0 < np.nanmax(c0):
            ax.contour(ctx.lon, ctx.lat, np.ma.masked_invalid(c0), levels=[0.0], colors="k", linewidths=2.0, linestyles="solid", zorder=8)
        ax.set_title(t, fontsize=20, loc="left", pad=10)
        cax = fig.add_axes([(px + aw * 0.04) / W, 1 - (py + ah + 62) / H, aw * 0.92 / W, 26 / H])
        cb = fig.colorbar(cs, cax=cax, orientation="horizontal")
        tk = levels if len(levels) <= 12 else levels[::2]
        cb.set_ticks(tk); cb.ax.set_xticklabels([f"{x:g}" for x in tk])
        cb.ax.tick_params(labelsize=15)
        vetores(ax, ctx, legenda=False, rotulos=False, esc=0.62)
    fig.legend(handles=handles_legenda(), loc="lower center", ncol=4, fontsize=17, frameon=True,
               bbox_to_anchor=(0.5, 0.004), framealpha=.95)
    return fig


def hodomap(ctx, mucape, alt, U, V, rm, lm, passo=8):
    rot, tit, levels, cores, ext = PARAMS["hd"]
    fig, ax = figura(tit, ctx)
    moldura(ax, ctx)
    cm, nm = _norm(levels, cores, ext)
    cs = ax.contourf(ctx.lon, ctx.lat, np.ma.masked_invalid(mucape), levels=levels, cmap=cm, norm=nm, extend=ext, zorder=2, alpha=.85)
    barra(fig, cs, levels)
    ny, nx = mucape.shape
    km_por_ms = 4.4 / 30.0
    cor = plt.get_cmap("turbo")
    segs, cols = [], []
    bx, by, bc = [], [], []
    for j in range(passo // 2 + 3, ny - 4, passo):
        for i in range(passo // 2 + 3, nx - 4, passo):
            lo0, la0 = ctx.lon[j, i], ctx.lat[j, i]
            kx = km_por_ms / (111.32 * np.cos(np.radians(la0)))
            ky = km_por_ms / 110.57
            xs = lo0 + U[:, j, i] * kx
            ys = la0 + V[:, j, i] * ky
            for k in range(len(alt) - 1):
                segs.append([(xs[k], ys[k]), (xs[k + 1], ys[k + 1])])
                cols.append(cor(alt[k] / 6000.0))
            for (cu, cv), c in ((rm, "#0000ff"), (lm, "#ff0000")):
                bx.append(lo0 + cu[j, i] * kx); by.append(la0 + cv[j, i] * ky); bc.append(c)
            ax.plot([lo0], [la0], marker="+", color="k", ms=5, mew=1, zorder=9)
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=2.4, zorder=10))
    ax.scatter(bx, by, s=26, c=bc, edgecolors="black", linewidths=.6, zorder=11)
    vetores(ax, ctx, legenda=True)
    # legenda de altura
    cax = fig.add_axes([60 / W, 85 / H, 700 / W, 26 / H])
    sm = plt.cm.ScalarMappable(cmap=cor, norm=matplotlib.colors.Normalize(0, 6))
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Altura AGL na hodógrafa [km]; escala: 30 m/s = 4,4 km", fontsize=15)
    cb.ax.tick_params(labelsize=14)
    return fig


def salvar(fig, caminho):
    fig.savefig(caminho, dpi=DPI, facecolor="white")
    plt.close(fig)
