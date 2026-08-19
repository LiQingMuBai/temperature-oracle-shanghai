#!/usr/bin/env python3
"""Weather Underground ZSPD 最高温量化回测系统（仅依赖标准库）。"""
from __future__ import annotations
import argparse, csv, datetime as dt, html.parser, json, math, re, statistics, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parent; DATA=ROOT/"data"; OUT=ROOT/"outputs"
BASE="https://www.wunderground.com/history/monthly/cn/shanghai/ZSPD/date/{year}-{month}"

class TableParser(html.parser.HTMLParser):
    def __init__(self): super().__init__(); self.in_table=False; self.in_td=False; self.cell=[]; self.row=[]; self.rows=[]
    def handle_starttag(self,tag,attrs):
        cls=dict(attrs).get("class","")
        if tag=="table" and "observations-table" in cls: self.in_table=True
        elif self.in_table and tag=="tr": self.row=[]
        elif self.in_table and tag=="td": self.in_td=True; self.cell=[]
    def handle_data(self,data):
        if self.in_td: self.cell.append(data)
    def handle_endtag(self,tag):
        if self.in_table and tag=="td": self.row.append(" ".join("".join(self.cell).split())); self.in_td=False
        elif self.in_table and tag=="tr" and self.row: self.rows.append(self.row)
        elif self.in_table and tag=="table": self.in_table=False

def fetch_month(year,month):
    url=BASE.format(year=year,month=month)
    raw=subprocess.check_output(["curl","-fsSL","--retry","3","--max-time","30","-A","Mozilla/5.0 Codex research",url],timeout=45)
    p=TableParser(); p.feed(raw.decode("utf-8","replace")); out=[]
    for r in p.rows:
        if len(r)<2: continue
        try: d=dt.datetime.strptime(r[0],"%m/%d/%Y").date()
        except ValueError: continue
        nums=re.findall(r"-?\d+(?:\.\d+)?",r[1])
        if len(nums)>=2: out.append((d,float(nums[0]),float(nums[1])))
    return out

def download(start_year=2015,end_year=None,workers=4):
    end_year=end_year or dt.date.today().year
    jobs=[(y,m) for y in range(start_year,end_year+1) for m in range(1,13)
          if dt.date(y,m,1)<=dt.date.today()]
    rows=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs={ex.submit(fetch_month,y,m):(y,m) for y,m in jobs}
        for f in as_completed(fs):
            try: rows.extend(f.result())
            except Exception as e: print("WARN month",fs[f],e)
    # 当日页面在白天只含部分观测，必须排除，避免把“截至当前的最高温”当成日终最高温。
    rows=sorted({d:(d,hi,lo) for d,hi,lo in rows if d<dt.date.today()}.values())
    DATA.mkdir(exist_ok=True); path=DATA/"wu_zspd_daily_c.csv"
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["date","tmax_c","tmin_c","source"])
        for d,hi,lo in rows: w.writerow([d.isoformat(),f"{hi:g}",f"{lo:g}","Wunderground ZSPD"])
    return path,rows

def load(path=DATA/"wu_zspd_daily_c.csv"):
    with Path(path).open(encoding="utf-8") as f:
        return [(dt.date.fromisoformat(r["date"]),float(r["tmax_c"]),float(r["tmin_c"])) for r in csv.DictReader(f)]

def contiguous(rows,i,n=30): return i>=n and all((rows[j][0]-rows[j-1][0]).days==1 for j in range(i-n+1,i+1))

def features(rows,i):
    if not contiguous(rows,i,30): return None
    d=rows[i][0]; hi=[r[1] for r in rows[:i]]; lo=[r[2] for r in rows[:i]]
    a=2*math.pi*d.timetuple().tm_yday/365.2425
    return [1,math.sin(a),math.cos(a),hi[-1],hi[-2],hi[-7],lo[-1],lo[-2],lo[-7],
            statistics.mean(hi[-7:]),statistics.mean(hi[-30:]),statistics.mean(lo[-7:]),statistics.mean(lo[-30:]),
            hi[-1]-lo[-1],statistics.mean(hi[-3:])-statistics.mean(hi[-7:-4])]

