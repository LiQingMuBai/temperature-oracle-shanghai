#!/usr/bin/env python3
"""ZSPD 历史数值天气预报 D+1/D+2 无穿越回测。"""
import argparse,csv,datetime as dt,json,math,statistics,subprocess,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DATA=ROOT/"data";OUT=ROOT/"outputs"
MODELS=["gfs_global","ecmwf_ifs025","cma_grapes_global","jma_seamless"]
API="https://previous-runs-api.open-meteo.com/v1/forecast"

def get(params):
    url=API+"?"+urllib.parse.urlencode(params,safe=",")
    return json.loads(subprocess.check_output(["curl","-fsS","--retry","3","--max-time","120",url],timeout=150))

def download(start="2024-01-01",end=None):
    end=end or (dt.date.today()-dt.timedelta(days=1)).isoformat(); merged={}
    for model in MODELS:
        x=get({"latitude":31.1443,"longitude":121.8083,"start_date":start,"end_date":end,
               "hourly":"temperature_2m_previous_day1,temperature_2m_previous_day2",
               "timezone":"Asia/Shanghai","models":model})["hourly"]
        days={}
        for t,a,b in zip(x["time"],x["temperature_2m_previous_day1"],x["temperature_2m_previous_day2"]):
            d=t[:10]; days.setdefault(d,{1:[],2:[]})
            if a is not None:days[d][1].append(float(a))
            if b is not None:days[d][2].append(float(b))
        for d,v in days.items():
            merged.setdefault(d,{})
            for lead in (1,2): merged[d][f"{model}_d{lead}"]=max(v[lead]) if len(v[lead])>=18 else None
    DATA.mkdir(exist_ok=True); path=DATA/"zspd_nwp_previous_runs.csv"
    fields=["date"]+[f"{m}_d{lead}" for lead in (1,2) for m in MODELS]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for d in sorted(merged):w.writerow({"date":d,**{k:("" if v is None else round(v,2)) for k,v in merged[d].items()}})
    return path

def load_actual():
    with (DATA/"wu_zspd_daily_c.csv").open(encoding="utf-8") as f:return {r["date"]:float(r["tmax_c"]) for r in csv.DictReader(f)}
def load_nwp():
    with (DATA/"zspd_nwp_previous_runs.csv").open(encoding="utf-8") as f:return list(csv.DictReader(f))

def metrics(rows,key):
    e=[r[key]-r["actual_c"] for r in rows];n=len(e)
    return {"n":n,"mae_c":round(statistics.mean(map(abs,e)),3),"rmse_c":round(math.sqrt(statistics.mean(x*x for x in e)),3),
      "bias_c":round(statistics.mean(e),3),"exact_integer_accuracy":round(sum(round(r[key])==round(r["actual_c"]) for r in rows)/n,3),
      "adjacent_integer_accuracy":round(sum(abs(round(r[key])-round(r["actual_c"]))<=1 for r in rows)/n,3)}

def run_lead(nwp,actual,lead=1,warmup=60):
    history={m:[] for m in MODELS};ensemble_errors=[];out=[]
    for r in nwp:
        if r["date"] not in actual:continue
        raw={m:float(r[f"{m}_d{lead}"]) for m in MODELS if r.get(f"{m}_d{lead}") not in (None,"")
             and -10<=float(r[f"{m}_d{lead}"])<=50}  # ZSPD 日最高温物理质检
        if len(raw)<2:continue
        if min((len(history[m]) for m in raw),default=0)<warmup:
            for m,v in raw.items():history[m].append(v-actual[r["date"]])
            continue
        corrected={};weights={}
        for m,v in raw.items():
            h=history[m][-180:];bias=statistics.mean(h);rmse=math.sqrt(statistics.mean(e*e for e in h))
            corrected[m]=v-bias;weights[m]=1/max(rmse*rmse,.25)
        ens=sum(corrected[m]*weights[m] for m in corrected)/sum(weights.values())
        equal=statistics.mean(raw.values());sigma=max(1.,math.sqrt(statistics.mean(e*e for e in ensemble_errors[-180:]))) if ensemble_errors else 2.5
        y=actual[r["date"]];prob=.5*(math.erf((round(y)+.5-ens)/(sigma*math.sqrt(2)))-math.erf((round(y)-.5-ens)/(sigma*math.sqrt(2))))
        rec={"date":r["date"],"lead_days":lead,"actual_c":y,"equal_ensemble_c":round(equal,3),
             "dynamic_ensemble_c":round(ens,3),"predicted_bin_c":round(ens),"predictive_sigma_c":round(sigma,3),
             "actual_bin_probability":max(prob,1e-12)}
        for m in MODELS:rec[m+"_c"]=raw.get(m)
        out.append(rec);ensemble_errors.append(ens-y)
        for m,v in raw.items():history[m].append(v-y)
    return out

def backtest():
    actual=load_actual();nwp=load_nwp();allrows=[];report={"station":"ZSPD","unit":"°C","method":"fixed-lead archived forecasts; rolling bias correction and inverse-RMSE weights","leads":{}}
    for lead in (1,2):
        rows=run_lead(nwp,actual,lead);allrows+=rows
        rep={"period":[rows[0]["date"],rows[-1]["date"]],"dynamic_ensemble":metrics(rows,"dynamic_ensemble_c"),"equal_raw_ensemble":metrics(rows,"equal_ensemble_c")}
        rep["dynamic_ensemble"]["integer_bin_log_loss"]=round(-statistics.mean(math.log(r["actual_bin_probability"]) for r in rows),3)
        for m in MODELS:
            valid=[r for r in rows if r.get(m+"_c") is not None]
            if valid:rep[m]=metrics(valid,m+"_c")
        report["leads"][f"D+{lead}"]=rep
    OUT.mkdir(exist_ok=True)
    with (OUT/"zspd_nwp_backtest_predictions.csv").open("w",newline="",encoding="utf-8") as f:
        fields=list(allrows[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(allrows)
    (OUT/"zspd_nwp_backtest_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
    d=s.add_parser("download");d.add_argument("--start",default="2024-01-01");d.add_argument("--end")
    s.add_parser("backtest");a=p.parse_args()
    out={"path":str(download(a.start,a.end))} if a.cmd=="download" else backtest();print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
