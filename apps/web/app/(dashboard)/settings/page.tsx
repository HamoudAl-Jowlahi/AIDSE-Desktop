"use client";
/**
 * AIDSE Desktop Platform — Settings & Preferences Page
 * Fully customized for offline standalone desktop application.
 * Manages local application security, storage paths, hardware allocation,
 * cache cleanup, and system diagnostics.
 */
import { useEffect, useState } from "react";
import { desktopSystem, type SystemInfoResponse, type DesktopSettings } from "@/lib/api";

type TabKey = "security" | "storage" | "performance" | "appearance" | "diagnostics";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("security");

  // System and settings state
  const [info, setInfo] = useState<SystemInfoResponse | null>(null);
  const [settings, setSettings] = useState<DesktopSettings>({
    max_training_threads: 4,
    performance_mode: "balanced",
    theme: "dark",
    auto_cleanup_cache: false,
    launch_on_startup: false,
  });
  const [loadingInfo, setLoadingInfo] = useState(true);

  // Password state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordFeedback, setPasswordFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Storage actions state
  const [openFolderLoading, setOpenFolderLoading] = useState(false);
  const [clearCacheLoading, setClearCacheLoading] = useState(false);
  const [cacheFeedback, setCacheFeedback] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState(false);

  // Settings save state
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsFeedback, setSettingsFeedback] = useState<string | null>(null);

  // Load system info and desktop settings on mount
  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoadingInfo(true);
    try {
      const [sysInfo, deskSettings] = await Promise.all([
        desktopSystem.getInfo().catch(() => null),
        desktopSystem.getSettings().catch(() => null),
      ]);
      if (sysInfo) setInfo(sysInfo);
      if (deskSettings) setSettings(deskSettings);
    } catch {
      // Fallback to defaults
    } finally {
      setLoadingInfo(false);
    }
  }

  // Password strength calculation
  function calculatePasswordStrength(pass: string): { score: number; label: string; color: string } {
    if (!pass) return { score: 0, label: "Not set", color: "#64748b" };
    let score = 0;
    if (pass.length >= 6) score += 1;
    if (pass.length >= 10) score += 1;
    if (/[A-Z]/.test(pass)) score += 1;
    if (/[0-9]/.test(pass)) score += 1;
    if (/[^A-Za-z0-9]/.test(pass)) score += 1;

    if (score <= 2) return { score: 1, label: "Weak", color: "#ef4444" };
    if (score <= 3) return { score: 2, label: "Medium", color: "#f59e0b" };
    return { score: 3, label: "Very strong", color: "#10b981" };
  }

  const passStrength = calculatePasswordStrength(newPassword);

  // Change password handler
  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPasswordFeedback(null);

    if (!newPassword || newPassword.length < 6) {
      setPasswordFeedback({ type: "error", text: "New password must be at least 6 characters" });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordFeedback({ type: "error", text: "Passwords do not match" });
      return;
    }

    setPasswordLoading(true);
    try {
      const res = await desktopSystem.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordFeedback({ type: "success", text: res.message || "New password saved successfully" });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setPasswordFeedback({ type: "error", text: err.message || "Could not change the password" });
    } finally {
      setPasswordLoading(false);
    }
  }

  // Save desktop settings handler
  async function handleSaveSettings(newVals: Partial<DesktopSettings>) {
    const updated = { ...settings, ...newVals };
    setSettings(updated);
    setSavingSettings(true);
    setSettingsFeedback(null);
    try {
      await desktopSystem.updateSettings(updated);
      setSettingsFeedback("Preferences saved successfully");
      setTimeout(() => setSettingsFeedback(null), 3000);
    } catch {
      setSettingsFeedback("Could not save preferences");
    } finally {
      setSavingSettings(false);
    }
  }

  // Open storage directory in Windows Explorer
  async function handleOpenStorage() {
    setOpenFolderLoading(true);
    try {
      await desktopSystem.openStorage();
    } catch (err: any) {
      alert("Could not open the folder: " + (err.message || ""));
    } finally {
      setOpenFolderLoading(false);
    }
  }

  // Clear cache handler
  async function handleClearCache() {
    setClearCacheLoading(true);
    setCacheFeedback(null);
    try {
      const res = await desktopSystem.clearCache();
      setCacheFeedback(res.message || "Cache cleaned successfully");
      const refreshed = await desktopSystem.getInfo().catch(() => null);
      if (refreshed) setInfo(refreshed);
    } catch (err: any) {
      setCacheFeedback("Could not clean the cache: " + err.message);
    } finally {
      setClearCacheLoading(false);
    }
  }

  // Copy path helper
  function copyStoragePath() {
    if (info?.storage?.storage_dir) {
      navigator.clipboard.writeText(info.storage.storage_dir);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
    }
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1" style={{ color: "var(--color-on-surface)" }}>
            Desktop Settings
          </h1>
          <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Manage app security, local storage, AI engine performance, and appearance — all offline.
          </p>
        </div>

        {/* Engine status indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Local engine running • Port {info?.backend_port ?? 8010}</span>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 p-1 rounded-xl glass-panel overflow-x-auto">
        <button
          onClick={() => setActiveTab("security")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "security"
              ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
          }`}
        >
          <span className="material-symbols-outlined text-lg">lock</span>
          <span>Security & Password</span>
        </button>

        <button
          onClick={() => setActiveTab("storage")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "storage"
              ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
          }`}
        >
          <span className="material-symbols-outlined text-lg">folder_open</span>
          <span>Storage & Database</span>
        </button>

        <button
          onClick={() => setActiveTab("performance")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "performance"
              ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
          }`}
        >
          <span className="material-symbols-outlined text-lg">memory</span>
          <span>Performance & AI Engine</span>
        </button>

        <button
          onClick={() => setActiveTab("appearance")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "appearance"
              ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
          }`}
        >
          <span className="material-symbols-outlined text-lg">palette</span>
          <span>Appearance & Behavior</span>
        </button>

        <button
          onClick={() => setActiveTab("diagnostics")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "diagnostics"
              ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
          }`}
        >
          <span className="material-symbols-outlined text-lg">info</span>
          <span>Diagnostics & About</span>
        </button>
      </div>

      {/* TAB 1: SECURITY & PASSWORD */}
      {activeTab === "security" && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 glass-panel rounded-xl p-6 space-y-6">
            <div className="flex items-center gap-3 pb-4 border-b border-white/10">
              <span className="p-2.5 rounded-lg bg-cyan-500/10 text-cyan-400 material-symbols-outlined">
                key
              </span>
              <div>
                <h2 className="text-lg font-semibold text-white">Master Access Password</h2>
                <p className="text-xs text-slate-400">
                  Locks the AIDSE workspace on this computer. Leave the new password empty to remove the lock.
                </p>
              </div>
            </div>

            {passwordFeedback && (
              <div
                className={`p-4 rounded-lg text-sm flex items-center gap-3 ${
                  passwordFeedback.type === "success"
                    ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"
                    : "bg-red-500/10 border border-red-500/30 text-red-300"
                }`}
              >
                <span className="material-symbols-outlined">
                  {passwordFeedback.type === "success" ? "check_circle" : "error"}
                </span>
                <span>{passwordFeedback.text}</span>
              </div>
            )}

            <form onSubmit={handleChangePassword} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase text-slate-400 mb-1.5">
                  Current password
                </label>
                <div className="relative">
                  <input
                    type={showCurrentPassword ? "text" : "password"}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Leave empty if no password is set yet"
                    className="input-field pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                  >
                    <span className="material-symbols-outlined text-lg">
                      {showCurrentPassword ? "visibility_off" : "visibility"}
                    </span>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-mono uppercase text-slate-400 mb-1.5">
                  New password
                </label>
                <div className="relative">
                  <input
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="At least 6 characters, or empty to remove the lock"
                    className="input-field pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                  >
                    <span className="material-symbols-outlined text-lg">
                      {showNewPassword ? "visibility_off" : "visibility"}
                    </span>
                  </button>
                </div>

                {/* Password Strength Indicator */}
                {newPassword && (
                  <div className="mt-2 space-y-1">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-400">Password strength:</span>
                      <span style={{ color: passStrength.color }} className="font-medium">
                        {passStrength.label}
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden flex gap-1">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${(passStrength.score / 3) * 100}%`,
                          backgroundColor: passStrength.color,
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-mono uppercase text-slate-400 mb-1.5">
                  Confirm new password
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter the new password"
                  className="input-field"
                />
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  type="submit"
                  disabled={passwordLoading}
                  className="btn-primary flex items-center gap-2"
                >
                  {passwordLoading ? (
                    <>
                      <span className="w-4 h-4 rounded-full border-2 border-slate-900 border-t-transparent animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-sm">lock_reset</span>
                      <span>Save password</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Quick Security Toggles */}
          <div className="space-y-6">
            <div className="glass-panel rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2 pb-2 border-b border-white/10">
                <span className="material-symbols-outlined text-cyan-400 text-base">shield</span>
                <span>Maintenance</span>
              </h3>

              <div className="space-y-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.auto_cleanup_cache}
                    onChange={(e) => handleSaveSettings({ auto_cleanup_cache: e.target.checked })}
                    className="mt-1 rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-cyan-500"
                  />
                  <div>
                    <span className="text-sm font-medium text-slate-200 block">Clean cached files periodically</span>
                    <span className="text-xs text-slate-400">Remove temporary experiment output to free disk space.</span>
                  </div>
                </label>
              </div>

              {settingsFeedback && (
                <div className="text-xs text-emerald-400 pt-2 flex items-center gap-1">
                  <span className="material-symbols-outlined text-sm">check</span>
                  <span>{settingsFeedback}</span>
                </div>
              )}
            </div>

            <div className="glass-panel rounded-xl p-5 space-y-2 border-cyan-500/20 bg-cyan-950/20">
              <div className="flex items-center gap-2 text-cyan-400 font-semibold text-xs uppercase tracking-wider">
                <span className="material-symbols-outlined text-sm">verified_user</span>
                <span>How your password is stored</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Your master password is hashed with <strong>bcrypt</strong> and stored in the local SQLite database on this machine. Nothing is sent to any server. The database file itself is not encrypted, so rely on disk encryption to protect the data it holds.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: STORAGE & DATABASE */}
      {activeTab === "storage" && (
        <div className="space-y-6">
          {/* Storage Path Card */}
          <div className="glass-panel rounded-xl p-6 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span className="material-symbols-outlined text-cyan-400">folder</span>
                  <span>Local storage location</span>
                </h2>
                <p className="text-xs text-slate-400">
                  Where datasets, trained models, and experiment records are kept.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={copyStoragePath}
                  className="btn-ghost flex items-center gap-1.5 text-xs"
                >
                  <span className="material-symbols-outlined text-sm">
                    {copiedPath ? "done" : "content_copy"}
                  </span>
                  <span>{copiedPath ? "Copied" : "Copy path"}</span>
                </button>

                <button
                  onClick={handleOpenStorage}
                  disabled={openFolderLoading}
                  className="btn-primary flex items-center gap-2 text-xs"
                >
                  <span className="material-symbols-outlined text-sm">launch</span>
                  <span>Open in File Explorer</span>
                </button>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-950/80 border border-white/10 font-mono text-xs text-cyan-300 select-all break-all">
              {info?.storage?.storage_dir || "%LOCALAPPDATA%\AIDSE-Desktop\storage"}
            </div>
          </div>

          {/* Disk usage bar & stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="glass-card rounded-xl p-4">
              <span className="text-xs text-slate-400 font-mono uppercase block mb-1">Datasets</span>
              <div className="text-2xl font-bold text-cyan-300">
                {info?.storage?.datasets_size_mb ?? 0} <span className="text-xs text-slate-400 font-normal">MB</span>
              </div>
              <span className="text-xs text-slate-500 mt-1 block">CSV, Parquet, Excel files</span>
            </div>

            <div className="glass-card rounded-xl p-4">
              <span className="text-xs text-slate-400 font-mono uppercase block mb-1">Models & experiments</span>
              <div className="text-2xl font-bold text-cyan-300">
                {info?.storage?.models_size_mb ?? 0} <span className="text-xs text-slate-400 font-normal">MB</span>
              </div>
              <span className="text-xs text-slate-500 mt-1 block">MLflow & AutoML Trials</span>
            </div>

            <div className="glass-card rounded-xl p-4">
              <span className="text-xs text-slate-400 font-mono uppercase block mb-1">Local database</span>
              <div className="text-2xl font-bold text-cyan-300">
                {info?.storage?.db_size_mb ?? 0} <span className="text-xs text-slate-400 font-normal">MB</span>
              </div>
              <span className="text-xs text-slate-500 mt-1 block">SQLite (aidse.db • WAL Mode)</span>
            </div>

            <div className="glass-card rounded-xl p-4">
              <span className="text-xs text-slate-400 font-mono uppercase block mb-1">Temporary files</span>
              <div className="text-2xl font-bold text-cyan-300">
                {info?.storage?.cache_size_mb ?? 0} <span className="text-xs text-slate-400 font-normal">MB</span>
              </div>
              <span className="text-xs text-slate-500 mt-1 block">Scratch & Optuna Cache</span>
            </div>
          </div>

          {/* Disk capacity bar */}
          {info?.storage && (
            <div className="glass-panel rounded-xl p-5 space-y-3">
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-300 font-medium">Available disk space</span>
                <span className="text-cyan-400 font-mono">
                  {info.storage.disk_free_gb} GB free of {info.storage.disk_total_gb} GB
                </span>
              </div>
              <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(5, info.storage.disk_used_percent))}%` }}
                />
              </div>
            </div>
          )}

          {/* Cache Cleaning Card */}
          <div className="glass-panel rounded-xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <span className="material-symbols-outlined text-amber-400">mop</span>
                <span>Cache cleanup</span>
              </h3>
              <p className="text-xs text-slate-400">
                Deletes temporary files and leftover plots from AutoML runs. Your datasets and trained models are untouched.
              </p>
              {cacheFeedback && (
                <div className="text-xs text-emerald-400 pt-2 flex items-center gap-1">
                  <span className="material-symbols-outlined text-sm">check_circle</span>
                  <span>{cacheFeedback}</span>
                </div>
              )}
            </div>

            <button
              onClick={handleClearCache}
              disabled={clearCacheLoading}
              className="btn-ghost border border-amber-500/30 text-amber-300 hover:bg-amber-500/10 flex items-center gap-2 whitespace-nowrap"
            >
              <span className="material-symbols-outlined text-base">cleaning_services</span>
              <span>{clearCacheLoading ? "Cleaning..." : "Clean temporary files now"}</span>
            </button>
          </div>
        </div>
      )}

      {/* TAB 3: PERFORMANCE & AI ENGINE */}
      {activeTab === "performance" && (
        <div className="space-y-6">
          <div className="glass-panel rounded-xl p-6 space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-cyan-400">tune</span>
                <span>CPU threads for AutoML</span>
              </h2>
              <p className="text-xs text-slate-400">
                How many CPU cores training and hyperparameter search may use.
              </p>
            </div>

            <div className="space-y-4 p-4 rounded-xl bg-slate-950/40 border border-white/5">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-slate-200">Cores used for training:</span>
                <span className="px-3 py-1 rounded-full bg-cyan-500/20 text-cyan-300 font-mono text-sm font-bold border border-cyan-500/30">
                  {settings.max_training_threads} cores
                </span>
              </div>

              <input
                type="range"
                min="1"
                max={info?.hardware?.cpu_cores || 8}
                value={settings.max_training_threads}
                onChange={(e) => handleSaveSettings({ max_training_threads: parseInt(e.target.value) })}
                className="w-full accent-cyan-400 cursor-pointer"
              />

              <div className="flex justify-between text-xs text-slate-500 font-mono">
                <span>1 core (power saving)</span>
                <span>Available on this machine: {info?.hardware?.cpu_cores ?? 4} cores</span>
              </div>
            </div>

            {/* Performance Profile */}
            <div className="space-y-3">
              <label className="text-sm font-medium text-slate-200 block">Performance profile</label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div
                  onClick={() => handleSaveSettings({ performance_mode: "balanced" })}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    settings.performance_mode === "balanced"
                      ? "bg-cyan-500/10 border-cyan-500/40 shadow-sm"
                      : "glass-card hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-sm text-white flex items-center gap-2">
                      <span className="material-symbols-outlined text-cyan-400 text-base">balance</span>
                      <span>Balanced (recommended)</span>
                    </span>
                    {settings.performance_mode === "balanced" && (
                      <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
                    )}
                  </div>
                  <p className="text-xs text-slate-400">
                    Trains quickly while leaving room for the rest of your system.
                  </p>
                </div>

                <div
                  onClick={() => handleSaveSettings({ performance_mode: "max" })}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    settings.performance_mode === "max"
                      ? "bg-cyan-500/10 border-cyan-500/40 shadow-sm"
                      : "glass-card hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-sm text-white flex items-center gap-2">
                      <span className="material-symbols-outlined text-amber-400 text-base">bolt</span>
                      <span>Maximum performance</span>
                    </span>
                    {settings.performance_mode === "max" && (
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                    )}
                  </div>
                  <p className="text-xs text-slate-400">
                    Uses every available core for large models and SHAP explanations.
                  </p>
                </div>
              </div>
            </div>

            {/* Hardware specifications overview */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              <div className="p-3.5 rounded-lg bg-slate-950/40 border border-white/5 space-y-1">
                <span className="text-xs text-slate-400 font-mono">Total CPU cores</span>
                <div className="text-lg font-bold text-white">{info?.hardware?.cpu_cores ?? "—"} Cores</div>
              </div>
              <div className="p-3.5 rounded-lg bg-slate-950/40 border border-white/5 space-y-1">
                <span className="text-xs text-slate-400 font-mono">Total memory</span>
                <div className="text-lg font-bold text-white">{info?.hardware?.total_ram_gb ?? "—"} GB</div>
              </div>
              <div className="p-3.5 rounded-lg bg-slate-950/40 border border-white/5 space-y-1">
                <span className="text-xs text-slate-400 font-mono">Memory available</span>
                <div className="text-lg font-bold text-emerald-400">{info?.hardware?.available_ram_gb ?? "—"} GB</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: APPEARANCE & SYSTEM BEHAVIOR */}
      {activeTab === "appearance" && (
        <div className="space-y-6">
          <div className="glass-panel rounded-xl p-6 space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-cyan-400">palette</span>
                <span>Display theme</span>
              </h2>
              <p className="text-xs text-slate-400">
                Choose how AIDSE looks.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div
                onClick={() => handleSaveSettings({ theme: "dark" })}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  settings.theme === "dark"
                    ? "bg-cyan-500/10 border-cyan-500/40 shadow-sm"
                    : "glass-card hover:border-white/20"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-white flex items-center gap-2">
                    <span className="material-symbols-outlined text-cyan-400 text-base">dark_mode</span>
                    <span>Dark (recommended)</span>
                  </span>
                  {settings.theme === "dark" && <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />}
                </div>
                <p className="text-xs text-slate-400">Easier on the eyes during long analysis sessions.</p>
              </div>

              <div
                onClick={() => handleSaveSettings({ theme: "light" })}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  settings.theme === "light"
                    ? "bg-cyan-500/10 border-cyan-500/40 shadow-sm"
                    : "glass-card hover:border-white/20"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-white flex items-center gap-2">
                    <span className="material-symbols-outlined text-amber-400 text-base">light_mode</span>
                    <span>Light</span>
                  </span>
                  {settings.theme === "light" && <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />}
                </div>
                <p className="text-xs text-slate-400">High-contrast light background for bright rooms.</p>
              </div>

              <div
                onClick={() => handleSaveSettings({ theme: "system" })}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  settings.theme === "system"
                    ? "bg-cyan-500/10 border-cyan-500/40 shadow-sm"
                    : "glass-card hover:border-white/20"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-white flex items-center gap-2">
                    <span className="material-symbols-outlined text-slate-400 text-base">settings_brightness</span>
                    <span>Match Windows</span>
                  </span>
                  {settings.theme === "system" && <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />}
                </div>
                <p className="text-xs text-slate-400">Follows your Windows light or dark setting.</p>
              </div>
            </div>

            {/* Desktop Startup Behavior */}
            <div className="pt-4 border-t border-white/10 space-y-4">
              <h3 className="text-sm font-semibold text-white">Startup</h3>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.launch_on_startup}
                  onChange={(e) => handleSaveSettings({ launch_on_startup: e.target.checked })}
                  className="mt-1 rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-cyan-500"
                />
                <div>
                  <span className="text-sm font-medium text-slate-200 block">Start AIDSE automatically with Windows</span>
                  <span className="text-xs text-slate-400">Adds AIDSE to your Windows startup items so projects open faster.</span>
                </div>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: ABOUT & SYSTEM DIAGNOSTICS */}
      {activeTab === "diagnostics" && (
        <div className="space-y-6">
          <div className="glass-panel rounded-xl p-6 space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500/20 to-teal-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-300 font-bold text-xl">
                  AI
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">AIDSE — AI Data Scientist & Evaluation Platform</h2>
                  <p className="text-xs text-slate-400 font-mono">
                    {info?.edition || "Standalone Desktop Edition"} • v{info?.app_version || "0.1.0"}
                  </p>
                </div>
              </div>

              <button
                onClick={loadData}
                disabled={loadingInfo}
                className="btn-ghost flex items-center gap-2 text-xs"
              >
                <span className="material-symbols-outlined text-sm">refresh</span>
                <span>Refresh</span>
              </button>
            </div>

            {/* Diagnostics grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="glass-card rounded-xl p-4 space-y-2">
                <span className="text-xs font-mono uppercase text-cyan-400 block font-semibold">Local environment</span>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between py-1 border-b border-white/5">
                    <span className="text-slate-400">Operating system:</span>
                    <span className="text-white font-mono">{info?.environment?.os ?? "Windows"}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-white/5">
                    <span className="text-slate-400">Architecture:</span>
                    <span className="text-white font-mono">{info?.environment?.arch ?? "x86_64"}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-white/5">
                    <span className="text-slate-400">Python version:</span>
                    <span className="text-white font-mono">{info?.environment?.python_version ?? "3.14"}</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-slate-400">Network:</span>
                    <span className="text-emerald-400 font-mono">Fully offline</span>
                  </div>
                </div>
              </div>

              <div className="glass-card rounded-xl p-4 space-y-2">
                <span className="text-xs font-mono uppercase text-cyan-400 block font-semibold">Bundled AI libraries</span>
                <div className="space-y-1 text-xs">
                  {info?.ml_libraries ? (
                    Object.entries(info.ml_libraries).map(([name, ver]) => (
                      <div key={name} className="flex justify-between py-1 border-b border-white/5 last:border-0">
                        <span className="text-slate-400 capitalize">{name}:</span>
                        <span className="text-cyan-300 font-mono font-medium">v{ver}</span>
                      </div>
                    ))
                  ) : (
                    <span className="text-slate-500">Loading versions...</span>
                  )}
                </div>
              </div>
            </div>

            {/* Copyright and publisher info */}
            <div className="pt-4 border-t border-white/10 flex flex-col md:flex-row justify-between items-center text-xs text-slate-500 gap-2 font-mono">
              <span>© 2026 eMind Work — AIDSE Platform. All rights reserved.</span>
              <span>Standalone Executable Package</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
