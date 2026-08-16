import Link from "next/link"

import { Button } from "@/components/ui/button"

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-24">
      <h1 className="text-4xl font-bold tracking-tight">
        Energoliczydło
      </h1>
      <p className="text-lg text-muted-foreground max-w-xl text-center">
        Narzędzie do obliczania charakterystyki energetycznej budynków metodą godzinową
        zgodnie z PN-EN ISO 52016-1 i polską metodologią.
      </p>
      <Link href="/building">
        <Button size="lg">Nowa analiza</Button>
      </Link>
    </main>
  )
}
