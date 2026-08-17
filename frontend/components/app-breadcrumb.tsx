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
  "/building": { label: "Nowa analiza", parent: "/" },
  "/results": { label: "Wyniki", parent: "/building" },
  "/normative": { label: "Ustawienia normatywne", parent: "/building" },
  "/normative/legal": { label: "Tryb formalny", parent: "/normative" },
}

export function AppBreadcrumb() {
  const pathname = usePathname()
  const router = useRouter()

  const current = routeMap[pathname] ?? { label: pathname, parent: "/" }

  const crumbs: { href: string; label: string; current?: boolean }[] = [
    { href: "/", label: "Strona główna" },
  ]
  if (current.parent === "/building" || current.parent === "/normative") {
    crumbs.push({ href: "/building", label: "Nowa analiza" })
  }
  if (current.parent === "/normative") {
    crumbs.push({ href: "/normative", label: "Ustawienia normatywne" })
  }
  crumbs.push({ href: pathname, label: current.label, current: true })

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
                Ustawienia normatywne
              </a>
            </Button>
          ) : null}
          {pathname !== "/normative/legal" ? (
            <Button variant="outline" size="sm" asChild className="shrink-0">
              <a href="/normative/legal">
                <FileCheck2 className="mr-2 h-4 w-4" />
                Tryb formalny
              </a>
            </Button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
