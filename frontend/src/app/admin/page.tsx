"use client";

import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageLoading } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Shield, Users, FileText } from "lucide-react";

export default function AdminPage() {
  const { data: stats } = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: api.adminGetStats,
  });

  const { data: users } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: api.adminListUsers,
  });

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-6 flex items-center gap-4">
              <Users className="h-10 w-10 text-blue-500" />
              <div>
                <p className="text-2xl font-bold">{stats?.total_users || 0}</p>
                <p className="text-sm text-gray-500">Users</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6 flex items-center gap-4">
              <FileText className="h-10 w-10 text-green-500" />
              <div>
                <p className="text-2xl font-bold">{stats?.total_meetings || 0}</p>
                <p className="text-sm text-gray-500">Meetings</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6 flex items-center gap-4">
              <Shield className="h-10 w-10 text-purple-500" />
              <div>
                <p className="text-2xl font-bold">{users?.length || 0}</p>
                <p className="text-sm text-gray-500">Active Users</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Users table */}
        <Card>
          <CardHeader>
            <CardTitle>User Management</CardTitle>
          </CardHeader>
          <CardContent>
            {users ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 px-3 font-medium text-gray-500">Name</th>
                      <th className="text-left py-2 px-3 font-medium text-gray-500">Email</th>
                      <th className="text-left py-2 px-3 font-medium text-gray-500">Provider</th>
                      <th className="text-left py-2 px-3 font-medium text-gray-500">Role</th>
                      <th className="text-left py-2 px-3 font-medium text-gray-500">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-b border-gray-100">
                        <td className="py-2 px-3 font-medium text-gray-900">{u.display_name}</td>
                        <td className="py-2 px-3 text-gray-500">{u.email}</td>
                        <td className="py-2 px-3">
                          <Badge variant="info">{u.auth_provider}</Badge>
                        </td>
                        <td className="py-2 px-3">
                          <Badge
                            variant={u.role === "admin" ? "default" : "info"}
                          >
                            {u.role}
                          </Badge>
                        </td>
                        <td className="py-2 px-3">
                          <Badge variant={u.is_active ? "success" : "danger"}>
                            {u.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <PageLoading />
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
