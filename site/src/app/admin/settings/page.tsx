"use client";

import { useState } from "react";

export default function AdminSettings() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setStatus("idle");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setStatus("error");
      setMessage("New passwords do not match");
      return;
    }

    if (newPassword.length < 6) {
      setStatus("error");
      setMessage("New password must be at least 6 characters");
      return;
    }

    setStatus("loading");

    try {
      const res = await fetch("/api/admin/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      const data = await res.json();

      if (res.ok) {
        setStatus("success");
        setMessage("Password changed successfully");
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
      } else {
        setStatus("error");
        setMessage(data.error || "Failed to change password");
      }
    } catch {
      setStatus("error");
      setMessage("Network error. Please try again.");
    }
  }

  return (
    <div className="max-w-xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-white/40 mt-1">Manage admin account</p>
      </div>

      <div className="glass-card p-6">
        <h3 className="text-sm font-semibold text-white/60 mb-6">Change Password</h3>

        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="text-xs text-white/40 block mb-1.5">Current Password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-neon-purple/40"
              required
            />
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1.5">New Password</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-neon-purple/40"
              required
              minLength={6}
            />
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1.5">Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-neon-purple/40"
              required
              minLength={6}
            />
          </div>

          {message && (
            <div
              className={`text-sm px-4 py-2.5 rounded-lg ${
                status === "success"
                  ? "bg-green-500/10 text-green-400 border border-green-500/20"
                  : "bg-red-500/10 text-red-400 border border-red-500/20"
              }`}
            >
              {message}
            </div>
          )}

          <button
            type="submit"
            disabled={status === "loading"}
            className="btn-primary text-sm py-2.5 px-6 disabled:opacity-50"
          >
            {status === "loading" ? "Changing..." : "Change Password"}
          </button>
        </form>
      </div>
    </div>
  );
}
