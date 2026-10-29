#!/usr/bin/env python3
"""Vale1Km: gera namelist.wps e namelist.input (2 domínios: 5 km como ponte e 1 km como produto).

Uso:
  gerar_namelists.py wps   --manifesto dados/manifesto.json --fim 2026-10-24T21 --geog /caminho/geog_mini --saida namelist.wps
  gerar_namelists.py input --manifesto dados/manifesto.json --fim 2026-10-24T21 --niveis 19 --saida namelist.input
"""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta

import dominio as D

FMT = "%Y-%m-%dT%H"


def datas(man, fim):
    ini = datetime.strptime(man["horarios_utc"][0], FMT)
    bc_fim = datetime.strptime(man["horarios_utc"][-1], FMT)
    fim = datetime.strptime(fim, FMT)
    fim = min(fim, bc_fim)
    return ini, fim, bc_fim


def wps(man, fim, geog):
    ini, fim, bc_fim = datas(man, fim)
    f = lambda t: t.strftime("%Y-%m-%d_%H:%M:%S")
    d1, d2 = D.D01, D.D02
    return f"""&share
 wrf_core = 'ARW',
 max_dom = 2,
 start_date = '{f(ini)}','{f(ini)}',
 end_date   = '{f(bc_fim)}','{f(bc_fim)}',
 interval_seconds = {D.PASSO_CONTORNO_S},
 io_form_geogrid = 2,
/

&geogrid
 parent_id         = 1, 1,
 parent_grid_ratio = 1, {d2['razao']},
 i_parent_start    = 1, {d2['i0']},
 j_parent_start    = 1, {d2['j0']},
 e_we              = {d1['e_we']}, {d2['e_we']},
 e_sn              = {d1['e_sn']}, {d2['e_sn']},
 geog_data_res     = 'default','default',
 dx = {d1['dx']},
 dy = {d1['dx']},
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
    d1, d2 = D.D01, D.D02
    dt1 = 30
    par = lambda v: f"{v}, {v}"
    return f"""&time_control
 run_days = 0,
 run_hours = {horas},
 run_minutes = 0,
 run_seconds = 0,
 start_year = {par(ini.year)}, start_month = {par(ini.month)}, start_day = {par(ini.day)},
 start_hour = {par(ini.hour)}, start_minute = 00, 00, start_second = 00, 00,
 end_year = {par(fim.year)}, end_month = {par(fim.month)}, end_day = {par(fim.day)},
 end_hour = {par(fim.hour)}, end_minute = 00, 00, end_second = 00, 00,
 interval_seconds = {D.PASSO_CONTORNO_S},
 input_from_file = .true., .true.,
 history_interval = 60, 60,
 frames_per_outfile = 1000, 1000,
 auxhist2_outname = "auxhist2_d<domain>_<date>",
 auxhist2_interval = 60, 10,
 frames_per_auxhist2 = 1000, 1000,
 io_form_auxhist2 = 2,
 iofields_filename = "iofields.txt", "iofields.txt",
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
 max_dom = 2,
 e_we = {d1['e_we']}, {d2['e_we']},
 e_sn = {d1['e_sn']}, {d2['e_sn']},
 e_vert = 51, 51,
 dx = {d1['dx']}, {d2['dx']},
 dy = {d1['dx']}, {d2['dx']},
 grid_id = 1, 2,
 parent_id = 0, 1,
 i_parent_start = 1, {d2['i0']},
 j_parent_start = 1, {d2['j0']},
 parent_grid_ratio = 1, {d2['razao']},
 parent_time_step_ratio = 1, {d2['razao']},
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
 mp_physics = 8, 8,
 do_radar_ref = 1,
 ra_lw_physics = 4, 4,
 ra_sw_physics = 4, 4,
 radt = 5, 5,
 sf_sfclay_physics = 5, 5,
 sf_surface_physics = 2, 2,
 bl_pbl_physics = 5, 5,
 bldt = 0, 0,
 cu_physics = 0, 0,
 cudt = 0, 0,
 num_soil_layers = 4,
 sf_urban_physics = 0, 0,
/

&dynamics
 hybrid_opt = 2,
 use_theta_m = 0,
 w_damping = 1,
 diff_opt = 2, 2,
 km_opt = 4, 4,
 diff_6th_opt = 2, 2,
 diff_6th_factor = 0.12, 0.12,
 base_temp = 290.,
 damp_opt = 3,
 zdamp = 5000., 5000.,
 dampcoef = 0.2, 0.2,
 khdif = 0, 0,
 kvdif = 0, 0,
 epssm = 0.3, 0.3,
 non_hydrostatic = .true., .true.,
 moist_adv_opt = 1, 1,
 scalar_adv_opt = 1, 1,
/

&bdy_control
 spec_bdy_width = 5,
 specified = .true., .false.,
 nested = .false., .true.,
/

&grib2
/

&namelist_quilt
 nio_tasks_per_group = 0,
 nio_groups = 1,
/
"""


# Variáveis 3D extras em auxhist2 (a cada 10 min no domínio de 1 km): o UH é calculado depois, no pós-processamento
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
