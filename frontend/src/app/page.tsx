"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { PageLoading } from "@/components/ui/spinner";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      router.push(user ? "/meetings" : "/login");
    }
  }, [user, loading, router]);

  return <PageLoading />;
}
