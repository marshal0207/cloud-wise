import { Link, useNavigate } from "@tanstack/react-router";
import { CloudCog, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { supabase } from "@/integrations/supabase/client";

const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address").max(255),
  password: z.string().min(6, "Password must be at least 6 characters").max(72),
});

const signupSchema = loginSchema
  .extend({
    fullName: z.string().trim().min(2, "Please enter your full name").max(100),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match",
  });

type Mode = "login" | "signup";
type Fields = { fullName: string; email: string; password: string; confirmPassword: string };

const emptyFields: Fields = { fullName: "", email: "", password: "", confirmPassword: "" };

export function AuthCard({ mode }: { mode: Mode }) {
  const [fields, setFields] = useState<Fields>(emptyFields);
  const [errors, setErrors] = useState<Partial<Record<keyof Fields, string>>>({});
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && user) void navigate({ to: "/dashboard", replace: true });
  }, [user, loading, navigate]);

  function update(field: keyof Fields, value: string) {
    setFields((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  }

  function collectErrors(issues: z.ZodIssue[]) {
    const next: Partial<Record<keyof Fields, string>> = {};
    for (const issue of issues) {
      const key = issue.path[0] as keyof Fields;
      if (key && !next[key]) next[key] = issue.message;
    }
    setErrors(next);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setNotice(null);

    if (mode === "login") {
      const parsed = loginSchema.safeParse(fields);
      if (!parsed.success) return collectErrors(parsed.error.issues);

      setBusy(true);
      const { error } = await supabase.auth.signInWithPassword(parsed.data);
      setBusy(false);

      if (error) {
        toast.error(error.message || "Unable to log in");
        setNotice(error.message);
        return;
      }
      toast.success("Welcome back to CloudWise!");
      void navigate({ to: "/dashboard", replace: true });
      return;
    }

    const parsed = signupSchema.safeParse(fields);
    if (!parsed.success) return collectErrors(parsed.error.issues);

    setBusy(true);
    const { data, error } = await supabase.auth.signUp({
      email: parsed.data.email,
      password: parsed.data.password,
      options: {
        emailRedirectTo: window.location.origin,
        data: { full_name: parsed.data.fullName },
      },
    });
    setBusy(false);

    if (error) {
      toast.error(error.message || "Unable to create your account");
      setNotice(error.message);
      return;
    }

    if (!data.session) {
      setNotice("Account created. Please check your email to confirm your address, then log in.");
      toast.success("Account created — check your email to confirm");
      return;
    }

    toast.success("Account created. Welcome to CloudWise!");
    void navigate({ to: "/dashboard", replace: true });
  }

  async function handleForgotPassword() {
    const email = fields.email.trim();
    if (!z.string().email().safeParse(email).success) {
      setErrors((prev) => ({ ...prev, email: "Enter your email first to reset your password" }));
      return;
    }
    setBusy(true);
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    setBusy(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    toast.success("Password reset link sent to your email");
  }

  const isLogin = mode === "login";

  return (
    <div className="mx-auto grid w-full max-w-5xl items-center gap-10 px-4 py-14 sm:px-6 lg:grid-cols-2 lg:gap-16">
      <div className="hidden lg:block">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-hero text-primary-foreground shadow-soft">
          <CloudCog className="h-6 w-6" />
        </span>
        <h2 className="mt-6 text-3xl font-bold tracking-tight">
          Your cloud, <span className="text-gradient">clearly explained</span>
        </h2>
        <p className="mt-4 max-w-md leading-relaxed text-muted-foreground">
          CloudWise brings your resources, usage patterns, performance signals and estimated costs
          into one calm dashboard — so decisions are based on data, not guesswork.
        </p>
        <ul className="mt-8 space-y-3 text-sm text-muted-foreground">
          {[
            "Monitor resource status at a glance",
            "Track usage trends over time",
            "Spot unnecessary cloud spend early",
          ].map((item) => (
            <li key={item} className="flex items-center gap-3">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gradient-hero" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <Card className="rounded-3xl border-border/70 shadow-lift">
        <CardContent className="p-6 sm:p-8">
          <h1 className="text-2xl font-bold tracking-tight">
            {isLogin ? "Log in to CloudWise" : "Create your CloudWise account"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isLogin
              ? "Enter your details to open your dashboard."
              : "It takes less than a minute to get started."}
          </p>

          {notice && (
            <div className="mt-5 rounded-xl border border-border bg-secondary/70 p-3 text-sm">{notice}</div>
          )}

          <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
            {!isLogin && (
              <div className="space-y-2">
                <Label htmlFor="fullName">Full Name</Label>
                <Input
                  id="fullName"
                  value={fields.fullName}
                  onChange={(e) => update("fullName", e.target.value)}
                  placeholder="Your full name"
                  className="rounded-xl"
                />
                {errors.fullName && <p className="text-xs text-destructive">{errors.fullName}</p>}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={fields.email}
                onChange={(e) => update("email", e.target.value)}
                placeholder="you@example.com"
                className="rounded-xl"
              />
              {errors.email && <p className="text-xs text-destructive">{errors.email}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={isLogin ? "current-password" : "new-password"}
                value={fields.password}
                onChange={(e) => update("password", e.target.value)}
                placeholder="••••••••"
                className="rounded-xl"
              />
              {errors.password && <p className="text-xs text-destructive">{errors.password}</p>}
            </div>

            {!isLogin && (
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm Password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  value={fields.confirmPassword}
                  onChange={(e) => update("confirmPassword", e.target.value)}
                  placeholder="••••••••"
                  className="rounded-xl"
                />
                {errors.confirmPassword && (
                  <p className="text-xs text-destructive">{errors.confirmPassword}</p>
                )}
              </div>
            )}

            {isLogin && (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Checkbox
                    checked={remember}
                    onCheckedChange={(value) => setRemember(value === true)}
                  />
                  Remember me
                </label>
                <button
                  type="button"
                  onClick={() => void handleForgotPassword()}
                  className="text-sm font-medium text-primary transition-colors hover:text-primary-glow"
                >
                  Forgot password?
                </button>
              </div>
            )}

            <Button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-gradient-hero shadow-soft transition-shadow hover:shadow-lift"
            >
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isLogin ? "Logging in…" : "Creating account…"}
                </>
              ) : isLogin ? (
                "Login"
              ) : (
                "Create Account"
              )}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isLogin ? (
              <>
                New to CloudWise?{" "}
                <Link to="/signup" className="font-medium text-primary hover:text-primary-glow">
                  Sign up
                </Link>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <Link to="/login" className="font-medium text-primary hover:text-primary-glow">
                  Log in
                </Link>
              </>
            )}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}