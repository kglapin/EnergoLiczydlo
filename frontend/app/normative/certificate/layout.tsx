import Link from "next/link"

import { Button } from "@/components/ui/button"

export default function CertificateSettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="container mx-auto flex justify-end px-4 pt-2">
        <Button variant="outline" size="sm" asChild>
          <Link href="/normative/certificate/primary-energy">
            Współczynniki energii pierwotnej i emisji
          </Link>
        </Button>
      </div>
      {children}
    </>
  )
}
