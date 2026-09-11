"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
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

  return null;
}
