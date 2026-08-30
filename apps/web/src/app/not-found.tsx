import Link from "next/link";
import { Compass } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";

export default function NotFound() {
  return (
    <AppShell>
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-hairline bg-surface-subtle text-fg-faint">
          <Compass className="h-6 w-6" />
        </div>
        <div className="label-mono">404</div>
        <h1 className="display-lg font-bold text-fg">PAGE NOT FOUND</h1>
        <p className="max-w-md text-sm text-fg-muted">
          This route doesn&apos;t exist in RECON OS. Check the URL, or head back to the
          Command Center.
        </p>
        <Link
          href="/"
          className="mt-2 inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          Return to Command Center
        </Link>
      </div>
    </AppShell>
  );
}
