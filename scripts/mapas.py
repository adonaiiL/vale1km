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


def _expandir(base, n):
    """Gera n cores a partir de um nome do matplotlib ou de uma lista curta."""
    n = max(int(n), 2)
    if isinstance(base, str):
        return _cmap(base, n)
    cm = matplotlib.colors.LinearSegmentedColormap.from_list("faixa", list(base), N=n)
    return [matplotlib.colors.to_hex(cm(i / (n - 1))) for i in range(n)]


def faixa(rotulo, titulo, niveis, base, ext, rotulos):
    """níveis = bordas das cores; rotulos = passo ou lista do que a barra escreve."""
    n = len(niveis) - 1
    extra = 2 if ext == "both" else (1 if ext in ("min", "max") else 0)
    return (rotulo, titulo, niveis, _expandir(base, n + extra), ext, rotulos)


CAPE_LV = [0, 50, 100, 250, 500, 750, 1000, 1250, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 6000]
CAPE_ROT = [0, 500, 1000, 2000, 3000, 4000, 5000, 6000]
PREC_LV = [0.1, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200]
PREC_ROT = [0.1, 1, 5, 10, 20, 30, 50, 100, 200]

# chave: (rótulo, título, níveis, cores, extensão, rótulos da barra)
PARAMS = {
    "rf": faixa("Refletividade", "Refletividade Composta [dBZ] | UH 2-5 km 1-hr [<{u:.0f} m²/s²]", lv(0, 75, 2.5), RF, "max", 5),
    "ws": faixa("Ventos", "Vento instantâneo a 10 m [kt] | barbelas", lv(0, 60, 2), "viridis", "max", 5),
    "gust": faixa("Rajada máx.", "Vento máximo a 10 m no intervalo de saída [kt]", lv(0, 100, 2), "viridis", "max", [0, 20, 40, 60, 80, 100]),
    "wu": faixa("Corrente ascendente", "Velocidade vertical máxima ascendente [m/s]", lv(0, 50, 1), "magma", "max", [0, 5, 10, 20, 30, 40, 50]),
    "wd": faixa("Corrente descendente", "Intensidade máxima de corrente descendente [m/s]", lv(0, 40, 1), "cividis", "max", [0, 5, 10, 20, 30, 40]),
    "wm": faixa("W média", "Velocidade vertical média na camada sigma 0,5–0,8 [m/s]", lv(-5, 5, 0.25), "RdBu_r", "both", [-5, -3, -1, 0, 1, 3, 5]),
    "gr": faixa("Graupel integrado", "Máximo de graupel integrado na coluna [kg/m²]", lv(0, 6, 0.2), "YlOrRd", "max", [0, 0.5, 1, 2, 3, 4, 5, 6]),
    "hail": faixa("Granizo estimado", "Diâmetro máximo diagnóstico de granizo [mm] (estimativa do WRF)", lv(0, 80, 2), "YlGnBu", "max", [0, 10, 20, 40, 60, 80]),
    "t2": faixa("Temperatura", "Temperatura a 2 m [°C]", lv(-10, 42, 1), "RdYlBu_r", "both", 2),
    "rh": faixa("Umidade", "Umidade relativa a 2 m [%]", lv(0, 100, 5), "YlGnBu", "neither", 10),
    "pr": faixa("Precip. acumulada", "Precipitação acumulada total [mm]", PREC_LV, PREC_C, "max", PREC_ROT),
    "td": faixa("Ponto de orvalho", "Ponto de orvalho a 2 m [°C]", lv(-10, 28, 1), "YlGnBu", "both", 2),
    "fr": faixa("Geada", "Previsão de geada | Tmín 2 m desde o início [°C]", lv(-12, 12, 1), GEADA_C, "both", 2),
    "ml": faixa("MLCAPE", "MLCAPE [J/kg]", CAPE_LV, CAPE_C, "max", CAPE_ROT),
    "mu": faixa("MUCAPE", "MUCAPE [J/kg]", CAPE_LV, CAPE_C, "max", CAPE_ROT),
    "mc": faixa("MLCIN", "MLCIN [J/kg] (valores negativos)", lv(-500, 0, 25), "PuBu", "min", [-500, -400, -300, -200, -100, 0]),
    "uc": faixa("MUCIN", "MUCIN [J/kg] (valores negativos)", lv(-500, 0, 25), "PuBu", "min", [-500, -400, -300, -200, -100, 0]),
    "sr1": faixa("SRH 0-1 km", "SRH 0-1 km [m²/s²] (ciclônica < 0 no HS)", lv(-300, 300, 25), "RdBu_r", "both", [-300, -200, -100, 0, 100, 200, 300]),
    "sr3": faixa("SRH 0-3 km", "SRH 0-3 km [m²/s²] (ciclônica < 0 no HS)", lv(-500, 500, 50), "RdBu_r", "both", [-500, -400, -300, -200, -100, 0, 100, 200, 300, 400, 500]),
    "pr1": faixa("Precip. 1h", "Precipitação na última hora [mm]", PREC_LV, PREC_C, "max", PREC_ROT),
    "brnsh": faixa("BRN shear", "BRN shear [m²/s²]", lv(0, 200, 10), "viridis", "max", [0, 25, 50, 75, 100, 125, 150, 175, 200]),
    "sc": faixa("SCP fixo", "SCP de camadas fixas [MUCAPE / 1000 × (−SRH 0–3 km) / 150 × BRN shear / 40]", [0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30], CAPE_C, "max", [0, 1, 2, 4, 8, 12, 20, 30]),
    "vo": faixa("Vorticidade 850 hPa", "Vorticidade relativa 850 hPa [10⁻⁵ s⁻¹] (ciclônica < 0)", lv(-40, 40, 4), "RdBu_r", "both", 8),
    "sn": ("Neve acumulada", "Mosaico de neve acumulada", None, None, None, None),
    "sh": ("Cisalhamento", "Mosaico de cisalhamento do vento [kt]", None, None, None, None),
    "hd": faixa("Hodomap", "Hodomap 0-6 km | MUCAPE [J/kg] | Bunkers (LM vermelho, RM azul)", CAPE_LV, CAPE_C, "max", CAPE_ROT),
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
                 label=", ".join(f"{k} {v[0]}" for k, v in D.PONTOS.items()))]
    return h


