"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { ChevronLeft, FileCheck2, Settings2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"

const routeMap: Record<string, { label: string; parent?: string }> = {
  "/": { label: "Strona główna" },
  "/building": { label: "Dane budynku", parent: "/" },
  "/results": { label: "Wyniki obliczeń", parent: "/building" },
  "/normative": { label: "Zaawansowane ustawienia obliczeniowe", parent: "/building" },
  "/normative/legal": { label: "Dane źródłowe formalnego obliczenia", parent: "/normative" },
  "/normative/certificate": { label: "Miesięczne dane formalnej charakterystyki", parent: "/normative/legal" },
  "/normative/certificate/primary-energy": {
    label: "Współczynniki energii pierwotnej i emisji",
    parent: "/normative/certificate",
  },
}

function buildCrumbs(pathname: string) {
  const crumbs: { href: string; label: string; current?: boolean }[] = []
  const visited = new Set<string>()
  let currentPath: string | undefined = pathname

  while (currentPath && !visited.has(currentPath)) {
    visited.add(currentPath)
    const entry = routeMap[currentPath] ?? { label: currentPath, parent: "/" }
    crumbs.unshift({ href: currentPath, label: entry.label })
    currentPath = entry.parent
  }

  if (crumbs[0]?.href !== "/") {
    crumbs.unshift({ href: "/", label: "Strona główna" })
  }

  if (crumbs.length > 0) {
    crumbs[crumbs.length - 1] = { ...crumbs[crumbs.length - 1], current: true }
  }

  return crumbs
}

export function AppBreadcrumb() {
  const pathname = usePathname()
  const router = useRouter()
  const crumbs = buildCrumbs(pathname)
  const canGoBack = pathname !== "/"

  return (
    <header className="container mx-auto px-4 py-4">
      <div className="flex flex-wrap items-center gap-3">
        {canGoBack ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => router.back()}
            className="shrink-0"
          >
            <ChevronLeft className="mr-1 h-4 w-4" />
            Wstecz
          </Button>
        ) : null}
        <Breadcrumb>
          <BreadcrumbList>
            {crumbs.map((crumb, index) => (
              <React.Fragment key={crumb.href}>
                <BreadcrumbItem>
                  {crumb.current ? (
                    <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink href={crumb.href}>{crumb.label}</BreadcrumbLink>
                  )}
                </BreadcrumbItem>
                {index < crumbs.length - 1 ? <BreadcrumbSeparator /> : null}
              </React.Fragment>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {pathname !== "/normative" ? (
            <Button variant="outline" size="sm" asChild className="shrink-0">
              <a href="/normative">
                <Settings2 className="mr-2 h-4 w-4" />
                Zaawansowane ustawienia
              </a>
            </Button>
          ) : null}
          {pathname !== "/normative/legal" ? (
            <Button variant="outline" size="sm" asChild className="shrink-0">
              <a href="/normative/legal">
                <FileCheck2 className="mr-2 h-4 w-4" />
                Dane formalnego obliczenia
              </a>
            </Button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
