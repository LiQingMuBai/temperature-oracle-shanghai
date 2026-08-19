#!/usr/bin/env python3
"""ZSPD 最高温概率与 Polymarket 实时订单簿融合（标准库）。"""
import argparse, csv, datetime as dt, json, math, re, statistics, subprocess, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ["best_match", "ecmwf_ifs025", "gfs_global", "cma_grapes_global", "jma_seamless"]

def get(url):
    raw = subprocess.check_output(["curl", "-fsS", "-A", "Mozilla/5.0 Codex-research", url], timeout=30)
    return json.loads(raw)

def forecast(model, target_date):
    days=max(1,(dt.date.fromisoformat(target_date)-dt.date.today()).days+1)
    q = urllib.parse.urlencode({"latitude":31.1443,"longitude":121.8083,
        "daily":"temperature_2m_max","forecast_days":days,"timezone":"Asia/Shanghai","models":model})
    d=get("https://api.open-meteo.com/v1/forecast?"+q)["daily"]
    return float(d["temperature_2m_max"][d["time"].index(target_date)])

def normal_cdf(x, mu, sigma): return .5*(1+math.erf((x-mu)/(sigma*math.sqrt(2))))

def wx_probs(mu, sigma, labels):
    p={}
    for label in labels:
        x=int(re.search(r"-?\d+",label).group())
        if "below" in label:p[label]=normal_cdf(x+.5,mu,sigma)
        elif "higher" in label:p[label]=1-normal_cdf(x-.5,mu,sigma)
        else:p[label]=normal_cdf(x+.5,mu,sigma)-normal_cdf(x-.5,mu,sigma)
    return p

