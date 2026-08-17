"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Save } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  loadNormativeSettings,
  saveNormativeSettings,
  type NormativeSettings,
} from "@/lib/normative-settings"
import { useAppStore } from "@/lib/store"

function carrierValue(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined
}

export default function LegalProvenancePage() {
  const project = useAppStore((state) => state.project)
  const [settings, setSettings] = useState<NormativeSettings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setSettings(loadNormativeSettings())
  }, [])

  const usedCarriers = useMemo(() => {
    const carriers = new Set<string>()
    if (!project) return ["electricity"]
    const heating = project.systems?.heating
    if (heating && heating.system_type !== "none") {
      const carrier = carrierValue(heating.fuel_or_carrier)
      if (carrier) carriers.add(carrier)
    }
    const cooling = project.systems?.cooling
    if (cooling && cooling.system_type !== "none") {
      const carrier = carrierValue(cooling.fuel_or_carrier)
      if (carrier) carriers.add(carrier)
    }
    const dhw = project.systems?.dhw
    if (dhw && dhw.system_type !== "none") {
      const carrier = carrierValue(dhw.fuel_or_carrier)
      if (carrier) carriers.add(carrier)
    }
    carriers.add("electricity")
    return Array.from(carriers).sort()
  }, [project])

  if (!settings) {
    return <main className="mx-auto max-w-4xl px-4 py-12 text-sm text-muted-foreground">Ładowanie…</main>
  }

  const legal = settings.legal

  function updateLegal(patch: Partial<NormativeSettings["legal"]>) {
    setSettings((current) => current ? {
      ...current,
      legal: { ...current.legal, ...patch },
    } : current)
  }

  function save() {
    saveNormativeSettings(settings)
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2500)
  }

  return (
    <main className="mx-auto w-full max-w-4xl space-y-8 px-4 py-8 md:px-8 md:py-12">
      <div className="space-y-3">
        <Button variant="ghost" size="sm" asChild className="-ml-3">
          <Link href="/normative"><ArrowLeft className="mr-2 h-4 w-4" />Ustawienia normatywne</Link>
        </Button>
        <h1 className="text-3xl font-semibold tracking-tight">Tryb formalny — ślad źródłowy</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          Ta sekcja nie nadaje wynikowi statusu prawnego. Wymusza natomiast zapis danych potrzebnych
          do audytu obliczenia: daty, podstawy metodologicznej, źródła danych klimatycznych i
          pochodzenia współczynników nakładu nieodnawialnej energii pierwotnej wi.
        </p>
      </div>

      <Alert>
        <AlertTitle>Współczynniki wi</AlertTitle>
        <AlertDescription>
          W aktualnej metodologii dane dostawcy nośnika lub energii mają pierwszeństwo. Wartości
          tabelaryczne należy dokumentować jako fallback stosowany, gdy dostawca nie udostępnia
          wymaganej wartości. Wpisz rzeczywiste źródło dla każdego nośnika używanego w projekcie.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Gotowość formalna obliczenia</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <label className="flex cursor-pointer items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              checked={legal.certificate_mode}
              onChange={(event) => updateLegal({ certificate_mode: event.target.checked })}
            />
            Włącz tryb formalny — blokuj wynik przy braku wymaganych źródeł
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="calculation-date">Data obliczenia</Label>
              <Input
                id="calculation-date"
                type="date"
                value={legal.calculation_date ?? ""}
                onChange={(event) => updateLegal({
                  calculation_date: event.target.value || undefined,
                })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="methodology-source">Podstawa metodologiczna / wersja aktu</Label>
              <Input
                id="methodology-source"
                value={legal.methodology_source ?? ""}
                onChange={(event) => updateLegal({
                  methodology_source: event.target.value || undefined,
                })}
                placeholder="np. Dz.U. 2015 poz. 376 z późn. zm.; stan na dzień obliczenia"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="climate-source">Źródło danych klimatycznych</Label>
            <Input
              id="climate-source"
              value={legal.climate_data_source ?? ""}
              onChange={(event) => updateLegal({
                climate_data_source: event.target.value || undefined,
              })}
              placeholder="Nazwa zbioru, stacja, wersja/okres i źródło pliku"
            />
            <p className="text-xs text-muted-foreground">
              Sam identyfikator stacji w projekcie nie jest dowodem pochodzenia danych — zapisz tu
              źródło zestawu klimatycznego użytego w obliczeniu.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pochodzenie współczynników wi</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {usedCarriers.map((carrier) => (
            <div className="space-y-2" key={carrier}>
              <Label htmlFor={`wi-source-${carrier}`}>{carrier}</Label>
              <Input
                id={`wi-source-${carrier}`}
                value={legal.primary_energy_factor_sources[carrier] ?? ""}
                onChange={(event) => updateLegal({
                  primary_energy_factor_sources: {
                    ...legal.primary_energy_factor_sources,
                    [carrier]: event.target.value,
                  },
                })}
                placeholder="Dostawca + dokument/wartość albo jawna informacja o użyciu tabeli fallback"
              />
            </div>
          ))}
        </CardContent>
      </Card>

      {legal.certificate_mode ? (
        <Alert>
          <AlertTitle>Kontrole uruchamiane przez backend</AlertTitle>
          <AlertDescription>
            Dla budynku z kontaktem z gruntem wymagany będzie formalny model ISO 13370. Dla
            wentylacji z odzyskiem wymagany będzie szczegółowy model urządzenia ze źródłem danych.
            Jeżeli obliczasz również projektowe obciążenie cieplne, jego warunki projektowe też muszą
            być zweryfikowane. Brak któregokolwiek z tych elementów zatrzyma obliczenie zamiast
            zwrócić pozornie formalny wynik.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex justify-end">
        <Button onClick={save}><Save className="mr-2 h-4 w-4" />Zapisz ślad źródłowy</Button>
      </div>

      {saved ? (
        <p className="text-right text-sm font-medium text-emerald-700">
          Zapisano. Dane zostaną dołączone do następnego obliczenia.
        </p>
      ) : null}
    </main>
  )
}
