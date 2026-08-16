import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"

import { AppBreadcrumb } from "@/components/app-breadcrumb"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Energoliczydło – Charakterystyka energetyczna budynku",
  description: "Obliczenia charakterystyki energetycznej budynków metodą godzinową PN-EN ISO 52016-1",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pl">
      <body className={inter.className}>
        <AppBreadcrumb />
        {children}
      </body>
    </html>
  )
}