def executable(levels, dollars, ascending):
    lv = sorted([(float(x["price"]),float(x["size"])) for x in levels], reverse=not ascending)
    cost=shares=0.0
    for price,size in lv:
        take=min(size,(dollars-cost)/price) if price else 0
        cost += take*price; shares += take
        if cost >= dollars-.001: break
    return round(cost/shares,4) if shares else None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--slug",default="highest-temperature-in-shanghai-on-july-31-2026")
    ap.add_argument("--date",help="YYYY-MM-DD; defaults to date parsed from slug")
    args=ap.parse_args(); slug=args.slug
    target=args.date
    if not target:
        z=re.search(r"-(january|february|march|april|may|june|july|august|september|october|november|december)-(\d+)-(\d{4})$",slug)
        if not z: raise SystemExit("Cannot parse date; pass --date")
        months="january february march april may june july august september october november december".split()
        target=f"{int(z.group(3)):04d}-{months.index(z.group(1))+1:02d}-{int(z.group(2)):02d}"
    event=get("https://gamma-api.polymarket.com/events/slug/"+slug)
    fs={m:forecast(m,target) for m in MODELS}
    vals=sorted(fs.values()); median=vals[len(vals)//2]
    mad=sorted(abs(v-median) for v in vals)[len(vals)//2];robust_spread=1.4826*mad
    raw_mu=.5*median+.5*fs["best_match"]
    mu=raw_mu;sigma=max(1.15,math.sqrt(.7**2+robust_spread**2));calibration={}
    # 若已有真实D+1回测，使用最近180期误差进行与生产模型一致的偏差校正及逆RMSE加权。
    hist_path=ROOT/"outputs"/"zspd_nwp_backtest_predictions.csv"
    if hist_path.exists():
        rows=[r for r in csv.DictReader(hist_path.open()) if r["lead_days"]=="1"][-180:]
        mapped={m:m for m in ["gfs_global","ecmwf_ifs025","cma_grapes_global","jma_seamless"]}
        corrected={};weights={}
        for m in mapped:
            errors=[float(r[m+"_c"])-float(r["actual_c"]) for r in rows if r.get(m+"_c") not in (None,"") and -10<=float(r[m+"_c"])<=50]
            if errors and m in fs:
                bias=statistics.mean(errors);rmse=math.sqrt(statistics.mean(e*e for e in errors))
                corrected[m]=fs[m]-bias;weights[m]=1/max(rmse*rmse,.25);calibration[m]={"bias_c":round(bias,2),"corrected_c":round(corrected[m],2)}
        if corrected:
            calibrated_mu=sum(corrected[m]*weights[m] for m in corrected)/sum(weights.values())
            # Guard against historical bias corrections overwhelming today's raw NWP consensus.
            mu=max(raw_mu-1.0,min(raw_mu+1.0,calibrated_mu))
            calibration["ensemble"]={"uncapped_center_c":round(calibrated_mu,2),
                "raw_center_c":round(raw_mu,2),"applied_center_c":round(mu,2),"max_shift_c":1.0}
            past_errors=[float(r["dynamic_ensemble_c"])-float(r["actual_c"]) for r in rows]
            sigma=max(1.,math.sqrt(statistics.mean(e*e for e in past_errors)))
    labels=[m["groupItemTitle"] for m in event["markets"]]
    weather=wx_probs(mu,sigma,labels)
    rows=[]
    for m in event["markets"]:
        ids=json.loads(m["clobTokenIds"]) if isinstance(m["clobTokenIds"],str) else m["clobTokenIds"]
        b=get("https://clob.polymarket.com/book?token_id="+ids[0])
        bids=sorted([(float(x["price"]),float(x["size"])) for x in b["bids"]],reverse=True)
        asks=sorted([(float(x["price"]),float(x["size"])) for x in b["asks"]])
        bid=bids[0][0] if bids else 0; ask=asks[0][0] if asks else 1
        # 触价微价格：对更薄一侧更敏感；最终跨合约归一化。
        bs=bids[0][1] if bids else 0; az=asks[0][1] if asks else 0
        # 单边盘口时微价格会机械坍缩到0/1，改用中点避免把“无买单”误作零概率。
        micro=(ask*bs+bid*az)/(bs+az) if bs and az else (bid+ask)/2
        rows.append({"outcome":m["groupItemTitle"],"best_bid":bid,"best_ask":ask,
            "spread":round(ask-bid,4),"bid_size":bs,"ask_size":az,"micro":micro,
            "ask_levels":[{"price":p,"size":s} for p,s in asks],
            "buy_100_vwap":executable(b["asks"],100,True),"weather_prob":weather[m["groupItemTitle"]]})
    sm=sum(r["micro"] for r in rows)
    for r in rows: r["market_prob"]=r["micro"]/sm
    # 几何池减少同一气象信息被重复计数；气象65%，盘口/深度35%。
    raw=[max(r["weather_prob"],1e-8)**.65*max(r["market_prob"],1e-8)**.35 for r in rows]; z=sum(raw)
    for r,x in zip(rows,raw):
        r["fused_prob"]=x/z; r["edge_vs_ask"]=r["fused_prob"]-r["best_ask"]
        r["edge_at_100_vwap"]=(r["fused_prob"]-r["buy_100_vwap"]) if r["buy_100_vwap"] is not None else None
    rows.sort(key=lambda r:r["fused_prob"],reverse=True)
    out={"as_of":dt.datetime.now().astimezone().isoformat(),"contract_date":target,"slug":slug,
         "event_end_at":event.get("endDate"),
         "station":"Shanghai Pudong International Airport (ZSPD)","model_forecasts_c":fs,
         "weather_center_c":round(mu,2),"robust_model_spread_c":round(robust_spread,2),
         "raw_weather_center_c":round(raw_mu,2),
         "weather_sigma_c":round(sigma,2),"rolling_bias_calibration":calibration,
         "fusion":"65% weather / 35% depth-adjusted market (log pool)",
         "ranking":rows,"note":"Read-only analysis; prices move and fees/slippage are not fully represented."}
    outpath=ROOT/"outputs"/("polymarket_"+slug+".json")
    outpath.parent.mkdir(exist_ok=True); outpath.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
