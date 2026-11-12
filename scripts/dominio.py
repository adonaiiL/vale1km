"""Vale1Km: constantes do domínio, compartilhadas por todos os scripts."""

NOME = "Vale1Km"

# Centro do domínio: ponto médio entre Blumenau e Pomerode (SC)
CENTRO = (-26.83, -49.12)  # (lat, lon)

# Três domínios, razão 3 em cada salto (9 km em cima de 6 km seria 1,5 e o geogrid recusa).
#   d01 = 9 km, recebe o ICON e não é plotado
#   d02 = 3 km, ponte, não é plotado
#   d03 = 1 km, o produto
# O passo do 1 km continua 6 s, igual à grade antiga de 5 km → 1 km.
N_DOM = 3

D01 = dict(dx=9000, e_we=56, e_sn=54)                          # 55 x 53 células (495 x 477 km)
D02 = dict(dx=3000, e_we=64, e_sn=58, i0=18, j0=18, razao=3)  # 63 x 57 células (189 x 171 km)
D03 = dict(dx=1000, e_we=94, e_sn=76, i0=17, j0=17, razao=3)  # 93 x 75 células (93 x 75 km)
D_UNICO = dict(dx=1000, e_we=141, e_sn=121)                    # só se N_DOM = 1
NIVEIS_VERT = 60

DOMINIOS = [D_UNICO] if N_DOM == 1 else [D01, D02, D03][:N_DOM]
FINO = "d%02d" % len(DOMINIOS)  # d03
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
# Onde escrever o nome de cada município no mapa (lat, lon), longe dos pontos A, F, K e Ko; ajuste à vontade
ROTULOS_MUN = {"4202404": (-26.985, -49.085), "4213203": (-26.700, -49.100)}
SEDES = {"4202404": (-26.9194, -49.0661), "4213203": (-26.7406, -49.1769)}

# UH 2-5 km, hemisfério Sul: rotação ciclônica é negativa
UH_LIMIAR = -100.0  # m²/s², ajustado para 1 km

PASSO_CONTORNO_S = 10800  # condições de contorno a cada 3 h
SPINUP_PADRAO_H = 6
