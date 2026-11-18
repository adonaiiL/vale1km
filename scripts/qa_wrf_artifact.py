#!/usr/bin/env python3
"""Audita UH assinado e vorticidade do dominio d03 a partir dos brutos WRF."""
import argparse, json, sys
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, chartostring
from scipy.ndimage import convolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
import termo

G = 9.81
ALT = np.arange(2000.0, 5000.1, 250.0)
KERNEL = np.array([[0.0625, 0.125, 0.0625],
                   [0.1250, 0.250, 0.1250],
                   [0.0625, 0.125, 0.0625]])

def get_times(ds):
    values = chartostring(ds.variables["Times"][:])
    return [datetime.strptime(str(v).replace("\\x00", "").strip(), "%Y-%m-%d_%H:%M:%S")
            for v in np.asarray(values).reshape(-1)]

def records(paths):
    result = []
    for path in paths:
        with Dataset(path) as ds:
            result.extend((when, Path(path), i) for i, when in enumerate(get_times(ds)))
    return sorted(result, key=lambda item: (item[0], str(item[1]), item[2]))

def field(ds, name, index):
    return np.asarray(np.ma.filled(ds.variables[name][index], np.nan), dtype=np.float64)

def destagger(array, axis):
    lo = [slice(None)] * array.ndim
    hi = [slice(None)] * array.ndim
    lo[axis], hi[axis] = slice(0, -1), slice(1, None)
    return 0.5 * (array[tuple(lo)] + array[tuple(hi)])

def stats(values):
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    if not a.size:
        return {"n": 0, "min": None, "p05": None, "median": None, "p95": None, "max": None, "mean": None}
    q = np.percentile(a, [5, 50, 95])
    return {"n": int(a.size), "min": float(a.min()), "p05": float(q[0]),
            "median": float(q[1]), "p95": float(q[2]), "max": float(a.max()), "mean": float(a.mean())}

def cadence(items):
    if len(items) < 2:
        return {"records": len(items), "median_min": None, "max_min": None}
    minutes = np.array([(b[0] - a[0]).total_seconds() / 60.0 for a, b in zip(items[:-1], items[1:])])
    return {"records": len(items), "median_min": float(np.median(minutes)), "max_min": float(minutes.max())}

def map_factors(wrf_files):
    with Dataset(wrf_files[0]) as ds:
        return (field(ds, "MAPFAC_M", 0), field(ds, "MAPFAC_U", 0), field(ds, "MAPFAC_V", 0),
                float(ds.getncattr("DX")), float(ds.getncattr("DY")))

def uh_snapshot(path, index, maps):
    mfm, mfu, mfv, dx, dy = maps
    with Dataset(path) as ds:
        z_stag = (field(ds, "PH", index) + field(ds, "PHB", index)) / G
        z_mass = destagger(z_stag, 0)
        zagl = z_mass - z_stag[0][None, :, :]
        u = destagger(field(ds, "U", index), -1)
        v = destagger(field(ds, "V", index), -2)
        w = destagger(field(ds, "W", index), 0)
    wz = termo.perfil_agl(zagl, w, ALT)
    zeta = termo.vorticidade_em_altura_agl(zagl, u, v, ALT, mfu, mfv, mfm, dx, dy)
    product = np.maximum(wz, 0.0) * zeta
    uh = np.sum(0.5 * (product[1:] + product[:-1]) * np.diff(ALT)[:, None, None], axis=0)
    valid = np.all(np.isfinite(wz), axis=0) & np.all(np.isfinite(zeta), axis=0)
    # Kernel 9-pontos ponderado equivalente ao suavizador de cal_helicity do WRF.
    uh = convolve(np.nan_to_num(uh, nan=0.0), KERNEL, mode="nearest")
    uh = np.where(valid, uh, np.nan)
    border = 6
    uh[:border, :] = np.nan
    uh[-border:, :] = np.nan
    uh[:, :border] = np.nan
    uh[:, -border:] = np.nan
    return uh

def zeta_850(path, index, maps):
    mfm, mfu, mfv, dx, dy = maps
    with Dataset(path) as ds:
        pressure = field(ds, "P", index) + field(ds, "PB", index)
        u = destagger(field(ds, "U", index), -1)
        v = destagger(field(ds, "V", index), -2)
        psfc = field(ds, "PSFC", index)
    return termo.vorticidade_em_pressao(
        pressure, u, v, 85000.0, mfu, mfv, mfm, dx, dy, psfc=psfc
    ) * 1.0e5

