import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { List } from "lucide-react";

/**
 * Wraps the (existing) stops timeline + CRUD flows inside a full-screen dialog.
 * The child slot receives the untouched stops timeline JSX from Trip.jsx.
 */
export default function ManageStopsDialog({ open, onOpenChange, children }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="glass-strong border-white/10 sm:max-w-3xl max-h-[90vh] overflow-y-auto text-twt-text"
        data-testid="manage-stops-dialog"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-2xl flex items-center gap-2">
            <List className="w-4 h-4 text-twt-teal" />
            Manage stops
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            Add, edit, reorder or remove the stops in your trip. Attractions
            and expenses are managed from the day tabs.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4">{children}</div>
      </DialogContent>
    </Dialog>
  );
}
