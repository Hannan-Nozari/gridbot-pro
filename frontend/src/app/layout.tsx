"use client";

import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Bot,
  FlaskConical,
  BarChart3,
  ArrowLeftRight,
  Bell,
  Settings,
  LogOut,
  Lock,
  Search,
  Zap,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Toaster } from "@/components/ui/sonner";
import { useAuth } from "@/hooks/useAuth";
import { KillSwitchButton } from "@/components/kill-switch";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const navSections = [
  {
    label: "Main",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/bots", label: "My Bots", icon: Bot },
      { href: "/trades", label: "Trades", icon: ArrowLeftRight },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/backtest", label: "Backtester", icon: FlaskConical },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/alerts", label: "Alerts", icon: Bell },
      { href: "/config", label: "Config", icon: Settings },
    ],
  },
];

function LoginForm() {
  const { login } = useAuth();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(password);
    } catch {
      setError("Invalid credentials. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      {/* Radial glow backdrop */}
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(255, 77, 21, 0.08) 0%, transparent 60%)",
        }}
      />

      <Card className="relative w-full max-w-md border-border bg-card elevated">
        <CardHeader className="space-y-4 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl brand-gradient brand-glow">
              <Zap className="h-5 w-5 text-white" strokeWidth={2.5} />
            </div>
            <div>
              <CardTitle className="text-xl font-bold tracking-tight text-foreground">
                GridBot Pro
              </CardTitle>
              <p className="text-xs text-muted-foreground">
                Premium Trading Platform
              </p>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Sign in to access your trading dashboard
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Access Key
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="h-11 border-border bg-muted/50 text-foreground placeholder:text-muted-foreground/50"
                required
                autoFocus
              />
            </div>
            {error && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}
            <Button
              type="submit"
              className="h-11 w-full brand-gradient font-semibold text-white hover:opacity-90"
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Authenticating...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Lock className="h-4 w-4" />
                  Sign In
                </span>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function Sidebar() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-60 flex-col border-r border-sidebar-border bg-sidebar">
      {/* Brand */}
      <div className="flex h-16 items-center gap-3 px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl brand-gradient">
          <Zap className="h-4 w-4 text-white" strokeWidth={2.5} />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-bold tracking-tight text-foreground">
            GridBot Pro
          </span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Trading Platform
          </span>
        </div>
      </div>

      {/* Nav sections */}
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {navSections.map((section) => (
          <div key={section.label} className="space-y-1">
            <p className="px-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              {section.label}
            </p>
            {section.items.map((item) => {
              const isActive =
                pathname === item.href || pathname?.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
                    isActive
                      ? "bg-brand-muted text-foreground"
                      : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
                  }`}
                >
                  {isActive && (
                    <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand" />
                  )}
                  <item.icon
                    className={`h-4 w-4 transition-colors ${
                      isActive ? "text-brand" : "text-muted-foreground group-hover:text-foreground"
                    }`}
                    strokeWidth={isActive ? 2.5 : 2}
                  />
                  <span className="flex-1">{item.label}</span>
                  {isActive && (
                    <ChevronRight className="h-3.5 w-3.5 text-brand" />
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Upgrade Card */}
      <div className="mx-3 mb-3 rounded-2xl border border-brand/20 bg-gradient-to-br from-brand/10 to-brand/5 p-4">
        <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg brand-gradient">
          <Zap className="h-4 w-4 text-white" />
        </div>
        <p className="text-sm font-semibold text-foreground">Live Trading</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Connect your Binance keys to trade with real funds.
        </p>
        <Link
          href="/config"
          className="mt-3 block rounded-lg bg-brand px-3 py-1.5 text-center text-xs font-semibold text-white transition-opacity hover:opacity-90"
        >
          Configure
        </Link>
      </div>

      {/* Sign out */}
      <div className="border-t border-sidebar-border p-3">
        <button
          onClick={() => logout()}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent/50 hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}

function AppHeader() {
  const pathname = usePathname();
  const pageName =
    pathname === "/dashboard"
      ? "Dashboard"
      : pathname?.split("/").filter(Boolean)[0]?.replace(/^\w/, (c) => c.toUpperCase()) || "Dashboard";

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/80 px-8 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground">Pages</span>
        <ChevronRight className="h-3 w-3 text-muted-foreground" />
        <span className="text-sm font-semibold text-foreground">{pageName}</span>
      </div>

      <div className="flex items-center gap-3">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            placeholder="Search..."
            className="h-9 w-64 rounded-xl border border-border bg-muted/30 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand/50 focus:outline-none focus:ring-2 focus:ring-brand/20"
          />
        </div>

        {/* Live indicator */}
        <div className="flex items-center gap-2 rounded-xl border border-profit/20 bg-profit/10 px-3 py-1.5">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-profit opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-profit" />
          </span>
          <span className="text-xs font-medium text-profit">Live</span>
        </div>

        {/* Emergency Kill Switch */}
        <KillSwitchButton />

        {/* Avatar */}
        <div className="flex h-9 w-9 items-center justify-center rounded-xl brand-gradient text-sm font-bold text-white">
          H
        </div>
      </div>
    </header>
  );
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { isAuthenticated } = useAuth();

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full">
        {!isAuthenticated ? (
          <LoginForm />
        ) : (
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex flex-1 flex-col pl-60">
              <AppHeader />
              <main className="flex-1 p-8">{children}</main>
            </div>
          </div>
        )}
        <Toaster />
      </body>
    </html>
  );
}
