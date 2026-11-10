#!/usr/bin/env python3
"""Vale1Km: gera namelist.wps e namelist.input para 1 ou 2 domínios (veja N_DOM em dominio.py).

Uso:
  gerar_namelists.py wps   --manifesto dados/manifesto.json --fim 2026-10-24T21 --geog /caminho/geog_mini --saida namelist.wps
  gerar_namelists.py input --manifesto dados/manifesto.json --fim 2026-10-24T21 --niveis 19 --saida namelist.input
"""
import argparse
import json
from datetime import datetime, timedelta

import dominio as D

FMT = "%Y-%m-%dT%H"


def datas(man, fim):
    ini = datetime.strptime(man["horarios_utc"][0], FMT)
    bc_fim = datetime.strptime(man["horarios_utc"][-1], FMT)
    fim = min(datetime.strptime(fim, FMT), bc_fim)
    return ini, fim, bc_fim


def L(valores):
    return ", ".join(str(v) for v in valores)


def rep(v, n):
    return ", ".join([str(v)] * n)


def wps(man, fim, geog):
    ini, fim, bc_fim = datas(man, fim)
    f = lambda t: t.strftime("%Y-%m-%d_%H:%M:%S")
    doms = D.DOMINIOS
    n = len(doms)
    razao = [1] + [d["razao"] for d in doms[1:]]
    i0 = [1] + [d["i0"] for d in doms[1:]]
    j0 = [1] + [d["j0"] for d in doms[1:]]
    return f"""&share
 wrf_core = 'ARW',
 max_dom = {n},
 start_date = {L(repr(f(ini)) for _ in doms)},
 end_date   = {L(repr(f(bc_fim)) for _ in doms)},
 interval_seconds = {D.PASSO_CONTORNO_S},
 io_form_geogrid = 2,
/

&geogrid
 parent_id         = {rep(1, n)},
 parent_grid_ratio = {L(razao)},
 i_parent_start    = {L(i0)},
 j_parent_start    = {L(j0)},
 e_we              = {L(d['e_we'] for d in doms)},
 e_sn              = {L(d['e_sn'] for d in doms)},
 geog_data_res     = {L("'default'" for _ in doms)},
 dx = {doms[0]['dx']},
 dy = {doms[0]['dx']},
 map_proj  = 'lambert',
 ref_lat   = {D.CENTRO[0]},
 ref_lon   = {D.CENTRO[1]},
 truelat1  = {D.TRUELAT[0]},
 truelat2  = {D.TRUELAT[1]},
 stand_lon = {D.CENTRO[1]},
 geog_data_path = '{geog}',
/

&ungrib
 out_format = 'WPS',
 prefix = 'FILE',
/

&metgrid
 fg_name = 'FILE',
 io_form_metgrid = 2,
/
"""


