export function isLockedError(err){
  return err?.response?.status === 402;
}
export function lockedMessage(err){
  return err?.response?.data?.detail || "Subscription inactive. Please renew.";
}