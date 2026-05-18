"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { PageLoading } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { Search, FileText } from "lucide-react";
import { useRouter } from "next/navigation";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const router = useRouter();

  const { data, isLoading } = useQuery({
    queryKey: ["search", searchQuery],
    queryFn: () => api.search(searchQuery),
    enabled: searchQuery.length > 0,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) setSearchQuery(query.trim());
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Search</h1>

        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            placeholder="Search transcripts, summaries, titles..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1"
          />
          <Button type="submit">
            <Search className="h-4 w-4 mr-2" />
            Search
          </Button>
        </form>

        {isLoading && <PageLoading />}

        {data && (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">
              {data.total} result{data.total !== 1 ? "s" : ""} for &ldquo;{searchQuery}&rdquo;
            </p>

            {data.items.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <FileText className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                <p>No results found</p>
              </div>
            ) : (
              data.items.map((item) => (
                <Card
                  key={item.meeting_id}
                  className="cursor-pointer hover:border-blue-200 transition-colors"
                  onClick={() => router.push(`/meetings/${item.meeting_id}`)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-medium text-gray-900">
                        {item.title || "Untitled"}
                      </h3>
                      <StatusBadge status={item.status} />
                    </div>
                    <p className="text-sm text-gray-600 line-clamp-2">
                      {item.matched_text}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
                        {item.match_type}
                      </span>
                      {item.date && (
                        <span className="text-xs text-gray-400">
                          {new Date(item.date).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
