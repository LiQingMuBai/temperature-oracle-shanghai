#!/usr/bin/env python3
"""带云量/辐射/海风特征的ZSPD D+1最高温后处理模型。"""
import argparse,csv,datetime as dt,json,math,statistics,subprocess,urllib.parse
from pathlib import Path
from wu_backtest import fit,pred,bin_prob
ROOT=Path(__file__).resolve().parent;DATA=ROOT/"data";OUT=ROOT/"outputs"
MODELS=["gfs_global","ecmwf_ifs025","cma_grapes_global","jma_seamless"]
VARS=["temperature_2m","dew_point_2m","cloud_cover","shortwave_radiation","wind_speed_10m","wind_direction_10m","precipitation"]

def get(params):
    u="https://previous-runs-api.open-meteo.com/v1/forecast?"+urllib.parse.urlencode(params,safe=",")
    return json.loads(subprocess.check_output(["curl","-fsS","--retry","3","--max-time","180",u],timeout=200))

def download(start="2024-01-01",end=None):
    end=end or (dt.date.today()-dt.timedelta(days=1)).isoformat();daily={}
    names=[v+"_previous_day1" for v in VARS]
    for model in MODELS:
        by={};start_d=dt.date.fromisoformat(start);end_d=dt.date.fromisoformat(end)
        for year in range(start_d.year,end_d.year+1):
            a=max(start_d,dt.date(year,1,1));b=min(end_d,dt.date(year,12,31))
            h=get({"latitude":31.1443,"longitude":121.8083,"start_date":a.isoformat(),"end_date":b.isoformat(),
              "hourly":",".join(names),"timezone":"Asia/Shanghai","models":model})["hourly"]
            for i,t in enumerate(h["time"]):
                d=t[:10];hour=int(t[11:13]);by.setdefault(d,[]).append((hour,{v:h[v+"_previous_day1"][i] for v in VARS}))
        for d,hrs in by.items():
            valid=[(hr,x) for hr,x in hrs if x["temperature_2m"] is not None]
            if len(valid)<18:continue
            day=[x for hr,x in valid if 8<=hr<=17]; wind=[x for hr,x in valid if 11<=hr<=16]
            def avg(v,seq):
                z=[x[v] for x in seq if x[v] is not None];return statistics.mean(z) if z else None
            tmax=max(x["temperature_2m"] for hr,x in valid)
            if not -10<=tmax<=50:continue
            direction=[math.radians(x["wind_direction_10m"]) for x in wind if x["wind_direction_10m"] is not None and x["wind_speed_10m"] is not None]
            speeds=[x["wind_speed_10m"] for x in wind if x["wind_direction_10m"] is not None and x["wind_speed_10m"] is not None]
            f={"tmax":tmax,"dew":avg("dew_point_2m",day),"cloud":avg("cloud_cover",day),
               "radiation":sum(x["shortwave_radiation"] or 0 for x in day),
               "precip":sum(x["precipitation"] or 0 for hr,x in valid),
               "wind_u":statistics.mean(s*math.sin(a) for s,a in zip(speeds,direction)) if speeds else None,
               "wind_v":statistics.mean(s*math.cos(a) for s,a in zip(speeds,direction)) if speeds else None}
            if all(v is not None for v in f.values()):daily.setdefault(d,{})[model]=f
    DATA.mkdir(exist_ok=True);path=DATA/"zspd_nwp_enhanced_d1.csv"
    fields=["date"]+[f"{m}_{v}" for m in MODELS for v in ["tmax","dew","cloud","radiation","precip","wind_u","wind_v"]]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for d in sorted(daily):
            row={"date":d}
            for m,z in daily[d].items():row.update({f"{m}_{k}":round(v,4) for k,v in z.items()})
            w.writerow(row)
    return path

def load():
    actual={r["date"]:float(r["tmax_c"]) for r in csv.DictReader(open(DATA/"wu_zspd_daily_c.csv"))}
    rows=[]
    for r in csv.DictReader(open(DATA/"zspd_nwp_enhanced_d1.csv")):
        if r["date"] not in actual:continue
        models={m:{v:float(r[f"{m}_{v}"]) for v in ["tmax","dew","cloud","radiation","precip","wind_u","wind_v"]}
                for m in MODELS if r.get(f"{m}_tmax")}
        if len(models)>=3:rows.append((r["date"],actual[r["date"]],models))
    return rows

