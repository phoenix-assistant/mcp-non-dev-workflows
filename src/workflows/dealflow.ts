import { v4 as uuid } from 'uuid';
import { getDb } from '../storage.js';

const STAGES = ['prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost'];

export function addDeal(name: string, opts: { company?: string; value?: number; owner?: string; stage?: string } = {}) {
  const db = getDb();
  const id = uuid();
  db.prepare('INSERT INTO deals (id, name, company, value, stage, owner) VALUES (?, ?, ?, ?, ?, ?)')
    .run(id, name, opts.company || null, opts.value || 0, opts.stage || 'prospecting', opts.owner || null);
  return { id, name, ...opts, stage: opts.stage || 'prospecting' };
}

export function updateStage(dealId: string, stage: string) {
  if (!STAGES.includes(stage)) throw new Error(`Invalid stage. Must be one of: ${STAGES.join(', ')}`);
  const db = getDb();
  db.prepare("UPDATE deals SET stage = ?, updated_at = datetime('now') WHERE id = ?").run(stage, dealId);
  return db.prepare('SELECT * FROM deals WHERE id = ?').get(dealId);
}

export function getPipeline(filters?: { stage?: string; owner?: string }) {
  const db = getDb();
  let sql = 'SELECT * FROM deals WHERE 1=1';
  const params: any[] = [];
  if (filters?.stage) { sql += ' AND stage = ?'; params.push(filters.stage); }
  if (filters?.owner) { sql += ' AND owner = ?'; params.push(filters.owner); }
  sql += ' ORDER BY updated_at DESC';
  const deals = db.prepare(sql).all(...params) as any[];
  const totalValue = deals.reduce((s, d) => s + (d.value || 0), 0);
  return { deals, count: deals.length, total_value: totalValue };
}

export function addNote(dealId: string, content: string, author?: string) {
  const db = getDb();
  const id = uuid();
  db.prepare('INSERT INTO deal_notes (id, deal_id, content, author) VALUES (?, ?, ?, ?)').run(id, dealId, content, author || null);
  return { id, deal_id: dealId, content, author };
}

export { STAGES };
