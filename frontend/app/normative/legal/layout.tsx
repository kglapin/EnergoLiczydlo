import Link from "next/link"

import { Button } from "@/components/ui/button"

export default function FormalSettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="container mx-auto flex justify-end px-4 pt-2">
        <Button variant="outline" size="sm" asChild>
          <Link href="/normative/certificate">Miesięczne dane formalnej charakterystyki</Link>
        </Button>
      </div>
      {children}
    </>
  )
}
