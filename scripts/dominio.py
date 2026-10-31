"""Vale1Km: constantes do domínio, compartilhadas por todos os scripts."""

NOME = "Vale1Km"

# Centro do domínio: ponto médio entre Blumenau e Pomerode (SC)
CENTRO = (-26.83, -49.12)  # (lat, lon)

# d01 funciona só como "ponte" entre o ICON (~13 km) e o domínio de 1 km; não é plotado.
D01 = dict(dx=5000, e_we=72, e_sn=72)                       # 71 x 71 células (355 km)
D02 = dict(dx=1000, e_we=96, e_sn=76, i0=27, j0=29, razao=5)  # 95 x 75 células (95 x 75 km), centrado em D01
TRUELAT = (-24.0, -30.0)

# Recorte do ICON em lat/lon (graus): lon_min, lon_max, lat_min, lat_max
RECORTE = (-58.0, -40.0, -34.0, -19.0)

PONTOS = {
    "A": ("Adonai", -26.91468, -49.07622),
    "F": ("Fabrício", -26.760251, -49.184348),
    "K": ("Kelvin", -26.675419, -49.184906),
    "Ko": ("Komprão", -26.706956, -49.162766),
}

# Municípios destacados (código IBGE)
MUNICIPIOS = {"4202404": "Blumenau", "4213203": "Pomerode"}
# Sede de cada município (lat, lon): rótulo no mapa e conferência dos limites baixados
SEDES = {"4202404": (-26.9194, -49.0661), "4213203": (-26.7406, -49.1769)}

# UH 2-5 km, hemisfério Sul: rotação ciclônica é negativa
UH_LIMIAR = -100.0  # m²/s², ajustado para 1 km

PASSO_CONTORNO_S = 10800  # condições de contorno a cada 3 h
SPINUP_PADRAO_H = 3
