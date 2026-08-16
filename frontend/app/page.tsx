"use client"

import Link from "next/link"
import { ArrowRight, FolderOpen, Pencil, Plus, Trash2 } from "lucide-react"
import { useRouter } from "next/navigation"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAppStore } from "@/lib/store"

const savedAtFormatter = new Intl.DateTimeFormat("pl-PL", {
  dateStyle: "medium",
  timeStyle: "short",
})

function formatSavedAt(savedAt: string) {
  const date = new Date(savedAt)
  return Number.isNaN(date.getTime()) ? "Nieznana data zapisu" : savedAtFormatter.format(date)
}

export default function Home() {
  const router = useRouter()
  const history = useAppStore((state) => state.history)
  const loadHistoryItem = useAppStore((state) => state.loadHistoryItem)
  const removeHistoryItem = useAppStore((state) => state.removeHistoryItem)

  function handleLoad(id: string) {
    loadHistoryItem(id)
    router.push(`/building?history=${encodeURIComponent(id)}`)
  }

  function handleRemove(id: string, projectName: string) {
    if (window.confirm(`Usunąć zapisany projekt „${projectName}”?`)) {
      removeHistoryItem(id)
    }
  }

  return (
    <main className="container mx-auto max-w-6xl px-4 py-10 md:py-16">
      <section className="mb-12 flex flex-col gap-8 rounded-2xl border bg-card p-6 shadow-sm md:flex-row md:items-end md:justify-between md:p-10">
        <div className="max-w-2xl">
          <Badge variant="secondary" className="mb-4">
            PN-EN ISO 52016-1
          </Badge>
          <h1 className="text-4xl font-bold tracking-tight md:text-5xl">Energoliczydło</h1>
          <p className="mt-4 text-lg leading-8 text-muted-foreground">
            Oblicz charakterystykę energetyczną budynku metodą godzinową i wracaj do
            zapisanych analiz, kiedy chcesz.
          </p>
        </div>
        <Button asChild size="lg" className="shrink-0">
          <Link href="/building?new=1">
            <Plus className="mr-2 h-4 w-4" />
            Nowa analiza
          </Link>
        </Button>
      </section>

      <section aria-labelledby="saved-projects-heading">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div>
            <h2 id="saved-projects-heading" className="text-2xl font-semibold tracking-tight">
              Zapisane projekty
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Wybierz projekt, aby otworzyć jego dane i kontynuować edycję.
            </p>
          </div>
          {history.length > 0 ? <Badge variant="outline">{history.length}</Badge> : null}
        </div>

        {history.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center px-6 py-14 text-center">
              <div className="mb-4 rounded-full bg-muted p-3">
                <FolderOpen className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
              </div>
              <h3 className="text-lg font-semibold">Nie masz jeszcze zapisanych projektów</h3>
              <p className="mt-2 max-w-md text-sm text-muted-foreground">
                Projekt pojawi się tutaj automatycznie po rozpoczęciu edycji i będzie
                dostępny do dalszej pracy na tym urządzeniu.
              </p>
              <Button asChild variant="outline" className="mt-6">
                <Link href="/building?new=1">
                  Rozpocznij pierwszą analizę
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {history.map((item) => (
              <Card key={item.id}>
                <CardHeader className="gap-3 pb-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-lg">
                      {item.project_name || "Projekt bez nazwy"}
                    </CardTitle>
                    <CardDescription className="mt-1 truncate">
                      {item.building_name || "Budynek bez nazwy"} · Zapisano {formatSavedAt(item.savedAt)}
                    </CardDescription>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button type="button" size="sm" onClick={() => handleLoad(item.id)}>
                      <Pencil className="mr-2 h-4 w-4" />
                      Edytuj
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      aria-label={`Usuń projekt ${item.project_name || "bez nazwy"}`}
                      onClick={() => handleRemove(item.id, item.project_name || "bez nazwy")}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  {item.result ? (
                    <div className="grid grid-cols-3 gap-3 rounded-md bg-muted/50 p-3 sm:max-w-md">
                      <div>
                        <p className="text-xs uppercase tracking-wide text-muted-foreground">EU</p>
                        <p className="mt-1 font-semibold">
                          {item.eu?.toFixed(1)} <span className="text-xs font-normal text-muted-foreground">kWh/m²</span>
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-wide text-muted-foreground">EK</p>
                        <p className="mt-1 font-semibold">
                          {item.ek?.toFixed(1)} <span className="text-xs font-normal text-muted-foreground">kWh/m²</span>
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-wide text-muted-foreground">EP</p>
                        <p className="mt-1 font-semibold">
                          {item.ep?.toFixed(1)} <span className="text-xs font-normal text-muted-foreground">kWh/m²</span>
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
                      Wersja robocza — wynik pojawi się po uruchomieniu obliczeń.
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
