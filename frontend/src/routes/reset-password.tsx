import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/reset-password")({
  head: () => ({
    meta: [
      { title: "Reset Password — CloudWise" },
      { name: "description", content: "Choose a new password for your CloudWise account." },
      { property: "og:title", content: "Reset Password — CloudWise" },
      { property: "og:description", content: "Set a new password for your CloudWise account." },
    ],
  }),
  component: ResetPasswordPage,
});

function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!z.string().min(6).max(72).safeParse(password).success) {
      setError("Password must be at least 6 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }

    setBusy(true);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setBusy(false);

    if (updateError) {
      setError(updateError.message);
      toast.error(updateError.message);
      return;
    }

    toast.success("Password updated. You can now use it to log in.");
    void navigate({ to: "/dashboard", replace: true });
  }

  return (
    <PageShell withFooter={false}>
      <div className="bg-gradient-soft">
        <div className="mx-auto max-w-md px-4 py-20 sm:px-6">
          <Card className="rounded-3xl border-border/70 shadow-lift">
            <CardContent className="p-6 sm:p-8">
              <h1 className="text-2xl font-bold tracking-tight">Set a new password</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Open this page from the reset link in your email, then choose a new password.
              </p>

              {error && (
                <div className="mt-5 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm">
                  {error}
                </div>
              )}

              <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
                <div className="space-y-2">
                  <Label htmlFor="new-password">New password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="rounded-xl"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Confirm new password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="rounded-xl"
                  />
                </div>
                <Button type="submit" disabled={busy} className="w-full rounded-xl bg-gradient-hero">
                  {busy ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Updating…
                    </>
                  ) : (
                    "Update password"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}