def solve(a,b):
    n=len(b); m=[a[i][:]+[b[i]] for i in range(n)]
    for k in range(n):
        p=max(range(k,n),key=lambda i:abs(m[i][k])); m[k],m[p]=m[p],m[k]
        if abs(m[k][k])<1e-10:m[k][k]=1e-10
        for i in range(k+1,n):
            q=m[i][k]/m[k][k]
            for j in range(k,n+1):m[i][j]-=q*m[k][j]
    x=[0.]*n
    for i in range(n-1,-1,-1):x[i]=(m[i][n]-sum(m[i][j]*x[j] for j in range(i+1,n)))/m[i][i]
    return x

def fit(xs,ys,alpha=25):
    p=len(xs[0]); mean=[statistics.mean(x[j] for x in xs) for j in range(p)]; sd=[statistics.pstdev(x[j] for x in xs) or 1 for j in range(p)]
    mean[0]=0;sd[0]=1; z=[[(x[j]-mean[j])/sd[j] for j in range(p)] for x in xs]
    a=[[sum(r[i]*r[j] for r in z)+(alpha if i==j and i else 0) for j in range(p)] for i in range(p)]
    b=[sum(r[i]*y for r,y in zip(z,ys)) for i in range(p)]
    return solve(a,b),mean,sd

def pred(model,x):
    beta,mean,sd=model; return sum(b*(v-mean[i])/sd[i] for i,(b,v) in enumerate(zip(beta,x)))

def cdf(x,mu,sd): return .5*(1+math.erf((x-mu)/(sd*math.sqrt(2))))
def bin_prob(k,mu,sd): return max(1e-12,cdf(k+.5,mu,sd)-cdf(k-.5,mu,sd))

def calibrate_integer_model(rows,pairs,validation_days=365):
    """训练尾窗校准“岭回归分布+持续性分布”的概率混合。"""
    cut=max(365,len(pairs)-validation_days)
    base=fit([x for x,y in pairs[:cut]],[y for x,y in pairs[:cut]])
    val=[]
    # pairs 从原序列第30个有效样本开始；尾部按日期反查昨日最高温。
    date_to_hi={r[0]:r[1] for r in rows}
    for x,y in pairs[cut:]:
        # 特征中的 lag1 即昨日最高温，避免日期映射误差。
        val.append((pred(base,x),x[3],round(y)))
    if not val:return .5,2.5,2.5
    best=(1e99,.5,2.5,2.5)
    for wi in range(0,11,2):
        w=wi/10
        for s1i in range(10,41,5):
            for s2i in range(10,41,5):
                s1,s2=s1i/10,s2i/10
                loss=-statistics.mean(math.log(w*bin_prob(y,p,s1)+(1-w)*bin_prob(y,lag,s2)) for p,lag,y in val)
                if loss<best[0]:best=(loss,w,s1,s2)
    return best[1],best[2],best[3]

def score(rows,key="prediction_c"):
    err=[r[key]-r["actual_c"] for r in rows]; n=len(rows)
    out={"n":n,"mae_c":round(statistics.mean(map(abs,err)),3),"rmse_c":round(math.sqrt(statistics.mean(e*e for e in err)),3),
            "bias_c":round(statistics.mean(err),3),"within_1c":round(sum(abs(e)<=1 for e in err)/n,3),
            "within_2c":round(sum(abs(e)<=2 for e in err)/n,3),
            "exact_integer_accuracy":round(sum(round(r[key])==round(r["actual_c"]) for r in rows)/n,3),
            "adjacent_integer_accuracy":round(sum(abs(round(r[key])-round(r["actual_c"]))<=1 for r in rows)/n,3)}
    if key=="prediction_c" and "actual_bin_probability" in rows[0]:
        out["integer_bin_log_loss"]=round(-statistics.mean(math.log(r["actual_bin_probability"]) for r in rows),3)
        out["mean_predictive_sigma_c"]=round(statistics.mean(r["predictive_sigma_c"] for r in rows),3)
    return out

