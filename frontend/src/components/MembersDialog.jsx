import React, { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import { Users, X, Copy, LogOut, Check, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import ConfirmDeleteDialog from "@/components/ConfirmDeleteDialog";

function Avatar({ user, size = 32 }) {
  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();
  if (user?.avatar_url)
    return <img src={user.avatar_url} alt="" className="rounded-full object-cover ring-1 ring-white/10" style={{ width: size, height: size }} />;
  return (
    <div
      className="rounded-full grid place-items-center bg-gradient-to-br from-twt-teal to-twt-teal-strong text-black font-bold text-xs"
      style={{ width: size, height: size }}
    >
      {initial}
    </div>
  );
}

export default function MembersDialog({ open, onOpenChange, tripId, isOwner, onChanged, onLeft }) {
  const { user: me } = useAuth();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "editor" });
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState(null);
  const [pendingRemove, setPendingRemove] = useState(null);
  const [pendingLeave, setPendingLeave] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/trips/${tripId}/members`);
      setMembers(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      load();
      setInviteResult(null);
      setInviteForm({ email: "", role: "editor" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const sendInvite = async (e) => {
    e.preventDefault();
    if (!inviteForm.email.trim()) return;
    setInviting(true);
    try {
      const { data } = await api.post(`/trips/${tripId}/invites`, {
        email: inviteForm.email.trim(),
        role: inviteForm.role,
      });
      setInviteResult(data);
      setInviteForm({ email: "", role: "editor" });
      await load();
      onChanged?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to invite");
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (member_id, role) => {
    try {
      await api.patch(`/trips/${tripId}/members/${member_id}`, { role });
      await load();
      onChanged?.();
      toast.success("Role updated");
    } catch (e) {
      toast.error("Could not update role");
    }
  };

  const confirmRemove = async () => {
    if (!pendingRemove) return;
    const id = pendingRemove.member_id;
    setPendingRemove(null);
    try {
      await api.delete(`/trips/${tripId}/members/${id}`);
      await load();
      onChanged?.();
      toast.success("Member removed");
    } catch (e) {
      toast.error("Could not remove");
    }
  };

  const confirmLeave = async () => {
    setPendingLeave(false);
    try {
      const { data } = await api.post(`/trips/${tripId}/leave`);
      toast.success("You left the trip");
      onLeft?.(data);
    } catch (e) {
      toast.error("Could not leave");
    }
  };

  const copyLink = async (url) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        // Fallback for insecure contexts / older browsers.
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      toast.success("Invite link copied");
    } catch (err) {
      toast.error("Copy blocked — long-press the link to copy manually");
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className="glass-strong border-white/10 sm:max-w-lg text-twt-text max-h-[90vh] overflow-y-auto"
          data-testid="members-dialog"
        >
          <DialogHeader>
            <DialogTitle className="text-display text-3xl flex items-center gap-2">
              <Users className="w-4 h-4 text-twt-teal" />
              Collaborators
            </DialogTitle>
            <DialogDescription className="text-twt-muted">
              {isOwner
                ? "Invite people with a copy-paste link. Emails come in a later phase."
                : "You are viewing this trip's crew."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 mt-3" data-testid="members-list">
            <AnimatePresence>
              {members.map((m) => (
                <motion.div
                  key={m.member_id}
                  layout
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="glass rounded-xl px-3 py-2 flex items-center gap-3"
                  data-testid={`member-row-${m.member_id}`}
                >
                  <Avatar user={m.user || { name: m.invited_email }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-bold truncate">
                      {m.user?.name || m.invited_email}
                    </div>
                    <div className="text-xs text-twt-muted flex items-center gap-2">
                      {m.user?.email || m.invited_email}
                      {m.status === "pending" && (
                        <span className="inline-flex items-center gap-1 text-twt-amber">
                          <Clock className="w-3 h-3" /> pending
                        </span>
                      )}
                    </div>
                  </div>
                  {isOwner && m.role !== "owner" && m.user?.user_id !== me?.user_id ? (
                    <Select
                      value={m.role}
                      onValueChange={(v) => changeRole(m.member_id, v)}
                    >
                      <SelectTrigger
                        className="w-28 bg-white/[0.03] border-white/10 h-8 text-xs"
                        data-testid={`member-role-select-${m.member_id}`}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass-strong border-white/10">
                        <SelectItem value="editor">Editor</SelectItem>
                        <SelectItem value="viewer">Viewer</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <span className="text-[10px] uppercase tracking-widest px-2 py-1 rounded-full border border-white/10 text-twt-muted">
                      {m.role}
                    </span>
                  )}
                  {isOwner && m.user?.user_id !== me?.user_id && (
                    <button
                      type="button"
                      onClick={() => setPendingRemove(m)}
                      className="p-1.5 rounded-md hover:bg-twt-rose/15 text-twt-muted hover:text-twt-rose"
                      data-testid={`member-remove-${m.member_id}`}
                      aria-label="Remove"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {isOwner && (
            <form onSubmit={sendInvite} className="mt-4 pt-4 border-t border-white/[0.06] space-y-2">
              <div className="text-[11px] uppercase tracking-widest text-twt-muted">
                Invite someone
              </div>
              <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
                <div>
                  <Label className="text-twt-muted text-[10px] uppercase tracking-widest">
                    Email
                  </Label>
                  <Input
                    type="email"
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                    placeholder="friend@example.com"
                    className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
                    data-testid="invite-email-input"
                  />
                </div>
                <Select
                  value={inviteForm.role}
                  onValueChange={(v) => setInviteForm({ ...inviteForm, role: v })}
                >
                  <SelectTrigger className="bg-white/[0.03] border-white/10 w-28" data-testid="invite-role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="glass-strong border-white/10">
                    <SelectItem value="editor">Editor</SelectItem>
                    <SelectItem value="viewer">Viewer</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  type="submit"
                  disabled={inviting}
                  className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
                  data-testid="invite-send-btn"
                >
                  {inviting ? "…" : "Invite"}
                </Button>
              </div>
              {inviteResult && (
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-3 glass rounded-xl p-3 space-y-2"
                  data-testid="invite-result"
                >
                  <div className="text-xs text-twt-muted">
                    Share this link with the invitee. Once they log in with{" "}
                    <span className="text-twt-teal">{inviteResult.invited_email}</span> and
                    accept, they will appear here.
                  </div>
                  <div className="flex items-center gap-2">
                    <code
                      className="flex-1 text-xs bg-black/40 rounded-md px-2 py-1.5 truncate"
                      data-testid="invite-link"
                    >
                      {inviteResult.invite_url}
                    </code>
                    <Button
                      type="button"
                      onClick={() => copyLink(inviteResult.invite_url)}
                      size="sm"
                      className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
                      data-testid="invite-copy-btn"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </motion.div>
              )}
            </form>
          )}

          {!isOwner && (
            <div className="mt-4 pt-4 border-t border-white/[0.06]">
              <Button
                type="button"
                onClick={() => setPendingLeave(true)}
                variant="ghost"
                className="text-twt-rose hover:text-twt-rose hover:bg-twt-rose/10 w-full"
                data-testid="leave-trip-btn"
              >
                <LogOut className="w-4 h-4 mr-2" />
                Leave this trip
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={!!pendingRemove}
        onOpenChange={(v) => !v && setPendingRemove(null)}
        onConfirm={confirmRemove}
        testId="member-remove-dialog"
        title="Remove this member?"
        description={
          pendingRemove
            ? `${pendingRemove.user?.name || pendingRemove.invited_email} will lose access to this trip.`
            : ""
        }
      />
      <ConfirmDeleteDialog
        open={pendingLeave}
        onOpenChange={setPendingLeave}
        onConfirm={confirmLeave}
        testId="leave-trip-dialog"
        title="Leave this trip?"
        description="You'll lose access immediately. The owner can re-invite you later."
      />
    </>
  );
}
