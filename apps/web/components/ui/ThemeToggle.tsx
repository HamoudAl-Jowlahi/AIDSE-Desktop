"use client";
/**
 * AIDSE Platform — Theme toggle
 *
 * globals.css carries a complete `.light` palette (every one of the 47 colour
 * tokens is overridden, plus the glass, button, input and badge components),
 * but the root layout pinned forcedTheme="dark" and this component returned
 * null — so the light theme was fully built and completely unreachable, and
 * the theme selector in Settings changed nothing.
 */
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // next-themes only knows the real theme after hydration; rendering the icon
  // before that would flash the wrong one.
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme !== "light";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="p-1.5 rounded-lg transition-colors hover:bg-white/5 flex items-center justify-center"
      style={{ color: "var(--color-on-surface-variant)" }}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
    >
      <span className="material-symbols-outlined">
        {mounted ? (isDark ? "light_mode" : "dark_mode") : "light_mode"}
      </span>
    </button>
  );
}
