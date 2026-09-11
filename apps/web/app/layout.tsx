/**
 * AIDSE Platform — Root Layout
 * Uses CSS variable fonts declared in globals.css.
 * Note: next/font/google is avoided since it requires network access to Google
 * Fonts CDN at build time — fonts are loaded via <link> in globals.css instead.
 */
import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "AIDSE — AI Data Scientist & Evaluation Platform",
  description:
    "Unified platform for AI model evaluation, regression detection, AutoML, explainability, and MLOps monitoring.",
  keywords: ["AI evaluation", "MLOps", "AutoML", "model monitoring", "AIDSE"],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        {/* Inter + JetBrains Mono + Material Symbols via Google Fonts CDN */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
        />
      </head>
      <body className="min-h-full antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          forcedTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
