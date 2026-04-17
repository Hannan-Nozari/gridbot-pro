"use client";

import { useState } from "react";
import { AlertTriangle, Power } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { killSwitch } from "@/lib/api";

export function KillSwitchButton() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleKill = async () => {
    setLoading(true);
    try {
      const result = await killSwitch();
      const count = result.bots_stopped?.length ?? 0;
      const errs = result.errors?.length ?? 0;
      if (count === 0 && errs === 0) {
        toast.info("No running bots to stop");
      } else if (errs > 0) {
        toast.warning(
          `Stopped ${count} bot(s). ${errs} failed — check logs.`
        );
      } else {
        toast.success(`Killed ${count} running bot(s)`, {
          description: "All trading has been halted.",
        });
      }
      setOpen(false);
    } catch (err) {
      toast.error("Kill switch failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger>
        <button
          type="button"
          className="flex h-9 items-center gap-1.5 rounded-xl border border-destructive/30 bg-destructive/10 px-3 text-xs font-semibold text-destructive transition-colors hover:border-destructive/50 hover:bg-destructive/20"
          title="Emergency: stop all bots"
        >
          <Power className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Kill Switch</span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" />
          </div>
          <DialogTitle className="text-center text-xl">
            Emergency Kill Switch
          </DialogTitle>
          <DialogDescription className="text-center">
            This will <strong className="text-destructive">immediately stop all running bots</strong>.
            Open orders will remain on the exchange — close them manually if
            needed.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-xl border border-border bg-muted/30 p-4 text-xs text-muted-foreground">
          <p className="font-semibold text-foreground">When to use this:</p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>Unexpected losses or strange behavior</li>
            <li>Market crashes / extreme volatility</li>
            <li>Before updating config or code</li>
            <li>End of trading session</li>
          </ul>
        </div>

        <DialogFooter className="flex gap-2 sm:gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            onClick={() => setOpen(false)}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            type="button"
            className="flex-1 bg-destructive text-white hover:bg-destructive/90"
            onClick={handleKill}
            disabled={loading}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Stopping...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Power className="h-4 w-4" />
                Kill All Bots
              </span>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
