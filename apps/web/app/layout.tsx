/**
 * AIDSE Platform — Root Layout
 *
 * Fonts are declared in globals.css and served from public/fonts. There is
 * deliberately no <link> to fonts.googleapis.com here: this app runs offline,
 * and pulling the icon font over the network meant every icon showed as its
 * ligature name ("dashboard", "lock") on any machine without a connection.
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
      <head />

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
