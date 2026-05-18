"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoading } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { ArrowLeft } from "lucide-react";

export default function TeamDetailPage() {
  const params = useParams();
  const router = useRouter();
  const teamId = params.id as string;

  const { data: team, isLoading } = useQuery({
    queryKey: ["team", teamId],
    queryFn: () => api.getTeam(teamId),
  });

  if (isLoading) return <AppShell><PageLoading /></AppShell>;
  if (!team) return <AppShell><div className="text-center py-12 text-gray-500">Team not found</div></AppShell>;

  const roleBadge = (role: string) => {
    const variants: Record<string, "default" | "success" | "info"> = {
      owner: "default",
      editor: "success",
      viewer: "info",
    };
    return <Badge variant={variants[role] || "info"}>{role}</Badge>;
  };

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto space-y-6">
        <button
          onClick={() => router.push("/teams")}
          className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to teams
        </button>

        <div>
          <h1 className="text-2xl font-bold text-gray-900">{team.name}</h1>
          {team.description && (
            <p className="text-sm text-gray-500 mt-1">{team.description}</p>
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Members ({team.members?.length || 0})</CardTitle>
          </CardHeader>
          <CardContent>
            {team.members && team.members.length > 0 ? (
              <div className="divide-y divide-gray-100">
                {team.members.map((m) => (
                  <div
                    key={m.user_id}
                    className="flex items-center justify-between py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {m.display_name}
                      </p>
                      <p className="text-xs text-gray-500">{m.email}</p>
                    </div>
                    {roleBadge(m.role)}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400">No members</p>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
