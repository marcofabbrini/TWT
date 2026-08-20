export const ROLE_RANK = { viewer: 1, editor: 2, owner: 3 };

export function canEdit(role) {
  return ROLE_RANK[role] >= ROLE_RANK.editor;
}

export function canDelete(role) {
  return canEdit(role);
}

export function roleLabel(role) {
  return role?.charAt(0).toUpperCase() + role?.slice(1);
}
