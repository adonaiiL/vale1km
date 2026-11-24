#!/usr/bin/env python3
"""Auditoria independente da termodinâmica WRF versus MetPy."""
import argparse, csv, json, sys
from datetime import datetime
from pathlib import Path
import numpy as np
import netCDF4
import metpy.calc as mpcalc
from metpy.units import units

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import termo

RD,RV,CP,T0,G=287.0,461.5,1004.5,300.0,9.81
KAPPA=RD/CP

def sfloat(x):
    try:
        a=float(np.asarray(x).squeeze())
        return a if np.isfinite(a) else None
    except Exception: return None

def mval(x,u):
    try: return sfloat(x.to(u).magnitude)
    except Exception: return sfloat(x)

def z_at(p,pp,zz):
    if p is None: return None
    good=np.isfinite(pp)&np.isfinite(zz)
    pp,zz=pp[good],zz[good]
    if len(pp)<2 or p>pp[0] or p<pp[-1]: return None
    return sfloat(np.interp(-np.log(p),-np.log(pp),zz))

def metpy_calc(kind,p,t,td,z):
    out={"method":"MetPy","parcel":kind}
    P=p*units.hPa; T=t*units.degC; Td=td*units.degC
    try:
        if kind=="SB": p0,t0,td0,idx=P[0],T[0],Td[0],0
        elif kind=="ML": p0,t0,td0=mpcalc.mixed_parcel(P,T,Td,depth=100*units.hPa);idx=None
        else: p0,t0,td0,idx=mpcalc.most_unstable_parcel(P,T,Td,depth=300*units.hPa)
        prof=mpcalc.parcel_profile(P,t0,td0)
        cape,cin=mpcalc.cape_cin(P,T,Td,prof)
        lp,_=mpcalc.lcl(p0,t0,td0)
        try: fp,_=mpcalc.lfc(P,T,Td,parcel_temperature_profile=prof,which="bottom")
        except Exception: fp=np.nan*units.hPa
        try: ep,_=mpcalc.el(P,T,Td,parcel_temperature_profile=prof,which="top")
        except Exception: ep=np.nan*units.hPa
        out.update(index=int(idx) if idx is not None else None,p0_hPa=mval(p0,"hPa"),
          T0_C=mval(t0,"degC"),Td0_C=mval(td0,"degC"),cape_Jkg=mval(cape,"J/kg"),
          cin_Jkg=mval(cin,"J/kg"),lcl_hPa=mval(lp,"hPa"),lfc_hPa=mval(fp,"hPa"),
          el_hPa=mval(ep,"hPa"),lcl_m=z_at(mval(lp,"hPa"),p,z),
          lfc_m=z_at(mval(fp,"hPa"),p,z),el_m=z_at(mval(ep,"hPa"),p,z))
    except Exception as e: out["error"]=f"{type(e).__name__}: {e}"
    return out

def vale_calc(kind,p,T,r,z):
    pe,te,re,ze=(x[:,None] for x in (p,T,r,z))
    if kind=="MU":
        p0,t0,r0,idx,valid=termo.parcela_mu(pe,te,re,ze)
        index=int(idx[0]) if valid[0] else None
    else: p0,t0,r0=termo.parcelas(pe,te,re,ze,kind);index=0
    o=termo.cape_cin(pe,te,re,ze,p0,t0,r0,dp=250.)
    return {"method":"Vale1Km","parcel":kind,"index":index,
      "p0_hPa":sfloat(p0[0]/100),"T0_C":sfloat(t0[0]-273.15),
      "Td0_C":sfloat(termo.dewpoint(p0[0],r0[0])-273.15) if np.isfinite(r0[0]) else None,
      "r0_gkg":sfloat(r0[0]*1000),"cape_Jkg":sfloat(o["cape"][0]),
      "cin_Jkg":sfloat(o["cin"][0]),"lcl_hPa":sfloat(o["plcl"][0]/100),
      "lcl_m":sfloat(o["lcl_z"][0]),"lfc_m":sfloat(o["lfc_z"][0]),
      "el_m":sfloat(o["el_z"][0])}

