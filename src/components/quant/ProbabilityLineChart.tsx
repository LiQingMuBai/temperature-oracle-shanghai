import type { ApexOptions } from 'apexcharts'
import ReactApexChart from 'react-apexcharts'
import type { ProbabilityPoint } from '../../types/quant'
import Card from './Card'

export default function ProbabilityLineChart({ title, points }: { title: string; points: ProbabilityPoint[] }) {
  const series = [
    { name: 'YES', data: points.map((p) => [p.timestamp * 1000, p.yes]) },
    { name: 'NO', data: points.map((p) => [p.timestamp * 1000, p.no]) },
  ]
  const options: ApexOptions = {
    chart: { type: 'line', background: 'transparent', toolbar: { show: false }, animations: { enabled: true, speed: 350 } },
    theme: { mode: 'dark' },
    colors: ['#24da89', '#ff5e7d'],
    stroke: { curve: 'smooth', width: 3 },
    markers: { size: 0 },
    grid: { borderColor: '#26324d', strokeDashArray: 4 },
    xaxis: { type: 'datetime', labels: { style: { colors: '#8390a8' }, datetimeUTC: false }, axisBorder: { show: false }, axisTicks: { show: false } },
    yaxis: { min: 0, max: 100, tickAmount: 4, labels: { formatter: (v) => `${v.toFixed(0)}%`, style: { colors: '#8390a8' } } },
    legend: { position: 'top', horizontalAlign: 'right', labels: { colors: '#c8d1e5' } },
    tooltip: { x: { format: 'HH:mm:ss' }, y: { formatter: (v) => `${(v ?? 0).toFixed(2)}%` } },
  }
  return (
    <Card title="隐含概率走势 / Implied Probability" subtitle={title} className="min-h-[390px]">
      <ReactApexChart options={options} series={series} type="line" height={310} />
    </Card>
  )
}
