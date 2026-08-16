"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { ChevronLeft } from "lucide-react"

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
}

export function AppBreadcrumb() {
  const pathname = usePathname()
  const router = useRouter()

  const current = routeMap[pathname] ?? { label: pathname, parent: "/" }

  const crumbs: { href: string; label: string; current?: boolean }[] = [
    { href: "/", label: "Strona główna" },
  ]
  if (current.parent === "/building") {
    crumbs.push({ href: "/building", label: "Nowa analiza" })
  }
  crumbs.push({ href: pathname, label: current.label, current: true })

  const canGoBack = pathname !== "/"

  return (
    <header className="container mx-auto py-4 px-4">
      <div className="flex items-center gap-4">
        {canGoBack ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => router.back()}
            className="shrink-0"
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
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
      </div>
    </header>
  )
}
