"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageLoading } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { Shield, Users, FileText, KeyRound } from "lucide-react";

export default function AdminPage() {
  const queryClient = useQueryClient();
  const [groupName, setGroupName] = useState("");
  const [mappedRole, setMappedRole] = useState("member");
  const [mappingError, setMappingError] = useState("");

  const { data: stats } = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: api.adminGetStats,
  });

  const { data: users } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: api.adminListUsers,
  });

  const { data: mappings } = useQuery({
    queryKey: ["admin", "auth-mappings"],
    queryFn: api.adminListAuthMappings,
  });

  const createMapping = useMutation({
    mutationFn: () =>
      api.adminCreateAuthMapping({
        group_name: groupName.trim(),
        mapped_role: mappedRole,
      }),
    onSuccess: () => {
      setGroupName("");
      setMappingError("");
      queryClient.invalidateQueries({ queryKey: ["admin", "auth-mappings"] });
    },
    onError: (e: Error) => setMappingError(e.message),
  });

  const deleteMapping = useMutation({
    mutationFn: (id: string) => api.adminDeleteAuthMapping(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "auth-mappings"] });
    },
  });

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>

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

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5" />
              AD Group → Role Mappings
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-gray-500">
              Map Active Directory security group names to MeetMemo roles. Users
              receive the highest matched role on LDAP login.
            </p>

            <form
              className="flex flex-wrap gap-3 items-end"
              onSubmit={(e) => {
                e.preventDefault();
                if (!groupName.trim()) return;
                createMapping.mutate();
              }}
            >
              <div className="flex-1 min-w-[200px]">
                <label className="text-xs text-gray-500 block mb-1">
                  AD Group Name (cn)
                </label>
                <Input
                  placeholder="e.g. MeetMemo-Admins"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                />
              </div>
              <div className="w-36">
                <label className="text-xs text-gray-500 block mb-1">Role</label>
                <Select
                  value={mappedRole}
                  onChange={(e) => setMappedRole(e.target.value)}
                  options={[
                    { value: "admin", label: "admin" },
                    { value: "editor", label: "editor" },
                    { value: "member", label: "member" },
                    { value: "viewer", label: "viewer" },
                  ]}
                />
              </div>
              <Button type="submit" loading={createMapping.isPending}>
                Add Mapping
              </Button>
            </form>

            {mappingError && (
              <p className="text-sm text-red-600">{mappingError}</p>
            )}

            {mappings ? (
              mappings.length === 0 ? (
                <p className="text-sm text-gray-400">No mappings configured yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200">
                        <th className="text-left py-2 px-3 font-medium text-gray-500">
                          Provider
                        </th>
                        <th className="text-left py-2 px-3 font-medium text-gray-500">
                          AD Group
                        </th>
                        <th className="text-left py-2 px-3 font-medium text-gray-500">
                          Role
                        </th>
                        <th className="text-right py-2 px-3 font-medium text-gray-500">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {mappings.map((m) => (
                        <tr key={m.id} className="border-b border-gray-100">
                          <td className="py-2 px-3">
                            <Badge variant="info">{m.auth_provider}</Badge>
                          </td>
                          <td className="py-2 px-3 font-medium text-gray-900">
                            {m.group_name}
                          </td>
                          <td className="py-2 px-3">
                            <Badge
                              variant={m.mapped_role === "admin" ? "default" : "info"}
                            >
                              {m.mapped_role}
                            </Badge>
                          </td>
                          <td className="py-2 px-3 text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => deleteMapping.mutate(m.id)}
                              loading={deleteMapping.isPending}
                            >
                              Remove
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : (
              <PageLoading />
            )}
          </CardContent>
        </Card>

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
