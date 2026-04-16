"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Bell, Mail, Send, TestTube2, Save } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { getAlertConfig } from "@/lib/api";
import type { AlertConfig } from "@/types";

async function saveAlertConfig(config: AlertConfig): Promise<void> {
  const { updateAlertConfig } = await import("@/lib/api");
  return updateAlertConfig(config) as unknown as void;
}

async function doTestEmail(): Promise<void> {
  const { testEmail } = await import("@/lib/api");
  return testEmail() as unknown as void;
}

async function doTestTelegram(): Promise<void> {
  const { testTelegram } = await import("@/lib/api");
  return testTelegram() as unknown as void;
}

export default function AlertsPage() {
  const { data: config, isLoading } = useSWR<AlertConfig>(
    "alert-config",
    getAlertConfig
  );

  // Email
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");

  // Telegram
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState("");

  // Triggers
  const [tradeExecuted, setTradeExecuted] = useState(true);
  const [drawdownThreshold, setDrawdownThreshold] = useState("10");
  const [profitTarget, setProfitTarget] = useState("5");

  const [saving, setSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);
  const [testingTelegram, setTestingTelegram] = useState(false);

  useEffect(() => {
    if (config) {
      setEmailEnabled(config.email_enabled ?? false);
      setSmtpHost(config.smtp_host ?? "");
      setSmtpPort(String(config.smtp_port ?? 587));
      setSmtpUser(config.smtp_user ?? "");
      setSmtpPass(config.smtp_pass ?? "");
      setRecipientEmail(config.recipient_email ?? "");
      setTelegramEnabled(config.telegram_enabled ?? false);
      setBotToken(config.telegram_bot_token ?? "");
      setChatId(config.telegram_chat_id ?? "");
      setTradeExecuted(config.on_trade_executed ?? true);
      setDrawdownThreshold(String(config.drawdown_threshold ?? 10));
      setProfitTarget(String(config.profit_target ?? 5));
    }
  }, [config]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveAlertConfig({
        email_enabled: emailEnabled,
        smtp_host: smtpHost,
        smtp_port: parseInt(smtpPort, 10),
        smtp_user: smtpUser,
        smtp_pass: smtpPass,
        recipient_email: recipientEmail,
        telegram_enabled: telegramEnabled,
        telegram_bot_token: botToken,
        telegram_chat_id: chatId,
        on_trade_executed: tradeExecuted,
        drawdown_threshold: parseFloat(drawdownThreshold),
        profit_target: parseFloat(profitTarget),
      });
      toast.success("Alert settings saved");
    } catch {
      toast.error("Failed to save alert settings");
    } finally {
      setSaving(false);
    }
  };

  const handleTestEmail = async () => {
    setTestingEmail(true);
    try {
      await doTestEmail();
      toast.success("Test email sent successfully");
    } catch {
      toast.error("Failed to send test email");
    } finally {
      setTestingEmail(false);
    }
  };

  const handleTestTelegram = async () => {
    setTestingTelegram(true);
    try {
      await doTestTelegram();
      toast.success("Test Telegram message sent");
    } catch {
      toast.error("Failed to send test Telegram message");
    } finally {
      setTestingTelegram(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Alert Settings
          </h2>
          <p className="text-sm text-muted-foreground">Loading configuration...</p>
        </div>
        <div className="animate-pulse space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="border-border/50 bg-card">
              <CardContent className="p-6">
                <div className="h-32 rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Alert Settings
          </h2>
          <p className="text-sm text-muted-foreground">
            Configure notifications for trading events
          </p>
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <span className="flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              Saving...
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <Save className="h-4 w-4" />
              Save Settings
            </span>
          )}
        </Button>
      </div>

      {/* Email Section */}
      <Card className="border-border/50 bg-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Mail className="h-4 w-4 text-primary" />
              Email Notifications
            </CardTitle>
            <Switch checked={emailEnabled} onCheckedChange={setEmailEnabled} />
          </div>
        </CardHeader>
        {emailEnabled && (
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="smtp-host">SMTP Host</Label>
                <Input
                  id="smtp-host"
                  value={smtpHost}
                  onChange={(e) => setSmtpHost(e.target.value)}
                  placeholder="smtp.gmail.com"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="smtp-port">SMTP Port</Label>
                <Input
                  id="smtp-port"
                  type="number"
                  value={smtpPort}
                  onChange={(e) => setSmtpPort(e.target.value)}
                  placeholder="587"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="smtp-user">SMTP Username</Label>
                <Input
                  id="smtp-user"
                  value={smtpUser}
                  onChange={(e) => setSmtpUser(e.target.value)}
                  placeholder="your@email.com"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="smtp-pass">SMTP Password</Label>
                <Input
                  id="smtp-pass"
                  type="password"
                  value={smtpPass}
                  onChange={(e) => setSmtpPass(e.target.value)}
                  placeholder="App password"
                />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="recipient">Recipient Email</Label>
              <Input
                id="recipient"
                type="email"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                placeholder="alerts@example.com"
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestEmail}
              disabled={testingEmail}
            >
              <TestTube2 className="mr-2 h-4 w-4" />
              {testingEmail ? "Sending..." : "Send Test Email"}
            </Button>
          </CardContent>
        )}
      </Card>

      {/* Telegram Section */}
      <Card className="border-border/50 bg-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Send className="h-4 w-4 text-primary" />
              Telegram Notifications
            </CardTitle>
            <Switch
              checked={telegramEnabled}
              onCheckedChange={setTelegramEnabled}
            />
          </div>
        </CardHeader>
        {telegramEnabled && (
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="bot-token">Bot Token</Label>
              <Input
                id="bot-token"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="chat-id">Chat ID</Label>
              <Input
                id="chat-id"
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
                placeholder="-1001234567890"
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestTelegram}
              disabled={testingTelegram}
            >
              <TestTube2 className="mr-2 h-4 w-4" />
              {testingTelegram ? "Sending..." : "Send Test Message"}
            </Button>
          </CardContent>
        )}
      </Card>

      {/* Triggers Section */}
      <Card className="border-border/50 bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bell className="h-4 w-4 text-primary" />
            Alert Triggers
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-border/50 p-4">
            <div>
              <p className="text-sm font-medium text-foreground">
                Trade Executed
              </p>
              <p className="text-xs text-muted-foreground">
                Notify when any bot executes a trade
              </p>
            </div>
            <Switch
              checked={tradeExecuted}
              onCheckedChange={setTradeExecuted}
            />
          </div>

          <Separator />

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dd-threshold">Drawdown Threshold (%)</Label>
              <Input
                id="dd-threshold"
                type="number"
                step="0.5"
                value={drawdownThreshold}
                onChange={(e) => setDrawdownThreshold(e.target.value)}
                placeholder="10"
              />
              <p className="text-xs text-muted-foreground">
                Alert when drawdown exceeds this value
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="profit-target">Profit Target (%)</Label>
              <Input
                id="profit-target"
                type="number"
                step="0.5"
                value={profitTarget}
                onChange={(e) => setProfitTarget(e.target.value)}
                placeholder="5"
              />
              <p className="text-xs text-muted-foreground">
                Alert when profit target is reached
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
