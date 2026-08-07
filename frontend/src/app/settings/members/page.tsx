"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { format } from "date-fns";
import { UserPlus, Trash2, KeyRound } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { useMe } from "@/hooks/use-me";
import { useIsOwner } from "@/hooks/use-role";
import { ManageAccessDialog } from "@/components/settings/manage-access-dialog";

const inviteSchema = z.object({
  email: z.string().email("Invalid email"),
});
type InviteForm = z.infer<typeof inviteSchema>;

interface Member {
  membership_id: string;
  id?: string | null;
  name?: string | null;
  email: string;
  role: string;
  joined_at?: string | null;
  invite_pending?: boolean;
}

export default function MembersSettingsPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [manageAccess, setManageAccess] = useState<{ id: string; name: string } | null>(null);

  // Current user — to prevent self-removal
  const { data: me } = useMe();
  const currentUserId = me?.id;

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
    mutationFn: (membershipId: string) => orgApi.removeMember(membershipId),
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
            <Button size="sm" className="group" disabled={!isOwner} title={!isOwner ? "Owner only" : undefined} onClick={() => { setInviteOpen(true); setInviteSuccess(null); setInviteError(null); reset(); }}>
              <AnimatedIcon icon={UserPlus} motionPreset="pop" iconClassName="size-4" />
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
                  <TableHead className="text-right">Access</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.membership_id}>
                    <TableCell>
                      <div>
                        <p className="text-sm font-medium">{m.name ?? "—"}</p>
                        <p className="text-xs text-muted-foreground">{m.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={m.role === "owner" ? "bg-primary/10 text-primary" : undefined}
                      >
                        {m.role.charAt(0).toUpperCase() + m.role.slice(1)}
                      </Badge>
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
                      <div className="flex items-center justify-end gap-1">
                        {m.role === "owner" ? (
                          <span className="text-xs text-muted-foreground">All accounts</span>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!isOwner}
                            title={!isOwner ? "Owner only" : "Manage account access"}
                            className="group gap-1.5 text-xs"
                            onClick={() => setManageAccess({ id: m.membership_id, name: m.name ?? m.email })}
                          >
                            <AnimatedIcon icon={KeyRound} motionPreset="pop" iconClassName="size-3.5" />
                            Manage access
                          </Button>
                        )}
                        {m.id !== currentUserId && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            disabled={!isOwner}
                            title={!isOwner ? "Owner only" : "Remove member"}
                            className="group text-destructive hover:text-destructive"
                            onClick={() => setRemoveId(m.membership_id)}
                          >
                            <AnimatedIcon icon={Trash2} motionPreset="wiggle" iconClassName="size-3.5" />
                          </Button>
                        )}
                      </div>
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

      {/* Manage account access dialog */}
      <ManageAccessDialog
        membershipId={manageAccess?.id ?? null}
        memberName={manageAccess?.name ?? ""}
        open={!!manageAccess}
        onOpenChange={(o) => { if (!o) setManageAccess(null); }}
      />

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