def xvec(date,models):
    d=dt.date.fromisoformat(date);a=2*math.pi*d.timetuple().tm_yday/365.2425
    means={v:statistics.mean(z[v] for z in models.values()) for v in ["tmax","dew","cloud","radiation","precip","wind_u","wind_v"]}
    spread=statistics.pstdev(z["tmax"] for z in models.values())
    hot=max(0,means["tmax"]-30)
    return [1,math.sin(a),math.cos(a)]+[models[m]["tmax"] if m in models else means["tmax"] for m in MODELS]+[
      means["dew"],means["cloud"],means["radiation"],means["precip"],means["wind_u"],means["wind_v"],spread,
      hot,hot*means["cloud"]/100,hot*means["radiation"]/5000,hot*means["wind_u"]/20]

def metrics(rows,key):
    e=[r[key]-r["actual_c"] for r in rows];n=len(e)
    return {"n":n,"mae_c":round(statistics.mean(map(abs,e)),3),"rmse_c":round(math.sqrt(statistics.mean(x*x for x in e)),3),
      "bias_c":round(statistics.mean(e),3),"exact_integer_accuracy":round(sum(round(r[key])==r["actual_c"] for r in rows)/n,3),
      "adjacent_integer_accuracy":round(sum(abs(round(r[key])-r["actual_c"])<=1 for r in rows)/n,3)}

