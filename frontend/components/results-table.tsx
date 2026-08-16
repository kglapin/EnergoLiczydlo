"use client"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

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

interface ResultsTableProps {
  data: MonthlyData[]
}

export function ResultsTable({ data }: ResultsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Miesiąc</TableHead>
          <TableHead className="text-right">Ogrzewanie (kWh)</TableHead>
          <TableHead className="text-right">Chłodzenie (kWh)</TableHead>
          <TableHead className="text-right">C.W.U. (kWh)</TableHead>
          <TableHead className="text-right">Zyski wewn. (kWh)</TableHead>
          <TableHead className="text-right">Zyski słoneczne (kWh)</TableHead>
          <TableHead className="text-right">Straty przenikanie (kWh)</TableHead>
          <TableHead className="text-right">Straty wentylacja (kWh)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((row) => (
          <TableRow key={row.month}>
            <TableCell>{row.month}</TableCell>
            <TableCell className="text-right">{row.heating_kwh.toFixed(1)}</TableCell>
            <TableCell className="text-right">{row.cooling_kwh.toFixed(1)}</TableCell>
            <TableCell className="text-right">{row.dhw_kwh.toFixed(1)}</TableCell>
            <TableCell className="text-right">{row.internal_gains_kwh.toFixed(1)}</TableCell>
            <TableCell className="text-right">{row.solar_gains_kwh.toFixed(1)}</TableCell>
            <TableCell className="text-right">{row.transmission_losses_kwh.toFixed(1)}</TableCell>
            <TableCell className="text-right">{row.ventilation_losses_kwh.toFixed(1)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