def vetores(ax, ctx, legenda=False, rotulos=True, esc=1.0):
    mun_lw = []
    for cod, aneis in ctx.mun.items():
        dest = cod in D.MUNICIPIOS
        lc = LineCollection(aneis, colors="black" if dest else "#6b6b6b", linewidths=(3.0 if dest else 1.2) * max(esc, .6), zorder=6 if dest else 5)
        ax.add_collection(lc)
        if dest and rotulos and cod in D.ROTULOS_MUN:
            la_, lo_ = D.ROTULOS_MUN[cod]
            ax.text(lo_, la_, D.MUNICIPIOS[cod], fontsize=21, fontweight="bold", color="black", ha="center", va="center",
                    zorder=20, path_effects=[pe.withStroke(linewidth=5, foreground="white")])
    vistos = {}
    LW = {"motorway": 3.6, "trunk": 3.6, "primary": 2.8, "secondary": 1.8}
    COR = {"motorway": "#9a3412", "trunk": "#9a3412", "primary": "#b45309", "secondary": "#d9a066"}
    for ref, pts, cl in sorted(ctx.rod, key=lambda r: LW.get(r[2], 2) ):
        ax.add_collection(LineCollection([pts], colors=COR.get(cl, "#b45309"), linewidths=LW.get(cl, 2.4) * max(esc, .6), zorder=7))
        dentro = sum(ctx.ext[0] < x < ctx.ext[1] and ctx.ext[2] < y < ctx.ext[3] for x, y in pts)
        if rotulos and ref and cl in ("motorway", "trunk", "primary") and dentro > vistos.get(ref, (0,))[0]:
            vistos[ref] = (dentro, pts[len(pts) // 2])
    for ref, (n, (x, y)) in vistos.items():
        if n >= 3 and ctx.ext[0] < x < ctx.ext[1] and ctx.ext[2] < y < ctx.ext[3]:
            ax.text(x, y, ref.split(";")[0], fontsize=13, color="#7c2d00", fontweight="bold", zorder=16, path_effects=HALO, ha="center")
    for k, (nome, la, lo) in D.PONTOS.items():
        ax.scatter([lo], [la], s=150 * esc ** 2, c="#ffe600", edgecolors="black", linewidths=2.2 * max(esc, .6), zorder=12)
        ax.text(lo + 0.006, la - 0.004, k, fontsize=26 * esc, fontweight="bold", color="black", zorder=13, path_effects=HALO)
    ax.text(0.985, 0.025, D.NOME, transform=ax.transAxes, fontsize=34 * esc, fontweight="bold", ha="right", va="bottom",
            color="black", path_effects=[pe.withStroke(linewidth=6, foreground="white")], zorder=14)
    if legenda:
        leg = ax.legend(handles=handles_legenda(uh=(legenda == 'uh')), loc="lower left", fontsize=17, framealpha=.94,
                        borderpad=.8, labelspacing=.6)
        leg.set_zorder(20)


def ticks_legenda(levels, guia, maximo=18):
    levels = [float(x) for x in levels]
    if isinstance(guia, (list, tuple)):
        ticks = [float(x) for x in guia if levels[0] - 1e-6 <= float(x) <= levels[-1] + 1e-6]
    elif guia:
        ticks = [x for x in levels if abs(x / float(guia) - round(x / float(guia))) < 1e-4]
    else:
        ticks = list(levels)
    if len(ticks) < 2:
        ticks = list(levels)
    if len(ticks) > maximo:
        k = int(np.ceil(len(ticks) / maximo))
        ticks = ticks[::k]
        if ticks[-1] != levels[-1]:
            ticks.append(levels[-1])
    return ticks


def barra(fig, cs, levels, guia=None):
    cax = fig.add_axes([2118 / W, 44 / H, 82 / W, 1752 / H])
    cb = fig.colorbar(cs, cax=cax)
    ticks = ticks_legenda(levels, guia, 28)
    cb.set_ticks(ticks)
    cb.ax.set_yticklabels([f"{v:g}" for v in ticks])
    cb.ax.tick_params(labelsize=14 if len(ticks) > 16 else 18, length=6, width=1.2, pad=2)
    cb.outline.set_linewidth(2)
    return cb


def _norm(levels, cores, ext):
    n = len(levels) - 1
    pal = list(cores)
    if ext == "both" and len(pal) >= n + 2:
        under, corpo, over = pal[0], pal[1:n + 1], pal[n + 1]
    elif ext == "max" and len(pal) >= n + 1:
        under, corpo, over = pal[0], pal[:n], pal[n]
    elif ext == "min" and len(pal) >= n + 1:
        under, corpo, over = pal[0], pal[1:n + 1], pal[-1]
    else:
        if len(pal) < n:
            pal = _expandir(pal, n)
        under, corpo, over = pal[0], pal[:n], pal[-1]
    cm = ListedColormap(corpo[:n])
    if ext in ("max", "both"):
        cm.set_over(over)
    if ext in ("min", "both"):
        cm.set_under(under)
    return cm, BoundaryNorm(levels, cm.N)


def segmentos_fechados(segmentos, tolerancia=1e-5):
    """Retorna apenas contornos fechados; descarta linhas truncadas por bordas/máscaras."""
    fechados = []
    for segmento in segmentos:
        xy = np.asarray(segmento, dtype=float)
        if xy.ndim != 2 or xy.shape[0] < 4 or xy.shape[1] < 2:
            continue
        if not np.all(np.isfinite(xy[:, :2])):
            continue
        distancia = np.hypot(xy[0, 0] - xy[-1, 0], xy[0, 1] - xy[-1, 1])
        if distancia <= tolerancia:
            fechados.append(xy[:, :2])
    return fechados


def mapa_simples(chave, ctx, campo, barbs=None, dest=None):
    rot, tit, levels, cores, ext, guia = PARAMS[chave]
    tit = tit.format(u=D.UH_LIMIAR) if "{u" in tit else tit
    fig, ax = figura(tit, ctx)
    moldura(ax, ctx)
    cm, nm = _norm(levels, cores, ext)
    cs = ax.contourf(ctx.lon, ctx.lat, np.ma.masked_invalid(campo), levels=levels, cmap=cm, norm=nm, extend=ext, zorder=2)
    barra(fig, cs, levels, guia)
    if barbs is not None:
        u, v, s = barbs
        ax.barbs(ctx.lon[::s, ::s], ctx.lat[::s, ::s], u[::s, ::s], v[::s, ::s], length=6.5, linewidth=1.3, zorder=4,
                 sizes=dict(emptybarb=0.1))
    if chave == "rf" and ctx.uh is not None and np.any(np.isfinite(ctx.uh)) and np.nanmin(ctx.uh) <= D.UH_LIMIAR:
        cs_uh = ax.contour(ctx.lon, ctx.lat, np.ma.masked_invalid(ctx.uh),
                           levels=[D.UH_LIMIAR], colors="k", linewidths=2.2,
                           linestyles="solid", zorder=9, corner_mask=False)
        # A grade termina no limite do aninhamento. Sem WRF fora dela, não se
        # extrapolam linhas abertas como se fossem contornos completos.
        completos = segmentos_fechados(cs_uh.allsegs[0])
        cs_uh.remove()
        if completos:
            ax.add_collection(LineCollection(completos, colors="k", linewidths=2.2, zorder=9))
    vetores(ax, ctx, legenda="uh" if chave == "rf" else True)
    return fig


def caixas_mosaico(ctx, shape):
    """Caixas dos painéis em pixels da figura (x, y a partir do topo, largura, altura)."""
    nl, nc = shape
    x0, y0, w, h = 20, 262, 2255, 1480
    gx, gy = 50, 125
    pw = (w - gx * (nc - 1)) / nc
    ph = (h - gy * (nl - 1)) / nl
    ah = min(pw / ctx.ratio, ph - 95)
    aw = ah * ctx.ratio
    caixas = []
    for i in range(nl * nc):
        r, c = divmod(i, nc)
        px = x0 + c * (pw + gx) + (pw - aw) / 2
        py = y0 + r * (ph + gy)
        caixas.append((px, py, aw, ah))
    return caixas


def mosaico(chave, ctx, paineis, shape):
    """paineis: lista de (titulo, campo, levels, cores, ext, contorno_0C ou None). shape=(linhas, colunas)."""
    rot, tit, *_ = PARAMS[chave]
    fig, _ax = figura(tit, ctx, mosaico=True)
    _ax.remove()
    caixas = caixas_mosaico(ctx, shape)
    for i, (t, campo, levels, cores, ext, c0) in enumerate(paineis):
        px, py, aw, ah = caixas[i]
        ax = fig.add_axes([px / W, 1 - (py + ah) / H, aw / W, ah / H])
        moldura(ax, ctx)
        cm, nm = _norm(levels, cores, ext)
        cs = ax.contourf(ctx.lon, ctx.lat, np.ma.masked_invalid(campo), levels=levels, cmap=cm, norm=nm, extend=ext, zorder=2)
        if c0 is not None and np.nanmin(c0) < 0 < np.nanmax(c0):
            ax.contour(ctx.lon, ctx.lat, np.ma.masked_invalid(c0), levels=[0.0], colors="k", linewidths=2.0, linestyles="solid", zorder=8)
        ax.set_title(t, fontsize=20, loc="left", pad=10)
        cax = fig.add_axes([(px + aw * 0.04) / W, 1 - (py + ah + 62) / H, aw * 0.92 / W, 26 / H])
        cb = fig.colorbar(cs, cax=cax, orientation="horizontal")
        tk = ticks_legenda(levels, None, 8)
        cb.set_ticks(tk); cb.ax.set_xticklabels([f"{x:g}" for x in tk])
        cb.ax.tick_params(labelsize=12)
        vetores(ax, ctx, legenda=False, rotulos=False, esc=0.62)
    fig.legend(handles=handles_legenda(), loc="lower center", ncol=4, fontsize=17, frameon=True,
               bbox_to_anchor=(0.5, 0.004), framealpha=.95)
    return fig


def hodomap(ctx, mucape, alt, U, V, rm, lm, passo=8):
    rot, tit, levels, cores, ext, guia = PARAMS["hd"]
    fig, ax = figura(tit, ctx)
    moldura(ax, ctx)
    cm, nm = _norm(levels, cores, ext)
    cs = ax.contourf(ctx.lon, ctx.lat, np.ma.masked_invalid(mucape), levels=levels, cmap=cm, norm=nm, extend=ext, zorder=2, alpha=.85)
    barra(fig, cs, levels, guia)
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
