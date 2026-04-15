import { v4 as uuid } from 'uuid';
import { getDb } from '../storage.js';

export function createTicket(title: string, opts: { description?: string; priority?: string; customer?: string; assignee?: string } = {}) {
  const db = getDb();
  const id = uuid();
  db.prepare('INSERT INTO tickets (id, title, description, priority, customer, assignee) VALUES (?, ?, ?, ?, ?, ?)')
    .run(id, title, opts.description || null, opts.priority || 'medium', opts.customer || null, opts.assignee || null);
  return { id, title, ...opts, status: 'open', priority: opts.priority || 'medium' };
}

export function escalate(ticketId: string, reason?: string) {
  const db = getDb();
  const ticket = db.prepare('SELECT * FROM tickets WHERE id = ?').get(ticketId) as any;
  if (!ticket) throw new Error('Ticket not found');
  const newLevel = (ticket.escalation_level || 0) + 1;
  db.prepare("UPDATE tickets SET escalation_level = ?, status = 'escalated', updated_at = datetime('now') WHERE id = ?").run(newLevel, ticketId);
  return { ...ticket, escalation_level: newLevel, status: 'escalated', reason };
}

export function getQueue(filters?: { status?: string; priority?: string; assignee?: string }) {
  const db = getDb();
  let sql = 'SELECT * FROM tickets WHERE 1=1';
  const params: any[] = [];
  if (filters?.status) { sql += ' AND status = ?'; params.push(filters.status); }
  if (filters?.priority) { sql += ' AND priority = ?'; params.push(filters.priority); }
  if (filters?.assignee) { sql += ' AND assignee = ?'; params.push(filters.assignee); }
  sql += ' ORDER BY escalation_level DESC, created_at ASC';
  return db.prepare(sql).all(...params);
}

export function resolve(ticketId: string, resolution?: string) {
  const db = getDb();
  db.prepare("UPDATE tickets SET status = 'resolved', resolution = COALESCE(?, resolution), updated_at = datetime('now') WHERE id = ?")
    .run(resolution || null, ticketId);
  return db.prepare('SELECT * FROM tickets WHERE id = ?').get(ticketId);
}