def backtest(rows,start_year=2020,retrain_days=30):
    result=[]; model=None; sigma=None; persistence_sigma=None; mix_weight=None; last=-99999
    for i in range(30,len(rows)):
        if rows[i][0].year<start_year or features(rows,i) is None: continue
        if model is None or i-last>=retrain_days:
            pairs=[(features(rows,j),rows[j][1]) for j in range(30,i) if features(rows,j) is not None]
            if len(pairs)<365: continue
            train_x=[x for x,y in pairs];train_y=[y for x,y in pairs]
            mix_weight,sigma,persistence_sigma=calibrate_integer_model(rows,pairs)
            model=fit(train_x,train_y)
            last=i
        p=pred(model,features(rows,i)); lag=rows[i-1][1]
        hybrid=mix_weight*p+(1-mix_weight)*lag
        candidates=range(round(min(p,lag))-10,round(max(p,lag))+11)
        probs={k:mix_weight*bin_prob(k,p,sigma)+(1-mix_weight)*bin_prob(k,lag,persistence_sigma) for k in candidates}
        top_bin=max(probs,key=probs.get)
        prior=[r[1] for r in rows[:i] if abs((r[0].timetuple().tm_yday-rows[i][0].timetuple().tm_yday+182)%365-182)<=15]
        actual_bin=round(rows[i][1])
        result.append({"date":rows[i][0].isoformat(),"actual_c":rows[i][1],"prediction_c":round(p,3),
                       "rounded_bin_c":round(p),"tmin_previous_c":rows[i-1][2],"persistence_c":rows[i-1][1],
                       "climatology_c":round(statistics.mean(prior),3),"predictive_sigma_c":round(sigma,3),
                       "actual_bin_probability":round(bin_prob(actual_bin,p,sigma),8),
                       "integer_expected_c":round(hybrid,3),"integer_model_c":top_bin,"integer_bin_c":top_bin,
                       "ridge_weight":mix_weight,"persistence_sigma_c":persistence_sigma,
                       "top_bin_probability":round(probs[top_bin],8),
                       "integer_bin_probability":round(mix_weight*bin_prob(actual_bin,p,sigma)+(1-mix_weight)*bin_prob(actual_bin,lag,persistence_sigma),8),
                       "integer_brier_score":round(sum(q*q for q in probs.values())-2*probs.get(actual_bin,0)+1,8)})
    if not result: raise RuntimeError("Not enough clean history for backtest")
    report={"station":"ZSPD","unit":"°C","target":"next-day maximum temperature","method":"expanding-window walk-forward",
            "features":"seasonality + lagged tmax/tmin + rolling means + diurnal range + trend",
            "period":[result[0]["date"],result[-1]["date"]],"ridge":score(result),
            "integer_probability_model":score(result,"integer_model_c"),
            "persistence":score(result,"persistence_c"),"seasonal_climatology":score(result,"climatology_c")}
    report["integer_probability_model"]["integer_bin_log_loss"]=round(-statistics.mean(math.log(r["integer_bin_probability"]) for r in result),3)
    report["integer_probability_model"]["multiclass_brier_score"]=round(statistics.mean(r["integer_brier_score"] for r in result),3)
    report["integer_probability_model"]["mean_ridge_weight"]=round(statistics.mean(r["ridge_weight"] for r in result),3)
    report["mae_skill_vs_persistence"]=round(1-report["ridge"]["mae_c"]/report["persistence"]["mae_c"],3)
    OUT.mkdir(exist_ok=True)
    with (OUT/"wu_zspd_backtest_predictions.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=result[0].keys());w.writeheader();w.writerows(result)
    (OUT/"wu_zspd_backtest_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    d=sub.add_parser("download");d.add_argument("--start-year",type=int,default=2015);d.add_argument("--end-year",type=int);d.add_argument("--workers",type=int,default=4)
    b=sub.add_parser("backtest");b.add_argument("--start-year",type=int,default=2020)
    a=p.parse_args()
    if a.cmd=="download": path,rows=download(a.start_year,a.end_year,a.workers);out={"path":str(path),"rows":len(rows),"period":[str(rows[0][0]),str(rows[-1][0])]}
    else: out=backtest(load(),a.start_year)
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