def entrada(man, fim, niveis):
    ini, fim, bc_fim = datas(man, fim)
    # o wrfbdy só cobre múltiplos do intervalo de contorno: roda até o último horário ICON (>= fim pedido)
    horas = max(3, int((bc_fim - ini).total_seconds() // 3600))
    fim = ini + timedelta(hours=horas)
    doms = D.DOMINIOS
    n = len(doms)
    dt1 = int(6 * doms[0]["dx"] / 1000)  # regra de 6 s por km do domínio externo
    razao = [1] + [d["razao"] for d in doms[1:]]
    i0 = [0] + [d["i0"] for d in doms[1:]]
    j0 = [0] + [d["j0"] for d in doms[1:]]
    aux = L(["60"] * (n - 1) + ["10"])  # auxhist2 (U,V,W,PH,PHB para o UH): a cada 10 min só no domínio de 1 km
    return f"""&time_control
 run_days = 0,
 run_hours = {horas},
 run_minutes = 0,
 run_seconds = 0,
 start_year = {rep(ini.year, n)}, start_month = {rep(ini.month, n)}, start_day = {rep(ini.day, n)},
 start_hour = {rep(ini.hour, n)}, start_minute = {rep('00', n)}, start_second = {rep('00', n)},
 end_year = {rep(fim.year, n)}, end_month = {rep(fim.month, n)}, end_day = {rep(fim.day, n)},
 end_hour = {rep(fim.hour, n)}, end_minute = {rep('00', n)}, end_second = {rep('00', n)},
 interval_seconds = {D.PASSO_CONTORNO_S},
 input_from_file = {rep('.true.', n)},
 history_interval = {rep(60, n)},
 frames_per_outfile = {rep(1000, n)},
 auxhist2_outname = "auxhist2_d<domain>_<date>",
 auxhist2_interval = {aux},
 frames_per_auxhist2 = {rep(1000, n)},
 io_form_auxhist2 = 2,
 iofields_filename = {L('"iofields.txt"' for _ in doms)},
 restart = .false.,
 io_form_history = 2,
 io_form_restart = 2,
 io_form_input = 2,
 io_form_boundary = 2,
 debug_level = 0,
/

&domains
 time_step = {dt1},
 time_step_fract_num = 0,
 time_step_fract_den = 1,
 max_dom = {n},
 e_we = {L(d['e_we'] for d in doms)},
 e_sn = {L(d['e_sn'] for d in doms)},
 e_vert = {rep(D.NIVEIS_VERT, n)},
 dx = {L(d['dx'] for d in doms)},
 dy = {L(d['dx'] for d in doms)},
 grid_id = {L(range(1, n + 1))},
 parent_id = {L([0] + [1] * (n - 1))},
 i_parent_start = {L(i0)},
 j_parent_start = {L(j0)},
 parent_grid_ratio = {L(razao)},
 parent_time_step_ratio = {L(razao)},
 feedback = 0,
 smooth_option = 0,
 p_top_requested = 5000,
 num_metgrid_levels = {niveis},
 num_metgrid_soil_levels = 4,
 interp_type = 2,
 extrap_type = 2,
 t_extrap_type = 2,
 use_surface = .true.,
 use_levels_below_ground = .true.,
 lowest_lev_from_sfc = .false.,
 force_sfc_in_vinterp = 1,
 zap_close_levels = 500,
 adjust_heights = .false.,
 lagrange_order = 1,
/

&physics
 mp_physics = {rep(8, n)},
 do_radar_ref = 1,
 ra_lw_physics = {rep(4, n)},
 ra_sw_physics = {rep(4, n)},
 radt = {rep(5, n)},
 sf_sfclay_physics = {rep(5, n)},
 sf_surface_physics = {rep(2, n)},
 bl_pbl_physics = {rep(5, n)},
 bldt = {rep(0, n)},
 cu_physics = {rep(0, n)},
 cudt = {rep(0, n)},
 num_soil_layers = 4,
 sf_urban_physics = {rep(0, n)},
/

&dynamics
 hybrid_opt = 2,
 use_theta_m = 0,
 w_damping = 1,
 diff_opt = {rep(2, n)},
 km_opt = {rep(4, n)},
 diff_6th_opt = {rep(2, n)},
 diff_6th_factor = {rep(0.12, n)},
 base_temp = 290.,
 damp_opt = 3,
 zdamp = {rep('5000.', n)},
 dampcoef = {rep(0.2, n)},
 khdif = {rep(0, n)},
 kvdif = {rep(0, n)},
 epssm = {rep(0.3, n)},
 non_hydrostatic = {rep('.true.', n)},
 moist_adv_opt = {rep(1, n)},
 scalar_adv_opt = {rep(1, n)},
/

&bdy_control
 spec_bdy_width = 5,
 specified = {L(['.true.'] + ['.false.'] * (n - 1))},
 nested = {L(['.false.'] + ['.true.'] * (n - 1))},
/

&grib2
/

&namelist_quilt
 nio_tasks_per_group = 0,
 nio_groups = 1,
/
"""


# Variáveis 3D extras em auxhist2: o UH é calculado depois, no pós-processamento
IOFIELDS = "+:h:2:U,V,W,PH,PHB\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["wps", "input"])
    ap.add_argument("--manifesto", default="dados/manifesto.json")
    ap.add_argument("--fim", required=True, help="fim da rodada (AAAA-MM-DDTHH, UTC)")
    ap.add_argument("--geog", default="geog_mini")
    ap.add_argument("--niveis", type=int, default=19)
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()
    man = json.load(open(a.manifesto, encoding="utf-8"))
    txt = wps(man, a.fim, a.geog) if a.modo == "wps" else entrada(man, a.fim, a.niveis)
    open(a.saida, "w", encoding="utf-8").write(txt)
    if a.modo == "input":
        open(a.saida.replace("namelist.input", "iofields.txt") if "namelist.input" in a.saida else "iofields.txt",
             "w").write(IOFIELDS)


if __name__ == "__main__":
    main()
