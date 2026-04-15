import { v4 as uuid } from 'uuid';
import { getDb } from '../storage.js';

const TEMPLATES: Record<string, string[]> = {
  'sox-quarterly': ['Review financial statements', 'Verify internal controls', 'Test access controls', 'Document exceptions', 'Management sign-off'],
  'gdpr-audit': ['Data inventory check', 'Consent mechanisms review', 'DPIA completion', 'Breach procedure test', 'DPO sign-off'],
  'hipaa-review': ['PHI access audit', 'Encryption verification', 'BAA review', 'Training records check', 'Incident response test'],
};

export function createChecklist(name: string, template?: string) {
  const db = getDb();
  const id = uuid();
  db.prepare('INSERT INTO compliance_checklists (id, name, template) VALUES (?, ?, ?)').run(id, name, template || null);
  if (template && template in TEMPLATES) {
    const items = TEMPLATES[template]!;
    const insert = db.prepare('INSERT INTO compliance_items (id, checklist_id, description) VALUES (?, ?, ?)');
    for (const desc of items) {
      insert.run(uuid(), id, desc);
    }
  }
  return { id, name, template, items: template && template in TEMPLATES ? TEMPLATES[template]!.length : 0 };
}

export function updateItem(itemId: string, updates: { status?: string; assignee?: string; notes?: string }) {
  const db = getDb();
  const sets: string[] = ["updated_at = datetime('now')"];
  const vals: any[] = [];
  if (updates.status) { sets.push('status = ?'); vals.push(updates.status); }
  if (updates.assignee) { sets.push('assignee = ?'); vals.push(updates.assignee); }
  if (updates.notes) { sets.push('notes = ?'); vals.push(updates.notes); }
  vals.push(itemId);
  db.prepare(`UPDATE compliance_items SET ${sets.join(', ')} WHERE id = ?`).run(...vals);
  return db.prepare('SELECT * FROM compliance_items WHERE id = ?').get(itemId);
}

export function getStatus(checklistId: string) {
  const db = getDb();
  const checklist = db.prepare('SELECT * FROM compliance_checklists WHERE id = ?').get(checklistId) as any;
  const items = db.prepare('SELECT * FROM compliance_items WHERE checklist_id = ?').all(checklistId) as any[];
  const total = items.length;
  const completed = items.filter(i => i.status === 'completed').length;
  return { ...checklist, items, progress: total ? Math.round((completed / total) * 100) : 0 };
}

export function generateReport(checklistId: string) {
  const status = getStatus(checklistId);
  const pending = status.items.filter((i: any) => i.status === 'pending');
  const failed = status.items.filter((i: any) => i.status === 'failed');
  return {
    checklist: status.name,
    progress: `${status.progress}%`,
    total_items: status.items.length,
    completed: status.items.filter((i: any) => i.status === 'completed').length,
    pending: pending.length,
    failed: failed.length,
    risk_items: failed.map((i: any) => i.description),
    generated_at: new Date().toISOString(),
  };
}

export const templates = Object.keys(TEMPLATES);