def read_column(file,when,lat,lon):
    with netCDF4.Dataset(file) as nc:
        ts=netCDF4.chartostring(nc.variables["Times"][:])
        times=[datetime.strptime(str(x),"%Y-%m-%d_%H:%M:%S") for x in ts]
        it=min(range(len(times)),key=lambda k:abs((times[k]-when).total_seconds()))
        delta=abs((times[it]-when).total_seconds())
        if delta>1800: raise RuntimeError(f"Sem horário {when}; mais próximo {times[it]}")
        la=np.asarray(nc.variables["XLAT"][it],float);lo=np.asarray(nc.variables["XLONG"][it],float)
        dist=(la-lat)**2+((lo-lon)*np.cos(np.radians(lat)))**2
        j,i=np.unravel_index(np.nanargmin(dist),dist.shape)
        p=np.asarray(nc.variables["P"][it,:,j,i],float)+np.asarray(nc.variables["PB"][it,:,j,i],float)
        thm=np.asarray(nc.variables["T"][it,:,j,i],float)+T0
        r=np.asarray(nc.variables["QVAPOR"][it,:,j,i],float)
        ph=np.asarray(nc.variables["PH"][it,:,j,i],float)+np.asarray(nc.variables["PHB"][it,:,j,i],float)
        zs=ph/G;z=.5*(zs[:-1]+zs[1:])-float(nc.variables["HGT"][it,j,i])
        # Conversão oficial use_theta_m=1: th_dry = thm/(1+Rv/Rd*QVAPOR).
        T=thm/(1+(RV/RD)*r)*(p/1e5)**KAPPA
        T161=thm/(1+1.61*r)*(p/1e5)**KAPPA
        Tunc=thm*(p/1e5)**KAPPA
        ps=float(nc.variables["PSFC"][it,j,i]);t2=float(nc.variables["T2"][it,j,i])
        q2=float(nc.variables["Q2"][it,j,i]);td2=float(termo.dewpoint(ps,q2))
        td=termo.dewpoint(p,r)
        ok=np.isfinite(p)&(p>9000)&np.isfinite(T)&(T>150)&(T<350)&np.isfinite(r)&(r>=0)&np.isfinite(z)
        p,r,T,z,td,thm,T161,Tunc=(x[ok] for x in (p,r,T,z,td,thm,T161,Tunc))
        order=np.argsort(p)[::-1]
        p,r,T,z,td,thm,T161,Tunc=(x[order] for x in (p,r,T,z,td,thm,T161,Tunc))
        return {"time":times[it].isoformat(),"delta":delta,
         "grid":{"j":int(j),"i":int(i),"lat":sfloat(la[j,i]),"lon":sfloat(lo[j,i]),
          "distance_km":sfloat(np.hypot((la[j,i]-lat)*111,(lo[j,i]-lon)*111*np.cos(np.radians(lat))))},
         "p":p,"r":r,"T":T,"z":z,"Td":td,"T161":T161,"Tunc":Tunc,
         "PSFC":ps,"T2":t2,"Q2":q2,"Td2":td2}

