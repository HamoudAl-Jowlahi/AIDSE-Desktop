"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const router = useRouter();

  useEffect(() => {
    // Local-first desktop mode: redirect directly to onboarding or dashboard
    const completed = localStorage.getItem("aidse_onboarding_completed");
    if (completed === "true") {
      router.replace("/");
    } else {
      router.replace("/onboarding");
    }
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 text-slate-400 text-sm">
      <span>Redirecting to AIDSE local workspace...</span>
    </div>
  );
}
