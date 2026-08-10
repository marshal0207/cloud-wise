import { Link } from "@tanstack/react-router";
import { CloudCog } from "lucide-react";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link to="/" className={`flex min-w-0 items-center gap-2 ${className}`}>
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-hero text-primary-foreground shadow-soft">
        <CloudCog className="h-5 w-5" />
      </span>
      <span className="truncate text-lg font-bold tracking-tight">CloudWise</span>
    </Link>
  );
}