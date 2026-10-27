import type { ApexOptions } from 'apexcharts'
import ReactApexChart from 'react-apexcharts'
import type { DepthPoint } from '../../types/quant'
import Card from './Card'

export default function DepthAreaChart({ points }: { points: DepthPoint[] }) {
  const series = [
    { name: 'Bid depth', data: points.map((p) => [p.price, p.bid]) },
    { name: 'Ask depth', data: points.map((p) => [p.price, p.ask]) },
  ]
  const options: ApexOptions = {
    chart: { type: 'area', background: 'transparent', toolbar: { show: false }, animations: { enabled: true, speed: 300 } },
    theme: { mode: 'dark' }, colors: ['#24da89', '#ff5e7d'],
    stroke: { curve: 'stepline', width: 2 }, fill: { type: 'gradient', gradient: { opacityFrom: .42, opacityTo: .04 } },
    dataLabels: { enabled: false }, grid: { borderColor: '#26324d', strokeDashArray: 4 },
    xaxis: { type: 'numeric', min: 0, max: 1, tickAmount: 5, labels: { formatter: (v) => `${(Number(v) * 100).toFixed(0)}¢`, style: { colors: '#8390a8' } } },
    yaxis: { labels: { formatter: (v) => `$${v.toFixed(0)}`, style: { colors: '#8390a8' } } },
    legend: { position: 'top', horizontalAlign: 'right', labels: { colors: '#c8d1e5' } },
    tooltip: { x: { formatter: (v) => `${(Number(v ?? 0) * 100).toFixed(1)}¢` }, y: { formatter: (v) => `$${(v ?? 0).toFixed(2)}` } },
  }
  return (
    <Card title="买卖盘深度 / Order Book Depth" subtitle="Cumulative executable liquidity" className="min-h-[390px]">
      <ReactApexChart options={options} series={series} type="area" height={310} />
    </Card>
  )
}
