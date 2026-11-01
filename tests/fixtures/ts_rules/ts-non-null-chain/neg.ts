declare const user: { profile?: { name?: string } };
export const profile = user.profile!.name;
export const safe = user.profile?.name?.length;
