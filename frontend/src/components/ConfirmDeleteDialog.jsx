import React from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export default function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  testId,
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        className="glass-strong border-white/10 text-twt-text"
        data-testid={testId}
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="text-display text-3xl">
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-twt-muted">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            className="bg-transparent border-white/10 text-twt-text hover:bg-white/5"
            data-testid={`${testId}-cancel`}
          >
            Keep it
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-twt-rose hover:bg-twt-rose/90 text-white"
            data-testid={`${testId}-confirm`}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