def backtest():
    src=load();out=[];model=None;selected_alpha=35;last=-9999;residual=[]
    for i,(date,y,models) in enumerate(src):
        if i<365:continue
        if model is None or i-last>=30:
            train=src[:i];split=max(365,len(train)-180);core=train[:split];valid=train[split:]
            candidates=[]
            for alpha in [3,8,15,35,75,150]:
                trial=fit([xvec(d,m) for d,y,m in core],[y for d,y,m in core],alpha=alpha)
                errors=[pred(trial,xvec(d,m))-y for d,y,m in valid]
                loss=statistics.mean(abs(e)+.25*(round(e)!=0) for e in errors) if errors else 999
                candidates.append((loss,alpha))
            selected_alpha=min(candidates)[1]
            model=fit([xvec(d,m) for d,y,m in train],[y for d,y,m in train],alpha=selected_alpha);last=i
        p=pred(model,xvec(date,models))
        forecast_mean=statistics.mean(z["tmax"] for z in models.values())
        # 仅用过去误差校准整数档偏移和概率宽度。
        recent=residual[-180:];offset=-statistics.mean(recent) if recent else 0;offset=max(-1,min(1,offset));q=p+offset
        sigma=max(1,math.sqrt(statistics.mean(e*e for e in recent))) if recent else 2
        out.append({"date":date,"actual_c":y,"enhanced_prediction_c":round(q,3),"predicted_bin_c":round(q),
          "forecast_mean_c":round(forecast_mean,3),"model_spread_c":round(statistics.pstdev(z["tmax"] for z in models.values()),3),
          "selected_alpha":selected_alpha,"actual_bin_probability":bin_prob(round(y),q,sigma)})
        residual.append(p-y)
    base={r["date"]:r for r in csv.DictReader(open(OUT/"zspd_nwp_backtest_predictions.csv")) if r["lead_days"]=="1"}
    joined=[]
    for r in out:
        if r["date"] in base:
            r["previous_dynamic_c"]=float(base[r["date"]]["dynamic_ensemble_c"])
            r["gated_strategy_c"]=r["previous_dynamic_c"] if r["forecast_mean_c"]>=30 else r["enhanced_prediction_c"]
            joined.append(r)
    # 在线元模型：只查找当前日期之前、季节及预报温度相近的样本选择融合权重。
    for i,r in enumerate(joined):
        hist=joined[max(0,i-240):i];month=int(r["date"][5:7])
        similar=[h for h in hist if min((int(h["date"][5:7])-month)%12,(month-int(h["date"][5:7]))%12)<=2
                 and abs(h["forecast_mean_c"]-r["forecast_mean_c"])<=5]
        if len(similar)<40:similar=hist
        if i<60:weight=0 if r["forecast_mean_c"]>=30 else 1
        else:
            choices=[]
            for wi in range(11):
                w=wi/10
                loss=statistics.mean(abs((w*h["enhanced_prediction_c"]+(1-w)*h["previous_dynamic_c"])-h["actual_c"])
                  +.3*(round(w*h["enhanced_prediction_c"]+(1-w)*h["previous_dynamic_c"])!=round(h["actual_c"])) for h in similar)
                choices.append((loss,w))
            weight=min(choices)[1]
        r["online_enhanced_weight"]=weight
        r["online_meta_c"]=round(weight*r["enhanced_prediction_c"]+(1-weight)*r["previous_dynamic_c"],3)
        # 相似天气的历史残差形成离散档概率；带宽1°C，直接选概率最大整数档。
        residual_pool=[h["actual_c"]-h["online_meta_c"] for h in similar if "online_meta_c" in h]
        candidates=range(round(r["online_meta_c"])-8,round(r["online_meta_c"])+9)
        if residual_pool:
            raw={k:statistics.mean(math.exp(-.5*(k-(r["online_meta_c"]+e))**2) for e in residual_pool) for k in candidates}
        else:raw={k:math.exp(-.5*((k-r["online_meta_c"])/2)**2) for k in candidates}
        total=sum(raw.values());probs={k:v/total for k,v in raw.items()};top=max(probs,key=probs.get)
        r["discrete_bin_c"]=top;r["discrete_top_probability"]=round(probs[top],6)
        r["discrete_actual_probability"]=max(probs.get(round(r["actual_c"]),0),1e-12)
    report={"station":"ZSPD","lead":"D+1","period":[joined[0]["date"],joined[-1]["date"]],
      "enhanced_weather_features":metrics(joined,"enhanced_prediction_c"),"previous_temperature_only_dynamic":metrics(joined,"previous_dynamic_c")}
    report["enhanced_weather_features"]["mean_selected_alpha"]=round(statistics.mean(r["selected_alpha"] for r in joined),2)
    report["gated_production_strategy"]=metrics(joined,"gated_strategy_c")
    report["gated_production_strategy"]["rule"]="forecast multi-model mean >=30°C: previous dynamic ensemble; otherwise enhanced weather-feature model"
    report["online_meta_strategy"]=metrics(joined,"online_meta_c")
    report["online_meta_strategy"]["mean_enhanced_weight"]=round(statistics.mean(r["online_enhanced_weight"] for r in joined),3)
    report["online_meta_strategy"]["rule"]="past-only 240-day similarity window by season and forecast temperature; optimize MAE plus integer-bin miss penalty"
    report["discrete_temperature_bin_strategy"]=metrics(joined,"discrete_bin_c")
    report["discrete_temperature_bin_strategy"]["integer_bin_log_loss"]=round(-statistics.mean(math.log(r["discrete_actual_probability"]) for r in joined),3)
    report["discrete_temperature_bin_strategy"]["rule"]="empirical residual distribution from past similar weather; 1°C Gaussian kernel; choose highest-probability integer bin"
    report["enhanced_weather_features"]["integer_bin_log_loss"]=round(-statistics.mean(math.log(r["actual_bin_probability"]) for r in joined),3)
    hot=[r for r in joined if r["actual_c"]>=30];report["hot_days_actual_ge_30c"]={"enhanced":metrics(hot,"enhanced_prediction_c"),"previous":metrics(hot,"previous_dynamic_c")}
    OUT.mkdir(exist_ok=True)
    with (OUT/"zspd_enhanced_nwp_predictions.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=joined[0].keys());w.writeheader();w.writerows(joined)
    (OUT/"zspd_enhanced_nwp_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True);d=s.add_parser("download");d.add_argument("--start",default="2024-01-01");d.add_argument("--end");s.add_parser("backtest");a=p.parse_args()
    z={"path":str(download(a.start,a.end))} if a.cmd=="download" else backtest();print(json.dumps(z,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
