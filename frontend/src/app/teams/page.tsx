"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { PageLoading } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { Plus, Users, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

export default function TeamsPage() {
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();
  const router = useRouter();

  const { data: teams, isLoading } = useQuery({
    queryKey: ["teams"],
    queryFn: api.listTeams,
  });

  const createMutation = useMutation({
    mutationFn: () => api.createTeam({ name, description: description || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      setShowCreate(false);
      setName("");
      setDescription("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteTeam(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["teams"] }),
  });

  if (isLoading) return <AppShell><PageLoading /></AppShell>;

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Teams</h1>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create Team
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {teams?.map((team) => (
            <Card
              key={team.id}
              className="cursor-pointer hover:border-blue-200 transition-colors"
              onClick={() => router.push(`/teams/${team.id}`)}
            >
              <CardHeader className="flex flex-row items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-gray-400" />
                  <CardTitle>{team.name}</CardTitle>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("Delete this team?")) deleteMutation.mutate(team.id);
                  }}
                  className="text-gray-400 hover:text-red-500"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-500">
                  {team.description || "No description"}
                </p>
                <p className="text-xs text-gray-400 mt-2">
                  {team.members?.length || 0} members
                </p>
              </CardContent>
            </Card>
          ))}

          {(!teams || teams.length === 0) && (
            <div className="col-span-2 text-center py-12 text-gray-500">
              No teams yet. Create one to get started.
            </div>
          )}
        </div>
      </div>

      <Dialog open={showCreate} onClose={() => setShowCreate(false)} title="Create Team">
        <div className="space-y-4">
          <Input
            placeholder="Team name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Button
            className="w-full"
            disabled={!name}
            loading={createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            Create
          </Button>
        </div>
      </Dialog>
    </AppShell>
  );
}
