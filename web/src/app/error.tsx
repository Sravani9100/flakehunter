"use client";

import { Button, ErrorNotice } from "@/components/ui";

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="space-y-4">
      <ErrorNotice message={error.message || "Something went wrong."} />
      <Button variant="secondary" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
