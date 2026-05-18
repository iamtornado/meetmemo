"use client";

import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { User, Shield } from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage("");
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/auth/change-password`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            old_password: currentPassword,
            new_password: newPassword,
          }),
        }
      );
      if (res.ok) {
        setMessage("Password changed successfully");
        setCurrentPassword("");
        setNewPassword("");
      } else {
        const err = await res.json();
        setMessage(err.detail || "Failed to change password");
      }
    } catch {
      setMessage("Failed to change password");
    }
  };

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

        {/* Profile */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-4 w-4" />
              Profile
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <label className="text-sm text-gray-500">Email</label>
              <p className="text-sm font-medium text-gray-900">{user?.email}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">Display Name</label>
              <p className="text-sm font-medium text-gray-900">{user?.display_name}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">Role</label>
              <p className="text-sm font-medium text-gray-900">{user?.role}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">Auth Provider</label>
              <p className="text-sm font-medium text-gray-900">{user?.auth_provider}</p>
            </div>
          </CardContent>
        </Card>

        {/* Change Password */}
        {user?.auth_provider === "local" && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-4 w-4" />
                Change Password
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleChangePassword} className="space-y-3">
                <Input
                  type="password"
                  placeholder="Current password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                />
                <Input
                  type="password"
                  placeholder="New password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={6}
                />
                <Button type="submit">Change Password</Button>
                {message && (
                  <p className="text-sm text-blue-600">{message}</p>
                )}
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
