"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { format } from "date-fns";
import { UserPlus, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { orgApi } from "@/lib/api/org";
import { authApi } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-keys";

const inviteSchema = z.object({
  email: z.string().email("Invalid email"),
});
type InviteForm = z.infer<typeof inviteSchema>;

interface Member {
  id: string;
  name?: string | null;
  email: string;
  role: string;
  joined_at?: string | null;
  invite_pending?: boolean;
}

export default function MembersSettingsPage() {
  const qc = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [removeId, setRemoveId] = useState<string | null>(null);

  // Current user — to prevent self-removal
  const { data: meRes } = useQuery({
    queryKey: queryKeys.me(),
    queryFn: () => authApi.me(),
    staleTime: 60 * 60 * 1000,
  });
  const currentUserId = (meRes?.data?.data as { id?: string } | undefined)?.id;

  const { data: membersRes, isLoading } = useQuery({
    queryKey: ["members"],
    queryFn: () => orgApi.members(),
    staleTime: 5 * 60 * 1000,
  });
  const members: Member[] = membersRes?.data?.data ?? [];

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<InviteForm>({ resolver: zodResolver(inviteSchema) });

  const inviteMutation = useMutation({
    mutationFn: (email: string) => orgApi.invite(email),
    onSuccess: (res) => {
      const msg = (res.data?.data as { message?: string })?.message ?? "Invite sent.";
      setInviteSuccess(msg);
      reset();
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setInviteError(typeof detail === "string" ? detail : "Failed to send invite.");
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => orgApi.removeMember(userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["members"] });
      setRemoveId(null);
    },
  });

  async function onInvite(values: InviteForm) {
    setInviteError(null);
    setInviteSuccess(null);
    await inviteMutation.mutateAsync(values.email);
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Members</CardTitle>
              <CardDescription>Manage who has access to this organization.</CardDescription>
            </div>
            <Button size="sm" onClick={() => { setInviteOpen(true); setInviteSuccess(null); setInviteError(null); reset(); }}>
              <UserPlus className="size-4" />
              Invite member
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-px px-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-muted my-1" />
              ))}
            </div>
          ) : members.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">No members</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Member</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Joined</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>
                      <div>
                        <p className="text-sm font-medium">{m.name ?? "—"}</p>
                        <p className="text-xs text-muted-foreground">{m.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        m.role === "owner"
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground"
                      }`}>
                        {m.role.charAt(0).toUpperCase() + m.role.slice(1)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">
                        {m.invite_pending ? (
                          <span className="text-muted-foreground">Pending invite</span>
                        ) : (
                          <span className="text-green-600">Joined</span>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {m.joined_at ? format(new Date(m.joined_at), "MMM d, yyyy") : "—"}
                    </TableCell>
                    <TableCell>
                      {m.id !== currentUserId && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setRemoveId(m.id)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Invite dialog */}
      <Dialog open={inviteOpen} onOpenChange={(o) => { setInviteOpen(o); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite member</DialogTitle>
            <DialogDescription>
              Send an email invitation. They&apos;ll join as a Member.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit(onInvite)} className="space-y-4">
            {inviteError && (
              <Alert variant="destructive">
                <AlertDescription>{inviteError}</AlertDescription>
              </Alert>
            )}
            {inviteSuccess && (
              <Alert>
                <AlertDescription>{inviteSuccess}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="invite-email">Email</Label>
              <Input
                id="invite-email"
                type="email"
                placeholder="teammate@company.com"
                {...register("email")}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email.message}</p>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setInviteOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Sending…" : "Send invite"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Remove confirm dialog */}
      <Dialog open={!!removeId} onOpenChange={(o) => { if (!o) setRemoveId(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove member</DialogTitle>
            <DialogDescription>
              This member will lose access to the organization immediately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoveId(null)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={removeMutation.isPending}
              onClick={() => removeId && removeMutation.mutate(removeId)}
            >
              {removeMutation.isPending ? "Removing…" : "Remove"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
