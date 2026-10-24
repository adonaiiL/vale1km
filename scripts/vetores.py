"""Vale1Km: limites municipais (IBGE) e rodovias (OpenStreetMap) para os mapas. Falhas não derrubam a rodada."""
import json
import os
import time
import urllib.parse
import urllib.request

IBGE = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/42"
        "?formato=application/vnd.geo+json&intrarregiao=municipio&qualidade=intermediaria")
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter"]


def _get(url, dados=None, tent=3, timeout=120):
    erro = None
    for i in range(tent):
        try:
            req = urllib.request.Request(url, data=dados, headers={"User-Agent": "vale1km/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            erro = e
            time.sleep(3 * (i + 1))
    raise erro


def _aneis(geom):
    if geom["type"] == "Polygon":
        polis = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polis = geom["coordinates"]
    else:
        return []
    return [[(p[0], p[1]) for p in anel] for poli in polis for anel in poli]


def municipios(cache, caixa):
    """Devolve {codarea: [anéis]} para municípios que tocam a caixa (lon0, lon1, lat0, lat1)."""
    try:
        if os.path.exists(cache):
            gj = json.load(open(cache, encoding="utf-8"))
        else:
            gj = json.loads(_get(IBGE))
            json.dump(gj, open(cache, "w", encoding="utf-8"))
    except Exception as e:
        print(f"Aviso: sem limites do IBGE ({e})")
        return {}
    out = {}
    for f in gj.get("features", []):
        cod = str(f.get("properties", {}).get("codarea", ""))
        an = _aneis(f["geometry"])
        pts = [p for a in an for p in a]
        if not pts:
            continue
        lo = [p[0] for p in pts]; la = [p[1] for p in pts]
        if max(lo) < caixa[0] or min(lo) > caixa[1] or max(la) < caixa[2] or min(la) > caixa[3]:
            continue
        out[cod] = an
    return out


def rodovias(cache, caixa):
    """Devolve lista de (ref, [(lon, lat), ...]) das rodovias principais na caixa."""
    try:
        if os.path.exists(cache):
            els = json.load(open(cache, encoding="utf-8"))
        else:
            q = (f'[out:json][timeout:90];way["highway"~"^(motorway|trunk|primary)$"]'
                 f'({caixa[2]},{caixa[0]},{caixa[3]},{caixa[1]});out geom;')
            els = None
            for url in OVERPASS:
                try:
                    els = json.loads(_get(url, urllib.parse.urlencode({"data": q}).encode(), tent=2))["elements"]
                    break
                except Exception as e:
                    print(f"Aviso: Overpass {url} falhou ({e})")
            if els is None:
                return []
            json.dump(els, open(cache, "w", encoding="utf-8"))
    except Exception as e:
        print(f"Aviso: sem rodovias ({e})")
        return []
    out = []
    for e in els:
        g = e.get("geometry")
        if g:
            out.append((e.get("tags", {}).get("ref", ""), [(p["lon"], p["lat"]) for p in g]))
    return out
