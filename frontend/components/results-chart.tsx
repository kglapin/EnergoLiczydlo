"use client"

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

interface MonthlyData {
  month: number
  heating_kwh: number
  cooling_kwh: number
  dhw_kwh: number
  internal_gains_kwh: number
  solar_gains_kwh: number
  transmission_losses_kwh: number
  ventilation_losses_kwh: number
}

interface ResultsChartProps {
  data: MonthlyData[]
}

const monthLabels = [
  "Sty",
  "Lut",
  "Mar",
  "Kwi",
  "Maj",
  "Cze",
  "Lip",
  "Sie",
  "Wrz",
  "Paź",
  "Lis",
  "Gru",
]

export function ResultsChart({ data }: ResultsChartProps) {
  const chartData = data.map((item) => ({
    name: monthLabels[item.month - 1],
    Ogrzewanie: item.heating_kwh,
    Chłodzenie: item.cooling_kwh,
    "C.W.U.": item.dhw_kwh,
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis label={{ value: "kWh/mies.", angle: -90, position: "insideLeft" }} />
        <Tooltip />
        <Legend />
        <Bar dataKey="Ogrzewanie" stackId="a" fill="#ef4444" />
        <Bar dataKey="Chłodzenie" stackId="a" fill="#3b82f6" />
        <Bar dataKey="C.W.U." stackId="a" fill="#22c55e" />
      </BarChart>
    </ResponsiveContainer>
  )
}