def audit(file,when,lat,lon):
    d=read_column(file,when,lat,lon)
    p,r,T,z,td=(d[k] for k in ("p","r","T","z","Td"))
    ph=p/100;tc=T-273.15;tdc=td-273.15;tdcap=np.minimum(tdc,tc)
    vale=[vale_calc(k,p,T,r,z) for k in ("SB","ML","MU")]
    met=[metpy_calc(k,ph,tc,tdcap,z) for k in ("SB","ML","MU")]
    # Surface parcel based on PSFC/T2/Q2, with an explicit surface boundary.
    p2=np.r_[d["PSFC"]/100,ph];t2=np.r_[d["T2"]-273.15,tc]
    td2=np.r_[min(d["Td2"]-273.15,d["T2"]-273.15),tdcap];z2=np.r_[0.,z]
    m2=metpy_calc("SB",p2,t2,td2,z2)
    return {"requested":{"lat":lat,"lon":lon},"time":d["time"],"grid":d["grid"],
      "surface":{"PSFC_hPa":d["PSFC"]/100,"T2_C":d["T2"]-273.15,"Q2_gkg":d["Q2"]*1000,
       "Td2_C":d["Td2"]-273.15,"first_mass_z_m":sfloat(z[0]),
       "first_mass_T_C":sfloat(tc[0]),"first_mass_Td_C":sfloat(tdc[0]),
       "first_mass_Td_minus_T_C":sfloat(tdc[0]-tc[0])},
      "profile":{"levels":len(p),"pressure_monotonic":bool(np.all(np.diff(ph)<0)),
       "height_monotonic":bool(np.all(np.diff(z)>0)),
       "supersaturated":int(np.sum(tdc>tc+.05)),
       "supersaturated_fraction":float(np.mean(tdc>tc+.05)),
       "max_Td_minus_T_C":sfloat(np.max(tdc-tc)),
       "T_lowest_C":sfloat(tc[0]),"Td_lowest_C":sfloat(tdc[0]),
       "max_T_difference_1_61_vs_exact_K":sfloat(np.max(np.abs(d["T161"]-T))),
       "max_T_difference_without_moist_correction_K":sfloat(np.max(np.abs(d["Tunc"]-T)))},
      "Vale1Km":vale,"MetPy":met,"MetPy_surface_2m":m2,
      "_profile":{"p_hPa":ph,"z_m":z,"T_C":tc,"Td_C":tdc,"QVAPOR_gkg":r*1000}}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--wrf",required=True)
    ap.add_argument("--time",default="2026-11-24T18");ap.add_argument("--out",default="sondagem-audit")
    a=ap.parse_args();when=datetime.strptime(a.time,"%Y-%m-%dT%H")
    files=sorted(Path(a.wrf).glob("wrfout_d03_*"))
    if not files: raise SystemExit("wrfout_d03 não encontrado")
    rec=[]
    for f in files:
        with netCDF4.Dataset(f) as nc:
            for k,s in enumerate(netCDF4.chartostring(nc.variables["Times"][:])):
                dt=datetime.strptime(str(s),"%Y-%m-%d_%H:%M:%S")
                rec.append((abs((dt-when).total_seconds()),f))
    if not rec: raise SystemExit("Sem timestamps no WRF")
    rec.sort(key=lambda x:x[0]);delta,file=rec[0]
    if delta>1800: raise SystemExit(f"Horário mais próximo difere {delta/60:.0f} minutos")
    pts=[("Vale_A",-26.91,-49.08),("Pivotal_near",-27.0,-49.0)]
    reports=[audit(file,when,lat,lon) for _,lat,lon in pts]
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    for (name,_,_),report in zip(pts,reports):
        prof=report.pop("_profile")
        with (out/f"{name}_profile.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f);w.writerow(["p_hPa","z_m_AGL","T_C","Td_C","QVAPOR_gkg"])
            w.writerows(zip(prof["p_hPa"],prof["z_m"],prof["T_C"],prof["Td_C"],prof["QVAPOR_gkg"]))
    reference={"SFC":{"CAPE":1198,"CIN":0,"LCL":670,"LFC":670,"EL":13285},
      "ML":{"CAPE":1116,"CIN":-14,"LCL":728,"LFC":866,"EL":12613},
      "FCST":{"CAPE":1756,"CIN":-6,"LCL":1290,"LFC":1290,"EL":13110},
      "MU":{"CAPE":189,"CIN":0,"LCL":670,"LFC":670,"EL":13285}}
    data={"time_requested":when.isoformat(),"file":str(file),"record_delta_seconds":delta,
      "points":{pts[k][0]:reports[k] for k in range(len(pts))},
      "Pivotal_capture_reference":reference}
    (out/"report.json").write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    lines=["# Auditoria da sondagem: Vale1Km × MetPy × Pivotal",""]
    for (name,_,_),rep in zip(pts,reports):
        lines += [f"## {name}: WRF grid {rep['grid']['lat']:.4f}, {rep['grid']['lon']:.4f} ({rep['grid']['distance_km']:.2f} km)",
         f"- Superfície: PSFC {rep['surface']['PSFC_hPa']:.1f} hPa, T2 {rep['surface']['T2_C']:.2f} °C, Td2 {rep['surface']['Td2_C']:.2f} °C.",
         f"- Primeiro nível: z {rep['surface']['first_mass_z_m']:.1f} m, T {rep['surface']['first_mass_T_C']:.2f} °C, Td {rep['surface']['first_mass_Td_C']:.2f} °C.",
         f"- Supersaturação: {rep['profile']['supersaturated']}/{rep['profile']['levels']} níveis; máximo Td−T {rep['profile']['max_Td_minus_T_C']:.2f} °C.",
         f"- Coeficiente 1.61 versus Rv/Rd exato: diferença máxima de T {rep['profile']['max_T_difference_1_61_vs_exact_K']:.4f} K.",
         "","| Algoritmo | Parcela | CAPE | CIN | LCL m | LFC m | EL m |","|---|---|---:|---:|---:|---:|---:|"]
        for x in rep["Vale1Km"]+rep["MetPy"]+([rep["MetPy_surface_2m"]] if name=="Vale_A" else []):
            lines.append(f"| {x['method']} | {x['parcel']} | {x.get('cape_Jkg')} | {x.get('cin_Jkg')} | {x.get('lcl_m')} | {x.get('lfc_m')} | {x.get('el_m')} |")
        lines.append("")
    lines += ["## Referência da captura Pivotal","",
      "| Parcela | CAPE | CIN | LCL | LFC | EL |","|---|---:|---:|---:|---:|---:|"]
    for k,v in reference.items(): lines.append(f"| {k} | {v['CAPE']} | {v['CIN']} | {v['LCL']} | {v['LFC']} | {v['EL']} |")
    lines += ["","A captura Pivotal é referência visual, não o mesmo ponto WRF; MetPy sobre a mesma coluna separa diferença de algoritmo de diferença espacial/modelo.",""]
    (out/"report.md").write_text("\n".join(lines),encoding="utf-8");print((out/"report.md").read_text())

if __name__=="__main__": main()
