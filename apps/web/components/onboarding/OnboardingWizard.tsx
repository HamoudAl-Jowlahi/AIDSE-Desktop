"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  Lock,
  Folder,
  CloudOff,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  HardDrive,
  Eye,
  Check,
} from "lucide-react";

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState<number>(1);

  // Form states
  const [workspacePath, setWorkspacePath] = useState<string>("Documents/AIDSE");
  const [llmJudgeEnabled, setLlmJudgeEnabled] = useState<boolean>(false);

  const handleFinish = () => {
    if (typeof window !== "undefined") {
      localStorage.setItem("aidse_onboarding_completed", "true");
      // A previous build collected a 4-digit PIN here, wrote it to localStorage
      // in cleartext, and never read it back — the lock was never enforced.
      // Remove anything it left behind on this machine.
      localStorage.removeItem("aidse_pin_code");
      localStorage.removeItem("aidse_app_lock_enabled");
      localStorage.setItem("aidse_workspace_path", workspacePath);
      localStorage.setItem("aidse_cloud_llm_judge", String(llmJudgeEnabled));
    }
    router.push("/");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6 relative overflow-hidden font-sans">
      {/* Background ambient dark glass glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Glassmorphic Container Card */}
      <div className="w-full max-w-2xl bg-slate-900/70 backdrop-blur-2xl border border-slate-800/80 rounded-2xl p-8 shadow-2xl shadow-black/80 relative z-10">
        {/* Step Progress Bar */}
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-slate-800/60">
          <div className="flex items-center gap-2.5">
            <img src="/logo.png" alt="AIDSE Logo" className="w-8 h-8 rounded-lg object-contain shadow-md shadow-cyan-500/20" />
            <span className="font-semibold text-slate-200 text-sm tracking-wide">
              First-Run Setup
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  i === step
                    ? "w-8 bg-cyan-400"
                    : i < step
                    ? "w-3 bg-cyan-800"
                    : "w-3 bg-slate-800"
                }`}
              />
            ))}
          </div>
        </div>

        {/* STEP 1: Welcome Screen */}
        {step === 1 && (
          <div className="space-y-6 text-center py-4">
            <div className="w-20 h-20 mx-auto flex items-center justify-center relative">
              <div className="absolute inset-0 bg-cyan-500/20 rounded-2xl blur-xl" />
              <img
                src="/logo.png"
                alt="AIDSE Logo"
                className="w-20 h-20 rounded-2xl object-contain relative z-10 shadow-2xl shadow-cyan-500/30"
              />
            </div>
            <div className="space-y-2">
              <h1 className="text-2xl font-bold tracking-tight text-white">
                Welcome to AIDSE Desktop
              </h1>
              <p className="text-slate-400 max-w-md mx-auto text-sm leading-relaxed">
                Analyze and evaluate your models, fully offline.
              </p>
            </div>
            <button
              onClick={() => setStep(2)}
              className="mt-6 w-full py-3.5 px-6 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/20 cursor-pointer"
            >
              <span>Get Started</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* STEP 2: Privacy Summary Screen (Replacement for Login Screen) */}
        {step === 2 && (
          <div className="space-y-6">
            <div className="space-y-1">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-cyan-400" />
                <span>Local-First Privacy Guarantee</span>
              </h2>
              <p className="text-slate-400 text-xs">
                AIDSE is built to keep your sensitive datasets and models completely private.
              </p>
            </div>

            <div className="space-y-3">
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3.5">
                <HardDrive className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-slate-200">100% On-Device Processing</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    All data processing, AutoML model fitting, and SHAP calculations happen locally on your hardware.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3.5">
                <Lock className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-slate-200">Credentials Kept in Your OS Keychain</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Any AI provider key you add is encrypted with a secret unique to this
                    machine, held in Windows Credential Manager. Your datasets are stored as
                    ordinary files in your user profile — use disk encryption to protect them.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3.5">
                <CloudOff className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-slate-200">No Account Required</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    No username, password, or cloud login is needed to use the platform.
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800/60">
              <span className="text-xs text-slate-500">
                Read our full Privacy Policy in Settings anytime.
              </span>
              <button
                onClick={() => setStep(3)}
                className="py-2.5 px-5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-sm transition-all duration-200 flex items-center gap-2 cursor-pointer"
              >
                <span>Continue</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: Workspace Path Screen */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="space-y-1">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <Folder className="w-5 h-5 text-cyan-400" />
                <span>Local Workspace Location</span>
              </h2>
              <p className="text-slate-400 text-xs">
                Confirm where AIDSE should store your local project files and datasets.
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-3">
              <label className="text-xs font-medium text-slate-300">Resolved Local Data Directory</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={workspacePath}
                  onChange={(e) => setWorkspacePath(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-cyan-300 font-mono focus:outline-none focus:border-cyan-500"
                />
              </div>
              <p className="text-[11px] text-slate-500">
                You can change or move your workspace folder anytime from Settings.
              </p>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800/60">
              <button
                onClick={() => setStep(2)}
                className="py-2.5 px-4 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
              >
                Back
              </button>
              <button
                onClick={() => setStep(4)}
                className="py-2.5 px-5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-sm transition-all duration-200 flex items-center gap-2 cursor-pointer"
              >
                <span>Next</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* STEP 5: Optional Cloud Features Screen */}
        {step === 4 && (
          <div className="space-y-6">
            <div className="space-y-1">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <CloudOff className="w-5 h-5 text-cyan-400" />
                <span>Optional Cloud Features</span>
              </h2>
              <p className="text-slate-400 text-xs">
                All cloud features are disabled by default. You control what data leaves your machine.
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="text-sm font-medium text-slate-200 flex items-center gap-2">
                    <span>LLM Judge Evaluation Strategy</span>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                      Off by default
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Sends test case prompts and expected outputs to external LLM provider API only when you run an LLM Judge evaluation.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setLlmJudgeEnabled(!llmJudgeEnabled)}
                  className={`w-12 h-6 rounded-full transition-colors p-1 flex items-center shrink-0 ${
                    llmJudgeEnabled ? "bg-cyan-500 justify-end" : "bg-slate-800 justify-start"
                  }`}
                >
                  <div className="w-4 h-4 rounded-full bg-slate-950 shadow-md" />
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800/60">
              <button
                onClick={() => setStep(3)}
                className="py-2.5 px-4 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleFinish}
                className="py-3 px-6 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm transition-all duration-200 flex items-center gap-2 shadow-lg shadow-cyan-500/20 cursor-pointer"
              >
                <Check className="w-4 h-4" />
                <span>Finish Setup & Open Dashboard</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