def native_uh(path, index):
    with Dataset(path) as ds:
        return field(ds, "UP_HELI_MAX", index) if "UP_HELI_MAX" in ds.variables else None

def compare_fields(native, derived):
    mask = np.isfinite(native) & np.isfinite(derived)
    x, y = np.asarray(native)[mask], np.asarray(derived)[mask]
    if not x.size:
        return {"n": 0, "correlation": None, "mae": None, "rmse": None, "bias_derived_minus_native": None}
    error = y - x
    x0, y0 = x - x.mean(), y - y.mean()
    denominator = np.sqrt(np.dot(x0, x0) * np.dot(y0, y0))
    return {"n": int(x.size),
            "correlation": float(np.dot(x0, y0) / denominator) if denominator else None,
            "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "bias_derived_minus_native": float(np.mean(error))}

def run(wrf_dir, out_dir):
    wrf_files = sorted(wrf_dir.glob("wrfout_d03_*"))
    aux_files = sorted(wrf_dir.glob("auxhist2_d03_*"))
    if not wrf_files or not aux_files:
        raise RuntimeError("Faltam wrfout_d03_* ou auxhist2_d03_* no artefato.")
    wrf_records, aux_records = records(wrf_files), records(aux_files)
    if not wrf_records or not aux_records:
        raise RuntimeError("Os arquivos WRF nao contem registros Times legiveis.")
    maps = map_factors(wrf_files)
    queue = deque()
    aux_pos = 0
    hourly, snapshots, vorticity = [], [], []
    native_stats = []
    comparisons = []
    for target, wrf_path, wrf_index in wrf_records:
        start = target - timedelta(hours=1)
        while aux_pos < len(aux_records) and aux_records[aux_pos][0] <= target:
            stamp, aux_path, aux_index = aux_records[aux_pos]
            aux_pos += 1
            if stamp >= start:
                uh = uh_snapshot(aux_path, aux_index, maps)
                queue.append((stamp, uh))
                snapshots.append({"utc": stamp.isoformat() + "Z", **stats(uh)})
        while queue and queue[0][0] < start:
            queue.popleft()
        if queue:
            cube = np.stack([item[1] for item in queue], axis=0)
            low = np.min(np.where(np.isfinite(cube), cube, np.inf), axis=0)
            high = np.max(np.where(np.isfinite(cube), cube, -np.inf), axis=0)
            low[~np.isfinite(low) | (low == np.inf)] = np.nan
            high[~np.isfinite(high) | (high == -np.inf)] = np.nan
            hourly.append({"valid_utc": target.isoformat() + "Z", "sample_count": len(queue),
                           "first_sample_utc": queue[0][0].isoformat() + "Z",
                           "last_sample_utc": queue[-1][0].isoformat() + "Z",
                           "uh_cyclonic_min": stats(low), "uh_anticyclonic_max": stats(high)})
            native = native_uh(wrf_path, wrf_index)
            if native is not None:
                native_stats.append({"valid_utc": target.isoformat() + "Z", **stats(native)})
                # UP_HELI_MAX e so maximo positivo: comparacao de consistencia, nao UH ciclônico.
                comparisons.append(compare_fields(native, high))
        vorticity.append({"valid_utc": target.isoformat() + "Z", **stats(zeta_850(wrf_path, wrf_index, maps))})

    with Dataset(wrf_files[0]) as ds:
        dimensions = {name: int(dim.size) for name, dim in ds.dimensions.items()}
        attributes = {name: str(getattr(ds, name)) for name in ("DX", "DY", "MAP_PROJ", "CEN_LAT", "CEN_LON") if hasattr(ds, name)}
        variables = {}
        for name in ("UP_HELI_MAX", "WSPD10MAX", "W_UP_MAX", "W_DN_MAX", "W_MEAN", "GRPL_MAX", "HAIL_MAX2D"):
            if name in ds.variables:
                var = ds.variables[name]
                variables[name] = {"dimensions": list(var.dimensions), "shape": list(var.shape), "units": getattr(var, "units", None)}
            else:
                variables[name] = None

    valid_comps = [item for item in comparisons if item["n"]]
    report = {
        "source": {"wrf_workflow_run_id": 44285670958, "artifact": "wrf-brutos-d03-2026-11-18T06"},
        "inventory": {
            "wrfout_file_count": len(wrf_files), "auxhist2_file_count": len(aux_files),
            "wrfout_record_count": len(wrf_records), "auxhist2_record_count": len(aux_records),
            "wrfout_range_utc": [wrf_records[0][0].isoformat() + "Z", wrf_records[-1][0].isoformat() + "Z"],
            "auxhist2_range_utc": [aux_records[0][0].isoformat() + "Z", aux_records[-1][0].isoformat() + "Z"],
            "wrfout_cadence": cadence(wrf_records), "auxhist2_cadence": cadence(aux_records),
            "dimensions": dimensions, "global_attributes": attributes
        },
        "nwp_variables": variables,
        "updraft_helicity_2_5km": {
            "method": "Signed integral max(w,0)*zeta dz over 2-5 km AGL; 250 m; trapezoidal; 9-point weighted smoothing after integration.",
            "hourly_sampled_windows": hourly, "auxhist2_snapshot_stats": snapshots,
            "native_UP_HELI_MAX_stats": native_stats,
            "positive_native_vs_derived_comparison_per_hour": valid_comps,
            "interpretation": "Qualitative only: UP_HELI_MAX stores a positive maximum and cannot validate the negative cyclonic UH in the Southern Hemisphere."
        },
        "vorticity_850hpa": {
            "units": "10^-5 s^-1",
            "description": "Grid-relative U/V interpolated to 850 hPa; columns with PSFC below 850 hPa are masked.",
            "records": vorticity
        },
        "limitations": [
            "This audit does not rerun WRF or verify forecast skill against observations.",
            "Derived UH is not numerically identical to WRF cal_helicity: fixed geometric AGL surfaces and first-order map-factor derivatives omit full eta-slope and staggered-vorticity-grid terms.",
            "UP_HELI_MAX is positive-only and cannot serve as the reference for negative cyclonic UH in the Southern Hemisphere.",
            "Hourly extrema are maxima/minima from 10-minute auxhist2 snapshots, not every internal WRF timestep.",
            "850-hPa vorticity is a diagnostic from the same model wind field, not independent observational validation."
        ]
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qa-wrf-diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    medians = [x["median"] for x in vorticity if x["median"] is not None]
    minima = [x["min"] for x in vorticity if x["min"] is not None]
    maxima = [x["max"] for x in vorticity if x["max"] is not None]
    markdown = [
        "# Auditoria dos diagnosticos WRF d03", "",
        f"- wrfout: **{len(wrf_files)} arquivos / {len(wrf_records)} registros**",
        f"- auxhist2: **{len(aux_files)} arquivos / {len(aux_records)} registros**",
        f"- wrfout UTC: {report['inventory']['wrfout_range_utc'][0]} a {report['inventory']['wrfout_range_utc'][1]}",
        f"- auxhist2 UTC: {report['inventory']['auxhist2_range_utc'][0]} a {report['inventory']['auxhist2_range_utc'][1]}",
        f"- Cadencia auxhist2: mediana {report['inventory']['auxhist2_cadence']['median_min']} min; maximo {report['inventory']['auxhist2_cadence']['max_min']} min",
        "", "## UH assinado 2-5 km", "",
        f"- Janelas horarias calculadas: **{len(hourly)}**",
        f"- UP_HELI_MAX nativo presente: **{'sim' if native_stats else 'nao'}**",
        "- Comparacao positiva nativa e qualitativa; nao valida UH ciclônico negativo no HS."
    ]
    if medians:
        markdown += ["", "## Vorticidade relativa em 850 hPa", "",
                     f"- Registros analisados: **{len(vorticity)}**",
                     f"- Mediana espacial por horario: {min(medians):.3f} a {max(medians):.3f} (10^-5 s^-1)",
                     f"- Extremos entre horarios: {min(minima):.3f} a {max(maxima):.3f} (10^-5 s^-1)"]
    markdown += ["", "## Limitacoes", ""] + ["- " + item for item in report["limitations"]]
    (out_dir / "qa-wrf-diagnostics.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print((out_dir / "qa-wrf-diagnostics.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrf", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=Path("qa-output"))
    args = parser.parse_args()
    run(args.wrf, args.report_dir)
