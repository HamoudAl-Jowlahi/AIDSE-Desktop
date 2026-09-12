"use client";
/**
 * AIDSE Platform — Dashboard Layout (authenticated app shell)
 * Wraps all dashboard pages with Sidebar + TopBar + auth guard.
 * ml-72 offset for the fixed 288px sidebar.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import LockScreen, { useAppLock } from "@/components/layout/LockScreen";
import { useAuth } from "@/lib/auth";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const { state: lockState, unlock } = useAppLock();
  const router = useRouter();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const completed = localStorage.getItem("aidse_onboarding_completed");
      if (completed !== "true") {
        router.replace("/onboarding");
      }
    }
  }, [router]);

  if (isLoading || lockState === "checking") {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--color-background)" }}
      >
        <div className="flex flex-col items-center gap-4 animate-fade-in">
          <div
            className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: "var(--color-primary-container)" }}
          />
          <span className="text-sm mono" style={{ color: "var(--color-on-surface-variant)" }}>
            Loading AIDSE...
          </span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  // Gate the whole workspace, so no dashboard content renders behind the lock.
  if (lockState === "locked") {
    return <LockScreen onUnlock={unlock} />;
  }

  return (
    <div className="min-h-screen flex overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col" style={{ marginLeft: "18rem" }}>
        <TopBar />
        <main className="flex-1 overflow-y-auto p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
}
