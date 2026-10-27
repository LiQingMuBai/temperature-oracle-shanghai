export type ProbabilityPoint = { timestamp: number; yes: number; no: number }
export type DepthPoint = { price: number; bid: number; ask: number }

export type ArbitrageRow = {
  id: string
  market: string
  outcome: string
  polymarket: number
  reference: number
  premium: number
  volume: number
  signal: 'BUY_POLY' | 'SELL_POLY' | 'WATCH'
  source: 'MODEL_REFERENCE'
  updatedAt: number
}

export type QuantPayload = {
  generatedAt: number
  selectedEvent: { title: string; outcome: string; eventSlug: string }
  metrics: { pnl: number; exposure: number; activeArbitrage: number; gasFeePol: number | null }
  probability: ProbabilityPoint[]
  depth: DepthPoint[]
  arbitrage: ArbitrageRow[]
  trackedAccounts: string[]
  dataMode: 'LIVE_WITH_MODEL_REFERENCE'
}
