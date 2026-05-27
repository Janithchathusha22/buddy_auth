const trackedRoles = ["student", "admin", "super_admin"];
const primaryRolePriority = ["super_admin", "admin", "student"];

export function normalizePresenceStatus(user) {
  return user?.presence_status === "online" ? "online" : "offline";
}

export function presenceBadgeClass(status) {
  return normalizePresenceStatus({ presence_status: status });
}

export function formatPresenceLabel(status) {
  return status === "online" ? "Online" : "Offline";
}

export function formatLastSeen(value) {
  if (!value) {
    return "Never seen";
  }

  const seenAt = new Date(value);
  if (Number.isNaN(seenAt.getTime())) {
    return "Unknown last seen";
  }

  const secondsAgo = Math.max(0, Math.floor((Date.now() - seenAt.getTime()) / 1000));
  if (secondsAgo < 10) {
    return "Just now";
  }

  if (secondsAgo < 60) {
    return `${secondsAgo}s ago`;
  }

  const minutesAgo = Math.floor(secondsAgo / 60);
  if (minutesAgo < 60) {
    return `${minutesAgo}m ago`;
  }

  const hoursAgo = Math.floor(minutesAgo / 60);
  if (hoursAgo < 24) {
    return `${hoursAgo}h ago`;
  }

  return seenAt.toLocaleString();
}

export function primaryRoleForUser(user) {
  const roles = Array.isArray(user?.roles) ? user.roles : [];
  return (
    primaryRolePriority.find((role) => roles.includes(role)) ||
    (trackedRoles.includes(user?.requested_role) ? user.requested_role : "student")
  );
}

export function summarizePresenceByRole(users) {
  const summary = Object.fromEntries(
    trackedRoles.map((role) => [role, { online: 0, offline: 0 }])
  );

  users.forEach((user) => {
    const role = primaryRoleForUser(user);
    const status = normalizePresenceStatus(user);
    summary[role][status] += 1;
  });

  return summary;
}
