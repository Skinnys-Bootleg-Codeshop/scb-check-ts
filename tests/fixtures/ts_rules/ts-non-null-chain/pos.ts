declare const user: { profile?: { name?: string } };
export const name = user.profile!.name!.length; // HIT
