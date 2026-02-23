const KEY = "glucolens_offline_queue_v1";

export function loadQueue(){
  try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; }
}

export function pushQueue(item){
  const q = loadQueue();
  q.push({ ...item, queued_at: new Date().toISOString() });
  localStorage.setItem(KEY, JSON.stringify(q));
  return q.length;
}

export function clearQueue(){
  localStorage.removeItem(KEY);
}